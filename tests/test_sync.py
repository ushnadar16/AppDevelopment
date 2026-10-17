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


def _auth(client, who):
    tok = client.post("/api/v1/auth/login", json={"email": f"{who}@nascon.test", "password": "Nascon@26"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_production_sync_enforces_rbac(client):
    match = next(f for f in client.get("/api/v1/fixtures", headers=_auth(client, "viewer")).json()["fixtures"]
                 if f["status"] == "in_progress")
    def body(device, action_id, event_id):
        return {"device_id": device, "actions": [
            {"action_id": action_id, "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 0,
             "payload": {"event_id": event_id, "match_id": match["match_id"], "type": "score",
                         "payload": {"team_id": match["home"]["team_id"], "event_type": "goal"}}},
            {"action_id": action_id + "-r", "type": "roster_transfer", "queued_at": "2026-10-17T11:01:00Z",
             "base_version": 0, "payload": {"request_id": "tr-" + action_id, "league_id": "league-alpha-1",
                                            "player_id": "demo-player-4", "type": "release", "from_squad_id": "club-alpha-1",
                                            "to_squad_id": None, "effective_date": "2026-10-17", "reason": "x"}}]}
    r = client.post("/api/v1/offline-sync", json=body("dev-v", "v1", "off-v1"), headers=_auth(client, "viewer")).json()
    assert [x["error_code"] for x in r["results"]] == ["FORBIDDEN", "FORBIDDEN"]
    assert r["summary"] == {"applied": 0, "rejected": 2, "duplicate": 0}
    r = client.post("/api/v1/offline-sync", json=body("dev-o", "o1", "off-o1"), headers=_auth(client, "organizer")).json()
    assert [x["status"] for x in r["results"]] == ["applied", "rejected"]
    r = client.post("/api/v1/offline-sync", json=body("dev-m", "m1", "off-m1"), headers=_auth(client, "manager")).json()
    assert [x["status"] for x in r["results"]] == ["rejected", "applied"]


def test_receipt_only_for_owner(client):
    order = {"order_id": "app-1", "items": [{"variant_id": "var-jersey-001-L", "quantity": 1}],
             "discount_code": None, "payment": {"token": "tok_success"}, "customer_id": "someone-else"}
    assert client.post("/api/v1/checkout", json=order, headers=_auth(client, "player")).status_code == 201
    assert client.get("/api/v1/orders/app-1/receipt.pdf", headers=_auth(client, "player")).content.startswith(b"%PDF")
    assert client.get("/api/v1/orders/app-1/receipt.pdf", headers=_auth(client, "viewer")).status_code == 403
    assert client.get("/api/v1/orders/app-1/receipt.pdf", headers=_auth(client, "admin")).status_code == 200
    assert client.get("/api/v1/orders/nope/receipt.pdf", headers=_auth(client, "admin")).status_code == 404
