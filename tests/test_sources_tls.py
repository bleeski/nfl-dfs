"""The operator-approved TLS relaxation in `sources.py` (2026-09-10).

Strict by default. With `NFL_DFS_TLS_ALLOW_NONSTRICT_CA=1` only the X.509
strictness flag is cleared; certificate verification and hostname checking stay
on, and every captured artifact records which mode produced it.
"""

from __future__ import annotations

import ssl

import pytest

from nfl_dfs import sources


def test_default_verify_is_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(sources.TLS_NONSTRICT_CA_ENV, raising=False)
    assert sources.tls_nonstrict_ca_enabled() is False
    assert sources.build_verify_context() is True


@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_only_the_literal_one_enables_the_relaxation(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(sources.TLS_NONSTRICT_CA_ENV, value)
    assert sources.tls_nonstrict_ca_enabled() is False
    assert sources.build_verify_context() is True


def test_relaxed_context_keeps_verification_and_hostname_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(sources.TLS_NONSTRICT_CA_ENV, "1")
    context = sources.build_verify_context()
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert not (context.verify_flags & ssl.VERIFY_X509_STRICT)


def test_capture_records_the_tls_mode_in_coverage(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    class _Response:
        status_code = 200
        headers = {"content-type": "text/csv"}
        content = b"a,b\n1,2\n"
        is_redirect = False

        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            return _Response()

    seen: list[dict] = []

    def factory(**kwargs):
        seen.append(kwargs)
        return _Client(**kwargs)

    monkeypatch.setattr(sources.httpx, "Client", factory)
    monkeypatch.delenv(sources.TLS_NONSTRICT_CA_ENV, raising=False)
    strict = sources.fetch_public_artifact(
        "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
        tmp_path / "strict",
        source="TEST",
        license_decision="PERMITTED_REPOSITORY_LICENSE",
        parser_version="test_v1",
    )
    assert seen[-1]["verify"] is True
    assert strict.coverage["tls_verify_x509_strict"] is True

    monkeypatch.setenv(sources.TLS_NONSTRICT_CA_ENV, "1")
    relaxed = sources.fetch_public_artifact(
        "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
        tmp_path / "relaxed",
        source="TEST",
        license_decision="PERMITTED_REPOSITORY_LICENSE",
        parser_version="test_v1",
    )
    assert isinstance(seen[-1]["verify"], ssl.SSLContext)
    assert relaxed.coverage["tls_verify_x509_strict"] is False
    # Same bytes, same hash: the TLS mode is provenance, not content.
    assert relaxed.sha256 == strict.sha256
