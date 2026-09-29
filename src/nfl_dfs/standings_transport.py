"""Standings corpus transport (Session 17, X2, R27): release assets in, the inbox out, hash-bound.

The 26 DraftKings standings exports are Ben's own downloads and live on his Windows checkout;
`data/standings/inbox/` is gitignored, so a fresh clone has none of them. This module moves them:
each file is published as a release asset of a private repository Ben owns and is fetched back with
authentication (`sources.AuthenticatedGithubClient`).

What binds an arriving file is a COMMITTED manifest (`config/standings_corpus_manifest_v1.json`,
`nfl_standings_corpus_manifest_v1`): name, sha256 and byte count per file. The release is only storage,
so an asset swapped there cannot change what is expected; the expected hashes travel in git. GitHub's
own asset `size` and `digest` are cross-checks made before a byte is downloaded.

Nothing here contacts DraftKings, grades a file, or decides that a file is a genuine export. The
inbox is an immutable snapshot directory: a file lands there only by an exclusive create after it has
been verified whole, and an existing name is never replaced.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import sources
from .contracts import SourceArtifact
from .hashing import sha256_bytes, sha256_file

MANIFEST_SCHEMA = "nfl_standings_corpus_manifest_v1"
RECORD_SCHEMA = "nfl_standings_transport_v1"
SOURCE_LABEL = "STANDINGS_CORPUS_RELEASE_ASSET"
STAGING_DIRNAME = ".transport-staging"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024 * 1024
MAX_FILES = 500

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.(?i:csv|zip)$")
_REPOSITORY = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}

DOES_NOT_ESTABLISH = (
    "THAT_A_FILE_IS_A_GENUINE_DRAFTKINGS_EXPORT",
    "THAT_A_FILE_IS_CURRENT_OR_COMPLETE_FOR_ITS_CONTEST",
    "THAT_A_FILE_CAN_BE_GRADED",
    "THAT_THE_MANIFEST_IS_CORRECT_ONLY_THAT_THE_BYTES_MATCH_IT",
    "THAT_THE_TRANSPORT_RECORD_IS_THE_BINDING_A_CONSUMER_CHECKS_AGAINST",
    "UPLOAD_CLEARANCE_OR_CERTIFICATION",
)


class StandingsTransportError(ValueError):
    """A run-level refusal named by `code`; a per-file refusal is a row in the record instead."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class Manifest:
    payload: dict[str, Any]
    sha256: str
    name: str

    @property
    def repository(self) -> str:
        return self.payload["repository"]

    @property
    def release_tag(self) -> str:
        return self.payload["release_tag"]

    @property
    def files(self) -> list[dict[str, Any]]:
        return self.payload["files"]


@dataclass(frozen=True)
class TransportRecord:
    payload: dict[str, Any]
    record_path: Path
    all_bound: bool


# --- the manifest ----------------------------------------------------------------------------------


def _invalid(detail: str) -> StandingsTransportError:
    return StandingsTransportError("STANDINGS_TRANSPORT_MANIFEST_INVALID", detail)


def _validate_repository(repository: object) -> str:
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        raise _invalid("repository must be owner/name")
    try:
        sources.parse_authenticated_github_url(f"https://api.github.com/repos/{repository}")
    except sources.AuthenticatedFetchError:
        raise _invalid("repository is not an approved owner/name") from None
    return repository


def validate_manifest(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "repository", "release_tag", "files"}:
        raise _invalid("a manifest holds exactly schema_version, repository, release_tag and files")
    if payload["schema_version"] != MANIFEST_SCHEMA:
        raise _invalid(f"schema_version must be {MANIFEST_SCHEMA}")
    _validate_repository(payload["repository"])
    if not isinstance(payload["release_tag"], str) or not _TAG.fullmatch(payload["release_tag"]):
        raise _invalid("release_tag is not a plain tag name")
    files = payload["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise _invalid(f"files must be a list of 1 to {MAX_FILES} entries")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"name", "sha256", "byte_count"}:
            raise _invalid("a file entry holds exactly name, sha256 and byte_count")
        name, digest, size = entry["name"], entry["sha256"], entry["byte_count"]
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise _invalid("a file name must be a plain basename ending .csv or .zip")
        if name.split(".", 1)[0].upper() in _RESERVED:
            raise _invalid("a file name may not be a Windows reserved device name")
        if name.casefold() in seen:
            raise _invalid("file names must be unique ignoring case")
        seen.add(name.casefold())
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise _invalid("sha256 must be 64 lowercase hex characters")
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_FILE_BYTES:
            raise _invalid(f"byte_count must be an integer from 1 to {MAX_FILE_BYTES}")
    names = [entry["name"] for entry in files]
    if names != sorted(names):
        raise _invalid("files must be sorted by name")
    return payload


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key")
    return dict(pairs)


def load_manifest(path: str | Path) -> Manifest:
    target = Path(path)
    if not target.is_file():
        raise StandingsTransportError("STANDINGS_TRANSPORT_MANIFEST_MISSING", f"{target.name} is not a file")
    if target.stat().st_size > MAX_MANIFEST_BYTES:
        raise _invalid(f"a manifest over {MAX_MANIFEST_BYTES} bytes is refused")
    data = target.read_bytes()
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (ValueError, RecursionError):
        raise _invalid("the manifest is not UTF-8 JSON with unique keys") from None
    return Manifest(validate_manifest(payload), sha256_bytes(data), target.name)


def manifest_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_manifest(inbox_dir: str | Path, *, repository: str, release_tag: str) -> dict[str, Any]:
    """Hash the exports in an inbox into a manifest. Reads the inbox; never writes or renames there."""

    inbox = Path(inbox_dir)
    files = []
    for path in sorted(inbox.iterdir()) if inbox.is_dir() else []:
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in {".csv", ".zip"}:
            continue
        files.append({"name": path.name, "sha256": sha256_file(path), "byte_count": path.stat().st_size})
    return validate_manifest(
        {"schema_version": MANIFEST_SCHEMA, "repository": repository, "release_tag": release_tag, "files": files}
    )


def _create_new(path: Path, data: bytes, *, code: str) -> None:
    """Write `data` at `path` only if nothing is there: temp file, fsync, hard link (atomic, never replaces)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    exists = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            exists = True
    finally:
        temporary.unlink(missing_ok=True)
    if exists:
        raise StandingsTransportError(code, f"{path.name} already exists and is never overwritten")


def write_manifest(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    _create_new(target, manifest_bytes(validate_manifest(payload)), code="STANDINGS_TRANSPORT_RECORD_EXISTS")
    return target


# --- the fetch -----------------------------------------------------------------------------------------


def _row(entry: dict[str, Any], disposition: str, *, code: str | None = None, actual: str | None = None,
         artifact: SourceArtifact | None = None, observed: datetime | None = None) -> dict[str, Any]:
    artifact_json = None
    if artifact is not None:
        artifact_json = artifact.model_dump(mode="json")
        artifact_json["captured_at"] = observed.isoformat() if observed else artifact_json["captured_at"]
    return {
        "name": entry["name"],
        "expected_sha256": entry["sha256"],
        "expected_byte_count": entry["byte_count"],
        "disposition": disposition,
        "code": code,
        "actual_sha256": actual,
        "artifact": artifact_json,
    }


def _bound_regular_file(path: Path, sha256: str) -> bool:
    """A plain file (never a symlink, which points at bytes that can change) holding exactly `sha256`."""

    return path.is_file() and not path.is_symlink() and sha256_file(path) == sha256


def _refused(code: str, entry: dict[str, Any], actual: str | None = None) -> dict[str, Any]:
    return _row(entry, "REFUSED", code=code, actual=actual)


def fetch_corpus(
    manifest_path: str | Path,
    *,
    inbox_dir: str | Path,
    record_dir: str | Path,
    repository: str | None = None,
    allow_public_repository: bool = False,
    transport: Any = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    timeout_seconds: float = 60.0,
) -> TransportRecord:
    """Bring every manifest file into the inbox, verified, without replacing anything.

    A file already in the inbox is hashed and costs no request. A file that is not is downloaded to
    a staging directory, checked against the manifest's sha256 and byte count, and only then linked
    into the inbox by an exclusive create. A mismatch, a size or digest disagreement, a missing asset
    or a name collision is a refusal row in the record, and the other files still arrive.
    """

    manifest = load_manifest(manifest_path)
    repo = _validate_repository(repository or manifest.repository)
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("the observation time must be timezone-aware")
    inbox = Path(inbox_dir)
    inbox.mkdir(parents=True, exist_ok=True)

    rows: dict[str, dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    for entry in manifest.files:
        target = inbox / entry["name"]
        if not (target.exists() or target.is_symlink()):
            pending.append(entry)
        elif _bound_regular_file(target, entry["sha256"]):
            rows[entry["name"]] = _present(entry, inbox, observed)
        else:
            actual = sha256_file(target) if target.is_file() and not target.is_symlink() else None
            rows[entry["name"]] = _refused("STANDINGS_TRANSPORT_NAME_COLLISION", entry, actual)

    repository_private: bool | None = None
    token_env_name: str | None = None
    strict_tls = not sources.tls_nonstrict_ca_enabled()
    if pending:
        token, token_env_name = sources.resolve_transport_token(env)
        with sources.AuthenticatedGithubClient(
            token=token, token_env_name=token_env_name, transport=transport, timeout_seconds=timeout_seconds
        ) as client:
            strict_tls = client.tls_verify_x509_strict
            base = f"https://api.github.com/repos/{repo}"
            info = client.get_json(base)
            repository_private = info.get("private") if isinstance(info, dict) else None
            if repository_private is not True and not allow_public_repository:
                state = "public" if repository_private is False else "of unknown visibility"
                raise StandingsTransportError(
                    "STANDINGS_TRANSPORT_REPOSITORY_NOT_PRIVATE",
                    f"{repo} is {state}; the exports would be readable by anyone. "
                    "Publish them to a private repository, or pass allow_public_repository to record the override",
                )
            release = client.get_json(f"{base}/releases/tags/{manifest.release_tag}")
            assets = _index_assets(release)
            for entry in pending:
                try:
                    rows[entry["name"]] = _fetch_one(
                        client, entry, assets.get(entry["name"]), base, inbox, observed,
                        repository_private=repository_private, strict_tls=strict_tls,
                    )
                except OSError:
                    # Disk full, permission: files linked earlier in this run stay, so the record must exist.
                    rows[entry["name"]] = _refused("STANDINGS_TRANSPORT_WRITE_FAILED", entry)

    ordered = [rows[entry["name"]] for entry in manifest.files]
    bound = {"FETCHED", "ALREADY_PRESENT"}
    payload = {
        "schema_version": RECORD_SCHEMA,
        "parser_version": sources.STANDINGS_TRANSPORT_PARSER_VERSION,
        "license_decision": "OPERATOR_SUPPLIED",
        "repository": repo,
        "release_tag": manifest.release_tag,
        "repository_private": repository_private,
        "allow_public_repository": allow_public_repository,
        "token_source_env_name": token_env_name,
        "tls_verify_x509_strict": strict_tls,
        "manifest": {"name": manifest.name, "sha256": manifest.sha256},
        "observed_at": observed.isoformat(),
        "all_files_bound": all(row["disposition"] in bound for row in ordered),
        "counts": {
            "fetched": sum(row["disposition"] == "FETCHED" for row in ordered),
            "already_present": sum(row["disposition"] == "ALREADY_PRESENT" for row in ordered),
            "refused": sum(row["disposition"] == "REFUSED" for row in ordered),
        },
        "files": ordered,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }
    stamp = observed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    record_path = Path(record_dir) / f"standings_transport_{stamp}_{manifest.sha256[:12]}.json"
    _create_new(
        record_path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        code="STANDINGS_TRANSPORT_RECORD_EXISTS",
    )
    return TransportRecord(payload, record_path, payload["all_files_bound"])


def _index_assets(release: object) -> dict[str, dict[str, Any]]:
    assets = release.get("assets") if isinstance(release, dict) else None
    if not isinstance(assets, list):
        raise StandingsTransportError("STANDINGS_TRANSPORT_RELEASE_INVALID", "the release lists no assets array")
    indexed: dict[str, dict[str, Any]] = {}
    for asset in assets:
        name = asset.get("name") if isinstance(asset, dict) else None
        if not isinstance(name, str) or name in indexed:
            raise StandingsTransportError(
                "STANDINGS_TRANSPORT_RELEASE_INVALID", "the release has an unnamed or duplicated asset name"
            )
        indexed[name] = asset
    return indexed


def _artifact(entry: dict[str, Any], inbox: Path, observed: datetime, *, source_uri: str | None,
              coverage: dict[str, Any]) -> SourceArtifact:
    return SourceArtifact(
        artifact_id=entry["sha256"],
        path=f"{inbox.name}/{entry['name']}",
        sha256=entry["sha256"],
        byte_count=entry["byte_count"],
        source=SOURCE_LABEL,
        source_uri=source_uri,
        license_decision="OPERATOR_SUPPLIED",
        captured_at=observed,
        parser_version=sources.STANDINGS_TRANSPORT_PARSER_VERSION,
        coverage=coverage,
    )


def _present(entry: dict[str, Any], inbox: Path, observed: datetime) -> dict[str, Any]:
    artifact = _artifact(entry, inbox, observed, source_uri=None, coverage={"already_in_inbox": True})
    return _row(entry, "ALREADY_PRESENT", actual=entry["sha256"], artifact=artifact, observed=observed)


def _fetch_one(
    client: sources.AuthenticatedGithubClient,
    entry: dict[str, Any],
    asset: dict[str, Any] | None,
    base: str,
    inbox: Path,
    observed: datetime,
    *,
    repository_private: bool | None,
    strict_tls: bool,
) -> dict[str, Any]:
    expected, expected_bytes = entry["sha256"], entry["byte_count"]
    if asset is None:
        return _refused("STANDINGS_TRANSPORT_ASSET_MISSING", entry)
    asset_id = asset.get("id")
    if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 1:
        return _refused("STANDINGS_TRANSPORT_RELEASE_INVALID", entry)
    if asset.get("size") != expected_bytes:
        return _refused("STANDINGS_TRANSPORT_PUBLISHER_SIZE_DISAGREES", entry)
    digest = asset.get("digest")
    publisher_digest_checked = isinstance(digest, str) and digest.startswith("sha256:")
    if publisher_digest_checked and digest != f"sha256:{expected}":
        return _refused("STANDINGS_TRANSPORT_PUBLISHER_DIGEST_DISAGREES", entry)

    url = f"{base}/releases/assets/{asset_id}"
    sources.validate_source_reference_policy(
        url, license_decision="OPERATOR_SUPPLIED", parser_version=sources.STANDINGS_TRANSPORT_PARSER_VERSION
    )
    staging = inbox / STAGING_DIRNAME
    staging.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{entry['name']}.", suffix=".part", dir=staging)
    temporary = Path(temporary_name)
    destination = inbox / entry["name"]
    try:
        try:
            with os.fdopen(descriptor, "wb") as handle:
                download = client.download_asset(url, handle, max_bytes=expected_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        except sources.AuthenticatedFetchError as exc:
            return _refused(exc.code, entry)
        if download.sha256 != expected or download.byte_count != expected_bytes:
            return _refused("STANDINGS_TRANSPORT_HASH_MISMATCH", entry, download.sha256)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            actual = sha256_file(destination) if destination.is_file() and not destination.is_symlink() else None
            if actual == expected:
                return _present(entry, inbox, observed)
            return _refused("STANDINGS_TRANSPORT_NAME_COLLISION", entry, actual)
        except OSError:
            return _refused("STANDINGS_TRANSPORT_LINK_UNSUPPORTED", entry)
        if sha256_file(destination) != expected:
            destination.unlink(missing_ok=True)  # our own fresh link, never a pre-existing file
            return _refused("STANDINGS_TRANSPORT_HASH_MISMATCH", entry)
    finally:
        temporary.unlink(missing_ok=True)
    artifact = _artifact(
        entry,
        inbox,
        observed,
        source_uri=url,
        coverage={
            "http_status": download.http_status,
            "content_type": download.content_type,
            "resolved_uri_host": download.resolved_uri_host,
            "redirect_followed": download.redirect_followed,
            "tls_verify_x509_strict": strict_tls,
            "repository_private": repository_private,
            "publisher_digest_checked": publisher_digest_checked,
        },
    )
    return _row(entry, "FETCHED", actual=download.sha256, artifact=artifact, observed=observed)
