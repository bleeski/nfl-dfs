"""Session 23 acceptance: the P2 structural hygiene bounds and `max_person_share`.

The card's acceptance names the DAL@NYG and DEN@KC fixtures; their bytes are
not in the repo, only their hashes (`docs/RUN_RECORD_20260914_DEN_KC.md`), so
this proves the mechanism on the two Showdown fixtures the repo actually has:
NE@SEA (`tests/fixtures/supplied/`) and DET@BUF
(`data/inbox/slates/det-buf-2026-09-17/`), both immutable, read here through
the parser only. This is a mechanism check, not a pre-lock claim (the card's
own words): `make_showdown_policy.py`'s v2 defaults generate a real bounded
bank and a real joint solve over each fixture's actual salary bytes.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from nfl_dfs.concentration import load_concentration_defaults
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.entry_groups import plan_entries
from nfl_dfs.portfolio_enforcement import build_policy_candidate_bank, solve_policy_portfolio
from nfl_dfs.portfolio_policy import (
    POLICY_SCHEMA_VERSION_V2,
    portfolio_policy_template,
    structural_bound_violations,
    validate_portfolio_policy_bytes,
)

from .test_participation import _slate as _synthetic_slate

REPO_ROOT = Path(__file__).resolve().parents[1]
SUPPLIED = REPO_ROOT / "tests" / "fixtures" / "supplied"
DET_BUF = REPO_ROOT / "data" / "inbox" / "slates" / "det-buf-2026-09-17"
GENERATOR = REPO_ROOT / "scripts" / "make_showdown_policy.py"

NE_SEA = (SUPPLIED / "DKSalaries Salary CSV Showdown.csv", SUPPLIED / "DKEntries CSV 20 entries.csv")
DET_BUF_FILES = (DET_BUF / "7c85ca11-DKSalaries_97.csv", DET_BUF / "53fe7f5a-DKEntries_74.csv")
# Session 56: the generator's defaults are the registered concentration defaults (0.60 a person, 0.20 a Captain; they were 0.80
# and 0.4). Eight rows under them need a deeper bank than the scaled 32: measured on these two fixtures, NE@SEA solves from 48
# candidates and DET@BUF from 120 (32, 48 and 64 all end `CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`). `run-slate`'s ladder deepens a
# bank once and then gives the caps way by name; this test proves the defaults are satisfiable, so it gives the bank what it needs.
CANDIDATE_LIMIT = 120


def _generator():
    spec = importlib.util.spec_from_file_location("make_showdown_policy_acceptance", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("salaries", "entries", "entry_count"), [(*NE_SEA, 8), (*DET_BUF_FILES, 8)])
def test_generator_defaults_pass_100_percent_hygiene_and_cap_max_person_share(
    tmp_path, salaries: Path, entries: Path, entry_count: int
) -> None:
    module = _generator()
    slate = parse_salaries(salaries)
    fillable = list(plan_entries(parse_entries(entries), slate).fillable)
    bound = fillable[: min(entry_count, len(fillable))]
    out = tmp_path / "policy.json"
    args = ["--salaries", str(salaries), "--entries", str(entries), "--out", str(out)]
    for entry_id in bound:
        args += ["--entry-id", entry_id]
    assert module.main(args) == 0

    validation = validate_portfolio_policy_bytes(out.read_bytes(), slate=slate, entry_ids=bound)
    assert validation.valid, validation.blockers()
    policy = validation.policy

    # Kickers and DSTs stay in the combined pool: the generator's defaults
    # never exclude them, only zero their Captain fraction.
    assert policy.excluded_people == ()
    kicker_dst = {p.underlying_id for p in policy.people if p.underlying_id.split("|")[1] in ("K", "DST")}
    assert kicker_dst, "the fixture has no kicker or DST to prove this on"

    objective = {row.dk_id: 1.0 for row in slate.players}
    bank = build_policy_candidate_bank(
        slate, objective, policy=policy, candidate_limit=CANDIDATE_LIMIT,
        total_time_limit_seconds=30, per_solve_time_limit_seconds=3,
    )
    assert bank.candidates, "the generator's own defaults built no candidates"
    by_id = {row.dk_id: row for row in slate.players}
    assert any(
        any(by_id[dk_id].position in ("K", "DST") for dk_id in candidate.roster)
        for candidate in bank.candidates
    ), "kickers and DSTs never reach a candidate lineup"

    selection = solve_policy_portfolio(policy, bank, time_limit_seconds=15)
    assert selection.passed, selection.status
    selected = [bank.candidates[index] for index in selection.selected_candidate_indexes]
    assert len(selected) == len(bound)

    # 100% hygiene pass at rung 0: every delivered roster satisfies every
    # structural bound, independently recomputed from the roster IDs here
    # (the same function the SD4 audit uses), never trusted from the solve.
    for candidate in selected:
        assert structural_bound_violations(slate, candidate.roster, policy.structural_bounds) == ()

    # More than one captain.
    assert len({candidate.captain_person for candidate in selected}) > 1

    # max_person_share and the Captain share stay within the generator's own default caps: the registered 0.60 and 0.20 (it was
    # 0.80 and no Captain assertion before Session 56).
    defaults = load_concentration_defaults()
    combined: Counter[str] = Counter()
    for candidate in selected:
        combined.update(candidate.people)
    max_share = max(combined.values()) / len(selected)
    assert max_share <= float(defaults.person_fraction)
    captains = Counter(candidate.captain_person for candidate in selected)
    assert max(captains.values()) / len(selected) <= float(defaults.captain_fraction)


def test_an_infeasible_structural_bound_fails_closed(tmp_path) -> None:
    """A band no legal roster can satisfy blocks rather than silently delivering one.

    Proven on the small synthetic pool (`tests/test_participation.py`, exactly
    one QB per team, two total): requiring three rostered QBs is never
    satisfiable there, whatever a real slate's roster of backups allows.
    """

    slate = _synthetic_slate(tmp_path)
    entry_ids = ("1", "2", "3")
    document = portfolio_policy_template(
        slate, entry_ids,
        controls={"structural_bounds": {"qb_count": {"minimum": 3, "maximum": 3}}},
        schema_version=POLICY_SCHEMA_VERSION_V2,
    )
    validation = validate_portfolio_policy_bytes(
        json.dumps(document).encode(), slate=slate, entry_ids=entry_ids
    )
    assert validation.valid, validation.blockers()
    policy = validation.policy

    objective = {row.dk_id: 1.0 for row in slate.players}
    bank = build_policy_candidate_bank(
        slate, objective, policy=policy, candidate_limit=32,
        total_time_limit_seconds=10, per_solve_time_limit_seconds=2,
    )
    assert not bank.candidates
    selection = solve_policy_portfolio(policy, bank, time_limit_seconds=5)
    assert not selection.passed
    assert selection.status != "OPTIMAL"
