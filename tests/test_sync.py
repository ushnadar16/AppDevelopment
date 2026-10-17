from tests.test_roster import SETUP
from tests.test_scoring import ev


def test_offline_sync(client):
    ev(client, "s0", "m1", "match_init", {"sport_id": "football", "home_team_id": "t1", "away_team_id": "t2"}, 201)
    ev(client, "s1", "m1", "match_start", status=201)
    client.post("/audit/v1/roster/setup", json=SETUP)
    body = {"device_id": "dev-1", "actions": [
        {"action_id": "a2", "type": "roster_transfer", "queued_at": "2026-10-17T11:01:00Z", "base_version": 0,
         "payload": {"request_id": "tr-9", "league_id": "lg-r1", "player_id": "p2", "type": "transfer",
                     "from_squad_id": "sq-a", "to_squad_id": "sq-b", "effective_date": "2026-09-30",
                     "loan_end_date": None, "reason": "x", "requested_by": "u"}},
        {"action_id": "a1", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 1,
         "payload": {"event_id": "evt-9", "match_id": "m1", "type": "score",
                     "payload": {"team_id": "t1", "event_type": "goal"}}},
        {"action_id": "a3", "type": "score_event", "queued_at": "2026-10-17T11:02:00Z", "base_version": 3,
         "payload": {"event_id": "evt-10", "match_id": "m1", "type": "score",
                     "payload": {"team_id": "t1", "event_type": "goal"}}},
        {"action_id": "a4", "type": "score_event", "queued_at": "2026-10-17T11:03:00Z", "base_version": 99,
         "payload": {"event_id": "evt-11", "match_id": "m1", "type": "score",
                     "payload": {"team_id": "t1", "event_type": "goal"}}},
        {"action_id": "a5", "type": "score_event", "queued_at": "2026-10-17T11:04:00Z", "base_version": 0,
         "payload": {"event_id": "evt-12", "match_id": "nope", "type": "score",
                     "payload": {"team_id": "t1", "event_type": "goal"}}},
        {"action_id": "a6", "type": "roster_transfer", "queued_at": "2026-10-17T11:05:00Z", "base_version": 0,
         "payload": {"request_id": "tr-10", "league_id": "lg-r1", "player_id": "p3", "type": "transfer",
                     "from_squad_id": "sq-a", "to_squad_id": "sq-b", "effective_date": "2026-09-30"}},
        {"action_id": "a7", "type": "score_event", "queued_at": "2026-10-17T11:06:00Z", "base_version": 0,
         "payload": {"event_id": "s1", "match_id": "m1", "type": "match_start", "payload": {}}},
    ]}
    r = client.post("/audit/v1/offline-sync", json=body)
    assert r.status_code == 200
    res = {x["action_id"]: x for x in r.json()["results"]}
    assert [x["action_id"] for x in r.json()["results"]] == ["a2", "a1", "a3", "a4", "a5", "a6", "a7"]
    assert res["a1"]["status"] == "applied" and res["a1"]["resolution"] == "rebased_append"
    assert res["a1"]["processed_order"] == 1 and res["a1"]["server_version"] == 3 and len(res["a1"]["signature"]) == 64
    assert res["a2"]["resolution"] == "appended" and res["a2"]["server_version"] == 1 and res["a2"]["signature"] is None
    assert res["a3"]["resolution"] == "appended" and res["a3"]["server_version"] == 4
    assert res["a4"]["error_code"] == "INVALID_BASE_VERSION" and res["a4"]["server_version"] == 4
    assert res["a5"]["error_code"] == "MATCH_NOT_FOUND"
    assert res["a6"]["error_code"] == "NOT_IN_SQUAD"
    assert res["a7"]["status"] == "duplicate"
    assert r.json()["summary"] == {"applied": 3, "rejected": 3, "duplicate": 1}
    again = client.post("/audit/v1/offline-sync", json=body).json()
    assert again["summary"] == {"applied": 0, "rejected": 0, "duplicate": 7}
    assert client.get("/audit/v1/score/m1").json()["version"] == 4
    assert client.post("/audit/v1/offline-sync", json={"device_id": "d", "actions": []}).status_code == 400
