"""R20: contest identity gates economics, so it must not gate the prior-only path.

A DraftKings bulk-entry file is exported per draft group, so a slate's reserved
entries routinely span several contests and entry fees. `prior_review` reads no
payout table, prize value or field size and always ends `DO_NOT_UPLOAD`, and
Contest ID and Entry Fee are never read or written as roster cells. The spanning
file is therefore an observation there and stays a fail-closed blocker wherever
economics are consulted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nfl_dfs.dk import (
    DraftKingsParseError,
    parse_entries,
    parse_salaries,
    require_single_contest,
    single_contest_problems,
)
from nfl_dfs.review_export import export_review_entries


SHOWDOWN_SALARIES = Path("tests/fixtures/supplied/DKSalaries Salary CSV Showdown.csv")

ENTRY_HEADER = (
    "Entry ID,Contest Name,Contest ID,Entry Fee,CPT,FLEX,FLEX,FLEX,FLEX,FLEX,,Instructions"
)


def _spanning_entries(tmp_path: Path) -> Path:
    path = tmp_path / "DKEntries_multi_contest.csv"
    path.write_text(
        "\n".join(
            [
                ENTRY_HEADER,
                "5249214148,Showdown $0.25 Contest,195379585,$0.25,,,,,,,,",
                "5249167150,Showdown $8K Daily Dollar,195390889,$1,,,,,,,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_spanning_entries_are_named_by_the_economics_helper(tmp_path: Path) -> None:
    template = parse_entries(_spanning_entries(tmp_path))

    problems = single_contest_problems(template)

    assert problems == (
        "MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED: reserved entries must share one Contest ID",
        "MIXED_ENTRY_FEES_UNSUPPORTED: reserved entries must share one entry fee",
    )


def test_economics_bearing_callers_still_fail_closed(tmp_path: Path) -> None:
    template = parse_entries(_spanning_entries(tmp_path))

    with pytest.raises(DraftKingsParseError, match="MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED"):
        require_single_contest(template)


def test_review_export_reports_contest_scope_without_blocking(tmp_path: Path) -> None:
    slate = parse_salaries(SHOWDOWN_SALARIES)
    template = parse_entries(_spanning_entries(tmp_path))
    by_role: dict[str, list[str]] = {"CPT": [], "FLEX": []}
    for player in slate.players:
        by_role[player.role].append(player.dk_id)
    cheapest_flex = sorted(
        (player for player in slate.players if player.role == "FLEX"),
        key=lambda player: player.salary,
    )
    captain = min(
        (player for player in slate.players if player.role == "CPT"),
        key=lambda player: player.salary,
    )

    def _roster(offset: int) -> tuple[str, ...]:
        flex: list[str] = []
        for player in cheapest_flex[offset:]:
            if player.underlying_id == captain.underlying_id:
                continue
            flex.append(player.dk_id)
            if len(flex) == 5:
                break
        return (captain.dk_id, *flex)

    assignments = {
        "5249214148": _roster(0),
        "5249167150": _roster(1),
    }

    export = export_review_entries(
        slate=slate,
        template=template,
        assignments=assignments,
        output_path=tmp_path / "DK_REVIEW_ENTRY_multi_contest.csv",
    )

    assert "MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED" not in " ".join(export.problems)
    assert "MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED" in " ".join(export.observations)
    assert "MIXED_ENTRY_FEES_UNSUPPORTED" in " ".join(export.observations)
    report = export.as_report()
    assert report["MODEL_STATUS"] == "PRIOR_ONLY"
    assert report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert "SINGLE_CONTEST_AND_ENTRY_FEE_ECONOMICS_SCOPE" in report["checks_not_run"]
    assert "SINGLE_CONTEST_AND_ENTRY_FEE" not in report["checks_run"]
