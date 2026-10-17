"""FR-1.1 sport taxonomy as data. No branch on any sport or event name lives in this codebase."""
import re

from .util import conflict, is_int, validation_error

SPORT_ID_RE = re.compile(r"^[a-z0-9_-]{2,40}$")
EVENT_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
MODELS = ("event", "innings", "round")
OVERTIME = ("none", "extra_time", "shootout", "golden_score", "super_over")
TIE_BREAKS = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]

# Which field of a scoring event carries the score value, per scoring model.
VALUE_FIELD = {"event": "points", "innings": "runs", "round": "rounds"}


def validate_tie_break(order, field="tie_break_order"):
    if order is None:
        return list(TIE_BREAKS)
    if not isinstance(order, list) or len(set(map(str, order))) != len(order) or any(t not in TIE_BREAKS for t in order):
        raise validation_error(field)
    return list(order)


def validate_sport(body):
    bad = []
    if not isinstance(body, dict):
        raise validation_error("body")
    sid = body.get("sport_id")
    if not isinstance(sid, str) or not SPORT_ID_RE.match(sid):
        bad.append("sport_id")
    name = body.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        bad.append("name")
    model = body.get("scoring_model")
    if model not in MODELS:
        bad.append("scoring_model")
    periods = body.get("periods")
    if not isinstance(periods, dict):
        bad.append("periods")
    elif model == "event":
        if not (is_int(periods.get("count")) and periods["count"] >= 1
                and is_int(periods.get("duration_minutes")) and periods["duration_minutes"] >= 1):
            bad.append("periods")
    elif model == "innings":
        keys = ("innings_per_team", "overs_per_innings", "balls_per_over", "wickets_per_innings")
        if not all(is_int(periods.get(k)) and periods[k] >= 1 for k in keys):
            bad.append("periods")
    elif model == "round":
        bo = periods.get("best_of")
        if not (is_int(bo) and bo >= 1 and bo % 2 == 1):
            bad.append("periods")
    events = body.get("scoring_events")
    if not isinstance(events, dict) or not events:
        bad.append("scoring_events")
    else:
        for k, v in events.items():
            if not EVENT_KEY_RE.match(k) or not isinstance(v, dict):
                bad.append("scoring_events")
                break
            if model == "event" and not (is_int(v.get("points")) and v["points"] >= 1):
                bad.append("scoring_events")
                break
            if model == "innings" and not (is_int(v.get("runs")) and v["runs"] >= 0
                                           and isinstance(v.get("legal_ball"), bool)
                                           and isinstance(v.get("wicket"), bool)):
                bad.append("scoring_events")
                break
            if model == "round" and not (is_int(v.get("rounds")) and v["rounds"] >= 1):
                bad.append("scoring_events")
                break
    if not isinstance(body.get("draw_allowed"), bool):
        bad.append("draw_allowed")
    ot = body.get("overtime")
    if (not isinstance(ot, dict) or ot.get("policy") not in OVERTIME
            or ("duration_minutes" in ot and not (is_int(ot["duration_minutes"]) and ot["duration_minutes"] >= 0))):
        bad.append("overtime")
    try:
        tbo = validate_tie_break(body.get("tie_break_order"))
    except Exception:
        bad.append("tie_break_order")
        tbo = None
    roster = body.get("roster")
    if not isinstance(roster, dict):
        bad.append("roster")
    else:
        mn, mx, rp = roster.get("min_squad_size"), roster.get("max_squad_size"), roster.get("required_positions", {})
        if not (is_int(mn) and is_int(mx) and mn >= 1 and mx >= 1 and mn <= mx and isinstance(rp, dict)
                and all(isinstance(k, str) and is_int(v) and v >= 0 for k, v in rp.items())):
            bad.append("roster")
    if bad:
        raise validation_error(sorted(set(bad), key=bad.index))
    cfg = {
        "sport_id": sid, "name": name, "scoring_model": model, "periods": periods,
        "scoring_events": events, "draw_allowed": body["draw_allowed"], "overtime": ot,
        "tie_break_order": tbo,
        "roster": {"min_squad_size": roster["min_squad_size"], "max_squad_size": roster["max_squad_size"],
                   "required_positions": roster.get("required_positions", {})},
    }
    return cfg


def create_sport(state, body):
    cfg = validate_sport(body)
    if cfg["sport_id"] in state.sports:
        raise conflict("SPORT_EXISTS", f"Sport {cfg['sport_id']} already exists.", sport_id=cfg["sport_id"])
    state.sports[cfg["sport_id"]] = cfg
    return {"sport_id": cfg["sport_id"], "status": "created", "config": cfg}


def _innings_ev(runs, legal, wicket):
    return {"runs": runs, "legal_ball": legal, "wicket": wicket}


# Baseline sports: plain data passed through the same validator as the mystery sport.
SEED_SPORTS = [
    {"sport_id": "football", "name": "Football", "scoring_model": "event",
     "periods": {"count": 2, "duration_minutes": 45},
     "scoring_events": {"goal": {"points": 1}},
     "draw_allowed": True, "overtime": {"policy": "none"},
     "roster": {"min_squad_size": 11, "max_squad_size": 25, "required_positions": {"gk": 1}}},
    {"sport_id": "basketball", "name": "Basketball", "scoring_model": "event",
     "periods": {"count": 4, "duration_minutes": 12},
     "scoring_events": {"free_throw": {"points": 1}, "two_pointer": {"points": 2}, "three_pointer": {"points": 3}},
     "draw_allowed": False, "overtime": {"policy": "extra_time", "duration_minutes": 5},
     "roster": {"min_squad_size": 5, "max_squad_size": 15, "required_positions": {}}},
    {"sport_id": "cricket", "name": "Cricket", "scoring_model": "innings",
     "periods": {"innings_per_team": 1, "overs_per_innings": 20, "balls_per_over": 6, "wickets_per_innings": 10},
     "scoring_events": {"dot_ball": _innings_ev(0, True, False), "single": _innings_ev(1, True, False),
                        "two": _innings_ev(2, True, False), "four": _innings_ev(4, True, False),
                        "six": _innings_ev(6, True, False), "wide": _innings_ev(1, False, False),
                        "no_ball": _innings_ev(1, False, False), "wicket": _innings_ev(0, True, True)},
     "draw_allowed": True, "overtime": {"policy": "super_over"},
     "roster": {"min_squad_size": 11, "max_squad_size": 18, "required_positions": {"wicketkeeper": 1}}},
    {"sport_id": "esports", "name": "Esports", "scoring_model": "round",
     "periods": {"best_of": 3},
     "scoring_events": {"round_win": {"rounds": 1}},
     "draw_allowed": False, "overtime": {"policy": "none"},
     "roster": {"min_squad_size": 5, "max_squad_size": 8, "required_positions": {}}},
]
