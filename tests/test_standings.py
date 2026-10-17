from tests.test_scoring import ev


def league(c, lid, teams, fixtures, sport="football", **kw):
    body = {"league_id": lid, "sport_id": sport, "teams": teams,
            "fixtures": [{"match_id": m, "home": h, "away": a} for m, h, a in fixtures],
            "qualification": {"spots": kw.pop("spots", 2)}, **kw}
    return c.post("/audit/v1/leagues", json=body)


def play(c, mid, events, end=True):
    ev(c, f"{mid}-s", mid, "match_start", status=201)
    for i, (team, et) in enumerate(events):
        ev(c, f"{mid}-e{i}", mid, "score", {"team_id": team, "event_type": et}, 201)
    if end:
        ev(c, f"{mid}-end", mid, "match_end", status=201)


def test_league_registration_errors(client):
    assert league(client, "L", ["a", "b"], [("x1", "a", "b")]).status_code == 201
    assert league(client, "L", ["a", "b"], [("x2", "a", "b")]).json()["error"]["code"] == "LEAGUE_EXISTS"
    assert league(client, "L2", ["a", "b"], [("x1", "a", "b")]).json()["error"]["code"] == "MATCH_EXISTS"
    assert league(client, "L3", ["a", "b"], [("x3", "a", "b")], sport="nope").json()["error"]["code"] == \
        "SPORT_NOT_FOUND"
    assert league(client, "L4", ["a", "b"], [("x4", "a", "c")]).status_code == 400
    assert league(client, "L5", ["a", "b"], [("x5", "a", "b")], spots=3).status_code == 400
    assert client.get("/audit/v1/standings/none").status_code == 404


def test_three_way_h2h(client):
    teams = ["t1", "t2", "t3", "t4"]
    fx = [("m1", "t1", "t2"), ("m2", "t2", "t3"), ("m3", "t3", "t1"), ("m4", "t1", "t4"), ("m5", "t2", "t4"),
          ("m6", "t3", "t4")]
    assert league(client, "lg-1", teams, fx).status_code == 201
    play(client, "m1", [("t1", "goal"), ("t1", "goal"), ("t1", "goal")])  # t1 3-0 t2
    play(client, "m2", [("t2", "goal")])  # t2 1-0 t3
    play(client, "m3", [("t3", "goal")])  # t3 1-0 t1
    play(client, "m4", [("t4", "goal")])  # t4 beats t1
    play(client, "m5", [("t4", "goal")])  # t4 beats t2
    play(client, "m6", [("t4", "goal")])  # t4 beats t3
    st = client.get("/audit/v1/standings/lg-1").json()
    order = [r["team_id"] for r in st["table"]]
    assert order[0] == "t4"
    # t1, t2, t3 all 3 pts, h2h points 3 each; h2h diff: t1 +2, t2 -2, t3 0
    assert order[1:] == ["t1", "t3", "t2"]
    rows = {r["team_id"]: r for r in st["table"]}
    assert rows["t1"]["resolved_by"] == "h2h_diff" and rows["t3"]["resolved_by"] == "h2h_diff"
    assert rows["t2"]["resolved_by"] is None and rows["t4"]["resolved_by"] is None
    assert st["h2h"]["t1"]["t2"] == {"played": 1, "points": 3, "scored": 3, "conceded": 0}
    assert st["h2h"]["t2"]["t1"]["points"] == 0
    assert rows["t4"]["status"] == "clinched"
    # compensation after the fact changes everything
    ev(client, "fix", "m1", "compensation", {"compensates": "m1-e0", "reason": "offside"}, 201)
    ev(client, "fix2", "m1", "compensation", {"compensates": "m1-e1", "reason": "offside"}, 201)
    ev(client, "fix3", "m1", "compensation", {"compensates": "m1-e2", "reason": "offside"}, 201)
    st = client.get("/audit/v1/standings/lg-1").json()
    rows = {r["team_id"]: r for r in st["table"]}
    assert rows["t1"]["drawn"] == 1 and rows["t2"]["drawn"] == 1


def test_draw_lots_and_status(client):
    teams = ["t1", "t2", "t3"]
    league(client, "lg-1", teams, [("a1", "t1", "t2"), ("a2", "t2", "t3"), ("a3", "t1", "t3")], spots=1)
    st = client.get("/audit/v1/standings/lg-1").json()
    assert [r["team_id"] for r in st["table"]] == ["t1", "t3", "t2"]
    assert all(r["resolved_by"] == "draw_lots" for r in st["table"][:2])
    assert all(r["status"] == "still_possible" for r in st["table"])
    play(client, "a1", [("t1", "goal")])
    play(client, "a3", [("t1", "goal")])
    st = client.get("/audit/v1/standings/lg-1").json()
    rows = {r["team_id"]: r for r in st["table"]}
    assert rows["t1"]["status"] == "clinched" and rows["t2"]["status"] == "eliminated"
    assert rows["t1"]["points"] == 6


def test_custom_points_and_tiebreak_order(client):
    teams = ["a", "b"]
    league(client, "L", teams, [("g1", "a", "b"), ("g2", "b", "a")], points={"win": 2, "draw": 1, "loss": 0},
           tie_break_order=["scored"], spots=1, lots_seed=7)
    play(client, "g1", [("a", "goal")])
    play(client, "g2", [("b", "goal"), ("b", "goal")])
    st = client.get("/audit/v1/standings/L").json()
    assert [r["team_id"] for r in st["table"]] == ["b", "a"]
    assert st["table"][0]["resolved_by"] == "scored" and st["table"][0]["points"] == 2


def test_innings_nrr(client):
    league(client, "C", ["x", "y"], [("cc1", "x", "y")], sport="cricket", spots=1)
    ev(client, "cc1-s", "cc1", "match_start", status=201)
    for i in range(6):
        ev(client, f"cx{i}", "cc1", "score", {"team_id": "x", "event_type": "four"}, 201)
    for i in range(10):
        ev(client, f"cy{i}", "cc1", "score", {"team_id": "y", "event_type": "wicket"}, 201)
    ev(client, "cc1-end", "cc1", "match_end", status=201)
    st = client.get("/audit/v1/standings/C").json()
    rows = {r["team_id"]: r for r in st["table"]}
    # x: 24 runs off 1 over; y all out -> counts as 20 overs
    assert rows["x"]["diff"] == round(24 / 1 - 0 / 20, 3)
    assert rows["y"]["diff"] == round(0 / 20 - 24 / 1, 3)


def test_undecided_counts_as_remaining(client):
    league(client, "B", ["p", "q"], [("bb1", "p", "q")], sport="basketball", spots=1)
    ev(client, "bb1-s", "bb1", "match_start", status=201)
    ev(client, "bb1-t", "bb1", "tiebreak_winner", {"team_id": "p"}, 201)
    ev(client, "bb1-end", "bb1", "match_end", status=201)
    st = client.get("/audit/v1/standings/B").json()
    assert {r["team_id"]: r["won"] for r in st["table"]} == {"p": 1, "q": 0}
    ev(client, "bb1-c", "bb1", "compensation", {"compensates": "bb1-t"}, 201)
    st = client.get("/audit/v1/standings/B").json()
    assert all(r["played"] == 0 for r in st["table"])
