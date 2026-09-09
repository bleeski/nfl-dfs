"""SD2 failure reports and exact review bytes through the Cowork profile."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs import cli, prior_review
from nfl_dfs.dk import parse_salaries
from nfl_dfs.hashing import sha256_file
from .test_offensive_roles import _package, _declaration, _edit, _binding
from .test_participation import _model
from .test_prior_review_profile import _prepared_run, _attachments, _cowork_args, AS_OF
from .test_readiness_regressions import _statuses
from .test_priors_adapter import package


@pytest.mark.parametrize("fault", [None, "missing", "transfer", "inactive", "path_escape", "future", "stale", "source_bytes", "manifest_after", "source_after", "expired_after", "history_after"])
def test_cowork_roles_truths_and_no_new_csv_on_failure(tmp_path, monkeypatch, fault):
    now = datetime.now(timezone.utc)
    salary, entries, package, project = _prepared_run(tmp_path, expires_at=now + timedelta(hours=6))
    slate = parse_salaries(salary)
    model = _model(tmp_path, slate)
    role_path = _package(tmp_path / "roles", slate, [_declaration(slate, model)], as_of=now)
    person = "NE|RB|Backup RB"
    if fault in {"missing", "transfer"}:
        source = package / "player_prior.json"
        _edit(source, lambda p: p["metadata"]["coverage"]["offensive_history_by_person"].update({person: {
            "state": "MISSING_HISTORY" if fault == "missing" else "CURRENT_ROLE_UNKNOWN",
            "incompatible_transfer": fault == "transfer"}}))
        _edit(package / "prior_package.json", lambda p: p["artifacts"].update({"player_prior.json": sha256_file(source)}))
        role_path = None
    if fault == "path_escape":
        _edit(role_path, lambda p: p["sources"][0].update(path="../outside.txt"))
    if fault == "future":
        _edit(role_path, lambda p: p["sources"][0].update(captured_at=(now + timedelta(minutes=5)).isoformat()))
    if fault == "stale":
        _edit(role_path, lambda p: p["sources"][0].update(expires_at=(now - timedelta(minutes=1)).isoformat()))
    if fault == "source_bytes":
        capture = next((role_path.parent / "sources").iterdir())
        capture.write_bytes(capture.read_bytes() + b"tampered")
    official = None
    if fault == "inactive":
        dk_id = _binding(slate, person)["cpt_dk_id"]
        official = _statuses(tmp_path / "official.csv", slate, [dk_id], inactive=[dk_id], observed=now)
    attachments = _attachments(tmp_path, salary, entries)
    if official:
        copied = attachments / "official.csv"
        copied.write_bytes(official.read_bytes())
        official = copied
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    real = prior_review.run_prior_review
    monkeypatch.setattr(cli, "run_prior_review", lambda **kw: real(**kw, project=project))
    real_select = prior_review.select_prior_lineups
    if fault in {"manifest_after", "source_after", "expired_after", "history_after"}:
        def select(*args, **kwargs):
            output = real_select(*args, **kwargs)
            resolution = output[1].offensive_role_resolution
            if fault == "manifest_after":
                path = Path(resolution.evidence_path)
                path.write_bytes(path.read_bytes() + b" ")
            elif fault == "source_after":
                path = Path(next(iter(resolution.source_hashes)))
                path.write_bytes(path.read_bytes() + b"tamper")
            elif fault == "history_after":
                path = package / "player_prior.json"
                path.write_bytes(path.read_bytes() + b" ")
            else:
                class Clock(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return now + timedelta(hours=3)
                monkeypatch.setattr(prior_review, "datetime", Clock)
            return output
        monkeypatch.setattr(prior_review, "select_prior_lineups", select)
    sentinel = tmp_path / "outputs" / "old" / "DK_REVIEW_ENTRY_prior.csv"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"preserve old output\r\n")
    args = _cowork_args(tmp_path, attachments, prior_package_dir=str(package),
                        offensive_role_evidence_json=str(role_path) if role_path else None)
    code = cli.command_cowork_run(args)
    report = json.loads((tmp_path / "outputs" / "prior-review-test" / "cowork_run.json").read_text())
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["EVIDENCE_STATE"] == "UNKNOWN"
    assert sentinel.read_bytes() == b"preserve old output\r\n"
    new_csvs = list((tmp_path / "outputs" / "prior-review-test").rglob("DK_REVIEW_ENTRY_*.csv"))
    if fault is None:
        assert code == 0 and report["FILE_VALID"] and len(new_csvs) == 1
        role_report = report["prior_review_reports"]["selection"]["prior_scores"]["offensive_roles"]
        assert role_report["synthetic_note"] == "TEST_ONLY_SYNTHETIC_EVIDENCE"
        people = [f["person"] for f in role_report["findings"]]
        assert len(people) == len(set(people)) == 12
        copied_request = json.loads((tmp_path / "runs" / "prior-review-test" / "run_request.json").read_text())
        copied = Path(copied_request["offensive_role_evidence_json"])
        assert copied.parent.name == "inputs" and sha256_file(copied) == sha256_file(role_path)
    else:
        assert code == 2 and not report["FILE_VALID"] and not new_csvs
        assert "OFFENSIVE" in str(report["blockers"])
        if fault in {"missing", "transfer"}:
            findings = report["prior_review_reports"]["offensive_roles"]["findings"]
            assert len([f for f in findings if f["person"] == person]) == 1


def test_appg_mutation_cannot_move_role_numbers_or_rosters(tmp_path):
    from .test_offensive_roles import _setup, AS_OF as ROLE_AS_OF
    from nfl_dfs.selection import select_prior_lineups
    slate, model, contract, splits = _setup(tmp_path)
    path = _package(tmp_path / "before", slate, [_declaration(slate, model)])
    first = select_prior_lineups(slate, model, splits, contract, count=2, offensive_role_evidence_json=path, as_of=ROLE_AS_OF)
    salary = tmp_path / "DKSalaries.csv"
    salary.write_bytes(salary.read_bytes().replace(b",0,", b",99999999,"))
    changed = parse_salaries(salary)
    path = _package(tmp_path / "after", changed, [_declaration(changed, model)])
    second = select_prior_lineups(changed, model, splits, contract, count=2, offensive_role_evidence_json=path, as_of=ROLE_AS_OF)
    assert first[1].by_person == second[1].by_person
    assert [x.roster for x in first[0]] == [x.roster for x in second[0]]


def test_full_frozen_prior_projection_cowork_chain_and_portable_repeat(package, tmp_path, monkeypatch):
    """Real freeze/project/select/export; only captured inputs are synthetic."""
    import csv
    import io
    import shutil
    from nfl_dfs import priors
    from nfl_dfs.opportunity import load_opportunity_model
    from nfl_dfs.projection import build_projection_package
    from .test_priors_adapter import _freeze, AS_OF as FROZEN_AS_OF
    from .test_prior_selection import _entries_bytes

    # Add the frozen kicking splits required by the real scorer to the existing
    # synthetic team-stat source, updating all content-addressed bindings.
    root = package["root"]
    manifest = json.loads((root / priors.MANIFEST_FILENAME).read_text())
    item = next(a for a in manifest["artifacts"] if a["name"] == "team_stats")
    source = root / item["relative_path"]
    reader = csv.DictReader(io.StringIO(source.read_text()))
    extra = {"pat_made": "3", "pat_att": "3", "fg_made_0_19": "0", "fg_made_20_29": "0",
             "fg_made_30_39": "1", "fg_made_40_49": "1", "fg_made_50_59": "0", "fg_made_60_": "0"}
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=[*reader.fieldnames, *extra], lineterminator="\n")
    writer.writeheader()
    writer.writerows({**row, **extra} for row in reader)
    from nfl_dfs.hashing import sha256_bytes
    raw = buffer.getvalue().encode()
    digest = sha256_bytes(raw)
    relative = f"raw/{digest}.csv"
    (root / relative).write_bytes(raw)
    item.update(relative_path=relative, sha256=digest, artifact_id=digest, byte_count=len(raw))
    (root / priors.MANIFEST_FILENAME).write_bytes(priors.canonical_json_bytes(manifest))
    _edit(root / priors.PROPOSAL_FILENAME, lambda p: p.update(source_manifest_sha256=sha256_file(root / priors.MANIFEST_FILENAME)))
    frozen = _freeze(package, tmp_path, name="frozen")
    projected = build_projection_package(
        salaries=package["salary"], salary_sha256=package["salary_digest"],
        team_source=frozen["team_source"], team_source_sha256=frozen["hashes"][priors.TEAM_PRIOR_FILENAME],
        player_source=frozen["player_source"], player_source_sha256=frozen["hashes"][priors.PLAYER_PRIOR_FILENAME],
        identity_map=frozen["identity_map"], identity_map_sha256=frozen["hashes"][priors.IDENTITY_MAP_FILENAME],
        as_of=FROZEN_AS_OF, output_dir=tmp_path / "role-basis",
    )
    slate = package["slate"]
    model = load_opportunity_model(slate, projected.team_projections, projected.player_opportunities)
    roles = _package(tmp_path / "roles", slate,
                     [_declaration(slate, model, team=t) for t in ("LAR", "SEA")],
                     as_of=datetime.fromisoformat(FROZEN_AS_OF))
    entries = tmp_path / "entries.csv"
    entries.write_bytes(_entries_bytes())
    attachments = _attachments(tmp_path, package["salary"], entries)
    monkeypatch.setattr(cli, "DEFAULT_RUNS_DIR", tmp_path / "runs")
    first_args = _cowork_args(tmp_path, attachments, prior_package_dir=frozen["output_dir"],
                              offensive_role_evidence_json=str(roles), as_of=FROZEN_AS_OF)
    assert cli.command_cowork_run(first_args) == 0
    first = json.loads((tmp_path / "outputs" / "prior-review-test" / "cowork_run.json").read_text())
    assert first["FILE_VALID"] and first["MODEL_STATUS"] == "PRIOR_ONLY"
    assert first["EVIDENCE_STATE"] == "UNKNOWN" and first["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    copied = tmp_path / "portable"
    shutil.copytree(tmp_path / "runs" / "prior-review-test" / "inputs", copied / "inputs")
    shutil.copytree(Path(frozen["output_dir"]), copied / "priors")
    original_request = json.loads((tmp_path / "runs" / "prior-review-test" / "run_request.json").read_text())
    role_copy = copied / "inputs" / Path(original_request["offensive_role_evidence_json"]).name
    Path(frozen["output_dir"]).rename(tmp_path / "original-priors-unavailable")
    roles.rename(roles.with_suffix(".unavailable"))
    second_args = _cowork_args(tmp_path, attachments, run_id="portable-repeat", prior_package_dir=str(copied / "priors"),
                               offensive_role_evidence_json=str(role_copy), as_of=FROZEN_AS_OF)
    assert cli.command_cowork_run(second_args) == 0
    second = json.loads((tmp_path / "outputs" / "portable-repeat" / "cowork_run.json").read_text())
    assert first["prior_review_hashes"]["bulk_entry_csv"] == second["prior_review_hashes"]["bulk_entry_csv"]
