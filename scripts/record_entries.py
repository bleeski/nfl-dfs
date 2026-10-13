#!/usr/bin/env python3
"""Write the per-Entry-ID build record of one delivered DraftKings file (Session 72, `nfl_entry_build_record_v1`).

    python scripts/record_entries.py --salaries <DKSalaries.csv> --entries <DKEntries.csv> --file <delivered.csv> \
        (--scores <pool_scores.json> | --portfolio <portfolio record.json>) \
        --out data/inbox/slates/<slug>/construction/entry_build_record.jsonl

One row per Entry ID of the template: the roster by exact DraftKings ID, the prior from the one named source, its rank in the
file, the structure counts, DraftKings status flags and the later-window count. The run's fields (method, rung, policy, thesis,
market numbers) are null until Session 72b reads a run folder. The record is written once: the same bytes again are
`ALREADY_PRESENT`, and anything else holding the name is refused, never replaced.

Exit 0 with a one-line JSON summary on stdout (rows, state, the record's SHA-256); exit 2 with `REFUSED <code>: <detail>` on
stderr and nothing written. It certifies nothing: MODEL_STATUS=PRIOR_ONLY, RELEASE_DECISION=DO_NOT_UPLOAD.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nfl_dfs.entry_record import EntryRecordRefused, build_records, record_bytes, write_record
from nfl_dfs.hashing import sha256_bytes

EXIT_OK, EXIT_REFUSED = 0, 2
REPO_ROOT = Path(__file__).resolve().parent.parent
# Immutable snapshots (CLAUDE.md): a record never lands inside one.
SNAPSHOT_ROOTS = ("data/runs", "data/standings", "tests/fixtures/supplied")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--salaries", required=True, help="the DraftKings salary CSV the file was built against")
    parser.add_argument("--entries", required=True, help="the DKEntries template: the Entry IDs the record may name")
    parser.add_argument("--file", required=True, help="the delivered file, an engine output or a hand-edited one")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--scores", help="the run's pool-score dump (nfl_prior_pool_scores_v1)")
    source.add_argument("--portfolio", help="a portfolio record with each Entry ID's roster and prior_points")
    parser.add_argument("--out", required=True, help="where the record is written, once")
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    for root in SNAPSHOT_ROOTS:
        if out.is_relative_to(REPO_ROOT / root):
            parser.error(f"--out may not be inside {root}/ (immutable snapshots); write beside the slate's construction records")
    try:
        rows = build_records(args.salaries, args.entries, args.file, scores=args.scores, portfolio=args.portfolio)
        data = record_bytes(rows)
        state = write_record(args.out, data)
    except EntryRecordRefused as refusal:
        print(f"REFUSED {refusal.code}: {refusal.detail}", file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps({"rows": len(rows), "state": state, "sha256": sha256_bytes(data)}, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
