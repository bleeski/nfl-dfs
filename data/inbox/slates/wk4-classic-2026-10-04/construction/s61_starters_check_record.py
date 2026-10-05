"""Session 61 record: the starters check and the Classic backup default on Week 4's committed inputs (2026-10-05).

A record, not a tool. Run from the repository root:

    .venv/Scripts/python.exe data/inbox/slates/wk4-classic-2026-10-04/construction/s61_starters_check_record.py

It is NOT a replay of the engine on Week 4's priors. Those frozen priors are not committed, and a replay is refused by
design: `priors` raises `FETCH_CLOCK_AHEAD_OF_AS_OF` for a fetch after the pinned clock, and the lock has passed. What is
committed is the salary file, the entries, the QB depth package and the recorded score dump (`scores_qbclean.json`, made
after the engine and a by-hand quarterback clean-up). This reads those and runs the Session 61 starters check and the
backup-quarterback default against them, schema-level only: it prints counts and names, never a row of the salary file.

Result on 2026-10-05: 23 starting quarterbacks named, all scored (CHI: Tyson Bagent, promoted over DK-OUT Caleb Williams;
TB: Jalon Daniels, promoted over DK-OUT Baker Mayfield); LAR is not in the depth package (the chart listed no
quarterback for it), so it is named `unevaluated`; the default would exclude 53 backups, Nick Mullens among them; none
is rostered in the delivered v6 file.
"""

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from nfl_dfs import classic_judgment as cj  # noqa: E402
from nfl_dfs.dk import parse_salaries  # noqa: E402
from nfl_dfs.showdown_theses import backup_quarterbacks  # noqa: E402

UNAVAILABLE = {"OUT", "IR", "D"}
root = Path("data/inbox/slates/wk4-classic-2026-10-04")
slate = parse_salaries(root / "DKSalaries.csv")
depth = json.loads((root / "qb_depth" / "qb_depth_roles.json").read_text(encoding="utf-8"))
scores = json.loads((root / "construction" / "scores_qbclean.json").read_text(encoding="utf-8"))
by_dk = scores.get("by_dk_id") or {}
print("salary SHA-256 matches the depth package:", slate.salary_hash == depth["salary_sha256"])
print("recorded scores:", len(by_dk))

status = {p.underlying_id: p.status_raw for p in slate.players}
effective, promoted = {}, []
for declaration in depth["declarations"]:
    order = [declaration["starter"], *declaration["backups"]]
    chosen = next((q for q in order if status.get(q["underlying_id"], "") not in UNAVAILABLE), None)
    effective[declaration["team"]] = chosen["underlying_id"] if chosen else None
    if chosen and chosen["underlying_id"] != declaration["starter"]["underlying_id"]:
        promoted.append({"team": declaration["team"], "published_starter": declaration["starter"]["underlying_id"],
                         "effective_starter": chosen["underlying_id"],
                         "promoted_over": [declaration["starter"]["underlying_id"]]})
report = {"schema_version": depth["schema_version"], "starters_by_team": effective,
          "effective_starter_promotions": promoted}

people = {}
for player in slate.players:
    flagged = status.get(player.underlying_id, "") in UNAVAILABLE
    people[player.underlying_id] = {
        "person": player.underlying_id, "name": player.name, "team": player.team, "position": player.position,
        "dk_status": status.get(player.underlying_id, ""), "salary": player.salary,
        "reason": ("DK_STATUS_UNAVAILABLE:" + status[player.underlying_id]) if flagged else "SELECTABLE",
        "lock_at": player.lock_at.isoformat()}
prior = {p.underlying_id: float(by_dk[p.dk_id]) for p in slate.players if p.dk_id in by_dk}
check = cj.starters_check(slate, qb_depth_report=report, pool_coverage={"people": list(people.values())},
                          prior_points=prior)
print("starters named:", len(check["starters"]), "| unevaluated:", check["unevaluated_teams"])
print("missing from the scored pool:", [(r["team"], r["name"], r["reason"]) for r in check["missing_from_scored_pool"]])
print("promoted:", [(r["team"], r["name"]) for r in check["starters"] if r["promoted_over"]])

backups, unevaluated = backup_quarterbacks(slate, None, report)
print("backup quarterbacks the Classic default excludes:", len(backups), "| unevaluated:", list(unevaluated))
print("Nick Mullens excluded:", any("Mullens" in person for person in backups))

rows = list(csv.reader(io.StringIO((root / "DK_REVIEW_ENTRY_wk4_classic_FINAL_v6.csv").read_text(encoding="utf-8-sig"))))
fee = rows[0].index("Entry Fee")
ids = {r[i].strip() for r in rows[1:] if r and r[0].strip().isdigit() for i in range(fee + 1, fee + 10)}
by_id = {p.dk_id: p.underlying_id for p in slate.players}
print("backup quarterbacks rostered in the delivered v6 file:", sorted(set(backups) & {by_id[i] for i in ids if i in by_id}))
