"""TB@DAL iteration 3: in Dallas-Captain rows, trade Jalon Daniels at FLEX for a Tampa Bay pass catcher.

Research, not a number: Daniels has one full NFL start (Week 4: 11.4 PPR, 2 INT, 3 sacks; nflverse
stats_player_week_2026.csv) and sat in 20 of 28 rows, most of them Dallas-win scripts where a rookie
bring-back works against the script. Dallas is without CBs Porter Jr. and Durant and LB Overshown
(buccaneers.com inactives post), which favours Otton (19% of TB targets), Egbuka (20%) and Godwin
(15%, 7 targets under Daniels). For each row with a DAL Captain and Daniels at FLEX, the best change
puts one of those three in for Daniels, alone or with one more FLEX change that spends the freed
salary (never removing Lamb, a required quarterback, or iteration 1's protected people); the K rows
losing the least prior are written as swap lines for apply_swaps.py.
usage: daniels_iter3.py SALARIES REVIEW SCORES K OUT_SWAPS
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
STARTING_QB = g["STARTING_QB"]
DANIELS = "44395118"
CATCHERS = {"44395130": "Otton", "44395120": "Egbuka", "44395121": "Godwin"}
KEEP = {"TB|TE|Cade Otton", "TB|WR|Emeka Egbuka", "TB|WR|Chris Godwin Jr.", "DAL|DST|Cowboys", "DAL|WR|CeeDee Lamb"}
flex = [i for i, v in sal.items() if v["slot"] == "FLEX" and i in score and i not in excluded]
options = []
for eid, ids in state.items():
    if sal[ids[0]]["team"] != "DAL" or DANIELS not in ids[1:]:
        continue
    req = STARTING_QB["DAL"] if sal[ids[0]]["pos"] in ("WR", "TE") else None
    best = None
    for c in CATCHERS:
        if c in ids:
            continue
        base = list(ids)
        base[ids.index(DANIELS)] = c
        if not refuse(state, eid, base):
            s = sum(score[i] for i in base)
            if best is None or s > best[0] + 1e-9:
                best = (s, [(DANIELS, c)])
        for j in range(1, 6):
            if base[j] == c or person[base[j]] == req or person[base[j]] in KEEP:
                continue
            for y in flex:
                if y == DANIELS:
                    continue
                new = list(base)
                new[j] = y
                if refuse(state, eid, new):
                    continue
                s = sum(score[i] for i in new)
                if best is None or s > best[0] + 1e-9:
                    best = (s, [(DANIELS, c), (base[j], y)])
    if best:
        options.append((sum(score[i] for i in ids) - best[0], eid, best[1]))
options.sort()
with open(out_swaps, "x") as fh:
    fh.write("# Iteration 3: Daniels out of Dallas-Captain rows for a TB pass catcher, least prior loss first.\n")
    for loss, eid, swaps in options[:k]:
        for out_id, in_id in swaps:
            fh.write(f"{eid}|FLEX|{out_id}|{in_id}|iter3: {person[out_id]}->{person[in_id]} (row prior -{loss:.2f})\n")
for loss, eid, swaps in options:
    print(round(loss, 2), eid, person[state[eid][0]], [(person[a], person[b]) for a, b in swaps])
