"""TB@DAL iteration 2: place CeeDee Lamb at FLEX in place of George Pickens, by construction.

Research, not a number (nflverse stats_player_week_2026.csv, SHA-256 7c95b7db...): Lamb holds 32% of
Dallas targets in 2026 (28.0 PPR per game), Pickens 19% (10.1). The run's 2025-based prior ranks
Pickens above Lamb. For each row with Pickens at FLEX and neither of them at Captain, the best
Pickens->Lamb change is found (alone, or with one more FLEX change to fit the cap, maximizing the
row's prior); the K rows that lose the least prior are written as swap lines for apply_swaps.py.
usage: lamb_flex_iter2.py SALARIES REVIEW SCORES K OUT_SWAPS
"""
import io, contextlib, os, runpy, sys, tempfile
salaries, review, scores_path, k, out_swaps = sys.argv[1:6]
k = int(k)
here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
open(os.path.join(tmp, "e.txt"), "w").close()
argv = sys.argv
sys.argv = ["x", salaries, review, scores_path, os.path.join(tmp, "e.txt"), os.path.join(tmp, "e.csv"), os.path.join(tmp, "e.json")]
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path(os.path.join(here, "apply_swaps.py"))
sys.argv = argv
state, refuse, sal, person, score, excluded = g["state"], g["refuse"], g["sal"], g["person"], g["score"], g["excluded"]
LAMB, PICKENS = "44395113", "44395117"
STARTING_QB = g["STARTING_QB"]
flex = [i for i, v in sal.items() if v["slot"] == "FLEX" and i in score and i not in excluded]
# Never fund Lamb by removing the TB pass catchers or the DST that iteration 1 placed for its scripts.
PROTECT = {"TB|TE|Cade Otton", "TB|WR|Emeka Egbuka", "TB|WR|Chris Godwin Jr.", "DAL|DST|Cowboys"}
options = []
for eid, ids in state.items():
    cpt = person[ids[0]]
    if PICKENS not in ids[1:] or "CeeDee Lamb" in cpt or "George Pickens" in cpt:
        continue
    req = STARTING_QB[sal[ids[0]]["team"]] if sal[ids[0]]["pos"] in ("WR", "TE") else None
    base = list(ids)
    base[ids.index(PICKENS)] = LAMB
    best = None
    if not refuse(state, eid, base) and not (set(person[i] for i in ids) & PROTECT - set(person[i] for i in base)):
        best = (sum(score[i] for i in base), [(PICKENS, LAMB)])
    for j in range(1, 6):
        if base[j] == LAMB or person[base[j]] == req or person[base[j]] in PROTECT:
            continue
        for y in flex:
            new = list(base)
            new[j] = y
            if refuse(state, eid, new):
                continue
            s = sum(score[i] for i in new)
            if best is None or s > best[0] + 1e-9:
                best = (s, [(PICKENS, LAMB), (base[j], y)])
    if best:
        options.append((sum(score[i] for i in ids) - best[0], eid, best[1]))
options.sort()
with open(out_swaps, "x") as fh:
    fh.write("# Iteration 2: Lamb at FLEX for Pickens (2026 usage), least prior loss first.\n")
    for loss, eid, swaps in options[:k]:
        for out_id, in_id in swaps:
            fh.write(f"{eid}|FLEX|{out_id}|{in_id}|iter2: {person[out_id]}->{person[in_id]} (row prior -{loss:.2f})\n")
for loss, eid, swaps in options:
    print(round(loss, 2), eid, [(person[a], person[b]) for a, b in swaps])
