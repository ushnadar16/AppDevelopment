import base64
import json

import pytest

A, D = 200, 403
MATRIX = [
    # (method, path-template, target, expected per role [sa, org, mgr, player, viewer])
    ("post", "/audit/v1/rbac/tenants", None, [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/leagues/{}/fixtures", "own_league_id", [A, A, D, D, D]),
    ("post", "/audit/v1/rbac/leagues/{}/fixtures", "other_league_id", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/leagues/{}/fixtures", "foreign_league_id", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/clubs/{}/roster", "own_club_id", [A, D, A, D, D]),
    ("post", "/audit/v1/rbac/clubs/{}/roster", "other_club_id", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/clubs/{}/roster", "foreign_club_id", [A, D, D, D, D]),
    ("post", "/audit/v1/rbac/clubs/{}/products", "own_club_id", [A, D, A, D, D]),
    ("post", "/audit/v1/rbac/clubs/{}/products", "foreign_club_id", [A, D, D, D, D]),
    ("patch", "/audit/v1/rbac/players/{}", "own_player_id", [A, D, A, A, D]),
    ("patch", "/audit/v1/rbac/players/{}", "other_player_id", [A, D, D, D, D]),
    ("patch", "/audit/v1/rbac/players/{}", "foreign_player_id", [A, D, D, D, D]),
    ("get", "/audit/v1/rbac/clubs/{}", "own_club_id", [A, A, A, A, A]),
    ("get", "/audit/v1/rbac/clubs/{}", "other_club_id", [A, A, A, A, A]),
    ("get", "/audit/v1/rbac/clubs/{}", "foreign_club_id", [A, D, D, D, D]),
    ("get", "/audit/v1/rbac/platform/config", None, [A, D, D, D, D]),
]
ROLES = ["super_admin", "league_organizer", "club_manager", "player", "viewer"]


@pytest.mark.parametrize("method,path,target,expected", MATRIX)
def test_matrix(client, method, path, target, expected):
    m = client.post("/audit/v1/rbac-matrix").json()
    url = path.format(m["context"][target]) if target else path
    for role, exp in zip(ROLES, expected):
        kw = {"headers": {"Authorization": f"Bearer {m['tokens'][role]}"}}
        if method != "get":
            kw["json"] = {}
        r = getattr(client, method)(url, **kw)
        assert r.status_code == exp, (role, url, r.text)
        if exp == 403:
            assert r.json()["error"]["code"] == "FORBIDDEN"


def test_bad_tokens(client):
    m = client.post("/audit/v1/rbac-matrix").json()
    tok = m["tokens"]["super_admin"]
    url = "/audit/v1/rbac/platform/config"
    assert client.get(url).json()["error"]["code"] == "UNAUTHENTICATED"
    h, p, s = tok.split(".")
    tampered = f"{h}.{p}.{s[:-2]}{'AA' if s[-2:] != 'AA' else 'BB'}"
    assert client.get(url, headers={"Authorization": f"Bearer {tampered}"}).status_code == 401
    none_h = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    assert client.get(url, headers={"Authorization": f"Bearer {none_h}.{p}."}).status_code == 401
    claims = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    claims["exp"] = 1
    p2 = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    assert client.get(url, headers={"Authorization": f"Bearer {h}.{p2}.{s}"}).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/audit/v1/rbac/clubs/nope", headers={"Authorization": f"Bearer {tok}"}).status_code == 404


def test_rate_limit_and_body_size(client):
    from app import main
    main._hits.clear()
    codes = [client.get("/api/v1/ping").status_code for _ in range(150)]
    assert codes[0] == 200 and codes.count(429) >= 40
    r = client.get("/api/v1/ping")
    assert r.status_code == 429 and "retry-after" in {k.lower() for k in r.headers}
    main._hits.clear()
    assert client.post("/audit/v1/sports", content=b"x" * (1024 * 1024 + 10),
                       headers={"Content-Type": "application/json"}).status_code == 413
    assert all(client.get("/health").status_code == 200 for _ in range(120))


def test_login_and_production_api(client):
    from app import main
    main._hits.clear()
    assert client.post("/api/v1/auth/login", json={"email": "manager@nascon.test", "password": "x"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "manager@nascon.test", "password": "Nascon@26"}).json()
    h = {"Authorization": f"Bearer {r['token']}"}
    assert client.get("/api/v1/me", headers=h).json()["role"] == "club_manager"
    assert client.get("/api/v1/leagues", headers=h).json()["leagues"]
    fx = client.get("/api/v1/fixtures", headers=h).json()["fixtures"]
    assert fx and client.get(f"/api/v1/matches/{fx[0]['match_id']}", headers=h).status_code == 200
    assert client.get("/api/v1/standings/league-alpha-1", headers=h).status_code == 200
    club = client.get("/api/v1/clubs/club-alpha-1", headers=h).json()
    assert club["roster"] and club["tenant"]["name"] == "Alpha Sports"
    assert client.get("/api/v1/clubs/club-beta-1", headers=h).status_code == 403
    assert client.get("/api/v1/products", headers=h).json()["products"]
    r = client.post("/api/v1/roster/transfer", headers=h, json={
        "request_id": "m1", "league_id": "league-alpha-1", "player_id": "demo-player-2", "type": "transfer",
        "from_squad_id": "club-alpha-1", "to_squad_id": "club-alpha-2", "effective_date": "2026-10-17",
        "reason": "test"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/checkout", headers=h, json={"order_id": "app-1", "items": [
        {"variant_id": "var-jersey-001-L", "quantity": 1}], "payment": {"token": "tok_success"}})
    assert r.status_code == 201
    assert client.get("/api/v1/orders/app-1/receipt.pdf", headers=h).content.startswith(b"%PDF")
    org = client.post("/api/v1/auth/login", json={"email": "organizer@nascon.test", "password": "Nascon@26"}).json()
    ho = {"Authorization": f"Bearer {org['token']}"}
    r = client.post("/api/v1/matches/demo-a1-m2/events", headers=ho,
                    json={"event_id": "app-e1", "type": "score", "payload": {"team_id": "demo-alpha-4", "event_type": "goal"}})
    assert r.status_code == 201
    assert client.post("/api/v1/matches/demo-a1-m2/events", headers=h,
                       json={"event_id": "app-e2", "type": "score", "payload": {}}).status_code == 403
    assert client.post("/api/v1/matches/demo-a1-m2/pin", headers=ho, json={"product_id": "prod-jersey-001"}).status_code == 200
