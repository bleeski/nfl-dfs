"""SEA@DEN: move the seven chosen lineups into the Micro Booster's Entry IDs (Ben: that contest pays the top 5, so build
for one of its seven entries finishing top 5). A record of the by-hand step, never a tool.

Choice rule: highest prior first, at most two rows per Captain, and a second row for a Captain must share no more than
three people with the first. Each chosen lineup outside the booster swaps with a booster lineup not chosen; the swap
partner is the one whose Captain is least repeated in the receiving contest. Lineups move whole between Entry IDs, so
the file holds the same 28 lineups. Scores are the run's own priors; no number is written here.
"""
import csv
import json
import sys
from collections import Counter

salaries, entries, scores_path, out_path, record_path = sys.argv[1:6]
BOOSTER = "196781421"
K = 7

sal = {r["ID"]: r for r in csv.DictReader(open(salaries, encoding="utf-8-sig"))}
score = {i: float(v) for i, v in json.load(open(scores_path))["by_dk_id"].items()}
raw = open(entries, "rb").read()
lines = raw.split(b"\r\n")
rows, contest, line_of = {}, {}, {}
for idx, line in enumerate(lines[1:], start=1):
    f = line.split(b",")
    if len(f) > 9 and f[0].strip() and f[4].strip():
        e = f[0].decode()
        rows[e] = [x.decode() for x in f[4:10]]
        contest[e] = f[2].decode()
        line_of[e] = idx


def who(i):
    return sal[i]["TeamAbbrev"] + "|" + sal[i]["Name"]


def prior(ids):
    return sum(score[i] for i in ids)


ranked = sorted(rows, key=lambda e: -prior(rows[e]))
chosen = []
for e in ranked:
    cap = who(rows[e][0])
    same = [c for c in chosen if who(rows[c][0]) == cap]
    if len(same) >= 2:
        continue
    if same and len({who(i) for i in rows[e]} & {who(i) for i in rows[same[0]]}) > 3:
        continue
    chosen.append(e)
    if len(chosen) == K:
        break
chosen_lineups = [tuple(rows[e]) for e in chosen]

state = {e: list(v) for e, v in rows.items()}
booster_ids = [e for e in state if contest[e] == BOOSTER]
swaps = []
for lu in chosen_lineups:
    holder = next(e for e in state if tuple(state[e]) == lu)
    if contest[holder] == BOOSTER:
        continue
    free = [b for b in booster_ids if tuple(state[b]) not in chosen_lineups]
    caps_there = Counter(who(state[e][0]) for e in state if contest[e] == contest[holder] and e != holder)
    b = min(free, key=lambda x: (caps_there[who(state[x][0])], -prior(state[x])))
    state[holder], state[b] = state[b], state[holder]
    swaps.append({"booster_entry": b, "other_entry": holder, "other_contest": contest[holder]})

assert sorted(map(tuple, state.values())) == sorted(map(tuple, rows.values()))
assert all(tuple(state[b]) in chosen_lineups for b in booster_ids)

new_lines = list(lines)
for e, ids in state.items():
    if ids == rows[e]:
        continue
    f = lines[line_of[e]].split(b",")
    n = len(f)
    f[4:10] = [x.encode() for x in ids]
    assert len(f) == n
    new_lines[line_of[e]] = b",".join(f)
with open(out_path, "xb") as fh:
    fh.write(b"\r\n".join(new_lines))

per_contest = {}
for e, ids in state.items():
    per_contest.setdefault(contest[e], []).append(who(ids[0]))
record = {
    "schema": "sea_den_sd_booster_assign_record_v1",
    "status": "PRIOR_ONLY / DO_NOT_UPLOAD",
    "source": entries,
    "booster_contest": BOOSTER,
    "booster_rows": [{"entry_id": b, "captain": who(state[b][0]), "row_prior": round(prior(state[b]), 2)} for b in booster_ids],
    "swaps": swaps,
    "captains_by_contest": {c: Counter(v).most_common() for c, v in per_contest.items()},
}
with open(record_path, "x") as fh:
    json.dump(record, fh, indent=1)
print(json.dumps(record, indent=1))
