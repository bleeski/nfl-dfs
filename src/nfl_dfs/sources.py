from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from .contracts import SourceArtifact
from .hashing import sha256_bytes, sha256_file


class SourcePolicyError(ValueError):
    pass


ALLOWED_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "api.github.com",
    "api.sleeper.app",
    "api.weather.gov",
    "api.the-odds-api.com",
}
PROHIBITED_HOSTS = {"nfl.com", "www.nfl.com", "draftkings.com", "www.draftkings.com"}

# Every nflverse dataset is published as a GitHub release asset, and GitHub
# answers a release-download URL with a 302 to its own signed asset CDN. The
# redirect target carries a short-lived signature, so it can never be pinned in
# ALLOWED_HOSTS as a source in its own right. These hosts are therefore
# reachable only as the single permitted hop out of an already-approved
# github.com release-download URL, and the artifact's recorded source_uri stays
# the canonical github.com URL that was requested.
GITHUB_RELEASE_ASSET_HOSTS = {
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}


def is_github_release_download(url: str) -> bool:
    """Report whether a URL is a github.com release-asset download path."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "github.com":
        return False
    segments = [segment for segment in parsed.path.split("/") if segment]
    return (
        len(segments) >= 5
        and segments[2] == "releases"
        and segments[3] == "download"
    )


def resolve_github_release_redirect(url: str, location: str) -> str:
    """Validate and return the single permitted GitHub release-asset hop."""

    if not location:
        raise SourcePolicyError("release-asset redirect carried no Location header")
    target = urljoin(url, location)
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or host not in GITHUB_RELEASE_ASSET_HOSTS
    ):
        raise SourcePolicyError(
            f"release-asset redirect target is not an approved GitHub asset host: {host}"
        )
    return target


def validate_source_reference_policy(
    url: str,
    *,
    license_decision: str,
    parser_version: str,
) -> None:
    """Validate provenance references without authorizing a network retrieval."""

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SourcePolicyError("source references require an HTTPS URI without credentials")
    if host in {"draftkings.com", "www.draftkings.com"}:
        if license_decision != "OPERATOR_SUPPLIED" or parser_version != "dk_csv_v1":
            raise SourcePolicyError(
                "DraftKings references are permitted only for operator-supplied CSV bytes"
            )
        return
    validate_url_policy(
        url,
        optional_odds_key_configured=(host == "api.the-odds-api.com"),
    )
    permitted_licenses = {
        "github.com": {"PERMITTED_REPOSITORY_LICENSE"},
        "raw.githubusercontent.com": {"PERMITTED_REPOSITORY_LICENSE"},
        "api.github.com": {"PERMITTED_REPOSITORY_LICENSE"},
        "api.sleeper.app": {"SECONDARY_STATUS_ONLY"},
        "api.weather.gov": {"PUBLIC_DOMAIN", "PERMITTED_PUBLIC_API"},
        "api.the-odds-api.com": {"PERMITTED_PUBLIC_API"},
    }[host]
    if license_decision not in permitted_licenses:
        raise SourcePolicyError(
            f"license decision {license_decision!r} is not approved for {host}"
        )


def capture_local_artifact(
    path: str | Path,
    *,
    source: str,
    license_decision: str,
    parser_version: str,
    coverage: dict | None = None,
) -> SourceArtifact:
    artifact_path = Path(path).resolve()
    digest = sha256_file(artifact_path)
    return SourceArtifact(
        artifact_id=digest,
        path=str(artifact_path),
        sha256=digest,
        byte_count=artifact_path.stat().st_size,
        source=source,
        license_decision=license_decision,
        captured_at=datetime.now(timezone.utc),
        parser_version=parser_version,
        coverage=coverage or {},
    )


def validate_url_policy(url: str, *, optional_odds_key_configured: bool = False) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise SourcePolicyError("only HTTPS sources are permitted")
    if host in PROHIBITED_HOSTS:
        raise SourcePolicyError(f"systematic retrieval from {host} is prohibited by engine policy")
    if host not in ALLOWED_HOSTS:
        raise SourcePolicyError(f"host is not approved: {host}")
    if host == "api.the-odds-api.com" and not optional_odds_key_configured:
        raise SourcePolicyError("Odds API adapter requires an explicitly configured user-supplied free key")


def fetch_public_artifact(
    url: str,
    destination_dir: str | Path,
    *,
    source: str,
    license_decision: str,
    parser_version: str,
    optional_odds_key_configured: bool = False,
    timeout_seconds: float = 30.0,
) -> SourceArtifact:
    validate_url_policy(url, optional_odds_key_configured=optional_odds_key_configured)
    headers = {"User-Agent": "nfl-dfs-local-evidence-engine/0.1 (operator-controlled)"}
    resolved_uri = url
    with httpx.Client(timeout=timeout_seconds, follow_redirects=False, headers=headers) as client:
        response = client.get(url)
        if response.is_redirect and is_github_release_download(url):
            resolved_uri = resolve_github_release_redirect(
                url, response.headers.get("location", "")
            )
            response = client.get(resolved_uri)
        if response.is_redirect:
            # Without this an unfollowed redirect passes raise_for_status and
            # yields an empty artifact that would be hashed as if it were data.
            raise SourcePolicyError(
                f"refusing to follow a redirect from {url} to "
                f"{response.headers.get('location', '')!r}"
            )
        response.raise_for_status()
        data = response.content
    digest = sha256_bytes(data)
    suffix = Path(urlparse(url).path).suffix or ".bin"
    if len(suffix) > 10 or any(
        not (character.isalnum() or character == ".") for character in suffix
    ):
        suffix = ".bin"
    destination = Path(destination_dir).resolve() / f"{digest}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(destination)
    if sha256_file(destination) != digest:
        raise RuntimeError("downloaded artifact hash mismatch")
    return SourceArtifact(
        artifact_id=digest,
        path=str(destination),
        sha256=digest,
        byte_count=len(data),
        source=source,
        source_uri=url,
        license_decision=license_decision,
        captured_at=datetime.now(timezone.utc),
        parser_version=parser_version,
        coverage={
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "resolved_uri_host": (urlparse(resolved_uri).hostname or "").lower(),
            "redirect_followed": resolved_uri != url,
        },
    )


def sleeper_daily_player_snapshot(destination_dir: str | Path, as_of_date: str) -> SourceArtifact:
    directory = Path(destination_dir).resolve()
    marker = directory / f"sleeper_players_{as_of_date}.json"
    if marker.exists():
        return capture_local_artifact(
            marker,
            source="SLEEPER_DAILY_SECONDARY",
            license_decision="SECONDARY_STATUS_ONLY",
            parser_version="sleeper_players_v1",
        )
    artifact = fetch_public_artifact(
        "https://api.sleeper.app/v1/players/nfl",
        directory,
        source="SLEEPER_DAILY_SECONDARY",
        license_decision="SECONDARY_STATUS_ONLY",
        parser_version="sleeper_players_v1",
    )
    raw = Path(artifact.path).read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    marker.write_bytes(raw)
    return capture_local_artifact(
        marker,
        source="SLEEPER_DAILY_SECONDARY",
        license_decision="SECONDARY_STATUS_ONLY",
        parser_version="sleeper_players_v1",
        coverage={"players": len(payload), "at_most_once_daily": True},
    )
