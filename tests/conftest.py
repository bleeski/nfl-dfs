from __future__ import annotations

from pathlib import Path

import pytest

from nfl_dfs.dk import parse_entries, parse_salaries


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "supplied"


@pytest.fixture(scope="session")
def classic_slate():
    return parse_salaries(FIXTURE_ROOT / "DKSalaries Salary CSV Classic.csv")


@pytest.fixture(scope="session")
def showdown_slate():
    return parse_salaries(FIXTURE_ROOT / "DKSalaries Salary CSV Showdown.csv")


@pytest.fixture(scope="session")
def classic_entries():
    return parse_entries(FIXTURE_ROOT / "DKEntries CSV.csv")


@pytest.fixture(scope="session")
def classic_entries_20():
    """A Classic entries export at a realistic entry count.

    The two-entry `DKEntries CSV.csv` keeps both of its entries inside the
    six-line instructions block, so no entry row is ever wider than the header
    and the embedded player-pool table is never parsed alongside one. That is
    the only reason the 2026-09-13 parse defect reached a live slate. Fourteen
    of this file's twenty entry rows carry the pool table.
    """

    return parse_entries(FIXTURE_ROOT / "DKEntries CSV 20 entries.csv")
