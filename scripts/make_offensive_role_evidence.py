#!/usr/bin/env python3
"""Build the `nfl_qb_depth_role_evidence_v1` package a slate needs to name its
starting quarterbacks.

This is the "30-second script" the unresolved-material-role-change gate points
at. When a run stops with `OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE`, or when
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
from nfl_dfs.qb_depth_roles import (  # noqa: E402
    ALLOCATION_VERSION,
    DEPTH_CHART_COLUMNS,
    PARSER_VERSION,
    QUARTERBACK_ABBREVIATION,
    SCHEMA_VERSION,
    TRANSFORMATION_VERSION,
)

NFLVERSE_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
LICENSE_DECISION = "PERMITTED_REPOSITORY_LICENSE"
# A depth chart is re-published through the week and a stale one is exactly the
# failure this package exists to prevent, so the window is short and the run
# re-checks it at selection time as well as here.
DEFAULT_EXPIRY = timedelta(hours=36)


class ProducerError(RuntimeError):
    """A named refusal, printed rather than raised as a traceback."""


def depth_chart_url(season: int) -> str:
    return f"{NFLVERSE_RELEASE}/depth_charts/depth_charts_{season}.csv"


def fetch_depth_chart(season: int, destination: Path) -> tuple[Path, str, str]:
    """Pull the published artifact through the engine's only approved client."""

    from nfl_dfs.sources import fetch_public_artifact

    url = depth_chart_url(season)
    artifact = fetch_public_artifact(
        url,
        destination,
        source="nflverse_depth_charts",
        license_decision=LICENSE_DECISION,
        parser_version=PARSER_VERSION,
    )
    return Path(artifact.path), artifact.sha256, url


def read_depth_chart(path: Path) -> tuple[tuple[dict[str, str], ...], str]:
    """Read every row, and the digest of the exact bytes they were read from."""

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(encoding="utf-8", errors="strict", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ProducerError(f"depth chart is empty: {path}") from exc
        if tuple(header) != DEPTH_CHART_COLUMNS:
            raise ProducerError(
                "depth chart columns are not the ones this parser version was"
                f" written for.\n  expected: {','.join(DEPTH_CHART_COLUMNS)}"
                f"\n  found:    {','.join(header)}\n"
                "This is a schema change upstream, not a bad download. Stop and"
                " register a new parser version rather than editing the file."
            )
        rows = tuple(
            dict(zip(DEPTH_CHART_COLUMNS, raw))
            for raw in reader
            if len(raw) == len(DEPTH_CHART_COLUMNS)
        )
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ProducerError(f"depth chart changed while it was being read: {path}")
    return rows, digest


def _parse_stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ProducerError(f"depth chart `dt` is not timezone-aware: {value!r}")
    return parsed.astimezone(timezone.utc)


def select_snapshot(
    rows: tuple[dict[str, str], ...],
    *,
    as_of: datetime,
    observed_at: datetime | None,
) -> datetime:
    """Pin exactly one `dt`, so the package is never ambiguous about which."""

    stamps = sorted({_parse_stamp(row["dt"]) for row in rows})
    if not stamps:
        raise ProducerError("depth chart carries no rows")
    if observed_at is not None:
        if observed_at not in stamps:
            raise ProducerError(
                f"no depth-chart snapshot at {observed_at.isoformat()}."
                f" Nearest available: {[s.isoformat() for s in stamps[-5:]]}"
            )
        return observed_at
    usable = [stamp for stamp in stamps if stamp <= as_of]
    if not usable:
        raise ProducerError(
            f"every depth-chart snapshot is later than --as-of {as_of.isoformat()};"
            " the capture is from the future relative to the clock you gave"
        )
    return usable[-1]


def slice_for_team(
    rows: tuple[dict[str, str], ...],
    *,
    team: str,
    observed_at: datetime,
) -> str:
    """The header plus this team's quarterback rows, verbatim, in rank order."""

    selected = [
        row
        for row in rows
        if row["team"].strip().upper() == team
        and row["pos_abb"].strip().upper() == QUARTERBACK_ABBREVIATION
        and _parse_stamp(row["dt"]) == observed_at
    ]
    if not selected:
        raise ProducerError(
            f"the depth chart lists no quarterback for {team} at"
            f" {observed_at.isoformat()}"
        )
    selected.sort(key=lambda row: int(row["pos_rank"]))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(DEPTH_CHART_COLUMNS)
    writer.writerows([row[column] for column in DEPTH_CHART_COLUMNS] for row in selected)
    return buffer.getvalue()


def _binding(rows_by_role: dict[str, object], mode: EngineMode) -> dict[str, object]:
    if mode is EngineMode.SHOWDOWN:
        return {
            "cpt_dk_id": rows_by_role["CPT"].dk_id,
            "flex_dk_id": rows_by_role["FLEX"].dk_id,
        }
    only = next(iter(rows_by_role.values()))
    return {"dk_id": only.dk_id}


def build_package(
    salaries: Path,
    rows: tuple[dict[str, str], ...],
    *,
    upstream_sha256: str,
    source_uri: str,
    observed_at: datetime,
    as_of: datetime,
    out_dir: Path,
    expires_after: timedelta = DEFAULT_EXPIRY,
    teams: tuple[str, ...] | None = None,
) -> Path:
    slate = parse_salaries(salaries)
    quarterbacks: dict[str, dict[str, object]] = {}
    for player in slate.players:
        if player.position != "QB":
            continue
        bucket = quarterbacks.setdefault(
            player.underlying_id,
            {"team": player.team, "game_id": player.game_id, "name": player.name, "rows": {}},
        )
        bucket["rows"][player.role or "FLEX"] = player

    wanted = sorted({str(detail["team"]) for detail in quarterbacks.values()})
    if teams:
        missing = sorted(set(teams) - set(wanted))
        if missing:
            raise ProducerError(
                f"--teams names teams with no quarterback on this slate: {missing}"
            )
        wanted = sorted(teams)

    sources_dir = out_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, object]] = []
    declarations: list[dict[str, object]] = []

    for team in wanted:
        excerpt = slice_for_team(rows, team=team, observed_at=observed_at)
        digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        capture = sources_dir / f"{digest}.csv"
        capture.write_text(excerpt, encoding="utf-8")
        sources.append(
            {
                "path": f"sources/{capture.name}",
                "sha256": digest,
                "source_uri": source_uri,
                # The snapshot's own timestamp, never the time this ran. A
                # depth chart observed on Thursday is Thursday's evidence
                # whenever it happens to be formatted.
                "observed_at": observed_at.isoformat(),
                "captured_at": as_of.isoformat(),
                "expires_at": (observed_at + expires_after).isoformat(),
                "license_decision": LICENSE_DECISION,
                "parser_version": PARSER_VERSION,
                "transformation_version": TRANSFORMATION_VERSION,
                "support_kind": "DEPTH_CHART_ORDER",
                "supporting_excerpt": excerpt,
                "synthetic": False,
                "upstream_sha256": upstream_sha256,
            }
        )

        ordered = []
        for row in csv.DictReader(io.StringIO(excerpt)):
            person = _match_person(row, team, quarterbacks)
            ordered.append(
                {
                    **_binding(quarterbacks[person]["rows"], slate.mode),
                    "underlying_id": person,
                    "provider_player_id": row["gsis_id"].strip(),
                    "player_name": row["player_name"].strip(),
                    "pos_rank": int(row["pos_rank"]),
                }
            )
        ordered.sort(key=lambda entry: entry["pos_rank"])
        if ordered[0]["pos_rank"] != 1:
            raise ProducerError(
                f"{team}'s depth chart has no rank-1 quarterback at"
                f" {observed_at.isoformat()}; it does not establish a starter"
            )
        # DraftKings routinely sells a third-string quarterback the published
        # depth chart does not name. Measured on the 2026-09-17 DET@BUF slate:
        # three Buffalo quarterbacks priced, two on the chart. He is declared
        # explicitly as unlisted rather than silently dropped or called a
        # backup, because "no source places him" and "the chart ranks him third"
        # are different claims and only one of them is true.
        ranked = {entry["underlying_id"] for entry in ordered}
        unlisted = [
            {
                **_binding(detail["rows"], slate.mode),
                "underlying_id": person,
                "player_name": str(detail["name"]),
            }
            for person, detail in sorted(quarterbacks.items())
            if detail["team"] == team and person not in ranked
        ]
        declarations.append(
            {
                "team": team,
                "game_id": str(quarterbacks[ordered[0]["underlying_id"]]["game_id"]),
                "declared_observed_at": observed_at.isoformat(),
                "starter": ordered[0],
                "backups": ordered[1:],
                "unlisted": unlisted,
                "source_sha256": digest,
            }
        )

    package = {
        "schema_version": SCHEMA_VERSION,
        "allocation_version": ALLOCATION_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "salary_sha256": slate.salary_hash,
        "game_ids": sorted(game.game_id for game in slate.games),
        "sources": sources,
        "declarations": declarations,
    }
    target = out_dir / "qb_depth_roles.json"
    target.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _match_person(
    row: dict[str, str],
    team: str,
    quarterbacks: dict[str, dict[str, object]],
) -> str:
    """Bind one depth-chart row to the exact DraftKings person, or refuse.

    The two sides share no identifier, so the match is on the normalized name
    within the one team, and an ambiguous or absent match is a refusal rather
    than a guess. `qb_depth_roles._bind` re-checks this independently; a
    producer that got it wrong is caught there too.
    """

    from nfl_dfs.priors import normalize_person_name

    wanted = normalize_person_name(row["player_name"].strip())
    hits = [
        person
        for person, detail in quarterbacks.items()
        if detail["team"] == team
        and normalize_person_name(str(detail["name"])) == wanted
    ]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ProducerError(
            f"the depth chart lists {row['player_name']!r} at quarterback for"
            f" {team}, and DraftKings does not list him on this slate."
            "\nThis is the case the package must not paper over: DraftKings'"
            " quarterback set and the depth chart's have to agree before the"
            " package can claim a starter. Either the capture is for the wrong"
            " week, or the person is spelled differently and needs a reviewed"
            " crosswalk entry first."
        )
    raise ProducerError(
        f"{row['player_name']!r} matches {len(hits)} DraftKings people on {team}:"
        f" {sorted(hits)}. Resolve the identity before building the package."
    )


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
