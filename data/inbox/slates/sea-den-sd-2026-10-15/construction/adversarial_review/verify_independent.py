"""Independent check of a candidate Showdown file against the base: hard constraints and both goals' measures."""
import csv
import itertools
import json
import sys
from collections import Counter, defaultdict

salaries, base_path, cand_path, scores_path = sys.argv[1:5]
sal = {r["ID"]: r for r in csv.DictReader(open(salaries, encoding="utf-8-sig"))}
sc = json.load(open(scores_path))
score = {i: float(v) for i, v in sc["by_dk_id"].items()}
excluded = set(sc["excluded_dk_ids"])
QB = {"SEA": "Sam Darnold", "DEN": "Bo Nix"}
BACKUP = {"Drew Lock", "Jarrett Stidham"}


def load(p):
    raw = open(p, "rb").read()
    rows, contest, other = {}, {}, []
    for line in raw.split(b"\r\n")[1:]:
        f = line.split(b",")
        if len(f) > 9 and f[0].strip() and f[4].strip():
            rows[f[0].decode()] = [x.decode() for x in f[4:10]]
            contest[f[0].decode()] = f[2].decode()
        else:
            other.append(line)
    return raw, rows, contest, other


def nm(i):
    return sal[i]["TeamAbbrev"] + "|" + sal[i]["Name"]


def measures(rows, contest):
    c = Counter()
    for v in rows.values():
        c.update({nm(i) for i in v})
    caps = Counter(nm(v[0]) for v in rows.values())
    pairs = [len({nm(i) for i in a} & {nm(i) for i in b}) for a, b in itertools.combinations(rows.values(), 2)]
    per = defaultdict(list)
    for e, v in rows.items():
        per[contest[e]].append(v)
    pc = {}
    for k, vs in per.items():
        w = max((len({nm(i) for i in a} & {nm(i) for i in b}) for a, b in itertools.combinations(vs, 2)), default=0)
        pc[k] = (len(vs), len({nm(v[0]) for v in vs}), w)
    return {
        "total_prior": round(sum(sum(score[i] for i in v) for v in rows.values()), 2),
        "min_row_prior": round(min(sum(score[i] for i in v) for v in rows.values()), 2),
        "max_person": c.most_common(1)[0],
        "top3_slots": sum(n for _, n in c.most_common(3)),
        "mean_overlap": round(sum(pairs) / len(pairs), 4),
        "max_overlap": max(pairs),
        "distinct_people": len(c),
        "captains": caps.most_common(),
        "per_contest(entries,distinct_cpt,worst_pair)": pc,
        "booster_prior": sorted(round(sum(score[i] for i in v), 1) for e, v in rows.items() if contest[e] == "196781421"),
    }


def defects(rows):
    out = []
    seen = set()
    c = Counter()
    for v in rows.values():
        c.update({nm(i) for i in v})
    caps = Counter(nm(v[0]) for v in rows.values())
    for e, v in rows.items():
        if sal[v[0]]["Roster Position"] != "CPT" or any(sal[i]["Roster Position"] != "FLEX" for i in v[1:]):
            out.append((e, "SLOT"))
        if sum(int(sal[i]["Salary"]) for i in v) > 50000:
            out.append((e, "SALARY"))
        ps = [nm(i) for i in v]
        if len(set(ps)) != 6:
            out.append((e, "DUP_PERSON"))
        if len({sal[i]["TeamAbbrev"] for i in v}) < 2:
            out.append((e, "ONE_TEAM"))
        for i in v:
            if i not in score or i in excluded or sal[i]["Status"].strip() not in ("", "Q") or sal[i]["Name"] in BACKUP:
                out.append((e, "BAD_ID " + nm(i)))
        cp = sal[v[0]]
        if cp["Position"] in ("WR", "TE") and cp["TeamAbbrev"] + "|" + QB[cp["TeamAbbrev"]] not in ps:
            out.append((e, "WRTE_CPT_NO_QB"))
        for i in v:
            if sal[i]["Position"] == "DST":
                opp = "DEN" if sal[i]["TeamAbbrev"] == "SEA" else "SEA"
                if opp + "|" + QB[opp] in ps:
                    out.append((e, "DST_VS_QB"))
        if cp["Position"] == "DST":
            opp = [sal[i] for i in v[1:] if sal[i]["TeamAbbrev"] != cp["TeamAbbrev"]]
            if len(opp) > 1 or any(o["Position"] not in ("RB", "K") for o in opp):
                out.append((e, "DST_SHAPE"))
        key = (nm(v[0]), frozenset(ps[1:]))
        if key in seen:
            out.append((e, "DUP_LINEUP"))
        seen.add(key)
    for p, n in c.items():
        lim = 21 if p in ("SEA|Sam Darnold", "DEN|Bo Nix") else 17
        if n > lim:
            out.append((p, f"EXPOSURE {n}"))
    for p, n in caps.items():
        if n > 5:
            out.append((p, f"CAPTAIN {n}"))
    for a, b in itertools.combinations(rows, 2):
        if len({nm(i) for i in rows[a]} & {nm(i) for i in rows[b]}) > 5:
            out.append((a + "/" + b, "OVERLAP"))
    return out


braw, brows, bcon, both = load(base_path)
craw, crows, ccon, coth = load(cand_path)
assert set(brows) == set(crows) and bcon == ccon, "ENTRY_OR_CONTEST_CHANGED"
assert both == coth, "NON_ROSTER_LINES_CHANGED"
print("crlf_lines", craw.count(b"\r\n"), "bare_lf", craw.count(b"\n") - craw.count(b"\r\n"))
print("defects", defects(crows))
mb, mc = measures(brows, bcon), measures(crows, ccon)
for k in mb:
    print(k, "|", mb[k], "->", mc[k])
print("changed_rows", sorted(e for e in brows if brows[e] != crows[e]))
