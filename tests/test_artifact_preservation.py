"""Session 05: a validated review CSV survives a later presentation failure (R28).

The card's acceptance, both modes: a readable-review failure is classified code
by code through the gate registry. A roster, Entry ID or byte discrepancy (`V`),
or one the registry cannot classify, still withholds the CSV; any other keeps it
listed with a presentation limitation. C3 keeps its export and audit and
removes only the JSON and HTML. Nothing advertises a kept CSV until
`delivery.publish` has revalidated it, and the outer exception handler names a
revalidated deliverable and never deletes it.

The corruption cases below are the other half: wrong bytes or a wrong Entry ID
mapping are withheld however the display failure is labelled. Classic C1/C2
write no upload-shaped CSV, so their exit has nothing to preserve and reports
`NO_DELIVERABLE` with `PROFILE_WRITES_NO_ENTRY_FILE`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import delivery
from nfl_dfs.baseline import run_baseline
from nfl_dfs.byte_lines import csv_field_spans, split_byte_lines, split_line_ending
from nfl_dfs.classic_review import (
    ClassicReviewError,
    ClassicReviewPresentationError,
    create_classic_review_package,
)
from nfl_dfs.contracts import (
    CertificationBasis,
    DeliveryState,
    GateClass,
    ModelStatus,
    ReleaseEvidenceState,
)
from nfl_dfs.dk import parse_entries
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import sha256_bytes, sha256_file
from nfl_dfs.readable_review import ReadableReviewError
from nfl_dfs.release import derive_delivery_state, derive_release_policy, release_truths_v2

from .test_baseline import CLASSIC_SALARY, classic_template
from .test_classic_review_c3 import _assert_no_new_output, _direct_args, c3_seed  # noqa: F401
from .test_prior_review_profile import _attachments, _cowork_args, _prepared_run

REGISTRY = load_gate_registry()
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- helpers


def _set_cells(raw: bytes, entry_id: str, cells: dict[int, bytes]) -> bytes:
    """`raw` with the given fields of one entry row replaced, every other byte kept."""

    lines = list(split_byte_lines(raw))
    for number, line in enumerate(lines):
        body, ending = split_line_ending(line)
        spans = csv_field_spans(body)
        if body[spans[0][0]:spans[0][1]] != entry_id.encode():
            continue
        parts, cursor = [], 0
        for index, (start, end) in enumerate(spans):
            parts.append(body[cursor:start])
            parts.append(cells.get(index, body[start:end]))
            cursor = end
        parts.append(body[cursor:])
        lines[number] = b"".join(parts) + ending
        return b"".join(lines)
    raise AssertionError(f"no row for {entry_id}")


@pytest.fixture
def baseline_file(tmp_path: Path):
    """A three-row Classic baseline file, audited, with its truths: a real deliverable."""

    outcome = run_baseline(
        salaries=CLASSIC_SALARY,
        entries=classic_template(tmp_path, 3),
        out_dir=tmp_path / "runs",
        run_id="s05-baseline",
        now=NOW,
    )
    assert outcome.truths.delivery_state is DeliveryState.DELIVERABLE
    inputs = outcome.report["inputs"]
    item = delivery.Deliverable(
        path=outcome.output_path,
        sha256=outcome.output_sha256,
        file_kind="nfl_baseline_entry_csv_v1",
        producer="baseline",
        run_id=outcome.run_id,
        salary_path=Path(inputs["salaries"]["snapshot"]),
        salary_sha256=inputs["salaries"]["sha256"],
        entry_path=Path(inputs["entries"]["snapshot"]),
        entry_sha256=inputs["entries"]["sha256"],
        truths=outcome.truths,
    )
    return outcome.run_dir, item


def _variant(root: Path, item: delivery.Deliverable, raw: bytes, name: str, **changes):
    """The same claim about other bytes, written beside the original."""

    path = root / name
    path.write_bytes(raw)
    return delivery.Deliverable(**{**item.__dict__, "path": path, "sha256": sha256_bytes(raw), **changes})


def _partial_truths(item: delivery.Deliverable, unfilled: str):
    authorized = (*item.truths.delivered_entry_ids,)
    policy = derive_release_policy(
        file_valid=True, evidence_state=ReleaseEvidenceState.UNKNOWN,
        model_status=ModelStatus.PRIOR_ONLY, certification_basis=CertificationBasis.MODEL_ASSISTED,
    )
    truth = derive_delivery_state(
        file_valid=True, authorized_entry_ids=authorized,
        delivered_entry_ids=tuple(eid for eid in authorized if eid != unfilled),
    )
    return release_truths_v2(policy, truth)


# ------------------------------------------------- the pointer, delivery.py


def test_publish_writes_an_atomic_hash_bound_pointer_that_reads_back(
    baseline_file, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, item = baseline_file
    replaced: list[tuple[str, str]] = []
    real_replace = os.replace
    monkeypatch.setattr(delivery.os, "replace", lambda a, b: (replaced.append((str(a), str(b))), real_replace(a, b)))
    latest = delivery.publish(root, item, now=NOW)
    pointer = root / delivery.POINTER_NAME
    assert replaced == [(str(root / f".{delivery.POINTER_NAME}.{os.getpid()}.tmp"), str(pointer))]
    assert latest.pointer_sha256 == sha256_file(pointer)
    record = json.loads(pointer.read_text(encoding="utf-8"))
    assert record["schema_version"] == "nfl_latest_deliverable_v1"
    assert record["file"] == {
        "path": item.path.name, "sha256": item.sha256,
        "bytes": item.path.stat().st_size, "file_kind": "nfl_baseline_entry_csv_v1",
    }
    assert record["inputs"]["entries"]["sha256"] == item.entry_sha256
    assert record["mode"] == "CLASSIC"
    assert record["coverage"]["delivered_entry_ids"] == list(item.truths.delivered_entry_ids)
    assert record["release_truths"]["DELIVERY_STATE"] == "DELIVERABLE"
    assert record["release_truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert record["revalidation"]["status"] == "PASS"
    assert record["supersedes"] is None
    assert "not upload clearance" in record["warning"]
    assert not list(root.glob(".*.tmp"))

    again = delivery.read_latest(root)
    assert again is not None and again.pointer_sha256 == latest.pointer_sha256
    assert again.deliverable.sha256 == item.sha256
    with pytest.raises(delivery.DeliveryPointerError, match="DELIVERY_POINTER_EXISTS"):
        delivery.publish(root, item)
    assert delivery.read_latest(root / "inputs") is None


def test_a_pointer_whose_file_changed_is_never_read_back(baseline_file) -> None:
    root, item = baseline_file
    delivery.publish(root, item)
    item.path.write_bytes(item.path.read_bytes().replace(b"\r\n", b"\n", 1))
    with pytest.raises(delivery.DeliveryPointerError, match="DELIVERABLE_SHA256_MISMATCH"):
        delivery.read_latest(root)


@pytest.mark.parametrize(
    ("case", "code"),
    (
        ("entry_id", "DELIVERABLE_ENTRY_ORDER_MISMATCH"),
        ("contest_name", "DELIVERABLE_BYTE_AUDIT_FAILED"),
        ("person_twice", "DELIVERABLE_LINEUP_INVALID"),
        ("duplicate_lineup", "DELIVERABLE_LINEUP_DUPLICATE"),
        ("blank_row", "DELIVERABLE_COVERAGE_MISMATCH"),
    ),
)
def test_wrong_bytes_or_mapping_are_withheld_even_under_their_own_hash(
    baseline_file, case: str, code: str
) -> None:
    """A producer's claim about corrupt bytes is refused by what the bytes hold."""

    root, item = baseline_file
    raw = item.path.read_bytes()
    template = parse_entries(item.entry_path)
    first, second = (entry.entry_id for entry in template.authorizations[:2])
    rows = {entry.entry_id: entry.existing_cells for entry in parse_entries(item.path).authorizations}
    roster_start = template.roster_start_index
    if case == "entry_id":
        corrupt = _set_cells(raw, first, {0: b"5499999999"})
    elif case == "contest_name":
        corrupt = _set_cells(raw, first, {1: b"Another contest"})
    elif case == "person_twice":
        corrupt = _set_cells(raw, first, {roster_start + 1: rows[first][2].encode()})
    elif case == "duplicate_lineup":
        corrupt = _set_cells(raw, second, {roster_start + i: cell.encode() for i, cell in enumerate(rows[first])})
    else:
        corrupt = _set_cells(raw, second, {roster_start + i: b"" for i in range(9)})
    claim = _variant(root, item, corrupt, "DK_BASELINE_ENTRY_V1_corrupt.csv")
    problems = delivery.revalidate(claim, root=root)
    assert any(problem.startswith(code + ":") for problem in problems), problems
    with pytest.raises(delivery.DeliveryPointerError) as refused:
        delivery.publish(root, claim)
    assert not (root / delivery.POINTER_NAME).exists()
    limitations = delivery.blocker_limitations(refused.value.problems, REGISTRY)
    assert delivery.withholds(limitations)
    assert all(item.gate_class is GateClass.V for item in limitations)


def test_names_inputs_and_truths_that_cannot_be_delivered_are_refused(baseline_file, tmp_path: Path) -> None:
    root, item = baseline_file
    raw = item.path.read_bytes()
    upload = _variant(root, item, raw, "DK_UPLOAD_s05.csv")
    assert delivery.revalidate(upload, root=root)[0].startswith("DELIVERABLE_UPLOAD_NAME_PROHIBITED:")
    outside = tmp_path / "elsewhere.csv"
    outside.write_bytes(raw)
    moved = delivery.Deliverable(**{**item.__dict__, "path": outside})
    assert delivery.revalidate(moved, root=root)[0].startswith("DELIVERABLE_OUTSIDE_RUN_FOLDER:")
    changed = delivery.Deliverable(**{**item.__dict__, "entry_sha256": "0" * 64})
    assert delivery.revalidate(changed, root=root)[0].startswith("DELIVERABLE_INPUT_SHA256_MISMATCH:entries:")
    none = derive_delivery_state(file_valid=False, authorized_entry_ids=item.truths.delivered_entry_ids,
                                 delivered_entry_ids=())
    policy = derive_release_policy(file_valid=False, evidence_state=ReleaseEvidenceState.UNKNOWN,
                                   model_status=ModelStatus.PRIOR_ONLY,
                                   certification_basis=CertificationBasis.MODEL_ASSISTED)
    empty = delivery.Deliverable(**{**item.__dict__, "truths": release_truths_v2(policy, none)})
    assert delivery.revalidate(empty, root=root) == ("DELIVERABLE_STATE_NOT_DELIVERABLE:NO_DELIVERABLE",)
    missing = delivery.Deliverable(**{**item.__dict__, "path": root / "absent.csv"})
    assert delivery.revalidate(missing, root=root)[0].startswith("DELIVERABLE_FILE_MISSING:")


def test_replace_needs_the_same_inputs_and_equal_or_better_coverage(baseline_file) -> None:
    root, item = baseline_file
    last = item.truths.delivered_entry_ids[-1]
    blanked = _set_cells(item.path.read_bytes(), last, {parse_entries(item.entry_path).roster_start_index + i: b""
                                                        for i in range(9)})
    partial = _variant(root, item, blanked, "DK_BASELINE_ENTRY_V1_partial.csv",
                       truths=_partial_truths(item, last))
    assert partial.truths.delivery_state is DeliveryState.DELIVERABLE_PARTIAL
    with pytest.raises(delivery.DeliveryPointerError, match="DELIVERY_POINTER_MISSING"):
        delivery.replace(root, item)

    delivery.publish(root, item)
    with pytest.raises(delivery.DeliveryPointerError, match="DELIVERY_POINTER_COVERAGE_REGRESSION"):
        delivery.replace(root, partial)
    other = delivery.Deliverable(**{**item.__dict__, "salary_sha256": "1" * 64})
    with pytest.raises(delivery.DeliveryPointerError, match="DELIVERY_POINTER_INPUTS_DIFFER"):
        delivery.replace(root, other)
    assert delivery.read_latest(root).deliverable.path == item.path

    # A current file that no longer revalidates gives way to any file that does.
    item.path.write_bytes(item.path.read_bytes() + b"\r\n")
    replaced = delivery.replace(root, partial)
    assert replaced.record["supersedes"]["revalidation"] == "FAIL"
    assert replaced.record["supersedes"]["file_sha256"] == item.sha256
    assert delivery.read_latest(root).deliverable.path == partial.path


def test_a_failed_replace_leaves_the_old_pointer_whole(baseline_file, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = baseline_file
    delivery.publish(root, item)
    before = (root / delivery.POINTER_NAME).read_bytes()

    def refuse(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(delivery.os, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        delivery.replace(root, item)
    assert (root / delivery.POINTER_NAME).read_bytes() == before
    assert not list(root.glob(".*.tmp"))


@pytest.mark.parametrize("damage", ("not json", "fields", "escape"))
def test_a_malformed_pointer_is_refused(baseline_file, damage: str) -> None:
    root, item = baseline_file
    delivery.publish(root, item)
    pointer = root / delivery.POINTER_NAME
    record = json.loads(pointer.read_text(encoding="utf-8"))
    if damage == "not json":
        pointer.write_text("{", encoding="utf-8")
    elif damage == "fields":
        record["extra"] = True
        pointer.write_text(json.dumps(record), encoding="utf-8")
    else:
        record["file"]["path"] = "../" + record["file"]["path"]
        pointer.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(delivery.DeliveryPointerError, match="DELIVERY_POINTER_INVALID"):
        delivery.read_latest(root)


@pytest.mark.parametrize(
    ("text", "withheld", "codes"),
    (
        ("READABLE_REVIEW_JSON_SHA256_MISMATCH:actual=a:expected=b;READABLE_REVIEW_POOL_COVERAGE_TOTAL_MISMATCH:x",
         False, ["READABLE_REVIEW_JSON_SHA256_MISMATCH", "READABLE_REVIEW_POOL_COVERAGE_TOTAL_MISMATCH"]),
        ("READABLE_REVIEW_JSON_SHA256_MISMATCH:x;READABLE_REVIEW_BULK_ENTRY_CSV_SHA256_MISMATCH:y",
         True, ["READABLE_REVIEW_JSON_SHA256_MISMATCH", "READABLE_REVIEW_BULK_ENTRY_CSV_SHA256_MISMATCH"]),
        ("READABLE_REVIEW_OUTPUT_ENTRY_ORDER_MISMATCH:z", True, ["READABLE_REVIEW_OUTPUT_ENTRY_ORDER_MISMATCH"]),
        ("FORCED_POST_PUBLICATION_DISPLAY_MUTATION", True, ["GATE_CODE_UNCLASSIFIED"]),
        ("KeyError:'readable_review_json'", True, ["GATE_CODE_UNCLASSIFIED"]),
        ("", True, ["GATE_CODE_UNCLASSIFIED"]),
        ("READABLE_REVIEW_JSON_SHA256_MISMATCH:x; a fragment with no code", True,
         ["READABLE_REVIEW_JSON_SHA256_MISMATCH", "GATE_CODE_UNCLASSIFIED"]),
    ),
)
def test_a_discrepancy_is_classified_code_by_code_and_fails_closed(text: str, withheld: bool, codes: list[str]) -> None:
    limitations = delivery.discrepancy_limitations(text, REGISTRY)
    assert [item.code for item in limitations] == codes
    assert delivery.withholds(limitations) is withheld


# ---------------------------------------------------------- C3 in place


def test_c3_keeps_the_export_and_audit_when_the_readable_json_write_fails(
    c3_seed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import classic_review

    args = _direct_args(c3_seed, tmp_path / "json")
    json_file = Path(args["output_dir"]) / "prior_only_readable_review.json"
    real = classic_review._atomic_write

    def short_json(path, payload):
        digest = real(path, payload)
        return "not-the-json-hash" if Path(path) == json_file else digest

    monkeypatch.setattr(classic_review, "_atomic_write", short_json)
    with pytest.raises(ClassicReviewPresentationError, match="^CLASSIC_C3_READABLE_JSON_WRITE_MISMATCH$") as kept:
        create_classic_review_package(**args)
    error = kept.value
    assert Path(error.export_path) == Path(args["output_path"]).resolve()
    assert sha256_file(error.export_path) == error.export_sha256
    assert sha256_file(error.audit_path) == error.audit_sha256
    assert error.audit["status"] == "PASS"
    assert not json_file.exists()
    assert not (Path(args["output_dir"]) / "prior_only_readable_review.html").exists()
    assert not list(Path(args["output_dir"]).glob("*.tmp"))


def test_c3_names_a_render_exception_that_carries_no_code(
    c3_seed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import classic_review

    args = _direct_args(c3_seed, tmp_path / "render")

    def broken(data, *, data_sha256):
        raise KeyError("exposure")

    monkeypatch.setattr(classic_review, "_render_html", broken)
    with pytest.raises(ClassicReviewPresentationError, match="^CLASSIC_C3_READABLE_RENDER_FAILED:KeyError:") as kept:
        create_classic_review_package(**args)
    assert Path(kept.value.export_path).is_file()
    assert Path(kept.value.audit_path).is_file()
    limitations = delivery.discrepancy_limitations(str(kept.value), REGISTRY)
    assert [item.gate_class for item in limitations] == [GateClass.P]


@pytest.mark.parametrize(("target", "code"), (
    ("export", "CLASSIC_C3_FINAL_OUTPUT_REPARSE_MISMATCH"),
    ("audit", "CLASSIC_C3_FINAL_OUTPUT_SHA256_MISMATCH"),
))
def test_c3_withholds_everything_when_the_kept_files_changed_during_rendering(
    c3_seed, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, code: str
) -> None:
    from nfl_dfs import classic_review

    args = _direct_args(c3_seed, tmp_path / target)
    victim = (Path(args["output_path"]) if target == "export"
              else Path(args["output_dir"]) / "classic_review_export_audit.json")

    def corrupt_then_fail(data, *, data_sha256):
        raw = victim.read_bytes()
        if target == "export":
            template = parse_entries(args["entry_path"])
            entry = template.authorizations[0].entry_id
            rows = {item.entry_id: item.existing_cells for item in parse_entries(victim).authorizations}
            start = template.roster_start_index
            raw = _set_cells(raw, entry, {start: rows[entry][1].encode(), start + 1: rows[entry][0].encode()})
        else:
            raw = raw + b" "
        victim.write_bytes(raw)
        raise KeyError("display")

    monkeypatch.setattr(classic_review, "_render_html", corrupt_then_fail)
    with pytest.raises(ClassicReviewError, match=code) as withheld:
        create_classic_review_package(**args)
    assert not isinstance(withheld.value, ClassicReviewPresentationError)
    _assert_no_new_output(args)


# ------------------------------------------------ run-slate, Showdown


def _showdown_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, failing=None, workbook=None):
    from nfl_dfs import cli
    from nfl_dfs import prior_review as prior_review_module

    salary_path, entry_path, package_dir, project = _prepared_run(
        tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=6)
    )
    attachments = _attachments(tmp_path, salary_path, entry_path)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review_module.run_prior_review
    monkeypatch.setattr(cli, "run_prior_review", lambda **kwargs: real(**kwargs, project=project))
    if failing is not None:
        monkeypatch.setattr(cli, "create_readable_review", failing)
    if workbook is not None:
        monkeypatch.setattr(cli, "create_cowork_status_workbook", workbook)
    code = cli.command_cowork_run(_cowork_args(tmp_path, attachments, prior_package_dir=str(package_dir)))
    root = tmp_path / "outputs" / "prior-review-test"
    return code, json.loads((root / "cowork_run.json").read_text(encoding="utf-8")), root


def test_showdown_success_publishes_the_revalidated_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, report, root = _showdown_run(tmp_path, monkeypatch)
    assert code == 0
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["release_truths"]["schema_version"] == "nfl_release_truths_v2"
    assert report["release_truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert {item["class"] for item in report["release_truths"]["delivery_limitations"]} == {"P"}
    latest = delivery.read_latest(root)
    assert latest is not None and str(latest.deliverable.path) == report["bulk_entry_csv"]
    assert report["latest_deliverable"]["sha256"] == report["bulk_entry_sha256"]
    assert report["prior_review_hashes"]["latest_deliverable"] == latest.pointer_sha256


def test_showdown_roster_discrepancy_still_withholds_the_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-R28 expectation of the Showdown display regression, now for a `V` code only."""

    def failing(**kwargs):
        raise ReadableReviewError("READABLE_REVIEW_SELECTION_SALARY_MISMATCH:test")

    code, report, root = _showdown_run(tmp_path, monkeypatch, failing=failing)
    assert code == 2
    assert report["FILE_VALID"] is False
    assert report["DELIVERY_STATE"] == "NO_DELIVERABLE"
    assert report["bulk_entry_csv"] is None and report["latest_deliverable"] is None
    assert "bulk_entry_csv" not in report["prior_review_artifacts"]
    assert "bulk_entry_csv" not in report["prior_review_hashes"]
    withheld = report["prior_review_reports"]["readable_review_failure"]["withheld_artifacts"]["bulk_entry_csv"]
    assert sha256_file(withheld["path"]) == withheld["sha256"]
    assert not (root / delivery.POINTER_NAME).exists()
    codes = {item["code"]: item["class"] for item in report["release_truths"]["delivery_limitations"]}
    assert codes["READABLE_REVIEW_SELECTION_SALARY_MISMATCH"] == "V"


@pytest.mark.parametrize("damage", ("unclassified", "entry_ids_swapped"))
def test_showdown_presentation_label_cannot_save_a_corrupt_or_unclassified_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    def failing(**kwargs):
        if damage == "unclassified":
            raise KeyError("pool_coverage")
        csv_path = Path(kwargs["exported_path"])
        raw = csv_path.read_bytes()
        template = kwargs["template"]
        first, second = (item.entry_id for item in template.authorizations[:2])
        raw = raw.replace(first.encode(), b"PLACEHOLDER", 1).replace(second.encode(), first.encode(), 1)
        csv_path.write_bytes(raw.replace(b"PLACEHOLDER", second.encode(), 1))
        raise ReadableReviewError("READABLE_REVIEW_POOL_COVERAGE_TOTAL_MISMATCH:forced")

    code, report, root = _showdown_run(tmp_path, monkeypatch, failing=failing)
    assert code == 2
    assert report["FILE_VALID"] is False and report["DELIVERY_STATE"] == "NO_DELIVERABLE"
    assert report["bulk_entry_csv"] is None
    assert "bulk_entry_csv" not in report["prior_review_artifacts"]
    assert not (root / delivery.POINTER_NAME).exists()
    codes = {item["code"] for item in report["release_truths"]["delivery_limitations"]}
    assert ("GATE_CODE_UNCLASSIFIED" if damage == "unclassified" else "DELIVERABLE_SHA256_MISMATCH") in codes


def test_the_outer_handler_names_the_deliverable_and_never_deletes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(**kwargs):
        stray = Path(kwargs["output_path"]).parent / "DK_UPLOAD_stray.csv"
        stray.write_bytes(b"not ours to keep\r\n")
        raise RuntimeError("workbook crashed after the pointer was published")

    code, report, root = _showdown_run(tmp_path, monkeypatch, workbook=crash)
    assert code == 2
    assert report["stage"] == "BUILD_OR_CERTIFY_FAILED" and report["FILE_VALID"] is False
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    kept = Path(report["latest_deliverable"]["path"])
    assert kept.is_file() and sha256_file(kept) == report["latest_deliverable"]["sha256"]
    assert report["release_truths"]["DELIVERY_STATE"] == "DELIVERABLE"
    assert not (root / "DK_UPLOAD_stray.csv").exists()
    diagnostic = json.loads((root / "cowork_diagnostic.json").read_text(encoding="utf-8"))
    assert diagnostic["removed_uploads"] == [str(root / "DK_UPLOAD_stray.csv")]
    assert diagnostic["latest_deliverable"]["path"] == str(kept)


def test_the_outer_handler_names_nothing_it_cannot_revalidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(**kwargs):
        pointer = Path(kwargs["output_path"]).parent / delivery.POINTER_NAME
        csv_path = Path(json.loads(pointer.read_text(encoding="utf-8"))["file"]["path"])
        target = pointer.parent / csv_path
        target.write_bytes(target.read_bytes() + b"\r\n")
        raise RuntimeError("workbook crashed after the CSV changed")

    code, report, root = _showdown_run(tmp_path, monkeypatch, workbook=crash)
    assert code == 2
    assert report["DELIVERY_STATE"] == "NO_DELIVERABLE" and report["latest_deliverable"] is None
    assert report["latest_deliverable_problems"][0].startswith("DELIVERABLE_SHA256_MISMATCH:")
    assert list((root / "review").glob("DK_REVIEW_ENTRY_*.csv"))  # preserved, not advertised


# -------------------------------------------------- run-slate, Classic


def _classic_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, policy: bool = True, patch=None):
    from nfl_dfs import cli
    from nfl_dfs.classic_portfolio_policy import classic_portfolio_policy_template
    from nfl_dfs.dk import parse_salaries

    from .test_classic_prior_review import AS_OF, _fixture

    salary, entry, package, role, status, _inactive = _fixture(tmp_path / "fixture", entries=1)
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "salary.csv").write_bytes(salary.read_bytes())
    (attachments / "entries.csv").write_bytes(entry.read_bytes())
    overrides = {}
    if policy:
        slate = parse_salaries(attachments / "salary.csv")
        entries = parse_entries(attachments / "entries.csv")
        policy_path = tmp_path / "classic_policy.json"
        policy_path.write_text(json.dumps(classic_portfolio_policy_template(
            slate, tuple(item.entry_id for item in entries.authorizations), entry_sha256=entries.raw_hash,
        )), encoding="utf-8")
        overrides["portfolio_policy_json"] = str(policy_path)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    if patch is not None:
        patch(cli)
    code = cli.command_cowork_run(_cowork_args(
        tmp_path, attachments, label="classic-s05", run_id="classic-s05",
        prior_package_dir=str(package), build_priors=True, official_status_csv=str(status),
        offensive_role_evidence_json=str(role), as_of=AS_OF.isoformat(), **overrides,
    ))
    root = tmp_path / "outputs" / "classic-s05"
    return code, json.loads((root / "cowork_run.json").read_text(encoding="utf-8")), root


def test_c3_success_and_c1_exits_report_their_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, report, root = _classic_run(tmp_path / "c3", monkeypatch)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT"
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert delivery.read_latest(root).deliverable.sha256 == report["bulk_entry_sha256"]

    code, report, root = _classic_run(tmp_path / "c1", monkeypatch, policy=False)
    assert code == 0 and report["stage"] == "PRIOR_ONLY_CLASSIC_REVIEW_ARTIFACTS"
    assert report["FILE_VALID"] is True and report["DELIVERY_STATE"] == "NO_DELIVERABLE"
    assert report["release_truths"]["delivered_file_valid"] is False
    assert "PROFILE_WRITES_NO_ENTRY_FILE" in {
        item["code"] for item in report["release_truths"]["delivery_limitations"]
    }
    assert report["latest_deliverable"] is None and not (root / delivery.POINTER_NAME).exists()


def test_c3_internal_presentation_failure_is_listed_and_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nfl_dfs import classic_review

    def broken(data, *, data_sha256):
        raise KeyError("exposure")

    monkeypatch.setattr(classic_review, "_render_html", broken)
    code, report, root = _classic_run(tmp_path, monkeypatch)
    assert code == 2
    assert report["stage"] == "PRIOR_ONLY_CLASSIC_C3_REVIEW_EXPORT_READABLE_REVIEW_FAILED"
    assert report["FILE_VALID"] is True and report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["blockers"][0].startswith("CLASSIC_C3_READABLE_REVIEW_FAILED:CLASSIC_C3_READABLE_RENDER_FAILED:")
    for key in ("bulk_entry_csv", "classic_export_audit", "latest_deliverable"):
        assert key in report["prior_review_artifacts"] and key in report["prior_review_hashes"]
    assert "readable_review_json" not in report["prior_review_artifacts"]
    assert Path(report["bulk_entry_csv"]).is_file()
    assert not list(root.rglob("prior_only_readable_review.*"))
    assert delivery.read_latest(root).deliverable.path == Path(report["bulk_entry_csv"])


@pytest.mark.parametrize("damage", ("unclassified", "csv_changed"))
def test_c3_display_failure_withholds_when_unclassified_or_the_csv_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    """The pre-R28 expectation of the C3 display regression, now for these cases only."""

    def patch(cli):
        def verify(**kwargs):
            if damage == "unclassified":
                return ("FORCED_POST_PUBLICATION_DISPLAY_MUTATION",)
            csv_path = next(Path(kwargs["json_path"]).parent.glob("DK_REVIEW_ENTRY_*.csv"))
            csv_path.write_bytes(csv_path.read_bytes() + b"\r\n")
            return ("READABLE_REVIEW_HTML_SHA256_MISMATCH:actual=x:expected=y",)

        monkeypatch.setattr(cli, "verify_readable_review_artifacts", verify)

    code, report, root = _classic_run(tmp_path, monkeypatch, patch=patch)
    assert code == 2
    assert report["FILE_VALID"] is False and report["DELIVERY_STATE"] == "NO_DELIVERABLE"
    assert report["export"]["bulk_entry_csv"] is None
    for key in ("classic_export_audit", "bulk_entry_csv", "readable_review_json", "readable_review_html"):
        assert key not in report["prior_review_artifacts"]
    assert not list(root.rglob("DK_REVIEW_ENTRY_*.csv"))
    assert not list(root.rglob("classic_review_export_audit.json"))
    assert not (root / delivery.POINTER_NAME).exists()
    codes = {item["code"] for item in report["release_truths"]["delivery_limitations"]}
    assert ("GATE_CODE_UNCLASSIFIED" if damage == "unclassified" else "DELIVERABLE_SHA256_MISMATCH") in codes
