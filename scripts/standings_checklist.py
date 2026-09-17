#!/usr/bin/env python3
"""Standings pull checklist for nfl-dfs.

Reports which DraftKings contests Ben has already entered — recovered from
reserved-entry CSVs, principally the immutable snapshots Cowork writes under
``data/runs/*/inputs/`` but also loose `DKEntries*`/`DK_REVIEW_ENTRY*` CSVs
left in the repo root or `Claude outputs/` when a slate was built outside a
full `cowork-run` intake — but has no raw contest-standings export yet in
``data/standings/inbox/``.

This is a logistics tool only:

- It never fetches DraftKings. Ben pulls every export himself (My Contests ->
  History -> the contest -> Export) and drops the file, unmodified, into
  ``data/standings/inbox/``. The rendered checklist does emit one export URL
  per contest, built from a Contest ID that came out of his own entry CSV, so
  that the pull is one click instead of six; the click is still his, in his
  own logged-in browser. Nothing here requests DraftKings.
- It never files, archives, or scores anything. It only reports coverage.
- It is not the same thing as ``nfl.sh settle``, which needs the fully
  normalized, complete-field ``nfl_standings_csv_v2`` artifact
  (``EntryId,Rank,Points,Prize,Lineup``) documented in
  ``docs/DATA_CONTRACTS.md``. A raw DraftKings export landing in the inbox
  does not by itself satisfy that contract. This tool only tracks whether
  *any* raw export has been pulled for a contest at all.
- Every source it reads is read-only from here (``data/runs/``, the repo
  root, ``Claude outputs/``). A contest ID is discovered by reusing
  ``nfl_dfs.dk.parse_entries`` on each candidate CSV and keeping the ones
  that parse as a reserved-entry template (a salary CSV fails that parse and
  is silently skipped) — the same parser the engine itself uses, so this
  tool and the engine can never disagree about what counts as an entered
  contest. A hit under ``data/runs/*/inputs/`` is tagged ``confidence:
  snapshot`` (immutable, hash-bound); a hit only in the repo root or
  ``Claude outputs/`` is tagged ``confidence: loose`` (real, but not
  hash-bound — the file could still be edited or deleted by hand).

Usage:

    python3 scripts/standings_checklist.py                 # regenerate the .md + the clickable checklist
    python3 scripts/standings_checklist.py --json          # machine-readable, writes nothing
    python3 scripts/standings_checklist.py --mark-unrecoverable CONTEST_ID "reason"
    python3 scripts/standings_checklist.py --mark-placeholder CONTEST_ID "reason"
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from nfl_dfs.dk import DraftKingsParseError, parse_entries
except ImportError:
    sys.exit(
        "nfl_dfs is not importable. Run this with the project's own interpreter, "
        "not a bare system python3:\n"
        "  Linux: .venv-linux/bin/python scripts/standings_checklist.py\n"
        "  Windows:      .venv\\Scripts\\python.exe scripts\\standings_checklist.py\n"
        "If neither venv exists yet, run `sh ./nfl.sh setup` (Cowork) first."
    )

RUNS_DIR = REPO_ROOT / "data" / "runs"
STANDINGS_DIR = REPO_ROOT / "data" / "standings"
INBOX_DIR = STANDINGS_DIR / "inbox"
NORMALIZED_DIR = STANDINGS_DIR / "normalized"
SETTLEMENTS_DIR = REPO_ROOT / "outputs" / "settlements"
DISPOSITIONS_PATH = STANDINGS_DIR / "dispositions.json"
MARKDOWN_PATH = STANDINGS_DIR / "CONTESTS_AWAITING_STANDINGS.md"
HTML_PATH = STANDINGS_DIR / "CONTESTS_AWAITING_STANDINGS.html"

# DraftKings' own standings export for one contest. This tool only ever
# *writes the string*; the fetch is Ben clicking it in his own logged-in
# browser, which is the same manual action CLAUDE.md already requires. The
# contest ID comes from his own entry CSV, never from a DraftKings request.
DK_EXPORT_URL = "https://www.draftkings.com/contest/exportfullstandingscsv/{contest_id}"

_RUN_DATE_RE = re.compile(r"20\d{6}")
UNKNOWN_DATE = "date unknown"


def dated_html_path(report_date: str) -> Path:
    """Per-run checklist, mirroring mlb-dfs's ``standings_pulls_<date>.html``."""
    return STANDINGS_DIR / f"standings_pulls_{report_date}.html"

_CONTEST_ID_RE = re.compile(r"\d{5,}")
_VALID_DISPOSITIONS = ("unrecoverable", "placeholder")


class ChecklistError(ValueError):
    pass


@dataclass
class ContestRecord:
    contest_id: str
    contest_name: str
    mode: str
    entry_fee: float
    entry_ids: set[str] = field(default_factory=set)
    provenance: set[str] = field(default_factory=set)
    confidence: str = "loose"  # "snapshot" once any provenance is a data/runs hit
    evidence_dates: set[str] = field(default_factory=set)


def _provenance_for(csv_path: Path) -> tuple[str, bool]:
    """Return a (label, is_immutable_snapshot) pair for a discovered CSV.

    ``data/runs/<run_id>/inputs/<file>.csv`` is Cowork's own hash-bound,
    never-overwritten snapshot and is treated as authoritative ("snapshot").
    Anything else this tool looks at — a loose ``DKEntries_*.csv`` left in the
    repo root, or a copy under ``Claude outputs/`` — is real but not
    immutable: it could have been hand-edited or replaced after the fact, so
    it is labelled "loose" and called out separately rather than silently
    trusted at the same level.
    """
    try:
        relative = csv_path.relative_to(RUNS_DIR)
        return f"run:{relative.parts[0]}", True
    except ValueError:
        pass
    try:
        relative = csv_path.relative_to(REPO_ROOT)
    except ValueError:
        relative = csv_path
    return f"loose:{relative.as_posix()}", False


def _evidence_date_for(csv_path: Path) -> str:
    """Best available date for one piece of evidence, as ``YYYY-MM-DD``.

    A ``data/runs/`` snapshot carries its own date in the run ID
    (``20260913T161138Z-week1-portfolio``), which is the date the slate was
    actually operated. Anything else falls back to the file's own
    modification time. Neither is DraftKings' contest date, which the entry
    CSV does not contain: this is a proxy, and the rendered outputs say so.
    """
    try:
        run_id = csv_path.relative_to(RUNS_DIR).parts[0]
    except ValueError:
        run_id = ""
    for candidate in _RUN_DATE_RE.findall(run_id):
        try:
            return datetime.strptime(candidate, "%Y%m%d").date().isoformat()
        except ValueError:
            continue
    try:
        mtime = csv_path.stat().st_mtime
    except OSError:
        return UNKNOWN_DATE
    # Local, not UTC: a file written at 7pm Central on a Sunday slate is a
    # Sunday file to Ben, and grouping it under Monday would put it in the
    # wrong bucket. Run IDs are already UTC-stamped and parsed as written.
    return datetime.fromtimestamp(mtime).date().isoformat()


def group_by_evidence_date(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group rows by evidence date, oldest first, unknown dates last.

    Oldest first on purpose: a DraftKings standings export ages out some
    days after the contest settles, so the oldest unpulled contests are the
    ones at risk, not the newest.
    """
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row.get("evidence_date") or UNKNOWN_DATE, []).append(row)
    return [
        (key, sorted(bucket, key=lambda r: r["contest_id"]))
        for key, bucket in sorted(
            buckets.items(), key=lambda kv: (kv[0] == UNKNOWN_DATE, kv[0])
        )
    ]


def _candidate_csv_paths() -> list[Path]:
    """Every CSV this tool is willing to try as a reserved-entry template.

    The canonical source is ``data/runs/*/inputs/*.csv`` — every immutable
    snapshot Cowork's own intake step writes. This repo's actual history
    (see the 2026-09-13 retrospectives) also has at least one live slate
    built through emergency scripts under a lock clock rather than a full
    `cowork-run` intake, so its reserved-entry file may only ever have
    existed as a loose CSV in the repo root or in `Claude outputs/`. Both are
    scanned too, at lower confidence (see `_provenance_for`), rather than
    silently missing a contest the canonical path never captured.
    """
    seen: set[Path] = set()
    paths: list[Path] = []
    globs = []
    if RUNS_DIR.is_dir():
        globs.append(RUNS_DIR.glob("*/inputs/*.csv"))
    if REPO_ROOT.is_dir():
        globs.append(REPO_ROOT.glob("*.csv"))
    claude_outputs = REPO_ROOT / "Claude outputs"
    if claude_outputs.is_dir():
        globs.append(claude_outputs.glob("*.csv"))
    for group in globs:
        for path in sorted(group):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return paths


def discover_entered_contests() -> dict[str, ContestRecord]:
    """Recover every entered contest this tool can find evidence for.

    Reuses ``nfl_dfs.dk.parse_entries`` — the exact parser the engine runs at
    intake — so a file this tool counts as an entered contest is, by
    construction, the same thing the engine would accept as one. A CSV that
    is not a reserved-entry template (a salary file, an official-status
    file, a readable-review JSON's CSV sibling, etc.) raises
    ``DraftKingsParseError`` and is skipped rather than guessed at.

    One repo limitation carries through unchanged: the engine only accepts a
    reserved-entry file bound to a single Contest ID and entry fee
    (``MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED``), so if Ben entered the same
    lineups into several DraftKings contests but only ever ran one of them
    through Cowork, only the contests actually fed to the engine as their own
    run — or left behind as their own loose CSV — show up here. This tool
    cannot see a contest that produced no CSV anywhere it looks.
    """
    contests: dict[str, ContestRecord] = {}
    for csv_path in _candidate_csv_paths():
        try:
            template = parse_entries(csv_path)
        except DraftKingsParseError:
            continue
        provenance, is_snapshot = _provenance_for(csv_path)
        evidence_date = _evidence_date_for(csv_path)
        by_contest: dict[str, list] = {}
        for auth in template.authorizations:
            by_contest.setdefault(auth.contest_id, []).append(auth)
        for contest_id, auths in by_contest.items():
            record = contests.get(contest_id)
            if record is None:
                record = ContestRecord(
                    contest_id=contest_id,
                    contest_name=auths[0].contest_name,
                    mode=template.mode.value,
                    entry_fee=auths[0].entry_fee,
                )
                contests[contest_id] = record
            record.entry_ids.update(a.entry_id for a in auths)
            record.provenance.add(provenance)
            record.evidence_dates.add(evidence_date)
            if is_snapshot:
                record.confidence = "snapshot"
    return contests


def load_dispositions() -> dict[str, dict]:
    if not DISPOSITIONS_PATH.is_file():
        return {}
    raw = json.loads(DISPOSITIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ChecklistError(f"{DISPOSITIONS_PATH} must contain a JSON object")
    return raw


def save_dispositions(dispositions: dict[str, dict]) -> None:
    STANDINGS_DIR.mkdir(parents=True, exist_ok=True)
    DISPOSITIONS_PATH.write_text(
        json.dumps(dispositions, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def filed_contest_ids() -> set[str]:
    """Contest IDs with at least one raw export already sitting in the inbox.

    The inbox is flat by convention (matching the mlb-dfs and golf-dfs
    analogs) — never sort it into per-contest or per-mode subfolders. A
    DraftKings standings export filename normally embeds the Contest ID
    (``contest-standings-<contest_id>.zip`` or ``.csv``); this matches any
    digit run of five or more characters found anywhere in the filename.
    """
    if not INBOX_DIR.is_dir():
        return set()
    found: set[str] = set()
    for entry in sorted(INBOX_DIR.iterdir()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        found.update(_CONTEST_ID_RE.findall(entry.name))
    return found


def normalized_contest_ids() -> set[str]:
    """Contest IDs with at least one ``nfl_standings_csv_v2`` on disk.

    Filed and normalized are different states and were collapsed before Q1B: a
    raw DraftKings export in the inbox satisfies nothing downstream on its own,
    because it carries no prize column and names its lineups. Only
    ``scripts/file_standings.py`` produces the contract artifact, under
    ``data/standings/normalized/<contest_id>/<sha256>.csv``.
    """
    if not NORMALIZED_DIR.is_dir():
        return set()
    return {
        child.name
        for child in sorted(NORMALIZED_DIR.iterdir())
        if child.is_dir() and any(child.glob("*.csv"))
    }


def settled_contest_ids() -> set[str]:
    """Contest IDs with a complete Q1 settlement bundle.

    A bundle is the only thing that means the contest actually entered the
    validation corpus. It is found by reading each package's own
    ``settlement_bundle.json`` rather than by trusting a directory name, so a
    half-written or hand-made folder does not count as settled.
    """
    if not SETTLEMENTS_DIR.is_dir():
        return set()
    found: set[str] = set()
    for package in sorted(SETTLEMENTS_DIR.iterdir()):
        bundle = package / "settlement_bundle.json"
        if not bundle.is_file():
            continue
        try:
            payload = json.loads(bundle.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        contest = payload.get("contest") if isinstance(payload, dict) else None
        if isinstance(contest, dict) and contest.get("contest_id"):
            found.add(str(contest["contest_id"]))
    return found


def _newest_date(dates: set[str]) -> str:
    """The most recent real date seen for a contest, else ``UNKNOWN_DATE``.

    Newest rather than oldest: an early acceptance-test run can reference a
    real contest weeks before it was played, so the latest evidence is the
    closer proxy for when the contest actually ran.
    """
    real = sorted(d for d in dates if d != UNKNOWN_DATE)
    return real[-1] if real else UNKNOWN_DATE


def build_report() -> dict:
    contests = discover_entered_contests()
    dispositions = load_dispositions()
    filed = filed_contest_ids()
    normalized = normalized_contest_ids()
    settled = settled_contest_ids()
    rows = []
    for contest_id, record in sorted(contests.items()):
        disposition = dispositions.get(contest_id)
        # Most-advanced state wins, and a real settlement outranks a
        # disposition: a contest that actually settled is settled, whatever was
        # recorded about it earlier. Below that, an explicit disposition is Ben's
        # ruling and outranks the file states it was made in spite of.
        if contest_id in settled:
            status, reason = "settled", None
        elif disposition:
            status = disposition["status"]
            reason = disposition.get("reason")
        elif contest_id in normalized:
            status, reason = "normalized", None
        elif contest_id in filed:
            status, reason = "filed", None
        else:
            status, reason = "awaiting", None
        rows.append(
            {
                "contest_id": contest_id,
                "contest_name": record.contest_name,
                "mode": record.mode,
                "entry_fee": record.entry_fee,
                "entries": len(record.entry_ids),
                "confidence": record.confidence,
                "evidence_date": _newest_date(record.evidence_dates),
                "provenance": sorted(record.provenance),
                "status": status,
                "disposition_reason": reason,
                # Independent of status on purpose. A disposition is a ruling
                # about workflow, not a claim that the bytes are gone: a
                # dispositioned contest whose raw export is safely filed and
                # normalized is a different situation from one with nothing on
                # disk, and collapsing them would hide real preserved evidence.
                "raw_export_filed": contest_id in filed,
                "normalized_artifact": contest_id in normalized,
                "settlement_bundle": contest_id in settled,
            }
        )
    unresolved_inbox = sorted(filed - set(contests))
    counts = {
        "awaiting": sum(1 for r in rows if r["status"] == "awaiting"),
        "filed": sum(1 for r in rows if r["status"] == "filed"),
        "normalized": sum(1 for r in rows if r["status"] == "normalized"),
        "settled": sum(1 for r in rows if r["status"] == "settled"),
        "dispositioned": sum(
            1 for r in rows if r["status"] in _VALID_DISPOSITIONS
        ),
        "loose_only": sum(1 for r in rows if r["confidence"] == "loose"),
        "raw_exports_filed": sum(1 for r in rows if r["raw_export_filed"]),
        "normalized_artifacts": sum(1 for r in rows if r["normalized_artifact"]),
        "settlement_bundles": sum(1 for r in rows if r["settlement_bundle"]),
        "total_entered_contests": len(rows),
        "unresolved_inbox_files": len(unresolved_inbox),
    }
    generated_at = datetime.now(timezone.utc)
    return {
        "generated_at": generated_at.isoformat(),
        "report_date": generated_at.date().isoformat(),
        "counts": counts,
        "contests": rows,
        "unresolved_inbox_contest_ids": unresolved_inbox,
    }


def render_markdown(report: dict) -> str:
    counts = report["counts"]
    lines = [
        "# Contests awaiting standings",
        "",
        "Regenerated by `scripts/standings_checklist.py`. Do not edit by hand — "
        "rerun the tool instead, or use `--mark-unrecoverable` / "
        "`--mark-placeholder` to change a disposition.",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Awaiting: **{counts['awaiting']}** &middot; "
        f"Filed: **{counts['filed']}** &middot; "
        f"Normalized: **{counts['normalized']}** &middot; "
        f"Settled: **{counts['settled']}** &middot; "
        f"Dispositioned: **{counts['dispositioned']}** &middot; "
        f"Entered contests tracked: **{counts['total_entered_contests']}** "
        f"({counts['loose_only']} loose-only)",
        "",
        f"Raw exports on disk: **{counts['raw_exports_filed']}** &middot; "
        f"Normalized artifacts: **{counts['normalized_artifacts']}** &middot; "
        f"Settlement bundles: **{counts['settlement_bundles']}** "
        "(counted independently of status: a disposition is a ruling about "
        "workflow, not a claim that the bytes are gone)",
        "",
        "`awaiting` has no raw export; `filed` has a raw DraftKings export in "
        "`data/standings/inbox/`; `normalized` has an `nfl_standings_csv_v2` "
        "under `data/standings/normalized/`; `settled` has a complete Q1 "
        "settlement bundle. Filed is not normalized: a raw export carries no "
        "prize column and names its lineups, so it satisfies nothing downstream "
        "on its own. Only `settled` means the contest entered the validation "
        "corpus.",
        "",
    ]
    awaiting = [r for r in report["contests"] if r["status"] == "awaiting"]
    if awaiting:
        lines += ["## Awaiting a pull", "", "Oldest evidence date first.", ""]
        for date_key, bucket in group_by_evidence_date(awaiting):
            lines += [
                f"### {date_key} ({len(bucket)})",
                "",
                "| Contest ID | Contest | Mode | Fee | Entries | Confidence | Export | Source(s) |",
                "|---|---|---|---:|---:|---|---|---|",
            ]
            for r in bucket:
                url = DK_EXPORT_URL.format(contest_id=r['contest_id'])
                lines.append(
                    f"| {r['contest_id']} | {r['contest_name']} | {r['mode']} | "
                    f"${r['entry_fee']:.2f} | {r['entries']} | {r['confidence']} | "
                    f"[export]({url}) | {', '.join(r['provenance'])} |"
                )
            lines.append("")
    else:
        lines += ["No contests awaiting a pull.", ""]
    loose_only = [r for r in awaiting if r["confidence"] == "loose"]
    if loose_only:
        lines += [
            "`loose` means every source found for that contest was a repo-root "
            "or `Claude outputs/` CSV, not an immutable `data/runs/` snapshot — "
            "real, but not hash-bound, and worth a second look before treating "
            "the entry count as final.",
            "",
        ]
    other = [r for r in report["contests"] if r["status"] != "awaiting"]
    if other:
        lines += [
            "## Filed, normalized, settled or dispositioned",
            "",
            "| Contest ID | Contest | Status | Raw | Norm | Bundle | Reason |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in other:
            lines.append(
                f"| {r['contest_id']} | {r['contest_name']} | {r['status']} | "
                f"{'yes' if r['raw_export_filed'] else 'no'} | "
                f"{'yes' if r['normalized_artifact'] else 'no'} | "
                f"{'yes' if r['settlement_bundle'] else 'no'} | "
                f"{r['disposition_reason'] or ''} |"
            )
        lines.append("")
    if report["unresolved_inbox_contest_ids"]:
        lines += [
            "## Inbox files with no matching entered contest",
            "",
            "These filenames in `data/standings/inbox/` carry a digit run that "
            "does not match any contest ID recovered from an entered-contest "
            "CSV (`data/runs/`, the repo root, or `Claude outputs/`). Not a "
            "blocker — could be a contest run outside this repo, a renamed "
            "file, or a stale export. Named here rather than silently dropped:",
            "",
        ]
        lines += [f"- {contest_id}" for contest_id in report["unresolved_inbox_contest_ids"]]
        lines.append("")
    lines.append(
        "To pull one: DraftKings -> My Contests -> History -> the contest -> "
        "Export on the standings/leaderboard panel. Drop the file, unmodified, "
        "into `data/standings/inbox/` (flat — no per-contest or per-mode "
        "subfolders)."
    )
    return "\n".join(lines) + "\n"


def render_html(report: dict) -> str:
    """Render the clickable pull checklist.

    Deliberately the same working surface as the mlb-dfs checklist: one row
    per contest, grouped by evidence date with the oldest first, a checkbox
    per row, and an "Open export" link that opens DraftKings' own standings
    export for that contest **and** ticks the row off, so working the list is
    one click per contest instead of two.

    The link is a URL built from a Contest ID that came out of Ben's own
    entry CSV. Nothing here fetches DraftKings, reads account state, or sends
    a credential: the click happens in Ben's browser, in his own logged-in
    session, exactly as if he had walked My Contests -> History -> Export by
    hand. That is the same manual boundary CLAUDE.md draws for the whole
    repo, and this tool stays on the correct side of it.
    """
    counts = report["counts"]

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    awaiting = [r for r in report["contests"] if r["status"] == "awaiting"]
    other = [r for r in report["contests"] if r["status"] != "awaiting"]

    sections = []
    for date_key, rows in group_by_evidence_date(awaiting):
        items = []
        for row in rows:
            tags = [f"{esc(row['mode'])}", f"${row['entry_fee']:.2f}", f"{row['entries']}x"]
            if row["confidence"] == "loose":
                tags.append("loose")
            tag_html = "".join(
                f'<span class="tag{" loose" if tag == "loose" else ""}">{tag}</span>'
                for tag in tags
            )
            url = esc(DK_EXPORT_URL.format(contest_id=row["contest_id"]))
            items.append(
                '<li class="row">'
                '<label class="chk"><input type="checkbox"></label>'
                f'<span class="name">{esc(row["contest_name"])}<span class="tags">{tag_html}</span></span>'
                f'<span class="cid">{esc(row["contest_id"])}</span>'
                f'<a class="pull" href="{url}" target="_blank" rel="noopener">Open export &#8599;</a>'
                "</li>"
            )
        sections.append(
            "<section>"
            f'<h2>{esc(date_key)} <span class="count">({len(rows)} contest'
            f'{"s" if len(rows) != 1 else ""})</span></h2>'
            f'<ul class="rows">{"".join(items)}</ul>'
            "</section>"
        )
    sections_html = "".join(sections) or "<p class='empty'>Nothing awaiting a pull.</p>"

    other_html = ""
    if other:
        body = "".join(
            f"<tr><td class='cid'>{esc(r['contest_id'])}</td><td>{esc(r['contest_name'])}</td>"
            f"<td>{esc(r['status'])}</td>"
            f"<td>{'yes' if r['raw_export_filed'] else 'no'}</td>"
            f"<td>{'yes' if r['normalized_artifact'] else 'no'}</td>"
            f"<td>{'yes' if r['settlement_bundle'] else 'no'}</td>"
            f"<td>{esc(r['disposition_reason'] or '')}</td></tr>"
            for r in other
        )
        other_html = (
            "<section><h2>Filed, normalized, settled or dispositioned "
            f'<span class="count">({len(other)})</span></h2>'
            "<table><thead><tr><th>Contest ID</th><th>Contest</th><th>Status</th>"
            "<th>Raw</th><th>Norm</th><th>Bundle</th>"
            f"<th>Reason</th></tr></thead><tbody>{body}</tbody></table></section>"
        )

    loose_note = (
        f"<p class='note'><b>{counts['loose_only']}</b> of these were found only in a "
        "repo-root or <code>Claude outputs/</code> CSV, not an immutable "
        "<code>data/runs/</code> snapshot (tagged <span class='tag loose'>loose</span>). "
        "Real contests, but not hash-bound, so the entry count is worth a second look.</p>"
        if counts["loose_only"]
        else ""
    )

    inbox_ids = report["unresolved_inbox_contest_ids"]
    inbox_html = (
        "<section><h2>Inbox files with no matching entered contest</h2>"
        "<p class='note'>These filenames in <code>data/standings/inbox/</code> carry a "
        "digit run that matches no contest ID recovered from an entered-contest CSV. "
        "Not a blocker: could be a contest run outside this repo, a renamed file, or a "
        "stale export. Named rather than silently dropped.</p>"
        f"<p class='note'>{esc(', '.join(inbox_ids))}</p></section>"
        if inbox_ids
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NFL standings pulls needed &mdash; {esc(report['report_date'])}</title>
<style>
  :root {{
    --bg: #0f1115; --panel: #171a21; --border: #2a2e38;
    --text: #e6e8ec; --muted: #8b93a3; --accent: #4f8cff;
    --done-bg: #10241a; --done-text: #5fbd8a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 16px 80px;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: var(--muted); font-size: 14px; line-height: 1.5; margin: 0 0 24px; }}
  .sub b {{ color: var(--text); }}
  .sub code, .note code {{ background: var(--panel); padding: 1px 5px; border-radius: 4px; }}
  .progress {{
    position: sticky; top: 0; z-index: 5;
    background: var(--bg); padding: 8px 0 16px; font-size: 13px; color: var(--muted);
  }}
  #progressBar {{ height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; margin-top: 6px; }}
  #progressFill {{ height: 100%; width: 0%; background: var(--accent); transition: width .15s; }}
  section {{ margin-bottom: 28px; }}
  h2 {{
    font-size: 15px; border-bottom: 1px solid var(--border); padding-bottom: 6px;
    margin: 0 0 10px; display: flex; align-items: baseline; gap: 8px;
  }}
  h2 .count {{ color: var(--muted); font-weight: normal; font-size: 13px; }}
  ul.rows {{ list-style: none; margin: 0; padding: 0; }}
  li.row {{
    display: flex; align-items: center; gap: 10px;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 12px; margin-bottom: 6px;
    font-size: 13.5px;
  }}
  li.row.done {{ background: var(--done-bg); border-color: #1d3b2a; }}
  li.row.done .name {{ color: var(--done-text); text-decoration: line-through; }}
  .chk input {{ width: 16px; height: 16px; cursor: pointer; }}
  .name {{ flex: 1; min-width: 0; overflow-wrap: anywhere; }}
  .tags {{ display: inline-flex; gap: 5px; margin-left: 8px; vertical-align: middle; }}
  .tag {{
    color: var(--muted); border: 1px solid var(--border); border-radius: 4px;
    padding: 1px 5px; font-size: 11px; white-space: nowrap;
  }}
  .tag.loose {{ color: #d8a657; border-color: #4a3c22; }}
  .cid {{ color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; flex-shrink: 0; }}
  a.pull {{
    flex-shrink: 0; color: #fff; background: var(--accent); text-decoration: none;
    font-size: 12.5px; padding: 6px 10px; border-radius: 6px; white-space: nowrap;
  }}
  a.pull:hover {{ background: #3d78e6; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid var(--border); padding: 6px 8px; text-align: left; }}
  th {{ background: var(--panel); color: var(--muted); font-weight: 600; }}
  .note {{ color: var(--muted); font-size: 13px; line-height: 1.5; }}
  .empty {{ color: var(--muted); }}
</style>
</head>
<body>
<div class="wrap">
  <h1>NFL standings pulls needed</h1>
  <p class="sub">
    <b>{counts['awaiting']} contests</b> awaiting a pull; {counts['filed']} filed,
    {counts['normalized']} normalized, {counts['settled']} settled,
    {counts['dispositioned']} dispositioned, {counts['total_entered_contests']} entered
    contests tracked. Generated {esc(report['generated_at'])}.<br>
    Click <b>Open export</b> while logged into DraftKings; it opens the download and ticks
    the row off. Confirm the file is non-zero bytes, then drop it unmodified into
    <code>data/standings/inbox/</code> (flat &mdash; no subfolders). Oldest evidence date
    first: DK's export ages out after a contest settles, so those are the most at risk.
  </p>
  <div class="progress">
    <span id="progressLabel">0 / {counts['awaiting']} pulled</span>
    <div id="progressBar"><div id="progressFill"></div></div>
  </div>
{sections_html}
{loose_note}
{other_html}
{inbox_html}
  <p class="note">Evidence date is the newest date any entry file for that contest
  carries (a <code>data/runs/</code> snapshot ID, else the file's own modification
  date). It is this repo's best proxy for when the contest ran; DraftKings' own
  contest date is not in the entry CSV.</p>
</div>
<script>
  var rows = Array.prototype.slice.call(document.querySelectorAll('li.row'));
  var boxes = rows.map(function (row) {{ return row.querySelector('input[type=checkbox]'); }});
  var label = document.getElementById('progressLabel');
  var fill = document.getElementById('progressFill');
  function sync() {{
    var done = 0;
    rows.forEach(function (row, i) {{
      var on = boxes[i].checked;
      row.classList.toggle('done', on);
      if (on) {{ done += 1; }}
    }});
    label.textContent = done + ' / ' + rows.length + ' pulled';
    fill.style.width = (rows.length ? (100 * done / rows.length) : 0) + '%';
  }}
  rows.forEach(function (row, i) {{
    boxes[i].addEventListener('change', sync);
    var link = row.querySelector('a.pull');
    if (link) {{
      link.addEventListener('click', function () {{ boxes[i].checked = true; sync(); }});
    }}
  }});
  sync();
</script>
</body>
</html>
"""


def _mark(contest_id: str, status: str, reason: str) -> dict:
    if status not in _VALID_DISPOSITIONS:
        raise ChecklistError(f"unknown disposition: {status}")
    dispositions = load_dispositions()
    if contest_id in dispositions:
        raise ChecklistError(
            f"contest {contest_id} already has a disposition: {dispositions[contest_id]}. "
            f"Edit {DISPOSITIONS_PATH} by hand to change it."
        )
    dispositions[contest_id] = {
        "status": status,
        "reason": reason,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_dispositions(dispositions)
    return dispositions[contest_id]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--html",
        action="store_true",
        help="accepted for compatibility; the HTML checklist is always written",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON and write nothing")
    parser.add_argument("--mark-unrecoverable", nargs=2, metavar=("CONTEST_ID", "REASON"))
    parser.add_argument("--mark-placeholder", nargs=2, metavar=("CONTEST_ID", "REASON"))
    args = parser.parse_args(argv)

    try:
        if args.mark_unrecoverable and args.mark_placeholder:
            raise ChecklistError("use only one of --mark-unrecoverable or --mark-placeholder at a time")
        if args.mark_unrecoverable:
            contest_id, reason = args.mark_unrecoverable
            record = _mark(contest_id, "unrecoverable", reason)
            print(json.dumps({"contest_id": contest_id, **record}, indent=2))
            STANDINGS_DIR.mkdir(parents=True, exist_ok=True)
            MARKDOWN_PATH.write_text(render_markdown(build_report()), encoding="utf-8")
            print(f"Regenerated {MARKDOWN_PATH}")
            return 0
        if args.mark_placeholder:
            contest_id, reason = args.mark_placeholder
            record = _mark(contest_id, "placeholder", reason)
            print(json.dumps({"contest_id": contest_id, **record}, indent=2))
            STANDINGS_DIR.mkdir(parents=True, exist_ok=True)
            MARKDOWN_PATH.write_text(render_markdown(build_report()), encoding="utf-8")
            print(f"Regenerated {MARKDOWN_PATH}")
            return 0

        report = build_report()
        if args.json:
            print(json.dumps(report, indent=2))
            return 0

        STANDINGS_DIR.mkdir(parents=True, exist_ok=True)
        MARKDOWN_PATH.write_text(render_markdown(report), encoding="utf-8")
        print(f"Wrote {MARKDOWN_PATH}")
        rendered = render_html(report)
        dated = dated_html_path(report["report_date"])
        dated.write_text(rendered, encoding="utf-8")
        print(f"Wrote {dated}")
        HTML_PATH.write_text(rendered, encoding="utf-8")
        print(f"Wrote {HTML_PATH}")
        counts = report["counts"]
        print(
            f"awaiting={counts['awaiting']} filed={counts['filed']} "
            f"normalized={counts['normalized']} settled={counts['settled']} "
            f"raw_on_disk={counts['raw_exports_filed']} "
            f"normalized_artifacts={counts['normalized_artifacts']} "
            f"dispositioned={counts['dispositioned']} "
            f"total={counts['total_entered_contests']} "
            f"unresolved_inbox_files={counts['unresolved_inbox_files']}"
        )
        return 0
    except ChecklistError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
