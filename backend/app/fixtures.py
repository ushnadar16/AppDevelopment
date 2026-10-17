"""FR-1.3 fixture generation: round robin, swiss, single and double elimination.

Pure computation, no third-party fixture libraries. networkx is used only as a
general-purpose graph matching primitive for the Swiss minimum-cost pairing.
"""
import math

import networkx as nx

from .util import ApiError, conflict, is_int, validation_error

LIMITS = {"round_robin": (2, 40), "swiss": (2, 64), "single_elim": (2, 128), "double_elim": (3, 128)}


def generate(body):
    if not isinstance(body, dict):
        raise validation_error("body")
    fmt = body.get("format")
    if fmt not in LIMITS:
        raise validation_error("format")
    teams = body.get("teams")
    lo, hi = LIMITS[fmt]
    if (not isinstance(teams, list) or not all(isinstance(t, str) and t for t in teams)
            or len(set(teams)) != len(teams) or not lo <= len(teams) <= hi):
        raise validation_error("teams")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise validation_error("params")
    if fmt == "round_robin":
        return round_robin(teams, params)
    if fmt == "swiss":
        return swiss(teams, params)
    if fmt == "single_elim":
        return single_elim(teams, params)
    return double_elim(teams, params)


# --------------------------------------------------------------------------- round robin

def circle_rounds(teams):
    """Circle method. Returns list of rounds; each round = list of (home, away) incl. None byes."""
    arr = list(teams) + ([None] if len(teams) % 2 else [])
    n = len(arr)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            # Only the fixed team's pairing alternates; this keeps |home - away| <= 1.
            if i == 0 and r % 2 == 1:
                a, b = b, a
            pairs.append((a, b))
        rounds.append(pairs)
        arr = [arr[0], arr[-1]] + arr[1:-1]
    return rounds


def round_robin(teams, params):
    legs = params.get("legs", 1)
    if legs not in (1, 2) or not is_int(legs):
        raise validation_error("params.legs")
    policy = params.get("withdrawal_policy", "forfeit_remaining")
    if policy not in ("void_all", "forfeit_remaining"):
        raise validation_error("params.withdrawal_policy")
    base = circle_rounds(teams)
    per_leg = len(base)
    round_count = per_leg * legs
    withdrawals = params.get("withdrawals", [])
    if not isinstance(withdrawals, list):
        raise validation_error("params.withdrawals")
    wd = {}
    for w in withdrawals:
        if not isinstance(w, dict) or w.get("team_id") not in teams:
            raise validation_error("params.withdrawals.team_id")
        ar = w.get("after_round")
        if not is_int(ar) or not 0 <= ar <= round_count:
            raise validation_error("params.withdrawals.after_round")
        tid = w["team_id"]
        wd[tid] = min(ar, wd.get(tid, ar))

    rounds = []
    summary = {"total": 0, "scheduled": 0, "forfeit": 0, "voided": 0}
    for leg in range(1, legs + 1):
        for ri, pairs in enumerate(base):
            gr = (leg - 1) * per_leg + ri + 1
            matches, byes = [], []
            idx = 0
            for a, b in pairs:
                if a is None or b is None:
                    byes.append(a if b is None else b)
                    continue
                home, away = (a, b) if leg == 1 else (b, a)
                idx += 1
                status, awarded = "scheduled", None
                if policy == "void_all":
                    if home in wd or away in wd:
                        status = "voided"
                else:
                    h_out = home in wd and gr > wd[home]
                    a_out = away in wd and gr > wd[away]
                    if h_out and a_out:
                        status = "voided"
                    elif h_out:
                        status, awarded = "forfeit", away
                    elif a_out:
                        status, awarded = "forfeit", home
                summary["total"] += 1
                summary[status] += 1
                matches.append({"match_id": f"RR-L{leg}-R{gr}-M{idx}", "leg": leg, "home": home,
                                "away": away, "status": status, "awarded_to": awarded})
            rounds.append({"round": gr, "matches": matches, "byes": byes})
    return {"format": "round_robin", "legs": legs, "team_count": len(teams), "round_count": round_count,
            "rounds": rounds, "summary": summary}


# --------------------------------------------------------------------------- swiss

def swiss(teams, params):
    n = len(teams)
    default_rounds = max(1, math.ceil(math.log2(n)))
    total = params.get("total_rounds", default_rounds)
    if not is_int(total) or not 1 <= total <= max(1, n - 1):
        raise validation_error("params.total_rounds")
    rnd = params.get("round", 1)
    if not is_int(rnd) or not 1 <= rnd <= total:
        raise validation_error("params.round")
    history = params.get("history", [])
    if not isinstance(history, list):
        raise validation_error("params.history")
    seen_rounds = []
    tset = set(teams)
    for h in history:
        if not isinstance(h, dict) or not is_int(h.get("round")):
            raise validation_error("params.history")
        seen_rounds.append(h["round"])
        bye = h.get("bye")
        if bye is not None and bye not in tset:
            raise validation_error("params.history.bye")
        ms = h.get("matches", [])
        if not isinstance(ms, list):
            raise validation_error("params.history.matches")
        for m in ms:
            if (not isinstance(m, dict) or m.get("home") not in tset or m.get("away") not in tset
                    or m.get("home") == m.get("away") or m.get("result") not in ("home", "away", "draw")):
                raise validation_error("params.history.matches")
    if sorted(seen_rounds) != list(range(1, rnd)):
        raise validation_error("params.history")

    seed = {t: i for i, t in enumerate(teams)}
    score = {t: 0.0 for t in teams}
    opponents = {t: [] for t in teams}
    had_bye = set()
    played = set()
    for h in sorted(history, key=lambda x: x["round"]):
        if h.get("bye") is not None:
            score[h["bye"]] += 1.0
            had_bye.add(h["bye"])
        for m in h.get("matches", []):
            a, b, res = m["home"], m["away"], m["result"]
            opponents[a].append(b)
            opponents[b].append(a)
            played.add(frozenset((a, b)))
            if res == "home":
                score[a] += 1.0
            elif res == "away":
                score[b] += 1.0
            else:
                score[a] += 0.5
                score[b] += 0.5
    buch = {t: float(sum(score[o] for o in opponents[t])) for t in teams}
    order = sorted(teams, key=lambda t: (-score[t], -buch[t], seed[t]))
    standings = [{"rank": i + 1, "team_id": t, "score": score[t], "buchholz": buch[t]}
                 for i, t in enumerate(order)]

    bye = None
    if rnd == 1:
        m = n // 2
        if n % 2:
            bye = teams[-1]
        pairs = [(teams[i], teams[i + m]) for i in range(m)]
    else:
        pairs = None
        if n % 2:
            cands = [t for t in teams if t not in had_bye] or list(teams)
            cands.sort(key=lambda t: (score[t], -seed[t]))
            for c in cands:
                rest = [t for t in teams if t != c]
                pairs = min_cost_pairing(rest, score, played)
                if pairs is not None:
                    bye = c
                    break
        else:
            pairs = min_cost_pairing(list(teams), score, played)
        if pairs is None:
            raise conflict("NO_VALID_PAIRING", f"No rematch-free pairing exists for round {rnd}.", round=rnd)
        rank = {t: i for i, t in enumerate(order)}
        pairs = [tuple(sorted(p, key=lambda t: rank[t])) for p in pairs]
        pairs.sort(key=lambda p: rank[p[0]])
    pairings = [{"match_id": f"SW-R{rnd}-M{i + 1}", "home": a, "away": b} for i, (a, b) in enumerate(pairs)]
    return {"format": "swiss", "round": rnd, "total_rounds": total, "pairings": pairings, "bye": bye,
            "standings": standings}


def min_cost_pairing(teams, score, played):
    """Exact minimum sum |score diff| perfect matching avoiding rematches, or None."""
    if not teams:
        return []
    g = nx.Graph()
    g.add_nodes_from(teams)
    big = 10_000
    for i, a in enumerate(teams):
        for b in teams[i + 1:]:
            if frozenset((a, b)) in played:
                continue
            g.add_edge(a, b, weight=big - int(round(abs(score[a] - score[b]) * 2)))
    mate = nx.max_weight_matching(g, maxcardinality=True)
    if len(mate) * 2 != len(teams):
        return None
    return [tuple(p) for p in mate]


# --------------------------------------------------------------------------- elimination

DEAD = object()  # a slot that will never be filled (bye)


def seed_order(size):
    order = [1, 2]
    while len(order) < size:
        k = len(order)
        order = [x for s in order for x in (s, 2 * k + 1 - s)]
    return order[:size] if size >= 2 else [1]


def _match(mid, bracket, rnd, idx):
    return {"match_id": mid, "bracket": bracket, "round": rnd, "index": idx, "home": None, "away": None,
            "home_seed": None, "away_seed": None, "bye": False, "winner": None, "loser": None,
            "winner_to": None, "loser_to": None}


def _parse_results(params):
    results = params.get("results", [])
    if not isinstance(results, list):
        raise validation_error("params.results")
    out = {}
    for r in results:
        if not isinstance(r, dict) or not isinstance(r.get("match_id"), str) or not isinstance(r.get("winner"), str):
            raise validation_error("params.results")
        out[r["match_id"]] = r["winner"]
    return out


def _resolve(matches, order, results, seeds):
    """Propagate byes and results through the bracket graph until fixpoint."""
    for mid in results:
        if mid not in matches:
            raise validation_error("params.results.match_id", f"Unknown match_id {mid}.")
    slots = {mid: {"home": m["_home"], "away": m["_away"]} for mid, m in matches.items()}
    done = set()
    changed = True
    while changed:
        changed = False
        for mid in order:
            if mid in done:
                continue
            m, s = matches[mid], slots[mid]
            h, a = s["home"], s["away"]
            if h is None or a is None:
                continue
            if h is DEAD or a is DEAD:
                winner = a if h is DEAD else h
                loser = DEAD
                if h is not DEAD or a is not DEAD:
                    m["bye"] = True
                if mid in results and results[mid] != winner:
                    raise validation_error("params.results.winner", f"{results[mid]} is not in {mid}.")
            elif mid in results:
                winner = results[mid]
                if winner not in (h, a):
                    raise validation_error("params.results.winner", f"{winner} is not in {mid}.")
                loser = a if winner == h else h
            else:
                continue
            done.add(mid)
            changed = True
            m["winner"] = None if winner is DEAD else winner
            m["loser"] = None if loser is DEAD else loser
            if m["winner_to"]:
                slots[m["winner_to"]["match_id"]][m["winner_to"]["slot"]] = winner
            if m["loser_to"]:
                slots[m["loser_to"]["match_id"]][m["loser_to"]["slot"]] = loser
            if m.get("_mirror"):
                for k in ("home", "away"):
                    slots[m["_mirror"]][k] = s[k]
    for mid in results:
        if mid not in done:
            raise validation_error("params.results.winner", f"Participants of {mid} are not known yet.")
    for mid, m in matches.items():
        for k in ("home", "away"):
            v = slots[mid][k]
            m[k] = None if v is DEAD else v
            m[k + "_seed"] = seeds.get(m[k]) if m[k] is not None else None
        m.pop("_home", None)
        m.pop("_away", None)
        m.pop("_mirror", None)


def _first_round(teams, prefix, bracket):
    n = len(teams)
    size = 1
    while size < n:
        size *= 2
    size = max(size, 2)
    order = seed_order(size)
    first = []
    for i in range(size // 2):
        hs, as_ = order[2 * i], order[2 * i + 1]
        m = _match(f"{prefix}1M{i + 1}", bracket, 1, i + 1)
        m["_home"] = teams[hs - 1] if hs <= n else DEAD
        m["_away"] = teams[as_ - 1] if as_ <= n else DEAD
        first.append(m)
    return size, first


def _blank(m):
    m["_home"] = None
    m["_away"] = None
    return m


def single_elim(teams, params):
    third = params.get("third_place_match", False)
    if not isinstance(third, bool):
        raise validation_error("params.third_place_match")
    results = _parse_results(params)
    seeds = {t: i + 1 for i, t in enumerate(teams)}
    size, first = _first_round(teams, "R", "main")
    k = int(math.log2(size))
    rounds = [first]
    for r in range(2, k + 1):
        rounds.append([_blank(_match(f"R{r}M{i + 1}", "main", r, i + 1)) for i in range(size // 2 ** r)])
    for r in range(k - 1):
        for i, m in enumerate(rounds[r]):
            m["winner_to"] = {"match_id": f"R{r + 2}M{i // 2 + 1}", "slot": "home" if i % 2 == 0 else "away"}
    all_matches = [m for rr in rounds for m in rr]
    if third and k >= 2:
        tp = _blank(_match("TP", "third_place", k, 1))
        for i, m in enumerate(rounds[k - 2]):
            m["loser_to"] = {"match_id": "TP", "slot": "home" if i == 0 else "away"}
        rounds[k - 1].append(tp)
        all_matches.append(tp)
    by_id = {m["match_id"]: m for m in all_matches}
    _resolve(by_id, [m["match_id"] for m in all_matches], results, seeds)
    return {"format": "single_elim", "bracket_size": size,
            "rounds": [{"round": i + 1, "matches": rr} for i, rr in enumerate(rounds)]}


def double_elim(teams, params):
    reset = params.get("bracket_reset", False)
    if not isinstance(reset, bool):
        raise validation_error("params.bracket_reset")
    results = _parse_results(params)
    seeds = {t: i + 1 for i, t in enumerate(teams)}
    size, first = _first_round(teams, "WR", "winners")
    k = int(math.log2(size))
    wr = [first]
    for r in range(2, k + 1):
        wr.append([_blank(_match(f"WR{r}M{i + 1}", "winners", r, i + 1)) for i in range(size // 2 ** r)])
    lr = []
    for r in range(1, 2 * (k - 1) + 1):
        j = (r + 1) // 2
        lr.append([_blank(_match(f"LR{r}M{i + 1}", "losers", r, i + 1)) for i in range(size // 2 ** (j + 1))])
    gf1 = _blank(_match("GF1", "grand_final", 1, 1))
    gf1.update({"conditional": False, "required": True})
    gfs = [gf1]

    def slot(i):
        return "home" if i % 2 == 0 else "away"

    # winners bracket
    for r in range(k):
        for i, m in enumerate(wr[r]):
            if r < k - 1:
                m["winner_to"] = {"match_id": f"WR{r + 2}M{i // 2 + 1}", "slot": slot(i)}
            else:
                m["winner_to"] = {"match_id": "GF1", "slot": "home"}
            if r == 0:
                m["loser_to"] = {"match_id": f"LR1M{i // 2 + 1}", "slot": slot(i)}
            else:
                m["loser_to"] = {"match_id": f"LR{2 * (r + 1) - 2}M{i + 1}", "slot": "away"}
    # losers bracket
    nlr = len(lr)
    for r in range(1, nlr + 1):
        for i, m in enumerate(lr[r - 1]):
            if r == nlr:
                m["winner_to"] = {"match_id": "GF1", "slot": "away"}
            elif r % 2 == 1:
                m["winner_to"] = {"match_id": f"LR{r + 1}M{i + 1}", "slot": "home"}
            else:
                m["winner_to"] = {"match_id": f"LR{r + 1}M{i // 2 + 1}", "slot": slot(i)}
    if reset:
        gf2 = _blank(_match("GF2", "grand_final", 2, 1))
        gf2.update({"conditional": True, "required": None})
        gf1["_mirror"] = "GF2"
        gfs.append(gf2)

    all_matches = [m for rr in wr for m in rr] + [m for rr in lr for m in rr] + gfs
    by_id = {m["match_id"]: m for m in all_matches}
    gf2_result = results.pop("GF2", None) if reset else None
    _resolve(by_id, [m["match_id"] for m in all_matches if m["match_id"] != "GF2"], results, seeds)
    if reset:
        gf2 = by_id["GF2"]
        gf2["home"], gf2["away"] = gf1["home"], gf1["away"]
        gf2["home_seed"], gf2["away_seed"] = gf1["home_seed"], gf1["away_seed"]
        if gf1["winner"] is not None:
            gf2["required"] = gf1["winner"] == gf1["away"]
        if gf2_result is not None:
            if not gf2["required"] or gf2_result not in (gf2["home"], gf2["away"]):
                raise validation_error("params.results.winner", "GF2 is not being played.")
            gf2["winner"] = gf2_result
            gf2["loser"] = gf2["away"] if gf2_result == gf2["home"] else gf2["home"]
        gf2.pop("_home", None)
        gf2.pop("_away", None)
        # graph edges from GF1 into GF2 (same two teams play again)
        gf1["winner_to"] = {"match_id": "GF2", "slot": "home"}
        gf1["loser_to"] = {"match_id": "GF2", "slot": "away"}
    elif "GF2" in results:
        raise validation_error("params.results.match_id", "Unknown match_id GF2.")
    return {"format": "double_elim", "bracket_size": size, "bracket_reset": reset,
            "winners": [{"round": i + 1, "matches": rr} for i, rr in enumerate(wr)],
            "losers": [{"round": i + 1, "matches": rr} for i, rr in enumerate(lr)],
            "grand_final": gfs}
