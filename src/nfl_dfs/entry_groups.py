"""Entry groups (Session 11, R28, R29): what a DraftKings entries template authorizes, row by row.

Until Session 11 one prefilled row refused the whole file on every path. Now
authority is per row, and every producer reads it from `plan_entries`:

- a **blank** row (every roster cell empty) may be filled;
- a **prefilled** row (every roster cell set) is preserved byte for byte. Its
  cells are parsed into exact current-slate DraftKings IDs where they resolve,
  and its roster joins the set no generated lineup may repeat (R29: "within a
  given portfolio keep all submitted lineups distinct and unique");
- a **partly filled** row (some cells set, some blank) is neither. It is
  preserved, never touched, and named unresolved: filling around existing
  cells is governed late swap's (Session 12).

A row outcome is one of four, and they never overlap: `fillable` blank rows are
filled or named unfilled by the producer; `preserved` rows are prefilled rows
that resolve; `unresolved` rows are partly filled rows, prefilled rows that do
not resolve or repeat an earlier prefilled roster, and every row of a group the
engine cannot state (below). Every unresolved row is named by a limitation.

Rows group by Contest ID. A group whose rows disagree on the contest name or the
entry fee cannot say which contest its rows enter, so its rows are left as they
are and named (`ENTRY_GROUP_UNRESOLVED`, `V`, scoped to those rows); every other
group still ships. A file-scoped integrity problem still withholds the file:
that is the producers' own gates, unchanged.

A prefilled cell resolves as a bare DraftKings ID or as text ending in `(ID)`,
the form the fallback scripts read (`scripts/write_dk_entries.py`). Nothing else
is guessed: a name, a stale ID or another slate's player does not resolve, and
since such a row cannot equal an exact-ID roster it stays out of the
distinctness set. Only exact current-slate IDs ever enter it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .contracts import DeliveryLimitation, EntryAuthorization, SlateContract
from .dk import EntryTemplate
from .gate_registry import GateRegistry
from .lineups import roster_canonical_key, validate_lineup

ROW_BLANK = "BLANK"
ROW_PREFILLED = "PREFILLED"
ROW_PARTIAL = "PARTLY_FILLED"
_BARE_ID = re.compile(r"[0-9]+")
_TRAILING_ID = re.compile(r"\(([0-9]+)\)\s*$")


def row_kind(entry: EntryAuthorization) -> str:
    """`BLANK`, `PREFILLED` or `PARTLY_FILLED`, from the template's own roster cells."""

    cells = entry.existing_cells
    if not any(cells):
        return ROW_BLANK
    if all(cells):
        return ROW_PREFILLED
    return ROW_PARTIAL


def blank_entry_ids(template: EntryTemplate) -> tuple[str, ...]:
    """Every row whose roster cells are all blank, in template order."""

    return tuple(e.entry_id for e in template.authorizations if row_kind(e) == ROW_BLANK)


def prefilled_cell_id(cell: str) -> str | None:
    """The DraftKings ID a prefilled cell names, or None when it names none exactly."""

    value = cell.strip()
    if _BARE_ID.fullmatch(value):
        return value
    match = _TRAILING_ID.search(value)
    return match.group(1) if match else None


@dataclass(frozen=True)
class PrefilledRoster:
    """One prefilled row read against the slate."""

    entry_id: str
    roster: tuple[str, ...] | None  # every cell's exact current-slate ID, when all resolve
    canonical_key: str | None       # its identity (R29), when `roster` is set
    errors: tuple[str, ...]         # why it does not resolve; empty when it does

    @property
    def resolved(self) -> bool:
        return self.roster is not None and not self.errors


def read_prefilled(entry: EntryAuthorization, slate: SlateContract) -> PrefilledRoster:
    """Parse one prefilled row into exact current-slate DraftKings IDs, where it resolves."""

    ids = tuple(prefilled_cell_id(cell) for cell in entry.existing_cells)
    pool = {player.dk_id for player in slate.players}
    unparsed = [index + 1 for index, value in enumerate(ids) if value is None]
    if unparsed:
        return PrefilledRoster(entry.entry_id, None, None, (
            f"slots {unparsed} hold no exact DraftKings ID (a bare ID or 'Name (ID)')",))
    roster = tuple(value for value in ids if value is not None)
    outside = [value for value in roster if value not in pool]
    if outside:
        return PrefilledRoster(entry.entry_id, None, None, (
            f"IDs {outside} are not in the current salary file",))
    key = roster_canonical_key(slate, roster)
    result = validate_lineup(slate, roster)
    return PrefilledRoster(entry.entry_id, roster, key, result.errors)


@dataclass(frozen=True)
class EntryGroup:
    """One Contest ID's rows, in template order."""

    contest_id: str
    contest_names: tuple[str, ...]
    entry_fees: tuple[float, ...]
    entry_ids: tuple[str, ...]

    @property
    def stated(self) -> bool:
        """Whether every row agrees on one contest name and one entry fee."""

        return len(self.contest_names) == 1 and len(self.entry_fees) == 1


@dataclass(frozen=True)
class EntryPlan:
    """What a template authorizes against one slate, row by row and by Contest ID."""

    order: tuple[str, ...]
    kinds: Mapping[str, str]
    fillable: tuple[str, ...]
    preserved: tuple[str, ...]
    unresolved: tuple[str, ...]
    prefilled: Mapping[str, PrefilledRoster]
    forbidden_rosters: tuple[tuple[str, ...], ...]
    forbidden_keys: frozenset[str]
    groups: tuple[EntryGroup, ...]
    findings: tuple[tuple[str, tuple[str, ...], str], ...]

    @property
    def left_blank(self) -> tuple[str, ...]:
        """Blank rows no producer may fill: those of an unresolved group."""

        fillable = set(self.fillable)
        return tuple(eid for eid in self.order
                     if self.kinds[eid] == ROW_BLANK and eid not in fillable)

    def limitations(self, registry: GateRegistry) -> list[DeliveryLimitation]:
        """Each finding as a registry limitation naming its rows."""

        return [registry.limitation(code, entry_ids=ids, detail=detail)
                for code, ids, detail in self.findings]

    def slate_summary(self) -> dict[str, object]:
        return {
            "entry_rows": len(self.order),
            "blank_rows": [eid for eid in self.order if self.kinds[eid] == ROW_BLANK],
            "prefilled_rows": [eid for eid in self.order if self.kinds[eid] == ROW_PREFILLED],
            "partly_filled_rows": [eid for eid in self.order if self.kinds[eid] == ROW_PARTIAL],
            "fillable_rows": list(self.fillable),
            "preserved_rows": list(self.preserved),
            "unresolved_rows": list(self.unresolved),
            "contest_ids": [group.contest_id for group in self.groups],
        }


def _finding(code: str, entry_ids: Iterable[str], detail: str) -> tuple[str, tuple[str, ...], str]:
    return code, tuple(entry_ids), detail


def plan_entries(template: EntryTemplate, slate: SlateContract) -> EntryPlan:
    """Classify every row, read every prefilled roster, and group rows by Contest ID.

    `template` must already be reconciled to `slate` (same mode and width);
    this reads it and never refuses the file.
    """

    order = tuple(entry.entry_id for entry in template.authorizations)
    kinds = {entry.entry_id: row_kind(entry) for entry in template.authorizations}
    findings: list[tuple[str, tuple[str, ...], str]] = []
    by_contest: dict[str, list[EntryAuthorization]] = {}
    for entry in template.authorizations:
        by_contest.setdefault(entry.contest_id, []).append(entry)
    groups = tuple(
        EntryGroup(
            contest_id=contest_id,
            contest_names=tuple(dict.fromkeys(entry.contest_name for entry in rows)),
            entry_fees=tuple(dict.fromkeys(entry.entry_fee for entry in rows)),
            entry_ids=tuple(entry.entry_id for entry in rows),
        )
        for contest_id, rows in by_contest.items()
    )
    unstated: set[str] = set()
    for group in groups:
        if not group.stated:
            unstated.update(group.entry_ids)
            findings.append(_finding(
                "ENTRY_GROUP_UNRESOLVED", group.entry_ids,
                f"Contest ID {group.contest_id}'s rows disagree on the contest name "
                f"{list(group.contest_names)} or the entry fee {list(group.entry_fees)}, so which "
                "contest they enter cannot be stated; they are left as they are and every other "
                "group ships"))

    partial = [eid for eid in order if kinds[eid] == ROW_PARTIAL and eid not in unstated]
    if partial:
        findings.append(_finding(
            "ENTRY_ROW_PARTLY_PREFILLED", partial,
            "some roster cells are set and some blank; the row is preserved byte for byte and never "
            "filled around, which is governed late swap's (Session 12)"))

    prefilled: dict[str, PrefilledRoster] = {}
    forbidden: dict[str, tuple[str, ...]] = {}
    first_holder: dict[str, str] = {}
    unresolved_prefilled: dict[str, str] = {}
    for entry in template.authorizations:
        if kinds[entry.entry_id] != ROW_PREFILLED:
            continue
        read = read_prefilled(entry, slate)
        prefilled[entry.entry_id] = read
        if read.roster is not None and read.canonical_key is not None:
            forbidden.setdefault(read.canonical_key, read.roster)
        if not read.resolved:
            unresolved_prefilled[entry.entry_id] = "; ".join(read.errors)
            continue
        earlier = first_holder.setdefault(str(read.canonical_key), entry.entry_id)
        if earlier != entry.entry_id:
            unresolved_prefilled[entry.entry_id] = (
                f"repeats the prefilled roster of Entry {earlier}, which R29 never allows; "
                "the engine never changes a filled cell")
    named = [eid for eid in order if eid in unresolved_prefilled and eid not in unstated]
    if named:
        findings.append(_finding(
            "ENTRY_PREFILLED_ROSTER_UNRESOLVED", named,
            "prefilled rows preserved byte for byte that do not resolve to a distinct legal lineup "
            "of exact current-slate DraftKings IDs: "
            + "; ".join(f"{eid}: {unresolved_prefilled[eid]}" for eid in named)))

    unresolved_set = unstated | set(partial) | set(named)
    fillable = tuple(eid for eid in order if kinds[eid] == ROW_BLANK and eid not in unstated)
    preserved = tuple(eid for eid in order
                      if kinds[eid] == ROW_PREFILLED and eid not in unresolved_set)
    unresolved = tuple(eid for eid in order if eid in unresolved_set)
    return EntryPlan(
        order=order,
        kinds=kinds,
        fillable=fillable,
        preserved=preserved,
        unresolved=unresolved,
        prefilled=prefilled,
        forbidden_rosters=tuple(forbidden.values()),
        forbidden_keys=frozenset(forbidden),
        groups=groups,
        findings=tuple(findings),
    )


def group_report(
    plan: EntryPlan,
    *,
    delivered: Iterable[str] = (),
    unfilled: Iterable[str] = (),
    limitations: Iterable[DeliveryLimitation] = (),
) -> list[dict[str, object]]:
    """Per Contest ID: its rows by kind and outcome, and the codes naming each row not delivered.

    `delivered` and `unfilled` are the file's (`nfl_release_truths_v3`); a
    withheld file delivers nothing, and then its fillable rows are unfilled.
    """

    done = set(delivered)
    left = set(unfilled)
    preserved = set(plan.preserved)
    unresolved = set(plan.unresolved)
    reasons: dict[str, list[str]] = {}
    file_wide: list[str] = []
    for item in limitations:
        if not item.entry_ids:
            file_wide.append(item.code)
        for eid in item.entry_ids:
            codes = reasons.setdefault(eid, [])
            if item.code not in codes:
                codes.append(item.code)
    report = []
    for group in plan.groups:
        ids = group.entry_ids
        report.append({
            "contest_id": group.contest_id,
            "contest_name": group.contest_names[0] if group.stated else None,
            "entry_fee": group.entry_fees[0] if group.stated else None,
            "contest_names": list(group.contest_names),
            "entry_fees": list(group.entry_fees),
            "rows": len(ids),
            "blank": [eid for eid in ids if plan.kinds[eid] == ROW_BLANK],
            "prefilled": [eid for eid in ids if plan.kinds[eid] == ROW_PREFILLED],
            "partly_filled": [eid for eid in ids if plan.kinds[eid] == ROW_PARTIAL],
            "filled": [eid for eid in ids if eid in done],
            "unfilled": [eid for eid in ids if eid in left],
            "preserved": [eid for eid in ids if eid in preserved],
            "unresolved": [eid for eid in ids if eid in unresolved],
            "reasons": {eid: reasons.get(eid, []) or file_wide
                        for eid in ids if eid in left or eid in unresolved},
        })
    return report


def group_coverage(plan: EntryPlan, delivered: Iterable[str]) -> dict[str, int]:
    """Delivered rows per Contest ID, every group present."""

    done = set(delivered)
    return {group.contest_id: sum(1 for eid in group.entry_ids if eid in done)
            for group in plan.groups}
