"""Session 57 (2026-10-02 review F-06 and F-07): the default structural bounds, re-cut from the field.

Two Session 23 defaults were universal exclusions the graded fields contradict: `offense_against_own_dst`
(no non-DST person on a rostered DST's team) and `--qb-count-max=1`. New default policies in both modes now
leave the first open and the Showdown generator admits two quarterbacks (minimum one). This is a construction
preference (class S): nothing forces two quarterbacks or adds a bonus, and the scorer compares the larger bank.

What must NOT move is what these tests pin as hard as the new defaults: an explicit true policy still forbids,
a false one permits, the auditors, the MILP rows and the relaxation tables keep their meaning for an explicit or a
frozen policy (the Boolean is never inverted to mean opposing offense), and the frozen policies already on disk
normalize to the same bytes. Rosters here are fixed and legal; nothing asserts a historical winner would be
selected by pre-lock projections.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from nfl_dfs.classic_portfolio import _Enumerator
from nfl_dfs.classic_portfolio_policy import (
    ClassicStructuralBounds,
    classic_portfolio_policy_template,
    validate_classic_portfolio_policy_bytes,
)
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.hashing import sha256_bytes
from nfl_dfs.lineups import validate_lineup
from nfl_dfs.optimizer import LineupOptimizer
from nfl_dfs.portfolio_enforcement import _apply_structural_bounds, build_policy_candidate_bank
from nfl_dfs.portfolio_policy import (
    OPEN_RANGE,
    POLICY_SCHEMA_VERSION_V2,
    StructuralBounds,
    portfolio_policy_template,
    structural_bound_violations,
    validate_portfolio_policy_bytes,
)
from nfl_dfs.relaxation import (
    SHOWDOWN_RUNGS,
    classic_relaxed_controls,
    classic_rung_controls,
    classic_structural_bounds,
    showdown_relaxed_controls,
)

from .test_classic_policy_generator import SALARY as CLASSIC_SALARY
from .test_classic_policy_generator import _generator as _classic_generator
from .test_classic_portfolio_c2 import _slate as _classic_slate
from .test_concentration_defaults import SUPPLIED, _generate
from .test_participation import _salary_bytes

REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN = REPO_ROOT / "data" / "inbox" / "slates" / "phi-chi-sd-2026-09-28"
CLASSIC_TWENTY = Path(CLASSIC_SALARY).parent / "DKEntries CSV 20 entries.csv"

# The frozen policies' bytes and the normalized form the validator derives from them, captured from the code as it
# stood before this session (`main` @ 9204cc5). The validator, the normalizer and the auditors are not touched by
# Session 57, so these must hold; a mismatch means the change leaked into how an explicit policy is read.
FROZEN_ANCHORS = {
    "policy_K1b": ("bd808acffb04a8b1a14de450e7db0e34e1fbb228b84f34e928b5568adf60dcb2",
                   "03df43de9e2a74dcfbb71e721b99a2e57a4e505b7f1c516018f051f8a5ad4775"),
    "policy_S3": ("c7928e548860ac5f44efa86b7406056b88ed9ee76de5e769b53a67b68f987d51",
                  "73d39ea00f8cff86901d8a7cd0ec390a2be0eaa4b2944f6d94c9b8ec0a955d40"),
    "policy_S1": ("9654b85b423e3d37a7d7618bdec02e8572d3480244dade97fdd8a77674dd2b2c",
                  "b5e379177e361ff9e13b9a307742f82440eab68bed3c005642db96e071f42649"),
}


def _showdown_policy(tmp_path, capsys, *extra, name="policy.json"):
    """The Showdown generator's policy on the supplied NE@SEA fixture, validated: (document, policy)."""

    document, out = _generate(tmp_path, capsys, *extra, name=name)
    slate = parse_salaries(SUPPLIED / "DKSalaries Salary CSV Showdown.csv")
    entry_ids = [item.entry_id for item in parse_entries(SUPPLIED / "DKEntries CSV 20 entries.csv").authorizations]
    validation = validate_portfolio_policy_bytes(out.read_bytes(), slate=slate, entry_ids=entry_ids)
    assert validation.valid, validation.blockers()
    return document, validation.policy


# --------------------------------------------------------------------------- #
# Acceptance 1 and 3, Showdown: what the generator writes, and what a flag still asks for
# --------------------------------------------------------------------------- #


def test_the_showdown_generator_leaves_the_own_dst_bound_open_and_admits_two_quarterbacks(tmp_path, capsys):
    document, policy = _showdown_policy(tmp_path, capsys)
    bounds = document["controls"]["structural_bounds"]
    assert bounds["offense_against_own_dst"] is False
    assert bounds["qb_count"] == {"minimum": 1, "maximum": 2}
    # The rest of Session 23's hygiene is as it was: depth exclusions and per-QB pass-catcher bounds untouched.
    assert bounds["pass_catchers_with_rostered_qb"] == {"minimum": 1, "maximum": 2}
    assert bounds["salary_left"] == {"minimum": 1, "maximum": 500}
    assert (bounds["kicker_count"], bounds["dst_count"]) == (1, 1)
    assert policy.structural_bounds.offense_against_own_dst is False
    assert (policy.structural_bounds.qb_count.minimum, policy.structural_bounds.qb_count.maximum) == (1, 2)


@pytest.mark.parametrize(("flags", "offense", "qb_count"), [
    (("--offense-against-own-dst",), True, (1, 2)),
    (("--no-offense-against-own-dst",), False, (1, 2)),
    (("--qb-count-max", "1"), False, (1, 1)),
    (("--qb-count-min", "1", "--qb-count-max", "2"), False, (1, 2)),
    (("--offense-against-own-dst", "--qb-count-max", "1"), True, (1, 1)),
])
def test_an_explicit_flag_still_gets_exactly_what_it_asks_for(tmp_path, capsys, flags, offense, qb_count):
    document, policy = _showdown_policy(tmp_path, capsys, *flags)
    bounds = document["controls"]["structural_bounds"]
    assert bounds["offense_against_own_dst"] is offense
    assert (bounds["qb_count"]["minimum"], bounds["qb_count"]["maximum"]) == qb_count
    assert policy.structural_bounds.offense_against_own_dst is offense


# --------------------------------------------------------------------------- #
# Acceptance 1, Classic: the emitted rung controls, and the table they relax by
# --------------------------------------------------------------------------- #


def test_the_classic_generator_emits_the_own_dst_bound_open_on_every_rung():
    slate = _classic_slate()
    for rung in range(4):
        structural = classic_rung_controls(slate, 5, rung)["structural_bounds"]
        assert structural["offense_against_own_dst"] is False
        # The salary band is not part of this ruling: $0 to $1,000 at rung 0, open from rung 1.
        assert structural["salary_left"] == ({"minimum": 0, "maximum": 1000} if rung == 0
                                             else {"minimum": None, "maximum": None})
    assert classic_rung_controls(slate, 5, 0)["max_person_share"] == 0.8


def test_an_explicit_true_classic_policy_still_forbids_and_relaxes_where_it_always_did():
    slate = _classic_slate()
    for rung, expected in zip(range(4), (True, True, False, False)):
        structural = classic_rung_controls(slate, 5, rung, offense_against_own_dst=True)["structural_bounds"]
        assert structural["offense_against_own_dst"] is expected, rung
    # The relaxation table itself is unchanged: rung 2 is where an explicit true policy loses it.
    assert [classic_structural_bounds(rung).offense_against_own_dst for rung in range(4)] == [True, True, False, False]
    legacy = _classic_policy(slate, True)
    assert [classic_relaxed_controls(legacy, rung)["structural_bounds"]["offense_against_own_dst"]
            for rung in range(4)] == [True, True, False, False]
    assert classic_relaxed_controls(legacy, None)["structural_bounds"]["offense_against_own_dst"] is True
    # A false policy stays permitted at every rung, and a relaxation never tightens it.
    default = _classic_policy(slate, False)
    assert [classic_relaxed_controls(default, rung)["structural_bounds"]["offense_against_own_dst"]
            for rung in range(4)] == [False] * 4


def _classic_policy(slate, offense: bool, count: int = 5):
    entry_ids = tuple(f"E{index:03d}" for index in range(1, count + 1))
    controls = classic_rung_controls(slate, count, 0, offense_against_own_dst=offense)
    document = classic_portfolio_policy_template(
        slate, entry_ids, entry_sha256=sha256_bytes(b"entry"), controls=controls)
    validation = validate_classic_portfolio_policy_bytes(
        json.dumps(document).encode("utf-8"), slate=slate, entry_ids=entry_ids, entry_sha256=sha256_bytes(b"entry"))
    assert validation.valid, validation.blockers()
    return validation.policy


def _classic_cli(tmp_path, capsys, *extra, rung="0"):
    from .test_classic_policy_generator import IMPROVEMENT_STOP

    out = tmp_path / f"policy_{rung}_{len(extra)}.json"
    code = _classic_generator().main(
        ["--salaries", str(CLASSIC_SALARY), "--entries", str(CLASSIC_TWENTY), "--out", str(out), "--rung", rung,
         "--host-rates", str(tmp_path / "absent.json"), *extra],
        wall=lambda: IMPROVEMENT_STOP - timedelta(seconds=86_400.0))
    assert code == 0
    return json.loads(out.read_text(encoding="utf-8")), capsys.readouterr().out.splitlines()


def test_the_classic_generator_writes_the_bound_open_says_so_and_a_flag_turns_it_on(tmp_path, capsys):
    document, printed = _classic_cli(tmp_path, capsys)
    assert document["controls"]["structural_bounds"] == {
        "salary_left": {"minimum": 0, "maximum": 1000}, "offense_against_own_dst": False}
    assert ("no offense with own DST: off (the default since Session 57; --offense-against-own-dst forbids it)"
            in printed)
    document, printed = _classic_cli(tmp_path, capsys, "--offense-against-own-dst")
    assert document["controls"]["structural_bounds"]["offense_against_own_dst"] is True
    assert "no offense with own DST: on" in printed
    # The explicit true policy keeps its old table: rung 2 drops it, and the printed line says the rung did.
    document, printed = _classic_cli(tmp_path, capsys, "--offense-against-own-dst", rung="2")
    assert document["controls"]["structural_bounds"]["offense_against_own_dst"] is False
    assert "no offense with own DST: off at this rung" in printed
    slate, entries = parse_salaries(CLASSIC_SALARY), parse_entries(CLASSIC_TWENTY)
    out = next(tmp_path.glob("policy_2_*.json"))
    validation = validate_classic_portfolio_policy_bytes(
        out.read_bytes(), slate=slate, entry_ids=tuple(item.entry_id for item in entries.authorizations),
        entry_sha256=entries.raw_hash)
    assert validation.valid, validation.blockers()


# --------------------------------------------------------------------------- #
# Acceptance 4: explicit and frozen policies keep their meaning
# --------------------------------------------------------------------------- #


def test_the_showdown_table_still_drops_an_explicit_true_policy_at_rung_two_and_its_one_qb_band_at_rung_three(
        tmp_path, capsys):
    _document, legacy = _showdown_policy(tmp_path, capsys, "--offense-against-own-dst", "--qb-count-max", "1")
    seen = {rung: showdown_relaxed_controls(legacy, rung)["structural_bounds"] for rung in (None, 1, 2, 3)}
    assert [seen[rung]["offense_against_own_dst"] for rung in (None, 1, 2, 3)] == [True, True, False, False]
    assert [(seen[rung]["qb_count"]["minimum"], seen[rung]["qb_count"]["maximum"]) for rung in (None, 1, 2, 3)] == [
        (1, 1), (1, 1), (1, 1), (None, None)]
    assert SHOWDOWN_RUNGS[2].drop_offense_against_own_dst and not SHOWDOWN_RUNGS[1].drop_offense_against_own_dst
    assert SHOWDOWN_RUNGS[3].drop_qb_count_band and not SHOWDOWN_RUNGS[2].drop_qb_count_band


def test_a_default_showdown_policy_is_never_tightened_by_a_rung(tmp_path, capsys):
    _document, policy = _showdown_policy(tmp_path, capsys)
    for rung in (1, 2, 3):
        bounds = showdown_relaxed_controls(policy, rung)["structural_bounds"]
        assert bounds["offense_against_own_dst"] is False
        qb = (bounds["qb_count"]["minimum"], bounds["qb_count"]["maximum"])
        assert qb == ((1, 2) if rung < 3 else (None, None))


@pytest.mark.parametrize("name", sorted(FROZEN_ANCHORS))
def test_the_frozen_policies_on_disk_still_normalize_to_the_bytes_they_always_did(name):
    slate = parse_salaries(FROZEN / "bdc34f2b-DKSalaries_119.csv")
    raw = (FROZEN / "policies" / f"{name}.json").read_bytes()
    source_sha256, normalized_sha256 = FROZEN_ANCHORS[name]
    assert sha256_bytes(raw) == source_sha256
    validation = validate_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=tuple(json.loads(raw)["bindings"]["entry_ids"]))
    assert validation.valid, validation.blockers()
    assert validation.policy.normalized_sha256 == normalized_sha256


def test_a_frozen_one_quarterback_policy_keeps_its_bounds_and_its_ladder():
    slate = parse_salaries(FROZEN / "bdc34f2b-DKSalaries_119.csv")
    raw = (FROZEN / "policies" / "policy_K1b.json").read_bytes()
    policy = validate_portfolio_policy_bytes(
        raw, slate=slate, entry_ids=tuple(json.loads(raw)["bindings"]["entry_ids"])).policy
    bounds = policy.structural_bounds
    assert bounds.offense_against_own_dst is True
    assert (bounds.qb_count.minimum, bounds.qb_count.maximum) == (1, 1)
    assert showdown_relaxed_controls(policy, 1)["structural_bounds"]["offense_against_own_dst"] is True
    assert showdown_relaxed_controls(policy, 2)["structural_bounds"]["offense_against_own_dst"] is False


# --------------------------------------------------------------------------- #
# Acceptance 2 and 3: fixed legal rosters, in the auditor and as MILP rows
# --------------------------------------------------------------------------- #

# (team, position, name, status, flex salary): synthetic, built so the three fixed rosters below are legal and
# leave $1 to $500 of the cap, the band the Showdown generator writes.
_POOL = (
    ("NE", "QB", "NE QB", "", 10000), ("NE", "WR", "NE WR1", "", 9500), ("NE", "WR", "NE WR2", "", 4500),
    ("NE", "TE", "NE TE", "", 3400), ("NE", "RB", "NE RB", "", 5500), ("NE", "K", "NE K", "", 3500),
    ("NE", "DST", "NE DST", "", 4200),
    ("SEA", "QB", "SEA QB", "", 6000), ("SEA", "WR", "SEA WR1", "", 9300), ("SEA", "WR", "SEA WR2", "", 4300),
    ("SEA", "TE", "SEA TE", "", 5300), ("SEA", "RB", "SEA RB", "", 6500), ("SEA", "K", "SEA K", "", 3300),
    ("SEA", "DST", "SEA DST", "", 2800),
)


def _showdown_world(tmp_path):
    path = tmp_path / "DKSalaries.csv"
    path.write_bytes(_salary_bytes(_POOL))
    slate = parse_salaries(path)
    by = {(player.name, player.role): player.dk_id for player in slate.players}

    def roster(captain, *flex):
        return (by[(captain, "CPT")],) + tuple(by[(name, "FLEX")] for name in flex)

    return slate, {
        # One QB (captain) with one pass catcher, and the DST of his own team beside his offense.
        "dst_and_teammates": roster("NE QB", "NE WR1", "NE DST", "SEA WR1", "SEA RB", "SEA TE"),
        # Both starting quarterbacks, each with his pass catchers, and no DST.
        "two_quarterbacks": roster("NE QB", "SEA QB", "NE WR1", "NE TE", "SEA WR1", "SEA RB"),
        # Two quarterbacks, one of them with no pass catcher at all.
        "second_quarterback_alone": roster("NE QB", "SEA QB", "NE WR1", "NE TE", "SEA RB", "SEA K"),
    }


def _solve_fixed(slate, roster, bounds):
    optimizer = LineupOptimizer(slate, time_limit_seconds=5.0)
    _apply_structural_bounds(optimizer, slate, bounds)
    for dk_id in roster:
        optimizer.add_required_row(dk_id)
    return optimizer.solve({row.dk_id: 1.0 for row in slate.players}).status


def test_a_legal_showdown_roster_with_a_dst_and_a_teammate_passes_the_new_defaults_and_fails_the_legacy_policy(
        tmp_path, capsys):
    slate, rosters = _showdown_world(tmp_path)
    roster = rosters["dst_and_teammates"]
    assert validate_lineup(slate, roster).valid
    _doc, new = _showdown_policy(tmp_path / "new", capsys)
    _doc, legacy = _showdown_policy(tmp_path / "old", capsys, "--offense-against-own-dst", "--qb-count-max", "1")
    assert structural_bound_violations(slate, roster, new.structural_bounds) == ()
    assert structural_bound_violations(slate, roster, legacy.structural_bounds) == ("offense_against_own_dst",)
    # The review's isolated reproduction: all six rows fixed, only the structural rows differ.
    assert _solve_fixed(slate, roster, new.structural_bounds) == "OPTIMAL"
    assert _solve_fixed(slate, roster, legacy.structural_bounds) == "INFEASIBLE"
    # An explicit false permits it too, and an explicit true policy forbids it, whatever the quarterback count.
    only_true = StructuralBounds(
        qb_count=new.structural_bounds.qb_count, offense_against_own_dst=True)
    assert structural_bound_violations(slate, roster, only_true) == ("offense_against_own_dst",)
    assert structural_bound_violations(slate, roster, StructuralBounds(offense_against_own_dst=False)) == ()


def test_a_legal_two_quarterback_roster_passes_the_default_and_fails_the_explicit_one_quarterback_policy(
        tmp_path, capsys):
    slate, rosters = _showdown_world(tmp_path)
    roster = rosters["two_quarterbacks"]
    assert validate_lineup(slate, roster).valid
    _doc, new = _showdown_policy(tmp_path / "new", capsys)
    _doc, one = _showdown_policy(tmp_path / "one", capsys, "--qb-count-max", "1")
    assert structural_bound_violations(slate, roster, new.structural_bounds) == ()
    assert structural_bound_violations(slate, roster, one.structural_bounds) == ("qb_count",)
    assert _solve_fixed(slate, roster, new.structural_bounds) == "OPTIMAL"
    assert _solve_fixed(slate, roster, one.structural_bounds) == "INFEASIBLE"


def test_the_pass_catcher_bound_is_still_per_rostered_quarterback_under_two_quarterbacks(tmp_path, capsys):
    slate, rosters = _showdown_world(tmp_path)
    roster = rosters["second_quarterback_alone"]
    assert validate_lineup(slate, roster).valid
    _doc, new = _showdown_policy(tmp_path, capsys)
    # Salary aside (this roster leaves $6,300), the only thing wrong is the quarterback with no pass catcher.
    bounds = StructuralBounds(
        qb_count=new.structural_bounds.qb_count,
        pass_catchers_with_rostered_qb=new.structural_bounds.pass_catchers_with_rostered_qb,
        salary_left=OPEN_RANGE)
    assert structural_bound_violations(slate, roster, bounds) == ("pass_catchers_with_rostered_qb",)


def _classic_world():
    """The synthetic Classic slate with nine fixed people priced so their roster leaves $300 (the generated $0 to $1,000 band)."""

    base = _classic_slate()
    names = ["DAL QB 1", "NE RB 1", "PHI RB 1", "DAL WR 1", "PHI WR 1", "BUF WR 1", "BUF TE 1", "NYJ WR 2", "NE DST 1"]
    prices = dict(zip(names, [5500] * 8 + [5700], strict=True))
    slate = base.model_copy(update={"players": tuple(
        player.model_copy(update={"salary": prices[player.name]}) if player.name in prices else player
        for player in base.players)})
    by_name = {player.name: player.dk_id for player in slate.players}
    return slate, tuple(by_name[name] for name in names)


def test_a_classic_rb_plus_own_dst_roster_passes_the_new_default_and_fails_the_legacy_policy():
    slate, roster = _classic_world()
    assert validate_lineup(slate, roster).valid  # NE RB 1 beside NE DST 1, the only own-team pair
    new, legacy = _classic_policy(slate, False), _classic_policy(slate, True)
    assert new.structural_bounds == ClassicStructuralBounds(new.structural_bounds.salary_left, False)
    assert new.structural_bounds.violations(slate, roster) == ()
    assert legacy.structural_bounds.violations(slate, roster) == ("offense_against_own_dst",)
    objective = {row.dk_id: 1.0 for row in slate.players}
    statuses = {}
    for label, policy in (("new", new), ("legacy", legacy)):
        optimizer = LineupOptimizer(slate, time_limit_seconds=5.0, mip_gap=0.0)
        _Enumerator(slate, policy, objective, excluded_ids=())._add_structural_rows(optimizer)
        for dk_id in roster:
            optimizer.add_required_row(dk_id)
        statuses[label] = optimizer.solve(objective).status
    assert statuses == {"new": "OPTIMAL", "legacy": "INFEASIBLE"}


# --------------------------------------------------------------------------- #
# F-07's bank check: neither a one-quarterback nor a two-quarterback bank needs a relaxation to be admitted
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("favoured", "quarterbacks"), [("two", 2), ("one", 1)])
def test_the_default_bank_admits_each_quarterback_count_without_a_relaxation(tmp_path, capsys, favoured, quarterbacks):
    slate, _rosters = _showdown_world(tmp_path)
    _doc, new = _showdown_policy(tmp_path / "gen", capsys)
    entry_ids = ("1", "2", "3")
    document = portfolio_policy_template(
        slate, entry_ids,
        controls={"structural_bounds": new.structural_bounds.as_mapping()},
        schema_version=POLICY_SCHEMA_VERSION_V2)
    policy = validate_portfolio_policy_bytes(json.dumps(document).encode(), slate=slate, entry_ids=entry_ids).policy
    assert policy is not None and (policy.structural_bounds.qb_count.minimum,
                                   policy.structural_bounds.qb_count.maximum) == (1, 2)
    # Favour two quarterbacks by making both worth far more than anyone else; favour one by making only the first so
    # and the second worth less than a replacement, so a second quarterback is never the better row.
    def _worth(row) -> float:
        if row.position != "QB":
            return 5.0
        return 50.0 if favoured == "two" or row.team == "NE" else 0.0

    objective = {row.dk_id: _worth(row) for row in slate.players}
    bank = build_policy_candidate_bank(
        slate, objective, policy=policy, candidate_limit=6,
        total_time_limit_seconds=10, per_solve_time_limit_seconds=2)
    by_id = {row.dk_id: row for row in slate.players}
    counts = [sum(1 for dk_id in candidate.roster if by_id[dk_id].position == "QB") for candidate in bank.candidates]
    assert bank.candidates and counts[0] == quarterbacks
    assert set(counts) <= {1, 2}
