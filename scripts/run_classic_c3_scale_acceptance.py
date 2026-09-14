"""Run one registered C3 full-fixture scale in an isolated short directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nfl_dfs.classic_scale_acceptance import run_classic_c3_scale_acceptance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entries", type=int, required=True, choices=(1, 3, 20, 150))
    parser.add_argument("--work-root", required=True)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--limits")
    args = parser.parse_args()
    report = run_classic_c3_scale_acceptance(
        repo_root=args.repo_root,
        work_root=args.work_root,
        entry_count=args.entries,
        limits_path=args.limits,
    )
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
