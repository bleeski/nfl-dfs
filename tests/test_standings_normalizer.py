"""A raw DraftKings standings export must become a contract artifact or a refusal.

`scripts/file_standings.py` is the back half of the standings pipeline: the
checklist says which contests need a pull, this says what a pulled file has to
become before `settle --request` will look at it. Everything it does to an
export is a decision about meaning, so every one of those decisions is pinned
here — and every way a real export can fail to be normalizable produces a named
refusal rather than a quietly repaired file.

The golden fixture is shaped like the real thing, measured against Ben's own 18
exports rather than assumed: one header row, DraftKings' standings columns
first, one unnamed spacer column, then the per-player ownership table living in
the *same rows* and running out before the standings do.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "supplied"
SHOWDOWN_SALARY = FIXTURE_ROOT / "DKSalaries Salary CSV Showdown.csv"


def _normalizer():
    path = Path(__file__).resolve().parents[1] / "scripts" / "file_standings.py"
    spec = importlib.util.spec_from_file_location("file_standings", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def normalizer():
    return _normalizer()


# ---------------------------------------------------------------------------
# Building an export shaped like DraftKings' own
# ---------------------------------------------------------------------------

RAW_HEADER = [
    "Rank", "EntryId", "EntryName", "TimeRemaining", "Points", "Lineup",
    "", "Player", "Roster Position", "%Drafted", "FPTS",
]

#: Six people from the supplied Showdown salary fixture, as DraftKings writes
#: them into a lineup string: slot token, then the person's name.
#: Cheap enough to be cap-legal and spanning both teams, so the same six can be
#: reused as a real lineup when a test needs the engine to validate one.
CPT_A = "Reggie Gilliam"
FLEX_A = (
    "Jacardia Wright", "Brady Russell", "Robbie Ouzts",
    "Myles Montgomery", "Tejhaun Palmer",
)
LINEUP_A = "CPT " + CPT_A + " " + " ".join("FLEX " + name for name in FLEX_A)
LINEUP_B = (
    "CPT " + FLEX_A[0] + " FLEX " + CPT_A + " "
    + " ".join("FLEX " + name for name in FLEX_A[1:])
)


def write_export(
    path: Path,
    rows: list[tuple[int, str, str, str]],
    *,
    header: list[str] | None = None,
    ownership_rows: int = 3,
    zipped: bool = False,
    truncate_last_row: bool = False,
) -> Path:
    """Write a DraftKings-shaped export. `rows` is (rank, entry_id, points, lineup)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    head = header if header is not None else RAW_HEADER
    writer.writerow(head)
    width = len(head)
    for index, (rank, entry_id, points, lineup) in enumerate(rows):
        record = [rank, entry_id, f"user{index}", "0", points, lineup]
        # The ownership table shares these rows and runs out early, exactly as
        # DraftKings ships it.
        if index < ownership_rows:
            record += ["", f"Player {index}", "FLEX", "12.34%", "9.9"]
        else:
            record += ["", "", "", "", ""]
        writer.writerow(record[:width])
    text = buffer.getvalue()
    if truncate_last_row:
        text = text[: text.rfind("\r\n", 0, text.rfind("\r\n"))] + "\r\n1,999,u,0\r\n"
    if zipped:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(f"{path.stem}.csv", text)
        path.write_bytes(payload.getvalue())
    else:
        path.write_text(text, encoding="utf-8", newline="")
    return path


GOLDEN_ROWS = [
    (1, "5000000001", "101.02", LINEUP_A),
    (2, "5000000002", "85.850006", LINEUP_B),
    (2, "5000000003", "85.85", LINEUP_B),
    (4, "5000000004", "40.5", LINEUP_A),
]


@pytest.fixture()
def payouts(tmp_path):
    path = tmp_path / "payouts.csv"
    path.write_text(
        "rank_start,rank_end,prize_type,value\r\n"
        "1,1,CASH,10\r\n"
        "2,2,CASH,5\r\n"
        "3,3,CASH,5\r\n",
        encoding="utf-8",
        newline="",
    )
    return path


@pytest.fixture()
def golden(tmp_path):
    return write_export(tmp_path / "contest-standings-195384501.csv", GOLDEN_ROWS)


def run(normalizer, raw, payouts, tmp_path, **kwargs):
    kwargs.setdefault("advertised_prize_value", Decimal("20.00"))
    kwargs.setdefault("output_root", tmp_path / "normalized")
    return normalizer.normalize_export(
        raw, salaries=SHOWDOWN_SALARY, payouts=payouts, **kwargs
    )


def read_normalized(result) -> list[dict]:
    with result.normalized_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------------------
# Golden
# ---------------------------------------------------------------------------


def test_the_normalized_file_is_exactly_the_contract_shape(normalizer, golden, payouts, tmp_path):
    result = run(normalizer, golden, payouts, tmp_path)
    rows = read_normalized(result)
    assert list(rows[0]) == list(normalizer.NORMALIZED_COLUMNS)
    assert [r["EntryId"] for r in rows] == [
        "5000000001", "5000000002", "5000000003", "5000000004"
    ]
    assert result.row_count == 4


def test_the_side_by_side_ownership_table_is_dropped_not_parsed(normalizer, golden, payouts, tmp_path):
    """The ownership block is columns, not a trailing block, and never a row."""
    result = run(normalizer, golden, payouts, tmp_path)
    assert result.manifest["ownership_block_columns_dropped"] == 5
    text = result.normalized_path.read_text(encoding="utf-8")
    assert "%Drafted" not in text and "Player 0" not in text
    assert result.row_count == len(GOLDEN_ROWS)


def test_points_are_rounded_to_two_places_and_the_move_is_recorded(normalizer, golden, payouts, tmp_path):
    """DraftKings' own Rank is computed from the true 2-decimal score.

    `85.850006` and `85.85` are DraftKings' float round-trip noise around one
    real score, and it ranks both entries 2nd. Carrying the raw values through
    would split a tie group DraftKings did not split.
    """
    result = run(normalizer, golden, payouts, tmp_path)
    points = {r["EntryId"]: r["Points"] for r in read_normalized(result)}
    assert points["5000000002"] == points["5000000003"] == "85.85"
    assert result.manifest["points"]["rows_adjusted"] == 1
    assert Decimal(result.manifest["points"]["max_adjustment"]) == Decimal("0.000006")


def test_a_points_value_too_far_from_two_places_is_refused_not_rounded(normalizer, tmp_path, payouts):
    """Past the float-noise tolerance the assumption has stopped holding."""
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        [(1, "5000000001", "101.029", LINEUP_A), (2, "5000000002", "40.5", LINEUP_B)],
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="POINTS_ADJUSTMENT_TOO_LARGE"):
        run(normalizer, raw, payouts, tmp_path)


def test_lineup_names_become_the_engines_own_canonical_key(normalizer, golden, payouts, tmp_path):
    """The whole point of the Lineup column: it must equal what the engine builds.

    Rebuilt here through `lineups.validate_lineup` from the salary rows the
    export's names resolve to, which is the same function
    `settlement._prepare_settlement` uses to check an owned entry.
    """
    from nfl_dfs.dk import parse_salaries
    from nfl_dfs.lineups import validate_lineup

    result = run(normalizer, golden, payouts, tmp_path)
    slate = parse_salaries(SHOWDOWN_SALARY)
    by_name = {p.name: p for p in slate.players}

    def dk_id(name: str, role: str) -> str:
        return next(
            p.dk_id for p in slate.players
            if p.underlying_id == by_name[name].underlying_id and p.role == role
        )

    validated = validate_lineup(
        slate, [dk_id(CPT_A, "CPT"), *(dk_id(name, "FLEX") for name in FLEX_A)]
    )
    assert validated.valid, validated.errors
    expected = validated.lineup.canonical_key
    keys = {r["EntryId"]: r["Lineup"] for r in read_normalized(result)}
    assert keys["5000000001"] == expected


def test_a_zipped_export_normalizes_to_the_same_bytes_as_a_plain_one(normalizer, tmp_path, payouts):
    """DraftKings ships large contests zipped and small ones plain."""
    plain = write_export(tmp_path / "a" / "contest-standings-195384501.csv", GOLDEN_ROWS)
    zipped = write_export(tmp_path / "b" / "contest-standings-195384501.zip", GOLDEN_ROWS, zipped=True)
    first = run(normalizer, plain, payouts, tmp_path / "one")
    second = run(normalizer, zipped, payouts, tmp_path / "two")
    assert first.normalized_sha256 == second.normalized_sha256
    assert second.manifest["raw"]["zip_member"] == "contest-standings-195384501.csv"


def test_prize_is_labelled_derived_because_draftkings_exports_none(normalizer, golden, payouts, tmp_path):
    """The design answer to 'where does Prize come from'.

    A real DraftKings full standings export has no Prize column at all, so the
    column is necessarily joined from the payout table. The manifest says so, and
    binds the payout bytes by hash, so nothing downstream can mistake it for an
    observation.
    """
    result = run(normalizer, golden, payouts, tmp_path)
    prize = result.manifest["prize"]
    assert prize["observed_in_export"] is False
    assert prize["provenance"] == "DERIVED_REFERENCE_SETTLEMENT_V1"
    assert len(prize["payout_sha256"]) == 64
    assert "cannot be independent evidence" in prize["note"]


# ---------------------------------------------------------------------------
# Adversarial
# ---------------------------------------------------------------------------


def test_a_truncated_export_is_refused_not_settled_as_a_short_field(normalizer, tmp_path, payouts):
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv", GOLDEN_ROWS, truncate_last_row=True
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="RAW_EXPORT_TRUNCATED_ROW"):
        run(normalizer, raw, payouts, tmp_path)


def test_a_duplicate_entry_id_is_refused(normalizer, tmp_path, payouts):
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        GOLDEN_ROWS + [(5, "5000000001", "10.0", LINEUP_A)],
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="DUPLICATE_ENTRY_ID"):
        run(normalizer, raw, payouts, tmp_path)


def test_a_missing_required_column_is_refused(normalizer, tmp_path, payouts):
    """The absent column that matters is a *standings* column.

    `Prize` is absent from every real export, which is why it is derived rather
    than read; losing `Points` or `Lineup` is the failure this catches.
    """
    header = [c for c in RAW_HEADER if c != "Points"]
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv", GOLDEN_ROWS, header=header
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="RAW_EXPORT_MISSING_COLUMNS"):
        run(normalizer, raw, payouts, tmp_path)


def test_a_blank_lineup_is_refused_by_default(normalizer, tmp_path, payouts):
    """A real field member who never submitted a lineup.

    11 of Ben's 18 exports carry them. `nfl_standings_csv_v2` requires a nonempty
    canonical key, so the contract cannot represent them and the default is to
    say so rather than invent one.
    """
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        GOLDEN_ROWS + [(5, "5000000005", "0", "")],
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="UNSUBMITTED_ENTRY_LINEUP"):
        run(normalizer, raw, payouts, tmp_path)


def test_an_unsubmitted_entry_can_be_recorded_explicitly_when_asked(normalizer, tmp_path, payouts):
    """The opt-in path, and it must stay a declared absence, not a fake lineup."""
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        GOLDEN_ROWS + [(5, "5000000005", "0", "")],
    )
    result = run(
        normalizer, raw, payouts, tmp_path, unsubmitted_entry_policy="sentinel"
    )
    keys = {r["EntryId"]: r["Lineup"] for r in read_normalized(result)}
    assert keys["5000000005"] == "NO_LINEUP_SUBMITTED:5000000005"
    assert result.manifest["lineup"]["unsubmitted_entry_count"] == 1
    assert result.manifest["lineup"]["unsubmitted_entry_policy"] == "sentinel"


def test_an_owned_entry_with_no_lineup_is_always_refused(normalizer, tmp_path, payouts):
    """The sentinel must never paper over a portfolio that never reached DK."""
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        GOLDEN_ROWS + [(5, "5000000005", "0", "")],
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="OWNED_ENTRY_NEVER_SUBMITTED"):
        run(
            normalizer, raw, payouts, tmp_path,
            unsubmitted_entry_policy="sentinel",
            owned_entry_ids={"5000000005"},
        )


def test_a_field_size_disagreement_with_contest_facts_is_refused(normalizer, golden, payouts, tmp_path):
    """The real case: 193391013's operator-stated 133,000 against an observed 126,020."""
    with pytest.raises(normalizer.StandingsNormalizationError, match="FIELD_SIZE_DISAGREEMENT"):
        run(normalizer, golden, payouts, tmp_path, expected_field_size=99)


def test_an_unresolvable_lineup_name_is_refused(normalizer, tmp_path, payouts):
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        [
            (1, "5000000001", "10.0", LINEUP_A.replace(FLEX_A[0], "Nobody Atall")),
            (2, "5000000002", "9.0", LINEUP_B),
        ],
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="LINEUP_NAME_UNRESOLVED"):
        run(normalizer, raw, payouts, tmp_path)


def test_a_lineup_with_the_wrong_roster_shape_is_refused(normalizer, tmp_path, payouts):
    """The check that makes the slot split safe rather than clever."""
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        [
            (1, "5000000001", "10.0", "CPT Drake Maye FLEX A.J. Brown"),
            (2, "5000000002", "9.0", LINEUP_B),
        ],
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="LINEUP_SHAPE_MISMATCH"):
        run(normalizer, raw, payouts, tmp_path)


def test_a_filename_without_a_contest_id_is_refused(normalizer, tmp_path, payouts):
    raw = write_export(tmp_path / "standings.csv", GOLDEN_ROWS)
    with pytest.raises(normalizer.StandingsNormalizationError, match="CONTEST_ID_UNRESOLVED"):
        run(normalizer, raw, payouts, tmp_path)


def test_a_zip_with_several_csv_members_is_refused(normalizer, tmp_path, payouts):
    path = tmp_path / "contest-standings-195384501.zip"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("one.csv", "Rank\n1\n")
        archive.writestr("two.csv", "Rank\n1\n")
    path.write_bytes(payload.getvalue())
    with pytest.raises(normalizer.StandingsNormalizationError, match="RAW_EXPORT_AMBIGUOUS_MEMBER"):
        run(normalizer, path, payouts, tmp_path)


def test_an_uneven_tie_split_is_refused_before_it_is_rounded(normalizer, tmp_path):
    """The exact tie share that `nfl_standings_csv_v2` cannot hold.

    Three entries tie for a prize that does not divide into whole cents. The
    reference evaluator keeps it as an exact rational; the contract requires an
    integer. Real contests hit this constantly, so the refusal names it rather
    than rounding it away by default.
    """
    payouts = tmp_path / "payouts.csv"
    payouts.write_text(
        "rank_start,rank_end,prize_type,value\r\n"
        "1,1,CASH,10\r\n2,2,CASH,5\r\n3,3,CASH,5\r\n",
        encoding="utf-8",
        newline="",
    )
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        [
            (1, "5000000001", "50.00", LINEUP_A),
            (1, "5000000002", "50.00", LINEUP_B),
            (1, "5000000003", "50.00", LINEUP_A),
            (4, "5000000004", "10.00", LINEUP_B),
        ],
    )
    with pytest.raises(normalizer.StandingsNormalizationError, match="PRIZE_NOT_WHOLE_CENTS"):
        run(normalizer, raw, payouts, tmp_path)


def test_rounding_an_uneven_tie_split_records_the_residual(normalizer, tmp_path):
    payouts = tmp_path / "payouts.csv"
    payouts.write_text(
        "rank_start,rank_end,prize_type,value\r\n"
        "1,1,CASH,10\r\n2,2,CASH,5\r\n3,3,CASH,5\r\n",
        encoding="utf-8",
        newline="",
    )
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        [
            (1, "5000000001", "50.00", LINEUP_A),
            (1, "5000000002", "50.00", LINEUP_B),
            (1, "5000000003", "50.00", LINEUP_A),
            (4, "5000000004", "10.00", LINEUP_B),
        ],
    )
    result = run(normalizer, raw, payouts, tmp_path, prize_rounding="half-even")
    rounding = result.manifest["prize"]["rounding"]
    assert rounding["policy"] == "half-even"
    assert rounding["entries_with_fractional_exact_share"] == 3
    # $20.00 split three ways is 666.67 + 666.67 + 666.66 cents; the residual is
    # what rounding to whole cents could not place, and it is recorded, not lost.
    assert Decimal(rounding["residual_cents_after_rounding"]) != 0


# ---------------------------------------------------------------------------
# Determinism and the one guarantee everything else rests on
# ---------------------------------------------------------------------------


def test_the_same_export_normalizes_to_byte_identical_output(normalizer, tmp_path, payouts):
    first = write_export(tmp_path / "a" / "contest-standings-195384501.csv", GOLDEN_ROWS)
    second = write_export(tmp_path / "b" / "contest-standings-195384501.csv", GOLDEN_ROWS)
    one = run(normalizer, first, payouts, tmp_path / "one")
    two = run(normalizer, second, payouts, tmp_path / "two")
    assert one.normalized_sha256 == two.normalized_sha256
    assert one.normalized_path.read_bytes() == two.normalized_path.read_bytes()
    # Content-addressed, so the same export lands at the same filename too.
    assert one.normalized_path.name == two.normalized_path.name


def test_the_manifest_is_stable_apart_from_its_own_timestamp(normalizer, tmp_path, payouts):
    first = write_export(tmp_path / "a" / "contest-standings-195384501.csv", GOLDEN_ROWS)
    second = write_export(tmp_path / "b" / "contest-standings-195384501.csv", GOLDEN_ROWS)
    one = run(normalizer, first, payouts, tmp_path / "one").manifest
    two = run(normalizer, second, payouts, tmp_path / "two").manifest
    for manifest in (one, two):
        manifest.pop("generated_at")
        manifest["raw"].pop("path")
        manifest["normalized"].pop("path")
    assert one == two


def test_the_raw_inbox_file_is_unchanged_by_a_full_run(normalizer, tmp_path, payouts):
    """The guarantee everything downstream rests on: the delivered bytes are kept."""
    raw = write_export(tmp_path / "contest-standings-195384501.csv", GOLDEN_ROWS)
    before = raw.read_bytes()
    before_mtime = raw.stat().st_mtime_ns
    result = run(normalizer, raw, payouts, tmp_path)
    assert raw.read_bytes() == before
    assert raw.stat().st_mtime_ns == before_mtime
    assert raw.is_file()
    assert result.manifest["raw"]["sha256"] == result.raw.sha256
    assert result.normalized_path != raw


def test_nothing_is_written_when_the_export_is_refused(normalizer, tmp_path, payouts):
    raw = write_export(
        tmp_path / "contest-standings-195384501.csv",
        GOLDEN_ROWS + [(5, "5000000001", "10.0", LINEUP_A)],
    )
    output_root = tmp_path / "normalized"
    with pytest.raises(normalizer.StandingsNormalizationError):
        run(normalizer, raw, payouts, tmp_path, output_root=output_root)
    assert not output_root.exists()


# ---------------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------------


def test_survey_reads_an_export_without_a_salary_or_payout_binding(normalizer, tmp_path):
    """The observed row count is the contest's true field size, and nothing else has it."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    write_export(inbox / "contest-standings-195384501.csv", GOLDEN_ROWS)
    findings = normalizer.survey_inbox(inbox)
    assert len(findings) == 1
    assert findings[0]["status"] == "READABLE"
    assert findings[0]["contest_id"] == "195384501"
    assert findings[0]["observed_field_size"] == 4
    assert not list(tmp_path.glob("normalized/**/*.csv"))
