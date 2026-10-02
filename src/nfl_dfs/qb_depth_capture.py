"""Capture a quarterback depth-chart role package from depth-chart bytes (Session 53, R36).

The pure logic of `scripts/make_offensive_role_evidence.py`, moved here so `run-slate` can build
the package itself from the `depth_charts` bytes the prior package already froze. The script's
command line is unchanged and imports every name below. A depth chart names a quarterback order
and nothing else: the package it yields says who is the declared starter and who is behind him,
never a target share, a carry share, official activity or a model value.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import EngineMode
from .dk import parse_salaries
from .qb_depth_roles import (
    CURRENT_ALLOCATION_VERSION,
    CURRENT_TRANSFORMATION_VERSION,
    DEPTH_CHART_COLUMNS,
    PARSER_VERSION,
    QUARTERBACK_ABBREVIATION,
    SCHEMA_VERSION,
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

    from .sources import fetch_public_artifact

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

    return pick_snapshot({_parse_stamp(row["dt"]) for row in rows}, as_of=as_of, observed_at=observed_at)


def pick_snapshot(
    snapshot_stamps: set[datetime] | frozenset[datetime],
    *,
    as_of: datetime,
    observed_at: datetime | None,
) -> datetime:
    """`select_snapshot` over a set of snapshot times already read from the file."""

    stamps = sorted(snapshot_stamps)
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
        # Bytes, never text. `write_text` translates "\n" to os.linesep, so on
        # Windows the file would not hash to the digest just taken over these
        # exact bytes, and every consumer would refuse the package it just
        # wrote. Measured 2026-09-22: 24 failures on Windows, none on Linux.
        capture.write_bytes(excerpt.encode("utf-8"))
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
                "transformation_version": CURRENT_TRANSFORMATION_VERSION,
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
        "allocation_version": CURRENT_ALLOCATION_VERSION,
        "transformation_version": CURRENT_TRANSFORMATION_VERSION,
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

    from .priors import normalize_person_name

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


# --------------------------------------------------------------------------- #
# Session 53: capture inside `run-slate`, from bytes the prior package froze
# --------------------------------------------------------------------------- #

QB_DEPTH_CAPTURE_STALE = "QB_DEPTH_CAPTURE_STALE"
QB_DEPTH_CAPTURE_REFUSED = "QB_DEPTH_CAPTURE_REFUSED"
QB_DEPTH_CAPTURE_UNAVAILABLE = "QB_DEPTH_CAPTURE_UNAVAILABLE"
# Hash the file in blocks, never materialize it: 51 MB and 545,184 rows.
_BLOCK = 1 << 20


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def read_quarterback_rows(path: Path) -> tuple[tuple[dict[str, str], ...], frozenset[datetime], str]:
    """Only the quarterback rows of a depth chart, every snapshot time in it, and the digest.

    The published chart is 51 MB; `read_depth_chart` keeps all of it, which cost 14.9 s and
    519 MB on the path that must finish before a lock. The package needs one position, so this
    keeps one. The snapshot times come from every row, not only the quarterback rows, so the
    latest snapshot at or before the run is the one `select_snapshot` would pick on the whole
    file. Its header check, its row-length rule and its changed-while-read check are
    `read_depth_chart`'s.
    """

    digest = _file_digest(path)
    with path.open(encoding="utf-8", errors="strict", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ProducerError(f"depth chart is empty: {path}") from exc
        if tuple(header) != DEPTH_CHART_COLUMNS:
            raise ProducerError(
                "depth chart columns are not the ones this parser version was written for"
                f" (expected {len(DEPTH_CHART_COLUMNS)} columns, found {len(header)})"
            )
        abbreviation = DEPTH_CHART_COLUMNS.index("pos_abb")
        stamp_column = DEPTH_CHART_COLUMNS.index("dt")
        raw_stamps: set[str] = set()
        kept: list[dict[str, str]] = []
        for raw in reader:
            if len(raw) != len(DEPTH_CHART_COLUMNS):
                continue
            raw_stamps.add(raw[stamp_column])
            if raw[abbreviation].strip().upper() == QUARTERBACK_ABBREVIATION:
                kept.append(dict(zip(DEPTH_CHART_COLUMNS, raw)))
    if _file_digest(path) != digest:
        raise ProducerError(f"depth chart changed while it was being read: {path}")
    return tuple(kept), frozenset(_parse_stamp(value) for value in raw_stamps), digest


def locate_frozen_depth_chart(
    *, proposal_dir: Path | None = None, package_dir: Path | None = None, season: int | None = None
) -> tuple[Path, str, str] | None:
    """(bytes, sha256, source URI) of the depth chart a prior package froze, or None.

    A proposal records it in `source_manifest.json`; a frozen package records the hash in
    `prior_package.json` and archives the bytes under `raw/<sha256>.csv`. Nothing is fetched.
    """

    if proposal_dir is not None:
        try:
            manifest = json.loads((Path(proposal_dir) / "source_manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        for entry in manifest.get("artifacts") or ():
            if entry.get("name") == "depth_charts":
                path = (Path(proposal_dir) / str(entry["relative_path"])).resolve()
                return (path, str(entry["sha256"]), str(entry["source_uri"])) if path.is_file() else None
        return None
    if package_dir is not None:
        try:
            package = json.loads((Path(package_dir) / "prior_package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        digest = (package.get("frozen_sources") or {}).get("depth_charts")
        year = season if season is not None else package.get("season")
        if not digest or year is None:
            return None
        path = (Path(package_dir) / "raw" / f"{digest}.csv").resolve()
        return (path, str(digest), depth_chart_url(int(year))) if path.is_file() else None
    return None


@dataclass(frozen=True)
class CaptureOutcome:
    """What a run-time capture produced. It never raises; a failure is a named limitation."""

    status: str  # CAPTURED, or the code of the refusal
    package: Path | None = None
    observed_at: datetime | None = None
    upstream_sha256: str | None = None
    detail: str = ""

    @property
    def captured(self) -> bool:
        return self.package is not None

    def as_report(self) -> dict[str, object]:
        return {
            "status": self.status,
            "package": str(self.package) if self.package else None,
            "depth_chart_observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "upstream_sha256": self.upstream_sha256,
            "detail": self.detail,
            "does_not_establish": [
                "TARGET_SHARE",
                "CARRY_SHARE",
                "OFFICIAL_ACTIVE_STATUS",
                "THAT_THE_RANK_ONE_QUARTERBACK_IS_PLAYING",
                "MODEL_VALIDATION",
            ],
        }

    @property
    def limitation(self) -> str | None:
        """The `P` limitation this outcome carries, or None when it captured."""

        if self.captured:
            return None
        return f"{self.status}:{self.detail}" if self.detail else self.status


def capture_for_run(
    *,
    salaries: Path,
    as_of: datetime,
    out_dir: Path,
    depth_chart: tuple[Path, str, str] | None = None,
    proposal_dir: Path | None = None,
    package_dir: Path | None = None,
    season: int | None = None,
    teams: tuple[str, ...] | None = None,
    expires_after: timedelta = DEFAULT_EXPIRY,
) -> CaptureOutcome:
    """Build the QB depth package for one slate from frozen depth-chart bytes, or say why not.

    `depth_chart` is `(path, sha256, source_uri)`; when it is None the chart is located from
    `proposal_dir` or `package_dir` (`locate_frozen_depth_chart`), inside this function's guard.
    The snapshot is the latest at or before `as_of`, so a run can never read a chart from its
    own future. One older than its window, one that names a quarterback DraftKings does not
    list, one with no rank-1 quarterback and an absent file are each a named refusal. `teams`
    declares only those teams (the others stay unevaluated, and the run names them).

    It never raises: this runs on the path that must finish before a lock (R28), so anything
    unforeseen is a `QB_DEPTH_CAPTURE_REFUSED` naming the exception, and the run goes on
    without the package.
    """

    try:
        if depth_chart is None:
            depth_chart = locate_frozen_depth_chart(
                proposal_dir=proposal_dir, package_dir=package_dir, season=season
            )
        if depth_chart is None or not Path(depth_chart[0]).is_file():
            return CaptureOutcome(
                QB_DEPTH_CAPTURE_UNAVAILABLE, detail="no depth chart was frozen with the prior package"
            )
        path, upstream, uri = Path(depth_chart[0]), depth_chart[1], depth_chart[2]
        when = as_of.astimezone(timezone.utc)
        try:
            rows, stamps, digest = read_quarterback_rows(path)
            if digest != upstream:
                return CaptureOutcome(
                    QB_DEPTH_CAPTURE_REFUSED,
                    detail="the frozen depth chart's bytes no longer match their hash",
                )
            snapshot = pick_snapshot(stamps, as_of=when, observed_at=None)
            if snapshot + expires_after <= when:
                return CaptureOutcome(
                    QB_DEPTH_CAPTURE_STALE,
                    observed_at=snapshot,
                    upstream_sha256=upstream,
                    detail=(
                        f"the latest depth-chart snapshot at or before the run is {snapshot.isoformat()},"
                        f" older than its {int(expires_after.total_seconds() // 3600)}-hour window"
                    ),
                )
            target = build_package(
                salaries,
                rows,
                upstream_sha256=upstream,
                source_uri=uri,
                observed_at=snapshot,
                as_of=when,
                out_dir=out_dir,
                expires_after=expires_after,
                teams=teams,
            )
        except ProducerError as exc:
            return CaptureOutcome(
                QB_DEPTH_CAPTURE_REFUSED, upstream_sha256=upstream, detail=" ".join(str(exc).split())[:300]
            )
    except Exception as exc:  # noqa: BLE001 - the contract above: a capture never stops a run
        return CaptureOutcome(
            QB_DEPTH_CAPTURE_REFUSED,
            detail=f"{type(exc).__name__}: {' '.join(str(exc).split())[:200]}",
        )
    return CaptureOutcome("CAPTURED", package=target, observed_at=snapshot, upstream_sha256=upstream)
