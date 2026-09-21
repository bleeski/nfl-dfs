#!/usr/bin/env python3
"""Report which evidence gates *this session* can clear, before a slate is run.

Standard library only, and it imports nothing from `nfl_dfs`, so it runs in a
cold container before `setup` and answers in about ten seconds.

Why this exists. On 2026-09-20 a live 13-game Classic slate was lost because
`api.weather.gov` was blocked by the session's egress proxy. The block was
found roughly twenty minutes in, by walking into it, and the walking cost most
of the working window before lock. Nothing in the repository answered the
question "can this session reach the hosts its gates require", and
`src/nfl_dfs/preflight.py` answers a different question: it is a pre-UPLOAD
check on an already-built package, not a pre-RUN check on session capability.

What it does, in order:

* reads `ALLOWED_HOSTS` out of `src/nfl_dfs/sources.py` by parsing the source,
  never by importing it, so the list cannot drift from the real allowlist and
  the probe still runs when the package will not import;
* probes each host over HTTPS through whatever proxy the environment sets,
  recording the outcome and separating "the policy refused me" from "the host
  is down" from "TLS is misconfigured";
* optionally reads a DraftKings salary CSV to report the slate shape and the
  lock clock, so the window is measured rather than estimated.

What it does not do: fetch evidence, judge a source, or clear anything. It only
reports what is reachable. A gate it reports as unclearable is still a gate.

Exit codes:
    0  every host a run needs is reachable
    2  at least one required host is unreachable; a full run cannot complete
    1  usage or parse error

Example:

    python3 scripts/session_probe.py --salaries DKSalaries.csv
"""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_PY = REPO_ROOT / "src" / "nfl_dfs" / "sources.py"

# Which gate each host feeds, and whether a Classic run can finish without it.
# `api.sleeper.app` and `api.the-odds-api.com` are allowlisted but no current
# prior-only Classic path requires them, so they are probed and reported without
# being counted against the verdict.
HOST_ROLE = {
    "github.com": ("nflverse prior artifacts (release downloads)", True),
    "raw.githubusercontent.com": ("nflverse prior artifacts (nfldata)", True),
    "api.github.com": ("GitHub API", False),
    "api.weather.gov": ("per-game Classic weather captures", True),
    "api.sleeper.app": ("not required by the prior-only Classic path", False),
    "api.the-odds-api.com": ("optional odds adapter, needs a user key", False),
}

UA = "nfl-dfs-session-probe/1.0"
TIMEOUT = 8


def allowed_hosts() -> list[str]:
    """Read ALLOWED_HOSTS from sources.py by parsing it, never by importing."""

    try:
        tree = ast.parse(SOURCES_PY.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise SystemExit(f"cannot parse {SOURCES_PY}: {exc}")
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "ALLOWED_HOSTS":
                try:
                    return sorted(ast.literal_eval(node.value))
                except ValueError as exc:
                    raise SystemExit(f"ALLOWED_HOSTS is not a literal: {exc}")
    raise SystemExit(f"ALLOWED_HOSTS not found in {SOURCES_PY}")


def probe(host: str) -> dict[str, object]:
    """Classify one host as reachable, policy-blocked, TLS-broken or down."""

    url = f"https://{host}/"
    request = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return {"host": host, "reachable": True, "detail": f"HTTP {response.status}"}
    except urllib.error.HTTPError as exc:
        # An HTTP status means the tunnel opened and the origin answered. 400 or
        # 404 from a bare root path is still proof of reachability.
        return {"host": host, "reachable": True, "detail": f"HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        reason = exc.reason
        text = str(reason)
        if isinstance(reason, ssl.SSLError) or "CERTIFICATE" in text.upper():
            return {
                "host": host,
                "reachable": False,
                "detail": f"TLS_FAILED: {text}",
                "hint": "point the tool at the proxy CA bundle; never disable verification",
            }
        if "403" in text or "407" in text or "tunnel" in text.lower():
            return {
                "host": host,
                "reachable": False,
                "detail": f"EGRESS_BLOCKED: {text}",
                "hint": "organization egress policy refused this host; do not route around it",
            }
        return {"host": host, "reachable": False, "detail": f"UNREACHABLE: {text}"}
    except (socket.timeout, TimeoutError):
        return {"host": host, "reachable": False, "detail": f"TIMEOUT after {TIMEOUT}s"}
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        return {"host": host, "reachable": False, "detail": f"{type(exc).__name__}: {exc}"}


def read_slate(path: Path) -> dict[str, object]:
    """Summarize the salary CSV: games, people, and the lock, which is the
    EARLIEST kickoff on a Classic file, not the latest."""

    from zoneinfo import ZoneInfo

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"salary CSV has no rows: {path}")

    eastern = ZoneInfo("America/New_York")
    games: set[str] = set()
    kickoffs: list[datetime] = []
    for row in rows:
        cell = (row.get("Game Info") or "").strip()
        parts = cell.split()
        if len(parts) < 3:
            continue
        games.add(parts[0])
        try:
            naive = datetime.strptime(" ".join(parts[1:3]), "%m/%d/%Y %I:%M%p")
        except ValueError:
            continue
        kickoffs.append(naive.replace(tzinfo=eastern))

    lock = min(kickoffs) if kickoffs else None
    now = datetime.now(timezone.utc)
    return {
        "people": len(rows),
        "games": len(games),
        "format": "SHOWDOWN" if len(games) <= 1 else "CLASSIC",
        "lock_et": lock.isoformat() if lock else None,
        "minutes_to_lock": round((lock - now).total_seconds() / 60, 1) if lock else None,
        "weather_captures_needed_at_most": len(games),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salaries", help="DraftKings salary CSV, for slate shape and lock clock")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()

    hosts = allowed_hosts()
    with ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        results = list(pool.map(probe, hosts))

    unknown = [h for h in hosts if h not in HOST_ROLE]
    blocking = [
        r for r in results
        if not r["reachable"] and HOST_ROLE.get(str(r["host"]), ("", True))[1]
    ]

    slate = None
    if args.salaries:
        slate = read_slate(Path(args.salaries))

    report: dict[str, object] = {
        "proxy": os.environ.get("HTTPS_PROXY") or None,
        "hosts": results,
        "hosts_without_a_declared_role": unknown,
        "slate": slate,
        "verdict": "CAN_COMPLETE_A_RUN" if not blocking else "CANNOT_COMPLETE_A_RUN",
        "blocking_hosts": [
            {"host": r["host"], "gate": HOST_ROLE[str(r["host"])][0], "detail": r["detail"]}
            for r in blocking
        ],
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 2 if blocking else 0

    print(f"{'HOST':28} {'OK':4} DETAIL")
    print("-" * 78)
    for r in sorted(results, key=lambda x: str(x["host"])):
        role, required = HOST_ROLE.get(str(r["host"]), ("(role not declared)", True))
        mark = "yes" if r["reachable"] else ("NO" if required else "no")
        print(f"{r['host']:28} {mark:4} {r['detail']}")
        if not r["reachable"]:
            print(f"{'':33}gate: {role}")
            if r.get("hint"):
                print(f"{'':33}{r['hint']}")
    if unknown:
        print(f"\nallowlisted but no declared role in this probe: {unknown}")
        print("treated as required; add them to HOST_ROLE.")

    if slate:
        print(
            f"\nslate: {slate['format']}, {slate['games']} games, {slate['people']} people"
            f"\nlock:  {slate['lock_et']} (earliest kickoff)"
            f"\nwindow:{slate['minutes_to_lock']} minutes from now"
            f"\nweather captures needed: up to {slate['weather_captures_needed_at_most']}"
            " (one per non-dome game)"
        )

    print(f"\nVERDICT: {report['verdict']}")
    for b in report["blocking_hosts"]:
        print(f"  blocked: {b['host']} -> {b['gate']}")
    if blocking:
        print(
            "\nA full run cannot finish in this session. Decide now, not at the gate:"
            "\n  - capture the missing evidence somewhere that can reach the host, or"
            "\n  - run the slate from a session that can."
            "\nNever invent an observation to clear the gate."
        )
        if any(b["host"] == "api.weather.gov" for b in report["blocking_hosts"]):
            # The one blocked host with a ready answer. Naming the commands beats
            # describing the idea: on 2026-09-20 this chain existed, was stdlib
            # only, and went unused on two lost slates.
            print(
                "\nFor api.weather.gov specifically, the capture does not have to"
                "\nhappen here. On a machine that reaches the host (the Windows"
                "\ndesktop), inside six hours of lock:"
                "\n  python3 scripts/fetch_weather_captures.py \\"
                "\n      --salaries <the salary CSV> --out-dir <run>/weather"
                "\n  python3 scripts/make_classic_weather_evidence.py \\"
                "\n      --salaries <the salary CSV> --plan <run>/weather/plan.json \\"
                "\n      --out-dir <run>/weather"
                "\nthen pass the result to run-slate as --weather-evidence-json."
            )
    return 2 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
