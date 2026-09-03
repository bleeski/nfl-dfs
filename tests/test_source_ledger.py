from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nfl_dfs.evidence import EvidenceError, validate_source_ledger
from nfl_dfs.hashing import sha256_file


def _ledger_payload(artifact: Path, derived: dict[str, str]) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "schema_version": "nfl_source_ledger_v1",
        "entries": [
            {
                "artifact_id": sha256_file(artifact),
                "path": artifact.name,
                "source_uri": "https://api.sleeper.app/v1/players/nfl",
                "captured_at": now.isoformat(),
                "observed_at": (now - timedelta(minutes=1)).isoformat(),
                "license_decision": "SECONDARY_STATUS_ONLY",
                "parser_version": "sleeper_players_v1",
            }
        ],
        "derived": derived,
    }


def _write_ledger(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_source_ledger_binds_both_model_outputs(tmp_path: Path) -> None:
    artifact = tmp_path / "source.json"
    artifact.write_text('{"players": []}\n', encoding="utf-8")
    expected = {"team_projections": "1" * 64, "player_opportunities": "2" * 64}
    ledger_path = _write_ledger(
        tmp_path / "ledger.json", _ledger_payload(artifact, expected)
    )

    ledger = validate_source_ledger(ledger_path, expected_outputs=expected)

    assert ledger.derived == expected
    assert ledger.entries[0].artifact_id == sha256_file(artifact)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda payload: {"schema": "test"}, "invalid source ledger contract"),
        (
            lambda payload: {**payload, "unknown": True},
            "invalid source ledger contract",
        ),
        (
            lambda payload: {
                **payload,
                "derived": {"team_projections": "1" * 64},
            },
            "derived outputs must be exactly",
        ),
        (
            lambda payload: {
                **payload,
                "derived": {
                    "team_projections": "3" * 64,
                    "player_opportunities": "2" * 64,
                },
            },
            "derived hash mismatch",
        ),
    ],
)
def test_source_ledger_rejects_arbitrary_partial_unknown_or_mismatched_data(
    tmp_path: Path, mutation, match: str
) -> None:
    artifact = tmp_path / "source.json"
    artifact.write_text("{}\n", encoding="utf-8")
    expected = {"team_projections": "1" * 64, "player_opportunities": "2" * 64}
    payload = mutation(_ledger_payload(artifact, expected))
    ledger_path = _write_ledger(tmp_path / "ledger.json", payload)

    with pytest.raises(EvidenceError, match=match):
        validate_source_ledger(ledger_path, expected_outputs=expected)


def test_source_ledger_rejects_missing_and_tampered_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "source.json"
    artifact.write_text("original\n", encoding="utf-8")
    expected = {"team_projections": "1" * 64, "player_opportunities": "2" * 64}
    payload = _ledger_payload(artifact, expected)
    ledger_path = _write_ledger(tmp_path / "ledger.json", payload)
    artifact.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(EvidenceError, match="artifact hash mismatch"):
        validate_source_ledger(ledger_path, expected_outputs=expected)

    payload["entries"][0]["path"] = "missing.json"  # type: ignore[index]
    ledger_path = _write_ledger(tmp_path / "missing-ledger.json", payload)
    with pytest.raises(EvidenceError, match="artifact is missing"):
        validate_source_ledger(ledger_path, expected_outputs=expected)


def test_source_ledger_rejects_unapproved_uri_and_future_timestamp(tmp_path: Path) -> None:
    artifact = tmp_path / "source.json"
    artifact.write_text("{}\n", encoding="utf-8")
    expected = {"team_projections": "1" * 64, "player_opportunities": "2" * 64}
    payload = _ledger_payload(artifact, expected)
    payload["entries"][0]["source_uri"] = "https://example.com/data"  # type: ignore[index]
    with pytest.raises(EvidenceError, match="URI is not approved"):
        validate_source_ledger(
            _write_ledger(tmp_path / "uri.json", payload), expected_outputs=expected
        )

    payload = _ledger_payload(artifact, expected)
    payload["entries"][0]["captured_at"] = (  # type: ignore[index]
        datetime.now(timezone.utc) + timedelta(hours=1)
    ).isoformat()
    with pytest.raises(EvidenceError, match="captured_at is in the future"):
        validate_source_ledger(
            _write_ledger(tmp_path / "future.json", payload), expected_outputs=expected
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("license_decision", "UNREVIEWED"),
        ("parser_version", ""),
        ("captured_at", "2026-09-01T12:00:00"),
    ],
)
def test_source_ledger_rejects_invalid_license_parser_and_timestamp_contracts(
    tmp_path: Path, field: str, value: str
) -> None:
    artifact = tmp_path / "source.json"
    artifact.write_text("{}\n", encoding="utf-8")
    expected = {"team_projections": "1" * 64, "player_opportunities": "2" * 64}
    payload = _ledger_payload(artifact, expected)
    payload["entries"][0][field] = value  # type: ignore[index]

    with pytest.raises(EvidenceError, match="invalid source ledger contract"):
        validate_source_ledger(
            _write_ledger(tmp_path / f"invalid-{field}.json", payload),
            expected_outputs=expected,
        )


def test_source_ledger_rejects_unknown_entry_fields(tmp_path: Path) -> None:
    artifact = tmp_path / "source.json"
    artifact.write_text("{}\n", encoding="utf-8")
    expected = {"team_projections": "1" * 64, "player_opportunities": "2" * 64}
    payload = _ledger_payload(artifact, expected)
    payload["entries"][0]["invented"] = True  # type: ignore[index]

    with pytest.raises(EvidenceError, match="invalid source ledger contract"):
        validate_source_ledger(
            _write_ledger(tmp_path / "unknown-entry.json", payload),
            expected_outputs=expected,
        )
