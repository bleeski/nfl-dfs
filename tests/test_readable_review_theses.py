"""Session 23f: the readable review's "Game theses" section (P8 part 3).

The review recomputes each Entry ID's thesis and every R34 figure from its own byte-reparsed rosters and the normalized
v4 policy bytes, then reconciles them against the audit's `theses` block and the selector's by-lineup claim. A thesis is a
choice, not a forecast, and with no ownership input leverage is unmeasured; every release truth stays
`PRIOR_ONLY / DO_NOT_UPLOAD`. A disagreement is `READABLE_REVIEW_THESIS_MISMATCH`, a presentation code that must not
withhold the CSV.
"""

from __future__ import annotations

import contextlib
import copy
import json
import re
from collections import Counter
from html import escape as html_escape
from itertools import combinations
from pathlib import Path

import pytest

from nfl_dfs import portfolio_enforcement
from nfl_dfs.delivery import discrepancy_limitations, withholds
from nfl_dfs.dk import parse_entries, parse_salaries
from nfl_dfs.gate_registry import load_gate_registry
from nfl_dfs.hashing import sha256_file
from nfl_dfs.portfolio_policy import POLICY_SCHEMA_VERSION_V2, POLICY_SCHEMA_VERSION_V3, POLICY_SCHEMA_VERSION_V4
from nfl_dfs.readable_review import (
    READABLE_REVIEW_VERSION,
    ReadableReviewError,
    _safe_detail,
    _theses_html,
    create_readable_review,
)

from .test_contest_assignment_run_slate import (
    INTERLEAVED_CONTESTS,
    SIX,
    _assert_truths_unchanged,
    _assignment_rosters,
    _run,
)
from .test_readable_review import TRUTHS
from .test_showdown_thesis_run_slate import _portfolio_controls

CODE = "READABLE_REVIEW_THESIS_MISMATCH"
HOSTILE = ("<b>NE_WIN_BIG</b>", "=SUM(1) NE_CLOSE", "A&B <script>alert(1)</script>")


def _controls(overlap: int = 4, names: tuple[str, ...] = (), weights: tuple[int, ...] = ()):
    def build(slate):
        built = _portfolio_controls(slate)
        built["max_pairwise_person_overlap"] = overlap
        for item, name in zip(built["theses"], names):
            item["name"] = name
        for item, weight in zip(built["theses"], weights):
            item["row_weight"] = weight
        return built

    return build


class _Run:
    """One finished `run-slate` run and the means to build its review again over the same bytes."""

    def __init__(self, code, report, entries, root):
        self.code, self.report, self.entries, self.root = code, report, Path(entries), Path(root)
        self.salary = self.entries.parent / "salary.csv"
        self.slate = parse_salaries(self.salary)
        self.artifacts = {k: v for k, v in report["prior_review_artifacts"].items() if not k.startswith("readable_review")}
        self.hashes = {k: v for k, v in report["prior_review_hashes"].items() if not k.startswith("readable_review")}
        self.reports = report["prior_review_reports"]

    def review(self, name, *, hashes=None, reports=None):
        return create_readable_review(
            slate=self.slate, template=parse_entries(self.entries), salary_path=self.salary, entry_path=self.entries,
            assignment_path=self.artifacts["assignments"], exported_path=self.artifacts["bulk_entry_csv"],
            artifacts=self.artifacts, expected_hashes=hashes or self.hashes, reports=reports or self.reports,
            truth_values=TRUTHS, blockers=tuple(self.report["blockers"]), next_action="Rerun.",
            output_dir=self.root / name, package_root=self.root)

    def readable(self) -> dict:
        return json.loads(Path(self.report["prior_review_artifacts"]["readable_review_json"]).read_text(encoding="utf-8"))

    def html(self) -> str:
        return Path(self.report["prior_review_artifacts"]["readable_review_html"]).read_text(encoding="utf-8")

    def claim_by_roster(self) -> dict[tuple[str, ...], str]:
        return {tuple(row["roster"]): row["thesis"] for row in self.reports["selection"]["lineups"]}

    def delivered(self) -> dict[str, tuple[str, ...]]:
        return _assignment_rosters(self.report)


def _finished(tmp_path_factory, label, **kwargs) -> _Run:
    root = tmp_path_factory.mktemp(label)
    with pytest.MonkeyPatch.context() as patch:
        code, report, entries, _slate = _run(
            root, patch, run_id=label, contests=INTERLEAVED_CONTESTS, policy_schema=POLICY_SCHEMA_VERSION_V4, **kwargs)
    assert code == 0, report["blockers"]
    return _Run(code, report, entries, root)


@pytest.fixture(scope="module")
def acceptance(tmp_path_factory) -> _Run:
    """The Session 23c fixture: three theses, six rows, the contest step moves lineups between Entry IDs."""

    return _finished(tmp_path_factory, "th-o4", policy_controls=_controls(4))


@pytest.fixture(scope="module")
def wide(tmp_path_factory) -> _Run:
    """The same portfolio with the overlap cap open to 6 and thesis names a renderer must escape.

    The acceptance fixture holds no pair of rows sharing five people (its overlap cap is 4), so only this run reconciles
    a non-empty `same_core_pairs` and people at exactly half the rows (the strict "more than half").
    """

    return _finished(tmp_path_factory, "th-o6", policy_controls=_controls(6, HOSTILE))


@contextlib.contextmanager
def _doctored(path, mutate):
    """Rewrite a JSON artifact, yield its new hash, and put the original bytes back."""

    path = Path(path)
    original = path.read_bytes()
    record = json.loads(original)
    mutate(record)
    path.write_text(json.dumps(record), encoding="utf-8")
    try:
        yield sha256_file(path)
    finally:
        path.write_bytes(original)


def _refused(run: _Run, artifact: str, mutate, label: str) -> str:
    """The review refuses a doctored artifact whose hash was rebound; returns the whole message."""

    with _doctored(run.artifacts[artifact], mutate) as digest:
        with pytest.raises(ReadableReviewError) as caught:
            run.review(label, hashes={**run.hashes, artifact: digest})
    message = str(caught.value)
    assert all(part.startswith(CODE) for part in message.split(";")), message  # nothing else is wrong: only the claim
    return message


def _hand(run: _Run) -> dict:
    """The R34 figures from the delivered roster IDs and the selector's per-lineup claim, in plain Python."""

    by_id = {row.dk_id: row for row in run.slate.players}
    delivered = run.delivered()
    claim = run.claim_by_roster()
    entries = [entry for entry in SIX if entry in delivered]
    people = {entry: frozenset(by_id[dk].underlying_id for dk in delivered[entry]) for entry in entries}
    captain = {entry: by_id[delivered[entry][0]].underlying_id for entry in entries}
    thesis = {entry: claim[delivered[entry]] for entry in entries}
    rows = len(entries)
    shared = Counter(person for entry in entries for person in people[entry])
    return {
        "entries": entries, "thesis": thesis, "captain": captain, "rows": rows,
        "captain_counts": dict(Counter(captain.values())),
        "captain_theses": {c: dict(Counter(thesis[e] for e in entries if captain[e] == c)) for c in set(captain.values())},
        "over_half": {person: count for person, count in shared.items() if 2 * count > rows},
        "exactly_half": {person for person, count in shared.items() if 2 * count == rows},
        "most_one_player": max(shared.values()),
        "most_one_thesis": max(Counter(thesis.values()).values()),
        "pairs": [(a, b, len(people[a] & people[b])) for a, b in combinations(entries, 2) if len(people[a] & people[b]) >= 5],
    }


def _assert_figures_equal_hand_and_audit(run: _Run) -> dict:
    data = run.readable()
    block = data["theses"]
    hand = _hand(run)
    audit = run.reports["portfolio_policy_audit"]["theses"]
    measures = block["measures"]
    assert measures == audit["measures"]  # the figures are the audit's, to the byte
    assert [row["entry_id"] for row in block["entries"]] == hand["entries"]
    for row in block["entries"]:
        assert row["thesis"] == hand["thesis"][row["entry_id"]]
        assert row["follows"] is True and row["broken_rules"] == []
        assert row["captain"] == hand["captain"][row["entry_id"]]
    assert {c: item["count"] for c, item in measures["captains"].items()} == hand["captain_counts"]
    assert {c: item["theses"] for c, item in measures["captains"].items()} == hand["captain_theses"]
    assert {c: item["share_percentage"] for c, item in measures["captains"].items()} == {
        c: round(100 * count / hand["rows"], 3) for c, count in hand["captain_counts"].items()}
    assert measures["distinct_captains"] == len(hand["captain_counts"])
    assert measures["max_captain_share_percentage"] == round(100 * max(hand["captain_counts"].values()) / hand["rows"], 3)
    assert {item["person"]: item["rows"] for item in measures["people_in_more_than_half"]} == hand["over_half"]
    assert measures["most_rows_one_player_sinks"]["rows"] == hand["most_one_player"]
    assert measures["most_rows_one_thesis_sinks"]["rows"] == hand["most_one_thesis"]
    assert [(p["entry_id_a"], p["entry_id_b"], p["shared_people"]) for p in measures["same_core_pairs"]] == hand["pairs"]
    return hand


def test_the_review_lists_every_entry_ids_thesis_and_every_figure_and_they_equal_the_audit_and_a_hand_recompute(
    acceptance,
):
    run = acceptance
    _assert_truths_unchanged(run.report)
    data = run.readable()
    assert data["schema_version"] == READABLE_REVIEW_VERSION == "prior_only_readable_review_sd5_v3"  # additive: no new version
    assert "PRIOR_ONLY" in data["warning"] and "review only, not certified upload files" in data["warning"]
    assert data["truths"]["RELEASE_DECISION"] == "DO_NOT_UPLOAD" and data["truths"]["MODEL_STATUS"] == "PRIOR_ONLY"
    block = data["theses"]
    assert block["reconciliation"]["status"] == "PASS"
    assert block["build_version"] == "showdown_thesis_portfolio_sd3_v1"
    assert [(item["name"], item["rows_allotted"], item["rows_delivered"]) for item in block["theses"]] == [
        ("NE_WIN_BIG", 2, 2), ("NE_WIN_CLOSE_LOW", 2, 2), ("SEA_WIN_BIG", 2, 2)]
    hand = _assert_figures_equal_hand_and_audit(run)
    # The figures are not vacuous here: five people are in more than half the rows, one in exactly half is left out.
    assert len(hand["over_half"]) == 5 and len(hand["exactly_half"]) == 1
    assert not set(hand["over_half"]) & hand["exactly_half"]
    for person in hand["captain_counts"]:
        assert block["people"][person]["name"]
    html = run.html()
    assert "<h2>Game theses</h2>" in html
    for entry in SIX:
        assert entry in html


def test_a_thesis_dropped_at_validation_stays_in_the_review_and_reconciles_with_zero_rows(tmp_path_factory):
    """Six rows at weights 100, 100 and 1: the third thesis cannot get a row, so the policy keeps it DROPPED.

    The audit's allotment covers every thesis, dropped ones included, so `by_thesis` names it with zero rows; a review
    that allotted over the active theses alone would disagree with the audit on a real portfolio.
    """

    run = _finished(tmp_path_factory, "th-dropped", policy_controls=_controls(4, weights=(100, 100, 1)))
    block = run.readable()["theses"]
    assert [(item["status"], item["rows_allotted"], item["rows_delivered"]) for item in block["theses"]] == [
        ("ACTIVE", 3, 3), ("ACTIVE", 3, 3), ("DROPPED", 0, 0)]
    assert block["theses"][2]["entry_ids"] == [] and block["theses"][2]["dropped_reason"]
    assert block["measures"]["by_thesis"][block["theses"][2]["name"]]["rows"] == 0
    assert block["measures"] == run.reports["portfolio_policy_audit"]["theses"]["measures"]
    assert {row["thesis"] for row in block["entries"]} == {item["name"] for item in block["theses"][:2]}


def test_a_pair_of_rows_sharing_five_people_and_people_at_exactly_half_reconcile_in_the_audits_own_order(wide):
    run = wide
    hand = _assert_figures_equal_hand_and_audit(run)
    assert len(hand["pairs"]) > 0 and len(hand["over_half"]) > 0  # both lists are non-empty: order can bite
    assert hand["exactly_half"]  # and the strict "more than half" can bite: these people are not in the list
    assert not set(hand["over_half"]) & hand["exactly_half"]
    html = run.html()
    assert "Pairs of rows sharing 5 or more people" in html
    # Hostile thesis names reach the page only escaped.
    section = html.split("<h2>Game theses</h2>", 1)[1].split("<h2>", 1)[0]
    assert "<script>" not in section and "<b>NE_WIN_BIG</b>" not in section
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in section and "&lt;b&gt;NE_WIN_BIG&lt;/b&gt;" in section


def test_each_entry_ids_thesis_is_right_after_the_contest_step_moved_lineups(acceptance):
    run = acceptance
    assert run.reports["contest_assignment"]["moved_rows"] > 0
    selection = run.reports["selection"]
    solver_order = {entry: lineup["thesis"] for entry, lineup in zip(selection["reserved_entries"], selection["lineups"])}
    final = {row["entry_id"]: row["thesis"] for row in run.readable()["theses"]["entries"]}
    assert final == _hand(run)["thesis"]
    # The contest step really changed which thesis sits on an Entry ID, so reading by Entry ID in the solver's order is wrong.
    assert sum(1 for entry in final if final[entry] != solver_order[entry]) > 0


# ---- a doctored audit, selector claim or depth report is refused by name, and nothing else is wrong ----

AUDIT_DOCTORING = [
    ("entries", lambda r: r["theses"]["entries"][SIX[0]].update(follows=False), "audit.entries"),
    ("distinct_captains", lambda r: r["theses"]["measures"].update(
        distinct_captains=r["theses"]["measures"]["distinct_captains"] + 1), "audit.measures.distinct_captains"),
    ("people_over_half", lambda r: r["theses"]["measures"].update(people_in_more_than_half=[]),
     "audit.measures.people_in_more_than_half"),
    ("one_player_sinks", lambda r: r["theses"]["measures"]["most_rows_one_player_sinks"].update(rows=1),
     "audit.measures.most_rows_one_player_sinks"),
    ("one_thesis_sinks", lambda r: r["theses"]["measures"]["most_rows_one_thesis_sinks"].update(rows=1),
     "audit.measures.most_rows_one_thesis_sinks"),
    ("an_invented_key", lambda r: r["theses"]["measures"].update(invented=1), "audit.measures.invented"),
    ("theses", lambda r: r["theses"]["theses"][0].update(rows=3), "audit.theses"),
    ("assignment_source", lambda r: r["theses"].update(assignment_source="DERIVED_BY_THE_AUDIT"), "audit.assignment_source"),
    ("no_theses_block", lambda r: r.pop("theses"), "audit.theses_missing"),
]


@pytest.mark.parametrize("label,mutate,detail", AUDIT_DOCTORING, ids=[row[0] for row in AUDIT_DOCTORING])
def test_a_doctored_audit_figure_is_refused_by_name(acceptance, label, mutate, detail):
    message = _refused(acceptance, "portfolio_policy_audit", mutate, f"audit-{label}")
    assert f"{CODE}:{detail}" in message


def _lineups_of_two_theses(run: _Run, record: dict) -> tuple[str, str]:
    claim = record["selection"]["portfolio_policy"]["theses"]["by_lineup"]
    first = next(iter(claim))
    other = next(key for key, name in claim.items() if name != claim[first])
    return first, other


def test_a_doctored_selector_claim_is_refused_by_name(acceptance):
    run = acceptance

    def swap(record):
        theses = record["selection"]["portfolio_policy"]["theses"]
        first, other = _lineups_of_two_theses(run, record)
        theses["by_lineup"][first], theses["by_lineup"][other] = theses["by_lineup"][other], theses["by_lineup"][first]

    message = _refused(run, "selection_report", swap, "claim-swap")
    assert f"{CODE}:selector.entries" in message  # the relabelled Entry block no longer matches the claim it came from

    def inactive(record):
        theses = record["selection"]["portfolio_policy"]["theses"]
        theses["by_lineup"][_lineups_of_two_theses(run, record)[0]] = "NO_SUCH_THESIS"

    message = _refused(run, "selection_report", inactive, "claim-inactive")
    assert f"{CODE}:entry=" in message and "claim_not_an_active_thesis" in message

    def solver_order(record):
        selection = record["selection"]
        selection["portfolio_policy"]["theses"]["entries"] = {
            entry: lineup["thesis"] for entry, lineup in zip(record["reserved_entries"], record["lineups"])}

    message = _refused(run, "selection_report", solver_order, "claim-stale-entries")
    assert f"{CODE}:selector.entries" in message  # a block left in the solver's order after the contest step

    message = _refused(
        run, "selection_report",
        lambda record: record["selection"]["portfolio_policy"]["theses"].pop("by_lineup"), "claim-missing")
    assert f"{CODE}:selector.by_lineup_missing" in message

    def move_one_lineup(record):
        # Every lineup still names an active thesis, but one thesis now holds three rows and another one.
        claim = record["selection"]["portfolio_policy"]["theses"]["by_lineup"]
        first, other = _lineups_of_two_theses(run, record)
        claim[first] = claim[other]

    message = _refused(run, "selection_report", move_one_lineup, "claim-counts")
    assert f"{CODE}:rows.thesis[" in message  # each thesis must hold exactly its allotment, named by position

    def extra_entry(record):
        record["selection"]["portfolio_policy"]["theses"]["entries"]["999999999"] = "NE_WIN_BIG"

    message = _refused(run, "selection_report", extra_entry, "claim-extra-entry")
    assert f"{CODE}:selector.entries" in message  # an Entry ID the policy does not bind is not part of the claim


def test_the_backup_quarterback_rule_is_read_from_the_selectors_depth_report(acceptance):
    run = acceptance
    teams = {row.team for row in run.slate.players if row.position == "QB"}

    def make_every_quarterback_a_backup(record):
        # A starter nobody is: under the rule every quarterback a thesis does not itself admit is a backup.
        record["selection"]["qb_depth_roles"] = {"starters_by_team": {team: "NOBODY" for team in sorted(teams)}}

    message = _refused(run, "selection_report", make_every_quarterback_a_backup, "depth")
    assert f"{CODE}:audit.entries" in message  # the audit followed no such rule, so the two disagree


# ---- delivery: the CSV still ships, with a presentation limitation ----


def _patched_audit_run(tmp_path, monkeypatch, *, names=()):
    real = portfolio_enforcement.thesis_portfolio_measures

    def shifted(*args, **kwargs):
        measures = real(*args, **kwargs)
        return {**measures, "distinct_captains": measures["distinct_captains"] + 1}

    # The audit's own bound name only; the review holds its own reference, so one patch cannot move both sides.
    monkeypatch.setattr(portfolio_enforcement, "thesis_portfolio_measures", shifted)
    return _run(
        tmp_path, monkeypatch, run_id="th-patched", contests=INTERLEAVED_CONTESTS,
        policy_controls=_controls(4, names), policy_schema=POLICY_SCHEMA_VERSION_V4)


@pytest.mark.parametrize("names", [(), ("NE;WIN;BIG", "NE; CLOSE", "SEA;BIG")], ids=["plain_names", "names_with_semicolons"])
def test_a_thesis_mismatch_keeps_the_csv_with_a_presentation_limitation(tmp_path, monkeypatch, names):
    from nfl_dfs import delivery

    code, report, _entries, _slate = _patched_audit_run(tmp_path, monkeypatch, names=names)
    assert code == 2
    _assert_truths_unchanged(report)
    assert report["FILE_VALID"] is True and report["RELEASE_DECISION"] == "DO_NOT_UPLOAD"
    assert report["DELIVERY_STATE"] == "DELIVERABLE"
    assert report["prior_review_reports"]["portfolio_policy_audit"]["status"] == "PASS"  # the audit itself has no complaint
    record = report["prior_review_reports"]["readable_review_failure"]
    assert record["limitations"] == [CODE]  # exactly one fragment: a name or a ';' never made a second, unclassified one
    assert record["kept_artifacts"]["bulk_entry_csv"]["path"] == report["bulk_entry_csv"]
    assert sha256_file(report["bulk_entry_csv"]) == report["bulk_entry_sha256"]
    assert "readable_review_json" not in report["prior_review_artifacts"]
    codes = {item["code"]: item for item in report["release_truths"]["delivery_limitations"]}
    assert (codes[CODE].get("class") or codes[CODE].get("gate_class")) == "P" and "GATE_CODE_UNCLASSIFIED" not in codes
    latest = delivery.read_latest(tmp_path / "outputs" / "th-patched")
    assert latest is not None and str(latest.deliverable.path) == report["bulk_entry_csv"]


# ---- no theses: nothing moves ----


def test_a_run_with_no_theses_or_one_v3_thesis_has_no_theses_key_and_no_section(tmp_path_factory):
    def finished(label, controls, schema):
        root = tmp_path_factory.mktemp(label)
        with pytest.MonkeyPatch.context() as patch:
            code, report, entries, _slate = _run(
                root, patch, run_id=label, contests=INTERLEAVED_CONTESTS, policy_controls=controls, policy_schema=schema)
        assert code == 0, report["blockers"]
        return _Run(code, report, entries, root)

    def none(slate):
        built = _portfolio_controls(slate)
        built.pop("theses")
        return built

    def one(slate):
        built = _portfolio_controls(slate)
        built["theses"] = built["theses"][:1]
        return built

    for label, controls, schema in (("th-none", none, POLICY_SCHEMA_VERSION_V2), ("th-v3", one, POLICY_SCHEMA_VERSION_V3)):
        run = finished(label, controls, schema)
        data = run.readable()
        assert "theses" not in data and data["schema_version"] == READABLE_REVIEW_VERSION
        assert set(data) == EXISTING_KEYS  # no key is added to a review that has no theses
        assert "Game theses" not in run.html()
        assert data["reconciliation"]["status"] == "PASS"


# ---- rendering and determinism ----


def test_the_section_says_in_words_that_a_thesis_is_a_choice_and_leverage_is_unmeasured(acceptance):
    html = acceptance.html()
    section = html.split("<h2>Game theses</h2>", 1)[1].split("<h2>", 1)[0]
    prose = re.sub(r"<[^>]+>", " ", section)
    assert "Does not establish" in prose  # the registered tokens close the section; the prose is what comes before
    prose = prose.split("Does not establish")[0]
    assert "a choice" in prose and "not a forecast" in prose
    assert "Leverage is unmeasured" in prose and "no ownership input" in prose
    lowered = prose.lower()
    for word in ("likely", "calibrated", "+ev", "win probability", "roi"):
        assert word not in lowered
    assert "people in more than half the rows" in lowered
    assert "bad night" in lowered and "thesis sinks" in lowered


def test_the_renderer_escapes_every_name_and_says_none_when_a_list_is_empty(wide):
    block = copy.deepcopy(wide.readable()["theses"])
    hostile = "<script>alert(1)</script> =cmd|' /c calc'!A1"
    for item in block["theses"]:
        item["name"] = hostile
    for person in block["people"].values():
        person["name"] = hostile
    for row in block["entries"]:
        row["thesis"] = hostile
    rendered = "".join(_theses_html(block))
    assert "<script>" not in rendered and "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    # With people and pairs present, each heading is followed by a table, never by "none".
    assert "<h3>People in more than half the rows</h3><table" in rendered
    assert "<h3>Pairs of rows sharing 5 or more people</h3><table" in rendered
    block["measures"]["people_in_more_than_half"] = []
    block["measures"]["same_core_pairs"] = []
    emptied = "".join(_theses_html(block))
    # "none" also appears in each row's empty "Rules broken" cell, so pin the exact markup under each heading.
    assert "<h3>People in more than half the rows</h3><p>none</p>" in emptied
    assert "<h3>Pairs of rows sharing 5 or more people</h3><p>none</p>" in emptied


@pytest.mark.parametrize("which", ["acceptance", "wide"])
def test_the_html_shows_the_numbers_it_reconciled(request, which):
    """Every figure on the page is the reconciled figure: a renderer reading the wrong key shows a wrong number."""

    run = request.getfixturevalue(which)
    block = run.readable()["theses"]
    measures, people = block["measures"], block["people"]
    section = run.html().split("<h2>Game theses</h2>", 1)[1].split("<h2>", 1)[0]
    cell = lambda value: f"<td>{html_escape(str(value), quote=True)}</td>"  # noqa: E731
    who = lambda person: f'{people[person]["name"]} ({people[person]["team"]})'  # noqa: E731
    for item in block["theses"]:
        assert "<tr>" + "".join(cell(item[key]) for key in (
            "name", "status", "row_weight", "rows_allotted", "rows_delivered")) in section
    for row in block["entries"]:
        assert "<tr>" + "".join(cell(value) for value in (
            row["entry_id"], row["thesis"], "YES" if row["follows"] else "NO", who(row["captain"]),
            ", ".join(row["broken_rules"]) or "none")) + "</tr>" in section
    for person, item in measures["captains"].items():
        assert cell(who(person)) + cell(item["count"]) + cell(item["share_percentage"]) in section
    assert (f'{measures["distinct_captains"]} distinct Captains; the largest Captain share is '
            f'{measures["max_captain_share_percentage"]}%.') in section
    for item in measures["people_in_more_than_half"]:
        assert cell(who(item["person"])) + cell(item["rows"]) + cell(item["share_percentage"]) in section
    sink = measures["most_rows_one_player_sinks"]
    assert f'{sink["rows"]} of the rows ({sink["share_percentage"]}%): ' in section
    for person in sink["people"]:
        assert html_escape(who(person), quote=True) in section
    assert f'<p>{measures["most_rows_one_thesis_sinks"]["rows"]} rows: ' in section
    for pair in measures["same_core_pairs"]:
        assert ("<tr>" + cell(pair["entry_id_a"]) + cell(pair["entry_id_b"]) + cell(pair["shared_people"])
                + cell("YES" if pair["captain_rotation"] else "NO")) in section


def test_an_unreadable_normalized_policy_is_a_presentation_mismatch_with_no_semicolon_in_it(acceptance, monkeypatch):
    from nfl_dfs import readable_review

    def unreadable(raw):
        raise ValueError("a;b")

    monkeypatch.setattr(readable_review, "_parse_audited_policy_controls", unreadable)
    with pytest.raises(ReadableReviewError) as caught:
        acceptance.review("unreadable-policy")
    assert str(caught.value) == f"{CODE}:normalized_policy_theses_unreadable:ValueError:a,b"
    assert not withholds(discrepancy_limitations(str(caught.value), load_gate_registry()))


EXISTING_KEYS = {
    "schema_version", "status", "truths", "warning", "next_action", "blockers", "reconciliation", "entries",
    "exposure", "unbound_rows", "contest_assignment", "pool_coverage", "evidence_observations", "artifacts", "hashes",
}


def test_the_theses_key_is_the_only_key_a_portfolio_of_theses_adds(acceptance):
    assert set(acceptance.readable()) == EXISTING_KEYS | {"theses"}


def test_the_review_bytes_are_deterministic(acceptance):
    first, second = acceptance.review("again-1"), acceptance.review("again-2")
    assert Path(first.json_path).read_bytes() == Path(second.json_path).read_bytes()
    assert Path(first.html_path).read_bytes() == Path(second.html_path).read_bytes()
    assert first.data["theses"] == acceptance.readable()["theses"]


# ---- the registered code ----


def test_the_mismatch_code_is_registered_as_a_presentation_gate_that_does_not_withhold_the_file():
    registry = load_gate_registry()
    assert registry.codes[CODE] == "presentation"
    limitation = registry.limitation(CODE, detail=f"{CODE}:audit.measures.captains")
    assert limitation.gate_class.value == "P"
    assert not withholds(discrepancy_limitations(f"{CODE}:audit.measures.captains", registry))
    # Its neighbours in the same family, which this code follows.
    assert registry.codes["READABLE_REVIEW_AUDIT_OVERLAP_MISMATCH"] == "presentation"


def test_free_text_in_a_detail_cannot_turn_a_presentation_mismatch_into_a_withheld_file():
    registry = load_gate_registry()
    # The delivery layer splits a failure on ";" and classifies each fragment by its leading code; an unregistered
    # fragment is class V and withholds the file. A strict-parser message can carry ";".
    raw = f"{CODE}:normalized_policy_theses_unreadable:x;y"
    assert withholds(discrepancy_limitations(raw, registry))  # what would happen without the helper
    safe = f"{CODE}:normalized_policy_theses_unreadable:{_safe_detail('x;y')}"
    assert _safe_detail("x;y") == "x,y" and ";" not in safe
    assert not withholds(discrepancy_limitations(safe, registry))
