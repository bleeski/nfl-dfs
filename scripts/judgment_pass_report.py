"""Print the Classic judgment pass of a `run-slate` result as the handoff text (Session 61, R37).

    python scripts/judgment_pass_report.py <cowork_run.json | classic_complete_slate_coverage.json>

Reads the pass the run already wrote (`prior_review_reports.selection.judgment_pass`, or the
coverage artifact's `judgment_pass`) and the construction judgment's decision beside it. A pure
view: nothing is recomputed, no file is written, and no number is invented. `--json` prints the
pass block itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nfl_dfs.classic_judgment import render_judgment_pass_text  # noqa: E402


def _blocks(document: dict) -> tuple[dict | None, dict | None]:
    reports = document.get("prior_review_reports")
    selection = reports.get("selection") if isinstance(reports, dict) else None
    if isinstance(selection, dict) and isinstance(selection.get("judgment_pass"), dict):
        decision = reports.get("construction_judgment") or selection.get("selection", {}).get("construction_judgment")
        return selection["judgment_pass"], decision
    if isinstance(document.get("judgment_pass"), dict):
        return document["judgment_pass"], document.get("construction_judgment")
    return None, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", help="a run-slate cowork_run.json, or a Classic complete-slate coverage JSON")
    parser.add_argument("--json", action="store_true", help="print the pass block as JSON")
    args = parser.parse_args(argv)
    document = json.loads(Path(args.path).read_text(encoding="utf-8"))
    block, decision = _blocks(document)
    if block is None:
        print("no judgment_pass in this file: it is not a Classic run from Session 61 on", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"judgment_pass": block, "construction_judgment": decision}, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_judgment_pass_text(block, decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
