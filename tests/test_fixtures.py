import itertools

import pytest

from app import fixtures


def rr(n, legs=1, **params):
    teams = [f"t{i}" for i in range(1, n + 1)]
    return teams, fixtures.generate({"format": "round_robin", "teams": teams, "params": {"legs": legs, **params}})


@pytest.mark.parametrize("n", list(range(2, 41)))
@pytest.mark.parametrize("legs", [1, 2])
def test_round_robin_properties(n, legs):
    teams, out = rr(n, legs)
    per_leg = n - 1 if n % 2 == 0 else n
    assert out["round_count"] == per_leg * legs
    pairs = {}
    for leg in range(1, legs + 1):
        home = {t: 0 for t in teams}
        away = {t: 0 for t in teams}
        byes = {t: 0 for t in teams}
        for rnd in out["rounds"]:
            ms = [m for m in rnd["matches"] if m["leg"] == leg]
            if not ms:
                continue
            assert len(ms) == n // 2
            seen = [m["home"] for m in ms] + [m["away"] for m in ms] + rnd["byes"]
            assert sorted(seen) == sorted(teams)
            assert len(rnd["byes"]) == n % 2
            for b in rnd["byes"]:
                byes[b] += 1
            for i, m in enumerate(ms, 1):
                assert m["match_id"] == f"RR-L{leg}-R{rnd['round']}-M{i}"
                home[m["home"]] += 1
                away[m["away"]] += 1
                pairs[(m["home"], m["away"])] = pairs.get((m["home"], m["away"]), 0) + 1
        assert all(abs(home[t] - away[t]) <= 1 for t in teams)
        if n % 2:
            assert all(byes[t] == 1 for t in teams)
    for a, b in itertools.combinations(teams, 2):
        assert pairs.get((a, b), 0) + pairs.get((b, a), 0) == legs
        if legs == 2:
            assert pairs.get((a, b)) == 1 and pairs.get((b, a)) == 1


def test_round_robin_example_and_withdrawal():
    _, out = rr(5, withdrawals=[{"team_id": "t3", "after_round": 2}])
    r1 = out["rounds"][0]
    assert r1["byes"] == ["t1"]
    assert [(m["home"], m["away"]) for m in r1["matches"]] == [("t2", "t5"), ("t3", "t4")]
    s = out["summary"]
    assert s["total"] == 10 and s["forfeit"] == 2 and s["scheduled"] == 8
    for rnd in out["rounds"]:
        for m in rnd["matches"]:
            if "t3" in (m["home"], m["away"]) and rnd["round"] > 2:
                assert m["status"] == "forfeit" and m["awarded_to"] != "t3"
    _, out = rr(4, withdrawal_policy="void_all", withdrawals=[{"team_id": "t1", "after_round": 1},
                                                              {"team_id": "t2", "after_round": 3}])
    assert out["summary"]["voided"] == 5
    _, out = rr(4, withdrawals=[{"team_id": "t1", "after_round": 0}, {"team_id": "t2", "after_round": 0}])
    assert out["summary"]["voided"] == 1 and out["summary"]["forfeit"] == 4


@pytest.mark.parametrize("body", [
    {"format": "round_robin", "teams": ["a"]},
    {"format": "round_robin", "teams": ["a", "a"]},
    {"format": "nope", "teams": ["a", "b"]},
    {"format": "round_robin", "teams": ["a", "b"], "params": {"legs": 3}},
    {"format": "round_robin", "teams": ["a", "b"], "params": {"withdrawals": [{"team_id": "x", "after_round": 0}]}},
    {"format": "round_robin", "teams": ["a", "b"], "params": {"withdrawals": [{"team_id": "a", "after_round": 9}]}},
    {"format": "double_elim", "teams": ["a", "b"]},
    {"format": "swiss", "teams": ["a", "b", "c"], "params": {"round": 2, "history": []}},
])
def test_fixture_validation(client, body):
    r = client.post("/audit/v1/fixtures", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_swiss_round1_and_example(client):
    teams = ["t1", "t2", "t3", "t4", "t5"]
    out = fixtures.generate({"format": "swiss", "teams": teams, "params": {}})
    assert out["bye"] == "t5"
    assert [(p["home"], p["away"]) for p in out["pairings"]] == [("t1", "t3"), ("t2", "t4")]
    out = client.post("/audit/v1/fixtures", json={"format": "swiss", "teams": teams, "params": {
        "total_rounds": 3, "round": 2, "history": [{"round": 1, "bye": "t5", "matches": [
            {"home": "t1", "away": "t3", "result": "home"}, {"home": "t2", "away": "t4", "result": "draw"}]}]}}).json()
    st = {s["team_id"]: s for s in out["standings"]}
    assert [s["team_id"] for s in out["standings"]][:2] == ["t1", "t5"]
    assert st["t2"]["score"] == 0.5 and st["t2"]["buchholz"] == 0.5
    assert out["bye"] == "t3"
    used = [p["home"] for p in out["pairings"]] + [p["away"] for p in out["pairings"]]
    assert sorted(used + [out["bye"]]) == teams
    assert {"t1", "t3"} not in [{p["home"], p["away"]} for p in out["pairings"]]


def test_swiss_no_valid_pairing(client):
    teams = ["a", "b", "c", "d"]
    hist = [{"round": 1, "bye": None, "matches": [{"home": "a", "away": "b", "result": "home"},
                                                  {"home": "c", "away": "d", "result": "home"}]},
            {"round": 2, "bye": None, "matches": [{"home": "a", "away": "c", "result": "home"},
                                                  {"home": "b", "away": "d", "result": "home"}]},
            {"round": 3, "bye": None, "matches": [{"home": "a", "away": "d", "result": "home"},
                                                  {"home": "b", "away": "c", "result": "home"}]}]
    r = client.post("/audit/v1/fixtures", json={"format": "swiss", "teams": teams + ["e", "f"],
                                                "params": {"total_rounds": 5, "round": 4, "history": hist}})
    assert r.status_code == 409 and r.json()["error"]["details"] == {"round": 4}
    hist4 = [{"round": 1, "bye": None, "matches": [{"home": "a", "away": "b", "result": "home"}]}]
    r = client.post("/audit/v1/fixtures", json={"format": "swiss", "teams": ["a", "b"],
                                                "params": {"total_rounds": 1, "round": 1}})
    assert r.status_code == 200
    teams3 = ["a", "b", "c"]
    h = [{"round": 1, "bye": "c", "matches": [{"home": "a", "away": "b", "result": "home"}]},
         {"round": 2, "bye": "b", "matches": [{"home": "a", "away": "c", "result": "draw"}]}]
    r = client.post("/audit/v1/fixtures", json={"format": "swiss", "teams": teams3,
                                                "params": {"total_rounds": 2, "round": 2, "history": h[:1]}})
    assert r.status_code == 200
    teams4 = ["a", "b", "c", "d"]
    h = [{"round": 1, "bye": None, "matches": [{"home": "a", "away": "c", "result": "home"},
                                               {"home": "b", "away": "d", "result": "home"}]},
         {"round": 2, "bye": None, "matches": [{"home": "a", "away": "b", "result": "home"},
                                               {"home": "c", "away": "d", "result": "home"}]}]
    r = client.post("/audit/v1/fixtures", json={"format": "swiss", "teams": teams4,
                                                "params": {"total_rounds": 3, "round": 3, "history": h}})
    assert r.status_code == 200
    assert {frozenset((p["home"], p["away"])) for p in r.json()["pairings"]} == {frozenset("ad"), frozenset("bc")}


def test_swiss_optimal_not_greedy():
    # scores: a=2,b=2,c=1,d=1 ; a-b already met, c-d met -> must pair a-c/b-d (cost 2) or a-d/b-c (cost 2)
    teams = ["a", "b", "c", "d"]
    hist = [{"round": 1, "bye": None, "matches": [{"home": "a", "away": "b", "result": "draw"},
                                                  {"home": "c", "away": "d", "result": "draw"}]}]
    out = fixtures.generate({"format": "swiss", "teams": teams, "params": {"total_rounds": 3, "round": 2,
                                                                          "history": hist}})
    assert len(out["pairings"]) == 2


def test_swiss_409(client):
    teams = ["a", "b", "c", "d"]
    h = [{"round": 1, "bye": None, "matches": [{"home": "a", "away": "b", "result": "home"},
                                               {"home": "c", "away": "d", "result": "home"}]},
         {"round": 2, "bye": None, "matches": [{"home": "a", "away": "c", "result": "home"},
                                               {"home": "b", "away": "d", "result": "home"}]},
         {"round": 3, "bye": None, "matches": [{"home": "a", "away": "d", "result": "home"},
                                               {"home": "b", "away": "c", "result": "home"}]}]
    # 4 teams can only play 3 rounds; total_rounds max n-1=3 so construct with 5 teams instead
    r = client.post("/audit/v1/fixtures", json={"format": "swiss", "teams": teams,
                                                "params": {"total_rounds": 3, "round": 3, "history": h[:2] + []}})
    assert r.status_code == 200
    teams5 = ["a", "b", "c"]
    h3 = [{"round": 1, "bye": "c", "matches": [{"home": "a", "away": "b", "result": "home"}]}]
    r = client.post("/audit/v1/fixtures", json={"format": "swiss", "teams": ["a", "b"],
                                                "params": {"total_rounds": 1, "round": 1}})
    assert r.status_code == 200


def test_swiss_no_pairing_409_direct():
    teams = ["a", "b", "c", "d", "e", "f"]
    played_all = []
    # a,b,c have all played each other and d,e,f too; remaining edges cross -> make cross edges used as well
    import itertools as it
    pairs = list(it.combinations(teams, 2))
    rounds = []
    # Build history from a 1-factorisation of K6 (5 rounds), then ask for round 6 with total 5 -> invalid round
    from app.fixtures import circle_rounds
    for i, rnd in enumerate(circle_rounds(teams), 1):
        rounds.append({"round": i, "bye": None, "matches": [{"home": a, "away": b, "result": "draw"} for a, b in rnd]})
    with pytest.raises(Exception):
        fixtures.generate({"format": "swiss", "teams": teams, "params": {"total_rounds": 5, "round": 6,
                                                                        "history": rounds}})
    # 4 rounds played, 5th round still possible
    out = fixtures.generate({"format": "swiss", "teams": teams, "params": {"total_rounds": 5, "round": 5,
                                                                          "history": rounds[:4]}})
    assert len(out["pairings"]) == 3


def test_swiss_409_odd():
    from app.util import ApiError
    teams = ["a", "b", "c", "d"]
    # after a-b, c-d, a-c, b-d: only a-d, b-c remain. Force with 3rd round where a-d and b-c played via 'd' bye trick
    hist = [{"round": 1, "bye": None, "matches": [{"home": "a", "away": "b", "result": "home"},
                                                  {"home": "c", "away": "d", "result": "home"}]},
            {"round": 2, "bye": None, "matches": [{"home": "a", "away": "c", "result": "home"},
                                                  {"home": "b", "away": "d", "result": "home"}]}]
    hist_bad = [{"round": 1, "bye": None, "matches": [{"home": "a", "away": "b", "result": "home"},
                                                      {"home": "a", "away": "d", "result": "home"},
                                                      {"home": "a", "away": "c", "result": "home"}]}]
    with pytest.raises(ApiError) as e:
        fixtures.generate({"format": "swiss", "teams": teams, "params": {"total_rounds": 3, "round": 2,
                                                                        "history": hist_bad}})
    assert e.value.code == "NO_VALID_PAIRING" and e.value.details == {"round": 2}


def test_single_elim_structure(client):
    teams = [f"t{i}" for i in range(1, 7)]
    out = client.post("/audit/v1/fixtures", json={"format": "single_elim", "teams": teams,
                                                  "params": {"results": [{"match_id": "R1M2", "winner": "t4"}]}}).json()
    assert out["bracket_size"] == 8 and len(out["rounds"]) == 3
    r1 = {m["match_id"]: m for m in out["rounds"][0]["matches"]}
    assert r1["R1M1"]["bye"] and r1["R1M1"]["home"] == "t1" and r1["R1M1"]["away"] is None
    assert r1["R1M1"]["winner"] == "t1"
    assert (r1["R1M2"]["home"], r1["R1M2"]["away"]) == ("t4", "t5")
    assert r1["R1M2"]["winner_to"] == {"match_id": "R2M1", "slot": "away"}
    r2 = {m["match_id"]: m for m in out["rounds"][1]["matches"]}
    assert r2["R2M1"]["home"] == "t1" and r2["R2M1"]["away"] == "t4" and r2["R2M1"]["away_seed"] == 4
    assert out["rounds"][2]["matches"][0]["winner_to"] is None
    assert fixtures.seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    bad = client.post("/audit/v1/fixtures", json={"format": "single_elim", "teams": teams,
                                                  "params": {"results": [{"match_id": "R1M2", "winner": "t1"}]}})
    assert bad.status_code == 400
    bad = client.post("/audit/v1/fixtures", json={"format": "single_elim", "teams": teams,
                                                  "params": {"results": [{"match_id": "X", "winner": "t1"}]}})
    assert bad.status_code == 400


def test_single_elim_third_place():
    teams = ["a", "b", "c", "d"]
    out = fixtures.generate({"format": "single_elim", "teams": teams, "params": {
        "third_place_match": True, "results": [{"match_id": "R1M1", "winner": "a"}, {"match_id": "R1M2", "winner": "c"},
                                               {"match_id": "TP", "winner": "d"}]}})
    ms = {m["match_id"]: m for r in out["rounds"] for m in r["matches"]}
    assert ms["TP"]["home"] == "d" and ms["TP"]["away"] == "b" and ms["TP"]["winner"] == "d"
    assert ms["R1M1"]["loser_to"] == {"match_id": "TP", "slot": "home"}


@pytest.mark.parametrize("n", [3, 5, 6, 8, 11, 16, 33])
def test_double_elim_graph(n):
    teams = [f"t{i}" for i in range(1, n + 1)]
    out = fixtures.generate({"format": "double_elim", "teams": teams, "params": {"bracket_reset": True}})
    B = out["bracket_size"]
    k = B.bit_length() - 1
    assert [len(r["matches"]) for r in out["winners"]] == [B // 2 ** r for r in range(1, k + 1)]
    assert sum(len(r["matches"]) for r in out["losers"]) == B - 2
    assert len(out["losers"]) == 2 * (k - 1)
    allm = [m for r in out["winners"] + out["losers"] for m in r["matches"]] + out["grand_final"]
    ids = {m["match_id"] for m in allm}
    fed = {}
    for m in allm:
        for key in ("winner_to", "loser_to"):
            if m[key]:
                assert m[key]["match_id"] in ids
                slot = (m[key]["match_id"], m[key]["slot"])
                assert slot not in fed
                fed[slot] = m["match_id"]
        if m["bracket"] == "winners":
            assert m["loser_to"] is not None
        if m["bracket"] == "losers":
            assert m["loser_to"] is None
    wf = out["winners"][-1]["matches"][0]
    lf = out["losers"][-1]["matches"][0]
    assert wf["winner_to"] == {"match_id": "GF1", "slot": "home"}
    assert wf["loser_to"]["match_id"] == lf["match_id"] and wf["loser_to"]["slot"] == "away"
    assert lf["winner_to"] == {"match_id": "GF1", "slot": "away"}
    for m in allm:
        if not m["match_id"].startswith("WR1"):
            assert (m["match_id"], "home") in fed and (m["match_id"], "away") in fed
    gf2 = out["grand_final"][1]
    assert gf2["conditional"] is True and gf2["required"] is None


def _play_all(teams, reset, gf_winner_side):
    results = []
    for _ in range(200):
        out = fixtures.generate({"format": "double_elim", "teams": teams,
                                 "params": {"bracket_reset": reset, "results": results}})
        allm = [m for r in out["winners"] + out["losers"] for m in r["matches"]] + out["grand_final"][:1]
        pending = [m for m in allm if m["winner"] is None and m["home"] and m["away"]
                   and m["match_id"] not in {r["match_id"] for r in results}]
        if not pending:
            return out
        for m in pending:
            w = m["home"]
            if m["match_id"] == "GF1":
                w = m[gf_winner_side]
            results.append({"match_id": m["match_id"], "winner": w})
    raise AssertionError("did not finish")


def test_double_elim_reset_semantics():
    teams = [f"t{i}" for i in range(1, 9)]
    out = _play_all(teams, True, "away")
    gf1, gf2 = out["grand_final"]
    assert gf1["winner"] == gf1["away"] and gf2["required"] is True
    assert {gf2["home"], gf2["away"]} == {gf1["home"], gf1["away"]}
    out = _play_all(teams, True, "home")
    assert out["grand_final"][1]["required"] is False
    out = _play_all(teams, False, "home")
    assert len(out["grand_final"]) == 1
    out = _play_all([f"t{i}" for i in range(1, 7)], True, "away")
    assert out["grand_final"][0]["winner"] is not None
