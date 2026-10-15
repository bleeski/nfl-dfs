"""Session 75b: the first-place reading's two run-path builders and the Classic QA's guarded print, unit by unit.

`prior_review._first_place_reading` reads the contest step's claim against the final assignment and the run's facts block;
`readable_review.first_place_review` reads a review's own delivered rows against its reconciled facts. Both are checked
here on the synthetic Showdown files of `tests/test_first_place_coverage.py`, driven through the real `apply_step` and
`contest_facts.build_block`, against the QA reading of the same rosters (the independent figure). The four `run-slate`
exits are `tests/test_first_place_coverage_run_slate.py`'s.

Fixtures are written with `write_bytes`; nothing here compares a path against JSON text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs import contest_facts
from nfl_dfs import first_place_coverage as fpc
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.prior_review import _first_place_reading
from nfl_dfs.readable_review import first_place_review

from . import test_first_place_coverage as base
from . import test_qa_classic_portfolio as cl_base
from . import test_qa_showdown_portfolio as sd_base

GOOD = base.FACTS_HEADER + "700,1000,49,5\n100,200,40,5\n"
PARTIAL = base.FACTS_HEADER + "700,1000,49,5\n"
FEE = base.FACTS_HEADER + "700,1000,49,6\n100,200,40,5\n"
REFUSED = base.FACTS_HEADER + "700,1000,0,5\n100,200,40,5\n"


def _without_source(reading: dict) -> dict:
    return {key: value for key, value in reading.items() if key != "source"}


class _Inputs:
    """The synthetic Showdown slate and template, a step run over them, and the QA's reading of the same rosters."""

    def __init__(self, folder: Path, plan=base.SD_PLAN, filled=None, labels=None):
        self.folder = folder
        self.salary, self.template_path, self.export = base.sd_files(folder, plan)
        self.slate = parse_salaries(self.salary)
        self.template = parse_entries(self.template_path)
        rosters = {base.sd_entry_id(n): tuple(sd_base.ids(lineup)) for n, (_c, lineup) in enumerate(plan)}
        self.assignments = {entry: roster for entry, roster in rosters.items() if filled is None or entry in filled}
        self.step = ca.apply_step(
            mode=ca.MODE_SHOWDOWN, players=self.slate.players, entry_plan=plan_entries(self.template, self.slate),
            assignments=self.assignments, thesis_by_roster=labels, restarts=0)

    def facts(self, body: str | None) -> dict:
        path = None
        if body is not None:
            path = self.folder / "facts.csv"
            path.write_bytes(body.encode("utf-8"))
        return contest_facts.build_block(
            path, tuple((row.entry_id, row.contest_id, row.entry_fee) for row in self.template.authorizations))

    def block(self, body: str | None = None) -> dict:
        return _first_place_reading(self.step, self.step.assignments, self.slate, self.facts(body))

    def qa(self, body: str | None = None, rows=None) -> dict:
        read, _state = fpc.read_entries_file(self.export, mode=ca.MODE_SHOWDOWN)
        facts = self.facts(body)
        return fpc.reading(
            read if rows is None else rows, mode=ca.MODE_SHOWDOWN, players=fpc.players_from_salary_csv(self.salary),
            facts=None if facts["status"] == contest_facts.STATUS_NOT_SUPPLIED else facts)

    def review(self, body: str | None = None, labels=None) -> dict:
        contest_rows = [(row.entry_id, row.contest_id, self.step.assignments[row.entry_id], ca.POOL_ALL)
                        for row in self.template.authorizations if row.entry_id in self.step.assignments]
        facts = self.facts(body)
        return first_place_review(
            contest_rows, self.template.authorizations, mode=ca.MODE_SHOWDOWN, players=self.slate.players,
            labels_by_roster=labels, facts=None if facts["status"] == contest_facts.STATUS_NOT_SUPPLIED else facts)


@pytest.fixture
def inputs(tmp_path) -> _Inputs:
    return _Inputs(tmp_path)


# ------------------------------------------------------------------------------------ the facts states


@pytest.mark.parametrize(("body", "binding", "states"), [
    (None, fpc.FACTS_NOT_SUPPLIED, {"700": fpc.NO_CONTEST_FACTS, "100": fpc.NO_CONTEST_FACTS}),
    (GOOD, fpc.FACTS_BOUND, {"700": "SUPPLIED", "100": "SUPPLIED"}),
    (PARTIAL, fpc.FACTS_BOUND, {"700": "SUPPLIED", "100": "NO_FACTS_ROW"}),
    (FEE, fpc.FACTS_BOUND, {"700": "FEE_DISAGREES", "100": "SUPPLIED"}),
    (REFUSED, fpc.FACTS_NO_ROWS, {"700": fpc.NO_CONTEST_FACTS, "100": fpc.NO_CONTEST_FACTS}),
], ids=["none", "good", "partial", "fee", "refused"])
def test_the_run_block_reads_every_facts_state_as_the_qa_does(inputs, body, binding, states):
    block = inputs.block(body)
    assert block["status"] == fpc.READ and block["source"] == "CONTEST_STEP"
    assert block["facts"]["binding"] == binding
    assert {row["contest_id"]: row["facts_state"] for row in block["contests"]} == states
    assert _without_source(block) == _without_source(inputs.qa(body))
    assert block["contests"][1]["statistics"] == inputs.step.report["contests_after"]["700"]
    assert block["contests"][0]["shape"]["captain_salary"] and block["contests"][0]["no_tail_statistic"] == fpc.NO_TAIL_LINE
    if body == REFUSED:
        assert block["facts"]["facts_status"] == contest_facts.STATUS_REFUSED
    review = inputs.review(body)
    assert review["source"] == "DELIVERED_ROSTERS" and _without_source(review) == _without_source(block)


def test_a_contest_with_no_resolved_row_is_listed_and_the_facts_still_bind(tmp_path):
    """Plan decision D2: every template row is read, so a contest whose only row is unfilled keeps the facts bound."""

    unfilled = base.sd_entry_id(7)  # contest 100's one entry
    inputs = _Inputs(tmp_path, filled={base.sd_entry_id(n) for n in range(7)})
    block = inputs.block(GOOD)
    by_contest = {row["contest_id"]: row for row in block["contests"]}
    assert block["facts"]["binding"] == fpc.FACTS_BOUND
    assert by_contest["100"]["entries"] == 0 and by_contest["100"]["rows_without_roster"] == [unfilled]
    assert by_contest["100"]["facts_state"] == "SUPPLIED" and "shape" not in by_contest["100"]
    review = inputs.review(GOOD)
    assert _without_source(review) == _without_source(block)
    # Reading the resolved rows alone, the facts block's contest set no longer matches and nothing binds.
    read, _state = fpc.read_entries_file(inputs.export, mode=ca.MODE_SHOWDOWN)
    alone = inputs.qa(GOOD, rows=[row for row in read if row[0] != unfilled])
    assert alone["facts"] == {"binding": fpc.FACTS_NOT_BOUND, "detail": "CONTEST_SET", "facts_status": None}


def test_one_contest_is_read_as_one_contest(tmp_path):
    plan = [("700", lineup) for _contest, lineup in base.SD_PLAN]
    inputs = _Inputs(tmp_path, plan=plan)
    block = inputs.block()
    assert [row["contest_id"] for row in block["contests"]] == ["700"]
    assert block["contests"][0]["statistics"] == inputs.step.report["contests_after"]["700"]
    assert block["contest_count"] == 1 and block["one_entry_contest_count"] == 0


def test_the_step_labels_reach_the_block_through_the_final_rosters(tmp_path):
    rosters = [tuple(sd_base.ids(lineup)) for _contest, lineup in base.SD_PLAN]
    labels = {roster: ("SHOOTOUT" if index % 2 else "KC_WIN_BIG") for index, roster in enumerate(rosters)}
    inputs = _Inputs(tmp_path, labels=labels)
    block = inputs.block()
    after = inputs.step.report["contests_after"]["700"]
    assert after["distinct_theses"] == 2
    assert block["thesis_labels"] == "SUPPLIED" and block["contests"][1]["statistics"] == after
    assert _without_source(inputs.review(labels=labels)) == _without_source(block)
    assert inputs.review()["thesis_labels"] == "NONE"


def test_a_failed_step_and_a_raising_reading_are_named_not_raised(inputs, monkeypatch):
    failure = "CONTEST_ASSIGNMENT_STEP_FAILED:RuntimeError:injected"
    failed = ca.StepOutcome(dict(inputs.assignments), {"status": ca.STATUS_FAILED}, None, failure)
    block = _first_place_reading(failed, failed.assignments, inputs.slate, inputs.facts(GOOD))
    assert (block["status"], block["detail"], block["contests"]) == (fpc.NOT_COMPUTED, failure, [])
    monkeypatch.setattr(fpc, "players_from_slate", lambda players: (_ for _ in ()).throw(KeyError("x")))
    for reading in (inputs.block(GOOD), inputs.review(GOOD)):
        assert (reading["status"], reading["detail"], reading["contests"]) == (fpc.NOT_COMPUTED, "KeyError", [])


def test_a_section_that_cannot_render_names_itself_and_the_page_still_renders(inputs, monkeypatch):
    from nfl_dfs import readable_review

    monkeypatch.setattr(readable_review, "_first_place_sections", _raise_runtime)
    rendered = "".join(readable_review._first_place_coverage_html(inputs.review(GOOD)))
    assert rendered == ("<h2>First place, contest by contest</h2>"
                        "<p>first_place_coverage_v1: NOT_COMPUTED (RuntimeError).</p>")


def _raise_runtime(*_args, **_kwargs):
    raise RuntimeError("injected")


# ------------------------------------------------------------------------- the Classic QA's guarded print


def test_the_classic_qa_exit_code_survives_a_raising_section(tmp_path, monkeypatch):
    code, record, text = base.cl_qa(tmp_path)
    assert record["first_place_coverage"]["status"] == fpc.READ
    monkeypatch.setattr(fpc, "text_lines", lambda data: (_ for _ in ()).throw(TypeError("boom")))
    (tmp_path / "again").mkdir()
    again, broken, broken_text = base.cl_qa(tmp_path / "again")
    assert again == code
    assert broken["verdict"] == record["verdict"]
    assert (broken["first_place_coverage"]["status"], broken["first_place_coverage"]["detail"]) == (
        fpc.NOT_COMPUTED, "TypeError")
    # every line the QA printed outside the section is the same, byte for byte (the second run's folder printed as the first's)
    assert broken_text.replace(str(tmp_path / "again"), str(tmp_path)) == base.strip_classic(text)


def test_a_section_line_the_console_cannot_print_moves_no_exit_code(tmp_path, monkeypatch):
    """A console that cannot encode a name fails on `print`, not on `text_lines`: the print is inside the guard too."""

    code, record, _text = base.cl_qa(tmp_path)

    def console(*args, **kwargs):
        if args and isinstance(args[0], str) and base.CL_TITLE in args[0]:
            raise UnicodeEncodeError("cp1252", args[0], 0, 1, "character maps to <undefined>")
        print(*args, **kwargs)

    monkeypatch.setattr(cl_base.qa, "print", console, raising=False)
    (tmp_path / "again").mkdir()
    again, broken, broken_text = base.cl_qa(tmp_path / "again")
    assert again == code and broken["verdict"] == record["verdict"]
    assert (broken["first_place_coverage"]["status"], broken["first_place_coverage"]["detail"]) == (
        fpc.NOT_COMPUTED, "UnicodeEncodeError")
    assert "  VERDICT: " in broken_text
