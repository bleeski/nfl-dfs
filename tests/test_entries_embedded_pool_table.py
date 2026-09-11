"""R19: DraftKings overlaps its embedded salary-pool block with entry rows.

DraftKings exports the whole player pool into columns to the right of the entry
template. The block starts at a fixed physical row, so once the reserved-entry
count reaches that row the same rows carry both an Entry ID and pool cells and
are legitimately wider than the entry header. The over-wide-row guard must
admit exactly that geometry and nothing looser.
"""

from __future__ import annotations

import pytest

from nfl_dfs.dk import DraftKingsParseError, parse_entry_bytes


HEADER = "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions"
POOL_HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame"
POOL_ROW = "WR,Puka Nacua (44080768),Puka Nacua,44080768,CPT,16800,SF@LAR 09/10/2026 08:35PM ET,LAR,25.14"


def _entry(entry_id: str, trailing: str = "") -> str:
    return f"{entry_id},NFL Showdown $0.25 Contest (SF vs LAR),195379585,$0.25,,,,,,,,{trailing}"


def _build(rows: list[str]) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode("utf-8")


def test_entry_row_carrying_embedded_pool_cells_parses() -> None:
    raw = _build([_entry("5249214148"), _entry("5249175224", POOL_HEADER), _entry("5249160136", POOL_ROW)])

    template = parse_entry_bytes(raw, source_name="DKEntries_SF_LAR.csv")

    assert [entry.entry_id for entry in template.authorizations] == [
        "5249214148",
        "5249175224",
        "5249160136",
    ]
    assert all(entry.existing_cells == ("",) * 6 for entry in template.authorizations)


def test_over_wide_entry_row_without_a_pool_block_still_fails() -> None:
    raw = _build([_entry("5249214148", "44080768,44080714,44080715")])

    with pytest.raises(DraftKingsParseError, match="more cells than the header"):
        parse_entry_bytes(raw, source_name="DKEntries_SF_LAR.csv")


def test_pool_block_does_not_license_a_shifted_row() -> None:
    shifted = "5249160136,NFL Showdown $0.25 Contest (SF vs LAR),195379585,$0.25,,,,,,,44080768," + POOL_ROW
    raw = _build([_entry("5249175224", POOL_HEADER), shifted])

    with pytest.raises(DraftKingsParseError, match="more cells than the header"):
        parse_entry_bytes(raw, source_name="DKEntries_SF_LAR.csv")
