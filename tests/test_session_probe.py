"""Acceptance for `scripts/session_probe.py`.

The probe exists because a live slate was lost walking into an unreachable host
instead of asking first. Its value depends on two properties that are easy to
break silently: the host list it probes must be the real allowlist, and a host
added to the allowlist must not become a silently-required, undescribed gate.
Both are asserted here. Nothing in this module touches the network.
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PROBE_PATH = REPO_ROOT / "scripts" / "session_probe.py"


def _load_probe():
    """Import the script by path; `scripts/` is not a package."""

    spec = importlib.util.spec_from_file_location("session_probe", PROBE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["session_probe"] = module
    spec.loader.exec_module(module)
    return module


probe_module = _load_probe()


def test_allowed_hosts_parsed_without_importing_matches_the_real_allowlist():
    """The probe parses sources.py; drift between the two would make it lie."""

    from nfl_dfs.sources import ALLOWED_HOSTS

    assert set(probe_module.allowed_hosts()) == set(ALLOWED_HOSTS)


def test_every_allowlisted_host_has_a_declared_role():
    """A new allowlisted host must be classified deliberately.

    `HOST_ROLE` decides whether an unreachable host fails the verdict. An
    unlisted host defaults to required, which is the safe direction, but it
    would print "(role not declared)" to an operator under a lock clock. Force
    the decision here instead.
    """

    from nfl_dfs.sources import ALLOWED_HOSTS

    undeclared = sorted(set(ALLOWED_HOSTS) - set(probe_module.HOST_ROLE))
    assert not undeclared, f"add these to HOST_ROLE with a gate and a required flag: {undeclared}"


def test_weather_host_is_required_for_a_classic_run():
    """Regression on the 2026-09-20 loss: this host must fail the verdict."""

    gate, required = probe_module.HOST_ROLE["api.weather.gov"]
    assert required is True
    assert "weather" in gate.lower()


def test_proxy_403_is_reported_as_an_egress_block_not_a_dead_host(monkeypatch):
    """The operator has to tell policy refusal apart from an outage."""

    def raise_403(*_args, **_kwargs):
        raise urllib.error.URLError("Tunnel connection failed: 403 Forbidden")

    monkeypatch.setattr(probe_module.urllib.request, "urlopen", raise_403)
    result = probe_module.probe("api.weather.gov")
    assert result["reachable"] is False
    assert str(result["detail"]).startswith("EGRESS_BLOCKED")
    assert "route around" in str(result["hint"])


def test_http_error_status_still_counts_as_reachable(monkeypatch):
    """A 400 from a bare root path proves the tunnel opened."""

    def raise_400(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://github.com/", 400, "Bad Request", {}, None)

    monkeypatch.setattr(probe_module.urllib.request, "urlopen", raise_400)
    result = probe_module.probe("github.com")
    assert result["reachable"] is True
    assert result["detail"] == "HTTP 400"


def test_tls_nonstrict_ca_opt_in_is_off_by_default(monkeypatch):
    """Default is strict: `urlopen` gets no relaxed context."""

    monkeypatch.delenv("NFL_DFS_TLS_ALLOW_NONSTRICT_CA", raising=False)
    assert probe_module.tls_nonstrict_ca_enabled() is False
    assert probe_module.verify_context() is None


def test_tls_nonstrict_ca_opt_in_is_honored(monkeypatch):
    """The 2026-09-27 defect: this probe ignored the approved opt-in and
    reported github.com and raw.githubusercontent.com as `TLS_FAILED` in a
    container whose proxy CA needs it, while the same run's nflverse fetches
    through `sources.py` succeeded on the same host seconds later. `probe`
    must pass the same relaxed context `sources.build_verify_context` builds,
    with `VERIFY_X509_STRICT` cleared and nothing else changed.
    """

    import ssl

    monkeypatch.setenv("NFL_DFS_TLS_ALLOW_NONSTRICT_CA", "1")
    context = probe_module.verify_context()
    assert isinstance(context, ssl.SSLContext)
    assert not (context.verify_flags & ssl.VERIFY_X509_STRICT)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True

    seen = {}

    def capture(_request, timeout=None, context=None):
        seen["context"] = context
        raise urllib.error.HTTPError("https://github.com/", 200, "OK", {}, None)

    monkeypatch.setattr(probe_module.urllib.request, "urlopen", capture)
    probe_module.probe("github.com")
    assert seen["context"] is context or (
        isinstance(seen["context"], ssl.SSLContext)
        and not (seen["context"].verify_flags & ssl.VERIFY_X509_STRICT)
    )


def _salary_csv(path: Path, rows: list[tuple[str, str]]) -> Path:
    header = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
    body = "".join(
        f"RB,P{i} ({i}),P{i},{i},RB/FLEX,5000,{game} {kick},AAA,0,\n"
        for i, (game, kick) in enumerate(rows)
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def test_lock_is_the_earliest_kickoff_not_the_latest(tmp_path):
    """A Classic file carries one kickoff per game and locks at the first."""

    day = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%m/%d/%Y")
    path = _salary_csv(
        tmp_path / "sal.csv",
        [
            ("AAA@BBB", f"{day} 04:25PM ET"),
            ("CCC@DDD", f"{day} 01:00PM ET"),
            ("EEE@FFF", f"{day} 08:20PM ET"),
        ],
    )
    slate = probe_module.read_slate(path)
    assert slate["games"] == 3
    assert slate["format"] == "CLASSIC"
    assert slate["lock_et"].endswith("13:00:00-04:00") or "13:00:00" in slate["lock_et"]
    assert slate["weather_captures_needed_at_most"] == 3


def test_single_game_file_is_reported_as_showdown(tmp_path):
    day = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%m/%d/%Y")
    path = _salary_csv(tmp_path / "sd.csv", [("AAA@BBB", f"{day} 08:20PM ET")])
    assert probe_module.read_slate(path)["format"] == "SHOWDOWN"


def test_minutes_to_lock_is_measured_from_now(tmp_path):
    """The 2026-09-20 session estimated elapsed time and drifted 45 minutes."""

    future = datetime.now(timezone.utc) + timedelta(days=2)
    day = future.strftime("%m/%d/%Y")
    path = _salary_csv(tmp_path / "sal.csv", [("AAA@BBB", f"{day} 01:00PM ET")])
    slate = probe_module.read_slate(path)
    assert slate["minutes_to_lock"] > 0
    assert slate["minutes_to_lock"] == pytest.approx(48 * 60, abs=24 * 60)


def test_empty_salary_file_is_a_named_stop(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("Position,Name,ID,Salary,Game Info\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        probe_module.read_slate(path)
