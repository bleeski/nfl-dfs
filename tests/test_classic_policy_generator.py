"""The generated C2 policy must validate, and its rungs must actually relax.

`scripts/make_classic_policy.py` exists because the registered template's
defaults are the worst configuration the engine supports: every stack rule ships
`ADVISORY` with `minimum_entries: 0`, which the solver does not enforce, and the
candidate bank defaults to `max(32, entries + 24)` out of a several-hundred-person
pool. These tests pin the two things that would silently undo that: a policy the
validator rejects, and a ladder whose rungs do not monotonically loosen.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

from nfl_dfs.classic_portfolio_policy import (
    classic_portfolio_policy_template,
    validate_classic_portfolio_policy_bytes,
)
from nfl_dfs.dk import parse_entries, parse_salaries

import json


def _generator():
    path = Path(__file__).resolve().parents[1] / "scripts" / "make_classic_policy.py"
    spec = importlib.util.spec_from_file_location("make_classic_policy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "supplied"
SALARY = FIXTURES / "DKSalaries Salary CSV Classic.csv"
ENTRIES = FIXTURES / "DKEntries CSV.csv"


def _document(module, rung: int, entry_ids, slate, entry_sha256: str):
    count = len(entry_ids)
    controls: dict[str, object] = {
        "stack_rules": module._stack_rules(count, rung),
        "max_pairwise_person_overlap": min(module._overlap(rung), 8),
        "require_unique_lineups": True,
    }
    fraction = module._exposure_fraction(rung)
    if fraction is not None and count > 2:
        cap = max(1, math.ceil(fraction * count))
        controls["player_exposure_bounds"] = [
            {
                "underlying_id": row.underlying_id,
                "dk_id": row.dk_id,
                "minimum_entries": 0,
                "maximum_entries": cap,
                "hard": True,
            }
            for row in sorted(
                {row.underlying_id: row for row in slate.players}.values(),
                key=lambda row: row.underlying_id,
            )
        ]
    limits = module._limits(count, len(slate.players), rung, minutes=1.0)
    return classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=entry_sha256, controls=controls, limits=limits
    )


@pytest.mark.parametrize("rung", (0, 1, 2, 3))
def test_every_rung_produces_a_policy_the_validator_accepts(rung: int) -> None:
    module = _generator()
    slate = parse_salaries(SALARY)
    entries = parse_entries(ENTRIES)
    entry_ids = tuple(item.entry_id for item in entries.authorizations)
    document = _document(module, rung, entry_ids, slate, entries.raw_hash)
    raw = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    validation = validate_classic_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=entry_ids, entry_sha256=entries.raw_hash
    )
    assert validation.valid and validation.policy is not None, validation.blockers()


def test_player_exposure_bounds_use_the_schema_key() -> None:
    """`person` reads naturally and the validator rejects it; `underlying_id` is the key."""

    module = _generator()
    slate = parse_salaries(SALARY)
    entries = parse_entries(ENTRIES)
    entry_ids = tuple(item.entry_id for item in entries.authorizations) * 8
    document = _document(module, 0, entry_ids, slate, entries.raw_hash)
    bounds = document["controls"].get("player_exposure_bounds")
    assert bounds, "a portfolio with more than two entries must cap player exposure"
    assert set(bounds[0]) == {
        "underlying_id",
        "dk_id",
        "minimum_entries",
        "maximum_entries",
        "hard",
    }


def test_the_ladder_only_ever_loosens() -> None:
    module = _generator()
    count = 20
    previous_overlap = 0
    previous_pass_catcher = count + 1
    for rung in (0, 1, 2, 3):
        rules = {rule["rule_id"]: rule for rule in module._stack_rules(count, rung)}
        overlap = module._overlap(rung)
        assert overlap >= previous_overlap, f"rung {rung} tightened overlap"
        pass_catcher = rules["qb-pass-catcher"]["minimum_entries"]
        assert pass_catcher <= previous_pass_catcher, f"rung {rung} tightened the stack"
        previous_overlap, previous_pass_catcher = overlap, pass_catcher
    # Rung 0 is the only rung that demands a bring-back on most entries.
    by_id = lambda rung: {rule["rule_id"]: rule for rule in module._stack_rules(count, rung)}
    assert by_id(0)["qb-bringback"]["minimum_entries"] == math.ceil(0.70 * count)
    assert by_id(0)["qb-bringback"]["strength"] == "HARD"
    assert by_id(2)["qb-bringback"]["strength"] == "ADVISORY"


def test_rung_zero_enforces_a_stack_on_every_entry() -> None:
    module = _generator()
    rules = {rule["rule_id"]: rule for rule in module._stack_rules(20, 0)}
    assert rules["qb-pass-catcher"]["strength"] == "HARD"
    assert rules["qb-pass-catcher"]["minimum_entries"] == 20
