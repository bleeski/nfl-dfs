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
