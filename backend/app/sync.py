"""NFR-4 offline sync: replay queued device actions with deterministic conflict resolution."""
from . import roster, scoring
from .util import ApiError, canonical, is_id, is_int, is_timestamp, validation_error

ACTION_TYPES = ("score_event", "roster_transfer")


def _validate(body):
    if not isinstance(body, dict):
        raise validation_error("body")
    bad = []
    if not is_id(body.get("device_id")):
        bad.append("device_id")
    actions = body.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 100:
        bad.append("actions")
    else:
        for a in actions:
            if (not isinstance(a, dict) or not is_id(a.get("action_id")) or a.get("type") not in ACTION_TYPES
                    or not is_timestamp(a.get("queued_at")) or not is_int(a.get("base_version"))
                    or a["base_version"] < 0 or not isinstance(a.get("payload"), dict)):
                bad.append("actions")
                break
    if bad:
        raise validation_error(bad)
    return body["device_id"], actions


def _result(action, status, resolution, code, version, signature=None):
    return {"action_id": action["action_id"], "status": status, "resolution": resolution, "error_code": code,
            "processed_order": None, "server_version": version, "signature": signature}


def _score_event(state, a):
    p = a["payload"]
    mid = p.get("match_id")
    match = state.matches.get(mid) if isinstance(mid, str) else None
    version = len(match["events"]) if match else 0
    try:
        ev = scoring._validate_event(p)
    except ApiError as e:
        return _result(a, "rejected", "server_wins", e.code, version)
    prior = state.event_index.get(ev["event_id"])
    if prior is not None:
        if prior["fingerprint"] == canonical(ev):
            return _result(a, "duplicate", "skipped_duplicate", None, version)
        return _result(a, "rejected", "server_wins", "DUPLICATE_EVENT_ID", version)
    if match is None and ev["type"] != "match_init":
        return _result(a, "rejected", "server_wins", "MATCH_NOT_FOUND", 0)
    if a["base_version"] > version:
        return _result(a, "rejected", "server_wins", "INVALID_BASE_VERSION", version)
    try:
        _, resp = scoring.append_event(state, p)
    except ApiError as e:
        return _result(a, "rejected", "server_wins", e.code, version)
    resolution = "appended" if a["base_version"] == version else "rebased_append"
    return _result(a, "applied", resolution, None, resp["match_version"], resp["signature"])


def _roster(state, a):
    p = a["payload"]
    lid, pid = p.get("league_id"), p.get("player_id")
    version = roster.player_version(state, lid, pid) if isinstance(lid, str) and isinstance(pid, str) else 0
    try:
        req = roster.validate_transfer(p)
    except ApiError as e:
        return _result(a, "rejected", "server_wins", e.code, version)
    prior = state.transfer_requests.get(req["request_id"])
    if prior is not None and prior["fingerprint"] == canonical(req):
        return _result(a, "duplicate", "skipped_duplicate", None, version)
    try:
        roster.lookup(state, req)
    except ApiError as e:
        return _result(a, "rejected", "server_wins", e.code, version)
    if a["base_version"] > version:
        return _result(a, "rejected", "server_wins", "INVALID_BASE_VERSION", version)
    try:
        roster.transfer(state, p)
    except ApiError as e:
        return _result(a, "rejected", "server_wins", e.code, version)
    new_version = roster.player_version(state, lid, pid)
    resolution = "appended" if a["base_version"] == version else "rebased_append"
    return _result(a, "applied", resolution, None, new_version)


def offline_sync(state, body, authorize=None):
    """authorize(action) raises ApiError when the caller may not perform it (production route only)."""
    device_id, actions = _validate(body)
    order = sorted(range(len(actions)), key=lambda i: (actions[i]["queued_at"], i))
    results = [None] * len(actions)
    for n, i in enumerate(order, 1):
        a = actions[i]
        key = (device_id, a["action_id"])
        if key in state.sync_seen:
            prev = state.sync_seen[key]
            r = _result(a, "duplicate", "skipped_duplicate", None, _current_version(state, a, prev))
        else:
            r = _authorized(state, a, authorize)
            if r is None:
                r = _score_event(state, a) if a["type"] == "score_event" else _roster(state, a)
            state.sync_seen[key] = r["server_version"]
        r["processed_order"] = n
        results[i] = r
    summary = {"applied": 0, "rejected": 0, "duplicate": 0}
    for r in results:
        summary[r["status"]] += 1
    state.emit("offline_sync.processed", {"device_id": device_id, **summary})
    return {"device_id": device_id, "results": results, "summary": summary}


def _authorized(state, a, authorize):
    """None when allowed, else a rejected result carrying the authorization error code."""
    if authorize is None:
        return None
    try:
        authorize(a)
    except ApiError as e:
        return _result(a, "rejected", "server_wins", e.code, _current_version(state, a, 0))
    return None


def _current_version(state, a, fallback):
    p = a["payload"]
    if a["type"] == "score_event":
        m = state.matches.get(p.get("match_id")) if isinstance(p.get("match_id"), str) else None
        return len(m["events"]) if m else fallback
    lid, pid = p.get("league_id"), p.get("player_id")
    if isinstance(lid, str) and isinstance(pid, str):
        return roster.player_version(state, lid, pid)
    return fallback
