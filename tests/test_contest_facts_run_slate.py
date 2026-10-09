"""Session 23d through `run-slate`: the label reaches every `prior_review` exit and changes nothing else.

One test group per exit (`.claude/rules/operating-path.md`): Showdown (policy and sequential), Classic C1,
Classic C2/C3. Each exit is run with no facts, with a good file, and with the files a run must survive (a
refused file, a partial one, a fee that disagrees with the entry file, a doctored artifact). The delivered
CSV is byte-identical in every case: the label is a fact about a contest and moves no lineup.

Runs are shared through module fixtures (one run per scenario), each in its own `MonkeyPatch.context()`,
because the fixtures pin the clock and, for the sequential exit, the concentration defaults.
"""

from __future__ import annotations

import json
from collections import namedtuple
from datetime import timedelta
from pathlib import Path

import pytest

from nfl_dfs import contest_facts
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.gate_registry import load_gate_registry

from .test_classic_prior_review import AS_OF
from .test_classic_prior_review import _fixture as classic_fixture
from .test_contest_assignment_classic import CONTEST_COLUMN, THREE_CONTESTS
from .test_contest_assignment_run_slate import INTERLEAVED_CONTESTS, _run as showdown_run, _sequential_exit
from .test_deadline_controller import FakeClock, _clocked
from .test_entry_groups import _edit, _policy
from .test_prior_review_profile import _attachments, _cowork_args

HEADER = "contest_id,field_size,places_paid,entry_fee\n"
LABEL = "FIRST_PLACE_OBJECTIVE"
# Showdown fixture: contests 111 and 222, fee 20; 49/1000 is under 5%, 40/200 is 20%.
SD_GOOD = HEADER + "111,1000,49,20\n222,200,40,20\n"
SD_PARTIAL = HEADER + "111,1000,49,20\n"
SD_FEE = HEADER + "111,1000,49,25\n222,200,40,20\n"
SD_BAD = HEADER + "111,1000,49,20\n222,200,0,20\n"
# Classic fixture: contests 111, 222, 333, fee 5; 111 (4.9%) and 333 (0.5%) are under 5%.
CL_GOOD = HEADER + "111,1000,49,5\n222,200,40,5\n333,2000,10,5\n"
CL_PARTIAL = HEADER + "111,1000,49,5\n"
CL_FEE = HEADER + "111,1000,49,5\n222,200,40,6\n333,2000,10,5\n"
CL_BAD = HEADER + "111,1000,49,5\n222,abc,40,5\n333,2000,10,5\n"

Result = namedtuple("Result", "code report root entries csv review html artifact")


def _facts_file(base: Path, body: str) -> Path:
    path = base / "facts" / "contest_facts.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))
    return path


def _collect(code, report, root, entries_path) -> Result:
    csv_path = report.get("bulk_entry_csv")
    artifacts = report.get("prior_review_artifacts") or {}
    review_json = artifacts.get("readable_review_json")
    review_html = artifacts.get("readable_review_html")
    facts_path = artifacts.get("contest_facts")
    return Result(
        code=code, report=report, root=root, entries=entries_path,
        csv=Path(csv_path).read_bytes() if csv_path and Path(csv_path).is_file() else None,
        review=json.loads(Path(review_json).read_text(encoding="utf-8")) if review_json else None,
        html=Path(review_html).read_text(encoding="utf-8") if review_html else None,
        artifact=json.loads(Path(facts_path).read_text(encoding="utf-8")) if facts_path else None,
    )


def _showdown(base: Path, run_id: str, facts: str | None, *, sequential: bool = False, build=None) -> Result:
    cowork = {} if facts is None else {"contest_facts_csv": str(_facts_file(base, facts))}
    with pytest.MonkeyPatch.context() as patch:
        if sequential:
            _sequential_exit(patch)
        if build is not None:
            real = contest_facts.build_block
            patch.setattr(contest_facts, "build_block", lambda path, entries: build(real(path, entries)))
        code, report, entries_path, _slate = showdown_run(
            base, patch, run_id=run_id, contests=INTERLEAVED_CONTESTS, cowork=cowork)
    return _collect(code, report, base / "outputs" / run_id, entries_path)


def _classic(base: Path, run_id: str, facts: str | None, *, policy=None, build=None) -> Result:
    from nfl_dfs import cli

    with pytest.MonkeyPatch.context() as patch:
        _clocked(patch, FakeClock())
        salary, entry, package, role, status, _ = classic_fixture(base / "fixture", entries=6)
        _edit(entry, columns={eid: {CONTEST_COLUMN: cid} for eid, cid in THREE_CONTESTS.items()})
        attachments = _attachments(base, salary, entry)
        patch.setattr(cli, "DEFAULT_RUNS_DIR", base / "runs")
        values = dict(
            label=run_id, run_id=run_id, prior_package_dir=str(package), official_status_csv=str(status),
            offensive_role_evidence_json=str(role), as_of=AS_OF.isoformat(),
            delivery_deadline_utc=(AS_OF + timedelta(minutes=6)).isoformat())
        if facts is not None:
            values["contest_facts_csv"] = str(_facts_file(base, facts))
        if policy is not None:
            slate = parse_salaries(attachments / "salary.csv")
            template = parse_entries(attachments / "entries.csv")
            values["portfolio_policy_json"] = str(policy(attachments, plan_entries(template, slate)))
        if build is not None:
            real = contest_facts.build_block
            patch.setattr(contest_facts, "build_block", lambda path, entries: build(real(path, entries)))
        code = cli.command_cowork_run(_cowork_args(base, attachments, **values))
        root = base / "outputs" / run_id
        report = json.loads((root / "cowork_run.json").read_text(encoding="utf-8"))
    return _collect(code, report, root, attachments / "entries.csv")


def _doctor_a_field_size(block):
    block["contests"][0]["field_size"] = 0
    return block


def _stale_entry(block):
    """A record built for another template: its first entry is one this entry file does not hold."""

    block["entries"][0]["entry_id"] = "999999999"
    return block


@pytest.fixture(scope="module")
def sd(tmp_path_factory):
    make = tmp_path_factory.mktemp
    return {
        "none": _showdown(make("sd_none"), "sd-none", None),
        "good": _showdown(make("sd_good"), "sd-good", SD_GOOD),
        "bad": _showdown(make("sd_bad"), "sd-bad", SD_BAD),
        "partial": _showdown(make("sd_partial"), "sd-partial", SD_PARTIAL),
        "fee": _showdown(make("sd_fee"), "sd-fee", SD_FEE),
        "doctored": _showdown(make("sd_doctored"), "sd-doctored", SD_GOOD, build=_doctor_a_field_size),
        "stale": _showdown(make("sd_stale"), "sd-stale", SD_GOOD, build=_stale_entry),
    }


@pytest.fixture(scope="module")
def sq(tmp_path_factory):
    make = tmp_path_factory.mktemp
    return {
        "none": _showdown(make("sq_none"), "sq-none", None, sequential=True),
        "good": _showdown(make("sq_good"), "sq-good", SD_GOOD, sequential=True),
        "bad": _showdown(make("sq_bad"), "sq-bad", SD_BAD, sequential=True),
    }


@pytest.fixture(scope="module")
def c1(tmp_path_factory):
    make = tmp_path_factory.mktemp
    return {
        "none": _classic(make("c1_none"), "c1-none", None),
        "good": _classic(make("c1_good"), "c1-good", CL_GOOD),
        "bad": _classic(make("c1_bad"), "c1-bad", CL_BAD),
    }


@pytest.fixture(scope="module")
def c3(tmp_path_factory):
    make = tmp_path_factory.mktemp
    return {
        "none": _classic(make("c3_none"), "c3-none", None, policy=_policy),
        "good": _classic(make("c3_good"), "c3-good", CL_GOOD, policy=_policy),
        "bad": _classic(make("c3_bad"), "c3-bad", CL_BAD, policy=_policy),
        "partial": _classic(make("c3_partial"), "c3-partial", CL_PARTIAL, policy=_policy),
        "fee": _classic(make("c3_fee"), "c3-fee", CL_FEE, policy=_policy),
        "doctored": _classic(make("c3_doctored"), "c3-doctored", CL_GOOD, policy=_policy, build=_doctor_a_field_size),
        "stale": _classic(make("c3_stale"), "c3-stale", CL_GOOD, policy=_policy, build=_stale_entry),
    }


# ------------------------------------------------------------------------------- shared checks


def _block(result: Result) -> dict:
    return result.report["prior_review_reports"]["contest_facts"]


def _limitations(result: Result) -> dict[str, str]:
    return {item["code"]: item["class"] for item in result.report["release_truths"]["delivery_limitations"]}


def _blocker_heads(result: Result) -> list[str]:
    return [str(item).split(":", 1)[0] for item in result.report["blockers"]]


def _labels(block: dict) -> dict[str, str | None]:
    return {row["entry_id"]: row["label"] for row in block["entries"]}


def _assert_the_run_is_otherwise_unchanged(with_facts: Result, without: Result) -> None:
    assert with_facts.code == without.code
    assert with_facts.csv is not None and with_facts.csv == without.csv, "the label moved a byte of the file"
    assert with_facts.report["RELEASE_DECISION"] == without.report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert with_facts.report["MODEL_STATUS"] == without.report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert with_facts.report["DELIVERY_STATE"] == without.report["DELIVERY_STATE"]


def _assert_applied(result: Result, none: Result, expected_labelled: int) -> None:
    block = _block(result)
    assert block["status"] == "APPLIED", block
    assert block["entries_labelled"] == expected_labelled
    assert result.artifact == block, "the hash-bound artifact is the block"
    assert contest_facts.canonical_bytes(block) == Path(result.report["prior_review_artifacts"]["contest_facts"]).read_bytes()
    assert result.report["prior_review_hashes"]["contest_facts"] == contest_facts.sha256_hex(
        contest_facts.canonical_bytes(block))
    assert block["facts_sha256"] in result.report["input_hashes"].values()
    assert not any(head.startswith("CONTEST_FACTS_") for head in _blocker_heads(result))
    # certification-only blockers are untouched by a facts file
    assert any(str(item).startswith("CONTEST_PAYOUT_REQUIRED:") for item in result.report["blockers"]) == any(
        str(item).startswith("CONTEST_PAYOUT_REQUIRED:") for item in none.report["blockers"])
    _assert_the_run_is_otherwise_unchanged(result, none)


def _assert_no_facts_run(none: Result) -> None:
    block = _block(none)
    assert block["status"] == "NOT_SUPPLIED" and block["entries_labelled"] == 0
    assert "contest_facts" not in none.report["prior_review_artifacts"]
    assert "contest_facts" not in none.report["prior_review_hashes"]
    assert not any(head.startswith("CONTEST_FACTS_") for head in _blocker_heads(none))
    if none.review is not None:
        assert "contest_facts" not in none.review, "a run without facts writes the review it always wrote"
        assert "Contest facts" not in none.html and LABEL not in none.html


def _assert_refused(result: Result, none: Result) -> None:
    block = _block(result)
    assert block["status"] == "REFUSED" and block["entries_labelled"] == 0
    assert block["problems"], "a refused file names every problem"
    assert all(problem.startswith("CONTEST_FACTS_") for problem in block["problems"])
    assert "CONTEST_FACTS_REFUSED" in _blocker_heads(result)
    assert _limitations(result)["CONTEST_FACTS_REFUSED"] == "P"
    _assert_the_run_is_otherwise_unchanged(result, none)
    if result.review is not None:
        assert result.review["contest_facts"]["status"] == "REFUSED"
        assert "Contest facts" in result.html and "REFUSED" in result.html


def _assert_review_shows_the_labels(result: Result, expected: dict[str, str | None]) -> None:
    review = result.review["contest_facts"]
    assert review == _block(result)
    assert {row["entry_id"]: row["label"] for row in review["entries"]} == expected
    assert "Contest facts" in result.html and LABEL in result.html
    # `THAT_ANY_LINEUP_SUITS_A_CONTEST` is a token only this section prints (the contest-assignment text says "does not establish" too)
    assert "49/1000" in result.html and "THAT_ANY_LINEUP_SUITS_A_CONTEST" in result.html


# ------------------------------------------------------------------------------- Showdown, policy


def test_showdown_policy_without_facts_writes_the_review_it_always_wrote(sd):
    _assert_no_facts_run(sd["none"])


def test_showdown_policy_labels_each_entry_from_the_supplied_numbers_and_moves_nothing(sd):
    good = sd["good"]
    _assert_applied(good, sd["none"], expected_labelled=3)
    labels = _labels(_block(good))
    in_111 = {row["entry_id"] for row in _block(good)["entries"] if row["contest_id"] == "111"}
    assert {entry for entry, label in labels.items() if label == LABEL} == in_111
    assert good.review is not None
    _assert_review_shows_the_labels(good, labels)


def test_showdown_policy_survives_a_refused_a_partial_and_a_disagreeing_file(sd):
    _assert_refused(sd["bad"], sd["none"])
    partial = sd["partial"]
    assert _block(partial)["status"] == "PARTIAL" and _block(partial)["contests_without_row"] == ["222"]
    assert "CONTEST_FACTS_INCOMPLETE" in _blocker_heads(partial)
    assert _limitations(partial)["CONTEST_FACTS_INCOMPLETE"] == "P"
    _assert_the_run_is_otherwise_unchanged(partial, sd["none"])
    fee = sd["fee"]
    assert _block(fee)["contests_fee_disagree"] == ["111"] and _block(fee)["entries_labelled"] == 0
    assert "CONTEST_FACTS_FEE_DISAGREES_WITH_ENTRIES" in _blocker_heads(fee)
    _assert_the_run_is_otherwise_unchanged(fee, sd["none"])


def test_showdown_policy_keeps_the_file_when_the_review_cannot_reconcile_the_block(sd):
    doctored = sd["doctored"]
    assert doctored.csv is not None and doctored.csv == sd["none"].csv
    text = json.dumps(doctored.report["blockers"])
    assert "CONTEST_FACTS_REVIEW_MISMATCH" in text
    assert load_gate_registry().codes["CONTEST_FACTS_REVIEW_MISMATCH"] == "presentation"
    assert doctored.report["DELIVERY_STATE"] == sd["none"].report["DELIVERY_STATE"]
    assert doctored.report["latest_deliverable"]["path"].endswith(".csv")
    # a record built for another template is the same: named, the file kept, nothing withheld
    stale = sd["stale"]
    assert stale.csv == sd["none"].csv and "CONTEST_FACTS_REVIEW_MISMATCH:entries" in json.dumps(stale.report["blockers"])
    assert stale.report["DELIVERY_STATE"] == sd["none"].report["DELIVERY_STATE"]


# --------------------------------------------------------------------------- Showdown, sequential


def test_showdown_sequential_carries_the_label_and_survives_a_refused_file(sq):
    _assert_no_facts_run(sq["none"])
    _assert_applied(sq["good"], sq["none"], expected_labelled=3)
    _assert_review_shows_the_labels(sq["good"], _labels(_block(sq["good"])))
    _assert_refused(sq["bad"], sq["none"])


# ----------------------------------------------------------------------------------- Classic C1


def test_classic_c1_carries_the_block_in_its_bound_artifact_and_the_run_result(c1):
    _assert_no_facts_run(c1["none"])
    good = c1["good"]
    assert good.review is None, "C1 has no readable review; its record is the run result and the artifact"
    _assert_applied(good, c1["none"], expected_labelled=4)
    labelled_contests = {row["contest_id"] for row in _block(good)["contests"] if row["label"] == LABEL}
    assert labelled_contests == {"111", "333"}
    _assert_refused(c1["bad"], c1["none"])


# --------------------------------------------------------------------------------- Classic C2/C3


def test_classic_c3_without_facts_writes_the_review_it_always_wrote(c3):
    assert c3["none"].review is not None
    _assert_no_facts_run(c3["none"])


def test_classic_c3_labels_every_entry_in_its_review_and_moves_nothing(c3):
    good = c3["good"]
    _assert_applied(good, c3["none"], expected_labelled=4)
    _assert_review_shows_the_labels(good, _labels(_block(good)))
    # the C3 hash checkpoint never tracks the label artifact: a label can never stop the export
    assert "contest_facts" not in json.dumps(good.review.get("hash_checkpoints", {}))


def test_classic_c3_survives_a_refused_a_partial_and_a_disagreeing_file(c3):
    _assert_refused(c3["bad"], c3["none"])
    partial = c3["partial"]
    assert _block(partial)["status"] == "PARTIAL" and _block(partial)["contests_without_row"] == ["222", "333"]
    assert "CONTEST_FACTS_INCOMPLETE" in _blocker_heads(partial)
    _assert_the_run_is_otherwise_unchanged(partial, c3["none"])
    fee = c3["fee"]
    assert _block(fee)["contests_fee_disagree"] == ["222"]
    assert {row["contest_id"] for row in _block(fee)["contests"] if row["label"] == LABEL} == {"111", "333"}
    assert "CONTEST_FACTS_FEE_DISAGREES_WITH_ENTRIES" in _blocker_heads(fee)
    _assert_the_run_is_otherwise_unchanged(fee, c3["none"])


def test_classic_c3_keeps_the_export_when_the_review_cannot_reconcile_the_block(c3):
    doctored = c3["doctored"]
    assert doctored.csv is not None and doctored.csv == c3["none"].csv
    assert "CONTEST_FACTS_REVIEW_MISMATCH" in json.dumps(doctored.report["blockers"])
    assert doctored.report["DELIVERY_STATE"] == c3["none"].report["DELIVERY_STATE"]
    stale = c3["stale"]
    assert stale.csv == c3["none"].csv and "CONTEST_FACTS_REVIEW_MISMATCH:entries" in json.dumps(stale.report["blockers"])
    assert stale.report["DELIVERY_STATE"] == c3["none"].report["DELIVERY_STATE"]


# ------------------------------------------------------ the snapshot and the hash of the file itself


def test_the_facts_file_is_snapshotted_under_the_run_and_its_hash_is_the_blocks(sd):
    good = sd["good"]
    digest = contest_facts.sha256_hex(SD_GOOD.encode("utf-8"))
    assert _block(good)["facts_sha256"] == digest
    request = json.loads((good.root.parent.parent / "runs" / "sd-good" / "run_request.json").read_text("utf-8"))
    assert request["schema_version"] == "nfl_cowork_run_request_v5"
    snapshot = Path(request["contest_facts_csv"])
    # both sides resolved: the request holds a resolved path and a runner's temp root may be a short (8.3) name
    assert snapshot.parent.resolve() == (good.root.parent.parent / "runs" / "sd-good" / "inputs").resolve()
    assert snapshot.name == f"{digest}.csv"
    assert snapshot.read_bytes() == SD_GOOD.encode("utf-8")
    assert digest in good.report["input_hashes"].values()
    none_request = json.loads(
        (sd["none"].root.parent.parent / "runs" / "sd-none" / "run_request.json").read_text("utf-8"))
    assert none_request["contest_facts_csv"] is None


# --------------------------------------------- the card's acceptance, on a DEN@KC-shaped template

# SYNTHETIC. The contest IDs, entries per contest and the words "satellite" / "single entry" come from a
# schema-level read of the operator's local DEN@KC entries file (2026-09-14, not in the repository); the
# field sizes and places paid below are written for this test and are NOT DraftKings's numbers for those
# contests, which the repository does not hold.
DENKC_CONTESTS = (
    # contest id, entries, fee, name, synthetic field size, synthetic places paid, under 5%?
    ("195521607", 2, "$0.25", "NFL $1K Showdown Satellite", 400, 160, False),         # 40%
    ("195526229", 1, "$0.50", "NFL $5K Showdown", 5000, 200, True),                   # 4%
    ("195526255", 1, "$1", "NFL $10K Showdown", 2000, 100, False),                    # exactly 5%
    ("195526256", 2, "$0.25", "NFL $2K Showdown", 10000, 499, True),                  # 4.99%
    ("195526257", 2, "$0.10", "NFL $1K Showdown", 8000, 401, False),                  # 5.0125%
    ("195526271", 1, "$1", "NFL $10K Showdown Single Entry", 1000, 10, True),         # 1%
    ("195663904", 7, "$0.10", "NFL $500 Showdown Satellite", 300, 150, False),        # 50%
    ("195665148", 2, "$0.25", "NFL $1K Showdown Satellite", 600, 20, True),           # 3.3%, and named a satellite
)
ENTRY_HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions"


def _denkc_entries(tmp_path: Path, *, rotate_names: int = 0) -> Path:
    names = [row[3] for row in DENKC_CONTESTS]
    names = names[rotate_names:] + names[:rotate_names]
    lines = [ENTRY_HEADER]
    entry_id = 5_000_000_000
    for (contest_id, count, fee, _name, _field, _paid, _under), name in zip(DENKC_CONTESTS, names):
        for _ in range(count):
            entry_id += 1
            lines.append(f"{entry_id},{name},{contest_id},{fee},,,,,,,,")
    path = tmp_path / f"denkc_{rotate_names}.csv"
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def _denkc_facts(tmp_path: Path, *, bad_row: bool = False) -> Path:
    rows = [HEADER.strip()]
    for contest_id, _count, fee, _name, field, paid, _under in DENKC_CONTESTS:
        if bad_row and contest_id == "195526256":
            paid = 0
        rows.append(f"{contest_id},{field},{paid},{fee.lstrip('$')}")
    path = tmp_path / ("denkc_facts_bad.csv" if bad_row else "denkc_facts.csv")
    path.write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
    return path


def _refs(entries_path: Path):
    return tuple((a.entry_id, a.contest_id, a.entry_fee) for a in parse_entries(entries_path).authorizations)


def test_denkc_shaped_entries_under_five_percent_are_labelled_from_supplied_numbers_only(tmp_path):
    entries = _denkc_entries(tmp_path)
    refs = _refs(entries)
    assert len(refs) == 18 and len({contest for _entry, contest, _fee in refs}) == 8
    block = contest_facts.build_block(_denkc_facts(tmp_path), refs)
    assert block["status"] == "APPLIED" and block["problems"] == []
    labelled = {row["contest_id"] for row in block["contests"] if row["label"] == LABEL}
    assert labelled == {contest for contest, _c, _f, _n, _fi, _p, under in DENKC_CONTESTS if under}
    assert block["entries_labelled"] == 6 and len(block["entries"]) == 18
    # a "satellite" that pays 3.3% is labelled and a contest paying exactly 5% is not: the numbers decide
    by_contest = {row["contest_id"]: row for row in block["contests"]}
    assert by_contest["195665148"]["label"] == LABEL and by_contest["195526255"]["label"] is None
    assert by_contest["195526256"]["paid_fraction"] == "499/10000"
    # the same numbers over entries whose contest names are shuffled give the same block byte for byte
    shuffled = contest_facts.build_block(_denkc_facts(tmp_path), _refs(_denkc_entries(tmp_path, rotate_names=3)))
    assert contest_facts.canonical_bytes(shuffled) == contest_facts.canonical_bytes(block)
    assert parse_entries(_denkc_entries(tmp_path, rotate_names=3)).authorizations[0].contest_name != \
        parse_entries(entries).authorizations[0].contest_name


def test_denkc_shaped_file_with_a_bad_row_is_refused_by_name_and_labels_nothing(tmp_path):
    block = contest_facts.build_block(_denkc_facts(tmp_path, bad_row=True), _refs(_denkc_entries(tmp_path)))
    assert block["status"] == "REFUSED"
    assert block["problems"] == ["CONTEST_FACTS_PLACES_PAID_NOT_POSITIVE:row=5"]
    assert block["entries_labelled"] == 0 and block["entries"] == []
    assert contest_facts.limitations(block)[0].startswith(
        "CONTEST_FACTS_REFUSED:CONTEST_FACTS_PLACES_PAID_NOT_POSITIVE:1")
