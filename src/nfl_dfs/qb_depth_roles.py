"""P1: a source-bound quarterback attempt-share allocation from a depth chart.

Why this is its own contract rather than a field on
`nfl_offensive_role_evidence_v1`. That package is a *complete team* allocation:
every one of the five share fields must total 1.0 and every eligible offensive
person on the team must appear as a recipient. It is the right shape when
someone has measured the whole offense. A depth chart has not. It establishes
who takes the snaps at quarterback and nothing else — not target share, not
carry share, not receiving efficiency — so expressing it through the complete
contract would mean writing numbers for the other four fields that no source
supports. `does_not_establish` says so explicitly and the validator enforces it:
this package can only ever move `qb_attempt_share`.

What it is for. On the 2026-09-14 DEN@KC slate `opportunity.py` split Kansas
City's attempts Mahomes 0.5395 / Fields 0.4605 from prior-season history, and
the only way to stop a backup quarterback taking 46% of his team's attempts was
a portfolio-policy exclusion that lands after `score_pool` and never reaches the
projection at all. The published depth chart for that team resolves it in one
row: Mahomes `pos_rank` 1, Fields `pos_rank` 2.

Conservation, not creation. The starter receives exactly the sum of the
`qb_attempt_share` the team's quarterbacks already hold. This package never
increases a team's passing volume, never reaches a non-quarterback, and never
invents a fractional split — a depth chart is an ordering, so the only
allocation it supports is all-to-the-starter. A genuine committee needs measured
numbers, which is the complete contract's job.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping

from pydantic import Field, field_validator, model_validator

from .contracts import EngineMode, FrozenModel, SlateContract
from .hashing import sha256_file
from .kicker_roles import KickerRoleError, KickerRoleSource, _validate_source
from .offensive_roles import PersonBinding
from .opportunity import OpportunityModel
from .participation import ParticipationContract
from .priors import normalize_person_name

SCHEMA_VERSION = "nfl_qb_depth_role_evidence_v1"
ALLOCATION_VERSION = "qb_depth_chart_attempt_share_allocation_v1"
TRANSFORMATION_VERSION = "qb_depth_chart_order_v1"
PARSER_VERSION = "nflverse_depth_charts_csv_v1"
SHARE_TOLERANCE = 1e-9

# The exact nflverse `depth_charts` columns, confirmed against the published
# 2026 artifact on 2026-09-19 rather than recalled. The file is a time series:
# one snapshot per `dt`, 184 of them in the 2026 season file at the time of
# writing, so a package that does not pin one `dt` is ambiguous about which
# depth chart it read. `declared_observed_at` pins it.
DEPTH_CHART_COLUMNS = (
    "dt",
    "team",
    "player_name",
    "espn_id",
    "gsis_id",
    "pos_grp_id",
    "pos_grp",
    "pos_id",
    "pos_name",
    "pos_abb",
    "pos_slot",
    "pos_rank",
)
QUARTERBACK_ABBREVIATION = "QB"
STARTER_RANK = 1


class QbDepthRoleError(ValueError):
    """A named fail-closed quarterback-depth error."""

    def __init__(self, message: str, report: Mapping[str, object] | None = None):
        super().__init__(message)
        self.report = dict(report or {"evidence_state": "UNKNOWN", "blocker": message})


class QbDepthSource(KickerRoleSource):
    # The capture is a verbatim slice of the published CSV: the header line plus
    # one team's quarterback rows at one `dt`. A slice rather than the whole
    # file because the season artifact is ~50MB holding 184 snapshots of all 32
    # teams, and a package needs one capture per team with its own excerpt.
    # `upstream_sha256` and `source_uri` keep the slice traceable to the exact
    # published bytes it was cut from, so "verbatim subset" is checkable rather
    # than asserted.
    supporting_excerpt: str = Field(min_length=1, max_length=100000)
    support_kind: Literal["DEPTH_CHART_ORDER"]
    transformation_version: Literal["qb_depth_chart_order_v1"]
    parser_version: Literal["nflverse_depth_charts_csv_v1"]
    upstream_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class QbDepthEntry(PersonBinding):
    provider_player_id: str = Field(min_length=1)
    player_name: str = Field(min_length=1)
    pos_rank: int = Field(ge=1)


class UnlistedQuarterback(PersonBinding):
    """A quarterback DraftKings sells who the depth chart does not name.

    Measured on the real 2026-09-17 DET@BUF slate: DraftKings listed three
    Buffalo quarterbacks and the published depth chart named two. The third is
    not "a backup" — nothing observed says where he sits — he is simply absent,
    and the honest allocation for a person no source places is zero. Recording
    him here rather than as a backup keeps the two claims distinct, and the
    validator checks he really is absent from the capture so a package can never
    hide a named starter in this list.
    """

    player_name: str = Field(min_length=1)


class QbDepthDeclaration(FrozenModel):
    team: str = Field(min_length=1)
    game_id: str = Field(min_length=1)
    declared_observed_at: datetime
    starter: QbDepthEntry
    backups: tuple[QbDepthEntry, ...] = ()
    unlisted: tuple[UnlistedQuarterback, ...] = ()
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("declared_observed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("declared_observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def starter_outranks_every_backup(self) -> "QbDepthDeclaration":
        if self.starter.pos_rank != STARTER_RANK:
            raise ValueError("the starter must be the depth chart's rank 1")
        people = [
            self.starter.underlying_id,
            *(backup.underlying_id for backup in self.backups),
            *(absent.underlying_id for absent in self.unlisted),
        ]
        if len(set(people)) != len(people):
            raise ValueError("a person may appear once in a team's quarterback order")
        if any(backup.pos_rank <= STARTER_RANK for backup in self.backups):
            raise ValueError("a backup must rank below the starter")
        return self


class QbDepthEvidence(FrozenModel):
    schema_version: Literal["nfl_qb_depth_role_evidence_v1"]
    allocation_version: Literal["qb_depth_chart_attempt_share_allocation_v1"]
    transformation_version: Literal["qb_depth_chart_order_v1"]
    salary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    game_ids: tuple[str, ...] = Field(min_length=1)
    sources: tuple[QbDepthSource, ...] = Field(min_length=1)
    declarations: tuple[QbDepthDeclaration, ...] = Field(min_length=1)


@dataclass(frozen=True)
class QbDepthResolution:
    allocation_version: str
    model: OpportunityModel
    shares_by_person: dict[str, float]
    report: dict[str, object]
    evidence_path: str | None = None
    evidence_sha256: str | None = None
    source_hashes: dict[str, str] | None = None
    expires_at: datetime | None = None


def parse_depth_chart_excerpt(excerpt: str) -> tuple[dict[str, str], ...]:
    """Re-read the quarterback order out of the captured bytes themselves."""

    reader = csv.reader(io.StringIO(excerpt))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise QbDepthRoleError("QB_DEPTH_EXCERPT_EMPTY") from exc
    if tuple(header) != DEPTH_CHART_COLUMNS:
        raise QbDepthRoleError(
            f"QB_DEPTH_EXCERPT_COLUMNS_UNEXPECTED:{','.join(header)}"
        )
    rows: list[dict[str, str]] = []
    for raw in reader:
        if not any(field.strip() for field in raw):
            continue
        if len(raw) != len(DEPTH_CHART_COLUMNS):
            raise QbDepthRoleError("QB_DEPTH_EXCERPT_ROW_WIDTH_INVALID")
        rows.append(dict(zip(DEPTH_CHART_COLUMNS, raw)))
    if not rows:
        raise QbDepthRoleError("QB_DEPTH_EXCERPT_NO_ROWS")
    return tuple(rows)


def _derived_order(
    rows: tuple[dict[str, str], ...],
    *,
    team: str,
    observed_at: datetime,
) -> tuple[tuple[int, str, str], ...]:
    """(`pos_rank`, provider id, name) for one team's quarterbacks at one `dt`."""

    selected: list[tuple[int, str, str]] = []
    for row in rows:
        if row["team"].strip().upper() != team:
            raise QbDepthRoleError(f"QB_DEPTH_EXCERPT_TEAM_MISMATCH:{row['team']}")
        if row["pos_abb"].strip().upper() != QUARTERBACK_ABBREVIATION:
            raise QbDepthRoleError(
                f"QB_DEPTH_EXCERPT_NOT_A_QUARTERBACK_ROW:{row['pos_abb']}"
            )
        stamp = row["dt"].strip()
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QbDepthRoleError(f"QB_DEPTH_EXCERPT_DT_INVALID:{stamp}") from exc
        if parsed.tzinfo is None:
            raise QbDepthRoleError(f"QB_DEPTH_EXCERPT_DT_NAIVE:{stamp}")
        if parsed.astimezone(timezone.utc) != observed_at:
            raise QbDepthRoleError(
                "QB_DEPTH_EXCERPT_DT_MIXED:the excerpt must hold exactly one"
                f" snapshot; declared={observed_at.isoformat()}:row={stamp}"
            )
        try:
            rank = int(row["pos_rank"])
        except ValueError as exc:
            raise QbDepthRoleError(
                f"QB_DEPTH_EXCERPT_RANK_INVALID:{row['pos_rank']}"
            ) from exc
        selected.append((rank, row["gsis_id"].strip(), row["player_name"].strip()))
    ranks = [rank for rank, _id, _name in selected]
    if len(set(ranks)) != len(ranks):
        raise QbDepthRoleError("QB_DEPTH_EXCERPT_DUPLICATE_RANK")
    if ranks.count(STARTER_RANK) != 1:
        raise QbDepthRoleError(
            "QB_DEPTH_EXCERPT_STARTER_NOT_UNIQUE:a depth chart with no single"
            " rank-1 quarterback does not establish a starter"
        )
    return tuple(sorted(selected))


def _slate_quarterbacks(slate: SlateContract) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for player in slate.players:
        if player.position != "QB":
            continue
        bucket = grouped.setdefault(
            player.underlying_id,
            {"team": player.team, "game_id": player.game_id, "name": player.name, "rows": {}},
        )
        if bucket["team"] != player.team or bucket["game_id"] != player.game_id:
            raise QbDepthRoleError(f"QB_DEPTH_IDENTITY_CONFLICT:{player.underlying_id}")
        rows = bucket["rows"]
        assert isinstance(rows, dict)
        rows[player.role or "FLEX"] = player
    return grouped


def _bind(entry: QbDepthEntry, team: str, game_id: str, quarterbacks: dict, mode) -> None:
    detail = quarterbacks.get(entry.underlying_id)
    if detail is None:
        raise QbDepthRoleError(f"QB_DEPTH_EXACT_ID_MISMATCH:{entry.underlying_id}")
    rows = detail["rows"]
    if mode is EngineMode.SHOWDOWN:
        cpt, flex = rows.get("CPT"), rows.get("FLEX")
        if cpt is None or flex is None:
            raise QbDepthRoleError(f"QB_DEPTH_CPT_FLEX_INCOMPLETE:{entry.underlying_id}")
        if cpt.dk_id != entry.cpt_dk_id or flex.dk_id != entry.flex_dk_id:
            raise QbDepthRoleError(f"QB_DEPTH_EXACT_ID_MISMATCH:{entry.underlying_id}")
    else:
        if entry.dk_id is None or entry.dk_id not in {row.dk_id for row in rows.values()}:
            raise QbDepthRoleError(f"QB_DEPTH_EXACT_ID_MISMATCH:{entry.underlying_id}")
    if detail["team"] != team or detail["game_id"] != game_id:
        raise QbDepthRoleError(f"QB_DEPTH_TEAM_GAME_MISMATCH:{entry.underlying_id}")
    # The provider's person and DraftKings' person have to be the same human.
    # The depth chart is keyed on a gsis id that means nothing to DraftKings, so
    # the name is the only thing the two sides share; it is compared under the
    # same normalizer the identity gate uses for its proposals.
    if normalize_person_name(entry.player_name) != normalize_person_name(str(detail["name"])):
        raise QbDepthRoleError(
            f"QB_DEPTH_PROVIDER_NAME_MISMATCH:{entry.underlying_id}:"
            f"depth_chart={entry.player_name!r}:draftkings={detail['name']!r}"
        )


def resolve_qb_depth_roles(
    slate: SlateContract,
    model: OpportunityModel,
    contract: ParticipationContract,
    *,
    evidence_path: str | Path | None = None,
    as_of: datetime | None = None,
) -> QbDepthResolution:
    """Move each declared team's quarterback attempts onto its named starter."""

    when = (as_of or datetime.now(timezone.utc))
    if when.tzinfo is None:
        raise QbDepthRoleError("QB_DEPTH_CLOCK_REQUIRES_TIMEZONE")
    when = when.astimezone(timezone.utc)
    if evidence_path in (None, ""):
        return QbDepthResolution(
            allocation_version=ALLOCATION_VERSION,
            model=model,
            shares_by_person={},
            report=_report(None, None, {}, None, (), supplied=False),
        )

    manifest = Path(evidence_path).resolve()
    digest = sha256_file(manifest)
    try:
        evidence = QbDepthEvidence.model_validate_json(
            manifest.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise QbDepthRoleError(f"QB_DEPTH_EVIDENCE_INVALID:{exc}") from exc
    if sha256_file(manifest) != digest:
        raise QbDepthRoleError("QB_DEPTH_EVIDENCE_CHANGED_DURING_READ")
    if evidence.salary_sha256 != slate.salary_hash:
        raise QbDepthRoleError("QB_DEPTH_SALARY_HASH_MISMATCH")
    slate_games = {game.game_id for game in slate.games}
    if set(evidence.game_ids) != slate_games or len(evidence.game_ids) != len(slate_games):
        raise QbDepthRoleError("QB_DEPTH_GAME_COVERAGE_MISMATCH")

    sources: dict[str, QbDepthSource] = {}
    source_hashes: dict[str, str] = {}
    try:
        for source in evidence.sources:
            if source.sha256 in sources:
                raise QbDepthRoleError(f"QB_DEPTH_DUPLICATE_SOURCE:{source.sha256}")
            captured, captured_digest = _validate_source(
                source, manifest_path=manifest, as_of=when
            )
            sources[source.sha256] = source
            source_hashes[str(captured)] = captured_digest
    except KickerRoleError as exc:
        raise QbDepthRoleError(str(exc).replace("KICKER_ROLE", "QB_DEPTH")) from exc

    quarterbacks = _slate_quarterbacks(slate)
    selectable = set(contract.selectable_people)
    by_team: dict[str, set[str]] = {}
    for person, detail in quarterbacks.items():
        by_team.setdefault(str(detail["team"]), set()).add(person)

    declared_teams: set[str] = set()
    used_sources: set[str] = set()
    starters: dict[str, str] = {}
    unlisted_people: set[str] = set()
    observed: list[datetime] = []
    for declaration in evidence.declarations:
        team = declaration.team.strip().upper()
        if team in declared_teams:
            raise QbDepthRoleError(f"QB_DEPTH_DUPLICATE_TEAM:{team}")
        declared_teams.add(team)
        if team not in by_team:
            raise QbDepthRoleError(f"QB_DEPTH_UNKNOWN_TEAM:{team}")
        if declaration.game_id not in slate_games:
            raise QbDepthRoleError(f"QB_DEPTH_DECLARATION_GAME_UNKNOWN:{team}")
        source = sources.get(declaration.source_sha256)
        if source is None or source.support_kind != "DEPTH_CHART_ORDER":
            raise QbDepthRoleError(f"QB_DEPTH_SOURCE_REFERENCE_UNKNOWN:{team}")
        used_sources.add(declaration.source_sha256)

        entries = (declaration.starter, *declaration.backups)
        for entry in (*entries, *declaration.unlisted):
            _bind(entry, team, declaration.game_id, quarterbacks, slate.mode)
        # Every quarterback DraftKings lists for this team must be placed, as a
        # ranked entry or an explicitly unlisted one, so a package cannot
        # quietly omit the person it would otherwise have to zero. Omission and
        # a zero share are very different claims.
        placed = {entry.underlying_id for entry in entries} | {
            absent.underlying_id for absent in declaration.unlisted
        }
        if placed != by_team[team]:
            raise QbDepthRoleError(
                f"QB_DEPTH_TEAM_COVERAGE_MISMATCH:team={team}:"
                f"declared={sorted(placed)}:on_the_slate={sorted(by_team[team])}"
            )
        if declaration.starter.underlying_id not in selectable:
            raise QbDepthRoleError(
                f"QB_DEPTH_STARTER_NOT_SELECTABLE:{declaration.starter.underlying_id}:"
                "refresh the depth chart after the inactive or exclusion change"
            )
        derived = _derived_order(
            parse_depth_chart_excerpt(source.supporting_excerpt),
            team=team,
            observed_at=declaration.declared_observed_at,
        )
        # A person claimed to be absent from the depth chart has to actually be
        # absent from it. Without this, "unlisted" would be a place to hide a
        # quarterback the capture names at rank 1.
        captured_names = {
            normalize_person_name(name) for _rank, _provider, name in derived
        }
        for absent in declaration.unlisted:
            if normalize_person_name(absent.player_name) in captured_names:
                raise QbDepthRoleError(
                    f"QB_DEPTH_UNLISTED_IS_ON_THE_CAPTURE:{absent.underlying_id}:"
                    f"{absent.player_name!r} is named in the depth chart this"
                    " package cites, so he cannot be declared unlisted"
                )
        claimed = tuple(
            sorted(
                (entry.pos_rank, entry.provider_player_id, entry.player_name)
                for entry in entries
            )
        )
        if derived != claimed:
            raise QbDepthRoleError(
                f"QB_DEPTH_ORDER_NOT_SUPPORTED_BY_CAPTURE:team={team}:"
                f"capture={derived}:declared={claimed}"
            )
        starters[team] = declaration.starter.underlying_id
        unlisted_people.update(
            absent.underlying_id for absent in declaration.unlisted
        )
        observed.append(declaration.declared_observed_at)

    if used_sources != set(sources):
        raise QbDepthRoleError(
            f"QB_DEPTH_UNUSED_SOURCE:{sorted(set(sources) - used_sources)}"
        )

    players = {player.underlying_id: player for player in model.players}
    shares: dict[str, float] = {}
    moved: list[dict[str, object]] = []
    updated = dict(players)
    for team, starter in sorted(starters.items()):
        # Every quarterback the declaration placed must exist in the prior
        # package, not just the starter. A backup present on the slate but
        # absent from the model would otherwise be skipped silently: not zeroed,
        # not reported, and not scored either, which looks like it worked.
        missing = sorted(person for person in by_team[team] if person not in players)
        if missing:
            raise QbDepthRoleError(
                f"QB_DEPTH_PRIOR_ROW_MISSING:{','.join(missing)}:"
                "rebuild the complete prior package; the depth chart places"
                " quarterbacks this model has no row for"
            )
        team_people = [
            person for person in by_team[team] if players[person].position == "QB"
        ]
        pooled = sum(players[person].qb_attempt_share for person in team_people)
        if not math.isfinite(pooled) or pooled < 0:
            raise QbDepthRoleError(f"QB_DEPTH_POOLED_SHARE_INVALID:{team}")
        for person in sorted(team_people):
            before = players[person].qb_attempt_share
            after = pooled if person == starter else 0.0
            shares[person] = after
            updated[person] = replace(players[person], qb_attempt_share=after)
            # An unlisted quarterback is always reported, even when his
            # share was already zero: "no source places him" is the
            # finding, and it does not depend on the number moving.
            if before != after or person in unlisted_people:
                moved.append(
                    {
                        "person": person,
                        "team": team,
                        "role": (
                            "STARTER"
                            if person == starter
                            else (
                                "UNLISTED_ON_DEPTH_CHART"
                                if person in unlisted_people
                                else "BACKUP"
                            )
                        ),
                        "qb_attempt_share_before": round(before, 9),
                        "qb_attempt_share_after": round(after, 9),
                    }
                )
        allocated = sum(shares[person] for person in team_people)
        if not math.isclose(allocated, pooled, rel_tol=0, abs_tol=SHARE_TOLERANCE):
            raise QbDepthRoleError(
                f"QB_DEPTH_NOT_CONSERVED:team={team}:"
                f"allocated={allocated:.12g}:pooled={pooled:.12g}"
            )

    expiry = min(source.expires_at for source in sources.values())
    return QbDepthResolution(
        allocation_version=evidence.allocation_version,
        model=replace(model, players=tuple(updated[p.underlying_id] for p in model.players)),
        shares_by_person=shares,
        report=_report(
            str(manifest),
            digest,
            source_hashes,
            min(observed) if observed else None,
            tuple(moved),
            supplied=True,
            starters=starters,
            unlisted=tuple(sorted(unlisted_people)),
            expires_at=expiry,
            synthetic=tuple(
                sorted(s.sha256 for s in sources.values() if s.synthetic)
            ),
            upstream=tuple(sorted({s.upstream_sha256 for s in sources.values()})),
        ),
        evidence_path=str(manifest),
        evidence_sha256=digest,
        source_hashes=source_hashes,
        expires_at=expiry,
    )


def _report(
    manifest: str | None,
    digest: str | None,
    source_hashes: Mapping[str, str],
    observed_at: datetime | None,
    moved: tuple[dict[str, object], ...],
    *,
    supplied: bool,
    starters: Mapping[str, str] | None = None,
    unlisted: tuple[str, ...] = (),
    expires_at: datetime | None = None,
    synthetic: tuple[str, ...] = (),
    upstream: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION if supplied else None,
        "allocation_version": ALLOCATION_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "allocation_basis": (
            "SOURCE_BOUND_DEPTH_CHART_ORDER"
            if supplied
            else "PRIOR_ONLY_HISTORICAL_ATTEMPT_SPLIT"
        ),
        "evidence_state": "PASS" if supplied and not synthetic else "UNKNOWN",
        "does_not_establish": [
            "TARGET_SHARE",
            "CARRY_SHARE",
            "RUSHING_OR_RECEIVING_TOUCHDOWN_SHARE",
            "RECEIVING_EFFICIENCY",
            "OFFICIAL_ACTIVE_STATUS",
            "MODEL_VALIDATION",
            "HOW_MANY_ATTEMPTS_THE_TEAM_WILL_THROW",
        ],
        "allocation_rule": (
            "A depth chart is an ordering, not a measurement. The rank-1"
            " quarterback receives exactly the attempt share his team's"
            " quarterbacks already held; listed backups receive zero. Team"
            " passing volume is unchanged and no other share is touched."
        ),
        "starters_by_team": dict(sorted((starters or {}).items())),
        "unlisted_on_depth_chart": list(unlisted),
        "changed_people": [dict(row) for row in moved],
        "evidence_path": manifest,
        "evidence_sha256": digest,
        "source_hashes": dict(sorted(source_hashes.items())),
        "depth_chart_observed_at": observed_at.isoformat() if observed_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "synthetic_sources": list(synthetic),
        "synthetic_note": "TEST_ONLY_SYNTHETIC_EVIDENCE" if synthetic else None,
        "upstream_sha256s": sorted(upstream),
    }


def verify_qb_depth_resolution(resolution: QbDepthResolution, *, at: datetime) -> None:
    """Recheck immutable bytes and expiry immediately before review export."""

    if resolution.evidence_path is None:
        return
    if at.tzinfo is None:
        raise QbDepthRoleError("QB_DEPTH_CLOCK_REQUIRES_TIMEZONE")
    try:
        if sha256_file(resolution.evidence_path) != resolution.evidence_sha256:
            raise QbDepthRoleError("QB_DEPTH_EVIDENCE_CHANGED_DURING_SELECTION")
        for path, digest in (resolution.source_hashes or {}).items():
            if sha256_file(path) != digest:
                raise QbDepthRoleError(
                    f"QB_DEPTH_SOURCE_CHANGED_DURING_SELECTION:path={path}"
                )
    except OSError as exc:
        raise QbDepthRoleError("QB_DEPTH_ARTIFACT_MISSING_DURING_SELECTION") from exc
    if resolution.expires_at and at.astimezone(timezone.utc) > resolution.expires_at:
        raise QbDepthRoleError(
            "QB_DEPTH_SOURCE_EXPIRED_DURING_SELECTION:refresh the depth chart and rerun"
        )
