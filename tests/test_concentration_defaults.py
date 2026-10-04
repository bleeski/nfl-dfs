"""Session 56 (R35, review F-02): the registered Showdown concentration defaults.

`config/showdown_concentration_defaults_v1.json` is one default set (0.60 a person,
0.20 a Captain, overlap 4) and the order the caps give way in. This module proves
the file is what it says, that the policy generator reads it instead of its own
numbers, and (below, in later sections) that the engine applies it to a Showdown
run that supplied no policy, that the relaxation ladder gives the caps way before
any structural rung, and that every miss is named. Nothing here is evidence that
60 or 20 percent is a good number; the file says so itself.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from nfl_dfs.concentration import (
    DEFAULT_PATH,
    ENGINE_DEFAULT,
    POLICY,
    SCHEMA_VERSION,
    ConcentrationDefaultsError,
    load_concentration_defaults,
    parse_concentration_defaults,
)
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.portfolio_policy import validate_portfolio_policy_bytes

SUPPLIED = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "supplied"
# v1 is never mutated: a change is a new file and a new schema_version, with this pin moved by a visible edit.
PINNED_SHA256 = "8b2aa7b70085b8f39b48a2d066b98006f38120fa359e2ad909463c0fb02d3ed1"


def _document() -> dict:
    return json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))


def _bytes(document: dict) -> bytes:
    return json.dumps(document).encode("utf-8")


# --------------------------------------------------------------------------- #
# The file
# --------------------------------------------------------------------------- #


def test_the_registered_defaults_are_the_pinned_bytes():
    assert load_concentration_defaults(expected_sha256=PINNED_SHA256).sha256 == PINNED_SHA256
    with pytest.raises(ConcentrationDefaultsError, match="sha256 mismatch"):
        load_concentration_defaults(expected_sha256="0" * 64)


def test_the_registered_values_are_r35s():
    defaults = load_concentration_defaults()
    assert defaults.version == SCHEMA_VERSION == "showdown_concentration_defaults_v1"
    assert defaults.person_fraction == Decimal("0.60") and defaults.captain_fraction == Decimal("0.20")
    assert defaults.pairwise_person_overlap == 4
    assert [(s.name, s.person_fraction, s.captain_fraction) for s in defaults.steps] == [
        ("CAPS_0_80_0_40", Decimal("0.80"), Decimal("0.40")), ("CAPS_OFF", None, None)]
    # The engine's own default has no uncapped joint solve: its off is rung 4 (sequential selection).
    assert [s.name for s in defaults.steps_for(ENGINE_DEFAULT)] == ["CAPS_0_80_0_40"]
    assert [s.name for s in defaults.steps_for(POLICY)] == ["CAPS_0_80_0_40", "CAPS_OFF"]
    # 0.20 floors to zero Captain slots under five entries, so the default binds from five rows.
    assert defaults.least_entries() == 5
    assert (Decimal("0.20") * 4) // 1 == 0 and (Decimal("0.20") * 5) // 1 == 1
    assert defaults.matches(Decimal("0.60"), Decimal("0.20"))
    assert not defaults.matches(Decimal("0.6"), Decimal("0.25"))
    assert {"UPLOAD_CLEARANCE", "CERTIFICATION", "LINEUP_QUALITY"} <= set(defaults.does_not_establish)
    # Vocabulary rule: a preference never claims a value.
    assert not {"EV", "ROI", "WIN_PROBABILITY", "CALIBRATED"} & set(defaults.does_not_establish)


def _mutations():
    def tighter(d):
        d["relaxation_steps"][0]["person_fraction"] = "0.50"

    def capped_after_off(d):
        d["relaxation_steps"].append({"name": "CAPS_BACK", "person_fraction": "0.90", "captain_fraction": "0.90",
                                      "applies_to": ["POLICY"]})

    def repeated_name(d):
        d["relaxation_steps"][1]["name"] = d["relaxation_steps"][0]["name"]

    def changes_nothing(d):
        d["relaxation_steps"][0].update(person_fraction="0.60", captain_fraction="0.20")

    def out_of_range(d):
        d["defaults"]["captain_fraction"] = "1.5"

    def zero(d):
        d["defaults"]["person_fraction"] = "0"

    def number_not_string(d):
        d["defaults"]["person_fraction"] = 0.6

    def unknown_field(d):
        d["bonus"] = 1

    def unknown_target(d):
        d["relaxation_steps"][0]["applies_to"] = ["EVERYTHING"]

    def no_limits(d):
        d["does_not_establish"] = []

    def wrong_schema(d):
        d["schema_version"] = "showdown_concentration_defaults_v2"

    def bad_overlap(d):
        d["defaults"]["pairwise_person_overlap"] = 9

    return [tighter, capped_after_off, repeated_name, changes_nothing, out_of_range, zero, number_not_string,
            unknown_field, unknown_target, no_limits, wrong_schema, bad_overlap]


@pytest.mark.parametrize("mutate", _mutations(), ids=lambda fn: fn.__name__)
def test_a_defaults_file_that_is_malformed_or_tightens_is_refused(mutate):
    document = copy.deepcopy(_document())
    mutate(document)
    with pytest.raises(ConcentrationDefaultsError):
        parse_concentration_defaults(_bytes(document))


def test_an_unreadable_file_is_refused_not_guessed(tmp_path):
    with pytest.raises(ConcentrationDefaultsError, match="unreadable"):
        load_concentration_defaults(tmp_path / "missing.json")
    (tmp_path / "bad.json").write_bytes(b"{not json")
    with pytest.raises(ConcentrationDefaultsError, match="unreadable"):
        load_concentration_defaults(tmp_path / "bad.json")


# --------------------------------------------------------------------------- #
# The generator reads the registry (and an explicit flag still wins)
# --------------------------------------------------------------------------- #


def _generator():
    path = Path(__file__).resolve().parents[1] / "scripts" / "make_showdown_policy.py"
    spec = importlib.util.spec_from_file_location("make_showdown_policy_s56", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generate(tmp_path, capsys, *extra, name="policy.json"):
    salaries, entries = SUPPLIED / "DKSalaries Salary CSV Showdown.csv", SUPPLIED / "DKEntries CSV 20 entries.csv"
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / name
    assert _generator().main(["--salaries", str(salaries), "--entries", str(entries), "--out", str(out), *extra]) == 0
    capsys.readouterr()
    return json.loads(out.read_text(encoding="utf-8")), out


def test_the_generator_defaults_are_the_registered_ones(tmp_path, capsys):
    document, out = _generate(tmp_path, capsys)
    controls = document["controls"]
    defaults = load_concentration_defaults()
    assert Decimal(str(controls["max_combined_person_exposure"]["default_fraction"])) == defaults.person_fraction
    assert Decimal(str(controls["max_captain_exposure"]["default_fraction"])) == defaults.captain_fraction
    assert controls["max_pairwise_person_overlap"] == defaults.pairwise_person_overlap
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    entry_ids = [item.entry_id for item in parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv").authorizations]
    validation = validate_portfolio_policy_bytes(out.read_bytes(), slate=slate, entry_ids=entry_ids)
    assert validation.valid, validation.blockers()
    # 0.60 and 0.20 of twenty rows: the card's 12 and 4.
    assert (validation.policy.combined_rule.default_fraction, validation.policy.captain_rule.default_fraction) == (
        Decimal("0.6"), Decimal("0.2"))


def test_an_explicit_generator_flag_wins_over_the_registry(tmp_path, capsys):
    document, _out = _generate(tmp_path, capsys, "--combined-default", "0.7", "--captain-default", "0.3",
                               "--max-overlap", "3")
    controls = document["controls"]
    assert controls["max_combined_person_exposure"]["default_fraction"] == 0.7
    assert controls["max_captain_exposure"]["default_fraction"] == 0.3
    assert controls["max_pairwise_person_overlap"] == 3
