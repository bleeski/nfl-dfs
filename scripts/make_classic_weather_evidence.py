#!/usr/bin/env python3
"""Assemble the `nfl_classic_weather_evidence_c1_v1` package a Classic run needs.

Standard library only, and it never touches the network. It formats captures the
operator already took: one saved `api.weather.gov` gridpoint forecast response
per game on the slate. The Classic weather gate demands the exact complete game
set, a content-addressed copy of every capture, the capture's own observation
time, and an unexpired six-hour window, so hand-writing this JSON for a
thirteen-game slate is where a run gets lost.

What it does:

* reads the DraftKings Classic salary CSV, so every `game_id` and the salary
  SHA-256 come from the exact bytes the run will bind rather than from typing;
* copies each capture to `<out-dir>/sources/<sha256><ext>`, the layout
  `prior_review` re-validates;
* reads `properties.generatedAt` out of each forecast for `observed_at`, so the
  observation time is the forecast's own, never the time you ran this;
* writes `weather_evidence.json` next to that `sources/` directory.

What it does not do: fetch, verify, or vouch for any capture. `source_uri` is
the operator's statement of where the bytes came from, and the run re-checks its
shape, host policy, hashes and freshness, not its truth.

The plan file names one entry per game, keyed by the home team abbreviation as
DraftKings spells it (or by the exact `game_id`):

    {
      "CAR": {
        "source_uri": "https://api.weather.gov/gridpoints/GSP/117,60/forecast",
        "path": "captures/car.json"
      },
      "HOU": {
        "source_uri": "https://api.weather.gov/gridpoints/HGX/66,97/forecast",
        "path": "captures/hou.json",
        "weather_state": "CLEAR"
      }
    }

`weather_state` is only read for a roof the frozen schedule cannot resolve; a
`dome` or `closed` roof stays schedule-derived so the two can never disagree,
and an `outdoors` roof reports the capture without letting it override the
schedule. Supply it when the run reports `WEATHER_STATE_REQUIRED`.

Example:

    python scripts/make_classic_weather_evidence.py \\
        --salaries DKSalaries.csv \\
        --plan weather_plan.json \\
        --out-dir data/runs/20260913-classic-main/weather
"""

from __future__ import annotations

import argparse
import csv
import json
import hashlib
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED_HOST = "api.weather.gov"
SCHEMA = "nfl_classic_weather_evidence_c1_v1"
WEATHER_STATES = ("CLEAR", "INDOOR_OR_CLEAR", "MIXED", "RAIN", "SNOW", "WIND")
EXPIRY = timedelta(hours=6)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_games(path: Path) -> "dict[str, str]":
    """Return {home_team: game_id} from the exact salary bytes.

    The engine's `game_id` is the `AWAY@HOME` matchup alone, not the whole
    `Game Info` cell, which also carries the kickoff. Deriving it here is the
    reason this script exists: the weather gate compares the exact complete game
    set and says nothing helpful about a near miss.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"salary CSV has no rows: {path}")
    games: dict[str, str] = {}
    for row in rows:
        info = (row.get("Game Info") or "").strip()
        if not info:
            continue
        game_id = info.split()[0]
        if "@" not in game_id:
            raise SystemExit(f"unrecognized Game Info, expected AWAY@HOME: {info!r}")
        home = game_id.split("@", 1)[1].strip()
        previous = games.get(home)
        if previous is not None and previous != game_id:
            raise SystemExit(
                f"{home} appears in two games ({previous!r} and {game_id!r}); key the "
                "plan by exact game_id instead of home team"
            )
        games[home] = game_id
    if not games:
        raise SystemExit(f"no Game Info values in {path}")
    return games


def _observed_at(capture: Path) -> datetime:
    try:
        payload = json.loads(capture.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"capture is not readable JSON: {capture}: {exc}") from exc
    properties = payload.get("properties")
    generated = None
    if isinstance(properties, dict):
        generated = properties.get("generatedAt") or properties.get("updateTime")
    if not generated:
        raise SystemExit(
            f"capture has no properties.generatedAt: {capture}. Save the whole "
            "gridpoint forecast response, not an excerpt."
        )
    moment = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise SystemExit(f"generatedAt has no timezone: {capture}")
    return moment.astimezone(timezone.utc)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salaries", required=True)
    parser.add_argument("--plan", required=True, help="JSON keyed by home team or game_id")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--captured-at",
        default="now",
        help="ISO 8601 with offset, or 'now'. When you read the forecasts.",
    )
    parser.add_argument("--license-decision", default="PUBLIC_DOMAIN")
    parser.add_argument("--parser-version", default="nws_gridpoint_forecast_v1")
    args = parser.parse_args(argv)

    salary_path = Path(args.salaries).resolve()
    plan_path = Path(args.plan).resolve()
    out_dir = Path(args.out_dir).resolve()
    sources_dir = out_dir / "sources"

    games_by_home = _read_games(salary_path)
    expected = set(games_by_home.values())
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise SystemExit("plan must be a JSON object keyed by home team or game_id")

    captured_at = (
        datetime.now(timezone.utc).replace(microsecond=0)
        if args.captured_at.strip().lower() == "now"
        else datetime.fromisoformat(args.captured_at.strip().replace("Z", "+00:00"))
    )
    if captured_at.tzinfo is None:
        raise SystemExit("--captured-at must carry a timezone offset")
    captured_at = captured_at.astimezone(timezone.utc)
    expires_at = captured_at + EXPIRY

    resolved: dict[str, dict] = {}
    for key, raw in plan.items():
        if not isinstance(raw, dict):
            raise SystemExit(f"plan entry {key!r} must be an object")
        game_id = games_by_home.get(str(key).strip(), str(key).strip())
        if game_id not in expected:
            raise SystemExit(
                f"plan entry {key!r} does not name a game on this slate. "
                f"slate games: {sorted(expected)}"
            )
        if game_id in resolved:
            raise SystemExit(f"two plan entries resolve to the same game: {game_id!r}")

        source_uri = str(raw.get("source_uri") or "").strip()
        host = urlsplit(source_uri).hostname or ""
        if urlsplit(source_uri).scheme != "https" or host != ALLOWED_HOST:
            raise SystemExit(
                f"{key}: source_uri must be an https://{ALLOWED_HOST} URL, got {source_uri!r}"
            )

        capture = Path(str(raw.get("path") or "")).expanduser()
        if not capture.is_absolute():
            capture = (plan_path.parent / capture).resolve()
        if not capture.is_file():
            raise SystemExit(f"{key}: capture file not found: {capture}")

        state = str(raw.get("weather_state") or "").strip().upper()
        if state and state not in WEATHER_STATES:
            raise SystemExit(
                f"{key}: weather_state must be one of {list(WEATHER_STATES)}, got {state!r}"
            )

        observed = _observed_at(capture)
        if observed > captured_at:
            raise SystemExit(
                f"{key}: forecast generatedAt {observed.isoformat()} is after "
                f"--captured-at {captured_at.isoformat()}"
            )

        digest = _sha256(capture)
        stored = sources_dir / f"{digest}{capture.suffix or '.json'}"
        resolved[game_id] = {
            "capture": capture,
            "stored": stored,
            "sha256": digest,
            "source_uri": source_uri,
            "weather_state": state,
            "observed_at": observed,
        }

    missing = sorted(expected.difference(resolved))
    if missing:
        raise SystemExit(
            "the weather package must cover the exact complete game set; missing:\n  "
            + "\n  ".join(missing)
        )

    sources_dir.mkdir(parents=True, exist_ok=True)
    games_payload: dict[str, dict] = {}
    for game_id, item in sorted(resolved.items()):
        if not item["stored"].exists():
            shutil.copyfile(item["capture"], item["stored"])
        if _sha256(item["stored"]) != item["sha256"]:
            raise SystemExit(f"{game_id}: stored capture does not match its hash")
        entry = {
            "path": item["stored"].relative_to(out_dir).as_posix(),
            "sha256": item["sha256"],
            "source_uri": item["source_uri"],
            "license_decision": args.license_decision,
            "parser_version": args.parser_version,
            "observed_at": item["observed_at"].isoformat(),
            "captured_at": captured_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        if item["weather_state"]:
            entry["weather_state"] = item["weather_state"]
        games_payload[game_id] = entry

    payload = {
        "schema_version": SCHEMA,
        "salary_sha256": _sha256(salary_path),
        "games": games_payload,
    }
    out_path = out_dir / "weather_evidence.json"
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    oldest = min(item["observed_at"] for item in resolved.values())
    print(f"wrote {out_path}")
    print(f"games covered:   {len(games_payload)}")
    print(f"oldest forecast: {oldest.isoformat()}")
    print(f"expires at:      {expires_at.isoformat()}")
    print(
        "pass it to the run as --weather-evidence-json; rerun with fresh captures "
        "if the slate locks after that expiry."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
