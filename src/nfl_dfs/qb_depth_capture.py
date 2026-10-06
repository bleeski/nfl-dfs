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
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    QbDepthDeclaration,
    QbDepthRoleError,
    _derived_order,
    parse_depth_chart_excerpt,
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


# One team's refusal is a sentence on one line in a limitation, never a traceback or a paragraph.
REASON_LIMIT = 200


def team_reason(exc: BaseException) -> str:
    """One line naming why one team could not be declared. A producer's own refusal reads as written."""

    text = " ".join(str(exc).split())
    if not isinstance(exc, (ProducerError, QbDepthRoleError)):
        text = f"{type(exc).__name__}: {text}"
    return text[:REASON_LIMIT]


@dataclass(frozen=True)
class PackageBuild:
    """What a build produced: the manifest (None when no team could be declared), who is in it, who is not and why."""

    path: Path | None
    declared: tuple[str, ...]
    undeclared: dict[str, str]


@dataclass(frozen=True)
class _TeamBuild:
    team: str
    digest: str
    excerpt: str
    source: dict[str, object]
    declaration: dict[str, object]


def _slate_quarterbacks(slate) -> dict[str, dict[str, object]]:
    quarterbacks: dict[str, dict[str, object]] = {}
    for player in slate.players:
        if player.position != "QB":
            continue
        bucket = quarterbacks.setdefault(
            player.underlying_id,
            {"team": player.team, "game_id": player.game_id, "name": player.name, "rows": {}},
        )
        bucket["rows"][player.role or "FLEX"] = player
    return quarterbacks


def _resolver_team_check(
    declaration: dict[str, object], excerpt: str, *, team: str, observed_at: datetime
) -> None:
    """The resolver's own team-level checks, run over the declaration just built (Session 63).

    A chart the resolver would refuse for a reason that is about this team's rows (two rank-1
    quarterbacks, a repeated or unreadable rank, one person at two ranks, a declaration its own
    excerpt does not support) is named here, for this team, instead of surviving to selection, where
    the refusal names no team and the whole package is lost. These are the resolver's own functions,
    not a copy of its rules.
    """

    derived = _derived_order(parse_depth_chart_excerpt(excerpt), team=team, observed_at=observed_at)
    checked = QbDepthDeclaration.model_validate(declaration)
    claimed = tuple(
        sorted(
            (entry.pos_rank, entry.provider_player_id, entry.player_name)
            for entry in (checked.starter, *checked.backups)
        )
    )
    if derived != claimed:
        raise ProducerError(
            f"{team}'s declaration is not the order its own excerpt carries: {derived} against {claimed}"
        )


def _build_team(
    team: str,
    rows: tuple[dict[str, str], ...],
    quarterbacks: dict[str, dict[str, object]],
    mode: EngineMode,
    *,
    upstream_sha256: str,
    source_uri: str,
    observed_at: datetime,
    as_of: datetime,
    expires_after: timedelta,
) -> _TeamBuild:
    """One team's capture, source entry and declaration, in memory. Writes nothing; raises for this team alone."""

    excerpt = slice_for_team(rows, team=team, observed_at=observed_at)
    digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    source = {
        "path": f"sources/{digest}.csv",
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

    ordered = []
    for row in csv.DictReader(io.StringIO(excerpt)):
        person = _match_person(row, team, quarterbacks)
        ordered.append(
            {
                **_binding(quarterbacks[person]["rows"], mode),
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
            **_binding(detail["rows"], mode),
            "underlying_id": person,
            "player_name": str(detail["name"]),
        }
        for person, detail in sorted(quarterbacks.items())
        if detail["team"] == team and person not in ranked
    ]
    declaration = {
        "team": team,
        "game_id": str(quarterbacks[ordered[0]["underlying_id"]]["game_id"]),
        "declared_observed_at": observed_at.isoformat(),
        "starter": ordered[0],
        "backups": ordered[1:],
        "unlisted": unlisted,
        "source_sha256": digest,
    }
    _resolver_team_check(declaration, excerpt, team=team, observed_at=observed_at)
    return _TeamBuild(team=team, digest=digest, excerpt=excerpt, source=source, declaration=declaration)


def _build(
    salaries: Path,
    rows: tuple[dict[str, str], ...],
    *,
    upstream_sha256: str,
    source_uri: str,
    observed_at: datetime,
    as_of: datetime,
    out_dir: Path,
    expires_after: timedelta,
    teams: tuple[str, ...] | None,
    strict: bool,
) -> PackageBuild:
    slate = parse_salaries(salaries)
    quarterbacks = _slate_quarterbacks(slate)

    wanted = sorted({str(detail["team"]) for detail in quarterbacks.values()})
    if teams:
        missing = sorted(set(teams) - set(wanted))
        if missing:
            raise ProducerError(
                f"--teams names teams with no quarterback on this slate: {missing}"
            )
        wanted = sorted(teams)

    # Every requested team is built in memory first. A strict build (the producer script) raises on the
    # first one that fails; the run-time build (Session 63) drops that team, names it and builds the rest,
    # so one team's gap in the chart never costs the other 31. Nothing is written until the teams are known.
    built: list[_TeamBuild] = []
    undeclared: dict[str, str] = {}
    for team in wanted:
        try:
            built.append(
                _build_team(
                    team, rows, quarterbacks, slate.mode,
                    upstream_sha256=upstream_sha256, source_uri=source_uri,
                    observed_at=observed_at, as_of=as_of, expires_after=expires_after,
                )
            )
        except Exception as exc:  # noqa: BLE001 - this team's refusal, named; the others are unaffected
            if strict:
                if isinstance(exc, ProducerError):
                    raise
                raise ProducerError(f"{team}: {team_reason(exc)}") from exc
            undeclared[team] = team_reason(exc)
    if not built:
        return PackageBuild(None, (), dict(sorted(undeclared.items())))

    sources_dir = out_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    for item in built:
        # Bytes, never text. `write_text` translates "\n" to os.linesep, so on
        # Windows the file would not hash to the digest just taken over these
        # exact bytes, and every consumer would refuse the package it just
        # wrote. Measured 2026-09-22: 24 failures on Windows, none on Linux.
        (sources_dir / f"{item.digest}.csv").write_bytes(item.excerpt.encode("utf-8"))

    package = {
        "schema_version": SCHEMA_VERSION,
        "allocation_version": CURRENT_ALLOCATION_VERSION,
        "transformation_version": CURRENT_TRANSFORMATION_VERSION,
        "salary_sha256": slate.salary_hash,
        "game_ids": sorted(game.game_id for game in slate.games),
        "sources": [item.source for item in built],
        "declarations": [item.declaration for item in built],
    }
    target = out_dir / "qb_depth_roles.json"
    target.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PackageBuild(target, tuple(item.team for item in built), dict(sorted(undeclared.items())))


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
    """The package for every requested team, or a `ProducerError` naming the first team that cannot be built.

    The producer script's behavior, unchanged in what it accepts and refuses for a clean chart; it now
    also refuses a conflicted chart here (the resolver's own team-level checks) and writes nothing when it
    refuses. `capture_for_run` uses `build_package_by_team`.
    """

    build = _build(
        salaries, rows, upstream_sha256=upstream_sha256, source_uri=source_uri, observed_at=observed_at,
        as_of=as_of, out_dir=out_dir, expires_after=expires_after, teams=teams, strict=True,
    )
    if build.path is None:
        # Only reachable when the slate lists no quarterback team at all: a strict build raises for any team that fails.
        raise ProducerError("the slate lists no quarterback team to declare")
    return build.path


def build_package_by_team(
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
) -> PackageBuild:
    """The package for every team the chart can declare, and each team it cannot with the reason (Session 63).

    A team is left out, named and never guessed when the chart lists no quarterback for it, names one
    DraftKings does not list (or two it cannot tell apart), has no single rank-1 quarterback, or conflicts
    with itself. Every other team is declared exactly as `build_package` would declare it.
    """

    return _build(
        salaries, rows, upstream_sha256=upstream_sha256, source_uri=source_uri, observed_at=observed_at,
        as_of=as_of, out_dir=out_dir, expires_after=expires_after, teams=teams, strict=False,
    )


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
# A package that declares some teams and leaves one out (Session 63): a limitation per team, class P.
QB_DEPTH_CAPTURE_TEAM_UNDECLARED = "QB_DEPTH_CAPTURE_TEAM_UNDECLARED"
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
    """What a run-time capture produced. It never raises; a failure is a named limitation.

    Since Session 63 a package can be partial: `declared_teams` are in it and `undeclared_teams` (team to
    reason) are the teams the chart could not build, left out and named. `status` still describes the
    package (`CAPTURED` when the resolver can read it); each undeclared team travels as its own limitation.
    """

    status: str  # CAPTURED, or the code of the refusal
    package: Path | None = None
    observed_at: datetime | None = None
    upstream_sha256: str | None = None
    detail: str = ""
    declared_teams: tuple[str, ...] = ()
    undeclared_teams: dict[str, str] = field(default_factory=dict)

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
            "declared_teams": list(self.declared_teams),
            "undeclared_teams": dict(sorted(self.undeclared_teams.items())),
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
    own future. One older than its window, an absent file and a changed file are each a named
    refusal of the whole capture. A team the chart cannot declare (it lists no quarterback for
    him, names one DraftKings does not list, has no single rank-1 quarterback, conflicts with
    itself) is left out and named in `undeclared_teams` while every other team is declared
    (Session 63); only when no team can be declared is the capture refused. `teams` declares only
    those teams (the others stay unevaluated, and the run names them).

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
            build = build_package_by_team(
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
    if build.path is None:
        # No team could be declared. The map still names each one; the detail counts them and quotes
        # the first few so one line never has to carry 32 reasons.
        count = len(build.undeclared)
        first = "; ".join(f"{name}: {why}" for name, why in list(build.undeclared.items())[:3])
        return CaptureOutcome(
            QB_DEPTH_CAPTURE_REFUSED,
            observed_at=snapshot,
            upstream_sha256=upstream,
            detail=f"the chart declares none of its {count} team{'s' if count != 1 else ''}: {first}"[:300],
            undeclared_teams=build.undeclared,
        )
    return CaptureOutcome(
        "CAPTURED",
        package=build.path,
        observed_at=snapshot,
        upstream_sha256=upstream,
        declared_teams=build.declared,
        undeclared_teams=build.undeclared,
    )


def team_undeclared_limitations(capture_report: object) -> list[str]:
    """One `QB_DEPTH_CAPTURE_TEAM_UNDECLARED:<TEAM>:<reason>` for each team a built package leaves out (`P`).

    Read from `reports["qb_depth_capture"]`, which is where both a capture-time and a selection-time
    degradation are recorded. Only when a package was built: with none, the whole-capture limitation
    already says so and the full map stays in the report, so 32 lines never bury the file's real ones.
    """

    if not isinstance(capture_report, Mapping) or not capture_report.get("package"):
        return []
    undeclared = capture_report.get("undeclared_teams")
    if not isinstance(undeclared, Mapping):
        return []
    return [f"{QB_DEPTH_CAPTURE_TEAM_UNDECLARED}:{team}:{reason}" for team, reason in sorted(undeclared.items())]
