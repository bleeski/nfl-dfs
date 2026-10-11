"""Week 5 Classic late swap: edit named cells of the CURRENT DraftKings entries file (a record, never a tool).

Usage: python late_swap_cells_record.py <current DKEntries.csv> <out.csv> <DKSalaries.csv> "ENTRY_ID:OLD_ID:NEW_ID" ...

The current file is DraftKings' own export of the entered lineups, with locked cells marked. A late-swap
upload must keep every locked player in the slot DraftKings holds him in, so this edits only the one cell that
names OLD_ID in that Entry ID's row, writes "<New Name> (NEW_ID)" there, and keeps every other byte. It refuses
(writes nothing) when the cell is marked LOCKED, the old ID is not in exactly one roster cell of the row, the
new player's position cannot fill that slot, or anything outside the named cells differs afterwards.
"""
import csv
import io
import re
import sys

cur_p, out_p, sal_p = sys.argv[1:4]
swaps = [a.split(":") for a in sys.argv[4:]]
S = {r["ID"]: r for r in csv.DictReader(open(sal_p, encoding="utf-8-sig"))}
raw = open(cur_p, "rb").read()
text = raw.decode("utf-8-sig")
bom = raw.startswith(b"\xef\xbb\xbf")
lines = text.splitlines(keepends=True)
header = next(csv.reader([lines[0]]))
SLOT = {4: ("QB",), 5: ("RB",), 6: ("RB",), 7: ("WR",), 8: ("WR",), 9: ("WR",), 10: ("TE",), 11: ("RB", "WR", "TE"),
        12: ("DST",)}
assert header[4:13] == ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"], header[4:13]
changed = []
for e, old, new in swaps:
    idx = [i for i, l in enumerate(lines) if l.startswith(e + ",")]
    if len(idx) != 1:
        sys.exit(f"REFUSED {e}: entry row not found exactly once")
    i = idx[0]
    body = lines[i].rstrip("\r\n")
    ending = lines[i][len(body):]
    cells = next(csv.reader([body]))
    hits = [j for j in range(4, 13) if re.search(r"\(" + old + r"\)", cells[j])]
    if len(hits) != 1:
        sys.exit(f"REFUSED {e}: {old} is in {len(hits)} roster cells")
    j = hits[0]
    if "LOCKED" in cells[j]:
        sys.exit(f"REFUSED {e}: cell {header[j]} is LOCKED: {cells[j]}")
    if S[new]["Position"] not in SLOT[j]:
        sys.exit(f"REFUSED {e}: {S[new]['Name']} ({S[new]['Position']}) cannot fill slot {header[j]}")
    old_cell = cells[j]
    new_cell = f"{S[new]['Name']} ({new})"
    if body.count(old_cell) != 1 or any(ch in new_cell for ch in ',"'):
        sys.exit(f"REFUSED {e}: cannot replace {old_cell!r} in place")
    lines[i] = body.replace(old_cell, new_cell, 1) + ending  # in place: every other byte of the row is kept
    changed.append((e, header[j], old_cell, new_cell))

out_text = "".join(lines)
out_bytes = (b"\xef\xbb\xbf" if bom else b"") + out_text.encode("utf-8")
# independent check: reparse both files, every cell equal except the named ones
a = list(csv.reader(io.StringIO(text)))
b = list(csv.reader(io.StringIO(out_bytes.decode("utf-8-sig"))))
diff = [(r, c) for r in range(max(len(a), len(b))) for c in range(max(len(a[r]) if r < len(a) else 0, len(b[r]) if r < len(b) else 0))
        if (a[r][c] if r < len(a) and c < len(a[r]) else None) != (b[r][c] if r < len(b) and c < len(b[r]) else None)]
if len(diff) != len(changed):
    sys.exit(f"REFUSED: {len(diff)} cells differ, expected {len(changed)}")
open(out_p, "xb").write(out_bytes)
for c in changed:
    print("CELL", c)
print("cells changed:", len(diff), "line endings CRLF:", out_bytes.count(b"\r\n"), "of", out_bytes.count(b"\n"))
