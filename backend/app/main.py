"""FastAPI application: autograder interface (/audit/v1/*), production API (/api/v1/*), realtime WebSocket."""
import asyncio
import base64
import json
import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from . import fixtures, rbac, roster, scoring, sports, standings, store, sync
from .state import State
from .util import ApiError, is_int, validation_error

logging.basicConfig(level=logging.INFO)
MAX_BODY = 1024 * 1024
RATE_LIMIT, RATE_WINDOW = 100, 10.0

app = FastAPI(title="NaSCon League & Club Operations Platform", version="1.0.0")
state = State()


def ok(body, status=200):
    return JSONResponse(body, status_code=status)


def err(e: ApiError):
    return JSONResponse(e.body(), status_code=e.status, headers=e.headers)


@app.exception_handler(ApiError)
async def api_error_handler(request, exc: ApiError):
    return err(exc)


@app.exception_handler(Exception)
async def unhandled(request, exc):  # pragma: no cover - safety net, never leak a raw 500 page
    logging.exception("unhandled error")
    return JSONResponse({"error": {"code": "INTERNAL_ERROR", "message": "Unexpected server error.", "details": {}}},
                        status_code=500)


_hits = defaultdict(deque)


def rate_limited(ip):
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] >= RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        retry = max(1, int(RATE_WINDOW - (now - q[0])) + 1)
        return retry
    q.append(now)
    return None


@app.middleware("http")
async def guard(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return err(ApiError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.", {"limit_bytes": MAX_BODY}))
    if request.url.path.startswith("/api/v1/"):
        ip = request.client.host if request.client else "unknown"
        retry = rate_limited(ip)
        if retry is not None:
            e = ApiError(429, "RATE_LIMITED", "Too many requests. Please slow down.", {"retry_after_seconds": retry},
                         headers={"Retry-After": str(retry)})
            return err(e)
    return await call_next(request)


async def read_json(request: Request, optional=False):
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.", {"limit_bytes": MAX_BODY})
    if not raw.strip():
        if optional:
            return {}
        raise validation_error("body", "Request body is required.")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise validation_error("body", "Malformed JSON.")


@app.on_event("startup")
async def startup():
    loop = asyncio.get_running_loop()
    hub.loop = loop
    state.listeners.append(hub.publish)
    await loop.run_in_executor(None, state.init_db)
    with state.lock:
        state.reset()


# ============================================================================ health + reset

@app.get("/health")
async def health():
    if await asyncio.get_running_loop().run_in_executor(None, state.healthy):
        return ok({"status": "ok"})
    return ok({"status": "unavailable"}, 503)


@app.post("/audit/v1/reset")
async def reset(request: Request):
    body = await read_json(request, optional=True)
    if not isinstance(body, dict):
        raise validation_error("body")
    seed = body.get("seed", 42)
    if seed is None:
        seed = 42
    stock = body.get("stock") or {}
    if not is_int(seed):
        raise validation_error("seed")
    if not isinstance(stock, dict) or not all(isinstance(k, str) and is_int(v) and v >= 0 for k, v in stock.items()):
        raise validation_error("stock")
    with state.lock:
        echoed = state.reset(seed, stock)
    return ok({"status": "reset_complete", "seed": seed, "sports": ["football", "basketball", "cricket", "esports"],
               "tenants": ["tenant-alpha", "tenant-beta"], "stock": echoed})


# ============================================================================ sports / fixtures / leagues

@app.post("/audit/v1/sports")
async def create_sport(request: Request):
    body = await read_json(request)
    with state.lock:
        return ok(sports.create_sport(state, body), 201)


@app.post("/audit/v1/fixtures")
async def gen_fixtures(request: Request):
    body = await read_json(request)
    return ok(fixtures.generate(body))


@app.post("/audit/v1/leagues")
async def create_league(request: Request):
    body = await read_json(request)
    with state.lock:
        return ok(standings.register_league(state, body), 201)


@app.post("/audit/v1/events")
async def post_event(request: Request):
    body = await read_json(request)
    with state.lock:
        status, resp = scoring.append_event(state, body)
    return ok(resp, status)


@app.get("/audit/v1/score/{match_id}")
async def get_score(match_id: str):
    with state.lock:
        m = state.matches.get(match_id)
        if m is None:
            raise ApiError(404, "MATCH_NOT_FOUND", f"Match {match_id} not found.", {"match_id": match_id})
        return ok(scoring.score_view(state, m))


@app.get("/audit/v1/standings/{league_id}")
async def get_standings(league_id: str):
    with state.lock:
        return ok(standings.compute_standings(state, league_id))


# ============================================================================ roster

@app.post("/audit/v1/roster/setup")
async def roster_setup(request: Request):
    body = await read_json(request)
    with state.lock:
        return ok(roster.setup(state, body), 201)


@app.post("/audit/v1/roster/transfer")
async def roster_transfer(request: Request):
    body = await read_json(request)
    with state.lock:
        status, resp = roster.transfer(state, body)
    return ok(resp, status)


@app.get("/audit/v1/roster/history/{player_id}")
async def roster_history(player_id: str, as_of: str = None):
    with state.lock:
        return ok(roster.history(state, player_id, as_of))


# ============================================================================ store

@app.post("/audit/v1/checkout")
async def checkout(request: Request):
    body = await read_json(request)
    status, resp = store.checkout(state, body)
    return ok(resp, status)


@app.get("/audit/v1/inventory/{variant_id}")
async def get_inventory(variant_id: str):
    with state.lock:
        return ok(store.inventory(state, variant_id))


# ============================================================================ RBAC

@app.post("/audit/v1/rbac-matrix")
async def rbac_matrix():
    with state.lock:
        u = state.users
        tokens = {"super_admin": rbac.issue(u["admin@nascon.test"]),
                  "league_organizer": rbac.issue(u["organizer@nascon.test"]),
                  "club_manager": rbac.issue(u["manager@nascon.test"]),
                  "player": rbac.issue(u["player@nascon.test"]),
                  "viewer": rbac.issue(u["viewer@nascon.test"])}
    return ok({"tokens": tokens, "context": {
        "tenant_id": "tenant-alpha", "foreign_tenant_id": "tenant-beta",
        "own_league_id": "league-alpha-1", "other_league_id": "league-alpha-2", "foreign_league_id": "league-beta-1",
        "own_club_id": "club-alpha-1", "other_club_id": "club-alpha-2", "foreign_club_id": "club-beta-1",
        "own_player_id": "player-alpha-1", "other_player_id": "player-alpha-2", "foreign_player_id": "player-beta-1"}})


def probe(request: Request, action, kind=None, rid=None):
    claims = rbac.verify(request.headers.get("authorization"))
    resource = {"kind": kind, "id": rid} if kind else None
    with state.lock:
        if resource and not rbac.resource_exists(state, resource):
            raise ApiError(404, f"{kind.upper()}_NOT_FOUND", f"{kind.capitalize()} {rid} not found.", {f"{kind}_id": rid})
        rbac.authorize(state, claims, action, resource)
    return ok({"authorized": True})


@app.post("/audit/v1/rbac/tenants")
async def p1(request: Request):
    return probe(request, "tenant.create")


@app.post("/audit/v1/rbac/leagues/{league_id}/fixtures")
async def p2(league_id: str, request: Request):
    return probe(request, "league.fixtures.write", "league", league_id)


@app.post("/audit/v1/rbac/clubs/{club_id}/roster")
async def p3(club_id: str, request: Request):
    return probe(request, "club.roster.write", "club", club_id)


@app.post("/audit/v1/rbac/clubs/{club_id}/products")
async def p4(club_id: str, request: Request):
    return probe(request, "club.products.write", "club", club_id)


@app.patch("/audit/v1/rbac/players/{player_id}")
async def p5(player_id: str, request: Request):
    return probe(request, "player.update", "player", player_id)


@app.get("/audit/v1/rbac/clubs/{club_id}")
async def p6(club_id: str, request: Request):
    return probe(request, "club.read", "club", club_id)


@app.get("/audit/v1/rbac/platform/config")
async def p7(request: Request):
    return probe(request, "platform.config.read")


# ============================================================================ offline sync

@app.post("/audit/v1/offline-sync")
async def offline_sync(request: Request):
    body = await read_json(request)
    with state.lock:
        return ok(sync.offline_sync(state, body))


# ============================================================================ production API (mobile app)

@app.get("/api/v1/ping")
async def ping():
    return ok({"pong": True})


def current_user(request: Request):
    return rbac.verify(request.headers.get("authorization"))


@app.post("/api/v1/auth/login")
async def login(request: Request):
    body = await read_json(request)
    if not isinstance(body, dict) or not isinstance(body.get("email"), str) or not isinstance(body.get("password"), str):
        raise validation_error(["email", "password"])
    user = state.users.get(body["email"].strip().lower())
    if user is None or rbac.hash_password(body["password"]) != user["password_hash"]:
        raise ApiError(401, "UNAUTHENTICATED", "Email or password is incorrect.", {})
    return ok({"token": rbac.issue(user), "user": public_user(user)})


def public_user(u):
    t = state.tenants.get(u.get("tenant_id")) if u.get("tenant_id") else None
    return {"user_id": u["user_id"], "email": u["email"], "name": u["name"], "role": u["role"],
            "tenant_id": u.get("tenant_id"), "league_ids": u.get("league_ids", []), "club_id": u.get("club_id"),
            "player_id": u.get("player_id"), "tenant": t}


@app.get("/api/v1/me")
async def me(request: Request):
    claims = current_user(request)
    return ok(public_user(state.users[claims["email"]]))


def _visible(claims, tenant_id):
    return claims["role"] == "super_admin" or tenant_id is None or tenant_id == claims.get("tenant_id")


@app.get("/api/v1/leagues")
async def list_leagues(request: Request):
    claims = current_user(request)
    with state.lock:
        out = [{"league_id": l["league_id"], "name": l.get("name", l["league_id"]), "sport_id": l["sport_id"],
                "tenant_id": l.get("tenant_id"), "team_count": len(l["teams"])}
               for l in state.leagues.values() if _visible(claims, l.get("tenant_id"))]
    return ok({"leagues": out})


def match_summary(m):
    v = scoring.score_view(state, m)
    return {"match_id": m["match_id"], "league_id": m["league_id"], "sport_id": m["sport_id"],
            "home": v["home"], "away": v["away"], "status": v["status"], "outcome": v["outcome"],
            "scheduled_at": m.get("scheduled_at"), "venue": m.get("venue"), "version": v["version"]}


@app.get("/api/v1/fixtures")
async def list_fixtures(request: Request, league_id: str = None):
    claims = current_user(request)
    with state.lock:
        out = []
        for m in state.matches.values():
            lg = state.leagues.get(m["league_id"]) if m["league_id"] else None
            if league_id and m["league_id"] != league_id:
                continue
            if not _visible(claims, (lg or {}).get("tenant_id")):
                continue
            out.append(match_summary(m))
    out.sort(key=lambda x: (x["scheduled_at"] or "", x["match_id"]))
    return ok({"fixtures": out})


@app.get("/api/v1/matches/{match_id}")
async def match_detail(match_id: str, request: Request):
    current_user(request)
    with state.lock:
        m = state.matches.get(match_id)
        if m is None:
            raise ApiError(404, "MATCH_NOT_FOUND", "This match does not exist.", {"match_id": match_id})
        v = scoring.score_view(state, m)
        pid = m.get("pinned_product_id")
        v["pinned_product"] = product_view(state.products[pid]) if pid in state.products else None
        v["scheduled_at"], v["venue"] = m.get("scheduled_at"), m.get("venue")
        v["sport"] = state.sports[m["sport_id"]]
    return ok(v)


@app.post("/api/v1/matches/{match_id}/events")
async def match_event(match_id: str, request: Request):
    claims = current_user(request)
    body = await read_json(request)
    with state.lock:
        m = state.matches.get(match_id)
        if m is not None and m["league_id"] in state.rbac_leagues:
            rbac.authorize(state, claims, "league.scoring.write", {"kind": "league", "id": m["league_id"]})
        elif claims["role"] not in ("super_admin", "league_organizer"):
            raise rbac.forbidden()
        if isinstance(body, dict):
            body["match_id"] = match_id
        status, resp = scoring.append_event(state, body)
    return ok(resp, status)


@app.post("/api/v1/matches/{match_id}/pin")
async def pin_product(match_id: str, request: Request):
    claims = current_user(request)
    body = await read_json(request)
    if claims["role"] not in ("super_admin", "league_organizer", "club_manager"):
        raise rbac.forbidden()
    with state.lock:
        m = state.matches.get(match_id)
        if m is None:
            raise ApiError(404, "MATCH_NOT_FOUND", "This match does not exist.", {"match_id": match_id})
        pid = body.get("product_id") if isinstance(body, dict) else None
        if pid is not None and pid not in state.products:
            raise ApiError(404, "PRODUCT_NOT_FOUND", "This product does not exist.", {"product_id": pid})
        m["pinned_product_id"] = pid
        state.emit("match.product_pinned", {"match_id": match_id, "product_id": pid})
    return ok({"match_id": match_id, "pinned_product_id": pid})


@app.get("/api/v1/standings/{league_id}")
async def prod_standings(league_id: str, request: Request):
    claims = current_user(request)
    with state.lock:
        lg = state.leagues.get(league_id)
        if lg is not None and not _visible(claims, lg.get("tenant_id")):
            raise rbac.forbidden()
        return ok(standings.compute_standings(state, league_id))


@app.get("/api/v1/clubs/{club_id}")
async def club_profile(club_id: str, request: Request):
    claims = current_user(request)
    with state.lock:
        if club_id not in state.clubs:
            raise ApiError(404, "CLUB_NOT_FOUND", "This club does not exist.", {"club_id": club_id})
        rbac.authorize(state, claims, "club.read", {"kind": "club", "id": club_id})
        club = dict(state.clubs[club_id])
        club["tenant"] = state.tenants[club["tenant_id"]]
        rl = state.roster_leagues.get("league-alpha-1")
        members = []
        if rl:
            for p in rl["players"].values():
                reg = roster._effective(p, roster.today())
                if reg["squad_id"] == club_id:
                    members.append({"player_id": p["player_id"], "name": p["name"], "position": p["position"],
                                    "role": reg["role"], "registration_type": reg["registration_type"],
                                    "parent_squad_id": reg["parent_squad_id"]})
        club["roster"] = members
        club["roster_league_id"] = "league-alpha-1"
    return ok(club)


@app.post("/api/v1/roster/transfer")
async def prod_transfer(request: Request):
    claims = current_user(request)
    body = await read_json(request)
    with state.lock:
        if isinstance(body, dict):
            sq = body.get("from_squad_id")
            if sq in state.clubs:
                rbac.authorize(state, claims, "club.roster.write", {"kind": "club", "id": sq})
            elif claims["role"] != "super_admin":
                raise rbac.forbidden()
            body.setdefault("requested_by", claims["sub"])
        status, resp = roster.transfer(state, body)
    return ok(resp, status)


@app.get("/api/v1/roster/history/{player_id}")
async def prod_history(player_id: str, request: Request, as_of: str = None):
    current_user(request)
    with state.lock:
        return ok(roster.history(state, player_id, as_of))


def product_view(p):
    return {**p, "variants": [{k: v for k, v in state.variants[vid].items() if k != "reserved"}
                              | {"price_minor": store.current_price(state.variants[vid])} for vid in p["variants"]
                              if vid in state.variants]}


@app.get("/api/v1/products")
async def list_products(request: Request):
    claims = current_user(request)
    with state.lock:
        return ok({"products": [product_view(p) for p in state.products.values()
                                if _visible(claims, p["tenant_id"])],
                   "discount_codes_hint": ["WELCOME10"]})


@app.post("/api/v1/checkout")
async def prod_checkout(request: Request):
    claims = current_user(request)
    body = await read_json(request)
    if isinstance(body, dict):
        body.setdefault("customer_id", claims["sub"])
    status, resp = store.checkout(state, body)
    return ok(resp, status)


@app.get("/api/v1/orders/{order_id}/receipt.pdf")
async def receipt_pdf(order_id: str, request: Request):
    current_user(request)
    o = state.orders.get(order_id)
    if o is None or o["response"] is None:
        raise ApiError(404, "ORDER_NOT_FOUND", "This order does not exist.", {"order_id": order_id})
    pdf = base64.b64decode(o["response"]["receipt"]["pdf_base64"])
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="receipt-{order_id}.pdf"'})


@app.post("/api/v1/offline-sync")
async def prod_sync(request: Request):
    current_user(request)
    body = await read_json(request)
    with state.lock:
        return ok(sync.offline_sync(state, body))


# ============================================================================ realtime

class Hub:
    def __init__(self):
        self.clients = set()
        self.loop = None

    def publish(self, topic, body):
        if self.loop is None or not self.clients:
            return
        msg = json.dumps({"topic": topic, "data": body})
        self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._send(msg)))

    async def _send(self, msg):
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                self.clients.discard(ws)


hub = Hub()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)
