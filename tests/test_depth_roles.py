"""P7 acceptance: effective depth rank, and the promotion R25 authorised.

Every published rank asserted here was read out of the real nflverse artifact
`depth_charts_2026.csv`, sha256
`e6ba0a08dc40c164eb02ce7654a247c8eb5c2d189c92d993d028524eb0494c02`, at snapshot
`2026-09-20T12:14:30Z`, captured on 2026-09-21 through
`sources.fetch_public_artifact`. That snapshot is 08:14:30 ET, which is the
measurement the chunk rests on: it is the last chart published before a 13:00 ET
lock, and official inactives publish about 11:30 ET, so the published order is
always three hours stale by the time it is needed.

The ranks are pinned as constants rather than re-fetched. A test that reaches
the network is not a test, and the point of the fixture is the *shape* the
2026-09-20 chart had, which is now history and cannot change.

What these tests do not prove: the DraftKings half. `Status` values here are
fixture bytes chosen to reproduce the documented situation, not the 2026-09-20
salary export, which is an operator download under a gitignored path and is not
in this container. The snapshot-bound replay stays a Windows-session acceptance
item; see `backlog.md` P7.
"""

from __future__ import annotations

import pytest

from nfl_dfs.depth_roles import (
    EFFECTIVE_RANK_VERSION,
    SKILL_POSITIONS,
    DepthRoleError,
    DepthRow,
    effective_depth_ranks,
    effective_starter,
    promote_to_effective_starter,
)

# Verbatim from the 2026-09-20T12:14:30Z snapshot: (team, pos_abb, rank, gsis, name).
_PUBLISHED = (
    ("MIN", "QB", 1, "00-0035228", "Kyler Murray"),
    ("MIN", "QB", 2, "00-0032950", "Carson Wentz"),
    ("MIN", "QB", 3, "00-0039923", "J.J. McCarthy"),
    ("SEA", "QB", 1, "00-0034869", "Sam Darnold"),
    ("SEA", "QB", 2, "00-0035704", "Drew Lock"),
    ("SEA", "QB", 3, "00-0040673", "Jalen Milroe"),
    ("LV", "TE", 1, "00-0039338", "Brock Bowers"),
    ("LV", "TE", 2, "00-0039066", "Michael Mayer"),
    ("LV", "TE", 3, "00-0034365", "Ian Thomas"),
    ("HOU", "WR", 1, "00-0036554", "Nico Collins"),
    ("HOU", "WR", 2, "00-0038618", "Xavier Hutchinson"),
    ("HOU", "WR", 3, "00-0038608", "Kayshon Boutte"),
    ("BAL", "WR", 1, "00-0039064", "Zay Flowers"),
    ("BAL", "WR", 2, "00-0036550", "Rashod Bateman"),
    ("BAL", "WR", 3, "00-0039792", "Devontez Walker"),
)

# The return lines, from the same snapshot. Both people outrank their own
# offensive row on a kick-return or punt-return line.
_RETURN_ROWS = (
    ("ATL", "KR", 1, "00-0037746", "Brian Robinson Jr."),
    ("ATL", "RB", 2, "00-0037746", "Brian Robinson Jr."),
    ("ARI", "KR", 1, "00-0036331", "Devin Duvernay"),
    ("ARI", "PR", 1, "00-0036331", "Devin Duvernay"),
    ("ARI", "WR", 6, "00-0036331", "Devin Duvernay"),
)


def _rows(published=_PUBLISHED):
    return [
        DepthRow(
            person=gsis,
            team=team,
            position=position,
            published_rank=rank,
            player_name=name,
        )
        for team, position, rank, gsis, name in published
    ]


def test_nobody_moves_when_every_published_starter_is_available():
    ranks = effective_depth_ranks(_rows(), unavailable_people=())
    assert all(not rank.promoted for rank in ranks.values())
    assert ranks[("00-0034869", "QB")].effective_rank == 1
    assert ranks[("00-0035704", "QB")].effective_rank == 2


def test_the_backup_inherits_when_the_published_starter_is_out():
    """Darnold OUT promotes Lock, which is the case that stopped 2026-09-20."""

    ranks = effective_depth_ranks(_rows(), unavailable_people={"00-0034869"})
    lock = ranks[("00-0035704", "QB")]
    assert lock.effective_rank == 1
    assert lock.published_rank == 2
    assert lock.promoted is True
    assert lock.promoted_over == ("00-0034869",)
    assert ranks[("00-0040673", "QB")].effective_rank == 2
    assert ("00-0034869", "QB") not in ranks


def test_wentz_inherits_minnesota_when_murray_is_out():
    ranks = effective_depth_ranks(_rows(), unavailable_people={"00-0035228"})
    wentz = ranks[("00-0032950", "QB")]
    assert (wentz.effective_rank, wentz.published_rank) == (1, 2)
    assert effective_starter(ranks, team="MIN", position="QB").player_name == "Carson Wentz"


@pytest.mark.parametrize(
    "out_person,promoted_person,team,position,name",
    [
        ("00-0039338", "00-0039066", "LV", "TE", "Michael Mayer"),
        ("00-0036554", "00-0038618", "HOU", "WR", "Xavier Hutchinson"),
        ("00-0039064", "00-0036550", "BAL", "WR", "Rashod Bateman"),
    ],
)
def test_every_skill_position_resolves_not_just_quarterback(
    out_person, promoted_person, team, position, name
):
    """The three 2→1 promotions the R25 stanza named, at TE and WR."""

    ranks = effective_depth_ranks(_rows(), unavailable_people={out_person})
    promoted = ranks[(promoted_person, position)]
    assert (promoted.effective_rank, promoted.published_rank) == (1, 2)
    assert promoted.player_name == name
    assert effective_starter(ranks, team=team, position=position) == promoted


def test_a_kick_return_line_is_never_an_offensive_role():
    """Brian Robinson Jr. is KR 1 and RB 2. He is not Atlanta's lead back."""

    ranks = effective_depth_ranks(_rows(_RETURN_ROWS), unavailable_people=())
    assert ("00-0037746", "KR") not in ranks
    assert ranks[("00-0037746", "RB")].published_rank == 2
    assert ranks[("00-0037746", "RB")].effective_rank == 1
    # Rank 1 at RB here only because no other Atlanta back is in this fixture.
    # The point is the position key: his KR row contributed nothing.
    assert effective_starter(ranks, team="ATL", position="KR") is None


def test_a_punt_returner_does_not_become_a_number_one_receiver():
    ranks = effective_depth_ranks(_rows(_RETURN_ROWS), unavailable_people=())
    duvernay = ranks[("00-0036331", "WR")]
    assert duvernay.published_rank == 6
    assert ("00-0036331", "PR") not in ranks
    assert ("00-0036331", "KR") not in ranks


def test_only_the_four_skill_positions_are_ranked():
    assert SKILL_POSITIONS == ("QB", "RB", "WR", "TE")
    assert EFFECTIVE_RANK_VERSION == "effective_depth_rank_v1"


def test_a_duplicate_published_rank_is_refused():
    rows = _rows() + [
        DepthRow(person="00-0000001", team="SEA", position="QB", published_rank=1, player_name="Ghost")
    ]
    with pytest.raises(DepthRoleError, match="DEPTH_DUPLICATE_PUBLISHED_RANK"):
        effective_depth_ranks(rows, unavailable_people=())


def test_a_person_ranked_twice_at_one_position_is_refused():
    rows = _rows() + [
        DepthRow(person="00-0034869", team="SEA", position="QB", published_rank=9, player_name="Sam Darnold")
    ]
    with pytest.raises(DepthRoleError, match="DEPTH_PERSON_RANKED_TWICE"):
        effective_depth_ranks(rows, unavailable_people=())


def test_a_rank_below_one_is_refused():
    rows = [DepthRow(person="p", team="SEA", position="QB", published_rank=0, player_name="n")]
    with pytest.raises(DepthRoleError, match="DEPTH_PUBLISHED_RANK_INVALID"):
        effective_depth_ranks(rows, unavailable_people=())


# --- the promotion bound R25 made binding ---------------------------------


def test_promotion_steps_over_the_unavailable_and_names_them():
    person, stepped = promote_to_effective_starter(
        [(1, "starter"), (2, "backup"), (3, "third")],
        unavailable_people={"starter"},
        selectable_people={"backup", "third"},
        team="SEA",
    )
    assert person == "backup"
    assert stepped == ("starter",)


def test_an_operator_exclusion_never_promotes_a_backup():
    """The salary bytes still show the starter available, so nobody inherits.

    This is R25's first bound. Availability is a fact about who is playing and
    is re-derived from the bound salary bytes; an operator exclusion is a
    preference. A preference that could hand the job to someone else would let a
    supplied file widen the set, which is exactly what the bound forbids.
    """

    with pytest.raises(DepthRoleError, match="DEPTH_PROMOTION_OVER_AVAILABLE_PERSON"):
        promote_to_effective_starter(
            [(1, "starter"), (2, "backup")],
            unavailable_people=set(),
            selectable_people={"backup"},
            team="SEA",
        )


def test_a_position_with_nobody_selectable_still_refuses():
    with pytest.raises(DepthRoleError, match="DEPTH_NO_SELECTABLE_PERSON_AT_POSITION"):
        promote_to_effective_starter(
            [(1, "starter"), (2, "backup")],
            unavailable_people={"starter", "backup"},
            selectable_people=set(),
            team="SEA",
        )


def test_promotion_never_reaches_past_a_selectable_person():
    """Rank 1 selectable means rank 1 keeps the job, whoever is below him."""

    person, stepped = promote_to_effective_starter(
        [(1, "starter"), (2, "backup")],
        unavailable_people={"backup"},
        selectable_people={"starter"},
        team="SEA",
    )
    assert (person, stepped) == ("starter", ())


def test_an_empty_order_is_refused():
    with pytest.raises(DepthRoleError, match="DEPTH_ORDER_EMPTY"):
        promote_to_effective_starter(
            [], unavailable_people=set(), selectable_people=set(), team="SEA"
        )
