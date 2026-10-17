"""FR-2.2 roster registry: transfers, loans with automatic return, releases, immutable audit trail."""
from datetime import timedelta

from .util import ApiError, canonical, conflict, is_id, is_int, not_found, now_iso, parse_date, today, validation_error

ROLES = ("captain", "vice_captain", "starter", "substitute")
TYPES = ("transfer", "loan", "release")


def setup(state, body):
    if not isinstance(body, dict):
        raise validation_error("body")
    lg = body.get("league")
    bad = []
    if not isinstance(lg, dict):
        raise validation_error("league")
    for f in ("league_id", "tenant_id", "sport_id"):
        if not is_id(lg.get(f)):
            bad.append(f"league.{f}")
    tw = lg.get("transfer_window")
    if not isinstance(tw, dict) or parse_date(tw.get("open")) is None or parse_date(tw.get("close")) is None:
        bad.append("league.transfer_window")
    if "max_squad_size" in lg and lg["max_squad_size"] is not None and not (is_int(lg["max_squad_size"]) and lg["max_squad_size"] >= 1):
        bad.append("league.max_squad_size")
    rp = lg.get("required_positions")
    if rp is not None and not (isinstance(rp, dict) and all(is_int(v) and v >= 0 for v in rp.values())):
        bad.append("league.required_positions")
    squads = body.get("squads", [])
    players = body.get("players", [])
    mip = body.get("matches_in_progress", []) or []
    if not isinstance(squads, list) or not all(isinstance(s, dict) and is_id(s.get("squad_id")) for s in squads):
        bad.append("squads")
        squads = []
    sq_ids = {s["squad_id"] for s in squads}
    if not isinstance(players, list):
        bad.append("players")
        players = []
    for p in players:
        if (not isinstance(p, dict) or not is_id(p.get("player_id")) or p.get("squad_id") not in sq_ids
                or p.get("role", "substitute") not in ROLES or not isinstance(p.get("position", ""), str)):
            bad.append("players")
            break
    if not isinstance(mip, list) or not all(isinstance(m, dict) and is_id(m.get("match_id")) for m in mip):
        bad.append("matches_in_progress")
    if bad:
        raise validation_error(bad)
    sport = state.sports.get(lg["sport_id"])
    if sport is None:
        raise not_found("SPORT_NOT_FOUND", f"Sport {lg['sport_id']} not found.", sport_id=lg["sport_id"])
    lid = lg["league_id"]
    old = state.roster_leagues.get(lid)
    if old:
        for pid in old["players"]:
            if state.player_league.get(pid) == lid:
                state.player_league.pop(pid, None)
    rl = {
        "league_id": lid, "tenant_id": lg["tenant_id"], "sport_id": lg["sport_id"],
        "window": (parse_date(tw["open"]), parse_date(tw["close"])),
        "max_squad_size": lg.get("max_squad_size") or sport["roster"]["max_squad_size"],
        "required_positions": rp if rp is not None else dict(sport["roster"]["required_positions"]),
        "squads": {s["squad_id"]: {"squad_id": s["squad_id"], "club_id": s.get("club_id"),
                                   "tenant_id": s.get("tenant_id", lg["tenant_id"]), "name": s.get("name", s["squad_id"])}
                   for s in squads},
        "players": {},
        "matches_in_progress": [{"match_id": m["match_id"], "home": m.get("home_squad_id"),
                                 "away": m.get("away_squad_id")} for m in mip],
    }
    for p in players:
        rl["players"][p["player_id"]] = {
            "player_id": p["player_id"], "name": p.get("name", p["player_id"]), "position": p.get("position", ""),
            "initial_squad_id": p["squad_id"], "initial_role": p.get("role", "substitute"), "audit": [],
        }
        state.player_league[p["player_id"]] = lid
    state.roster_leagues[lid] = rl
    counts = {sid: 0 for sid in rl["squads"]}
    for p in rl["players"].values():
        counts[p["initial_squad_id"]] += 1
    return {"league_id": lid, "status": "configured", "squad_counts": counts}


def _replay(player):
    """Current registration after applying every accepted audit entry (ignoring dates)."""
    reg = {"squad_id": player["initial_squad_id"], "parent_squad_id": None, "role": player["initial_role"],
           "registration_type": "initial", "start_date": None, "loan_end_date": None}
    for e in player["audit"]:
        a = e["action"]
        if a == "release":
            reg = {"squad_id": None, "parent_squad_id": None, "role": None, "registration_type": None,
                   "start_date": e["effective_date"], "loan_end_date": None}
        elif a in ("transfer", "loan_return"):
            reg = {"squad_id": e["to_squad_id"], "parent_squad_id": None, "role": "substitute",
                   "registration_type": "transfer" if a == "transfer" else "loan_return",
                   "start_date": e["effective_date"], "loan_end_date": None}
        elif a == "loan":
            reg = {"squad_id": e["to_squad_id"], "parent_squad_id": e["from_squad_id"], "role": "substitute",
                   "registration_type": "loan", "start_date": e["effective_date"],
                   "loan_end_date": e["loan_end_date"]}
    return reg


def _materialize_returns(state, rl, player, as_of):
    """Write the loan_return audit entry once the day after loan_end_date has been reached."""
    reg = _replay(player)
    if reg["registration_type"] == "loan" and reg["loan_end_date"]:
        end = parse_date(reg["loan_end_date"])
        if as_of > end:
            ret = end + timedelta(days=1)
            _append_audit(state, rl, player, {
                "action": "loan_return", "from_squad_id": reg["squad_id"], "to_squad_id": reg["parent_squad_id"],
                "effective_date": ret.isoformat(), "state": "active", "who": "system",
                "why": f"Loan ended on {reg['loan_end_date']}; automatic return to parent squad."})


def _append_audit(state, rl, player, fields):
    state.audit_seq += 1
    entry = {"audit_id": f"au-{state.audit_seq:04d}", "action": fields["action"], "player_id": player["player_id"],
             "league_id": rl["league_id"], "from_squad_id": fields.get("from_squad_id"),
             "to_squad_id": fields.get("to_squad_id"), "effective_date": fields["effective_date"],
             "state": fields.get("state", "active"), "who": fields["who"], "when": now_iso(), "why": fields["why"]}
    if fields["action"] == "loan":
        entry["loan_end_date"] = fields.get("loan_end_date")
    if fields.get("blocking_match_id"):
        entry["blocking_match_id"] = fields["blocking_match_id"]
    player["audit"].append(entry)
    state.persist("audit", entry)
    state.emit("roster.changed", {"player_id": player["player_id"], "action": entry["action"],
                                  "league_id": rl["league_id"]})
    return entry


def _squad_members(rl, as_of):
    members = {}
    for p in rl["players"].values():
        reg = _effective(p, as_of)
        if reg["squad_id"]:
            members.setdefault(reg["squad_id"], []).append(p)
    return members


def _effective(player, as_of):
    """Registration with a virtual loan return applied when as_of is past loan_end_date."""
    reg = _replay(player)
    if reg["registration_type"] == "loan" and reg["loan_end_date"] and as_of > parse_date(reg["loan_end_date"]):
        reg = {"squad_id": reg["parent_squad_id"], "parent_squad_id": None, "role": "substitute",
               "registration_type": "loan_return", "start_date": None, "loan_end_date": None}
    return reg


def validate_transfer(body):
    if not isinstance(body, dict):
        raise validation_error("body")
    bad = [f for f in ("request_id", "league_id", "player_id") if not is_id(body.get(f))]
    t = body.get("type")
    if t not in TYPES:
        bad.append("type")
    if not is_id(body.get("from_squad_id")):
        bad.append("from_squad_id")
    if t in ("transfer", "loan") and not is_id(body.get("to_squad_id")):
        bad.append("to_squad_id")
    eff = parse_date(body.get("effective_date"))
    if eff is None:
        bad.append("effective_date")
    if t == "loan":
        end = parse_date(body.get("loan_end_date"))
        if end is None or (eff is not None and end <= eff):
            bad.append("loan_end_date")
    elif body.get("loan_end_date") is not None and parse_date(body.get("loan_end_date")) is None:
        bad.append("loan_end_date")
    for f in ("reason", "requested_by"):
        if body.get(f) is not None and not isinstance(body.get(f), str):
            bad.append(f)
    if bad:
        raise validation_error(bad)
    keys = ("request_id", "league_id", "player_id", "type", "from_squad_id", "to_squad_id", "effective_date",
            "loan_end_date", "reason", "requested_by")
    return {k: body.get(k) for k in keys}


def lookup(state, req):
    rl = state.roster_leagues.get(req["league_id"])
    if rl is None:
        raise not_found("LEAGUE_NOT_FOUND", f"League {req['league_id']} not found.", league_id=req["league_id"])
    player = rl["players"].get(req["player_id"])
    if player is None:
        raise not_found("PLAYER_NOT_FOUND", f"Player {req['player_id']} not found.", player_id=req["player_id"])
    return rl, player


def transfer(state, body):
    req = validate_transfer(body)
    fp = canonical(req)
    prior = state.transfer_requests.get(req["request_id"])
    if prior is not None:
        if prior["fingerprint"] == fp:
            return 200, prior["response"]
        raise conflict("DUPLICATE_REQUEST_ID", f"Request {req['request_id']} was already used with a different body.",
                       request_id=req["request_id"])
    rl, player = lookup(state, req)
    t = req["type"]
    for sid in (req["from_squad_id"], req["to_squad_id"] if t != "release" else None):
        if sid is not None and sid not in rl["squads"]:
            raise not_found("SQUAD_NOT_FOUND", f"Squad {sid} not found.", squad_id=sid)
    from_sq = rl["squads"][req["from_squad_id"]]
    to_sq = rl["squads"].get(req["to_squad_id"]) if t != "release" else None
    for sq in (from_sq, to_sq):
        if sq is not None and sq["tenant_id"] != rl["tenant_id"]:
            raise conflict("CROSS_TENANT_TRANSFER", "Squads must belong to the league's tenant.",
                           squad_id=sq["squad_id"], tenant_id=sq["tenant_id"], league_tenant_id=rl["tenant_id"])
    eff = parse_date(req["effective_date"])
    reg = _effective(player, eff)
    if reg["squad_id"] != req["from_squad_id"]:
        raise conflict("NOT_IN_SQUAD", f"Player is not registered with {req['from_squad_id']}.",
                       player_id=player["player_id"], current_squad_id=reg["squad_id"])
    if t in ("transfer", "loan"):
        open_, close = rl["window"]
        if not open_ <= eff <= close:
            raise conflict("TRANSFER_WINDOW_CLOSED", "The transfer window is closed on the effective date.",
                           effective_date=req["effective_date"], window_open=open_.isoformat(),
                           window_close=close.isoformat())
    if reg["registration_type"] == "loan":
        raise conflict("PLAYER_ON_LOAN", "Player is currently on loan.", player_id=player["player_id"],
                       parent_squad_id=reg["parent_squad_id"])
    members = _squad_members(rl, eff)
    if t in ("transfer", "loan"):
        if len(members.get(req["to_squad_id"], [])) + 1 > rl["max_squad_size"]:
            raise conflict("SQUAD_FULL", f"Squad {req['to_squad_id']} is full.", squad_id=req["to_squad_id"],
                           max_squad_size=rl["max_squad_size"])
    pos = player["position"]
    need = rl["required_positions"].get(pos)
    if need is not None:
        have = sum(1 for p in members.get(req["from_squad_id"], []) if p["position"] == pos)
        if have - 1 < need:
            raise conflict("MIN_POSITION_VIOLATION", f"Squad {req['from_squad_id']} needs at least {need} {pos}.",
                           squad_id=req["from_squad_id"], position=pos, required=need)

    blocking = None
    for m in rl["matches_in_progress"]:
        if req["from_squad_id"] in (m["home"], m["away"]):
            blocking = m["match_id"]
            break
    st = "deferred_until_match_end" if blocking else "active"
    _materialize_returns(state, rl, player, eff)
    entry = _append_audit(state, rl, player, {
        "action": t, "from_squad_id": req["from_squad_id"], "to_squad_id": req["to_squad_id"] if t != "release" else None,
        "effective_date": req["effective_date"], "state": st, "who": req["requested_by"] or "unknown",
        "why": req["reason"] or "", "loan_end_date": req["loan_end_date"], "blocking_match_id": blocking})
    registration = None
    if t != "release":
        registration = {"player_id": player["player_id"], "league_id": rl["league_id"], "squad_id": req["to_squad_id"],
                        "parent_squad_id": req["from_squad_id"] if t == "loan" else None, "registration_type": t,
                        "start_date": req["effective_date"],
                        "loan_end_date": req["loan_end_date"] if t == "loan" else None, "role": "substitute"}
    resp = {"request_id": req["request_id"], "status": "accepted", "state": st, "blocking_match_id": blocking,
            "registration": registration, "audit_entry": entry}
    state.transfer_requests[req["request_id"]] = {"fingerprint": fp, "response": resp,
                                                  "player_id": player["player_id"]}
    return 201, resp


def history(state, player_id, as_of_str=None):
    if as_of_str is None or as_of_str == "":
        as_of = today()
    else:
        as_of = parse_date(as_of_str)
        if as_of is None:
            raise validation_error("as_of")
    lid = state.player_league.get(player_id)
    if lid is None:
        raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} not found.", player_id=player_id)
    rl = state.roster_leagues[lid]
    player = rl["players"][player_id]
    _materialize_returns(state, rl, player, as_of)
    # Temporal view: the squad the player belongs to on as_of.
    squad, parent = player["initial_squad_id"], None
    for e in player["audit"]:
        if parse_date(e["effective_date"]) > as_of:
            continue
        if e["action"] == "release":
            squad, parent = None, None
        elif e["action"] == "loan":
            squad, parent = e["to_squad_id"], e["from_squad_id"]
        else:
            squad, parent = e["to_squad_id"], None
    return {"player_id": player_id, "as_of": as_of.isoformat(), "league_id": lid, "current_squad_id": squad,
            "parent_squad_id": parent, "history": list(player["audit"])}


def player_version(state, league_id, player_id):
    rl = state.roster_leagues.get(league_id)
    if rl is None or player_id not in rl["players"]:
        return 0
    return len(rl["players"][player_id]["audit"])
