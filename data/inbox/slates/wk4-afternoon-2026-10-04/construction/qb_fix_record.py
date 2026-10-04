"""Week 4 afternoon judgment pass on the C1 export: one backup QB out, three
DST-versus-opponent conflicts removed. Byte-level edit of one roster cell in the C1 export; writes a new file, never overwrites."""
import csv, hashlib, json, sys
SRC = "outputs/20261004T194724Z-wk4-afternoon-r2/review/DK_REVIEW_ENTRY_C1_20261004T194724Z-wk4-afternoon-r2.csv"
DST = "outputs/20261004T194724Z-wk4-afternoon-r2/review/DK_REVIEW_ENTRY_wk4_afternoon_FINAL.csv"
PORT = "data/inbox/slates/wk4-afternoon-2026-10-04/construction/portfolio_final.json"
SAL = "data/inbox/slates/wk4-afternoon-2026-10-04/DKSalaries.csv"
SWAPS = [
    ("5282913944", "44343981", "44343973"),  # Justin Fields (KC backup QB) -> Kirk Cousins (LV starter)
    ("5282913944", "44344348", "44344347"),  # Seahawks DST (faces LAC skill in row) -> Vikings DST
    ("5282906336", "44344348", "44344350"),  # Seahawks DST (faces LAC skill in row) -> 49ers DST
    ("5282913479", "44344263", "44344259"),  # Greg Dulcich (MIA, faces Vikings DST) -> Michael Mayer (LV)
]
raw = open(SRC, "rb").read()
lines = raw.split(b"\n")
for ENTRY, OLD, NEW in SWAPS:
    hit = [i for i, l in enumerate(lines) if l.startswith(ENTRY.encode() + b",")]
    assert len(hit) == 1, hit
    before = lines[hit[0]]
    assert before.count(OLD.encode()) == 1 and NEW.encode() not in before, before
    lines[hit[0]] = before.replace(OLD.encode(), NEW.encode())
out = b"\n".join(lines)
open(DST, "xb").write(out)
sal = {r["ID"]: r for r in csv.DictReader(open(SAL, encoding="utf-8-sig"))}
rows = list(csv.reader(open(DST, encoding="utf-8-sig")))
lineups = []
for r in rows[1:]:
    if r and r[0].isdigit() and all(r[4:13]):
        ids = [c.split("(")[-1].rstrip(")") if "(" in c else c for c in r[4:13]]
        lineups.append({"index": len(lineups) + 1, "entry_id": r[0], "roster": ids,
                        "salary": sum(int(sal[i]["Salary"]) for i in ids)})
json.dump({"lineups": lineups, "assignments_by_entry_id": {l["entry_id"]: l["roster"] for l in lineups}}, open(PORT, "w"), indent=1)
print("sha256", hashlib.sha256(out).hexdigest(), "rows", len(lineups))
