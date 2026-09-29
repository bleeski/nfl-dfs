#!/usr/bin/env python3
"""Move the DraftKings standings corpus between Ben's machine and a cloud session (Session 17, X2).

Two subcommands:

``manifest``  On the machine that holds the exports. Hashes ``data/standings/inbox/`` into the
              committed manifest ``config/standings_corpus_manifest_v1.json`` and prints the upload
              commands. Reads the inbox; never writes, renames or deletes there.
``fetch``     In any session, cloud included. Brings every file in the manifest into the inbox from the
              private release, verified against the manifest's sha256 and byte count, never replacing
              a file already there, and writes a transport record under ``data/standings/transport/``.

Boundaries, unchanged from ``CLAUDE.md``: nothing here contacts DraftKings (the exports are Ben's own
downloads), the credential is read from the environment (``NFL_DFS_GITHUB_TOKEN``, ``GH_TOKEN``, then
``GITHUB_TOKEN``) and is never printed, and a file that does not match the manifest is refused.

Exit codes: 0 every file bound; 1 at least one file refused (see the per-file lines); 2 the run itself
was refused (credential, manifest, repository visibility, network).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from nfl_dfs import sources, standings_transport
except ModuleNotFoundError:  # pragma: no cover - environment guard
    sys.exit(
        "nfl_dfs is not importable. Run this with the project's own interpreter, "
        "not a bare system python3:\n"
        "  Windows:      .venv\\Scripts\\python.exe scripts\\fetch_standings_corpus.py\n"
        "  Linux: .venv-linux/bin/python scripts/fetch_standings_corpus.py"
    )

DEFAULT_INBOX = REPO_ROOT / "data" / "standings" / "inbox"
DEFAULT_MANIFEST = REPO_ROOT / "config" / "standings_corpus_manifest_v1.json"
DEFAULT_RECORD_DIR = REPO_ROOT / "data" / "standings" / "transport"
DEFAULT_TAG = "standings-corpus-v1"


def _manifest(args: argparse.Namespace) -> int:
    payload = standings_transport.build_manifest(args.inbox, repository=args.repo, release_tag=args.tag)
    target = standings_transport.write_manifest(payload, args.out)
    total = sum(entry["byte_count"] for entry in payload["files"])
    print(f"manifest: {len(payload['files'])} files, {total} bytes -> {target}")
    for entry in payload["files"]:
        print(f"  {entry['sha256']}  {entry['byte_count']:>10}  {entry['name']}")
    print(
        f"\nNext: check that {args.repo} is a PRIVATE repository (the exports hold DraftKings usernames),\n"
        f"create its release {args.tag}, and attach these files plus nothing else. With the gh CLI:\n"
        f"  gh release create {args.tag} --repo {args.repo} --title {args.tag} --notes 'standings corpus'\n"
        f"  gh release upload {args.tag} --repo {args.repo} <each file in {args.inbox}>\n"
        "Then commit the manifest through a pull request."
    )
    return 0


def _fetch(args: argparse.Namespace) -> int:
    record = standings_transport.fetch_corpus(
        args.manifest,
        inbox_dir=args.inbox,
        record_dir=args.record_dir,
        repository=args.repo,
        allow_public_repository=args.allow_public_repository,
    )
    payload = record.payload
    for row in payload["files"]:
        detail = row["code"] or ""
        print(f"{row['disposition']:<15} {row['name']}  {detail}".rstrip())
    counts = payload["counts"]
    print(
        f"{counts['fetched']} fetched, {counts['already_present']} already present, {counts['refused']} refused; "
        f"record: {record.record_path}"
    )
    if payload["repository_private"] is False:
        print("WARNING: the repository is public; the override was recorded.", file=sys.stderr)
    return 0 if record.all_bound else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("manifest", help="hash the inbox into the committed manifest")
    build.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    build.add_argument("--out", type=Path, default=DEFAULT_MANIFEST)
    build.add_argument("--repo", required=True, help="owner/name of the PRIVATE repository holding the release")
    build.add_argument("--tag", default=DEFAULT_TAG)
    build.set_defaults(run=_manifest)

    fetch = sub.add_parser("fetch", help="bring the corpus into the inbox from the private release")
    fetch.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    fetch.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    fetch.add_argument("--record-dir", type=Path, default=DEFAULT_RECORD_DIR)
    fetch.add_argument("--repo", default=None, help="override the manifest's owner/name")
    fetch.add_argument(
        "--allow-public-repository",
        action="store_true",
        help="fetch from a public repository anyway; recorded in the transport record",
    )
    fetch.set_defaults(run=_fetch)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (standings_transport.StandingsTransportError, sources.AuthenticatedFetchError) as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
