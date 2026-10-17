"""FR-1.1 append-only event-sourced scoring engine with signed compensating events."""
from .sports import VALUE_FIELD
from .util import ApiError, canonical, conflict, is_id, is_int, not_found, now_iso, sign, validation_error

EVENT_TYPES = ("match_init", "match_start", "score", "discipline", "tiebreak_winner", "match_end", "compensation")
COMPENSABLE = ("score", "discipline", "tiebreak_winner")


def new_match(match_id, sport_id, home, away, league_id=None):
    return {"match_id": match_id, "sport_id": sport_id, "league_id": league_id, "home": home, "away": away,
            "events": [], "pinned_product_id": None}


def _validate_event(body):
    if not isinstance(body, dict):
        raise validation_error("body")
    bad = [f for f in ("event_id", "match_id") if not is_id(body.get(f))]
    if body.get("type") not in EVENT_TYPES:
        bad.append("type")
    payload = body.get("payload", {})
    if not isinstance(payload, dict):
        bad.append("payload")
    if bad:
        raise validation_error(bad)
    t = body["type"]
    need = {
        "match_init": {"sport_id": str, "home_team_id": str, "away_team_id": str},
        "score": {"team_id": str, "event_type": str},
        "discipline": {"team_id": str, "points": int},
        "tiebreak_winner": {"team_id": str},
        "compensation": {"compensates": str},
    }.get(t, {})
    bad = []
    for k, typ in need.items():
        v = payload.get(k)
        if typ is int:
            if not is_int(v):
                bad.append(f"payload.{k}")
        elif not isinstance(v, str) or not v:
            bad.append(f"payload.{k}")
    if t == "match_init":
        if "league_id" in payload and payload["league_id"] is not None and not isinstance(payload["league_id"], str):
            bad.append("payload.league_id")
        if not bad and payload["home_team_id"] == payload["away_team_id"]:
            bad.append("payload.away_team_id")
    if t == "compensation" and "reason" in payload and not isinstance(payload["reason"], (str, type(None))):
        bad.append("payload.reason")
    if bad:
        raise validation_error(bad)
    return {"event_id": body["event_id"], "match_id": body["match_id"], "type": t, "payload": payload}


def project(state, match):
    """Rebuild the match projection from its event log (never from mutable counters)."""
    sport = state.sports[match["sport_id"]]
    model = sport["scoring_model"]
    vf = VALUE_FIELD[model]
    evs = match["events"]
    compensated_by = {}
    for e in evs:
        if e["type"] == "compensation":
            compensated_by[e["payload"]["compensates"]] = e["event_id"]
    status = "upcoming"
    sides = {}
    for side in ("home", "away"):
        sides[match[side]] = {"team_id": match[side], "score": 0, "wickets": 0, "balls": 0, "fair_play": 0}
    tiebreak = None
    for e in evs:
        t = e["type"]
        if t == "match_start":
            status = "in_progress"
        elif t == "match_end":
            status = "completed"
        if e["event_id"] in compensated_by or t == "compensation":
            continue
        p = e["payload"]
        if t == "score":
            cfg = sport["scoring_events"].get(p["event_type"], {})
            s = sides[p["team_id"]]
            s["score"] += cfg.get(vf, 0)
            if model == "innings":
                if cfg.get("legal_ball"):
                    s["balls"] += 1
                if cfg.get("wicket"):
                    s["wickets"] += 1
        elif t == "discipline":
            sides[p["team_id"]]["fair_play"] += p["points"]
        elif t == "tiebreak_winner":
            tiebreak = p["team_id"]
    return {"status": status, "sides": sides, "tiebreak": tiebreak, "compensated_by": compensated_by,
            "model": model, "sport": sport}


def outcome_of(match, proj):
    h, a = proj["sides"][match["home"]], proj["sides"][match["away"]]
    if h["score"] > a["score"]:
        winner = match["home"]
    elif a["score"] > h["score"]:
        winner = match["away"]
    else:
        winner = proj["tiebreak"]
    if proj["status"] != "completed":
        return "pending", winner
    if winner == match["home"]:
        return "home_win", winner
    if winner == match["away"]:
        return "away_win", winner
    return ("draw" if proj["sport"]["draw_allowed"] else "undecided"), None


def score_view(state, match):
    proj = project(state, match)
    outcome, winner = outcome_of(match, proj)
    periods = proj["sport"]["periods"]

    def side(team):
        s = proj["sides"][team]
        out = {"team_id": team, "score": s["score"], "wickets": None, "balls": None, "overs": None,
               "fair_play": s["fair_play"]}
        if proj["model"] == "innings":
            bpo = periods["balls_per_over"]
            out.update({"wickets": s["wickets"], "balls": s["balls"], "overs": f"{s['balls'] // bpo}.{s['balls'] % bpo}"})
        return out

    events = []
    for i, e in enumerate(match["events"]):
        cb = proj["compensated_by"].get(e["event_id"])
        events.append({"sequence": i + 1, "event_id": e["event_id"], "type": e["type"], "payload": e["payload"],
                       "signature": e["signature"], "compensated": cb is not None, "compensated_by": cb,
                       "recorded_at": e["recorded_at"]})
    return {"match_id": match["match_id"], "sport_id": match["sport_id"], "league_id": match["league_id"],
            "status": proj["status"], "outcome": outcome, "winner_team_id": winner,
            "tiebreak_winner_team_id": proj["tiebreak"], "home": side(match["home"]), "away": side(match["away"]),
            "version": len(match["events"]), "events": events}


def check_rules(state, ev):
    """Raise ApiError if the event is not allowed. Returns the match (or None for match_init)."""
    t, p = ev["type"], ev["payload"]
    if t == "match_init":
        if p["sport_id"] not in state.sports:
            raise not_found("SPORT_NOT_FOUND", f"Sport {p['sport_id']} not found.", sport_id=p["sport_id"])
        if ev["match_id"] in state.matches:
            raise conflict("MATCH_EXISTS", f"Match {ev['match_id']} already exists.", match_id=ev["match_id"])
        return None
    match = state.matches.get(ev["match_id"])
    if match is None:
        raise not_found("MATCH_NOT_FOUND", f"Match {ev['match_id']} not found.", match_id=ev["match_id"])
    proj = project(state, match)
    sport = proj["sport"]
    status = proj["status"]
    if t in ("score", "discipline", "tiebreak_winner"):
        if p["team_id"] not in (match["home"], match["away"]):
            raise validation_error("payload.team_id", "team_id is not a participant of this match.")
        if t == "score" and p["event_type"] not in sport["scoring_events"]:
            raise ApiError(400, "UNKNOWN_EVENT_TYPE", f"Event type {p['event_type']} is not defined for this sport.",
                           {"event_type": p["event_type"], "sport_id": sport["sport_id"]})
        if status != "in_progress":
            raise conflict("MATCH_NOT_IN_PROGRESS", "Match is not in progress.", match_id=match["match_id"],
                           status=status)
        if t == "score":
            _check_limits(proj, p["team_id"], match)
    elif t == "match_start":
        if status != "upcoming":
            raise conflict("ILLEGAL_TRANSITION", f"Cannot start a match that is {status}.",
                           match_id=match["match_id"], status=status)
    elif t == "match_end":
        if status != "in_progress":
            raise conflict("ILLEGAL_TRANSITION", f"Cannot end a match that is {status}.",
                           match_id=match["match_id"], status=status)
        h, a = proj["sides"][match["home"]]["score"], proj["sides"][match["away"]]["score"]
        if h == a and not sport["draw_allowed"] and proj["tiebreak"] is None:
            raise conflict("TIE_NOT_ALLOWED", "Scores are level and this sport does not allow draws.",
                           match_id=match["match_id"])
    elif t == "compensation":
        target_id = p["compensates"]
        loc = state.event_index.get(target_id)
        if loc is None:
            raise not_found("EVENT_NOT_FOUND", f"Event {target_id} not found.", event_id=target_id)
        target = loc["event"]
        if (loc["match_id"] != match["match_id"] or target["type"] not in COMPENSABLE
                or target_id in proj["compensated_by"]):
            raise conflict("INVALID_COMPENSATION", f"Event {target_id} cannot be compensated.", event_id=target_id)
    return match


def _check_limits(proj, team, match):
    sport = proj["sport"]
    per = sport["periods"]
    s = proj["sides"][team]
    if proj["model"] == "innings":
        max_balls = per["innings_per_team"] * per["overs_per_innings"] * per["balls_per_over"]
        max_w = per["innings_per_team"] * per["wickets_per_innings"]
        if s["balls"] >= max_balls or s["wickets"] >= max_w:
            raise conflict("INNINGS_COMPLETE", "This team's innings is complete.", match_id=match["match_id"],
                           team_id=team)
    elif proj["model"] == "round":
        need = (per["best_of"] + 1) // 2
        if any(x["score"] >= need for x in proj["sides"].values()):
            raise conflict("SERIES_ALREADY_DECIDED", "The series is already decided.", match_id=match["match_id"])


def append_event(state, body):
    """Returns (http_status, response). Raises ApiError on rejection."""
    ev = _validate_event(body)
    fingerprint = canonical(ev)
    prior = state.event_index.get(ev["event_id"])
    if prior is not None:
        if prior["fingerprint"] == fingerprint:
            return 200, prior["response"]
        raise conflict("DUPLICATE_EVENT_ID", f"Event {ev['event_id']} already exists with a different body.",
                       event_id=ev["event_id"])
    match = check_rules(state, ev)
    if match is None:
        p = ev["payload"]
        match = new_match(ev["match_id"], p["sport_id"], p["home_team_id"], p["away_team_id"], p.get("league_id"))
        state.matches[ev["match_id"]] = match
    record = {"event_id": ev["event_id"], "type": ev["type"], "payload": ev["payload"],
              "signature": sign(ev["event_id"], ev["payload"]), "recorded_at": now_iso()}
    match["events"].append(record)
    seq = len(match["events"])
    resp = {"event_id": ev["event_id"], "match_id": ev["match_id"], "type": ev["type"], "sequence": seq,
            "match_version": seq, "signature": record["signature"]}
    state.event_index[ev["event_id"]] = {"match_id": ev["match_id"], "event": record, "fingerprint": fingerprint,
                                         "response": resp}
    state.emit("match.event_appended", {"match_id": ev["match_id"], "event_id": ev["event_id"],
                                        "type": ev["type"], "sequence": seq})
    state.persist("event", {"match_id": ev["match_id"], "sequence": seq, **record})
    return 201, resp
