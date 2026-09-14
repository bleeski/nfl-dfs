#!/usr/bin/env python3
"""Write the exact-template DraftKings entries CSV from a portfolio, and verify.

Provenance: promoted from the 2026-09-13 session scratchpad. Independent of the
engine exporter on purpose - this is the byte-level verification the skill
requires at handoff (diff the export against the source template and assert
nothing outside the nine authorized roster cells per Entry ID moved). It ran on
every version shipped that day and reported 0 cells changed each time.
"""

import csv, json, sys, hashlib

sel_path, tmpl_path, sal_path, out_path = sys.argv[1:5]
sel = json.load(open(sel_path))
rows = list(csv.reader(open(tmpl_path, encoding="utf-8-sig")))
hdr = rows[0]
fee = hdr.index("Entry Fee")
# roster region ends at the first blank/Instructions marker after Entry Fee
end = len(hdr)
for marker in ("", "Instructions"):
    if marker in hdr[fee + 1:]:
        end = min(end, hdr.index(marker, fee + 1))
roster_cols = hdr[fee + 1:end]           # QB,RB,RB,WR,WR,WR,TE,FLEX,DST
assert roster_cols == ["QB","RB","RB","WR","WR","WR","TE","FLEX","DST"], roster_cols

sal = {r["ID"]: r for r in csv.DictReader(open(sal_path, encoding="utf-8-sig"))}
by_entry = sel["assignments_by_entry_id"]

def slot_fill(ids):
    """Place nine dk_ids into QB,RB,RB,WR,WR,WR,TE,FLEX,DST by eligibility."""
    need = {"QB":1,"RB":2,"WR":3,"TE":1,"DST":1}
    pos = {i: sal[i]["Position"] for i in ids}
    out = {k: [] for k in ("QB","RB","WR","TE","DST")}
    flex = []
    for i in ids:
        p = pos[i]
        if len(out[p]) < need.get(p, 0):
            out[p].append(i)
        else:
            flex.append(i)
    assert len(flex) == 1, f"flex resolution failed: {flex} from {pos}"
    return [out["QB"][0], out["RB"][0], out["RB"][1],
            out["WR"][0], out["WR"][1], out["WR"][2],
            out["TE"][0], flex[0], out["DST"][0]]

changed = 0
for r in rows[1:]:
    eid = r[0].strip() if r else ""
    if not eid or not eid.isdigit() or eid not in by_entry:
        continue
    ids = by_entry[eid]
    ids = ids["roster"] if isinstance(ids, dict) else ids
    cells = slot_fill(list(ids))
    while len(r) < end:
        r.append("")
    for k, v in enumerate(cells):
        assert r[fee + 1 + k] == "", f"entry {eid} slot {k} was not blank"
        r[fee + 1 + k] = v
    changed += 1

with open(out_path, "w", newline="", encoding="utf-8") as fh:
    csv.writer(fh, lineterminator="\r\n").writerows(rows)

# ---- independent verification against the untouched template ----
src = list(csv.reader(open(tmpl_path, encoding="utf-8-sig")))
got = list(csv.reader(open(out_path, encoding="utf-8-sig")))
assert len(src) == len(got), f"row count changed {len(src)} -> {len(got)}"
moved = []
for a, b in zip(src, got):
    pa = a + [""] * (max(len(a), len(b)) - len(a))
    pb = b + [""] * (max(len(a), len(b)) - len(b))
    for j, (x, y) in enumerate(zip(pa, pb)):
        if x != y and not (fee + 1 <= j < end):
            moved.append((a[0] if a else "", j, x, y))
print(f"entries filled: {changed}")
print(f"cells changed outside the nine roster slots: {len(moved)} {moved[:5]}")
print(f"sha256: {hashlib.sha256(open(out_path,'rb').read()).hexdigest()}")
