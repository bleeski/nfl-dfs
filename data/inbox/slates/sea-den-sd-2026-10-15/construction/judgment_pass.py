"""SEA@DEN Showdown judgment pass (TNF, 2026-10-15). A record of the by-hand pass on the engine's r2 file, never a tool.

Rules, in order (docs/claude/working.md, Showdown judgment pass):
0. Low-total script (market total 40.5, Thursday short week): two of the engine's five RJ Harvey Captain rows become
   DST Captain rows (one per defense). Each is rebuilt by exhaustive search: own quarterback in (own kicker only when
   the 60% cap leaves room), no opposing quarterback, both teams present.
1. Every WR or TE Captain gets his own team's starting quarterback.
2. FLEX swaps raising a row's prior by 1.0 or more, best first, to a fixed point. Captains untouched; a DST row never
   takes the opposing quarterback.
Caps: starting quarterbacks to 21 of 28 (75%), everyone else 16 of 28 (60%), Captain 20%, pairwise overlap 5, R29.
A DST Captain row holds its own offense (at most one opposing RB or kicker), and its own-team people may use the 75%
headroom, so the low-total script is built whole rather than from whoever is left under the 60% cap.
Scores are the run's own dumped priors (pool_scores.json); no number is written here.
"""
import csv
import itertools
import json
import sys
from collections import Counter

salaries, review, scores_path, out_path, record_path = sys.argv[1:6]

sal = {}
for r in csv.DictReader(open(salaries, encoding="utf-8-sig")):
    sal[r["ID"]] = {
        "name": r["Name"], "team": r["TeamAbbrev"], "pos": r["Position"],
        "slot": r["Roster Position"], "salary": int(r["Salary"]), "status": r.get("Status", "").strip(),
    }
person = {i: f'{v["team"]}|{v["pos"]}|{v["name"]}' for i, v in sal.items()}
flex_id = {person[i]: i for i, v in sal.items() if v["slot"] == "FLEX"}
cpt_id = {person[i]: i for i, v in sal.items() if v["slot"] == "CPT"}

sc = json.load(open(scores_path))
excluded = set(sc["excluded_dk_ids"])
score = {i: float(v) for i, v in sc["by_dk_id"].items()}
BACKUP_QB = {"SEA|QB|Drew Lock", "DEN|QB|Jarrett Stidham"}
allowed_flex = {
    person[i] for i, v in sal.items()
    if v["slot"] == "FLEX" and i in score and i not in excluded and v["status"] in ("", "Q")
    and person[i] not in BACKUP_QB
}

STARTING_QB = {"SEA": "SEA|QB|Sam Darnold", "DEN": "DEN|QB|Bo Nix"}
KICKER = {"SEA": "SEA|K|Jason Myers", "DEN": "DEN|K|Wil Lutz"}
OTHER = {"SEA": "DEN", "DEN": "SEA"}
DST_CAPTAIN_ROWS = {"5296951179": "DEN|DST|Broncos", "5296941776": "SEA|DST|Seahawks"}
CAP = 50000
N = 28
PERSON_MAX = 21
NON_QB_MAX = 16
CAPTAIN_MAX = 5  # 20% of 28, floored
OVERLAP_MAX = 5
MIN_GAIN = 1.0

raw = open(review, "rb").read()
lines = raw.split(b"\r\n")
rows = {}
row_line = {}
for idx, line in enumerate(lines[1:], start=1):
    f = line.split(b",")
    if len(f) > 9 and f[0].strip() and f[4].strip():
        eid = f[0].decode()
        rows[eid] = [x.decode() for x in f[4:10]]
        row_line[eid] = idx
assert len(rows) == N, len(rows)


def people(ids):
    return [person[i] for i in ids]


def row_score(ids):
    return sum(score[i] for i in ids)


def row_salary(ids):
    return sum(sal[i]["salary"] for i in ids)


def counts(state):
    c = Counter()
    for ids in state.values():
        c.update(set(people(ids)))
    return c


def captain_counts(state):
    return Counter(person[ids[0]] for ids in state.values())


def overlap(a, b):
    return len(set(people(a)) & set(people(b)))


def dst_conflict(ids):
    """A DST beside the opposing starting quarterback."""
    ps = people(ids)
    for p in ps:
        team, pos, _ = p.split("|")
        if pos == "DST" and STARTING_QB[OTHER[team]] in ps:
            return True
    return False


def dst_shape_ok(ids):
    """A DST Captain row: own offense, at most one opposing player, and never an opposing QB, WR or TE."""
    cpt = person[ids[0]].split("|")
    if cpt[1] != "DST":
        return True
    opp = [person[i].split("|") for i in ids[1:] if sal[i]["team"] != cpt[0]]
    return len(opp) <= 1 and all(o[1] in ("RB", "K") for o in opp)


def ok(state, eid, new_ids, c):
    if row_salary(new_ids) > CAP:
        return False
    if not dst_shape_ok(new_ids):
        return False
    ps = people(new_ids)
    if len(set(ps)) != 6:
        return False
    if len({sal[i]["team"] for i in new_ids}) < 2:
        return False
    if dst_conflict(new_ids):
        return False
    for other, ids in state.items():
        if other == eid:
            continue
        if ids[0] == new_ids[0] and set(ids[1:]) == set(new_ids[1:]):
            return False
        if overlap(ids, new_ids) > OVERLAP_MAX:
            return False
    old = set(people(state[eid]))
    dst_team = person[new_ids[0]].split("|")[0] if "|DST|" in person[new_ids[0]] else None
    for p in set(ps) - old:
        wide = p in STARTING_QB.values() or (dst_team and p.startswith(dst_team + "|"))
        if c[p] + 1 > (PERSON_MAX if wide else NON_QB_MAX):
            return False
    return True


def required(ids):
    cpt = sal[ids[0]]
    if cpt["pos"] in ("WR", "TE", "DST"):
        return {STARTING_QB[cpt["team"]]}
    return set()


def measures(state):
    c = counts(state)
    cc = captain_counts(state)
    pairs = [overlap(a, b) for a, b in itertools.combinations(state.values(), 2)]
    return {
        "total_prior": round(sum(row_score(v) for v in state.values()), 2),
        "min_row_prior": round(min(row_score(v) for v in state.values()), 2),
        "max_person": c.most_common(1)[0],
        "people_over_half": sorted([(p, n) for p, n in c.items() if n > N / 2], key=lambda x: -x[1]),
        "top3_person_slots": sum(v for _, v in c.most_common(3)),
        "distinct_people": len(c),
        "captains": cc.most_common(),
        "max_captain_share": round(cc.most_common(1)[0][1] / N, 4),
        "max_pairwise_overlap": max(pairs),
        "mean_pairwise_overlap": round(sum(pairs) / len(pairs), 4),
        "rows_without_required_people": sum(1 for v in state.values() if not required(v) <= set(people(v))),
        "rows_dst_with_opposing_qb": sum(1 for v in state.values() if dst_conflict(v)),
        "rows_without_a_quarterback": sum(1 for v in state.values() if not any("|QB|" in p for p in people(v))),
        "distinct_lineups": len({(v[0], frozenset(v[1:])) for v in state.values()}),
    }


state = {k: list(v) for k, v in rows.items()}
before = measures(state)
log = []

# Step 0: DST Captain rows, rebuilt whole.
for eid, dst in DST_CAPTAIN_ROWS.items():
    team = dst.split("|")[0]
    cid = cpt_id[dst]
    must = [STARTING_QB[team]]
    pool = sorted(p for p in allowed_flex if p not in must and p != STARTING_QB[OTHER[team]] and "|DST|" not in p)
    c = counts(state)
    for p in set(people(state[eid])):
        c[p] -= 1
    best = None
    for combo in itertools.combinations(pool, 4):
        ids = [cid] + [flex_id[p] for p in must] + [flex_id[p] for p in combo]
        probe = dict(state)
        probe[eid] = [cid]  # an empty row, so ok() counts every person as new
        if ok(probe, eid, ids, c):
            s = row_score(ids)
            if best is None or s > best[0]:
                best = (s, ids)
    assert best is not None, eid
    log.append({
        "step": "dst_captain", "entry_id": eid, "captain": dst,
        "from": people(state[eid]), "to": people(best[1]),
        "row_prior_before": round(row_score(state[eid]), 2), "row_prior_after": round(best[0], 2),
    })
    state[eid] = best[1]

# Step 1: own quarterback for every WR/TE Captain.
for eid in list(state):
    ids = state[eid]
    missing = [p for p in required(ids) if p not in people(ids)]
    if not missing:
        continue
    qb = missing[0]
    qid = flex_id[qb]
    c = counts(state)
    best = None
    for j in range(1, 6):
        cand = ids[:j] + [qid] + ids[j + 1:]
        if ok(state, eid, cand, c):
            s = row_score(cand)
            if best is None or s > best[0]:
                best = (s, cand, [(ids[j], qid)])
    if best is None:
        for j, k in itertools.permutations(range(1, 6), 2):
            for p in allowed_flex:
                if p in people(ids) or p == qb:
                    continue
                cand = list(ids)
                cand[j] = qid
                cand[k] = flex_id[p]
                if ok(state, eid, cand, c):
                    s = row_score(cand)
                    if best is None or s > best[0]:
                        best = (s, cand, [(ids[j], qid), (ids[k], flex_id[p])])
    if best is None:
        log.append({"step": "own_qb", "entry_id": eid, "result": "NO_FEASIBLE_SWAP"})
        continue
    log.append({
        "step": "own_qb", "entry_id": eid, "swaps": [(person[a], person[b]) for a, b in best[2]],
        "row_prior_before": round(row_score(ids), 2), "row_prior_after": round(best[0], 2),
    })
    state[eid] = best[1]

# Step 2: FLEX upgrades.
while True:
    c = counts(state)
    best = None
    for eid, ids in state.items():
        req = required(ids)
        for j in range(1, 6):
            if person[ids[j]] in req:
                continue
            for p in allowed_flex:
                if p in people(ids):
                    continue
                cand = list(ids)
                cand[j] = flex_id[p]
                gain = row_score(cand) - row_score(ids)
                if gain < MIN_GAIN:
                    continue
                if ok(state, eid, cand, c) and (best is None or gain > best[0]):
                    best = (gain, eid, cand, (ids[j], flex_id[p]))
    if best is None:
        break
    gain, eid, cand, sw = best
    log.append({"step": "flex_upgrade", "entry_id": eid, "swaps": [(person[sw[0]], person[sw[1]])], "gain": round(gain, 2)})
    state[eid] = cand

after = measures(state)
assert after["distinct_lineups"] == N
assert max(n for _, n in captain_counts(state).items()) <= CAPTAIN_MAX

new_lines = list(lines)
for eid, ids in state.items():
    if ids == rows[eid]:
        continue
    f = lines[row_line[eid]].split(b",")
    n = len(f)
    f[4:10] = [x.encode() for x in ids]
    assert len(f) == n
    new_lines[row_line[eid]] = b",".join(f)
with open(out_path, "xb") as fh:
    fh.write(b"\r\n".join(new_lines))

record = {
    "schema": "sea_den_sd_judgment_pass_record_v1",
    "status": "PRIOR_ONLY / DO_NOT_UPLOAD",
    "source_review": review,
    "scores": scores_path,
    "rules": {"qb_max_rows": PERSON_MAX, "non_qb_max_rows": NON_QB_MAX, "captain_max_rows": CAPTAIN_MAX,
              "overlap_max": OVERLAP_MAX, "min_gain": MIN_GAIN, "salary_cap": CAP, "dst_captain_rows": DST_CAPTAIN_ROWS},
    "before": before,
    "after": after,
    "log": log,
    "changed_entry_ids": sorted(e for e in state if state[e] != rows[e]),
}
with open(record_path, "x") as fh:
    json.dump(record, fh, indent=1)
print(json.dumps({"before": before, "after": after, "changes": len(log)}, indent=1))
for item in log:
    print(item)
