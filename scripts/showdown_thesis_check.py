#!/usr/bin/env python3
"""Each Entry ID's thesis, read from a run's claim, and the one rule that decides whether a roster follows it (Session 66).

Shared by `qa_showdown_portfolio.py` and `showdown_value_add.py`. Each imports this module only when `--policy` and
`--claim` are given, so a run without them executes none of it. The judgment pass after the engine (a Captain swap, a
FLEX swap, `showdown_value_add.py`) can turn a row into a different bet under the old name (P8 principle 6); this makes
that visible and refuses it.

Inputs, both from one `run-slate` run:

* `--policy`: the run's normalized v4 policy (`portfolio_policy.normalized.json`), reparsed with the audit's own strict
  parser, which also checks its bytes are canonical, each thesis's `rows` equal the allotment and its `effective_bounds`
  equal the declared bounds widened for that thesis.
* `--claim`: the run's `selection_report.json`. `selection.portfolio_policy.theses.entries` names the thesis each Entry ID
  filled after the contest step (it is relabelled from the final assignment). A swap changes a roster's canonical key,
  so the thesis is read by Entry ID, never by looking the edited roster up in `by_lineup`; `by_lineup` is used only to
  refuse a file whose lineups were moved between Entry IDs after the run.

Refusals, each a named code and never a PASS:

* `THESIS_POLICY_UNREADABLE`, `THESIS_POLICY_NOT_A_PORTFOLIO` (a v2, v3 or no-thesis policy), `THESIS_POLICY_SALARY_MISMATCH`
  (the policy's salary SHA-256 is not the salary file's), `THESIS_POLICY_ENTRY_IDS_NOT_IN_TEMPLATE`;
* `THESIS_CLAIM_UNREADABLE`, `THESIS_CLAIM_MISSING`, `THESIS_CLAIM_POLICY_MISMATCH` (the claim's `normalized_policy_sha256` is
  not the policy file's), `THESIS_CLAIM_ENTRY_IDS_MISMATCH`, `THESIS_CLAIM_UNKNOWN_THESIS`, `THESIS_CLAIM_DISAGREES_WITH_ROWS`.

Not established: the claim file is bound to the policy and to the rows it names, but not to the run itself (the run's
`cowork_run.json` hashes it). A doctored `entries` could change only which rules a row is held to, never a number or a
gate. A thesis is a choice, not a forecast; nothing here reads or writes a projection.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from nfl_dfs.contracts import SlateContract
from nfl_dfs.lineups import LineupValidationError, roster_canonical_key
from nfl_dfs.portfolio_enforcement import _parse_audited_policy_controls
from nfl_dfs.portfolio_policy import thesis_roster_violations
from nfl_dfs.showdown_theses import ShowdownThesis, backup_quarterbacks

EVALUATED, PARTIAL, NOT_EVALUATED = "EVALUATED", "PARTIAL", "NOT_EVALUATED"


class ThesisInputRefused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class ThesisBook:
    """The active theses, each Entry ID's claimed thesis, and each thesis's own backup-quarterback set."""

    slate: SlateContract
    theses: Mapping[str, ShowdownThesis]
    entries: Mapping[str, str | None]  # Entry ID to thesis name; None (or absent) is a row with no claim
    backups: Mapping[str, frozenset[str]] = field(default_factory=dict)
    backup_state: str = NOT_EVALUATED
    unevaluated_teams: tuple[str, ...] = ()
    hashes: Mapping[str, str] = field(default_factory=dict)

    def check(self, entry_id: str, roster_ids: Sequence[str]) -> tuple[str, tuple[str, ...]] | None:
        """(the Entry ID's thesis, the rules `roster_ids` breaks under it), or None for a row with no claim."""

        name = self.entries.get(str(entry_id))
        if name is None:
            return None
        return name, tuple(thesis_roster_violations(
            self.slate, roster_ids, self.theses[name], self.backups.get(name, frozenset())))

    def describe(self) -> dict[str, object]:
        return {
            "policy_sha256": self.hashes.get("policy_sha256"),
            "claim_sha256": self.hashes.get("claim_sha256"),
            "salary_sha256": self.hashes.get("salary_sha256"),
            "theses": list(self.theses),
            "backup_quarterback": self.backup_state,
            "backup_quarterbacks_unevaluated_teams": list(self.unevaluated_teams),
        }


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_thesis_book(
    slate: SlateContract,
    template_entry_ids: Sequence[str],
    rosters: Mapping[str, Sequence[str]],
    policy_path: str | Path,
    claim_path: str | Path,
) -> ThesisBook:
    """Bind a run's policy and claim to this slate, template and file, or refuse by name.

    `rosters` is each row of the file being checked by Entry ID, used only to refuse a file whose lineups were
    moved between Entry IDs by hand after the run.
    """

    try:
        policy_raw = Path(policy_path).read_bytes()
        controls = _parse_audited_policy_controls(policy_raw)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise ThesisInputRefused("THESIS_POLICY_UNREADABLE", f"{policy_path}: {type(exc).__name__}: {exc}")
    active = [item for item in controls.theses if item.active]
    if controls.thesis_schema != "v4" or not active:
        raise ThesisInputRefused(
            "THESIS_POLICY_NOT_A_PORTFOLIO",
            f"{policy_path} is not a normalized v4 policy with an active thesis; a v2, v3 or no-thesis policy is not checked")
    if controls.salary_sha256 != slate.salary_hash:
        raise ThesisInputRefused(
            "THESIS_POLICY_SALARY_MISMATCH",
            f"the policy binds salary {controls.salary_sha256}, this file's salary bytes are {slate.salary_hash}")
    known = {str(entry) for entry in template_entry_ids}
    outside = [entry for entry in controls.entry_ids if entry not in known]
    if outside:
        raise ThesisInputRefused("THESIS_POLICY_ENTRY_IDS_NOT_IN_TEMPLATE", ", ".join(outside))

    try:
        claim_raw = Path(claim_path).read_bytes()
        record = json.loads(claim_raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise ThesisInputRefused("THESIS_CLAIM_UNREADABLE", f"{claim_path}: {type(exc).__name__}: {exc}")
    selector = record.get("selection") if isinstance(record, dict) else None
    block = selector.get("portfolio_policy") if isinstance(selector, dict) else None
    claim = block.get("theses") if isinstance(block, dict) else None
    if not isinstance(claim, dict) or not isinstance(claim.get("entries"), dict) or not isinstance(claim.get("by_lineup"), dict):
        raise ThesisInputRefused(
            "THESIS_CLAIM_MISSING", f"{claim_path} has no selection.portfolio_policy.theses with entries and by_lineup")
    policy_sha256 = _sha256(policy_raw)
    if block.get("normalized_policy_sha256") != policy_sha256:
        raise ThesisInputRefused(
            "THESIS_CLAIM_POLICY_MISMATCH",
            f"the claim names policy {block.get('normalized_policy_sha256')}, the policy file is {policy_sha256}")
    if block.get("entry_ids") != list(controls.entry_ids) or not set(claim["entries"]) <= set(controls.entry_ids):
        raise ThesisInputRefused("THESIS_CLAIM_ENTRY_IDS_MISMATCH", "the claim's Entry IDs are not the policy's, in order")

    names = {item.name for item in active}
    entries: dict[str, str | None] = {}
    for entry, name in claim["entries"].items():
        if name is not None and name not in names:
            raise ThesisInputRefused("THESIS_CLAIM_UNKNOWN_THESIS", f"entry {entry} claims {name!r}, which the policy does not hold active")
        entries[str(entry)] = name

    # A lineup that is still where the run left it carries its own thesis; if that is not the Entry ID's claim, the
    # lineups were moved between Entry IDs and the Entry ID's thesis is ambiguous, so the check refuses.
    moved = []
    for entry, name in sorted(entries.items()):
        roster = rosters.get(entry)
        if name is None or roster is None:
            continue
        try:
            key = roster_canonical_key(slate, roster)
        except LineupValidationError:
            continue
        if key in claim["by_lineup"] and claim["by_lineup"][key] != name:
            moved.append(entry)
    if moved:
        raise ThesisInputRefused(
            "THESIS_CLAIM_DISAGREES_WITH_ROWS",
            f"entries {', '.join(moved)} hold lineups the run gave to other Entry IDs; run the check on the run's own file")

    theses = {item.name: item for item in active}
    depth = selector.get("qb_depth_roles")
    backups: dict[str, frozenset[str]] = {}
    unevaluated: tuple[str, ...] = ()
    for name, item in theses.items():
        backups[name], unevaluated = backup_quarterbacks(slate, item, depth)
    quarterback_teams = {row.team for row in slate.players if row.position == "QB"}
    state = EVALUATED if not unevaluated else (NOT_EVALUATED if quarterback_teams <= set(unevaluated) else PARTIAL)
    return ThesisBook(
        slate=slate, theses=theses, entries=entries, backups=backups, backup_state=state,
        unevaluated_teams=tuple(unevaluated),
        hashes={"policy_sha256": policy_sha256, "claim_sha256": _sha256(claim_raw), "salary_sha256": slate.salary_hash})
