SETUP = {
    "league": {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "sport_id": "football",
               "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"},
               "max_squad_size": 3, "required_positions": {"gk": 1}},
    "squads": [{"squad_id": "sq-a", "club_id": "club-a", "tenant_id": "tenant-alpha", "name": "A"},
               {"squad_id": "sq-b", "club_id": "club-b", "tenant_id": "tenant-alpha", "name": "B"},
               {"squad_id": "sq-x", "club_id": "club-x", "tenant_id": "tenant-beta", "name": "X"}],
    "players": [{"player_id": "p1", "name": "Ali", "position": "gk", "squad_id": "sq-a", "role": "captain"},
                {"player_id": "p2", "name": "Bilal", "position": "df", "squad_id": "sq-a", "role": "starter"},
                {"player_id": "p3", "name": "Cyrus", "position": "df", "squad_id": "sq-b", "role": "starter"}],
    "matches_in_progress": [],
}


def tr(c, rid, pid, typ="transfer", frm="sq-a", to="sq-b", eff="2026-09-30", end=None, status=None):
    r = c.post("/audit/v1/roster/transfer", json={
        "request_id": rid, "league_id": "lg-r1", "player_id": pid, "type": typ, "from_squad_id": frm,
        "to_squad_id": to, "effective_date": eff, "loan_end_date": end, "reason": "Tactical move",
        "requested_by": "user-77"})
    if status:
        assert r.status_code == status, r.text
    return r


def code(r):
    return r.json()["error"]["code"]


def test_setup_and_transfer(client):
    r = client.post("/audit/v1/roster/setup", json=SETUP)
    assert r.status_code == 201 and r.json()["squad_counts"] == {"sq-a": 2, "sq-b": 1, "sq-x": 0}
    r = tr(client, "tr-001", "p2", status=201).json()
    assert r["state"] == "active" and r["registration"]["squad_id"] == "sq-b"
    assert r["registration"]["role"] == "substitute" and r["audit_entry"]["audit_id"] == "au-0001"
    assert r["audit_entry"]["who"] == "user-77" and r["audit_entry"]["why"] == "Tactical move"
    assert tr(client, "tr-001", "p2").status_code == 200
    h = client.get("/audit/v1/roster/history/p2").json()
    assert len(h["history"]) == 1 and h["current_squad_id"] == "sq-b"


def test_rule_order(client):
    client.post("/audit/v1/roster/setup", json=SETUP)
    assert code(tr(client, "r1", "p2", eff="2026-13-01")) == "VALIDATION_ERROR"
    assert code(tr(client, "r1", "p2", typ="loan", end="2026-09-01", eff="2026-09-10")) == "VALIDATION_ERROR"
    assert code(tr(client, "r1", "zz")) == "PLAYER_NOT_FOUND"
    assert code(tr(client, "r1", "p2", to="nope")) == "SQUAD_NOT_FOUND"
    assert code(tr(client, "r1", "p2", to="sq-x")) == "CROSS_TENANT_TRANSFER"
    assert code(tr(client, "r1", "p3")) == "NOT_IN_SQUAD"
    assert code(tr(client, "r1", "p2", eff="2026-10-01")) == "TRANSFER_WINDOW_CLOSED"
    assert code(tr(client, "r1", "p1")) == "MIN_POSITION_VIOLATION"
    assert tr(client, "r2", "p2", typ="release", to=None, eff="2026-09-15").status_code == 201
    r = client.post("/audit/v1/roster/transfer", json={"request_id": "x", "league_id": "nope", "player_id": "p1",
                                                       "type": "release", "from_squad_id": "sq-a",
                                                       "effective_date": "2026-09-01"})
    assert code(r) == "LEAGUE_NOT_FOUND"
    assert client.get("/audit/v1/roster/history/p2").json()["current_squad_id"] is None


def test_squad_full(client):
    s = dict(SETUP, players=SETUP["players"] + [
        {"player_id": "p4", "name": "D", "position": "df", "squad_id": "sq-b", "role": "starter"},
        {"player_id": "p5", "name": "E", "position": "df", "squad_id": "sq-b", "role": "starter"}])
    client.post("/audit/v1/roster/setup", json=s)
    assert code(tr(client, "f1", "p2")) == "SQUAD_FULL"


def test_loan_and_auto_return(client):
    client.post("/audit/v1/roster/setup", json=SETUP)
    r = tr(client, "l1", "p2", typ="loan", eff="2026-09-05", end="2026-12-31", status=201).json()
    assert r["registration"]["registration_type"] == "loan" and r["registration"]["parent_squad_id"] == "sq-a"
    assert code(tr(client, "l2", "p2", frm="sq-b", to="sq-a", eff="2026-09-20")) == "PLAYER_ON_LOAN"
    assert code(tr(client, "l3", "p2", frm="sq-a", eff="2026-09-20")) == "NOT_IN_SQUAD"
    h = client.get("/audit/v1/roster/history/p2?as_of=2026-10-01").json()
    assert h["current_squad_id"] == "sq-b" and h["parent_squad_id"] == "sq-a" and len(h["history"]) == 1
    for _ in range(2):
        h = client.get("/audit/v1/roster/history/p2?as_of=2027-01-05").json()
        assert h["current_squad_id"] == "sq-a" and h["parent_squad_id"] is None
        assert [e["action"] for e in h["history"]] == ["loan", "loan_return"]
        assert h["history"][1]["who"] == "system" and h["history"][1]["effective_date"] == "2027-01-01"
    assert client.get("/audit/v1/roster/history/p2?as_of=bad").status_code == 400
    assert client.get("/audit/v1/roster/history/none").status_code == 404


def test_deferred_in_progress(client):
    s = dict(SETUP, matches_in_progress=[{"match_id": "m-live", "home_squad_id": "sq-a", "away_squad_id": "sq-b"}])
    client.post("/audit/v1/roster/setup", json=s)
    r = tr(client, "d1", "p2", eff="2026-09-30", status=201).json()
    assert r["state"] == "deferred_until_match_end" and r["blocking_match_id"] == "m-live"
