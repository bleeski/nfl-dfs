"""TB@DAL Showdown ceiling pass (docs/claude/working.md, Showdown judgment pass, tie-break).

Record of the by-hand pass on the engine's r2 file, never a general tool. Rules applied:
1. Every WR or TE Captain gets his own team's starting quarterback as a FLEX (one swap, or two when
   salary needs a second cheaper swap). Captains are never touched.
2. The ceiling pass may raise a person to 75% of rows (21 of 28) and pairwise overlap to 5; the
   Captain cap and R29 distinctness never move. A quarterback over 21 rows is taken out of the
   optional rows (Captain not his team's WR or TE) where removing him costs the least prior.
3. FLEX swaps that raise a row's prior by 1.0 point or more, best first, to a fixed point.
Scores are the run's own dumped prior points (pool_scores.json); no number is written here.
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

sc = json.load(open(scores_path))
excluded = set(sc["excluded_dk_ids"])
score = {i: float(v) for i, v in sc["by_dk_id"].items()}
allowed_flex = {
    person[i] for i, v in sal.items()
    if v["slot"] == "FLEX" and i in score and i not in excluded and v["status"] in ("", "Q")
}

STARTING_QB = {"DAL": "DAL|QB|Dak Prescott", "TB": "TB|QB|Jalon Daniels"}
CAP = 50000
N = 28
PERSON_MAX = 21  # 75% of 28
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


def ok(state, eid, new_ids, c):
    if row_salary(new_ids) > CAP:
        return False
    ps = people(new_ids)
    if len(set(ps)) != 6:
        return False
    if len({sal[i]["team"] for i in new_ids}) < 2:  # DraftKings: both teams in every lineup
        return False
    for other, ids in state.items():
        if other == eid:
            continue
        if ids == new_ids or (ids[0] == new_ids[0] and set(ids[1:]) == set(new_ids[1:])):
            return False
        if overlap(ids, new_ids) > OVERLAP_MAX:
            return False
    old = set(people(state[eid]))
    for p in set(ps) - old:
        if c[p] + 1 > PERSON_MAX:
            return False
    return True


def required_qb(ids):
    cpt = sal[ids[0]]
    if cpt["pos"] in ("WR", "TE"):
        return STARTING_QB[cpt["team"]]
    return None


def measures(state):
    c = counts(state)
    cc = captain_counts(state)
    pairs = [overlap(a, b) for a, b in itertools.combinations(state.values(), 2)]
    top3 = sum(v for _, v in c.most_common(3))
    return {
        "total_prior": round(sum(row_score(v) for v in state.values()), 2),
        "min_row_prior": round(min(row_score(v) for v in state.values()), 2),
        "max_person": c.most_common(1)[0],
        "people_over_half": sorted([(p, n) for p, n in c.items() if n > N / 2], key=lambda x: -x[1]),
        "top3_person_slots": top3,
        "distinct_people": len(c),
        "captains": cc.most_common(),
        "max_captain_share": round(cc.most_common(1)[0][1] / N, 4),
        "max_pairwise_overlap": max(pairs),
        "mean_pairwise_overlap": round(sum(pairs) / len(pairs), 4),
        "rows_wr_te_captain_without_own_qb": sum(
            1 for v in state.values() if required_qb(v) and required_qb(v) not in people(v)
        ),
        "distinct_lineups": len({(v[0], frozenset(v[1:])) for v in state.values()}),
    }


state = {k: list(v) for k, v in rows.items()}
before = measures(state)
log = []

# Step 1: own quarterback for every WR/TE Captain.
for eid in list(state):
    qb = required_qb(state[eid])
    if not qb or qb in people(state[eid]):
        continue
    qid = flex_id[qb]
    c = counts(state)
    best = None
    ids = state[eid]
    for j in range(1, 6):
        cand = ids[:j] + [qid] + ids[j + 1:]
        if ok(state, eid, cand, Counter({k: v for k, v in c.items() if k != qb})):
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
                if ok(state, eid, cand, Counter({k2: v for k2, v in c.items() if k2 != qb})):
                    s = row_score(cand)
                    if best is None or s > best[0]:
                        best = (s, cand, [(ids[j], qid), (ids[k], flex_id[p])])
    if best is None:
        log.append({"step": "own_qb", "entry_id": eid, "result": "NO_FEASIBLE_SWAP"})
        continue
    log.append({
        "step": "own_qb", "entry_id": eid,
        "swaps": [(person[a], person[b]) for a, b in best[2]],
        "row_prior_before": round(row_score(ids), 2), "row_prior_after": round(best[0], 2),
    })
    state[eid] = best[1]

# Step 1b: bring each quarterback back to the 75% ceiling from optional rows.
for team, qb in STARTING_QB.items():
    while counts(state)[qb] > PERSON_MAX:
        c = counts(state)
        best = None
        for eid, ids in state.items():
            if qb not in people(ids[1:]) or required_qb(ids) == qb:
                continue
            j = people(ids).index(qb)
            for p in allowed_flex:
                if p in people(ids):
                    continue
                cand = list(ids)
                cand[j] = flex_id[p]
                if ok(state, eid, cand, c):
                    loss = row_score(ids) - row_score(cand)
                    if best is None or loss < best[0]:
                        best = (loss, eid, cand, (ids[j], flex_id[p]))
        if best is None:
            log.append({"step": "qb_ceiling", "person": qb, "result": "NO_FEASIBLE_REMOVAL"})
            break
        loss, eid, cand, sw = best
        log.append({
            "step": "qb_ceiling", "entry_id": eid, "swaps": [(person[sw[0]], person[sw[1]])],
            "row_prior_before": round(row_score(state[eid]), 2), "row_prior_after": round(row_score(cand), 2),
        })
        state[eid] = cand

# Step 2: FLEX swaps raising a row's prior by MIN_GAIN or more, Captains and required QBs untouched.
while True:
    c = counts(state)
    best = None
    for eid, ids in state.items():
        req = required_qb(ids)
        for j in range(1, 6):
            if person[ids[j]] == req:
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
    log.append({
        "step": "flex_upgrade", "entry_id": eid, "swaps": [(person[sw[0]], person[sw[1]])],
        "gain": round(gain, 2),
    })
    state[eid] = cand

after = measures(state)

# Write: replace only the six roster cells of each changed row.
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
    "schema": "tb_dal_sd_ceiling_pass_record_v1",
    "status": "PRIOR_ONLY / DO_NOT_UPLOAD",
    "source_review": review,
    "scores": scores_path,
    "rules": {"person_max_rows": PERSON_MAX, "overlap_max": OVERLAP_MAX, "min_gain": MIN_GAIN, "salary_cap": CAP},
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
