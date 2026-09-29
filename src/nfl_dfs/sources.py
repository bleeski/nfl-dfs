from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import ssl
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urljoin, urlparse

import httpx

from .contracts import SourceArtifact
from .deadline import FETCH_DEFAULT_SECONDS, Budget, active_budget
from .hashing import sha256_bytes, sha256_file


class SourcePolicyError(ValueError):
    pass


class SourceDeadlineError(RuntimeError):
    """A fetch the run's budget left too little time to start (Session 07b, R31)."""


# Operator opt-in for a TLS-terminating egress proxy whose CA certificate lacks
# the X.509 Key Usage extension. Python 3.13 enables VERIFY_X509_STRICT by
# default and rejects such a chain with "CA cert does not include key usage
# extension". Setting this variable to "1" clears only that strictness flag:
# certificate verification (CERT_REQUIRED), the trust store and hostname
# checking are unchanged, so an untrusted or misnamed certificate still fails.
# The choice is recorded on every artifact the client captures
# (`coverage.tls_verify_x509_strict`), so provenance shows which runs used it.
# Default is strict. Approved by the operator on 2026-09-10 for the Cowork cloud
# container; the device VM does not need it.
TLS_NONSTRICT_CA_ENV = "NFL_DFS_TLS_ALLOW_NONSTRICT_CA"


def tls_nonstrict_ca_enabled() -> bool:
    return os.environ.get(TLS_NONSTRICT_CA_ENV, "").strip() == "1"


def build_verify_context() -> ssl.SSLContext | bool:
    """The httpx `verify` argument: default strict, or the opt-in relaxed context."""

    if not tls_nonstrict_ca_enabled():
        return True
    context = ssl.create_default_context()
    cafile = os.environ.get("SSL_CERT_FILE")
    if cafile and Path(cafile).is_file():
        context.load_verify_locations(cafile=cafile)
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if context.verify_mode is not ssl.CERT_REQUIRED or not context.check_hostname:
        raise SourcePolicyError("TLS relaxation must keep CERT_REQUIRED and hostname checking")
    return context


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
    if host == "api.github.com" and license_decision == "OPERATOR_SUPPLIED":
        # Session 17 (X2): Ben's own DraftKings downloads, moved through his own release
        # assets. The label is scoped like the DraftKings branch above: this transport's
        # parser version, and one release-asset path of an allowlisted owner. No other
        # api.github.com fetch can call itself operator-supplied.
        if parser_version != STANDINGS_TRANSPORT_PARSER_VERSION:
            raise SourcePolicyError(
                "OPERATOR_SUPPLIED on api.github.com is permitted only for the standings transport"
            )
        try:
            target = parse_authenticated_github_url(url)
        except AuthenticatedFetchError as exc:
            raise SourcePolicyError(str(exc)) from None
        if target.kind != "asset":
            raise SourcePolicyError(
                "OPERATOR_SUPPLIED on api.github.com is permitted only for a release asset"
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
    timeout_seconds: float = FETCH_DEFAULT_SECONDS,
    budget: Budget | None = None,
) -> SourceArtifact:
    """Fetch one approved artifact and keep its bytes under their hash.

    With a budget, `budget` or the one `deadline.activated` set, the timeout is
    `Budget.fetch_seconds`: `min(timeout_seconds, the improvement window)`. A
    window under its 1 s minimum starts no request and raises
    `SourceDeadlineError`, whose text is the budget's
    `DEADLINE_FETCH_WINDOW_SPENT` limitation. Every fetch is measured as stage
    `evidence_fetch`, one that raises included. Without a budget the timeout
    is `timeout_seconds`, as before.
    """

    validate_url_policy(url, optional_odds_key_configured=optional_odds_key_configured)
    active = budget if budget is not None else active_budget()
    timeout = timeout_seconds
    if active is not None:
        allowed, stopped = active.fetch_seconds(timeout_seconds, (urlparse(url).hostname or "").lower())
        if allowed is None:
            raise SourceDeadlineError(stopped)
        timeout = allowed
    headers = {"User-Agent": "nfl-dfs-local-evidence-engine/0.1 (operator-controlled)"}
    resolved_uri = url
    strict_tls = not tls_nonstrict_ca_enabled()
    measured = active.stage("evidence_fetch") if active is not None else nullcontext()
    with measured, httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        headers=headers,
        verify=build_verify_context(),
    ) as client:
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
            "tls_verify_x509_strict": strict_tls,
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


# --- Authenticated release-asset retrieval (Session 17, X2, R27) -----------------------------------
#
# The standings corpus is Ben's own DraftKings downloads, kept as release assets of a private
# repository he owns. A private asset needs a credential, so this is the one place in the engine that
# sends one. The rules that keep it from leaking, each pinned by tests/test_standings_transport.py:
#
# - the credential comes from the environment only and is sent per request, never as a client-level
#   default, only to api.github.com, and only to that repository's release endpoints;
# - the API answers an asset request with a 302 to a signed URL on the asset CDN. That hop is validated
#   by `resolve_github_release_redirect` and fetched with no credential at all;
# - the asset URL is built from the integer asset id, never taken from the release JSON;
# - a refusal names a code, a status and a host, never a header, a body, a signed URL or the token, and
#   is raised outside the `except` that saw the httpx error so no request object rides along on
#   `__context__`.
#
# The egress proxy in a cloud container terminates TLS (see TLS_NONSTRICT_CA_ENV above), so the
# credential is visible to that proxy by the platform's design. This module cannot change that.

STANDINGS_TRANSPORT_PARSER_VERSION = "standings_transport_v1"
AUTHENTICATED_GITHUB_OWNERS = frozenset({"bleeski"})
TRANSPORT_TOKEN_ENV_NAMES = ("NFL_DFS_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
GITHUB_API_HOST = "api.github.com"
MAX_API_JSON_BYTES = 8 * 1024 * 1024

_GITHUB_API_PATH = re.compile(
    r"^/repos/(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})/(?P<repo>[A-Za-z0-9][A-Za-z0-9._-]{0,99})"
    r"(?:/releases/(?:tags/(?P<tag>[A-Za-z0-9][A-Za-z0-9._-]{0,127})|assets/(?P<asset>[0-9]{1,15})))?$"
)
_TOKEN_SHAPE = re.compile(r"^[!-~]{8,255}$")


class AuthenticatedFetchError(SourcePolicyError):
    """A refusal by the authenticated transport, named by `code`; never carries a secret."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class GithubTarget:
    owner: str
    repo: str
    kind: str  # "repository", "release" or "asset"
    ref: str | None = None  # the release tag or the asset id


def parse_authenticated_github_url(url: str) -> GithubTarget:
    """Accept only https://api.github.com/repos/<allowed owner>/<repo>[/releases/...], nothing else."""

    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    matched = _GITHUB_API_PATH.fullmatch(parsed.path)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != GITHUB_API_HOST
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or matched is None
        or matched["owner"].lower() not in AUTHENTICATED_GITHUB_OWNERS
    ):
        raise AuthenticatedFetchError(
            "STANDINGS_TRANSPORT_URL_REFUSED",
            "the credential reaches only a release endpoint of an approved repository on api.github.com",
        )
    if matched["asset"] is not None:
        return GithubTarget(matched["owner"], matched["repo"], "asset", matched["asset"])
    if matched["tag"] is not None:
        return GithubTarget(matched["owner"], matched["repo"], "release", matched["tag"])
    return GithubTarget(matched["owner"], matched["repo"], "repository")


validate_authenticated_github_url = parse_authenticated_github_url


def resolve_transport_token(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """The credential and the name of the variable that held it (the name is recorded, never the value)."""

    source = os.environ if env is None else env
    for name in TRANSPORT_TOKEN_ENV_NAMES:
        token = (source.get(name) or "").strip()
        if not token:
            continue
        if not _TOKEN_SHAPE.fullmatch(token):
            raise AuthenticatedFetchError(
                "STANDINGS_TRANSPORT_CREDENTIAL_INVALID",
                f"{name} must be one printable-ASCII token with no whitespace",
            )
        return token, name
    raise AuthenticatedFetchError(
        "STANDINGS_TRANSPORT_CREDENTIAL_MISSING",
        "set one of " + ", ".join(TRANSPORT_TOKEN_ENV_NAMES) + " to a token that can read the repository",
    )


class _SuppressSignedUrlLogs(logging.Filter):
    """httpx logs every request URL at INFO; the CDN URL carries a signature that is a bearer for the bytes."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "githubusercontent.com" not in record.getMessage()


@dataclass(frozen=True)
class AssetDownload:
    sha256: str
    byte_count: int
    http_status: int
    content_type: str | None
    resolved_uri_host: str
    redirect_followed: bool


class AuthenticatedGithubClient:
    """GET-only client for one repository's release endpoints. Use as a context manager."""

    def __init__(
        self,
        *,
        token: str,
        token_env_name: str,
        transport: Any = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not _TOKEN_SHAPE.fullmatch(token):
            raise AuthenticatedFetchError(
                "STANDINGS_TRANSPORT_CREDENTIAL_INVALID", "the token must be printable ASCII with no whitespace"
            )
        self._token = token
        self.token_env_name = token_env_name
        self._transport = transport
        self._timeout = timeout_seconds
        self._client: httpx.Client | None = None
        self._log_filter = _SuppressSignedUrlLogs()
        self.tls_verify_x509_strict = not tls_nonstrict_ca_enabled()

    def __enter__(self) -> "AuthenticatedGithubClient":
        logging.getLogger("httpx").addFilter(self._log_filter)
        self._client = httpx.Client(
            timeout=self._timeout,
            follow_redirects=False,
            headers={"User-Agent": "nfl-dfs-local-evidence-engine/0.1 (operator-controlled)"},
            verify=build_verify_context(),
            transport=self._transport,
        )
        return self

    def __exit__(self, *exc: object) -> bool:
        if self._client is not None:
            self._client.close()
            self._client = None
        logging.getLogger("httpx").removeFilter(self._log_filter)
        return False

    def _refusal(self, code: str, detail: str) -> AuthenticatedFetchError:
        return AuthenticatedFetchError(code, detail.replace(self._token, "[redacted]"))

    @contextmanager
    def _stream(self, url: str, *, authenticated: bool, accept: str) -> Iterator[httpx.Response]:
        if self._client is None:
            raise RuntimeError("AuthenticatedGithubClient must be used as a context manager")
        headers = {"Accept": accept}
        if authenticated:
            headers["Authorization"] = f"Bearer {self._token}"
        host = (urlparse(url).hostname or "").lower()
        failure = None
        try:
            with self._client.stream("GET", url, headers=headers) as response:
                yield response
        except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
            failure = type(exc).__name__
            if "CERTIFICATE_VERIFY_FAILED" in str(exc) or "key usage" in str(exc):
                failure += f" (TLS trust; a TLS-terminating egress proxy needs {TLS_NONSTRICT_CA_ENV}=1)"
        if failure is not None:
            # Raised here, outside the handler, so the httpx error and its request are not chained.
            raise self._refusal("STANDINGS_TRANSPORT_NETWORK_ERROR", f"{failure} contacting {host}")

    def _chunks(self, response: httpx.Response) -> Iterator[bytes]:
        """The body in chunks; a read failure becomes a refusal raised outside the handler.

        Converted here, in the caller's own frame, rather than left to `_stream`: an error thrown into
        that generator while the caller's `with` body runs would chain the httpx error, and its request,
        onto the refusal.
        """

        host = (response.url.host or "").lower()
        failure = None
        try:
            yield from response.iter_bytes(65536)
        except (httpx.HTTPError, httpx.StreamError) as exc:
            failure = type(exc).__name__
        if failure is not None:
            raise self._refusal("STANDINGS_TRANSPORT_NETWORK_ERROR", f"{failure} reading from {host}")

    def _require_ok(self, response: httpx.Response) -> None:
        if response.status_code != 200:
            host = (response.url.host or "").lower()
            hint = {
                401: " (the token is not accepted)",
                403: " (the token may lack read access to the repository)",
                404: " (no such repository, release or asset, or the token cannot see it)",
            }.get(response.status_code, "")
            raise self._refusal(
                "STANDINGS_TRANSPORT_HTTP_STATUS", f"HTTP {response.status_code} from {host}{hint}"
            )

    def get_json(self, url: str) -> Any:
        """One JSON document from an approved repository endpoint (repository or release)."""

        target = parse_authenticated_github_url(url)
        if target.kind == "asset":
            raise self._refusal("STANDINGS_TRANSPORT_URL_REFUSED", "an asset is downloaded, not read as JSON")
        body = bytearray()
        with self._stream(url, authenticated=True, accept="application/vnd.github+json") as response:
            self._require_ok(response)
            for chunk in self._chunks(response):
                body.extend(chunk)
                if len(body) > MAX_API_JSON_BYTES:
                    raise self._refusal("STANDINGS_TRANSPORT_RESPONSE_INVALID", "API answer exceeds its size cap")
        try:
            return json.loads(bytes(body).decode("utf-8"))
        except ValueError:
            pass
        raise self._refusal("STANDINGS_TRANSPORT_RESPONSE_INVALID", "API answer is not JSON")

    def download_asset(self, url: str, sink: BinaryIO, *, max_bytes: int) -> AssetDownload:
        """Stream one release asset into `sink`, hashing as it arrives, cut off past `max_bytes`."""

        if parse_authenticated_github_url(url).kind != "asset":
            raise self._refusal("STANDINGS_TRANSPORT_URL_REFUSED", "not a release-asset URL")
        octet = "application/octet-stream"
        location = None
        with self._stream(url, authenticated=True, accept=octet) as response:
            if not response.is_redirect:
                return self._consume(response, sink, max_bytes, redirected=False)
            location = response.headers.get("location", "")
        refused = False
        try:
            resolved = resolve_github_release_redirect(url, location)
        except SourcePolicyError:
            refused = True
        if refused:
            raise self._refusal(
                "STANDINGS_TRANSPORT_REDIRECT_REFUSED", "redirect target is not the approved release-asset host"
            )
        with self._stream(resolved, authenticated=False, accept=octet) as response:
            if response.is_redirect:
                raise self._refusal(
                    "STANDINGS_TRANSPORT_REDIRECT_REFUSED", "the release-asset host answered with a further redirect"
                )
            return self._consume(response, sink, max_bytes, redirected=True)

    def _consume(
        self, response: httpx.Response, sink: BinaryIO, max_bytes: int, *, redirected: bool
    ) -> AssetDownload:
        self._require_ok(response)
        media = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if media == "application/json" or media.endswith("+json") or media == "text/html":
            raise self._refusal(
                "STANDINGS_TRANSPORT_ASSET_NOT_BINARY", f"the asset endpoint answered {media}, not file bytes"
            )
        digest = hashlib.sha256()
        count = 0
        for chunk in self._chunks(response):
            count += len(chunk)
            if count > max_bytes:
                raise self._refusal(
                    "STANDINGS_TRANSPORT_ASSET_TOO_LARGE", f"more than the {max_bytes} bytes the manifest states"
                )
            digest.update(chunk)
            sink.write(chunk)
        return AssetDownload(
            sha256=digest.hexdigest(),
            byte_count=count,
            http_status=response.status_code,
            content_type=media or None,
            resolved_uri_host=(response.url.host or "").lower(),
            redirect_followed=redirected,
        )
