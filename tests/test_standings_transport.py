"""X2 (Session 17): the standings corpus arrives through authenticated release-asset retrieval.

No network: every request goes through `httpx.MockTransport`, so the tests read the header each
request really carried after httpx's own merging. The real release does not exist yet (O1), so nothing
here says the real corpus was obtained; it says the transport keeps its bounds against a fixture.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from nfl_dfs import sources
from nfl_dfs import standings_transport as st
from nfl_dfs.hashing import sha256_bytes

SENTINEL = "ghp_SENTINEL0123456789abcdefTOKENVALUE"
SIGNED = "SIGNEDQUERYSECRET"
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
REPO = "bleeski/nfl-corpus"
TAG = "standings-corpus-v1"
ENV = {"GH_TOKEN": SENTINEL}
ASSET_URL = f"https://api.github.com/repos/{REPO}/releases/assets/7"
FILES = {
    "contest-standings-100001.csv": b"Rank,EntryId,EntryName\n1,1,a\n2,2,b\n",
    "contest-standings-100002.csv": b"Rank,EntryId,EntryName\n1,3,c\n",
    "contest-standings-100003.zip": b"PK\x03\x04not really a zip but bytes are bytes\n",
}


class FakeGithub:
    """A private repository with one release, answering the way GitHub does."""

    def __init__(self, files=FILES, *, private=True, mode="redirect"):
        self.files = dict(files)
        self.private = private
        self.mode = mode
        self.served: dict[str, bytes] = {}
        self.digests: dict[str, str] = {}
        self.sizes: dict[str, int] = {}
        self.hidden: set[str] = set()
        self.content_type = "application/octet-stream"
        self.log: list[dict] = []
        self.transport = httpx.MockTransport(self.handle)

    def assets(self):
        out = []
        for index, (name, data) in enumerate(sorted(self.files.items())):
            if name in self.hidden:
                continue
            out.append(
                {
                    "id": 500 + index,
                    "name": name,
                    "size": self.sizes.get(name, len(data)),
                    "digest": self.digests.get(name, "sha256:" + sha256_bytes(data)),
                    "url": "https://evil.example/never-followed",
                    "browser_download_url": "https://github.com/never-followed",
                }
            )
        return out

    def bytes_for(self, asset_id: int) -> bytes:
        name = sorted(self.files)[asset_id - 500]
        return self.served.get(name, self.files[name])

    def handle(self, request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization")
        self.log.append(
            {
                "host": request.url.host,
                "path": request.url.path,
                "query": request.url.query.decode(),
                "auth": auth,
                "user": request.url.userinfo,
            }
        )
        host, path = request.url.host, request.url.path
        if host == "api.github.com":
            if auth != f"Bearer {SENTINEL}":
                return httpx.Response(401, json={"message": "Bad credentials", "echo": str(auth)})
            base = f"/repos/{REPO}"
            if path == base:
                return httpx.Response(200, json={"full_name": REPO, "private": self.private})
            if path == f"{base}/releases/tags/{TAG}":
                return httpx.Response(200, json={"tag_name": TAG, "assets": self.assets()})
            if path.startswith(f"{base}/releases/assets/"):
                asset_id = int(path.rsplit("/", 1)[1])
                if self.mode == "direct":
                    return httpx.Response(
                        200, content=self.bytes_for(asset_id),
                        headers={"content-type": self.content_type},
                    )
                targets = {
                    "redirect": f"https://release-assets.githubusercontent.com/blob/{asset_id}?sig={SIGNED}",
                    "evil": f"https://evil.example/blob/{asset_id}?token={SIGNED}",
                    "draftkings": "https://www.draftkings.com/x",
                    "userinfo": "https://u:p@release-assets.githubusercontent.com/blob/1",
                    "api_moved": f"https://api.github.com/repositories/9/releases/assets/{asset_id}",
                    "double": f"https://release-assets.githubusercontent.com/hop/{asset_id}",
                }
                status = 301 if self.mode == "api_moved" else 302
                return httpx.Response(status, headers={"location": targets[self.mode]})
            return httpx.Response(404, json={"message": "Not Found"})
        if host == "release-assets.githubusercontent.com":
            if path.startswith("/hop/"):
                return httpx.Response(302, headers={"location": "https://objects.githubusercontent.com/again"})
            asset_id = int(path.rsplit("/", 1)[1])
            return httpx.Response(
                200, content=self.bytes_for(asset_id), headers={"content-type": self.content_type}
            )
        return httpx.Response(599, json={"message": "unexpected host"})

    def hosts(self) -> list[str]:
        return [entry["host"] for entry in self.log]


def _manifest(files=FILES, repository=REPO) -> dict:
    return {
        "schema_version": "nfl_standings_corpus_manifest_v1",
        "repository": repository,
        "release_tag": TAG,
        "files": [
            {"name": name, "sha256": sha256_bytes(data), "byte_count": len(data)}
            for name, data in sorted(files.items())
        ],
    }


def _write_manifest(tmp_path: Path, payload: dict | None = None) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload or _manifest(), indent=2) + "\n", encoding="utf-8")
    return path


def _run(tmp_path: Path, fake: FakeGithub, *, manifest=None, env=ENV, **kwargs):
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    return st.fetch_corpus(
        _write_manifest(tmp_path, manifest),
        inbox_dir=inbox,
        record_dir=tmp_path / "transport",
        transport=fake.transport,
        now=NOW,
        env=env,
        **kwargs,
    )


def _sub(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def _dispositions(record) -> dict[str, str]:
    return {entry["name"]: entry["disposition"] for entry in record.payload["files"]}


def _codes(record) -> dict[str, str | None]:
    return {entry["name"]: entry["code"] for entry in record.payload["files"]}


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --- arrival, binding and the record ---------------------------------------------------------------


def test_the_corpus_arrives_hash_bound_with_every_capture_invariant(tmp_path: Path) -> None:
    fake = FakeGithub()
    record = _run(tmp_path, fake)

    assert record.all_bound is True
    assert _dispositions(record) == {name: "FETCHED" for name in FILES}
    for name, data in FILES.items():
        assert (tmp_path / "inbox" / name).read_bytes() == data
    payload = record.payload
    assert payload["schema_version"] == "nfl_standings_transport_v1"
    assert payload["parser_version"] == "standings_transport_v1"
    assert payload["license_decision"] == "OPERATOR_SUPPLIED"
    assert payload["repository"] == REPO and payload["repository_private"] is True
    assert payload["observed_at"] == NOW.isoformat()
    assert payload["token_source_env_name"] == "GH_TOKEN"
    assert payload["manifest"]["sha256"] == sha256_bytes((tmp_path / "manifest.json").read_bytes())
    for entry in payload["files"]:
        artifact = entry["artifact"]
        data = FILES[entry["name"]]
        assert artifact["sha256"] == artifact["artifact_id"] == sha256_bytes(data)
        assert artifact["byte_count"] == len(data)
        assert artifact["license_decision"] == "OPERATOR_SUPPLIED"
        assert artifact["parser_version"] == "standings_transport_v1"
        assert artifact["captured_at"].endswith("+00:00")
        # The canonical API URI, never the signed CDN URL.
        assert artifact["source_uri"].startswith(f"https://api.github.com/repos/{REPO}/releases/assets/")
        assert "?" not in artifact["source_uri"] and SIGNED not in json.dumps(artifact)
        assert artifact["coverage"]["resolved_uri_host"] == "release-assets.githubusercontent.com"
        assert artifact["coverage"]["redirect_followed"] is True
    assert record.record_path.parent == tmp_path / "transport"
    assert json.loads(record.record_path.read_text(encoding="utf-8")) == payload


def test_authorization_goes_only_to_the_api_host_and_never_across_the_redirect(tmp_path: Path) -> None:
    fake = FakeGithub()
    _run(tmp_path, fake)

    api = [entry for entry in fake.log if entry["host"] == "api.github.com"]
    cdn = [entry for entry in fake.log if entry["host"] != "api.github.com"]
    assert len(api) == 2 + len(FILES) and len(cdn) == len(FILES)
    assert all(entry["auth"] == f"Bearer {SENTINEL}" for entry in api)
    assert all(entry["auth"] is None for entry in cdn)
    assert {entry["host"] for entry in cdn} == {"release-assets.githubusercontent.com"}
    # The asset URL is built from the integer id, never taken from the release JSON.
    assert not any(entry["host"] in {"evil.example", "github.com"} for entry in fake.log)
    assert all(entry["user"] == b"" for entry in fake.log)


def test_a_direct_200_from_the_api_is_accepted_and_still_bound(tmp_path: Path) -> None:
    fake = FakeGithub(mode="direct")
    record = _run(tmp_path, fake)
    assert record.all_bound is True
    assert set(fake.hosts()) == {"api.github.com"}
    assert record.payload["files"][0]["artifact"]["coverage"]["redirect_followed"] is False


# --- refusals: bytes, size, digest, content ---------------------------------------------------------


def test_a_byte_mismatched_file_is_refused_and_leaves_no_partial_file(tmp_path: Path) -> None:
    fake = FakeGithub()
    victim = "contest-standings-100002.csv"
    fake.served[victim] = FILES[victim][:-1] + b"X"  # same length, one byte changed
    record = _run(tmp_path, fake)

    assert record.all_bound is False
    assert _dispositions(record)[victim] == "REFUSED"
    assert _codes(record)[victim] == "STANDINGS_TRANSPORT_HASH_MISMATCH"
    assert not (tmp_path / "inbox" / victim).exists()
    leftovers = [p for p in (tmp_path / "inbox").rglob("*") if p.is_file() and p.name != victim]
    assert sorted(p.name for p in leftovers) == sorted(n for n in FILES if n != victim)
    staging = tmp_path / "inbox" / ".transport-staging"
    assert not staging.exists() or list(staging.iterdir()) == []
    others = {n: d for n, d in _dispositions(record).items() if n != victim}
    assert set(others.values()) == {"FETCHED"}
    refused = next(entry for entry in record.payload["files"] if entry["name"] == victim)
    assert refused["artifact"] is None and refused["actual_sha256"] != refused["expected_sha256"]


def test_a_truncated_body_is_refused(tmp_path: Path) -> None:
    fake = FakeGithub()
    victim = "contest-standings-100001.csv"
    fake.served[victim] = FILES[victim][:10]
    record = _run(tmp_path, fake)
    assert _codes(record)[victim] == "STANDINGS_TRANSPORT_HASH_MISMATCH"
    assert not (tmp_path / "inbox" / victim).exists()


def test_a_body_longer_than_the_manifest_is_cut_off(tmp_path: Path) -> None:
    fake = FakeGithub()
    victim = "contest-standings-100001.csv"
    fake.served[victim] = FILES[victim] + b"more" * 100
    record = _run(tmp_path, fake)
    assert _codes(record)[victim] == "STANDINGS_TRANSPORT_ASSET_TOO_LARGE"
    assert not (tmp_path / "inbox" / victim).exists()


def test_publisher_size_and_digest_disagreements_refuse_before_any_download(tmp_path: Path) -> None:
    fake = FakeGithub()
    fake.sizes["contest-standings-100001.csv"] = 999
    fake.digests["contest-standings-100002.csv"] = "sha256:" + "0" * 64
    record = _run(tmp_path, fake)

    codes = _codes(record)
    assert codes["contest-standings-100001.csv"] == "STANDINGS_TRANSPORT_PUBLISHER_SIZE_DISAGREES"
    assert codes["contest-standings-100002.csv"] == "STANDINGS_TRANSPORT_PUBLISHER_DIGEST_DISAGREES"
    fetched_ids = {entry["path"] for entry in fake.log if "/releases/assets/" in entry["path"]}
    assert fetched_ids == {f"/repos/{REPO}/releases/assets/502"}


def test_an_asset_missing_from_the_release_is_named_and_the_rest_arrive(tmp_path: Path) -> None:
    fake = FakeGithub()
    fake.hidden.add("contest-standings-100003.zip")
    record = _run(tmp_path, fake)
    assert _codes(record)["contest-standings-100003.zip"] == "STANDINGS_TRANSPORT_ASSET_MISSING"
    assert _dispositions(record)["contest-standings-100001.csv"] == "FETCHED"
    assert record.all_bound is False


def test_a_json_answer_is_never_hashed_as_the_asset(tmp_path: Path) -> None:
    fake = FakeGithub()
    fake.content_type = "application/json; charset=utf-8"
    record = _run(tmp_path, fake)
    assert set(_codes(record).values()) == {"STANDINGS_TRANSPORT_ASSET_NOT_BINARY"}
    assert not any(p.is_file() for p in (tmp_path / "inbox").rglob("*"))


@pytest.mark.parametrize("mode", ["evil", "draftkings", "userinfo", "api_moved", "double"])
def test_every_redirect_but_the_one_release_hop_is_refused_unfollowed(tmp_path: Path, mode: str) -> None:
    fake = FakeGithub(mode=mode)
    record = _run(tmp_path, fake)

    assert set(_codes(record).values()) == {"STANDINGS_TRANSPORT_REDIRECT_REFUSED"}
    assert not any(p.is_file() for p in (tmp_path / "inbox").rglob("*"))
    hosts = set(fake.hosts())
    assert hosts <= {"api.github.com", "release-assets.githubusercontent.com"}
    assert not hosts & {"evil.example", "www.draftkings.com", "draftkings.com", "objects.githubusercontent.com"}
    for entry in fake.log:
        if entry["host"] != "api.github.com":
            assert entry["auth"] is None


# --- credentials never surface ---------------------------------------------------------------------


def test_the_token_appears_nowhere_on_success_or_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    raised: list[BaseException] = []

    _run(_sub(tmp_path, "ok"), FakeGithub())
    tampered = FakeGithub()
    tampered.served["contest-standings-100001.csv"] = b"tampered"
    _run(_sub(tmp_path, "bad"), tampered)
    _run(_sub(tmp_path, "evil"), FakeGithub(mode="evil"))

    # The server echoes the Authorization header it received into its error body (a wrong token here).
    with pytest.raises(sources.AuthenticatedFetchError) as wrong:
        _run(_sub(tmp_path, "wrong"), FakeGithub(), env={"GH_TOKEN": SENTINEL + "x"})
    raised.append(wrong.value)

    # The transport itself fails while carrying the header.
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset", request=request)

    class Boom(FakeGithub):
        def __init__(self):
            super().__init__()
            self.transport = httpx.MockTransport(boom)

    with pytest.raises(sources.AuthenticatedFetchError) as failed:
        _run(_sub(tmp_path, "boom"), Boom())
    raised.append(failed.value)

    for error in raised:
        text = "".join(traceback.format_exception(error)) + repr(error) + str(error)
        assert SENTINEL not in text and "SENTINEL0123" not in text
        assert error.__context__ is None and error.__cause__ is None

    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert SENTINEL not in caplog.text and SIGNED not in caplog.text
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SENTINEL.encode() not in path.read_bytes(), path


class _DiesMidBody(httpx.SyncByteStream):
    def __iter__(self):
        yield b"{"
        raise httpx.ReadError("mid-stream")


@pytest.mark.parametrize("mode", ["api_json", "asset_direct", "asset_cdn"])
def test_a_failure_while_reading_the_body_chains_no_httpx_error(tmp_path: Path, mode: str) -> None:
    fake = FakeGithub(mode="direct" if mode == "asset_direct" else "redirect")
    inner = fake.transport

    def handler(request: httpx.Request) -> httpx.Response:
        good = inner.handle_request(request)
        wanted = {
            "api_json": request.url.path == f"/repos/{REPO}",
            "asset_direct": "/releases/assets/" in request.url.path,
            "asset_cdn": request.url.host == "release-assets.githubusercontent.com",
        }[mode]
        if wanted:
            return httpx.Response(200, stream=_DiesMidBody(), headers={"content-type": "application/octet-stream"})
        good.read()
        return good

    fake.transport = httpx.MockTransport(handler)
    if mode == "api_json":
        with pytest.raises(sources.AuthenticatedFetchError, match="STANDINGS_TRANSPORT_NETWORK_ERROR") as failed:
            _run(tmp_path, fake)
        errors = [failed.value]
    else:
        record = _run(tmp_path, fake)
        assert set(_codes(record).values()) == {"STANDINGS_TRANSPORT_NETWORK_ERROR"}
        errors = []
    for error in errors:
        assert error.__context__ is None and error.__cause__ is None
        assert SENTINEL not in "".join(traceback.format_exception(error))
    assert not any(p.is_file() for p in (tmp_path / "inbox").rglob("*"))


def test_a_direct_body_failure_raises_with_no_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_DiesMidBody(), headers={"content-type": "application/octet-stream"})

    with sources.AuthenticatedGithubClient(
        token=SENTINEL, token_env_name="GH_TOKEN", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(sources.AuthenticatedFetchError) as failed:
            client.download_asset(ASSET_URL, io.BytesIO(), max_bytes=100)
    assert failed.value.__context__ is None and failed.value.__cause__ is None


@pytest.mark.parametrize(
    "env,code",
    [
        ({}, "STANDINGS_TRANSPORT_CREDENTIAL_MISSING"),
        ({"GH_TOKEN": "  "}, "STANDINGS_TRANSPORT_CREDENTIAL_MISSING"),
        ({"GH_TOKEN": "abc\ndef"}, "STANDINGS_TRANSPORT_CREDENTIAL_INVALID"),
        ({"GH_TOKEN": "has space"}, "STANDINGS_TRANSPORT_CREDENTIAL_INVALID"),
    ],
)
def test_a_missing_or_malformed_credential_refuses_before_any_request(tmp_path: Path, env, code: str) -> None:
    fake = FakeGithub()
    with pytest.raises(sources.AuthenticatedFetchError, match=code) as raised:
        _run(tmp_path, fake, env=env)
    assert fake.log == []
    assert "abc" not in str(raised.value) and "has space" not in str(raised.value)


def test_the_first_named_variable_wins_and_only_its_name_is_recorded(tmp_path: Path) -> None:
    fake = FakeGithub()
    env = {"GITHUB_TOKEN": "someone-else", "GH_TOKEN": SENTINEL, "NFL_DFS_GITHUB_TOKEN": SENTINEL}
    record = _run(tmp_path, fake, env=env)
    assert record.payload["token_source_env_name"] == "NFL_DFS_GITHUB_TOKEN"


# --- the repository must be private -----------------------------------------------------------------


def test_a_public_repository_is_refused_unless_the_override_is_named(tmp_path: Path) -> None:
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_REPOSITORY_NOT_PRIVATE"):
        _run(tmp_path, FakeGithub(private=False))
    assert not any(p.is_file() for p in (tmp_path / "inbox").rglob("*"))

    record = _run(_sub(tmp_path, "override"), FakeGithub(private=False), allow_public_repository=True)
    assert record.payload["repository_private"] is False
    assert record.payload["allow_public_repository"] is True


# --- the inbox is an immutable snapshot ---------------------------------------------------------------


def test_files_already_in_the_inbox_are_untouched_and_cost_no_request(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name, data in FILES.items():
        (inbox / name).write_bytes(data)
    before = _tree_hashes(inbox)
    fake = FakeGithub()
    record = _run(tmp_path, fake, env={})  # no credential needed when nothing must be fetched

    assert fake.log == []
    assert _dispositions(record) == {name: "ALREADY_PRESENT" for name in FILES}
    assert record.all_bound is True
    assert _tree_hashes(inbox) == before


def test_a_name_collision_with_different_bytes_is_refused_and_the_file_is_untouched(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    name = "contest-standings-100001.csv"
    (inbox / name).write_bytes(b"Ben's own different export\n")
    before = _tree_hashes(inbox)
    fake = FakeGithub()
    record = _run(tmp_path, fake)

    assert _codes(record)[name] == "STANDINGS_TRANSPORT_NAME_COLLISION"
    assert record.all_bound is False
    assert _tree_hashes(inbox)[name] == before[name]
    assert "/repos/bleeski/nfl-corpus/releases/assets/500" not in [entry["path"] for entry in fake.log]
    # The other two still arrive.
    assert {n for n, d in _dispositions(record).items() if d == "FETCHED"} == set(FILES) - {name}


def test_a_file_that_appears_during_the_download_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    name = "contest-standings-100001.csv"
    real_link = st.os.link

    def racing_link(source, destination, *args, **kwargs):
        if Path(destination).name == name:
            Path(destination).write_bytes(b"someone else got there first\n")
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(st.os, "link", racing_link)
    record = _run(tmp_path, FakeGithub())
    assert (inbox / name).read_bytes() == b"someone else got there first\n"
    assert _codes(record)[name] == "STANDINGS_TRANSPORT_NAME_COLLISION"
    assert list((inbox / ".transport-staging").iterdir()) == []


def test_a_symlink_at_an_inbox_name_is_never_bound(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    name = "contest-standings-100001.csv"
    outside = tmp_path / "elsewhere.csv"
    outside.write_bytes(FILES[name])  # same bytes, but the inbox entry is a mutable pointer
    (inbox / name).symlink_to(outside)
    record = _run(tmp_path, FakeGithub())
    assert _codes(record)[name] == "STANDINGS_TRANSPORT_NAME_COLLISION"
    assert (inbox / name).is_symlink() and outside.read_bytes() == FILES[name]


def test_a_write_failure_is_a_refusal_row_and_the_record_is_still_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_full(self, url, sink, *, max_bytes):
        sink.write(b"partial")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sources.AuthenticatedGithubClient, "download_asset", disk_full)
    record = _run(tmp_path, FakeGithub())
    assert set(_codes(record).values()) == {"STANDINGS_TRANSPORT_WRITE_FAILED"}
    assert record.record_path.is_file() and record.all_bound is False
    assert not any(p.is_file() for p in (tmp_path / "inbox").rglob("*"))  # the .part file is gone too


def test_a_rerun_after_arrival_is_a_no_op(tmp_path: Path) -> None:
    fake = FakeGithub()
    first = _run(tmp_path, fake)
    before = _tree_hashes(tmp_path / "inbox")
    second_fake = FakeGithub()
    inbox = tmp_path / "inbox"
    second = st.fetch_corpus(
        tmp_path / "manifest.json",
        inbox_dir=inbox,
        record_dir=tmp_path / "transport2",
        transport=second_fake.transport,
        now=NOW,
        env={},
    )
    assert first.all_bound and second.all_bound
    assert second_fake.log == []
    assert _tree_hashes(inbox) == before


# --- manifest contract ---------------------------------------------------------------------------------


def _mutated(mutate) -> dict:
    payload = _manifest()
    mutate(payload)
    return payload


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(schema_version="nfl_standings_corpus_manifest_v2"),
        lambda p: p.update(unknown=True),
        lambda p: p.update(files=[]),
        lambda p: p.update(repository="someone-else/nfl-corpus"),
        lambda p: p.update(repository="bleeski"),
        lambda p: p.update(release_tag="../evil"),
        lambda p: p["files"][0].update(name="../escape.csv"),
        lambda p: p["files"][0].update(name="sub/dir.csv"),
        lambda p: p["files"][0].update(name="back\\slash.csv"),
        lambda p: p["files"][0].update(name=".hidden.csv"),
        lambda p: p["files"][0].update(name="CON.csv"),
        lambda p: p["files"][0].update(name="stream.csv:ads"),
        lambda p: p["files"][0].update(name="contest-standings-100001.txt"),
        lambda p: p["files"][0].update(name="trailingdot.csv."),
        lambda p: p["files"][1].update(name=p["files"][0]["name"].upper()),
        lambda p: p["files"][0].update(sha256="A" * 64),
        lambda p: p["files"][0].update(sha256="abc"),
        lambda p: p["files"][0].update(byte_count=0),
        lambda p: p["files"][0].update(byte_count=2**31),
        lambda p: p["files"][0].update(extra=1),
        lambda p: p["files"].reverse(),
        lambda p: p["files"].append(dict(p["files"][0])),
        lambda p: p["files"][0].update(name="contest-standings-100001.csv\n"),
        lambda p: p["files"][0].update(sha256="a" * 64 + "\n"),
        lambda p: p.update(release_tag="tag\n"),
        lambda p: p.update(repository=REPO + "\n"),
    ],
)
def test_a_hostile_or_malformed_manifest_is_refused_whole(tmp_path: Path, mutate) -> None:
    fake = FakeGithub()
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_MANIFEST_INVALID"):
        _run(tmp_path, fake, manifest=_mutated(mutate))
    assert fake.log == []
    assert not any(p.is_file() for p in (tmp_path / "inbox").rglob("*"))


def test_hostile_json_is_a_named_refusal_not_a_traceback(tmp_path: Path) -> None:
    deep = tmp_path / "deep.json"
    deep.write_bytes(b"[" * 200_000)
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_MANIFEST_INVALID"):
        st.load_manifest(deep)
    duplicate = tmp_path / "dup.json"
    text = json.dumps(_manifest()).replace(
        '"schema_version"', '"schema_version": "nfl_standings_corpus_manifest_v1", "schema_version"', 1
    )
    duplicate.write_text(text, encoding="utf-8")
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_MANIFEST_INVALID"):
        st.load_manifest(duplicate)


def test_a_missing_or_oversized_manifest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_MANIFEST_MISSING"):
        st.load_manifest(tmp_path / "absent.json")
    huge = tmp_path / "huge.json"
    huge.write_bytes(b" " * (2 * 1024 * 1024))
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_MANIFEST_INVALID"):
        st.load_manifest(huge)


# --- determinism and mutation --------------------------------------------------------------------------


def test_the_record_is_byte_identical_for_the_same_bytes_and_clock(tmp_path: Path) -> None:
    for run in ("a", "b"):
        (tmp_path / run).mkdir()
        _run(tmp_path / run, FakeGithub())
    a = (next((tmp_path / "a" / "transport").iterdir())).read_bytes()
    b = (next((tmp_path / "b" / "transport").iterdir())).read_bytes()
    assert a == b


def test_one_changed_byte_withholds_the_file_and_changes_the_record(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    clean = _run(tmp_path / "a", FakeGithub())
    (tmp_path / "b").mkdir()
    fake = FakeGithub()
    name = "contest-standings-100001.csv"
    data = bytearray(FILES[name])
    data[-2] ^= 0x01
    fake.served[name] = bytes(data)
    mutated = _run(tmp_path / "b", fake)
    assert not (tmp_path / "b" / "inbox" / name).exists()
    assert clean.record_path.read_bytes() != mutated.record_path.read_bytes()
    assert clean.all_bound and not mutated.all_bound


def test_a_record_is_never_overwritten(tmp_path: Path) -> None:
    _run(tmp_path, FakeGithub())
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_RECORD_EXISTS"):
        st.fetch_corpus(
            tmp_path / "manifest.json",
            inbox_dir=tmp_path / "inbox",
            record_dir=tmp_path / "transport",
            transport=FakeGithub().transport,
            now=NOW,
            env=ENV,
        )


# --- the manifest builder (Ben, on the machine that holds the corpus) -------------------------------------


def test_the_manifest_builder_hashes_the_inbox_without_touching_it(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    (inbox / ".transport-staging").mkdir(parents=True)
    for name, data in FILES.items():
        (inbox / name).write_bytes(data)
    (inbox / ".gitkeep").write_bytes(b"")
    (inbox / "notes.txt").write_bytes(b"not an export")
    (inbox / ".transport-staging" / ".x.part").write_bytes(b"partial")
    before = _tree_hashes(inbox)

    payload = st.build_manifest(inbox, repository=REPO, release_tag=TAG)
    again = st.build_manifest(inbox, repository=REPO, release_tag=TAG)

    assert payload == _manifest() == again
    assert _tree_hashes(inbox) == before
    target = tmp_path / "config" / "manifest.json"
    st.write_manifest(payload, target)
    assert st.load_manifest(target).payload == payload
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_RECORD_EXISTS"):
        st.write_manifest(payload, target)
    # Changing one inbox byte changes the manifest.
    (inbox / "contest-standings-100002.csv").write_bytes(FILES["contest-standings-100002.csv"] + b"!")
    assert st.build_manifest(inbox, repository=REPO, release_tag=TAG) != payload


def test_the_manifest_builder_refuses_an_empty_inbox(tmp_path: Path) -> None:
    (tmp_path / "inbox").mkdir()
    with pytest.raises(st.StandingsTransportError, match="STANDINGS_TRANSPORT_MANIFEST_INVALID"):
        st.build_manifest(tmp_path / "inbox", repository=REPO, release_tag=TAG)


# --- source policy: the license and the surface it opens -----------------------------------------------------


def test_operator_supplied_is_allowed_only_for_this_transport_and_nothing_else_moves() -> None:
    sources.validate_source_reference_policy(
        ASSET_URL, license_decision="OPERATOR_SUPPLIED", parser_version=sources.STANDINGS_TRANSPORT_PARSER_VERSION
    )
    sources.validate_source_reference_policy(
        ASSET_URL, license_decision="PERMITTED_REPOSITORY_LICENSE", parser_version="anything_v1"
    )
    refused = [
        (ASSET_URL, "OPERATOR_SUPPLIED", "other_v1"),
        (f"https://api.github.com/repos/{REPO}/contents/x.csv", "OPERATOR_SUPPLIED", "standings_transport_v1"),
        ("https://api.github.com/repos/someone-else/x/releases/assets/7", "OPERATOR_SUPPLIED", "standings_transport_v1"),
        ("https://api.github.com/repos/bleeski/x/releases/assets/seven", "OPERATOR_SUPPLIED", "standings_transport_v1"),
        ("https://raw.githubusercontent.com/bleeski/x/main/a.csv", "OPERATOR_SUPPLIED", "standings_transport_v1"),
        ("https://api.sleeper.app/v1/players/nfl", "OPERATOR_SUPPLIED", "standings_transport_v1"),
    ]
    for url, license_decision, parser in refused:
        with pytest.raises(sources.SourcePolicyError):
            sources.validate_source_reference_policy(url, license_decision=license_decision, parser_version=parser)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.github.com/user",
        "https://api.github.com/repos/someone-else/x/releases/tags/t",
        f"https://api.github.com/repos/{REPO}/releases/assets/7?x=1",
        f"https://api.github.com/repos/{REPO}/contents/README.md",
        f"https://api.github.com:8443/repos/{REPO}",
        f"http://api.github.com/repos/{REPO}",
        f"https://token@api.github.com/repos/{REPO}",
        f"https://github.com/{REPO}/releases/download/t/a.csv",
        f"https://www.draftkings.com/repos/{REPO}",
        f"https://api.github.com/repos/{REPO}/releases/assets/7/../8",
    ],
)
def test_the_authenticated_client_reaches_only_the_repository_release_endpoints(url: str) -> None:
    with pytest.raises(sources.AuthenticatedFetchError, match="STANDINGS_TRANSPORT_URL_REFUSED"):
        sources.validate_authenticated_github_url(url)


def test_the_old_public_fetch_still_sends_no_authorization(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, content=b"a,b\n", headers={"content-type": "text/csv"})

    real = httpx.Client
    monkeypatch.setattr(sources.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "NFL_DFS_GITHUB_TOKEN"):
        monkeypatch.setenv(name, SENTINEL)
    sources.fetch_public_artifact(
        "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
        tmp_path,
        source="TEST",
        license_decision="PERMITTED_REPOSITORY_LICENSE",
        parser_version="test_v1",
    )
    assert seen and all("authorization" not in headers for headers in seen)


# --- the documented command ---------------------------------------------------------------------------------------


def _load_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "fetch_standings_corpus.py"
    spec = importlib.util.spec_from_file_location("fetch_standings_corpus", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_builds_a_manifest_then_reports_a_missing_credential_plainly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _load_script()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name, data in FILES.items():
        (inbox / name).write_bytes(data)
    manifest = tmp_path / "manifest.json"
    code = script.main(
        ["manifest", "--inbox", str(inbox), "--out", str(manifest), "--repo", REPO, "--tag", TAG]
    )
    out = capsys.readouterr().out
    assert code == 0 and manifest.is_file()
    assert "3 files" in out and sha256_bytes(FILES["contest-standings-100001.csv"]) in out

    for name in ("GH_TOKEN", "GITHUB_TOKEN", "NFL_DFS_GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    code = script.main(
        ["fetch", "--manifest", str(manifest), "--inbox", str(fresh), "--record-dir", str(tmp_path / "rec")]
    )
    err = capsys.readouterr().err
    assert code == 2 and "STANDINGS_TRANSPORT_CREDENTIAL_MISSING" in err
    assert not any(fresh.iterdir())
