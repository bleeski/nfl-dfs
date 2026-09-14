#!/usr/bin/env python3
"""Normalize a raw DraftKings standings export into ``nfl_standings_csv_v2``.

Q1B intake, back half of ``scripts/standings_checklist.py``. The checklist
answers *which* contests need a pull; this answers *what a pulled file has to
become* before ``nfl.ps1 settle --request`` will look at it.

Boundaries, unchanged from ``CLAUDE.md``:

- Nothing here fetches DraftKings. The raw export is Ben's own click in his own
  logged-in browser. This tool only ever reads a file already sitting in
  ``data/standings/inbox/``.
- The raw file is never edited, moved, renamed or deleted. It is read, hashed,
  and left exactly as delivered. Every output is written somewhere else.
- A field this tool cannot resolve from bytes already on disk is a named
  refusal, never a guess and never a default.

What a real DraftKings export actually looks like
-------------------------------------------------

Measured against all 18 of Ben's 2026-09-09/10/13 exports, not assumed:

``Rank,EntryId,EntryName,TimeRemaining,Points,Lineup,,Player,Roster Position,%Drafted,FPTS``

Three things about that header drive this whole module.

1. **The per-player ownership table is not a trailing block.** It sits in
   columns 7-10 *of the same rows*, separated from the standings by one unnamed
   empty column, and it runs out long before the standings do. Columns at and
   after the first unnamed header are dropped; the standings columns are the
   only ones read.

2. **There is no ``Prize`` column.** DraftKings does not export a per-entry
   prize at all. ``nfl_standings_csv_v2`` requires one, so the prize is
   necessarily a *derived* fact joined from the contest's payout table, never
   an observed one. See ``--payouts`` and ``PRIZE_PROVENANCE`` below; the
   consequence for the downstream prize check is recorded in ``backlog.md``.

3. **``Points`` carries float round-trip noise and ``Lineup`` carries names.**
   Both are handled below, each with its own measured justification.

Points rounding
---------------

Raw ``Points`` values such as ``85.850006`` and ``80.600006`` appear alongside
exact ones like ``85.85``. Across all 1,415,500 entry rows in the 18 exports the
largest gap between a raw value and its 2-decimal rounding is ``0.00003``, and
``ROUND_HALF_EVEN`` and ``ROUND_HALF_UP`` never disagree on a single row, so no
true midpoint exists anywhere and the rounding mode is immaterial.

That rounding is not cosmetic, it is load-bearing. DraftKings' own ``Rank``
column is computed from the true 2-decimal score, so ranking the raw values
splits tie groups DraftKings did not split. Measured rank agreement against
DraftKings' own ``Rank``:

===========  =========  =========
contest      raw        2dp
===========  =========  =========
195384501    70/71      71/71
195379585    223/237    237/237
195520918    430/475    475/475
195390889    6415/9512  9512/9512
195526163    4195/5945  5945/5945
===========  =========  =========

So the normalized file carries the rounded score, the manifest records how many
rows moved and by how much, and a row that would move by more than
``MAX_POINTS_ADJUSTMENT`` is a refusal rather than a repair — that would mean the
value is not float noise and the assumption has stopped holding.

Lineup resolution
-----------------

DraftKings exports a lineup as slot-tagged *names*
(``CPT Brock Purdy FLEX Kyren Williams ...``), while the engine's canonical key
is built from identifiers. ``settlement._prepare_settlement`` requires an owned
entry's ``Lineup`` to equal the key independently rebuilt from the frozen salary
file, and the reference evaluator counts complete-lineup duplication off the same
key, so the whole field has to be translated, not just Ben's rows.

The translation binds the exact salary snapshot for that slate (``--salaries``,
hashed into the manifest), splits on the known slot vocabulary, and then checks
the recovered slot multiset against the mode's required roster shape. That check
is what makes the split safe: a name that swallowed a slot token, or a slot token
that swallowed part of a name, cannot produce the right multiset. Any name that
does not resolve to exactly one person in the bound salary file is a refusal.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from fractions import Fraction
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from nfl_dfs.contracts import EngineMode
    from nfl_dfs.dk import DraftKingsParseError, parse_salaries
except ModuleNotFoundError:  # pragma: no cover - environment guard
    sys.exit(
        "nfl_dfs is not importable. Run this with the project's own interpreter, "
        "not a bare system python3:\n"
        "  Windows:      .venv\\Scripts\\python.exe scripts\\file_standings.py\n"
        "  Cowork/Linux: .cowork-venv/bin/python scripts/file_standings.py"
    )

STANDINGS_DIR = REPO_ROOT / "data" / "standings"
INBOX_DIR = STANDINGS_DIR / "inbox"
NORMALIZED_DIR = STANDINGS_DIR / "normalized"

NORMALIZER_VERSION = "nfl_standings_normalizer_q1b_v1"
MANIFEST_VERSION = "nfl_standings_normalization_v1"
STANDINGS_ARTIFACT_VERSION = "nfl_standings_csv_v2"

#: The exact output contract. ``docs/DATA_CONTRACTS.md`` "Standings settlement".
NORMALIZED_COLUMNS = ("EntryId", "Rank", "Points", "Prize", "Lineup")

#: DraftKings' own standings columns, in their exported order.
RAW_STANDINGS_COLUMNS = ("Rank", "EntryId", "EntryName", "TimeRemaining", "Points", "Lineup")

#: Largest raw-to-2dp gap this tool will treat as float round-trip noise.
#: The measured worst case across Ben's 18 exports is 0.00003; anything an order
#: of magnitude beyond that is a changed assumption, not noise.
MAX_POINTS_ADJUSTMENT = Decimal("0.0005")

#: What to do with a real field member who never submitted a lineup.
#:
#: 11 of Ben's 18 exports carry them: genuine paid entries, tied at the last
#: rank, scoring 0, with an empty ``Lineup`` cell. ``nfl_standings_csv_v2``
#: requires a nonempty canonical key and ``settlement.parse_standings`` refuses
#: an empty one, so the contract as written cannot represent a real DraftKings
#: field. That is a contract defect, recorded in ``backlog.md`` under Q1B, not
#: something this tool decides on its own.
#:
#: ``refuse`` (the default) keeps the strict contract and names the row.
#: ``sentinel`` writes ``NO_LINEUP_SUBMITTED:<entry_id>`` — nonempty, unique per
#: entry so the row forms its own duplication group of one, which is the true
#: statement that it duplicates nothing. It is available so Ben can exercise the
#: path the moment he rules on the contract; it is never the default, because
#: choosing it changes what a column in a versioned artifact means.
UNSUBMITTED_ENTRY_POLICIES = ("refuse", "sentinel")
UNSUBMITTED_LINEUP_SENTINEL = "NO_LINEUP_SUBMITTED"

#: What to do when an exact tie split is not a whole number of cents.
#:
#: ``nfl_reference_settlement_v1`` deliberately keeps money as exact rational
#: cents, so a prize divided across a tie group that does not divide evenly stays
#: a fraction. ``nfl_standings_csv_v2`` requires "prize an exact non-negative cent
#: amount", which cannot hold that value. Real contests hit this constantly: in
#: 193391013, 757 entries across 9 tie groups settle to a fractional share,
#: starting with a 23-way tie for first.
#:
#: This is a contract defect with a consequence beyond this tool:
#: ``settlement._prepare_settlement`` compares the evaluator's exact ``Fraction``
#: against the file's integer cents for *every* field row, so a contest with any
#: uneven tie split can never clear ``STANDINGS_PRIZE_MISMATCH`` whatever the
#: intake writes. Recorded under Q1B in ``backlog.md``; not this tool's call.
PRIZE_ROUNDING_POLICIES = ("refuse", "half-even")

#: Every slot token DraftKings writes into the ``Lineup`` string.
SLOT_TOKENS = ("CPT", "FLEX", "QB", "RB", "WR", "TE", "DST")
_SLOT_RE = re.compile(r"\b(" + "|".join(SLOT_TOKENS) + r")\b")

#: Required roster shape per mode, as a sorted multiset of slot tokens.
REQUIRED_SLOTS = {
    EngineMode.SHOWDOWN: ("CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"),
    EngineMode.CLASSIC: ("DST", "FLEX", "QB", "RB", "RB", "TE", "WR", "WR", "WR"),
}

_CONTEST_ID_RE = re.compile(r"\d{5,}")


class StandingsNormalizationError(ValueError):
    """A named refusal. Every message starts with a stable upper-case code."""


@dataclass(frozen=True)
class RawExport:
    """The untouched bytes of one delivered export, plus how they were reached."""

    path: Path
    sha256: str
    byte_count: int
    csv_bytes: bytes
    zip_member: str | None


@dataclass
class NormalizationResult:
    contest_id: str
    raw: RawExport
    normalized_path: Path
    normalized_sha256: str
    normalized_byte_count: int
    row_count: int
    manifest_path: Path
    manifest: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Reading the delivered bytes
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contest_id_from_filename(path: Path) -> str:
    """Recover the Contest ID DraftKings embeds in the export filename.

    ``contest-standings-195384501.zip`` and ``contest-standings-195384501.csv``
    are both the shape DraftKings ships. A filename carrying no digit run, or
    more than one distinct run, is refused rather than guessed at: filing an
    export under the wrong contest would bind a real field to the wrong payout
    table and the wrong entries.
    """
    found = sorted(set(_CONTEST_ID_RE.findall(path.name)))
    if not found:
        raise StandingsNormalizationError(
            f"CONTEST_ID_UNRESOLVED: no 5+ digit contest id in filename: {path.name}"
        )
    if len(found) > 1:
        raise StandingsNormalizationError(
            f"CONTEST_ID_AMBIGUOUS: filename carries several digit runs {found}: {path.name}"
        )
    return found[0]


def read_raw_export(path: Path) -> RawExport:
    """Read one delivered export without modifying it.

    DraftKings ships the full standings export zipped for most contests and
    plain for small ones; both appear in Ben's own 18. A zip must contain
    exactly one CSV member, otherwise which member is the standings becomes a
    guess.
    """
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if path.suffix.lower() == ".zip":
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
            members = [
                name for name in archive.namelist() if name.lower().endswith(".csv")
            ]
        except zipfile.BadZipFile as exc:
            raise StandingsNormalizationError(
                f"RAW_EXPORT_UNREADABLE: {path.name} is not a readable zip: {exc}"
            ) from exc
        if len(members) != 1:
            raise StandingsNormalizationError(
                f"RAW_EXPORT_AMBIGUOUS_MEMBER: {path.name} holds {len(members)} CSV members {members}"
            )
        return RawExport(path, digest, len(data), archive.read(members[0]), members[0])
    if path.suffix.lower() != ".csv":
        raise StandingsNormalizationError(
            f"RAW_EXPORT_UNSUPPORTED_SUFFIX: {path.name} is neither .zip nor .csv"
        )
    return RawExport(path, digest, len(data), data, None)


# ---------------------------------------------------------------------------
# Parsing the standings half of the export
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawStandingRow:
    rank: int
    entry_id: str
    points_raw: Decimal
    points_2dp: Decimal
    lineup_raw: str
    row_number: int
    submitted_lineup: bool = True


def _standings_width(header: list[str]) -> int:
    """How many leading columns are the standings, not the ownership table.

    The ownership table starts at the first unnamed header cell. Taking the
    prefix before it rather than a fixed count means a DraftKings export that
    omits the ownership block entirely still parses.
    """
    for index, name in enumerate(header):
        if not name.strip():
            return index
    return len(header)


def parse_raw_standings(
    export: RawExport, *, unsubmitted_entry_policy: str = "refuse"
) -> tuple[list[RawStandingRow], int, int, Decimal]:
    """Parse the standings columns, dropping the side-by-side ownership table.

    Returns the rows, the number of ownership columns dropped, the number of rows
    whose ``Points`` moved under 2-decimal rounding, and the largest such move.
    """
    if unsubmitted_entry_policy not in UNSUBMITTED_ENTRY_POLICIES:
        raise StandingsNormalizationError(
            f"UNKNOWN_UNSUBMITTED_ENTRY_POLICY: {unsubmitted_entry_policy!r}, "
            f"expected one of {list(UNSUBMITTED_ENTRY_POLICIES)}"
        )
    try:
        text = export.csv_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise StandingsNormalizationError(
            f"RAW_EXPORT_UNREADABLE: {export.path.name} is not UTF-8: {exc}"
        ) from exc
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise StandingsNormalizationError(
            f"RAW_EXPORT_EMPTY: {export.path.name} has no header row"
        ) from exc

    width = _standings_width(header)
    standings_header = [name.strip() for name in header[:width]]
    missing = [name for name in RAW_STANDINGS_COLUMNS if name not in standings_header]
    if missing:
        raise StandingsNormalizationError(
            f"RAW_EXPORT_MISSING_COLUMNS: {export.path.name} lacks {missing}; "
            f"observed standings columns {standings_header}"
        )
    index_of = {name: standings_header.index(name) for name in RAW_STANDINGS_COLUMNS}

    rows: list[RawStandingRow] = []
    seen: set[str] = set()
    adjusted = 0
    worst = Decimal(0)
    for row_number, raw_row in enumerate(reader, start=2):
        if len(raw_row) < width:
            # A truncated export stops mid-row. Refusing names the row rather
            # than silently settling a partial field as if it were complete.
            raise StandingsNormalizationError(
                f"RAW_EXPORT_TRUNCATED_ROW: row {row_number} has {len(raw_row)} cells, "
                f"expected at least {width}"
            )
        entry_id = raw_row[index_of["EntryId"]].strip()
        if not entry_id:
            # Ownership-only tail rows have no EntryId. They are the ownership
            # table outliving the standings, not standings rows.
            continue
        if not entry_id.isdigit():
            raise StandingsNormalizationError(
                f"NON_NUMERIC_ENTRY_ID: row {row_number} EntryId {entry_id!r}"
            )
        if entry_id in seen:
            raise StandingsNormalizationError(
                f"DUPLICATE_ENTRY_ID: row {row_number} repeats EntryId {entry_id}"
            )
        seen.add(entry_id)

        lineup = raw_row[index_of["Lineup"]].strip()
        submitted = bool(lineup)
        if not submitted and unsubmitted_entry_policy == "refuse":
            raise StandingsNormalizationError(
                f"UNSUBMITTED_ENTRY_LINEUP: row {row_number} EntryId {entry_id} is a "
                "real field member who never submitted a lineup. "
                "nfl_standings_csv_v2 requires a nonempty canonical key, so the "
                "contract cannot represent it. See Q1B in backlog.md; rerun with "
                "--unsubmitted-entry-policy sentinel to record it explicitly instead."
            )
        rank_text = raw_row[index_of["Rank"]].replace(",", "").strip()
        try:
            rank = int(rank_text)
        except ValueError as exc:
            raise StandingsNormalizationError(
                f"INVALID_RANK: row {row_number} rank {rank_text!r}"
            ) from exc
        if rank < 1:
            raise StandingsNormalizationError(
                f"INVALID_RANK: row {row_number} rank {rank} is below 1"
            )
        try:
            points_raw = Decimal(raw_row[index_of["Points"]].strip())
        except InvalidOperation as exc:
            raise StandingsNormalizationError(
                f"INVALID_POINTS: row {row_number} points "
                f"{raw_row[index_of['Points']]!r}"
            ) from exc
        if not points_raw.is_finite():
            raise StandingsNormalizationError(
                f"INVALID_POINTS: row {row_number} points are not finite"
            )
        points_2dp = points_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        delta = abs(points_raw - points_2dp)
        if delta > MAX_POINTS_ADJUSTMENT:
            raise StandingsNormalizationError(
                f"POINTS_ADJUSTMENT_TOO_LARGE: row {row_number} EntryId {entry_id} "
                f"moves {delta} from {points_raw} to {points_2dp}, over the "
                f"{MAX_POINTS_ADJUSTMENT} float-noise tolerance"
            )
        if delta:
            adjusted += 1
            worst = max(worst, delta)
        rows.append(
            RawStandingRow(
                rank, entry_id, points_raw, points_2dp, lineup, row_number, submitted
            )
        )

    if not rows:
        raise StandingsNormalizationError(
            f"RAW_EXPORT_EMPTY: {export.path.name} has no entry rows"
        )
    return rows, len(header) - width, adjusted, worst


# ---------------------------------------------------------------------------
# Lineup name resolution
# ---------------------------------------------------------------------------


def split_lineup(text: str) -> tuple[tuple[str, str], ...]:
    """Split ``CPT Brock Purdy FLEX Kyren Williams ...`` into (slot, name) pairs.

    Deliberately dumb: scan for the known slot vocabulary at word boundaries and
    take everything between two tokens as one name. The caller checks the
    recovered slot multiset against the mode's required roster shape, which is
    what catches a bad split rather than any cleverness here.
    """
    pairs: list[tuple[str, str]] = []
    slot: str | None = None
    cursor = 0
    for match in _SLOT_RE.finditer(text):
        if slot is not None:
            pairs.append((slot, text[cursor : match.start()].strip()))
        slot, cursor = match.group(1), match.end()
    if slot is not None:
        pairs.append((slot, text[cursor:].strip()))
    return tuple(pairs)


def build_name_index(slate) -> dict[str, tuple[str, str]]:
    """Map an exported player name to its ``(underlying_id, dk_id)``.

    A Showdown salary file lists each person twice, once per role, so the index
    is keyed on the person: both rows agree on ``underlying_id``, and the
    Showdown canonical key is built from that. Classic lists each person once,
    and its canonical key is built from ``dk_id``. A name that maps to two
    different people cannot be resolved from the export's name alone and is
    recorded as ambiguous.
    """
    index: dict[str, set[tuple[str, str]]] = {}
    for player in slate.players:
        index.setdefault(player.name.strip(), set()).add(
            (player.underlying_id, player.dk_id)
        )
    resolved: dict[str, tuple[str, str]] = {}
    ambiguous: list[str] = []
    for name, identities in index.items():
        people = {underlying for underlying, _ in identities}
        if len(people) > 1:
            ambiguous.append(name)
            continue
        # Classic has exactly one dk_id per person; Showdown has two (CPT and
        # FLEX) but a slot-independent canonical key, so the lowest dk_id is a
        # deterministic stand-in that Showdown never reads.
        resolved[name] = (
            sorted(people)[0],
            sorted(dk_id for _, dk_id in identities)[0],
        )
    if ambiguous:
        raise StandingsNormalizationError(
            f"AMBIGUOUS_SALARY_NAMES: {sorted(ambiguous)} map to several people in "
            "the bound salary file; the export's name column cannot resolve them"
        )
    return resolved


def canonical_lineup_key(
    lineup_raw: str,
    mode: EngineMode,
    name_index: dict[str, tuple[str, str]],
    *,
    row_number: int,
    entry_id: str,
) -> str:
    """Rebuild ``lineups._canonical_key`` from a DraftKings lineup string.

    Mirrors that function exactly: Showdown keys on the captain's person plus
    the sorted flex people, Classic on the sorted DraftKings ids.
    """
    pairs = split_lineup(lineup_raw)
    shape = tuple(sorted(slot for slot, _ in pairs))
    expected = tuple(sorted(REQUIRED_SLOTS[mode]))
    if shape != expected:
        raise StandingsNormalizationError(
            f"LINEUP_SHAPE_MISMATCH: row {row_number} EntryId {entry_id} parsed as "
            f"{list(shape)}, expected {list(expected)} for {mode.value}: {lineup_raw!r}"
        )
    unresolved = sorted({name for _, name in pairs if name not in name_index})
    if unresolved:
        raise StandingsNormalizationError(
            f"LINEUP_NAME_UNRESOLVED: row {row_number} EntryId {entry_id} names "
            f"{unresolved} that are absent from the bound salary file"
        )
    if mode is EngineMode.SHOWDOWN:
        captain = next(name for slot, name in pairs if slot == "CPT")
        flex = sorted(
            name_index[name][0] for slot, name in pairs if slot == "FLEX"
        )
        return f"CPT:{name_index[captain][0]}|FLEX:{'|'.join(flex)}"
    return "|".join(sorted(name_index[name][1] for _, name in pairs))


# ---------------------------------------------------------------------------
# Prize derivation
# ---------------------------------------------------------------------------


def derive_prizes(
    rows: list[RawStandingRow],
    *,
    payouts_path: Path,
    advertised_prize_value: Decimal,
    ticket_face_value: Decimal | None,
    owned_entry_ids: set[str],
    lineup_keys: dict[str, str],
    max_runtime_seconds: float,
    prize_rounding: str = "refuse",
) -> tuple[dict[str, int], object, dict]:
    """Join a per-entry prize in exact cents from the contest's payout table.

    DraftKings exports no prize, so this column is derived, never observed. It is
    derived by the registered ``nfl_reference_settlement_v1`` evaluator rather
    than by a second tie-splitting implementation here, because two
    implementations of exact tie-splitting would be two things to keep in
    agreement and the evaluator is the one that is already tested.

    The consequence is stated plainly rather than hidden: because this column is
    produced by the same evaluator that ``settlement._prepare_settlement`` later
    checks it against, ``STANDINGS_PRIZE_MISMATCH`` cannot fire on a file this
    tool wrote. That check is independent evidence only for a standings file that
    carries an externally observed prize, which a DraftKings export does not.
    """
    from nfl_dfs.payouts import parse_payout_csv
    from nfl_dfs.reference_settlement import (
        ReferenceBudget,
        ReferenceFieldEntry,
        evaluate_reference_settlement,
    )

    field_size = len(rows)
    tiers = parse_payout_csv(
        payouts_path,
        ticket_face_value=float(ticket_face_value) if ticket_face_value is not None else None,
        advertised_value=float(advertised_prize_value),
        field_size=field_size,
        reserved_entry_count=max(len(owned_entry_ids), 1),
        allow_zero_payout=True,
    )
    entries = tuple(
        ReferenceFieldEntry(
            entry_id=row.entry_id,
            score=row.points_2dp,
            lineup_key=lineup_keys[row.entry_id],
            operator_owned=row.entry_id in owned_entry_ids,
        )
        for row in rows
    )
    result = evaluate_reference_settlement(
        entries,
        tiers,
        field_size=field_size,
        ticket_face_value=ticket_face_value,
        advertised_prize_value=advertised_prize_value,
        budget=ReferenceBudget(
            max_entries=max(field_size, 1),
            max_work_units=max(field_size * 4, 1_000_000),
            max_runtime_seconds=max_runtime_seconds,
        ),
    )
    if prize_rounding not in PRIZE_ROUNDING_POLICIES:
        raise StandingsNormalizationError(
            f"UNKNOWN_PRIZE_ROUNDING_POLICY: {prize_rounding!r}, "
            f"expected one of {list(PRIZE_ROUNDING_POLICIES)}"
        )
    prizes: dict[str, int] = {}
    fractional = 0
    residual = Fraction(0)
    for settled in result.rows:
        cents = settled.gross_prize.cents
        if cents.denominator != 1:
            if prize_rounding == "refuse":
                raise StandingsNormalizationError(
                    f"PRIZE_NOT_WHOLE_CENTS: EntryId {settled.entry_id} settles to "
                    f"{cents} cents across a {settled.tie_count}-way tie at rank "
                    f"{settled.rank}, which is not an exact cent amount. "
                    "nfl_standings_csv_v2 cannot hold it; see Q1B in backlog.md. "
                    "Rerun with --prize-rounding half-even to record the residual."
                )
            fractional += 1
            whole = int(
                (Decimal(cents.numerator) / Decimal(cents.denominator)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_EVEN
                )
            )
            residual += cents - whole
            prizes[settled.entry_id] = whole
            continue
        prizes[settled.entry_id] = int(cents)
    accounting = {
        "policy": prize_rounding,
        "entries_with_fractional_exact_share": fractional,
        "residual_cents_after_rounding": str(residual),
        "total_paid_entries": sum(1 for value in prizes.values() if value > 0),
        "total_prize_cents": sum(prizes.values()),
    }
    return prizes, result, accounting


# ---------------------------------------------------------------------------
# Writing the normalized artifact
# ---------------------------------------------------------------------------


def render_normalized_csv(
    rows: list[RawStandingRow], prizes: dict[str, int], lineup_keys: dict[str, str]
) -> bytes:
    """Render ``nfl_standings_csv_v2`` deterministically.

    Ordered by rank then EntryId, CRLF terminated, no BOM: the same bytes for the
    same export every time, which is what makes the content-addressed path and
    the determinism test mean anything.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(NORMALIZED_COLUMNS)
    for row in sorted(rows, key=lambda item: (item.rank, item.entry_id)):
        cents = prizes[row.entry_id]
        writer.writerow(
            (
                row.entry_id,
                row.rank,
                f"{row.points_2dp:.2f}",
                f"{Decimal(cents) / 100:.2f}",
                lineup_keys[row.entry_id],
            )
        )
    return buffer.getvalue().encode("utf-8")


def normalize_export(
    raw_path: Path,
    *,
    salaries: Path,
    payouts: Path,
    advertised_prize_value: Decimal,
    ticket_face_value: Decimal | None = None,
    owned_entry_ids: set[str] | None = None,
    draft_group: str | None = None,
    output_root: Path | None = None,
    expected_field_size: int | None = None,
    max_runtime_seconds: float = 120.0,
    unsubmitted_entry_policy: str = "refuse",
    prize_rounding: str = "refuse",
) -> NormalizationResult:
    """Normalize one delivered export. Refuses rather than repairs."""
    output_root = output_root or NORMALIZED_DIR
    owned_entry_ids = owned_entry_ids or set()

    contest_id = contest_id_from_filename(raw_path)
    export = read_raw_export(raw_path)
    rows, dropped_columns, adjusted_rows, worst_adjustment = parse_raw_standings(
        export, unsubmitted_entry_policy=unsubmitted_entry_policy
    )

    if expected_field_size is not None and len(rows) != expected_field_size:
        raise StandingsNormalizationError(
            f"FIELD_SIZE_DISAGREEMENT: {raw_path.name} carries {len(rows)} entries but "
            f"the supplied contest facts declare {expected_field_size}"
        )

    try:
        slate = parse_salaries(salaries, draft_group=draft_group)
    except DraftKingsParseError as exc:
        raise StandingsNormalizationError(
            f"SALARY_SNAPSHOT_UNREADABLE: {salaries}: {exc}"
        ) from exc
    name_index = build_name_index(slate)

    unsubmitted = [row.entry_id for row in rows if not row.submitted_lineup]
    if unsubmitted and set(unsubmitted) & owned_entry_ids:
        # An operated entry with no lineup means the portfolio never reached
        # DraftKings. That is a fact about the slate, not a normalization
        # question, and it must never be papered over with a sentinel.
        raise StandingsNormalizationError(
            "OWNED_ENTRY_NEVER_SUBMITTED: operated Entry IDs "
            f"{sorted(set(unsubmitted) & owned_entry_ids)} carry no lineup in the "
            "export; the selected assignment was never entered"
        )
    lineup_keys = {
        row.entry_id: (
            canonical_lineup_key(
                row.lineup_raw,
                slate.mode,
                name_index,
                row_number=row.row_number,
                entry_id=row.entry_id,
            )
            if row.submitted_lineup
            else f"{UNSUBMITTED_LINEUP_SENTINEL}:{row.entry_id}"
        )
        for row in rows
    }

    prizes, reference, prize_accounting = derive_prizes(
        rows,
        payouts_path=payouts,
        advertised_prize_value=advertised_prize_value,
        ticket_face_value=ticket_face_value,
        owned_entry_ids=owned_entry_ids,
        lineup_keys=lineup_keys,
        max_runtime_seconds=max_runtime_seconds,
        prize_rounding=prize_rounding,
    )

    payload = render_normalized_csv(rows, prizes, lineup_keys)
    digest = sha256_bytes(payload)

    destination = output_root / contest_id
    destination.mkdir(parents=True, exist_ok=True)
    normalized_path = destination / f"{digest}.csv"
    manifest_path = destination / f"{digest}.manifest.json"

    manifest = {
        "schema_version": MANIFEST_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contest_id": contest_id,
        "raw": {
            "path": _repo_relative(export.path),
            "sha256": export.sha256,
            "byte_count": export.byte_count,
            "zip_member": export.zip_member,
        },
        "normalized": {
            "path": _repo_relative(normalized_path),
            "sha256": digest,
            "byte_count": len(payload),
            "artifact_version": STANDINGS_ARTIFACT_VERSION,
            "row_count": len(rows),
        },
        "observed_field_size": len(rows),
        "mode": slate.mode.value,
        "salary_binding": {
            "path": _repo_relative(Path(salaries)),
            "sha256": slate.salary_hash,
            "draft_group": slate.draft_group,
            "player_rows": len(slate.players),
        },
        "points": {
            "rule": "ROUND_HALF_EVEN to 0.01",
            "reason": (
                "DraftKings exports float round-trip noise in Points; its own Rank "
                "column is computed from the true 2-decimal score."
            ),
            "rows_adjusted": adjusted_rows,
            "max_adjustment": str(worst_adjustment),
            "tolerance": str(MAX_POINTS_ADJUSTMENT),
        },
        "lineup": {
            "rule": "canonical key rebuilt from the bound salary snapshot",
            "source_format": "DraftKings slot-tagged names",
            "provenance": "DERIVED_FROM_SALARY_SNAPSHOT",
            "unsubmitted_entry_policy": unsubmitted_entry_policy,
            "unsubmitted_entry_count": len(unsubmitted),
            "unsubmitted_entry_note": (
                "Field members who paid in and never submitted a lineup. They score "
                "zero, tie at the last rank, win nothing, and each forms its own "
                "duplication group. nfl_standings_csv_v2 has no representation for "
                "them; see Q1B in backlog.md."
            )
            if unsubmitted
            else None,
        },
        "prize": {
            "provenance": "DERIVED_REFERENCE_SETTLEMENT_V1",
            "observed_in_export": False,
            "note": (
                "DraftKings exports no per-entry prize. This column is joined from "
                "the payout table by the reference evaluator, so the downstream "
                "STANDINGS_PRIZE_MISMATCH check cannot be independent evidence."
            ),
            "payout_path": _repo_relative(Path(payouts)),
            "payout_sha256": sha256_bytes(Path(payouts).read_bytes()),
            "advertised_prize_value": str(advertised_prize_value),
            "ticket_face_value": (
                str(ticket_face_value) if ticket_face_value is not None else None
            ),
            "reference_evaluator_version": reference.evaluator_version,
            "reference_paid_rank_count": reference.paid_rank_count,
            "rounding": prize_accounting,
        },
        "ownership_block_columns_dropped": dropped_columns,
        "owned_entry_ids": sorted(owned_entry_ids),
        "credentials_or_account_state_stored": False,
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )

    if normalized_path.exists() and normalized_path.read_bytes() != payload:
        raise StandingsNormalizationError(
            f"NORMALIZED_COLLISION: {normalized_path} exists with different bytes"
        )
    normalized_path.write_bytes(payload)
    manifest_path.write_bytes(manifest_bytes)

    # The delivered bytes must be exactly as delivered. Cheap to prove, and the
    # one guarantee this tool makes that everything downstream depends on.
    if sha256_bytes(export.path.read_bytes()) != export.sha256:
        raise StandingsNormalizationError(
            f"RAW_EXPORT_MUTATED: {export.path} changed while being normalized"
        )

    return NormalizationResult(
        contest_id=contest_id,
        raw=export,
        normalized_path=normalized_path,
        normalized_sha256=digest,
        normalized_byte_count=len(payload),
        row_count=len(rows),
        manifest_path=manifest_path,
        manifest=manifest,
    )


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Survey mode
# ---------------------------------------------------------------------------


def survey_inbox(
    inbox: Path | None = None, *, unsubmitted_entry_policy: str = "sentinel"
) -> list[dict]:
    """Report what each delivered export is, without normalizing anything.

    Useful before any salary or payout binding exists: it reads the export, says
    how many entries the contest actually settled with, and names what is still
    required. The observed row count is the contest's true complete field size,
    which is otherwise nowhere on disk.
    """
    inbox = inbox or INBOX_DIR
    findings: list[dict] = []
    if not inbox.is_dir():
        return findings
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        record: dict = {"file": path.name}
        try:
            record["contest_id"] = contest_id_from_filename(path)
            export = read_raw_export(path)
            rows, dropped, adjusted, worst = parse_raw_standings(
                export, unsubmitted_entry_policy=unsubmitted_entry_policy
            )
            record.update(
                {
                    "raw_sha256": export.sha256,
                    "raw_byte_count": export.byte_count,
                    "observed_field_size": len(rows),
                    "unsubmitted_entries": sum(1 for row in rows if not row.submitted_lineup),
                    "points_rows_adjusted": adjusted,
                    "points_max_adjustment": str(worst),
                    "ownership_block_columns_dropped": dropped,
                    "status": "READABLE",
                }
            )
        except StandingsNormalizationError as exc:
            record.update({"status": "REFUSED", "refusal": str(exc)})
        findings.append(record)
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize a raw DraftKings standings export into nfl_standings_csv_v2."
    )
    parser.add_argument("--raw", help="one export in data/standings/inbox/")
    parser.add_argument("--salaries", help="the frozen salary snapshot for that slate")
    parser.add_argument("--payouts", help="the contest's payout table CSV")
    parser.add_argument("--advertised-prize-value", help="exact advertised cash+ticket value")
    parser.add_argument("--ticket-face-value", default=None)
    parser.add_argument("--draft-group", default=None)
    parser.add_argument(
        "--owned-entry-id", action="append", default=[], metavar="ENTRY_ID"
    )
    parser.add_argument(
        "--expected-field-size",
        type=int,
        default=None,
        help="refuse if the export disagrees with this declared contest fact",
    )
    parser.add_argument("--max-runtime-seconds", type=float, default=120.0)
    parser.add_argument(
        "--unsubmitted-entry-policy",
        choices=UNSUBMITTED_ENTRY_POLICIES,
        default="refuse",
        help=(
            "how to treat a real field member who never submitted a lineup: "
            "refuse (default, keeps the strict nfl_standings_csv_v2 contract) or "
            "sentinel (records the absence explicitly)"
        ),
    )
    parser.add_argument(
        "--prize-rounding",
        choices=PRIZE_ROUNDING_POLICIES,
        default="refuse",
        help=(
            "what to do when an exact tie split is not a whole number of cents: "
            "refuse (default) or half-even (records the residual in the manifest)"
        ),
    )
    parser.add_argument(
        "--survey",
        action="store_true",
        help="report every delivered export without normalizing or writing anything",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.survey:
            findings = survey_inbox()
            if args.json:
                print(json.dumps(findings, indent=2))
            else:
                for record in findings:
                    if record["status"] == "READABLE":
                        print(
                            f"{record['contest_id']:>10}  field={record['observed_field_size']:>7}  "
                            f"no_lineup={record['unsubmitted_entries']:>5}  "
                            f"points_adjusted={record['points_rows_adjusted']:>7}  {record['file']}"
                        )
                    else:
                        print(f"{record.get('contest_id', '?'):>10}  {record['refusal']}")
            return 0

        missing = [
            name
            for name, value in (
                ("--raw", args.raw),
                ("--salaries", args.salaries),
                ("--payouts", args.payouts),
                ("--advertised-prize-value", args.advertised_prize_value),
            )
            if not value
        ]
        if missing:
            raise StandingsNormalizationError(
                f"NORMALIZATION_INPUTS_REQUIRED: {missing}. A DraftKings export alone "
                "cannot produce nfl_standings_csv_v2: it carries no prize column and "
                "names its lineups, so the payout table and the frozen salary snapshot "
                "are both required. Use --survey to read an export without them."
            )
        result = normalize_export(
            Path(args.raw),
            salaries=Path(args.salaries),
            payouts=Path(args.payouts),
            advertised_prize_value=Decimal(args.advertised_prize_value),
            ticket_face_value=(
                Decimal(args.ticket_face_value) if args.ticket_face_value else None
            ),
            owned_entry_ids=set(args.owned_entry_id),
            draft_group=args.draft_group,
            expected_field_size=args.expected_field_size,
            max_runtime_seconds=args.max_runtime_seconds,
            unsubmitted_entry_policy=args.unsubmitted_entry_policy,
            prize_rounding=args.prize_rounding,
        )
        if args.json:
            print(json.dumps(result.manifest, indent=2))
        else:
            print(f"contest            {result.contest_id}")
            print(f"raw sha256         {result.raw.sha256}")
            print(f"normalized         {_repo_relative(result.normalized_path)}")
            print(f"normalized sha256  {result.normalized_sha256}")
            print(f"rows               {result.row_count}")
            print(f"manifest           {_repo_relative(result.manifest_path)}")
        return 0
    except (StandingsNormalizationError, InvalidOperation) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
