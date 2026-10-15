"""SEA@DEN: Jaylen Waddle for Courtland Sutton in five named rows. A record of the by-hand step, never a tool.

Why: the judgment pass's FLEX upgrades left Waddle in 0 of 28 rows on priors built from his old role, while tonight's
previews name him Denver's lead receiver (RotoGrinders: 76% route participation, 18% target share, 34% air-yards share;
Sutton 14%). Research informs the choice, never a number: each swap lowers the row's prior and that is reported.
Each named row already holds Bo Nix, Sutton and the salary room for +$1,000. Captains untouched.
"""
import csv
import json
import sys

salaries, entries, scores_path, out_path, record_path = sys.argv[1:6]
SUTTON, WADDLE = "44484635", "44484632"
ROWS = ["5296939573", "5296939570", "5296938659", "5296930241", "5296937591"]

sal = {r["ID"]: r for r in csv.DictReader(open(salaries, encoding="utf-8-sig"))}
score = {i: float(v) for i, v in json.load(open(scores_path))["by_dk_id"].items()}
lines = open(entries, "rb").read().split(b"\r\n")
log = []
for idx, line in enumerate(lines):
    f = line.split(b",")
    if not f[0] or f[0].decode() not in ROWS:
        continue
    ids = [x.decode() for x in f[4:10]]
    assert SUTTON in ids[1:] and WADDLE not in ids, f[0]
    new = [WADDLE if i == SUTTON else i for i in ids]
    salary = sum(int(sal[i]["Salary"]) for i in new)
    assert salary <= 50000, (f[0], salary)
    n = len(f)
    f[4:10] = [x.encode() for x in new]
    assert len(f) == n
    lines[idx] = b",".join(f)
    log.append({"entry_id": f[0].decode(), "salary_after": salary,
                "row_prior_before": round(sum(score[i] for i in ids), 2),
                "row_prior_after": round(sum(score[i] for i in new), 2)})
assert len(log) == len(ROWS)
with open(out_path, "xb") as fh:
    fh.write(b"\r\n".join(lines))
with open(record_path, "x") as fh:
    json.dump({"schema": "sea_den_sd_waddle_swap_record_v1", "status": "PRIOR_ONLY / DO_NOT_UPLOAD",
               "source": entries, "swaps": log}, fh, indent=1)
print(json.dumps(log, indent=1))
