"""TB@DAL Showdown: apply reviewed swaps to a filled review file and measure both goals.

Record of the adversarial-review iterations, never a general tool. Each swap line is
ENTRY_ID|SLOT|OUT_DK_ID|IN_DK_ID|reason, SLOT is CPT or FLEX. A swap is refused (and named) when
it breaks the salary cap, the two-team rule, R29 distinctness, the 75% person ceiling (21 of 28),
the Captain cap (5 of 28), the overlap ceiling (5), or names an excluded or unknown ID. The prior
scores are the run's own dump; nothing here writes a number.

usage: apply_swaps.py SALARIES REVIEW SCORES SWAPS OUT RECORD
"""
import csv
import itertools
import json
import sys
from collections import Counter

salaries, review, scores_path, swaps_path, out_path, record_path = sys.argv[1:7]
N, CAP, PERSON_MAX, CAPTAIN_MAX, OVERLAP_MAX = 28, 50000, 21, 5, 5

sal = {}
for r in csv.DictReader(open(salaries, encoding="utf-8-sig")):
    sal[r["ID"]] = {"name": r["Name"], "team": r["TeamAbbrev"], "pos": r["Position"],
                    "slot": r["Roster Position"], "salary": int(r["Salary"]), "status": r.get("Status", "").strip()}
person = {i: f'{v["team"]}|{v["pos"]}|{v["name"]}' for i, v in sal.items()}
sc = json.load(open(scores_path))
excluded = set(sc["excluded_dk_ids"])
score = {i: float(v) for i, v in sc["by_dk_id"].items()}
STARTING_QB = {"DAL": "DAL|QB|Dak Prescott", "TB": "TB|QB|Jalon Daniels"}

raw = open(review, "rb").read()
lines = raw.split(b"\r\n")
rows, row_line = {}, {}
for idx, line in enumerate(lines[1:], start=1):
    f = line.split(b",")
    if len(f) > 9 and f[0].strip() and f[4].strip():
        rows[f[0].decode()] = [x.decode() for x in f[4:10]]
        row_line[f[0].decode()] = idx
assert len(rows) == N


def ppl(ids):
    return [person[i] for i in ids]


def measures(state):
    c, cc = Counter(), Counter()
    for ids in state.values():
        c.update(set(ppl(ids)))
        cc[person[ids[0]]] += 1
    pairs = [len(set(ppl(a)) & set(ppl(b))) for a, b in itertools.combinations(state.values(), 2)]
    wr_te_no_qb = sum(1 for v in state.values() if sal[v[0]]["pos"] in ("WR", "TE")
                      and STARTING_QB[sal[v[0]]["team"]] not in ppl(v))
    return {
        "large_prizes": {
            "total_prior": round(sum(score[i] for v in state.values() for i in v), 2),
            "min_row_prior": round(min(sum(score[i] for i in v) for v in state.values()), 2),
            "wr_te_captain_rows_without_own_qb": wr_te_no_qb,
        },
        "washouts": {
            "max_person": max(c.values()),
            "top3_person_slots": sum(n for _, n in c.most_common(3)),
            "mean_pairwise_overlap": round(sum(pairs) / len(pairs), 4),
            "max_pairwise_overlap": max(pairs),
            "distinct_people": len(c),
            "max_captain": max(cc.values()),
        },
        "exposure": dict(c.most_common()),
        "captains": dict(cc.most_common()),
    }


def refuse(state, eid, new):
    if any(i not in sal or i in excluded or i not in score for i in new):
        return "UNKNOWN_OR_EXCLUDED_ID"
    if sal[new[0]]["slot"] != "CPT" or any(sal[i]["slot"] != "FLEX" for i in new[1:]):
        return "SLOT_MISMATCH"
    if sum(sal[i]["salary"] for i in new) > CAP:
        return "SALARY_CAP"
    if len(set(ppl(new))) != 6:
        return "DUPLICATE_PERSON_IN_ROW"
    if len({sal[i]["team"] for i in new}) < 2:
        return "SINGLE_TEAM_LINEUP"
    for other, ids in state.items():
        if other == eid:
            continue
        if ids[0] == new[0] and set(ids[1:]) == set(new[1:]):
            return f"DUPLICATES_{other}"
        if len(set(ppl(ids)) & set(ppl(new))) > OVERLAP_MAX:
            return f"OVERLAP_6_WITH_{other}"
    trial = dict(state)
    trial[eid] = new
    m = measures(trial)
    if m["washouts"]["max_person"] > PERSON_MAX:
        return "PERSON_OVER_21"
    if m["washouts"]["max_captain"] > CAPTAIN_MAX:
        return "CAPTAIN_OVER_5"
    return None


def pareto(b, a):
    better_or_equal = (
        a["large_prizes"]["total_prior"] >= b["large_prizes"]["total_prior"] - 1e-9
        and a["large_prizes"]["min_row_prior"] >= b["large_prizes"]["min_row_prior"] - 1e-9
        and a["large_prizes"]["wr_te_captain_rows_without_own_qb"] <= b["large_prizes"]["wr_te_captain_rows_without_own_qb"]
        and a["washouts"]["max_person"] <= b["washouts"]["max_person"]
        and a["washouts"]["top3_person_slots"] <= b["washouts"]["top3_person_slots"]
        and a["washouts"]["mean_pairwise_overlap"] <= b["washouts"]["mean_pairwise_overlap"] + 1e-9
        and a["washouts"]["distinct_people"] >= b["washouts"]["distinct_people"]
    )
    return better_or_equal


state = {k: list(v) for k, v in rows.items()}
start = measures(state)
log = []
# Consecutive lines naming the same Entry ID are one atomic change (a paired swap that only fits the
# cap together); the first version applied them one at a time and refused the first half.
groups = []
for line in open(swaps_path):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if groups and groups[-1][0].split("|")[0] == line.split("|")[0]:
        groups[-1].append(line)
    else:
        groups.append([line])
for group in groups:
    line = " + ".join(group)
    eid = group[0].split("|")[0]
    if eid not in state:
        log.append({"swap": line, "result": "UNKNOWN_ENTRY_ID"})
        continue
    ids = state[eid]
    new = list(ids)
    problem = None
    for part in group:
        _, slot, out_id, in_id, *why = part.split("|")
        if out_id not in new:
            problem = "OUT_ID_NOT_IN_ROW"
            break
        j = new.index(out_id)
        if (slot == "CPT") != (j == 0):
            problem = "SLOT_MISMATCH"
            break
        new[j] = in_id
    if problem:
        log.append({"swap": line, "result": problem, "row": ppl(ids)})
        continue
    why_not = refuse(state, eid, new)
    if why_not:
        log.append({"swap": line, "result": why_not})
        continue
    out_id, in_id = group[0].split("|")[2], group[0].split("|")[3]
    before = measures(state)
    state[eid] = new
    after = measures(state)
    log.append({
        "swap": line, "result": "APPLIED", "out": person[out_id], "in": person[in_id],
        "salary": sum(sal[i]["salary"] for i in new),
        "row_prior_delta": round(sum(score[i] for i in new) - sum(score[i] for i in ids), 2),
        "pareto_vs_previous": pareto(before, after),
        "large_prizes": after["large_prizes"], "washouts": after["washouts"],
    })

end = measures(state)
new_lines = list(lines)
for eid, ids in state.items():
    if ids != rows[eid]:
        f = lines[row_line[eid]].split(b",")
        n = len(f)
        f[4:10] = [x.encode() for x in ids]
        assert len(f) == n
        new_lines[row_line[eid]] = b",".join(f)
with open(out_path, "xb") as fh:
    fh.write(b"\r\n".join(new_lines))
record = {"schema": "tb_dal_sd_review_swaps_record_v1", "status": "PRIOR_ONLY / DO_NOT_UPLOAD",
          "source_review": review, "swaps_file": swaps_path, "before": start, "after": end,
          "pareto_overall": pareto(start, end), "log": log,
          "changed_entry_ids": sorted(e for e in state if state[e] != rows[e])}
with open(record_path, "x") as fh:
    json.dump(record, fh, indent=1)
print(json.dumps({"before": {k: start[k] for k in ("large_prizes", "washouts")},
                  "after": {k: end[k] for k in ("large_prizes", "washouts")},
                  "pareto_overall": record["pareto_overall"]}, indent=1))
for item in log:
    print({k: item[k] for k in item if k not in ("large_prizes", "washouts")})
print("exposure_after", end["exposure"])
print("captains_after", end["captains"])
