from __future__ import annotations

from pathlib import Path

import pytest

from nfl_dfs.byte_lines import split_byte_lines
from nfl_dfs.dk import parse_entries
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
