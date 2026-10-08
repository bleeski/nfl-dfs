"""Session 66: `qa_showdown_portfolio.py --policy --claim` checks every row against the thesis it fills.

A thesis is a choice, not a forecast: the check recomputes each row's rules from the exported bytes and reports which
rule a row breaks, never a number. A break is an operator limit (exit 2, verdict DEFECT: DraftKings accepts the file);
a thesis input that cannot be used is a validity failure (exit 1, verdict FAIL), never a PASS. Without the two flags the
script behaves as `c997395`'s did, byte for byte (pinned below from that script before it was edited).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import pytest

from nfl_dfs.byte_lines import csv_field_spans, split_byte_lines, split_line_ending
from nfl_dfs.lineups import roster_canonical_key, validate_lineup
from nfl_dfs.portfolio_policy import thesis_roster_violations

from .test_qa_showdown_portfolio import ENTRY_HEADER, LEGAL, OTHER, entry_line, files, qa
from .test_qa_showdown_portfolio import ids as synthetic_ids
from .test_qa_showdown_portfolio import salary_csv as synthetic_salary
from .test_readable_review_theses import _controls, _finished
from .test_showdown_thesis_check import (
    bounded_controls,
    cpt_flex,
    doctored_claim,
    dropped_controls,
    load,
    policy_path,
    claim_path,
    rosters,
)
from .test_showdown_theses import _policy, _thesis

# Exit code and SHA-256 of stdout of the unflagged script on the synthetic fixtures, captured from `c997395`'s
# `scripts/qa_showdown_portfolio.py` before this session edited it.
GOLDEN = {
    "clean": (0, "8c891b47e00ca31a96297eadd092a4ac4ef68d3a91e8c8ab7f6213a24b902afd"),
    "overlap_limit": (2, "a6a4785a99449d1d502c00c6add8506d819390c3040d943854a128cde34ef78e"),
    "unfilled": (3, "85c1626136bfe356f16cbf41039a81f817b6e45b35c8f35ef18f6f5d30d8bbeb"),
}


def _digest(code: int, stdout: str) -> tuple[int, str]:
    return code, hashlib.sha256(stdout.encode("utf-8")).hexdigest()


def run_qa(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = qa.main(argv)
    return code, buffer.getvalue()


def no_flag_runs(tmp_path: Path) -> dict[str, tuple[int, str]]:
    """Three runs of the script with no thesis flag on the synthetic fixtures: exit code and SHA-256 of stdout."""

    base = tmp_path / "clean"
    base.mkdir()
    salary = synthetic_salary(base)
    template, export = files(base, [LEGAL, OTHER])
    argv = ["--salaries", str(salary), "--template", str(template), "--export", str(export)]
    unfilled = tmp_path / "unfilled"
    unfilled.mkdir()
    salary_u = synthetic_salary(unfilled)
    template_u = unfilled / "tpl.csv"
    template_u.write_text(ENTRY_HEADER + entry_line(0) + entry_line(1), encoding="utf-8")
    export_u = unfilled / "exp.csv"
    export_u.write_text(ENTRY_HEADER + entry_line(0, synthetic_ids(LEGAL)) + entry_line(1), encoding="utf-8")
    return {
        "clean": _digest(*run_qa(argv)),
        "overlap_limit": _digest(*run_qa([*argv, "--max-overlap", "1"])),
        "unfilled": _digest(*run_qa(["--salaries", str(salary_u), "--template", str(template_u), "--export", str(export_u)])),
    }


def test_without_the_thesis_flags_the_output_is_the_pinned_c997395_output(tmp_path):
    assert no_flag_runs(tmp_path) == GOLDEN


# ----- real runs ---------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def acceptance(tmp_path_factory):
    return _finished(tmp_path_factory, "s66-qa-acc", policy_controls=_controls(4))


@pytest.fixture(scope="module")
def dropped(tmp_path_factory):
    return _finished(tmp_path_factory, "s66-qa-drop", policy_controls=dropped_controls)


@pytest.fixture(scope="module")
def bounded(tmp_path_factory):
    return _finished(tmp_path_factory, "s66-qa-bnd", policy_controls=bounded_controls)


def deliverable(run) -> Path:
    return Path(run.report["latest_deliverable"]["path"])


def qa_argv(run, export: Path | None = None, *extra: str) -> list[str]:
    return ["--salaries", str(run.salary), "--template", str(run.entries), "--export", str(export or deliverable(run)), *extra]


def flags(run) -> list[str]:
    return ["--policy", str(policy_path(run)), "--claim", str(claim_path(run))]


def run_json(argv, capsys):
    code = qa.main(argv)
    return code, json.loads(capsys.readouterr().out)


def first_roster_column(raw: bytes) -> int:
    return qa.cells_of(split_byte_lines(raw)[0]).index("Entry Fee") + 1


def with_roster(raw: bytes, entry_id: str, roster: list[str], *, first_slot: int = 0) -> bytes:
    """The export bytes with some of one row's roster cells replaced, nothing else touched."""

    lo = first_roster_column(raw)
    lines = list(split_byte_lines(raw))
    for n, line in enumerate(lines):
        body, ending = split_line_ending(line)
        spans = csv_field_spans(body)
        if body[spans[0][0]:spans[0][1]].decode("ascii", "ignore").strip() != entry_id:
            continue
        for offset, dk_id in enumerate(roster):
            start, end = csv_field_spans(body)[lo + first_slot + offset]
            body = body[:start] + dk_id.encode("ascii") + body[end:]
        lines[n] = body + ending
    return b"".join(lines)


def write_export(tmp_path: Path, raw: bytes, name: str = "export.csv") -> Path:
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def break_one_row(run) -> tuple[str, list[str]]:
    """(Entry ID, roster): a NE_WIN_BIG row whose Captain is replaced by a Captain of another thesis, legal and distinct."""

    book = load(run)
    delivered = rosters(run)
    keys = {roster_canonical_key(run.slate, roster) for roster in delivered.values()}
    entry = next(e for e, thesis in sorted(book.entries.items()) if thesis == "NE_WIN_BIG")
    own = book.theses["NE_WIN_BIG"].captain_people
    other = set().union(*(item.captain_people for name, item in book.theses.items() if name != "NE_WIN_BIG"))
    for row in sorted(run.slate.players, key=lambda p: p.dk_id):
        if row.role != "CPT" or row.underlying_id not in other or row.underlying_id in own:
            continue
        trial = [row.dk_id, *delivered[entry][1:]]
        result = validate_lineup(run.slate, trial)
        if result.valid and result.lineup.canonical_key not in keys:
            return entry, trial
    raise AssertionError("no legal Captain replacement from another thesis on this fixture")


def thesis_lines(out: dict) -> list[str]:
    return [line for line in out["LIMIT_BREACHES"] if "THESIS_BROKEN" in line]


def test_a_clean_real_run_passes_and_reports_every_row_with_its_thesis(acceptance, capsys):
    code, out = run_json([*qa_argv(acceptance), *flags(acceptance)], capsys)
    assert (code, out["VERDICT"]) == (0, "PASS")
    block = out["theses"]
    assert block["status"] == "CHECKED"
    assert sorted(block["entries"]) == sorted(rosters(acceptance))
    assert all(item["follows"] and item["broken_rules"] == [] for item in block["entries"].values())
    assert (block["rows_following"], block["rows_not_following"]) == (6, 0)
    assert block["entry_ids_without_thesis"] == [] and block["claimed_entry_ids_not_filled"] == []
    assert block["backup_quarterback"] == "NOT_EVALUATED" and block["backup_quarterbacks_unevaluated_teams"] == ["NE", "SEA"]
    assert {block["entries"][e]["thesis"] for e in block["entries"]} == {"NE_WIN_BIG", "NE_WIN_CLOSE_LOW", "SEA_WIN_BIG"}
    assert block["policy_sha256"] == acceptance.hashes["portfolio_policy_normalized"]
    assert "not a forecast" in block["does_not_establish"]


def test_one_row_that_breaks_its_thesis_is_named_with_its_entry_id_and_the_rule(acceptance, tmp_path, capsys):
    entry, trial = break_one_row(acceptance)
    # The new Captain belongs to another thesis's set, so the row follows a different thesis than the one it fills:
    # QA must still hold it to its own.
    book = load(acceptance)
    assert any(not thesis_roster_violations(acceptance.slate, trial, item) for name, item in book.theses.items()
               if name != "NE_WIN_BIG")
    export = write_export(tmp_path, with_roster(deliverable(acceptance).read_bytes(), entry, trial[:1]))
    code, out = run_json([*qa_argv(acceptance, export), *flags(acceptance)], capsys)
    assert (code, out["VERDICT"]) == (2, "DEFECT")
    assert out["DEFECTS"] == []  # the file itself is valid
    assert thesis_lines(out) == [f"{entry} THESIS_BROKEN thesis=NE_WIN_BIG rule=captain_set"]
    block = out["theses"]
    assert block["entries"][entry] == {"thesis": "NE_WIN_BIG", "follows": False, "broken_rules": ["captain_set"]}
    others = {e: item for e, item in block["entries"].items() if e != entry}
    assert len(others) == 5 and all(item["follows"] for item in others.values())
    assert (block["rows_following"], block["rows_not_following"]) == (5, 1)
    # Without the flags the same file reads as it always did: nothing says the row was a different bet.
    code, plain = run_json(qa_argv(acceptance, export), capsys)
    assert code == 0 and "theses" not in plain and not any("THESIS" in line for line in plain["LIMIT_BREACHES"])


def test_every_broken_rule_of_a_row_is_its_own_line_in_the_functions_order(bounded, tmp_path, capsys):
    run = bounded
    book = load(run)
    entry = next(e for e, thesis in sorted(book.entries.items()) if thesis == "NE_WIN_BIG")
    roster = cpt_flex(run.slate, "Sea QB", "Starter QB", "Sea Alpha WR", "Sea Backup RB", "Sea Third RB", "Seahawks")
    export = write_export(tmp_path, with_roster(deliverable(run).read_bytes(), entry, roster))
    code, out = run_json([*qa_argv(run, export), *flags(run)], capsys)
    assert code == 2
    assert thesis_lines(out) == [f"{entry} THESIS_BROKEN thesis=NE_WIN_BIG rule={rule}"
                                 for rule in ("captain_set", "team_bounds.NE", "structural_bounds.qb_count")]
    assert out["theses"]["entries"][entry]["broken_rules"] == ["captain_set", "team_bounds.NE", "structural_bounds.qb_count"]


def test_a_break_is_named_even_when_a_blank_row_makes_the_verdict_partial(acceptance, tmp_path, capsys):
    entry, trial = break_one_row(acceptance)
    raw = with_roster(deliverable(acceptance).read_bytes(), entry, trial[:1])
    blank = next(e for e in sorted(rosters(acceptance)) if e != entry)
    raw = with_roster(raw, blank, [""] * 6)
    code, out = run_json([*qa_argv(acceptance, write_export(tmp_path, raw)), *flags(acceptance)], capsys)
    assert (code, out["VERDICT"]) == (3, "PARTIAL")
    assert out["unfilled_entry_ids"] == [blank]
    assert thesis_lines(out) == [f"{entry} THESIS_BROKEN thesis=NE_WIN_BIG rule=captain_set"]
    assert out["theses"]["claimed_entry_ids_not_filled"] == [blank] and blank not in out["theses"]["entries"]


def test_a_filled_row_the_claim_does_not_name_is_listed_and_not_judged(acceptance, tmp_path, capsys):
    unclaimed = sorted(rosters(acceptance))[0]
    claim = doctored_claim(tmp_path, acceptance,
                           lambda rec: rec["selection"]["portfolio_policy"]["theses"]["entries"].update({unclaimed: None}))
    code, out = run_json([*qa_argv(acceptance), "--policy", str(policy_path(acceptance)), "--claim", str(claim)], capsys)
    assert (code, out["VERDICT"]) == (0, "PASS")
    assert out["theses"]["entry_ids_without_thesis"] == [unclaimed] and unclaimed not in out["theses"]["entries"]
    assert out["theses"]["rows_following"] == 5


def test_the_thesis_dropped_run_passes_against_its_rebuilt_policy(dropped, capsys):
    code, out = run_json([*qa_argv(dropped), *flags(dropped)], capsys)
    assert (code, out["VERDICT"]) == (0, "PASS")
    assert out["theses"]["theses"] == ["NE_WIN_BIG", "SEA_WIN_BIG"]
    assert out["theses"]["rows_following"] == 6


def _refusal(code, out, name):
    assert code == 1 and out["VERDICT"] == "FAIL", out
    assert out["theses"]["status"] == "REFUSED" and out["theses"]["refusal"]["code"] == name
    assert any(line.startswith(f"THESIS_INPUT_REFUSED:{name}") for line in out["DEFECTS"])
    assert "entries" not in out["theses"]  # nothing was judged


def test_a_claim_that_does_not_bind_to_the_policy_is_refused_and_never_passes(acceptance, tmp_path, capsys):
    claim = doctored_claim(tmp_path, acceptance, lambda rec: rec["selection"]["portfolio_policy"].update(
        normalized_policy_sha256="0" * 64))
    code, out = run_json([*qa_argv(acceptance), "--policy", str(policy_path(acceptance)), "--claim", str(claim)], capsys)
    _refusal(code, out, "THESIS_CLAIM_POLICY_MISMATCH")


def test_an_empty_flag_value_is_a_refused_input_not_a_skipped_check(acceptance, capsys):
    # An unset shell variable arrives as "": it must read as a path that cannot be read, never as "no check asked".
    code, out = run_json([*qa_argv(acceptance), "--policy", "", "--claim", ""], capsys)
    _refusal(code, out, "THESIS_POLICY_UNREADABLE")


def test_a_claim_that_names_no_row_is_refused_rather_than_passing_vacuously(acceptance, tmp_path, capsys):
    claim = doctored_claim(tmp_path, acceptance, lambda rec: rec["selection"]["portfolio_policy"]["theses"]["entries"].update(
        {entry: None for entry in rosters(acceptance)}))
    code, out = run_json([*qa_argv(acceptance), "--policy", str(policy_path(acceptance)), "--claim", str(claim)], capsys)
    _refusal(code, out, "THESIS_CLAIM_NAMES_NO_ROW")


@pytest.mark.parametrize("flag", ["--policy", "--claim"])
def test_one_flag_without_the_other_is_refused(flag, acceptance, capsys):
    value = str(policy_path(acceptance) if flag == "--policy" else claim_path(acceptance))
    code, out = run_json([*qa_argv(acceptance), flag, value], capsys)
    _refusal(code, out, "THESIS_INPUT_INCOMPLETE")


def test_a_single_thesis_policy_is_refused_not_skipped(acceptance, tmp_path, capsys):
    thesis = _thesis(acceptance.slate, ["NE Kicker", "Patriots"], name="NE_WIN_CLOSE_LOW", teams=["NE"])
    policy, _source = _policy(acceptance.slate, thesis, entry_ids=("1", "2"))
    path = tmp_path / "v3.json"
    path.write_bytes(policy.canonical_bytes())
    code, out = run_json([*qa_argv(acceptance), "--policy", str(path), "--claim", str(claim_path(acceptance))], capsys)
    _refusal(code, out, "THESIS_POLICY_NOT_A_PORTFOLIO")


def test_lineups_moved_between_entry_ids_by_hand_are_refused_by_name(acceptance, tmp_path, capsys):
    book = load(acceptance)
    delivered = rosters(acceptance)
    first, other = next((a, b) for a in sorted(book.entries) for b in sorted(book.entries)
                        if book.entries[a] != book.entries[b])
    raw = with_roster(deliverable(acceptance).read_bytes(), first, delivered[other])
    raw = with_roster(raw, other, delivered[first])
    code, out = run_json([*qa_argv(acceptance, write_export(tmp_path, raw)), *flags(acceptance)], capsys)
    _refusal(code, out, "THESIS_CLAIM_DISAGREES_WITH_ROWS")
    assert first in out["theses"]["refusal"]["detail"] and other in out["theses"]["refusal"]["detail"]


def test_the_output_is_deterministic(acceptance, capsys):
    argv = [*qa_argv(acceptance), *flags(acceptance)]
    qa.main(argv)
    first = capsys.readouterr().out
    qa.main(argv)
    assert capsys.readouterr().out == first
