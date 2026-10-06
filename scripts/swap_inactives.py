#!/usr/bin/env python3
"""Construction-only edits to an already-built Classic portfolio. NOT the
evidence layer: every mode reads the engine's own gated scores and the
current DraftKings salary file, and never invents an observation.

Provenance: promoted from `scripts/staging/slate_2026_09_27/swap_inactives.py`,
a session scratchpad that swapped newly inactive players and worked named
value adds into the Week 3 Classic portfolio by hand. This generalizes it to
four modes and gives every mode the same legality, caps and uniqueness the
portfolio was built under (see `scripts/build_classic_portfolio.py`, which
this deliberately mirrors: the same slot counts, DST/QB anti-correlation, and
bring-back definition, so a lineup this script writes never fails
`scripts/qa_classic_portfolio.py` Tier 1 for a reason this script could have
caught).

Modes (`--mode`):
  inactive    replace a newly OUT/IR/D player. Tries a same-slot single swap
              first (any legal, cap-fitting, exposure/overlap-respecting
              replacement, ranked by score); when none exists (the position
              broke: e.g. no legal single RB/WR/TE swap fits every FLEX
              constraint) falls back to a two-player swap, trading the
              absent player plus one non-core flex-eligible teammate for a
              better-scoring pair.
  value-add   work a named, currently-scored player into up to
              `--target-count` lineups, each time replacing the weakest
              non-core same-position-group player he beats.
  redeploy    salary-driven upgrades taken ONLY as Pareto gains (Session 62,
              R37; unused salary is never a defect, so nothing here chases the
              cap): a swap must raise the row's prior, fit the cap, keep the
              row legal and distinct, leave the QB, the DST, his stack, the
              bring-back and every `--protect` person alone, and leave no
              washout proxy worse (max exposure, top-3 union, mean pairwise
              overlap no higher; distinct people no fewer), checked on the
              whole portfolio. Every row, repeated to a fixed point, so a
              rerun on its own output changes nothing (`fixed_point` in
              the report; the 25-pass bound is reported if it is hit);
              `--changed-entry-id`
              restricts it. The rule is the engine's
              (`nfl_dfs.classic_redeploy`, Session 64: legality by
              `lineups.validate_lineup`, report `pareto_redeploy_v2`), the
              same code `run-slate`'s rung-4 build runs; with `--now` a
              person whose game has locked is never outgoing and never
              incoming. `--protect NAME_OR_ID` and
              `--protect-from <run json>` (a Classic run's
              `judgment_pass.protected_people`) name who never moves;
              `--status <official_status.csv>` names who is never added
              (INACTIVE), beside the scores file's own exclusions. The
              report (`construction.pareto_redeploy`, and printed) gives both
              goals before and after and every rejected swap with the goal it
              would have hurt; where no gain exists the portfolio stays.
  late-swap   the `inactive` replacement, restricted to cells whose game has
              not locked as of `--now` (from each player's own `Game Info`).
              A locked cell is never touched, whichever player is in it.

"Core" (never touched by value-add or redeploy, so the stack and bring-back
this portfolio was built for survive every edit): the QB, his own-team
WR/TE stackmates, and any opponent skill player supplying the bring-back.

Exit codes: 0 every named absent player (or, in `value-add`/`redeploy`, every
change asked for) was applied; 3 written with a shortfall, each one named on
stderr; 2 refused by name, nothing written.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from nfl_dfs import classic_redeploy
from nfl_dfs.classic_redeploy import (  # the Pareto rule lives in the engine since Session 64; one rule, not two
    DOES_NOT_ESTABLISH as PARETO_DOES_NOT_ESTABLISH,
    MAX_PASSES as PARETO_MAX_PASSES,
    REDEPLOY_RULE as PARETO_RULE,
    ROW_REJECTION_REASONS,
    WASHOUT_GOALS,
    proxies_hurt,
    render_report as render_pareto_report,
    washout_proxies,
)
from nfl_dfs.contracts import EngineMode, GameContract, SalaryPlayer, SlateContract

SALARY_COLUMNS = ("ID", "Name", "Position", "Roster Position", "Salary", "Game Info",
                  "TeamAbbrev", "Status")
UNAVAILABLE_STATUSES = {"O", "OUT", "IR", "D"}
FLEX_POSITIONS = ("RB", "WR", "TE")
EXIT_OK, EXIT_REFUSED, EXIT_PARTIAL = 0, 2, 3
EASTERN = ZoneInfo("America/New_York")


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# --------------------------------------------------------------------------- #
# Loaders, matching build_classic_portfolio.py's own vocabulary and columns.
# --------------------------------------------------------------------------- #


def read_csv_rows(path, what):
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise Refused(f"{what}_UNREADABLE", f"{path}: {exc}")


def load_salaries(path):
    rows = read_csv_rows(path, "SALARY")
    header = rows[0] if rows else []
    missing = [c for c in SALARY_COLUMNS if c not in header]
    if missing:
        raise Refused("SALARY_COLUMNS_MISSING", f"{path} lacks {missing}")
    index = {c: header.index(c) for c in SALARY_COLUMNS}
    sal = {}
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue
        rec = {c: (row[i].strip() if i < len(row) else "") for c, i in index.items()}
        if not rec["ID"]:
            continue
        if rec["ID"] in sal:
            raise Refused("SALARY_DUPLICATE_ID", rec["ID"])
        if "CPT" in rec["Roster Position"].split("/"):
            raise Refused("NOT_A_CLASSIC_SALARY_FILE", f"{path} has Showdown captain rows")
        try:
            rec["Salary"] = int(rec["Salary"])
        except ValueError:
            raise Refused("SALARY_UNREADABLE", f"ID {rec['ID']} salary {rec['Salary']!r}")
        sal[rec["ID"]] = rec
    if not sal:
        raise Refused("SALARY_EMPTY", f"{path} has no readable rows")
    return sal


def load_scores(path):
    try:
        with open(path, encoding="utf-8") as handle:
            by_id = json.load(handle)["by_dk_id"]
        return {str(k): float(v) for k, v in by_id.items()}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise Refused("SCORES_UNREADABLE", f"{path}: {type(exc).__name__}: {exc}")


def load_portfolio(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused("PORTFOLIO_UNREADABLE", f"{path}: {exc}")
    assignments = doc.get("assignments_by_entry_id")
    if not isinstance(assignments, dict) or not assignments:
        raise Refused("PORTFOLIO_HAS_NO_ASSIGNMENTS", f"{path} has no assignments_by_entry_id")
    for entry_id, roster in assignments.items():
        if not isinstance(roster, list) or len(roster) != 9:
            raise Refused("PORTFOLIO_ROSTER_MALFORMED", f"entry {entry_id} is not a nine-cell roster")
    return doc


def lock_at(row) -> datetime | None:
    """A salary row's kickoff, from its own `Game Info`, or `None` (TBD/postponed)."""

    parts = (row.get("Game Info") or "").split()
    if len(parts) < 3:
        return None
    try:
        naive = datetime.strptime(" ".join(parts[1:3]), "%m/%d/%Y %I:%M%p")
    except ValueError:
        return None
    return naive.replace(tzinfo=EASTERN)


# A kickoff the file does not state (TBD, postponed): the sentinel is never at or before a lock clock, so such a cell is never
# a locked outgoing cell, which is how late-swap treats it; `redeploy` below also keeps such a person out as an incoming one
# once a lock clock is given, which is how late-swap treats a candidate.
NEVER_LOCKED = datetime(9999, 12, 31, tzinfo=timezone.utc)


def slate_from_rows(sal, cap) -> SlateContract:
    """The engine's `SlateContract` for the salary rows this script already loaded (Session 64).

    `nfl_dfs.dk.parse_salaries` is the engine's file parser and refuses a file whose IDs are not numeric
    DraftKings IDs, which is every fixture this script's tests build, so the redeploy cannot start from the
    file. This is data plumbing, not a second legality: the legality that runs on the result is
    `lineups.validate_lineup`. A person's identity here is his DraftKings ID (this script counts exposure by ID),
    where the engine's file parser uses `TEAM|POS|Name`; they are one to one on a real Classic file."""

    players, games = [], {}
    for dk_id, row in sal.items():
        game_id = (row.get("Game Info") or "").split()[0] if (row.get("Game Info") or "").split() else ""
        away, home = game_id.split("@", 1) if "@" in game_id else ("", "")
        team = row["TeamAbbrev"]
        kickoff = lock_at(row) or NEVER_LOCKED
        players.append(SalaryPlayer(
            dk_id=dk_id, name=row["Name"], position=row["Position"],
            roster_positions=tuple(part for part in row["Roster Position"].split("/") if part),
            salary=int(row["Salary"]), team=team, opponent=home if team == away else away if away else "",
            game_id=game_id, lock_at=kickoff, status_raw=row.get("Status") or "", underlying_id=dk_id))
        games.setdefault(game_id, GameContract(game_id=game_id, away_team=away, home_team=home, lock_at=kickoff))
    return SlateContract(
        mode=EngineMode.CLASSIC, draft_group="swap_inactives", games=tuple(games.values()),
        scoring_version="draftkings_nfl_scoring_2026_fixture_v1", salary_hash="swap_inactives", players=tuple(players),
        salary_cap=int(cap))


# --------------------------------------------------------------------------- #
# Shared legality, matching build_classic_portfolio.py's own definitions.
# --------------------------------------------------------------------------- #


class Board:
    """Salary-row accessors and the legality rules the inactive, late-swap and value-add modes share. The redeploy
    does not use this mirror: it runs the engine's own legality on `engine_slate()`."""

    def __init__(self, sal, cap, floor):
        self.sal = sal
        self.cap = cap
        self.floor = floor
        self._slate = None

    def engine_slate(self) -> SlateContract:
        if self._slate is None:
            self._slate = slate_from_rows(self.sal, self.cap)
        return self._slate

    def P(self, i):
        return self.sal[i]["Position"]

    def S(self, i):
        return self.sal[i]["Salary"]

    def T(self, i):
        return self.sal[i]["TeamAbbrev"]

    def NM(self, i):
        return self.sal[i]["Name"]

    def G(self, i):
        return self.sal[i]["Game Info"].split()[0] if self.sal[i]["Game Info"] else ""

    def status(self, i):
        return (self.sal[i].get("Status") or "").upper()

    def lock(self, i):
        return lock_at(self.sal[i])

    def opponent(self, i):
        game = self.G(i)
        if "@" not in game:
            return ""
        away, home = game.split("@", 1)
        return home if self.T(i) == away else away

    def qb_of(self, roster):
        qbs = [i for i in roster if i in self.sal and self.P(i) == "QB"]
        return qbs[0] if qbs else None

    def has_bringback(self, roster):
        qb = self.qb_of(roster)
        if qb is None:
            return False
        opp = self.opponent(qb)
        return any(self.T(i) == opp and self.P(i) != "DST" for i in roster if i in self.sal)

    def has_stack(self, roster):
        qb = self.qb_of(roster)
        if qb is None:
            return False
        return any(
            i != qb and i in self.sal and self.T(i) == self.T(qb) and self.P(i) in ("WR", "TE")
            for i in roster
        )

    def preserves_shape(self, original, trial):
        """A stack or bring-back this roster already had must survive the
        edit; this script is never the reason a portfolio's construction
        preferences regress, whatever mode is doing the editing."""

        if self.has_stack(original) and not self.has_stack(trial):
            return False
        if self.has_bringback(original) and not self.has_bringback(trial):
            return False
        return True

    def is_anti_correlated(self, roster):
        dsts = [i for i in roster if i in self.sal and self.P(i) == "DST"]
        if not dsts:
            return False
        dst = dsts[0]
        foe = self.opponent(dst)
        if any(self.T(i) == foe and self.P(i) != "DST" for i in roster if i in self.sal):
            return True  # the DST plays a team you also rostered skill players from
        qb = self.qb_of(roster)
        if qb is not None and self.T(dst) == self.opponent(qb):
            return True  # the DST plays against the QB you rostered
        return False

    def is_legal(self, roster):
        if len(set(roster)) != 9 or any(i not in self.sal for i in roster):
            return False
        need = collections.Counter(self.P(i) for i in roster)
        if need["QB"] != 1 or need["DST"] != 1 or need["RB"] < 2 or need["WR"] < 3 or need["TE"] < 1:
            return False
        total = sum(self.S(i) for i in roster)
        if total > self.cap or total < self.floor:
            return False
        if len({self.G(i) for i in roster}) < 2:
            return False
        return not self.is_anti_correlated(roster)

    def core(self, roster):
        """QB, his stackmates, and his bring-back: never touched by value-add
        or redeploy, so the built stack and bring-back always survive."""

        qb = self.qb_of(roster)
        if qb is None:
            return set()
        opp = self.opponent(qb)
        return {
            i for i in roster
            if i in self.sal and (i == qb or self.T(i) in (self.T(qb), opp))
        }


def fits(board, assignments, entry_id, roster, *, max_exposure, max_overlap):
    """Uniqueness (R29), the overlap cap, and the exposure cap, against every
    OTHER entry's current roster."""

    others = [r for eid, r in assignments.items() if eid != entry_id]
    if frozenset(roster) in {frozenset(r) for r in others}:
        return False
    if any(len(set(roster) & set(other)) > max_overlap for other in others):
        return False
    exposure = collections.Counter()
    for other in others:
        exposure.update(other)
    exposure.update(roster)
    return all(exposure[i] <= max_exposure for i in roster)


def resolve_caps(a, construction):
    cap = a.cap if a.cap is not None else int(construction.get("cap", 50000))
    floor = a.min_salary if a.min_salary is not None else int(construction.get("min_salary", 0))
    max_exposure = (
        a.max_exposure if a.max_exposure is not None
        else construction.get("max_exposure_landed", construction.get("max_exposure"))
    )
    max_overlap = (
        a.max_overlap if a.max_overlap is not None
        else construction.get("max_overlap_landed", construction.get("max_overlap"))
    )
    if max_exposure is None or max_overlap is None:
        raise Refused(
            "CAPS_UNKNOWN",
            "pass --max-exposure and --max-overlap; the portfolio's own construction "
            "block does not carry them",
        )
    return cap, floor, int(max_exposure), int(max_overlap)


# --------------------------------------------------------------------------- #
# Mode: inactive (and late-swap, which is the same search under a lock filter)
# --------------------------------------------------------------------------- #


def newly_out_ids(board, previous_sal):
    return {
        dk_id for dk_id, row in board.sal.items()
        if row["Status"].upper() in UNAVAILABLE_STATUSES
        and dk_id in previous_sal
        and previous_sal[dk_id]["Status"].upper() not in UNAVAILABLE_STATUSES
    }


def swap_inactive(board, scores, assignments, out_ids, *, max_exposure, max_overlap, lock_floor=None):
    """Single-swap first, then a two-player fallback. Returns (log, changed,
    unresolved): `changed` is every entry id whose roster this touched."""

    pool = [i for i in scores if i in board.sal and scores[i] > 0 and i not in out_ids]
    if lock_floor is not None:
        pool = [i for i in pool if (board.lock(i) or lock_floor) > lock_floor]
    log, changed, unresolved = [], set(), []

    def locked(entry_roster, dk_id):
        if lock_floor is None:
            return False
        row_lock = board.lock(dk_id)
        return row_lock is not None and row_lock <= lock_floor

    for entry_id, roster in list(assignments.items()):
        gone_here = [i for i in roster if i in out_ids]
        for gone in gone_here:
            if locked(roster, gone):
                unresolved.append((entry_id, gone, "LOCKED_CELL"))
                continue
            same_group = FLEX_POSITIONS if board.P(gone) in FLEX_POSITIONS else (board.P(gone),)
            candidates = sorted(
                (i for i in pool if board.P(i) in same_group and i not in roster
                 and not locked(roster, i)),
                key=lambda i: -scores[i],
            )
            best = None
            for candidate in candidates:
                trial = [candidate if i == gone else i for i in roster]
                if board.is_legal(trial) and board.preserves_shape(roster, trial) and fits(
                    board, assignments, entry_id, trial,
                    max_exposure=max_exposure, max_overlap=max_overlap,
                ):
                    best = candidate
                    break
            if best is not None:
                assignments[entry_id] = [best if i == gone else i for i in roster]
                changed.add(entry_id)
                log.append(
                    f"SWAP {entry_id}: {board.NM(gone)} ({board.T(gone)} {board.P(gone)}) -> "
                    f"{board.NM(best)} ({board.T(best)} {board.P(best)} ${board.S(best)})"
                )
                roster = assignments[entry_id]
                continue

            pair = _two_player_fallback(
                board, scores, pool, assignments, entry_id, roster, gone, locked,
                max_exposure=max_exposure, max_overlap=max_overlap,
            )
            if pair is None:
                unresolved.append((entry_id, gone, "NO_LEGAL_SWAP"))
                continue
            replacement, dropped, added = pair
            assignments[entry_id] = [
                replacement if i == gone else (added if i == dropped else i) for i in roster
            ]
            changed.add(entry_id)
            log.append(
                f"SWAP2 {entry_id}: {board.NM(gone)} -> {board.NM(replacement)}; "
                f"{board.NM(dropped)} -> {board.NM(added)}"
            )
            roster = assignments[entry_id]
    return log, changed, unresolved


def _two_player_fallback(
    board, scores, pool, assignments, entry_id, roster, gone, locked, *, max_exposure, max_overlap
):
    """No legal single swap exists (the position broke): trade the absent
    player plus one non-core flex-eligible teammate for a better-scoring
    pair. `pool` is already restricted to available, positive-scored,
    unlocked players."""

    core = board.core(roster)
    bench = [
        i for i in roster
        if i not in core and i != gone and board.P(i) in FLEX_POSITIONS and not locked(roster, i)
    ]
    top = sorted(
        (i for i in pool if board.P(i) in FLEX_POSITIONS and i not in roster),
        key=lambda i: -scores[i],
    )[:60]
    best = None
    for replacement in top:
        for dropped in bench:
            for added in top:
                if added in (replacement, dropped) or added in roster:
                    continue
                trial = [
                    replacement if i == gone else (added if i == dropped else i) for i in roster
                ]
                if not board.is_legal(trial) or not board.preserves_shape(roster, trial):
                    continue
                if not fits(board, assignments, entry_id, trial,
                            max_exposure=max_exposure, max_overlap=max_overlap):
                    continue
                gain = scores[replacement] + scores[added] - scores.get(dropped, 0.0)
                if best is None or gain > best[0]:
                    best = (gain, replacement, dropped, added)
    if best is None:
        return None
    _gain, replacement, dropped, added = best
    return replacement, dropped, added


# --------------------------------------------------------------------------- #
# Mode: value-add
# --------------------------------------------------------------------------- #


def value_add(board, scores, assignments, names, target_count, *, max_exposure, max_overlap):
    log = []
    by_name = {board.NM(i): i for i in board.sal}
    for name in names:
        dk_id = by_name.get(name)
        if dk_id is None or dk_id not in scores or scores[dk_id] <= 0:
            log.append(f"VALUE_ADD_SKIPPED {name}: not in the current scored pool")
            continue
        current_exposure = sum(1 for roster in assignments.values() if dk_id in roster)
        for entry_id, roster in sorted(assignments.items()):
            if current_exposure >= target_count:
                break
            if dk_id in roster:
                continue
            core = board.core(roster)
            candidates = sorted(
                (i for i in roster if i not in core and board.P(i) == board.P(dk_id)),
                key=lambda i: scores.get(i, 0.0),
            )
            for weakest in candidates:
                if scores[dk_id] <= scores.get(weakest, 0.0):
                    continue
                trial = [dk_id if i == weakest else i for i in roster]
                if board.is_legal(trial) and fits(
                    board, assignments, entry_id, trial,
                    max_exposure=max_exposure, max_overlap=max_overlap,
                ):
                    assignments[entry_id] = trial
                    current_exposure += 1
                    log.append(f"VALUE_ADD {entry_id}: {board.NM(weakest)} -> {name}")
                    break
    return log


# --------------------------------------------------------------------------- #
# Mode: redeploy (Session 62, R37): a swap happens only as a Pareto gain
# --------------------------------------------------------------------------- #
#
# The rule itself, its proxies and its report moved into `src/nfl_dfs/classic_redeploy.py` in Session 64, so that
# `run-slate`'s rung-4 thesis build runs the very same code; this script imports it back (see the imports) and keeps
# what is the operator layer's: reading a scores file, an official status file, a run's protected people, and writing
# the portfolio. `redeploy` below is the adapter.


def load_gated(path, sal) -> set:
    """DraftKings IDs the scores file itself says are not selectable (`excluded_dk_ids`, the run dump's own
    exclusion set, and every salary row whose exact name or ID is in `operator_construction_exclusions`, a
    list an operator-built dump may carry; nothing in `src/` writes it): a redeploy never re-admits one. A
    file with no `excluded_dk_ids` (an older raw dump, which `filter_pool_scores.py` refuses without its
    report) gates nobody, and says so on stderr."""

    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        ids = {str(i) for i in doc.get("excluded_dk_ids") or ()}
        named = {str(i) for i in doc.get("operator_construction_exclusions") or ()}
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise Refused("SCORES_UNREADABLE", f"{path}: {type(exc).__name__}: {exc}")
    if "excluded_dk_ids" not in doc:
        print(f"SCORES_FILE_HAS_NO_EXCLUDED_DK_IDS: {path} declares no excluded_dk_ids, so it keeps nobody out of a "
              "redeploy; run scripts/filter_pool_scores.py on a raw dump first", file=sys.stderr)
    return ids | {dk_id for dk_id, row in sal.items() if row["Name"] in named or dk_id in named}


def load_inactive_ids(path) -> set:
    """DraftKings IDs an official status file (`official_status.csv`: `PLAYER_OR_GSIS_ID`, `STATUS`) marks
    INACTIVE. QA fails any lineup that rosters one, so a redeploy never adds one even if a scores file still
    scores him. A header-only file (no official observation) names nobody."""

    rows = read_csv_rows(path, "STATUS")
    header = rows[0] if rows else []
    if "PLAYER_OR_GSIS_ID" not in header or "STATUS" not in header:
        raise Refused("STATUS_COLUMNS_MISSING", f"{path} lacks PLAYER_OR_GSIS_ID or STATUS")
    id_col, status_col = header.index("PLAYER_OR_GSIS_ID"), header.index("STATUS")
    return {
        row[id_col].strip() for row in rows[1:]
        if len(row) > max(id_col, status_col) and row[status_col].strip().upper() == "INACTIVE"
    }


def load_protected_from(path) -> list[str]:
    """The DraftKings IDs in a run's `judgment_pass.protected_people` (Session 61): the people a construction
    judgment placed. Reads a `run-slate` `cowork_run.json` or the Classic coverage artifact."""

    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused("PROTECT_FROM_UNREADABLE", f"{path}: {exc}")
    reports = doc.get("prior_review_reports") if isinstance(doc, dict) else None
    selection = reports.get("selection") if isinstance(reports, dict) else None
    block = selection.get("judgment_pass") if isinstance(selection, dict) else None
    if not isinstance(block, dict) and isinstance(doc, dict):
        block = doc.get("judgment_pass")
    people = block.get("protected_people") if isinstance(block, dict) else None
    if not isinstance(people, list):
        raise Refused(
            "PROTECT_FROM_HAS_NO_JUDGMENT_PASS",
            f"{path} has no judgment_pass.protected_people: it is not a Classic run from Session 61 on",
        )
    ids = []
    for row in people:
        dk_id = str(row.get("dk_id") or "").strip() if isinstance(row, dict) else ""
        if not dk_id:
            raise Refused("PROTECT_FROM_ROW_HAS_NO_DK_ID", f"{path}: {row!r}")
        ids.append(dk_id)
    return ids


def resolve_protect(sal, tokens, from_ids) -> dict:
    """`{dk_id: name}` for every person a redeploy must leave alone: `--protect` tokens (an exact DraftKings ID,
    else an exact name) and `--protect-from` IDs. A token that names nobody, or two people, is refused: a typo
    that quietly protected nobody is the failure this exists to prevent."""

    by_name: dict[str, list[str]] = {}
    for dk_id, row in sal.items():
        by_name.setdefault(row["Name"], []).append(dk_id)
    protected: dict[str, str] = {}
    for token in tokens:
        token = token.strip()
        matches = [token] if token in sal else by_name.get(token, [])
        if not matches:
            raise Refused("PROTECT_UNKNOWN", f"--protect {token!r} is neither a DraftKings ID nor a name in the salary file")
        if len(matches) > 1:
            raise Refused("PROTECT_AMBIGUOUS", f"--protect {token!r} names {len(matches)} people {sorted(matches)}; pass the ID")
        protected[matches[0]] = sal[matches[0]]["Name"]
    for dk_id in from_ids:
        if dk_id not in sal:
            raise Refused("PROTECT_ID_NOT_IN_SALARY_FILE", f"protected DraftKings ID {dk_id!r} is not in the salary file")
        protected[dk_id] = sal[dk_id]["Name"]
    return protected


def redeploy(board, scores, assignments, entry_ids, *, protect=frozenset(), gated=frozenset(),
             max_exposure, max_overlap, now=None):
    """Take salary-driven upgrades only as Pareto gains, to a fixed point. Mutates `assignments`. Returns `(log, report)`.

    The rule is `nfl_dfs.classic_redeploy.redeploy` (Session 64; this was its first home, Session 62): the row's prior
    rises, the row is a legal lineup by the engine's own `validate_lineup` (the board's rows are put in the engine's
    `SlateContract` by `slate_from_rows`), it keeps the stack or bring-back it had and stays distinct (R29) inside the
    portfolio's caps, the QB, the DST, his team and his opponent and every protected person are never outgoing, a
    protected person is never incoming, an incoming person has a blank DraftKings status and is not gated, and no
    washout proxy is worse on the whole portfolio. `now` is the lock clock: a cell whose game kicked off at or before
    it is never outgoing and never incoming. The script's rows are not in slot order, so a changed row keeps its
    cell order and the incoming person takes the outgoing person's cell; the whole report is stored."""

    slate = board.engine_slate()
    gated = set(gated)
    if now is not None:  # late-swap refuses an incoming person whose kickoff the file does not state; so does this
        gated |= {dk_id for dk_id, row in board.sal.items() if lock_at(row) is None}
    try:
        result = classic_redeploy.redeploy(
            slate, scores, assignments, row_ids=list(entry_ids), protect=protect, gated=gated,
            exposure_limit=max_exposure, overlap_cap=max_overlap, min_salary=board.floor,
            locked=classic_redeploy.locked_dk_ids(slate, now) if now is not None else (),
            slot_ordered=False, stored_limit=None, max_passes=PARETO_MAX_PASSES)
    except ValueError as exc:
        if str(exc).startswith("REDEPLOY_DK_ID_NOT_IN_POOL"):
            raise Refused("PORTFOLIO_PERSON_NOT_IN_SALARY_FILE", str(exc))
        raise
    for entry_id in result.changed:
        assignments[entry_id] = list(result.rosters[entry_id])
    return result.log, result.report


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def write_new(out: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if Path(tmp).read_bytes() != data:
            raise Refused("VERIFICATION_FAILED", "temporary file does not hold the portfolio bytes")
        if out.exists():
            raise Refused("OUTPUT_EXISTS", f"{out} appeared while writing")
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def run(a) -> dict:
    out = Path(a.out)
    if out.exists():
        raise Refused("OUTPUT_EXISTS", f"{a.out} already exists; an earlier portfolio is never overwritten")

    if a.mode != "redeploy" and (a.protect or a.protect_from or a.status):
        raise Refused(
            "REDEPLOY_ONLY_FLAG",
            f"--protect, --protect-from and --status belong to --mode redeploy; --mode {a.mode} would ignore them "
            "and move the people they name",
        )
    portfolio = load_portfolio(a.portfolio)
    scores = load_scores(a.scores)
    sal = load_salaries(a.salaries)
    construction = dict(portfolio.get("construction") or {})
    cap, floor, max_exposure, max_overlap = resolve_caps(a, construction)
    board = Board(sal, cap, floor)
    assignments = {eid: list(roster) for eid, roster in portfolio["assignments_by_entry_id"].items()}

    unresolved = []
    pareto_report = None
    if a.mode in ("inactive", "late-swap"):
        if a.previous_salaries and a.inactive_id:
            raise Refused("CONFLICTING_INACTIVE_SOURCE", "pass --previous-salaries or --inactive-id, not both")
        if a.previous_salaries:
            previous = load_salaries(a.previous_salaries)
            out_ids = newly_out_ids(board, previous)
        elif a.inactive_id:
            out_ids = set(a.inactive_id)
        else:
            raise Refused("NO_INACTIVE_SOURCE", "pass --previous-salaries or --inactive-id")
        lock_floor = None
        if a.mode == "late-swap":
            if a.now is None:
                raise Refused("NOW_REQUIRED", "--mode late-swap requires --now")
            lock_floor = a.now
        log, changed, unresolved = swap_inactive(
            board, scores, assignments, out_ids,
            max_exposure=max_exposure, max_overlap=max_overlap, lock_floor=lock_floor,
        )
    elif a.mode == "value-add":
        if not a.add:
            raise Refused("NO_NAMES", "--mode value-add requires at least one --add NAME")
        log = value_add(
            board, scores, assignments, a.add, a.target_count,
            max_exposure=max_exposure, max_overlap=max_overlap,
        )
        changed = {eid for eid, roster in assignments.items()
                   if roster != portfolio["assignments_by_entry_id"][eid]}
    elif a.mode == "redeploy":
        unknown = [eid for eid in a.changed_entry_id if eid not in assignments]
        if unknown:
            raise Refused("CHANGED_ENTRY_UNKNOWN", f"--changed-entry-id names rows the portfolio does not hold: {unknown}")
        protect = resolve_protect(sal, a.protect, load_protected_from(a.protect_from) if a.protect_from else [])
        # Unused salary is never a defect (R37): the portfolio's inherited floor does not bound a redeploy, only
        # a floor the operator passes now does.
        floor = a.min_salary if a.min_salary is not None else 0
        log, pareto_report = redeploy(
            Board(sal, cap, floor), scores, assignments, a.changed_entry_id or list(assignments),
            protect=protect,
            gated=load_gated(a.scores, sal) | (load_inactive_ids(a.status) if a.status else set()),
            max_exposure=max_exposure, max_overlap=max_overlap, now=a.now,
        )
        changed = {eid for eid, roster in assignments.items()
                   if roster != portfolio["assignments_by_entry_id"][eid]}
    else:
        raise Refused("MODE_UNKNOWN", a.mode)

    doc = dict(portfolio)
    doc["assignments_by_entry_id"] = assignments
    doc["lineups"] = [
        {
            "index": n + 1,
            "entry_id": eid,
            "roster": roster,
            "salary": sum(board.S(i) for i in roster),
            "prior_points": round(sum(scores.get(i, 0.0) for i in roster), 3),
            "bringback": board.has_bringback(roster),
        }
        for n, (eid, roster) in enumerate(assignments.items())
    ]
    doc["construction"] = {
        **construction,
        "mode": a.mode,
        "cap": cap,
        "min_salary": floor,
        "max_exposure": max_exposure,
        "max_overlap": max_overlap,
        "changed_entry_ids": sorted(changed),
        "swap_log": construction.get("swap_log", []) + log,
    }
    doc["construction"].pop("pareto_redeploy", None)  # an earlier run's report describes an earlier portfolio
    if pareto_report is not None:
        doc["construction"]["pareto_redeploy"] = pareto_report
    data = json.dumps(doc, indent=1).encode("utf-8")
    write_new(out, data)
    return {
        "log": log,
        "changed": sorted(changed),
        "unresolved": unresolved,
        "pareto_report": pareto_report,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--portfolio", required=True, help="portfolio json to edit")
    ap.add_argument("--scores", required=True, help="current gated pool scores json, read as ['by_dk_id']")
    ap.add_argument("--salaries", required=True, help="current DKSalaries.csv")
    ap.add_argument("--out", required=True, help="portfolio json to write; a new path, never an input")
    ap.add_argument("--mode", required=True, choices=("inactive", "value-add", "redeploy", "late-swap"))
    ap.add_argument("--cap", type=int, default=None)
    ap.add_argument("--min-salary", type=int, default=None)
    ap.add_argument("--max-exposure", type=int, default=None)
    ap.add_argument("--max-overlap", type=int, default=None)
    ap.add_argument("--previous-salaries", help="mode inactive/late-swap: the salary file this portfolio was built from")
    ap.add_argument("--inactive-id", action="append", default=[], help="mode inactive/late-swap: an explicit dk_id")
    ap.add_argument("--add", action="append", default=[], help="mode value-add: a Name from --salaries")
    ap.add_argument("--target-count", type=int, default=3, help="mode value-add: lineups to work each --add into")
    ap.add_argument("--changed-entry-id", action="append", default=[],
                    help="mode redeploy: restrict the pass to this entry id (default: every row)")
    ap.add_argument("--protect", action="append", default=[],
                    help="mode redeploy: a DraftKings ID or exact name a redeploy never moves (repeatable)")
    ap.add_argument("--protect-from",
                    help="mode redeploy: a run-slate cowork_run.json or Classic coverage JSON; every "
                         "judgment_pass.protected_people dk_id is protected")
    ap.add_argument("--status",
                    help="mode redeploy: an official_status.csv; a person it marks INACTIVE is never added")
    ap.add_argument(
        "--now", type=lambda s: datetime.fromisoformat(s).astimezone(timezone.utc) if s else None,
        default=None, help="ISO 8601 with an offset. Mode late-swap (required): a cell whose game locked at or before this "
                           "is never touched. Mode redeploy (optional, Session 64): a person whose game locked at or "
                           "before this is never outgoing and never incoming; omitted, no lock filter",
    )
    a = ap.parse_args(argv)
    try:
        result = run(a)
    except Refused as exc:
        print(f"REFUSED {exc.code}: {exc.detail}", file=sys.stderr)
        print("nothing was written", file=sys.stderr)
        return EXIT_REFUSED

    print("\n".join(result["log"]) or "no rostered player changed")
    if result["pareto_report"] is not None:
        print("\n".join(render_pareto_report(result["pareto_report"])))
    print(f"changed entries: {result['changed']}")
    print(f"sha256: {result['sha256']}")
    print(f"wrote: {a.out}")
    if result["unresolved"]:
        for entry_id, dk_id, reason in result["unresolved"]:
            print(f"UNRESOLVED {entry_id}: {dk_id} ({reason})", file=sys.stderr)
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
