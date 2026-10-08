"""Session 66: `showdown_value_add.py --policy --claim` never takes a swap that breaks the thesis its row fills.

A thesis is a choice, not a forecast; the tool writes no number for anyone. A swap whose rebuilt roster breaks the
thesis of the Entry ID it lands in is refused by name (`SWAP_BREAKS_THESIS`, the thesis and each rule), `--count` takes
the next swap that keeps the thesis or skips the row and names it, and `--entry-id` on a breaking row refuses the run
and writes nothing. Without the two flags the tool behaves as `c997395`'s did, byte for byte (pinned below from that
script before it was edited). Rule-kind cases use the synthetic DEN@KC slate with a hand-built thesis book; the real
loader and the real run-slate bytes are exercised in `test_showdown_thesis_check.py` and the end-to-end cases at the end.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import pytest

from nfl_dfs.dk import parse_salaries
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.portfolio_policy import PersonBinding, StructuralBoundRange, StructuralBounds
from nfl_dfs.showdown_theses import CountBound, ShowdownThesis

from .test_qa_showdown_thesis import acceptance, bounded, deliverable, flags, qa_argv, run_json  # noqa: F401 (the run fixtures)
from .test_showdown_thesis_check import check_module, claim_path, load, rosters
from .test_showdown_value_add import BASE, CPT, FLEX, L0, L3, NAME, T, build, entry_id, go, refused, scores, tool

# Per scenario: exit code, then SHA-256 of stdout (output path masked), of stderr, and of the written file (None when
# nothing was written); captured from `c997395`'s `scripts/showdown_value_add.py` before this session edited it.
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # SHA-256 of no bytes
GOLDEN = {
    "count": (0, "c6a343b251979dc5a0aab36399ac4835911ff8afd0ca42384277fbb51e8df238", EMPTY,
              "f74a3f29293b54ed3dcd39e79d439165cf0e529c69c709c3fc8c2b33fb8572ce"),
    "captain": (0, "2eef9095a58ec938f575e50d548a0b6a2c75b80d6dfdefc5c88dab26a083e378", EMPTY,
                "8fa6495f6418cb10021d0fb3ab02d513801f4add6efa204a6bfaf08cbf863b1c"),
    "refused": (2, EMPTY, "cebd95b41588ac34ad2a927f259e368b2281847ef10049dc4513eb90b8c3e42d", None),
}

FLAGS = ["--policy", "policy.json", "--claim", "claim.json"]
FIRST, SECOND = entry_id(0), entry_id(1)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def no_flag_runs(tmp_path: Path) -> dict[str, tuple]:
    """Three runs with no thesis flag on the synthetic fixtures: exit code and hashes of every byte the tool emits."""

    results = {}
    scenarios = (
        ("count", ["--dk-id", FLEX[T], "--count", "2"]),
        ("captain", ["--dk-id", CPT[T], "--captain", "--entry-id", SECOND]),
        ("refused", ["--dk-id", "999999"]),
    )
    for name, args in scenarios:
        folder = tmp_path / name
        folder.mkdir()
        w = build(folder, BASE)
        target = folder / "out.csv"
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = tool.main(["--salaries", str(w["sal"]), "--template", str(w["tpl"]), "--review", str(w["rev"]),
                              "--out", str(target), *args])
        written = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        results[name] = (code, _sha(stdout.getvalue().replace(str(target), "<OUT>")), _sha(stderr.getvalue()), written)
    return results


def test_without_the_thesis_flags_the_output_is_the_pinned_c997395_output(tmp_path):
    assert no_flag_runs(tmp_path) == GOLDEN


# ----- a hand-built thesis book on the synthetic slate --------------------------------------------------------------


def person(slate, key: str) -> PersonBinding:
    rows = [row for row in slate.players if row.name == NAME[key]]
    return PersonBinding(rows[0].underlying_id, next(r.dk_id for r in rows if r.role == "CPT"),
                         next(r.dk_id for r in rows if r.role == "FLEX"))


def thesis(slate, name: str, captains, effective=StructuralBounds(), **fields) -> ShowdownThesis:
    return ShowdownThesis(name=name, teams=("KC", "DEN"), captain_set=tuple(person(slate, key) for key in captains),
                          row_weight=1, rows=1, effective_bounds=effective, **fields)


def use_book(monkeypatch, w, entries: dict[str, str | None], *theses_for) -> None:
    """Make the tool's loader return a book of the named theses; `theses_for` is a function of the slate."""

    slate = parse_salaries(w["sal"])
    theses = {item.name: item for item in theses_for[0](slate)}
    book = check_module().ThesisBook(
        slate=slate, theses=theses, entries=entries,
        hashes={"policy_sha256": "a" * 64, "claim_sha256": "b" * 64, "salary_sha256": slate.salary_hash})
    monkeypatch.setattr(check_module(), "load_thesis_book", lambda *args, **kwargs: book)


def qb_cap(slate):  # every swap of a quarterback into a one-quarterback row breaks the position count
    return [thesis(slate, "TH_QB", ["kc_qb"], position_bounds=(CountBound("QB", 0, 1),)),
            thesis(slate, "TH_FREE", ["kc_qb", "den_wr1"])]  # no bounds: it follows both L0 and L3


def removed(report) -> list[tuple[str, str]]:
    return [(s["entry_id"], s["removed"]) for s in report["swaps"]]


# ----- one refusal per kind of break --------------------------------------------------------------------------------


def test_a_position_count_break_is_refused_by_name_and_nothing_is_written(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, L3])  # L0 holds one quarterback, and the person worked in is a quarterback
    use_book(monkeypatch, w, {FIRST: "TH_QB", SECOND: None}, qb_cap)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", FIRST, *FLAGS)
    refused(code, err, out, "SWAP_BREAKS_THESIS")
    assert FIRST in err and "fills TH_QB" in err and "position_bounds.QB" in err
    assert "no legal swap leaves it following" in err


def test_a_team_count_break_is_refused_by_name(tmp_path, capsys, monkeypatch):
    row = ["den_qb", "kc_wr1", "kc_wr2", "kc_te", "kc_rb", "kc_k"]  # one Denver Captain, five Kansas City FLEX
    w = build(tmp_path, [row])
    use_book(monkeypatch, w, {FIRST: "TH_DEN"},
             lambda slate: [thesis(slate, "TH_DEN", ["den_qb"], team_bounds=(CountBound("DEN", 1, 1),))])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX["den_rb"], "--entry-id", FIRST, *FLAGS)
    refused(code, err, out, "SWAP_BREAKS_THESIS")
    assert "fills TH_DEN" in err and "team_bounds.DEN" in err  # any Kansas City cell out and a second Denver person in


def test_a_captain_set_break_is_refused_by_name_and_the_same_swap_keeps_a_thesis_that_names_him(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0])
    use_book(monkeypatch, w, {FIRST: "TH"}, lambda slate: [thesis(slate, "TH", ["kc_qb"])])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", CPT[T], "--captain", "--entry-id", FIRST, *FLAGS)
    refused(code, err, out, "SWAP_BREAKS_THESIS")
    assert "fills TH:" in err and "captain_set" in err
    use_book(monkeypatch, w, {FIRST: "TH"}, lambda slate: [thesis(slate, "TH", ["kc_qb", T])])
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", CPT[T], "--captain", "--entry-id", FIRST, *FLAGS, out="b.csv")
    assert code == tool.EXIT_OK, err
    assert removed(report) == [(FIRST, "KC QB")]


def test_an_effective_structural_bound_break_is_refused_by_name(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0])
    bounds = StructuralBounds(qb_count=StructuralBoundRange(minimum=0, maximum=1))
    use_book(monkeypatch, w, {FIRST: "TH"}, lambda slate: [thesis(slate, "TH", ["kc_qb"], effective=bounds)])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", FIRST, *FLAGS)
    refused(code, err, out, "SWAP_BREAKS_THESIS")
    assert "fills TH:" in err and "structural_bounds.qb_count" in err


def test_every_skipped_explicit_row_is_named_in_one_refusal(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, BASE[1]])  # both Captains are the row's only quarterback, so every swap of T adds a second
    use_book(monkeypatch, w, {FIRST: "TH_QB", SECOND: "TH_QB"},
             lambda slate: [thesis(slate, "TH_QB", ["kc_qb", "den_qb"], position_bounds=(CountBound("QB", 0, 1),))])
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--entry-id", FIRST, "--entry-id", SECOND, *FLAGS)
    refused(code, err, out, "SWAP_BREAKS_THESIS")
    assert FIRST in err and SECOND in err


# ----- --count: the next swap that keeps the thesis, or the row skipped and named --------------------------------


DEN_PAIR_SCORES = {"den_rb": 0.1, "den_wr2": 0.2, "kc_wr2": 2.0, "kc_te": 3.0, "kc_rb": 4.0,
                   "den_te": 1.0, "kc_qb": 5.0, "kc_wr1": 6.0, "kc_k": 7.0, "den_dst": 8.0}


def den_floor(slate):  # L0 holds two Denver people; the worked-in person is Kansas City's, so a Denver cell must stay
    return [thesis(slate, "TH_DEN", ["kc_qb"], team_bounds=(CountBound("DEN", 2, 6),)),
            thesis(slate, "TH_FREE", ["den_wr1"])]


def score_file(tmp_path) -> str:
    return str(scores(tmp_path, {FLEX[key]: value for key, value in DEN_PAIR_SCORES.items()}))


def test_count_takes_the_next_swap_that_keeps_the_thesis_not_the_cheapest_one(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0])
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1", "--scores", score_file(tmp_path),
                                 out="plain.csv")
    assert code == tool.EXIT_OK, err
    assert removed(report) == [(FIRST, "DEN RB")]  # without a thesis the cheapest cell goes: a Denver person
    use_book(monkeypatch, w, {FIRST: "TH_DEN"}, den_floor)
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1", "--scores", score_file(tmp_path),
                                 *FLAGS, out="thesis.csv")
    assert code == tool.EXIT_OK, err
    assert removed(report) == [(FIRST, "KC WR2")]  # the cheapest cell that leaves two Denver people


def test_a_row_ranks_by_its_cheapest_swap_that_keeps_its_thesis(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, L3])
    args = ["--dk-id", FLEX[T], "--count", "1", "--scores", score_file(tmp_path)]
    code, report, err, _out = go(tmp_path, capsys, w, *args, out="plain.csv")
    assert code == tool.EXIT_OK, err
    assert [s[0] for s in removed(report)] == [FIRST]  # unconstrained, row 0's 0.1 is the cheapest swap in the file
    use_book(monkeypatch, w, {FIRST: "TH_DEN", SECOND: "TH_FREE"}, den_floor)
    code, report, err, _out = go(tmp_path, capsys, w, *args, *FLAGS, out="thesis.csv")
    assert code == tool.EXIT_OK, err
    # Row 0's cheapest kept swap costs 2.0, so row 1 (1.0) goes first and the one swap is spent on it.
    assert removed(report) == [(SECOND, "DEN TE")]


def test_count_skips_a_row_whose_every_swap_breaks_names_it_and_still_swaps_the_others(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, L3])
    use_book(monkeypatch, w, {FIRST: "TH_QB", SECOND: "TH_FREE"}, qb_cap)
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2", *FLAGS)
    assert code == tool.EXIT_PARTIAL, err
    assert [s["entry_id"] for s in report["swaps"]] == [SECOND]
    assert report["skipped"] == {FIRST: "SWAP_BREAKS_THESIS:TH_QB:position_bounds.QB"}
    assert (report["requested"], report["swapped"], report["shortfall"]) == (2, 1, 1)
    assert out.exists()


def test_when_no_row_can_take_him_without_breaking_its_thesis_nothing_is_written(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0])
    use_book(monkeypatch, w, {FIRST: "TH_QB"}, qb_cap)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], *FLAGS)
    refused(code, err, out, "NO_ROW_CHANGED")
    assert "1 break their thesis" in err


def test_a_row_the_claim_does_not_name_is_unconstrained_and_listed(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, L3])
    use_book(monkeypatch, w, {FIRST: "TH_QB", SECOND: None}, qb_cap)
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2", *FLAGS)
    assert code == tool.EXIT_PARTIAL, err
    assert [s["entry_id"] for s in report["swaps"]] == [SECOND]
    assert report["theses"]["rows_without_thesis"] == [SECOND] and report["theses"]["rows_with_thesis"] == 1


def test_a_row_that_already_breaks_its_thesis_is_only_swapped_to_a_roster_that_follows(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [BASE[1], L0])  # row 0's Captain is DEN QB, but its thesis names KC QB
    use_book(monkeypatch, w, {FIRST: "TH", SECOND: "TH"}, lambda slate: [thesis(slate, "TH", ["kc_qb"])])
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2", *FLAGS)
    assert code == tool.EXIT_PARTIAL, err
    assert [s["entry_id"] for s in report["swaps"]] == [SECOND]
    assert report["skipped"] == {FIRST: "SWAP_BREAKS_THESIS:TH:captain_set"}
    block = report["theses"]
    assert (block["not_following_before"], block["not_following_after"]) == ([FIRST], [FIRST])


# ----- the flags and the report -------------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--policy", "--claim"])
def test_one_flag_without_the_other_is_refused_and_nothing_is_written(flag, tmp_path, capsys):
    w = build(tmp_path, BASE)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], flag, "x.json")
    refused(code, err, out, "THESIS_INPUT_INCOMPLETE")


def test_an_empty_flag_value_refuses_the_run_and_nothing_is_written(tmp_path, capsys):
    # An unset shell variable arrives as "": it must never read as "no thesis check was asked for".
    w = build(tmp_path, BASE)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--policy", "", "--claim", "")
    refused(code, err, out, "THESIS_POLICY_UNREADABLE")


def test_a_refused_thesis_input_is_named_and_nothing_is_written(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, BASE)
    check = check_module()

    def refuse(*args, **kwargs):
        raise check.ThesisInputRefused("THESIS_CLAIM_POLICY_MISMATCH", "the claim names another policy")

    monkeypatch.setattr(check, "load_thesis_book", refuse)
    code, _report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], *FLAGS)
    refused(code, err, out, "THESIS_CLAIM_POLICY_MISMATCH")


def test_the_report_carries_the_bindings_and_only_in_thesis_mode(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, L3])
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1", out="plain.csv")
    assert code == tool.EXIT_OK, err
    assert "theses" not in report
    use_book(monkeypatch, w, {FIRST: "TH_FREE", SECOND: "TH_FREE"}, qb_cap)
    code, report, err, out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "1", *FLAGS, out="thesis.csv")
    assert code == tool.EXIT_OK, err
    block = report["theses"]
    assert (block["policy_sha256"], block["claim_sha256"]) == ("a" * 64, "b" * 64)
    assert block["salary_sha256"] == report["salary_sha256"]
    assert block["theses"] == ["TH_QB", "TH_FREE"] and block["not_following_before"] == block["not_following_after"] == []
    assert block["backup_quarterback"] == "NOT_EVALUATED"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert not any("projection" in key.lower() or "prior_points" in key for key in block)


def test_the_label_filter_still_restricts_rows_with_the_flags_present(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, L3])
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({FIRST: "X", SECOND: "Y"}), encoding="utf-8")
    use_book(monkeypatch, w, {FIRST: "TH_FREE", SECOND: "TH_FREE"}, qb_cap)
    code, report, err, _out = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2", "--theses", str(labels),
                                 "--thesis", "Y", *FLAGS)
    assert code == tool.EXIT_PARTIAL, err  # the filter leaves one row, so two requested is a shortfall
    assert [s["entry_id"] for s in report["swaps"]] == [SECOND]


def test_the_output_bytes_are_deterministic_with_the_flags(tmp_path, capsys, monkeypatch):
    w = build(tmp_path, [L0, L3])
    use_book(monkeypatch, w, {FIRST: "TH_FREE", SECOND: "TH_FREE"}, qb_cap)
    first = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2", *FLAGS, out="a.csv")
    second = go(tmp_path, capsys, w, "--dk-id", FLEX[T], "--count", "2", *FLAGS, out="b.csv")
    assert first[0] == second[0] == tool.EXIT_OK
    assert first[3].read_bytes() == second[3].read_bytes()


# ----- end to end on the real run-slate bytes -------------------------------------------------------------------------


def _held(run):
    by_id = {row.dk_id: row for row in run.slate.players}
    return {entry: {by_id[dk].underlying_id for dk in roster} for entry, roster in rosters(run).items()}


def _value_add(run, out: Path, *args: str) -> int:
    return tool.main(["--salaries", str(run.salary), "--template", str(run.entries), "--review", str(deliverable(run)),
                      "--out", str(out), *args, *flags(run)])


def test_a_real_run_swap_is_accepted_and_qa_with_the_same_flags_agrees(acceptance, tmp_path, capsys):
    # The 23c theses name Captains only, so no FLEX swap can break them: this is the tool and QA agreeing end to end on
    # real bytes, not a test of the filter (the bounded run below and the rule-kind cases above are).
    run = acceptance
    held = _held(run)
    candidates = [row for row in sorted(run.slate.players, key=lambda p: p.dk_id)
                  if row.role == "FLEX" and not row.status_raw and any(row.underlying_id not in held[e] for e in held)]
    for attempt, person in enumerate(candidates):
        out = tmp_path / f"value_add_{attempt}.csv"
        code = _value_add(run, out, "--dk-id", person.dk_id, "--count", "6")
        captured = capsys.readouterr()
        if code in (tool.EXIT_OK, tool.EXIT_PARTIAL):
            break
    else:
        raise AssertionError("no person in this tiny pool could be swapped into a real row")
    report = json.loads(captured.out)
    assert report["swapped"] >= 1
    block = report["theses"]
    assert block["not_following_before"] == [] and block["not_following_after"] == []
    assert block["policy_sha256"] == run.hashes["portfolio_policy_normalized"]
    # The independent oracle: QA, with the same flags, over the file the tool wrote.
    # The overlap limit is opened to six: this tool is construction only, and one person added across a 16-person pool can
    # push a pair past the policy's cap of four, which is not what is under test.
    qa_code, qa_out = run_json([*qa_argv(run, out, "--max-overlap", "6"), *flags(run)], capsys)
    assert qa_out["theses"]["rows_not_following"] == 0 and qa_code == 0, qa_out["LIMIT_BREACHES"]


def test_a_real_run_with_bounds_never_takes_the_swap_that_breaks_them(bounded, tmp_path, capsys):
    """NE_WIN_BIG carries a team bound and the policy a one-quarterback bound: a second quarterback must come in only
    where the first goes out. The oracle lists each legal slot and whether the thesis keeps it, independent of the tool."""

    run = bounded
    book = load(run)
    delivered, held = rosters(run), _held(run)
    sea_qb = next(row for row in run.slate.players if row.name == "Sea QB" and row.role == "FLEX")
    for entry in sorted(e for e, name in book.entries.items() if name == "NE_WIN_BIG" and sea_qb.underlying_id not in held[e]):
        roster = delivered[entry]
        trials = {slot: [*roster[:slot], sea_qb.dk_id, *roster[slot + 1:]] for slot in range(1, 6)}
        legal = [slot for slot, trial in trials.items() if validate_lineup(run.slate, trial).valid]
        kept = [slot for slot in legal if not book.check(entry, trials[slot])[1]]
        if len(legal) > len(kept):  # at least one legal swap breaks a bound, so the filter has work to do
            break
    else:
        raise AssertionError("no NE_WIN_BIG row on this fixture has a legal swap that breaks a bound")
    out = tmp_path / "bounded.csv"
    code = _value_add(run, out, "--dk-id", sea_qb.dk_id, "--entry-id", entry)
    captured = capsys.readouterr()
    if kept:
        assert code == tool.EXIT_OK, captured.err
        taken = json.loads(captured.out)["swaps"][0]["removed_dk_id"]
        assert taken in {roster[slot] for slot in kept}  # never a cell whose swap breaks the bounds
        qa_code, qa_out = run_json([*qa_argv(run, out, "--max-overlap", "6"), *flags(run)], capsys)
        assert qa_out["theses"]["rows_not_following"] == 0 and qa_code == 0, qa_out["LIMIT_BREACHES"]
    else:
        assert code == tool.EXIT_REFUSED and not out.exists()
        assert "REFUSED SWAP_BREAKS_THESIS" in captured.err and f"entry {entry} fills NE_WIN_BIG" in captured.err
        # Every rule the oracle finds broken across the legal slots is named (here a team bound and the quarterback bound).
        for rule in set().union(*(book.check(entry, trials[slot])[1] for slot in legal)):
            assert rule in captured.err


def test_a_captain_swap_outside_the_rows_captain_set_is_refused_in_a_real_run(acceptance, tmp_path, capsys):
    run = acceptance
    book = load(run)
    delivered = rosters(run)
    held = _held(run)
    own = book.theses["NE_WIN_BIG"].captain_people
    for entry in sorted(e for e, name in book.entries.items() if name == "NE_WIN_BIG"):
        for row in sorted(run.slate.players, key=lambda p: p.dk_id):
            if row.role != "CPT" or row.status_raw or row.underlying_id in own or row.underlying_id in held[entry]:
                continue
            if validate_lineup(run.slate, [row.dk_id, *delivered[entry][1:]]).valid:
                out = tmp_path / "refused.csv"
                code = _value_add(run, out, "--dk-id", row.dk_id, "--captain", "--entry-id", entry)
                err = capsys.readouterr().err
                assert code == tool.EXIT_REFUSED and not out.exists()
                assert "REFUSED SWAP_BREAKS_THESIS" in err and f"entry {entry} fills NE_WIN_BIG" in err
                assert "captain_set" in err
                return
    raise AssertionError("no legal Captain swap outside the set on this fixture")
