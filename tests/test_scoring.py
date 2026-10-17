from app.util import canonical, lots_key, sign

KABADDI = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
           "periods": {"count": 2, "duration_minutes": 20},
           "scoring_events": {"raid_point": {"points": 1}, "tackle_point": {"points": 1}, "all_out": {"points": 2}},
           "draw_allowed": False, "overtime": {"policy": "golden_score", "duration_minutes": 5},
           "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
           "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2, "defender": 3}}}


def ev(c, eid, mid, t, payload=None, status=None):
    r = c.post("/audit/v1/events", json={"event_id": eid, "match_id": mid, "type": t, "payload": payload or {}})
    if status is not None:
        assert r.status_code == status, r.text
    return r


def test_reference_vectors():
    assert canonical({"team_id": "t1", "event_type": "goal"}) == '{"event_type":"goal","team_id":"t1"}'
    assert sign("evt-1", {"team_id": "t1", "event_type": "goal"}, "demo-salt") == \
        "972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501"
    assert lots_key(42, "lg-1", "t1").startswith("0613316991ce")


def test_mystery_sport_flow(client):
    r = client.post("/audit/v1/sports", json=KABADDI)
    assert r.status_code == 201 and r.json()["config"]["sport_id"] == "kabaddi"
    assert client.post("/audit/v1/sports", json=KABADDI).json()["error"]["code"] == "SPORT_EXISTS"
    ev(client, "e1", "k1", "match_init", {"sport_id": "kabaddi", "home_team_id": "A", "away_team_id": "B"}, 201)
    ev(client, "e1b", "k1", "match_init", {"sport_id": "kabaddi", "home_team_id": "A", "away_team_id": "B"}, 409)
    assert ev(client, "e2", "k1", "score", {"team_id": "A", "event_type": "all_out"}).json()["error"]["code"] == \
        "MATCH_NOT_IN_PROGRESS"
    ev(client, "e3", "k1", "match_start", status=201)
    ev(client, "e3x", "k1", "match_start", status=409)
    r = ev(client, "e4", "k1", "score", {"team_id": "A", "event_type": "all_out"}, 201).json()
    assert r["sequence"] == 3 and r["match_version"] == 3
    assert r["signature"] == sign("e4", {"team_id": "A", "event_type": "all_out"})
    assert ev(client, "e5", "k1", "score", {"team_id": "A", "event_type": "goal"}).json()["error"]["code"] == \
        "UNKNOWN_EVENT_TYPE"
    assert ev(client, "e5", "k1", "score", {"team_id": "Z", "event_type": "raid_point"}).status_code == 400
    ev(client, "e6", "k1", "score", {"team_id": "B", "event_type": "raid_point"}, 201)
    ev(client, "e7", "k1", "score", {"team_id": "B", "event_type": "tackle_point"}, 201)
    assert ev(client, "e8", "k1", "match_end").json()["error"]["code"] == "TIE_NOT_ALLOWED"
    ev(client, "e9", "k1", "tiebreak_winner", {"team_id": "B"}, 201)
    ev(client, "e10", "k1", "match_end", status=201)
    s = client.get("/audit/v1/score/k1").json()
    assert s["outcome"] == "away_win" and s["winner_team_id"] == "B" and s["home"]["score"] == 2
    ev(client, "e11", "k1", "compensation", {"compensates": "e9", "reason": "VAR"}, 201)
    s = client.get("/audit/v1/score/k1").json()
    assert s["outcome"] == "undecided" and s["winner_team_id"] is None and s["tiebreak_winner_team_id"] is None
    e9 = [e for e in s["events"] if e["event_id"] == "e9"][0]
    assert e9["compensated"] and e9["compensated_by"] == "e11"
    assert ev(client, "e12", "k1", "compensation", {"compensates": "e9"}).json()["error"]["code"] == \
        "INVALID_COMPENSATION"
    assert ev(client, "e12", "k1", "compensation", {"compensates": "e3"}).status_code == 409
    assert ev(client, "e12", "k1", "compensation", {"compensates": "nope"}).json()["error"]["code"] == \
        "EVENT_NOT_FOUND"
    assert ev(client, "e13", "zz", "match_start").json()["error"]["code"] == "MATCH_NOT_FOUND"
    assert ev(client, "e14", "k2", "match_init", {"sport_id": "nosport", "home_team_id": "A",
                                                  "away_team_id": "B"}).json()["error"]["code"] == "SPORT_NOT_FOUND"


def test_idempotency(client):
    ev(client, "i1", "m", "match_init", {"sport_id": "football", "home_team_id": "A", "away_team_id": "B"}, 201)
    r = ev(client, "i1", "m", "match_init", {"sport_id": "football", "home_team_id": "A", "away_team_id": "B"}, 200)
    assert r.json()["sequence"] == 1
    assert ev(client, "i1", "m", "match_start").json()["error"]["code"] == "DUPLICATE_EVENT_ID"


def test_innings_model(client):
    ev(client, "c0", "cm", "match_init", {"sport_id": "cricket", "home_team_id": "H", "away_team_id": "A"}, 201)
    ev(client, "c1", "cm", "match_start", status=201)
    for i, t in enumerate(["six", "wide", "single", "four", "wicket", "dot_ball", "two"]):
        ev(client, f"c{i + 2}", "cm", "score", {"team_id": "H", "event_type": t}, 201)
    s = client.get("/audit/v1/score/cm").json()["home"]
    assert s == {"team_id": "H", "score": 14, "wickets": 1, "balls": 6, "overs": "1.0", "fair_play": 0}
    ev(client, "d0", "cm2", "match_init", {"sport_id": "cricket", "home_team_id": "H", "away_team_id": "A"}, 201)
    ev(client, "d1", "cm2", "match_start", status=201)
    for i in range(10):
        ev(client, f"dw{i}", "cm2", "score", {"team_id": "A", "event_type": "wicket"}, 201)
    assert ev(client, "dw10", "cm2", "score", {"team_id": "A", "event_type": "single"}).json()["error"]["code"] == \
        "INNINGS_COMPLETE"
    ev(client, "dc", "cm2", "compensation", {"compensates": "dw0", "reason": "no ball"}, 201)
    ev(client, "dw11", "cm2", "score", {"team_id": "A", "event_type": "single"}, 201)


def test_round_model(client):
    ev(client, "r0", "es", "match_init", {"sport_id": "esports", "home_team_id": "H", "away_team_id": "A"}, 201)
    ev(client, "r1", "es", "match_start", status=201)
    ev(client, "r2", "es", "score", {"team_id": "H", "event_type": "round_win"}, 201)
    ev(client, "r3", "es", "score", {"team_id": "H", "event_type": "round_win"}, 201)
    assert ev(client, "r4", "es", "score", {"team_id": "A", "event_type": "round_win"}).json()["error"]["code"] == \
        "SERIES_ALREADY_DECIDED"
    ev(client, "r5", "es", "discipline", {"team_id": "A", "points": -2}, 201)
    ev(client, "r6", "es", "match_end", status=201)
    s = client.get("/audit/v1/score/es").json()
    assert s["outcome"] == "home_win" and s["away"]["fair_play"] == -2 and s["home"]["overs"] is None
    assert client.get("/audit/v1/score/none").status_code == 404


def test_sport_validation(client):
    bad = dict(KABADDI, sport_id="x'; DROP TABLE sports;--")
    r = client.post("/audit/v1/sports", json=bad)
    assert r.status_code == 400 and "sport_id" in r.json()["error"]["details"]["fields"]
    for patch in [{"scoring_model": "x"}, {"periods": {"count": 0}}, {"scoring_events": {}},
                  {"draw_allowed": "no"}, {"overtime": {"policy": "x"}}, {"tie_break_order": ["scored", "scored"]},
                  {"roster": {"min_squad_size": 5, "max_squad_size": 2}}, {"name": ""}]:
        assert client.post("/audit/v1/sports", json=dict(KABADDI, **patch)).status_code == 400
    inn = dict(KABADDI, sport_id="mini_cricket", scoring_model="innings",
               periods={"innings_per_team": 1, "overs_per_innings": 1, "balls_per_over": 6, "wickets_per_innings": 2},
               scoring_events={"super_six": {"runs": 6, "legal_ball": True, "wicket": False}})
    assert client.post("/audit/v1/sports", json=inn).status_code == 201
    rnd = dict(KABADDI, sport_id="bo5", scoring_model="round", periods={"best_of": 4},
               scoring_events={"map_win": {"rounds": 1}})
    assert client.post("/audit/v1/sports", json=rnd).status_code == 400
    assert client.post("/audit/v1/sports", content=b"{bad json").status_code == 400
