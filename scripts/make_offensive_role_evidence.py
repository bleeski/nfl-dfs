#!/usr/bin/env python3
"""Build the `nfl_qb_depth_role_evidence_v1` package a slate needs to name its
starting quarterbacks.

This is the "30-second script" the unresolved-material-role-change gate points
at. When a run names `OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE` (since Session
09 it leaves that person out of the pool rather than stopping), or when
`opportunity.py` has split a team's attempts across two quarterbacks on
prior-season history, this produces the source-bound package that resolves it.

Two ways in, and the choice is deliberate:

* `--capture <path>` formats bytes you already have. It never touches the
  network, which is the same shape `make_classic_weather_evidence.py` uses and
  the only shape that works in a session whose egress policy blocks the host.
* `--fetch` pulls the published artifact through `nfl_dfs.sources`, the engine's
  single approved retrieval client, which applies the host allowlist, keeps the
  raw bytes, and records the hash. No other client is used, here or anywhere.

What it writes, under `--out-dir`:

    sources/<sha256>.csv     one verbatim slice per team: the header line plus
                             that team's quarterback rows at one `dt`
    qb_depth_roles.json      the package, referencing those slices by hash

What it does not do. It does not decide anything. The depth chart's own
`pos_rank` names the starter; this script copies that ordering and the run
re-derives it from the captured bytes before believing a word of it. It writes
no share, no target, no carry, and nothing at all for a team whose quarterbacks
DraftKings does not list.

The published file is a time series — the 2026 season artifact carried 184
distinct `dt` snapshots of all 32 teams when this was written — so exactly one
snapshot is pinned. `--observed-at` selects it; the default is the most recent
one at or before `--as-of`, which is what you want on game day and what makes
the output reproducible from an archived file afterwards.

Example:

    python scripts/make_offensive_role_evidence.py \\
        --salaries DKSalaries.csv \\
        --fetch --season 2026 \\
        --out-dir data/runs/20260921-showdown-det-buf/roles
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nfl_dfs.contracts import EngineMode  # noqa: E402
from nfl_dfs.dk import parse_salaries  # noqa: E402
from nfl_dfs.qb_depth_capture import (  # noqa: E402,F401
    DEFAULT_EXPIRY,
    LICENSE_DECISION,
    NFLVERSE_RELEASE,
    ProducerError,
    _binding,
    _match_person,
    _parse_stamp,
    build_package,
    depth_chart_url,
    fetch_depth_chart,
    read_depth_chart,
    select_snapshot,
    slice_for_team,
)
from nfl_dfs.qb_depth_roles import SCHEMA_VERSION  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--salaries", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--capture", type=Path, help="a depth-chart CSV already on disk; no network"
    )
    source.add_argument(
        "--fetch", action="store_true", help="pull it through nfl_dfs.sources"
    )
    parser.add_argument("--season", type=int, help="season for --fetch")
    parser.add_argument(
        "--source-uri",
        help="where --capture came from; defaults to the published release URL",
    )
    parser.add_argument(
        "--observed-at",
        help="pin an exact `dt` snapshot; default is the latest at or before --as-of",
    )
    parser.add_argument("--as-of", help="clock for freshness, default now (UTC)")
    parser.add_argument(
        "--teams", nargs="*", help="limit to these teams; default every team on the slate"
    )
    parser.add_argument(
        "--expiry-hours",
        type=float,
        default=DEFAULT_EXPIRY.total_seconds() / 3600,
        help="how long the snapshot stays usable after it was observed",
    )
    args = parser.parse_args(argv)

    try:
        as_of = (
            datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
            if args.as_of
            else datetime.now(timezone.utc)
        )
        if as_of.tzinfo is None:
            raise ProducerError("--as-of must carry a timezone")
        as_of = as_of.astimezone(timezone.utc)
        observed_at = (
            _parse_stamp(args.observed_at) if args.observed_at else None
        )
        args.out_dir.mkdir(parents=True, exist_ok=True)

        if args.fetch:
            if not args.season:
                raise ProducerError("--fetch needs --season")
            path, upstream, uri = fetch_depth_chart(args.season, args.out_dir / "_upstream")
        else:
            path = args.capture
            if not path.is_file():
                raise ProducerError(f"--capture is not a readable file: {path}")
            upstream = hashlib.sha256(path.read_bytes()).hexdigest()
            uri = args.source_uri or (
                depth_chart_url(args.season) if args.season else None
            )
            if not uri:
                raise ProducerError(
                    "--capture needs --source-uri (or --season) so the bytes stay"
                    " traceable to where they came from"
                )

        rows, digest = read_depth_chart(path)
        if digest != upstream:
            raise ProducerError("the depth chart changed between fetch and read")
        snapshot = select_snapshot(rows, as_of=as_of, observed_at=observed_at)
        target = build_package(
            args.salaries,
            rows,
            upstream_sha256=upstream,
            source_uri=uri,
            observed_at=snapshot,
            as_of=as_of,
            out_dir=args.out_dir,
            expires_after=timedelta(hours=args.expiry_hours),
            teams=tuple(args.teams) if args.teams else None,
        )
    except ProducerError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": "QB_DEPTH_ROLE_EVIDENCE_WRITTEN",
                "package": str(target),
                "schema_version": SCHEMA_VERSION,
                "depth_chart_observed_at": snapshot.isoformat(),
                "upstream_sha256": upstream,
                "source_uri": uri,
                "does_not_establish": [
                    "TARGET_SHARE",
                    "CARRY_SHARE",
                    "OFFICIAL_ACTIVE_STATUS",
                    "MODEL_VALIDATION",
                ],
                "next": (
                    "Pass this path to select_prior_lineups as"
                    " qb_depth_role_evidence_json. NOTE: there is no `run-slate`"
                    " flag for it yet — wiring it into the request contract is"
                    " chunk P1b — so today this package is reachable from the"
                    " library entry point only. It is not an upload"
                    " authorization and it clears no other gate."
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
