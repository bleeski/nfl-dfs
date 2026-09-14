from __future__ import annotations

from pathlib import Path

import pytest

from nfl_dfs.byte_lines import split_byte_lines
from nfl_dfs.dk import DraftKingsParseError, parse_entries
from nfl_dfs.lineups import write_upload_bytes
from nfl_dfs.referee import audit_output_bytes

from .conftest import FIXTURE_ROOT


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
def test_writer_and_referee_do_not_treat_unicode_separators_as_csv_lines(
    tmp_path: Path, separator: str
) -> None:
    original = (FIXTURE_ROOT / "DKEntries CSV.csv").read_bytes().decode("cp1252")
    contest = "NFL $3.5M Fantasy Football Millionaire [$1M to 1st]"
    adversarial = original.replace(contest, f'"NFL{separator} $3.5M Fantasy Football Millionaire [$1M to 1st]"')
    source = tmp_path / "unicode-entry-template.csv"
    source.write_bytes(adversarial.rstrip("\r\n").encode("utf-8-sig"))
    template = parse_entries(source)
    assignments = {
        authorization.entry_id: tuple(
            f"{index + 1}{authorization.entry_id[-2:]}" for index in range(9)
        )
        for authorization in template.authorizations
    }

    output = write_upload_bytes(template, assignments)
    audit = audit_output_bytes(source, output, template, assignments)

    assert audit.valid, audit.problems
    assert len(split_byte_lines(output)) == len(split_byte_lines(source.read_bytes()))
    assert separator.encode("utf-8") in output
    assert not output.endswith(b"\n")
    assert output.startswith(b"\xef\xbb\xbf")
    assert output.count(b"\xef\xbb\xbf") == 1


def test_classic_entry_rows_carrying_the_embedded_player_pool_table_parse(tmp_path):
    """A real Classic export repeats DraftKings' pool table on the entry rows.

    Regression for the 2026-09-13 Week 1 main slate: the supplied two-entry
    fixture holds both of its entries inside the six-line instructions block, so
    no entry row was ever wider than the header. A twenty-entry export puts
    fourteen entry rows alongside the embedded pool table and the malformed-row
    guard refused the file outright, which blocked the Classic path for every
    real entry count.
    """

    header = (
        "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions"
    )
    pool_header = (
        "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame"
    )
    pool_row = (
        "RB,Jahmyr Gibbs (43727325),Jahmyr Gibbs,43727325,RB/FLEX,8000,"
        "NO@DET 09/13/2026 01:00PM ET,DET,22.3"
    )
    path = tmp_path / "DKEntries.csv"
    path.write_text(
        "\n".join(
            [
                header,
                "5210040219,NFL Millionaire,193028206,$5,,,,,,,,,,,1. instructions",
                f"5210040220,NFL Millionaire,193028206,$5,,,,,,,,,,,{pool_header}",
                f"5210040221,NFL Millionaire,193028206,$5,,,,,,,,,,,{pool_row}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    template = parse_entries(path)
    assert [item.entry_id for item in template.authorizations] == [
        "5210040219",
        "5210040220",
        "5210040221",
    ]
    # The roster cells stay empty: nothing from the embedded table leaks in.
    for authorization in template.authorizations:
        assert authorization.existing_cells == ("",) * 9


def test_a_wide_row_with_no_embedded_pool_table_still_fails_closed(tmp_path):
    """Relaxing the width guard must not retire it."""

    header = (
        "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions"
    )
    path = tmp_path / "DKEntries_bad.csv"
    path.write_text(
        header + "\n5210040222,NFL Millionaire,193028206,$5,,,,,,,,,,,x,junk,junk\n",
        encoding="utf-8",
    )
    with pytest.raises(DraftKingsParseError, match="more cells than the header"):
        parse_entries(path)


def test_unexplained_cells_before_the_embedded_pool_table_still_fail_closed(tmp_path):
    """Width is forgiven only to the right of the pool table's first column.

    A cell between the roster block and the embedded table is unaccounted for,
    and an unaccounted-for cell is how a roster silently shifts.
    """

    header = (
        "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions"
    )
    pool_header = (
        "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame"
    )
    path = tmp_path / "DKEntries_shifted.csv"
    path.write_text(
        "\n".join(
            [
                header,
                f"5210040220,NFL Millionaire,193028206,$5,,,,,,,,,,,{pool_header}",
                # one unexplained cell where the file's own table says nothing lives
                "5210040221,NFL Millionaire,193028206,$5,,,,,,,,,,SHIFTED,"
                "RB,Jahmyr Gibbs (43727325),Jahmyr Gibbs,43727325,RB/FLEX,8000,x,DET,22.3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DraftKingsParseError, match="more cells than the header"):
        parse_entries(path)


def test_the_supplied_twenty_entry_export_parses_every_entry(classic_entries_20):
    """The fixture defect itself: two entries could never have caught this.

    Fourteen of these twenty entry rows are wider than the header because they
    carry DraftKings' embedded player-pool table.
    """

    assert len(classic_entries_20.authorizations) == 20
    assert len({item.entry_id for item in classic_entries_20.authorizations}) == 20
    assert {item.contest_id for item in classic_entries_20.authorizations} == {"193028206"}
    for authorization in classic_entries_20.authorizations:
        assert authorization.existing_cells == ("",) * 9
        assert authorization.entry_fee == 5.0
