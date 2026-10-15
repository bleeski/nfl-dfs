"""Session 75: both QA scripts, run on a `run-slate` run's own delivered file, equal that run's `contests_after`.

The card's equality clause on real runs (`tests/test_first_place_coverage.py` holds the synthetic one):

- Showdown on the engine's default policy, which carries no thesis labels;
- Showdown on a v4 portfolio of theses, read with `--policy` and `--claim`, whose labels the contest step scored with;
- Classic C3, against `selection/contest_assignment.json`, the artifact the card names.

Session 75b adds the run's own block (`prior_review_reports.first_place_coverage`) on every exit and the readable review's
key and section on Showdown and C3, below the Session 75 tests.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from nfl_dfs import contest_assignment as ca
from nfl_dfs import first_place_coverage as fpc
from nfl_dfs.dk import parse_entries
from nfl_dfs.readable_review import _render_html

from . import test_qa_classic_portfolio as cl_base
from . import test_qa_showdown_portfolio as sd_base
from .test_contest_assignment_classic import ENTRIES, _classic_run
from .test_contest_facts_run_slate import CL_GOOD, SD_GOOD, _classic, _showdown
from .test_entry_groups import _named, _policy, _salary_top
from .test_readable_review_theses import _controls, _finished
from .test_showdown_thesis_check import claim_path, policy_path


def _stdout(call) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = call()
    return code, buffer.getvalue()


def _delivered(report) -> Path:
    return Path(report["latest_deliverable"]["path"])


def _statistics(reading) -> dict[str, dict]:
    return {row["contest_id"]: row["statistics"] for row in reading["contests"] if row["entries"] >= 2}


def _showdown_reading(salary: Path, entries: Path, delivered: Path, *extra: str) -> dict:
    _code, text = _stdout(lambda: sd_base.qa.main(
        ["--salaries", str(salary), "--template", str(entries), "--export", str(delivered), *extra]))
    return json.loads(text)["first_place_coverage"]


@pytest.fixture(scope="module")
def sd_default(tmp_path_factory):
    return _showdown(tmp_path_factory.mktemp("fp_sd"), "fp-sd", None)


@pytest.fixture(scope="module")
def sd_theses(tmp_path_factory):
    return _finished(tmp_path_factory, "fp-th", policy_controls=_controls(4))


@pytest.fixture(scope="module")
def c3_run(tmp_path_factory):
    return _classic(tmp_path_factory.mktemp("fp_c3"), "fp-c3", None, policy=_policy)


def test_the_showdown_qa_on_a_runs_file_equals_its_contests_after(sd_default):
    assert sd_default.code == 0, sd_default.report["blockers"]
    report = sd_default.report
    reading = _showdown_reading(sd_default.entries.parent / "salary.csv", sd_default.entries, _delivered(report))
    after = report["prior_review_reports"]["contest_assignment"]["contests_after"]
    assert after and _statistics(reading) == after
    assert reading["thesis_labels"] == "NONE" and reading["status"] == fpc.READ


def test_the_showdown_qa_with_the_claim_equals_a_portfolio_of_theses_contests_after(sd_theses):
    run = sd_theses
    after = run.report["prior_review_reports"]["contest_assignment"]["contests_after"]
    assert any(stats["distinct_theses"] for stats in after.values()), "the run's step scored with thesis labels"
    labelled = _showdown_reading(run.salary, run.entries, _delivered(run.report),
                                 "--policy", str(policy_path(run)), "--claim", str(claim_path(run)))
    assert labelled["thesis_labels"] == "SUPPLIED"
    assert _statistics(labelled) == after
    plain = _showdown_reading(run.salary, run.entries, _delivered(run.report))
    assert plain["thesis_labels"] == "NONE"
    assert all(stats["distinct_theses"] == 0 for stats in _statistics(plain).values())


def test_the_classic_qa_on_a_c3_file_equals_contest_assignment_json(c3_run, tmp_path):
    report = c3_run.report
    assert report["latest_deliverable"]["producer"] != "run-slate:baseline", report["blockers"]
    artifact = json.loads(Path(report["prior_review_artifacts"]["contest_assignment"]).read_text(encoding="utf-8"))
    delivered = _delivered(report)
    rosters = {entry.entry_id: [fpc.cell_dk_id(cell) for cell in entry.existing_cells]
               for entry in parse_entries(delivered).authorizations if all(entry.existing_cells)}
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_bytes(json.dumps({"lineups": [], "assignments_by_entry_id": rosters}).encode("utf-8"))
    record = tmp_path / "qa.json"
    _code, _text = _stdout(lambda: cl_base.qa.main([
        "--portfolio", str(portfolio), "--salaries", str(c3_run.entries.parent / "salary.csv"),
        "--template", str(c3_run.entries), "--export", str(delivered), "--json", str(record)]))
    reading = json.loads(record.read_text(encoding="utf-8"))["first_place_coverage"]
    assert artifact["contests_after"] and _statistics(reading) == artifact["contests_after"]
    assert reading["source"] == "EXPORT" and reading["thesis_labels"] == "NONE"


# =========================================================== Session 75b: the run's own block and the reviews

HEADING = "<h2>First place, contest by contest</h2>"
TRUTHS = ("FILE_VALID", "EVIDENCE_STATE", "MODEL_STATUS", "RELEASE_DECISION", "DELIVERY_STATE")
HOSTILE = "<script>alert(1)</script> =cmd|' /c calc'!A1"
ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt; =cmd|&#x27; /c calc&#x27;!A1"
ISO_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
# The review keys before Session 75b (`tests/test_readable_review_theses.py`'s `EXISTING_KEYS` as it stood at `0049769`),
# written out here so the guarantee does not read the edited pin.
OLD_SHOWDOWN_KEYS = {
    "schema_version", "status", "truths", "warning", "next_action", "blockers", "reconciliation", "entries",
    "exposure", "unbound_rows", "contest_assignment", "pool_coverage", "evidence_observations", "artifacts", "hashes",
}
OLD_C3_KEYS = {
    "artifacts", "blockers", "construction_judgment", "contest_assignment", "entries", "evidence_observations",
    "exposure", "hash_checkpoints", "hashes", "judgment_pass", "limitations", "mode", "next_action", "pool_coverage",
    "portfolio_scope", "reconciliation", "schema_version", "status", "truths", "unbound_rows", "warning",
}
# C1 with one row prefilled and locked (late swap's `Name (ID) (LOCKED)` cells), and a contest of one entry.
SHAPES = {ENTRIES[0]: "111", ENTRIES[1]: "111", ENTRIES[2]: "111", ENTRIES[3]: "222", ENTRIES[4]: "222",
          ENTRIES[5]: "333"}


def _raise_injected(*_args, **_kwargs):
    raise RuntimeError("injected")


@pytest.fixture(scope="module")
def runs(tmp_path_factory, sd_default, c3_run):
    make = tmp_path_factory.mktemp
    return {
        "sd-none": sd_default,
        "sd-good": _showdown(make("fp_sdg"), "fp-sdg", SD_GOOD),
        "sq-none": _showdown(make("fp_sqn"), "fp-sqn", None, sequential=True),
        "sq-good": _showdown(make("fp_sqg"), "fp-sqg", SD_GOOD, sequential=True),
        "c1-none": _classic(make("fp_c1n"), "fp-c1n", None),
        "c1-good": _classic(make("fp_c1g"), "fp-c1g", CL_GOOD),
        "c3-none": c3_run,
        "c3-good": _classic(make("fp_c3g"), "fp-c3g", CL_GOOD, policy=_policy),
    }


@pytest.fixture(scope="module")
def raised(tmp_path_factory):
    """The reading itself raises, in the run and in the review."""

    make = tmp_path_factory.mktemp
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(fpc, "reading", _raise_injected)
        return {"sd": _showdown(make("fp_sdr"), "fp-sdr", None),
                "c3": _classic(make("fp_c3r"), "fp-c3r", None, policy=_policy)}


@pytest.fixture(scope="module")
def failed(tmp_path_factory):
    """The contest step fails, so it has no claim."""

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ca, "diversify", _raise_injected)
        return _classic(tmp_path_factory.mktemp("fp_c1f"), "fp-c1f", None)


@pytest.fixture(scope="module")
def shapes(tmp_path_factory):
    def locked(slate):
        return {ENTRIES[1]: [f"{cell} (LOCKED)" for cell in _named(slate, _salary_top(slate, 1)[0])]}

    with pytest.MonkeyPatch.context() as patch:
        code, report, entries, _root = _classic_run(
            tmp_path_factory.mktemp("fp_c1s"), patch, run_id="fp-c1s", contests=SHAPES, cells=locked)
    return code, report, entries


def _block(report) -> dict:
    return report["prior_review_reports"]["first_place_coverage"]


def _step(report) -> dict:
    return report["prior_review_reports"]["contest_assignment"]


def _without_source(reading: dict) -> dict:
    return {key: value for key, value in reading.items() if key != "source"}


def _section(html: str) -> str:
    return html.split(HEADING, 1)[1].split("<h2>", 1)[0]


def _strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


@pytest.mark.parametrize("exit_", ["sd", "sq", "c1", "c3"])
def test_the_block_equals_contests_after_on_every_exit(runs, exit_):
    for facts in ("none", "good"):
        run = runs[f"{exit_}-{facts}"]
        assert run.code == 0, run.report["blockers"]
        step = _step(run.report)
        # a step that moved nothing could not tell the final assignment from the solver's order
        assert step["moved_rows"] > 0, step
        after = step["contests_after"]
        if exit_ == "c3":
            after = json.loads(Path(run.report["prior_review_artifacts"]["contest_assignment"]).read_text(
                encoding="utf-8"))["contests_after"]
        block = _block(run.report)
        assert block["status"] == fpc.READ and block["source"] == "CONTEST_STEP", block
        assert block["first_place_coverage_version"] == fpc.FIRST_PLACE_COVERAGE_VERSION
        assert after and _statistics(block) == after
        states = {row["facts_state"] for row in block["contests"]}
        if facts == "good":
            assert block["facts"]["binding"] == fpc.FACTS_BOUND and states == {"SUPPLIED"}
            assert all(row["field_size"] and row["places_paid"] for row in block["contests"])
        else:
            assert block["facts"]["binding"] == fpc.FACTS_NOT_SUPPLIED and states == {fpc.NO_CONTEST_FACTS}


def test_a_portfolio_of_theses_block_carries_the_step_labels(sd_theses):
    after = _step(sd_theses.report)["contests_after"]
    assert any(stats["distinct_theses"] for stats in after.values()), "the step scored with thesis labels"
    block = _block(sd_theses.report)
    assert block["thesis_labels"] == "SUPPLIED" and _statistics(block) == after
    assert _without_source(sd_theses.readable()["first_place_coverage"]) == _without_source(block)


def test_c1_carries_the_block_in_its_run_result_and_writes_no_review(runs):
    for facts in ("none", "good"):
        run = runs[f"c1-{facts}"]
        assert _block(run.report)["status"] == fpc.READ
        assert run.review is None and run.html is None
        assert not list(run.root.rglob("prior_only_readable_review.*"))


@pytest.mark.parametrize("exit_", ["sd", "sq", "c3"])
def test_the_reviews_carry_the_key_and_the_section(runs, exit_):
    for facts in ("none", "good"):
        run = runs[f"{exit_}-{facts}"]
        reading = run.review["first_place_coverage"]
        assert reading["source"] == "DELIVERED_ROSTERS"
        assert _without_source(reading) == _without_source(_block(run.report))
        assert run.html.count(HEADING) == 1
        section = _section(run.html)
        assert reading["contests"], "the fixture holds contests"
        if facts == "none":
            assert "Contest facts" not in run.html and "FIRST_PLACE_OBJECTIVE" not in run.html
            for row in reading["contests"]:
                assert f'<tr><td>{row["contest_id"]}</td><td>{row["entries"]}</td><td>NO_CONTEST_FACTS</td>' in section
        else:
            assert "SUPPLIED (field 1000, paid 49, 49/1000, FIRST_PLACE_OBJECTIVE)" in section
        assert "a reading, never a gate" in section and fpc.READ_AS in section
        assert all(token in section for token in fpc.DOES_NOT_ESTABLISH)


def test_the_review_key_set_is_the_old_one_plus_the_reading(runs, sd_theses):
    new = {"first_place_coverage"}
    assert set(runs["sd-none"].review) == OLD_SHOWDOWN_KEYS | new
    assert set(runs["sq-good"].review) == OLD_SHOWDOWN_KEYS | new | {"contest_facts"}
    assert set(sd_theses.readable()) == OLD_SHOWDOWN_KEYS | new | {"theses"}
    assert set(runs["c3-none"].review) == OLD_C3_KEYS | new
    assert set(runs["c3-good"].review) == OLD_C3_KEYS | new | {"contest_facts"}


@pytest.mark.parametrize("exit_", ["sd", "c3"])
def test_a_hostile_person_renders_escaped_in_both_reviews(runs, exit_):
    data = copy.deepcopy(runs[f"{exit_}-none"].review)
    reading = data["first_place_coverage"]
    first = reading["contests"][0]
    first["contest_id"] = HOSTILE
    first["repeated_key_people"] = [{"person": HOSTILE, "entries": 2}]
    first["rows_without_roster"] = [HOSTILE]
    shape = ({"captain": HOSTILE, "captain_salary": HOSTILE, "salary_left": HOSTILE} if exit_ == "sd" else
             {"quarterback": HOSTILE, "stack_team": HOSTILE, "stack_depth": 2, "bring_back": 1, "salary_left": HOSTILE})
    reading["contests"].append({"contest_id": "9", "entries": 1, "facts_state": HOSTILE, "shape": shape,
                                "no_tail_statistic": fpc.NO_TAIL_LINE})
    html = _render_html(data, data_sha256="0" * 64).decode("utf-8")
    section = _section(html)
    assert HOSTILE not in html and "<script>" not in section
    assert section.count(ESCAPED) >= 5
    # each value lands in its own cell: the repeated person with the count, the one-entry shape, the no-tail line
    assert f"<td>{ESCAPED} x2</td>" in section
    assert (f"<td>Captain {ESCAPED} at {ESCAPED}, salary left {ESCAPED}</td>" if exit_ == "sd" else
            f"<td>QB {ESCAPED}, stack {ESCAPED} x2, bring-back 1, salary left {ESCAPED}</td>") in section
    assert f"no pair to compare: {fpc.NO_TAIL_LINE}." in section
    reading.update({"status": fpc.NOT_COMPUTED, "detail": HOSTILE})
    html = _render_html(data, data_sha256="0" * 64).decode("utf-8")
    assert HOSTILE not in html and ESCAPED in _section(html)


@pytest.mark.parametrize("exit_", ["sd", "c3"])
def test_the_section_renders_any_block_without_raising(runs, exit_):
    malformed = {"status": fpc.READ, "facts": 7, "does_not_establish": 3,
                 "contests": [{"shape": "x", "statistics": 3, "repeated_key_people": [5]}, 4]}
    for value in (None, {}, malformed):
        data = copy.deepcopy(runs[f"{exit_}-none"].review)
        data["first_place_coverage"] = value
        html = _render_html(data, data_sha256="0" * 64).decode("utf-8")
        assert (HEADING in html) == (value is not None)


def test_a_failed_step_reads_not_computed_and_still_delivers(failed, runs):
    report, normal = failed.report, runs["c1-none"].report
    assert failed.code == 0 and _step(report)["status"] == "FAILED"
    block = _block(report)
    assert block["status"] == fpc.NOT_COMPUTED
    assert block["detail"] == "CONTEST_ASSIGNMENT_STEP_FAILED:RuntimeError:injected" == _step(report)["error"]
    assert block["contests"] == [] and block["source"] == "CONTEST_STEP"
    assert {key: report[key] for key in TRUTHS} == {key: normal[key] for key in TRUTHS}
    assert failed.csv is not None and report["latest_deliverable"]["producer"] == normal["latest_deliverable"]["producer"]


@pytest.mark.parametrize("exit_", ["sd", "c3"])
def test_a_raising_reading_moves_no_byte_and_no_truth(raised, runs, exit_):
    run, normal = raised[exit_], runs[f"{exit_}-none"]
    assert run.code == normal.code == 0
    assert run.csv is not None and hashlib.sha256(run.csv).hexdigest() == hashlib.sha256(normal.csv).hexdigest()
    assert {key: run.report[key] for key in TRUTHS} == {key: normal.report[key] for key in TRUTHS}
    heads = lambda report: sorted(str(item).split(":", 1)[0] for item in report["blockers"])  # noqa: E731
    assert heads(run.report) == heads(normal.report)
    for reading in (_block(run.report), run.review["first_place_coverage"]):
        assert (reading["status"], reading["detail"], reading["contests"]) == (fpc.NOT_COMPUTED, "RuntimeError", [])
    assert f"{fpc.NOT_COMPUTED}: RuntimeError" in _section(run.html)


def test_the_block_holds_no_path_and_no_clock(runs, raised, failed, shapes):
    for result in (*runs.values(), *raised.values(), failed):
        base = result.root.parent.parent
        markers = (str(base), str(base.resolve()), base.name)
        for text in _strings(_block(result.report)):
            assert not any(marker in text for marker in markers), text
            assert not ISO_CLOCK.search(text), text
    _code, report, entries = shapes
    base = entries.parent.parent
    for text in _strings(_block(report)):
        assert str(base) not in text and str(base.resolve()) not in text and not ISO_CLOCK.search(text), text


def test_a_locked_prefilled_row_differs_as_the_contract_says(shapes):
    code, report, entries = shapes
    assert code == 0, report["blockers"]
    locked = ENTRIES[1]
    assert locked in _step(report)["unscored_entry_ids"], "the run does not score a (LOCKED) row"
    block = _block(report)
    assert _statistics(block) == _step(report)["contests_after"]
    ours = {row["contest_id"]: row for row in block["contests"]}
    assert ours["111"]["rows_without_roster"] == [locked] and ours["111"]["entries"] == 2
    # The QA reading of the delivered file scores every complete roster of known IDs, the locked row among them.
    delivered = Path(report["latest_deliverable"]["path"])
    rows, state = fpc.read_entries_file(delivered, mode=ca.MODE_CLASSIC)
    assert state == fpc.READ
    theirs = {row["contest_id"]: row for row in fpc.reading(
        rows, mode=ca.MODE_CLASSIC, players=fpc.players_from_salary_csv(entries.parent / "salary.csv"))["contests"]}
    assert locked in theirs["111"]["entry_ids"] and theirs["111"]["entries"] == 3
    assert theirs["111"]["rows_without_roster"] == []
    assert theirs["222"] == ours["222"] and theirs["333"] == ours["333"]
    # The contest of one entry reads its lineup's shape on the run path.
    one = ours["333"]
    assert one["entries"] == 1 and "statistics" not in one and one["no_tail_statistic"] == fpc.NO_TAIL_LINE
    assert one["shape"]["quarterback"] and one["shape"]["salary_left"] >= 0
