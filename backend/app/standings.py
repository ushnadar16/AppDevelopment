"""FR-1.2 / FR-1.4 league registration and standings, recomputed from event logs on every call."""
from .scoring import new_match, outcome_of, project
from .sports import validate_tie_break
from .util import conflict, is_id, is_int, lots_key, not_found, validation_error


def register_league(state, body):
    if not isinstance(body, dict):
        raise validation_error("body")
    bad = []
    lid, sid = body.get("league_id"), body.get("sport_id")
    if not is_id(lid):
        bad.append("league_id")
    if not isinstance(sid, str) or not sid:
        bad.append("sport_id")
    teams = body.get("teams")
    if (not isinstance(teams, list) or not all(is_id(t) for t in teams) or len(set(teams)) != len(teams)
            or not 2 <= len(teams) <= 40):
        bad.append("teams")
        teams = None
    fixtures = body.get("fixtures")
    if not isinstance(fixtures, list):
        bad.append("fixtures")
    elif teams is not None:
        for f in fixtures:
            if (not isinstance(f, dict) or not is_id(f.get("match_id")) or f.get("home") not in teams
                    or f.get("away") not in teams or f["home"] == f["away"]):
                bad.append("fixtures")
                break
    points = body.get("points") or {}
    if not isinstance(points, dict) or any(not is_int(points.get(k, 0)) for k in ("win", "draw", "loss")):
        bad.append("points")
        points = {}
    try:
        tbo = validate_tie_break(body["tie_break_order"]) if body.get("tie_break_order") is not None else None
    except Exception:
        bad.append("tie_break_order")
        tbo = None
    q = body.get("qualification")
    if (not isinstance(q, dict) or not is_int(q.get("spots"))
            or (teams is not None and not 1 <= q["spots"] <= len(teams))):
        bad.append("qualification")
    seed = body.get("lots_seed", state.seed)
    if seed is None:
        seed = state.seed
    if not is_int(seed):
        bad.append("lots_seed")
    if bad:
        raise validation_error(bad)
    if sid not in state.sports:
        raise not_found("SPORT_NOT_FOUND", f"Sport {sid} not found.", sport_id=sid)
    if lid in state.leagues:
        raise conflict("LEAGUE_EXISTS", f"League {lid} already exists.", league_id=lid)
    ids = [f["match_id"] for f in fixtures]
    for mid in ids:
        if mid in state.matches or ids.count(mid) > 1:
            raise conflict("MATCH_EXISTS", f"Match {mid} already exists.", match_id=mid)
    league = {"league_id": lid, "sport_id": sid, "teams": list(teams), "fixtures": ids,
              "points": {"win": points.get("win", 3), "draw": points.get("draw", 1), "loss": points.get("loss", 0)},
              "tie_break_order": tbo if tbo is not None else list(state.sports[sid]["tie_break_order"]),
              "spots": q["spots"], "lots_seed": seed, "tenant_id": body.get("tenant_id")}
    state.leagues[lid] = league
    for f in fixtures:
        state.matches[f["match_id"]] = new_match(f["match_id"], sid, f["home"], f["away"], lid)
    return {"league_id": lid, "status": "created", "team_count": len(teams), "fixture_count": len(fixtures)}


def _results(state, league):
    """Played match facts: list of dicts with per-side score, overs, fair play, result."""
    sport = state.sports[league["sport_id"]]
    per = sport["periods"]
    innings = sport["scoring_model"] == "innings"
    played, remaining = [], {t: 0 for t in league["teams"]}
    for mid in league["fixtures"]:
        m = state.matches[mid]
        proj = project(state, m)
        outcome, winner = outcome_of(m, proj)
        if proj["status"] != "completed" or outcome == "undecided":
            for t in (m["home"], m["away"]):
                remaining[t] += 1
            continue
        facts = {"home": m["home"], "away": m["away"], "winner": None if outcome == "draw" else winner, "side": {}}
        for t in (m["home"], m["away"]):
            s = proj["sides"][t]
            overs = 0.0
            if innings:
                full = per["innings_per_team"] * per["overs_per_innings"]
                if s["wickets"] >= per["innings_per_team"] * per["wickets_per_innings"]:
                    overs = float(full)
                else:
                    overs = s["balls"] / per["balls_per_over"]
            facts["side"][t] = {"score": s["score"], "overs": overs, "fair_play": s["fair_play"]}
        played.append(facts)
    return played, remaining, innings


def _agg(matches, team, pts, innings, only=None):
    a = {"played": 0, "won": 0, "drawn": 0, "lost": 0, "scored": 0, "conceded": 0, "points": 0, "fair_play": 0,
         "of": 0.0, "ob": 0.0}
    for f in matches:
        if team not in (f["home"], f["away"]):
            continue
        opp = f["away"] if f["home"] == team else f["home"]
        if only is not None and opp not in only:
            continue
        a["played"] += 1
        me, them = f["side"][team], f["side"][opp]
        a["scored"] += me["score"]
        a["conceded"] += them["score"]
        a["fair_play"] += me["fair_play"]
        a["of"] += me["overs"]
        a["ob"] += them["overs"]
        if f["winner"] is None:
            a["drawn"] += 1
            a["points"] += pts["draw"]
        elif f["winner"] == team:
            a["won"] += 1
            a["points"] += pts["win"]
        else:
            a["lost"] += 1
            a["points"] += pts["loss"]
    if innings:
        rr_for = a["scored"] / a["of"] if a["of"] else 0.0
        rr_against = a["conceded"] / a["ob"] if a["ob"] else 0.0
        a["diff"] = round(rr_for - rr_against, 3)
    else:
        a["diff"] = a["scored"] - a["conceded"]
    return a


def compute_standings(state, league_id):
    league = state.leagues.get(league_id)
    if league is None:
        raise not_found("LEAGUE_NOT_FOUND", f"League {league_id} not found.", league_id=league_id)
    pts = league["points"]
    played, remaining, innings = _results(state, league)
    teams = league["teams"]
    overall = {t: _agg(played, t, pts, innings) for t in teams}
    order_crit = [c for c in league["tie_break_order"] if c != "draw_lots"] + ["draw_lots"]
    resolved_by = {t: None for t in teams}

    def crit_value(c, t, group):
        if c == "h2h_points":
            return _agg(played, t, pts, innings, only=set(group))["points"]
        if c == "h2h_diff":
            return _agg(played, t, pts, innings, only=set(group))["diff"]
        if c == "overall_diff":
            return overall[t]["diff"]
        if c == "scored":
            return overall[t]["scored"]
        if c == "fair_play":
            return overall[t]["fair_play"]
        # draw_lots: ascending hash is best -> negate ordering by using a key that sorts descending
        return None

    def resolve(group):
        if len(group) <= 1:
            return list(group)
        for c in order_crit:
            if c == "draw_lots":
                ordered = sorted(group, key=lambda t: lots_key(league["lots_seed"], league_id, t))
                for t in ordered[:-1]:
                    resolved_by[t] = "draw_lots"
                return ordered
            vals = {t: crit_value(c, t, group) for t in group}
            distinct = sorted(set(vals.values()), reverse=True)
            if len(distinct) == 1:
                continue
            out = []
            for v in distinct:
                sub = [t for t in group if vals[t] == v]
                sub_sorted = resolve(sub)
                if out:
                    resolved_by[out[-1]] = c
                out.extend(sub_sorted)
            return out
        return list(group)

    by_points = {}
    for t in teams:
        by_points.setdefault(overall[t]["points"], []).append(t)
    final = []
    for p in sorted(by_points, reverse=True):
        final.extend(resolve(by_points[p]))

    w, k = pts["win"], league["spots"]
    mx = {t: overall[t]["points"] + w * remaining[t] for t in teams}
    table = []
    for i, t in enumerate(final):
        a = overall[t]
        others = [x for x in teams if x != t]
        if sum(1 for x in others if mx[x] >= a["points"]) < k:
            status = "clinched"
        elif sum(1 for x in others if overall[x]["points"] > mx[t]) >= k:
            status = "eliminated"
        else:
            status = "still_possible"
        table.append({"rank": i + 1, "team_id": t, "played": a["played"], "won": a["won"], "drawn": a["drawn"],
                      "lost": a["lost"], "scored": a["scored"], "conceded": a["conceded"], "diff": a["diff"],
                      "points": a["points"], "fair_play": a["fair_play"], "status": status,
                      "resolved_by": resolved_by[t]})
    h2h = {a_: {b: {"played": 0, "points": 0, "scored": 0, "conceded": 0} for b in teams if b != a_} for a_ in teams}
    for f in played:
        for me, opp in ((f["home"], f["away"]), (f["away"], f["home"])):
            cell = h2h[me][opp]
            cell["played"] += 1
            cell["scored"] += f["side"][me]["score"]
            cell["conceded"] += f["side"][opp]["score"]
            if f["winner"] is None:
                cell["points"] += pts["draw"]
            elif f["winner"] == me:
                cell["points"] += pts["win"]
            else:
                cell["points"] += pts["loss"]
    return {"league_id": league_id, "sport_id": league["sport_id"], "qualification_spots": k, "table": table,
            "h2h": h2h}
