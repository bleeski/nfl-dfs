"""Gate classification tests (Session 03; the registry file itself is Session 03b).

This file holds the R24 condition today. R24 let a missing weather state stop
certification instead of construction on one ground: `weather_state` reaches no
number. That is a property of the code, and it decays silently. The day weather
feeds a projection, a portfolio built without it is built on a missing input
that moves numbers, and a derived roof (R26, `DERIVED_FROM_VENUE_ROOF_HISTORY`)
would feed that arithmetic a value nobody observed. So three checks, each of
which must fail on that day:

* where weather may be read at all: only in named plumbing (the request, the
  gates, the evidence records, the roof resolver, the weather scripts) and at a
  few pinned sites in numeric code that validate it or copy it into a row. Any
  other read, in any module under `src/nfl_dfs/` or `scripts/`, a new module
  included, fails, whatever shape it takes: a helper, a lookup table, a
  `match`, an early return;
* an arithmetic scan everywhere, plumbing included: no arithmetic takes a
  weather or roof value as an operand, is indexed by one, or runs under a branch
  that tests one, except four named sites that count games or join text;
* a behavioural check: every weather state, the derived-roof one included,
  gives identical prior scores and team volumes.

What none of this catches: plumbing code that turns weather into a number under
a name that does not say weather, for code elsewhere to consume. Plumbing is
kept small and named for that reason.

Session 03b added the gate registry below the R24 tests: `config/gate_registry_v1.json`,
its loader, completeness in both directions, the class rules on registry entries,
and the audit's section 4 rows landing in the classes it names.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

from nfl_dfs.contracts import GateClass, GateStops, ProvenanceKind
from nfl_dfs.gate_registry import (
    ALLOWED_PAIRS,
    DEFAULT_REGISTRY_PATH,
    GateRegistryError,
    load_gate_registry,
    parse_gate_registry,
    template_bindings,
)
from nfl_dfs.opportunity import WEATHER_STATES
from nfl_dfs.prior_score import score_pool, team_volumes
from nfl_dfs.priors import resolve_weather_state
from nfl_dfs.release import derive_delivery_state
from nfl_dfs.venues import VENUE_ROOF_BASIS

from .test_prior_selection import _prepared

SRC = Path(__file__).resolve().parent.parent / "src" / "nfl_dfs"

# Modules whose arithmetic produces a projection, an opportunity share, a score,
# a simulated outcome, a selection objective or a model grade. None of them may
# ever appear in NON_NUMERIC_SITES.
SCORING_MODULES = frozenset({
    "candidate_families.py", "classic_portfolio.py", "depth_roles.py", "economics.py",
    "field.py", "kicker_roles.py", "learning.py", "model_validation.py",
    "offensive_roles.py", "opportunity.py", "optimizer.py", "ownership.py",
    "participation.py", "payouts.py", "portfolio.py", "portfolio_enforcement.py",
    "prior_score.py", "priors.py", "projection.py", "qa.py", "qb_depth_roles.py",
    "referee.py", "scoring.py", "selection.py", "simulation.py", "training.py",
})

# Sites the scan sees that are not arithmetic on a weather value, keyed by
# (module, function, expression) so a moved line still matches and a changed
# expression does not.
NON_NUMERIC_SITES = {
    ("prior_review.py", "run_prior_review", "weather_path.parent / source_relative"):
        "a filesystem path join on the weather capture's directory",
    ("venues.py", "roof_history", "counts.setdefault(team, Counter())[roof] += 1"):
        "the R26 resolver's evidence: completed games per recorded roof value",
    ("venues.py", "resolve_blank_roof", "int(tally.get(RESOLVED_ROOF_VALUE, 0))"):
        "reads that game count to decide a roof value, never a projection",
}

SCRIPTS = SRC.parent.parent / "scripts"

# Code that handles weather as evidence or configuration and computes no
# projection, share, score or objective. Weather may be read anywhere in these.
PLUMBING_MODULES = frozenset({
    "src/nfl_dfs/certification.py", "src/nfl_dfs/cli.py", "src/nfl_dfs/cowork.py",
    "src/nfl_dfs/prior_review.py", "src/nfl_dfs/venues.py",
    "scripts/check_venue_roof_set.py", "scripts/fetch_weather_captures.py",
    "scripts/make_classic_weather_evidence.py", "scripts/session_probe.py",
})
# The weather functions of a module that also builds projection inputs.
PLUMBING_FUNCTIONS = frozenset({
    ("src/nfl_dfs/priors.py", "freeze_prior_package"),
    ("src/nfl_dfs/priors.py", "propose_prior_package"),
    ("src/nfl_dfs/priors.py", "resolve_weather_state"),
    ("src/nfl_dfs/priors.py", "_venue_roof_history_for"),
    ("src/nfl_dfs/priors.py", "_weather_evidence_basis"),
    # Session 09: refuses a v1 team source that holds an UNOBSERVED game.
    ("src/nfl_dfs/projection.py", "v1_never_holds_an_unobserved_game"),
})
# Every read of a weather value in numeric code, with how many times it occurs.
PINNED_READS = {
    ("src/nfl_dfs/opportunity.py", "load_opportunity_model", "row['WEATHER_STATE']"):
        (1, "parsed from the team projection CSV"),
    ("src/nfl_dfs/opportunity.py", "load_opportunity_model", "weather_state"):
        (2, "checked against the enum, then stored on TeamProjection"),
    ("src/nfl_dfs/opportunity.py", "load_opportunity_model", "WEATHER_STATES"):
        (2, "the enum it is checked against, and its error message"),
    ("src/nfl_dfs/projection.py", "_team_rows", "record.weather_state"):
        (1, "copied into the team CSV row"),
    ("src/nfl_dfs/priors.py", "build_team_records", "weather_by_game"):
        (4, "game coverage check, its message, and a copy into the record and diagnostics"),
}

WEATHER = re.compile(r"weather|roof", re.I)
ARITH_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.MatMult)
NUMERIC_CALLS = frozenset({"sum", "abs", "round", "float", "int", "Decimal", "pow", "divmod"})
NUMERIC_NAMESPACES = frozenset({"math", "np", "numpy", "statistics"})
PASS_THROUGH_CALLS = NUMERIC_CALLS | {"str"}
PASS_THROUGH_METHODS = frozenset({"strip", "upper", "lower", "casefold", "get", "items", "values", "copy"})
PREDICATE_METHODS = frozenset({"startswith", "endswith", "count", "find", "index"})
COLLECTION_CALLS = frozenset({"tuple", "list", "set", "frozenset", "sorted", "dict"})


def weather_valued(node: ast.AST, tainted: set[str]) -> bool:
    """Whether `node` evaluates to a weather or roof value, or a container of them.

    A name, attribute or constant key that says weather or roof; a name assigned
    from one earlier in the function; a string method, `.get`, numeric
    conversion or comparison of one, which is how an indicator such as
    `float(state == "RAIN")` would carry it; and the derived-roof basis string
    itself. A value an arbitrary function computes from a weather argument is not
    followed: that function is scanned on its own.
    """

    if isinstance(node, ast.Name):
        return node.id in tainted or WEATHER.search(node.id) is not None
    if isinstance(node, ast.Attribute):
        return WEATHER.search(node.attr) is not None or weather_valued(node.value, tainted)
    if isinstance(node, ast.Subscript):
        key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and WEATHER.search(key.value):
            return True
        # A table indexed by a weather value yields a weather-dependent number.
        return weather_valued(node.value, tainted) or weather_valued(key, tainted)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in PASS_THROUGH_METHODS:
            first = node.args[0] if node.args else None
            if func.attr == "get" and first is not None and (
                weather_valued(first, tainted)
                or (isinstance(first, ast.Constant) and isinstance(first.value, str)
                    and WEATHER.search(first.value))
            ):
                return True
            return weather_valued(func.value, tainted)
        if isinstance(func, ast.Attribute) and func.attr in PREDICATE_METHODS:
            return weather_valued(func.value, tainted) or any(
                weather_valued(arg, tainted) for arg in node.args)
        if isinstance(func, ast.Name) and func.id in PASS_THROUGH_CALLS:
            return any(weather_valued(arg, tainted) for arg in node.args)
        return False
    if isinstance(node, ast.Compare):
        return any(weather_valued(side, tainted) for side in (node.left, *node.comparators))
    if isinstance(node, ast.IfExp):
        return any(weather_valued(part, tainted) for part in (node.test, node.body, node.orelse))
    if isinstance(node, ast.BoolOp):
        return any(weather_valued(value, tainted) for value in node.values)
    if isinstance(node, ast.BinOp):
        return weather_valued(node.left, tainted) or weather_valued(node.right, tainted)
    if isinstance(node, ast.UnaryOp):
        return weather_valued(node.operand, tainted)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return VENUE_ROOF_BASIS in node.value
    return False


def _names(target: ast.AST) -> list[str]:
    return [node.id for node in ast.walk(target) if isinstance(node, ast.Name)]


def _not_a_quantity(node: ast.AST) -> bool:
    """Text, a collection, or a duration: `+` on these builds a string, a tuple or a
    time (an evidence expiry), never a projection, share or score."""

    if isinstance(node, (ast.JoinedStr, ast.Tuple, ast.List, ast.Set, ast.Dict)):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return True
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
    return name in COLLECTION_CALLS or name == "timedelta"


def _operands(node: ast.AST) -> tuple[ast.AST, ...] | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ARITH_OPS):
        return node.left, node.right
    if isinstance(node, ast.AugAssign) and isinstance(node.op, ARITH_OPS):
        return node.target, node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return (node.operand,)
    if isinstance(node, ast.Call):
        func = node.func
        if ((isinstance(func, ast.Name) and func.id in NUMERIC_CALLS)
                or (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    and func.value.id in NUMERIC_NAMESPACES)):
            return tuple(node.args)
    return None


def arithmetic_on_weather(source: str, module: str) -> list[tuple[str, str, str, int]]:
    """Every arithmetic node whose operand is weather-valued, as (module, function, expr, line).

    Flow-sensitive within a function, in source order: an assignment from a
    weather value taints its targets, and a later assignment from anything else
    clears them. Arithmetic inside a branch whose test is weather-valued counts
    too, because `if state == "RAIN": total *= 0.9` is the likeliest way weather
    would ever reach a number. String building, tuple or list concatenation, and
    a timestamp plus a `timedelta` (a capture's expiry) are not arithmetic.
    """

    hits = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tainted: set[str] = set()
        controlled: set[int] = set()
        ordered = sorted((n for n in ast.walk(fn) if hasattr(n, "lineno")),
                         key=lambda n: (n.lineno, n.col_offset))
        for node in ordered:
            if isinstance(node, (ast.If, ast.While)) and weather_valued(node.test, tainted):
                controlled.update(id(sub) for part in (*node.body, *node.orelse) for sub in ast.walk(part))
            if isinstance(node, ast.Match) and weather_valued(node.subject, tainted):
                controlled.update(id(sub) for case in node.cases for sub in ast.walk(case))
            if (isinstance(node, ast.IfExp) and weather_valued(node.test, tainted)
                    and any(isinstance(branch, ast.Constant) and type(branch.value) in (int, float)
                            for branch in (node.body, node.orelse))):
                hits.append((module, fn.name, ast.unparse(node), node.lineno))
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                weather = node.value is not None and weather_valued(node.value, tainted)
                for name in (n for t in targets for n in _names(t)):
                    (tainted.add if weather else tainted.discard)(name)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                weather = weather_valued(node.iter, tainted)
                for name in _names(node.target):
                    (tainted.add if weather else tainted.discard)(name)
            elif isinstance(node, ast.comprehension) and weather_valued(node.iter, tainted):
                tainted.update(_names(node.target))
            operands = _operands(node)
            if operands is None:
                continue
            if isinstance(node, (ast.BinOp, ast.AugAssign)) and any(map(_not_a_quantity, operands)):
                continue
            if id(node) in controlled or any(weather_valued(operand, tainted) for operand in operands):
                hits.append((module, fn.name, ast.unparse(node), node.lineno))
    return hits


def _all_hits():
    return [hit for path in sorted(SRC.glob("*.py"))
            for hit in arithmetic_on_weather(path.read_text(encoding="utf-8"), path.name)]


# ----------------------------------------------------------------- R24, where weather is read

def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def weather_reads(source: str) -> list[tuple[str, str]]:
    """Every read of a weather or roof value, as (enclosing function, expression).

    A loaded name or attribute that says weather or roof, and a string key that
    does when it indexes, is fetched with `.get`, or is compared. Module-level
    code is `<module>`.
    """

    tree = ast.parse(source)
    parents = _parents(tree)

    def owner(node: ast.AST) -> str:
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return "<module>"

    found = []
    for node in ast.walk(tree):
        read = None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and WEATHER.search(node.id):
            read = node
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) and WEATHER.search(node.attr):
            read = node
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and WEATHER.search(node.value):
            parent = parents.get(node)
            if isinstance(parent, ast.Subscript) and parent.slice is node:
                read = parent
            elif (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute)
                  and parent.func.attr == "get" and parent.args and parent.args[0] is node):
                read = parent
            elif isinstance(parent, ast.Compare):
                read = parent
        if read is not None:
            found.append((owner(node), ast.unparse(read)))
    return found


def _relative(path: Path) -> str:
    return path.relative_to(SRC.parent.parent).as_posix()


def _reads_outside_plumbing():
    counts: dict[tuple[str, str, str], int] = {}
    for base in (SRC, SCRIPTS):
        for path in sorted(base.glob("*.py")):
            module = _relative(path)
            if module in PLUMBING_MODULES:
                continue
            for function, expr in weather_reads(path.read_text(encoding="utf-8")):
                if (module, function) in PLUMBING_FUNCTIONS:
                    continue
                key = (module, function, expr)
                counts[key] = counts.get(key, 0) + 1
    return counts


def test_weather_is_read_only_where_it_moves_no_number():
    counts = _reads_outside_plumbing()
    pinned = {key: count for key, (count, _reason) in PINNED_READS.items()}
    unexpected = {key: n for key, n in counts.items() if n > pinned.get(key, 0)}
    assert not unexpected, (
        "Weather or a roof value is read in code outside the named plumbing. R24 let "
        "missing weather stop certification rather than construction only because it "
        "moves no number, and a derived roof (R26) is a value nobody observed. If this "
        "read feeds a projection, share or score, weather has to become a hard "
        "construction input again, which is a ruling, not a new pin: "
        f"{unexpected}"
    )
    stale = {key: (pinned[key], counts.get(key, 0)) for key in pinned if counts.get(key, 0) != pinned[key]}
    assert not stale, f"a pinned read moved or went away; re-pin it with its reason: {stale}"


def test_plumbing_never_includes_a_scoring_module():
    for module in PLUMBING_MODULES:
        assert Path(module).name not in SCORING_MODULES or not module.startswith("src/"), module
    for module, _function in PLUMBING_FUNCTIONS:
        assert module.startswith("src/nfl_dfs/"), module


def test_every_plumbing_entry_exists():
    root = SRC.parent.parent
    for module in PLUMBING_MODULES:
        assert (root / module).is_file(), module
    for module, function in PLUMBING_FUNCTIONS:
        tree = ast.parse((root / module).read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert function in names, (module, function)


@pytest.mark.parametrize("snippet", [
    "def f(team, total):\n    return total * weather_factor(team)\n",
    "def f(team, total):\n    return total * team.weather_multiplier()\n",
    "def f(team, total):\n    return ADJUST[team.weather_state] * total\n",
    "def f(team, total):\n    return FACTORS.get(team.weather_state, 1.0) * total\n",
    "def f(row, total):\n    state, basis = resolve_weather_state(row, None)\n    return total * (0.9 if state == 'RAIN' else 1.0)\n",
    "def f(t, total):\n    if t.weather_state != 'RAIN':\n        return total\n    return total * 0.9\n",
    "def f(t, total):\n    match t.weather_state:\n        case 'RAIN':\n            total *= 0.9\n    return total\n",
    "def f(t, total):\n    return adjust(total, t.weather_state)\n",
    "def f(row, total):\n    return total - float(row['ROOF'] == 'open')\n",
    "FACTOR = {'RAIN': 0.9}\ndef f(t):\n    return FACTOR[t.state]\nW = weather_scale()\n",
])
def test_the_read_rule_catches_every_shape_the_review_found(snippet):
    """The Session 03 review's patterns, each invisible to the arithmetic scan alone."""

    assert weather_reads(snippet)


# ----------------------------------------------------------------- R24, arithmetic

def test_no_arithmetic_reads_a_weather_or_roof_value():
    unexplained = [hit for hit in _all_hits() if hit[:3] not in NON_NUMERIC_SITES]
    assert not unexplained, (
        "A weather or roof value reached arithmetic. R24 let missing weather stop "
        "certification rather than construction only because weather moves no "
        "number, and a derived roof (R26) is a value nobody observed. Before this "
        "ships, weather must become a hard construction input again (a ruling), not "
        f"an entry in NON_NUMERIC_SITES: {unexplained}"
    )


def test_every_named_non_numeric_site_still_exists():
    """A stale exemption is a hole the next change could walk through."""

    seen = {hit[:3] for hit in _all_hits()}
    assert set(NON_NUMERIC_SITES) <= seen, set(NON_NUMERIC_SITES) - seen


def test_no_scoring_module_is_ever_exempt():
    assert not {module for module, _fn, _expr in NON_NUMERIC_SITES} & SCORING_MODULES


def test_every_scoring_module_exists():
    present = {path.name for path in SRC.glob("*.py")}
    assert SCORING_MODULES <= present, SCORING_MODULES - present


@pytest.mark.parametrize("snippet", [
    "def f(record):\n    return record.market_total * record.weather_factor\n",
    "def f(row):\n    w = row['WEATHER_STATE']\n    return 1.0 - float(w == 'RAIN')\n",
    "def f(row):\n    x = row.get('weather_state')\n    y = x\n    return y + 1\n",
    "def f(team):\n    for roof, games in team.venue_roof_history.items():\n        total = 0\n        total += games\n    return total\n",
    "def f(basis, total):\n    return total * (0.95 if basis.startswith(VENUE_ROOF_BASIS) else 1.0)\n",
    "def f(basis, total):\n    return total - ('DERIVED_FROM_VENUE_ROOF_HISTORY' in basis)\n",
    "def f(t, total):\n    if t.weather_state == 'RAIN':\n        total *= 0.9\n    return total\n",
    "def f(t, total):\n    windy = t.weather_state in {'WIND', 'SNOW'}\n    return total * (1 - 0.1 * windy)\n",
    "def f(t, total):\n    return ADJUST[t.weather_state] * total\n",
    "def f(t, total):\n    return FACTORS.get(t.weather_state, 1.0) * total\n",
    "def f(t, total):\n    match t.weather_state:\n        case 'RAIN':\n            total *= 0.9\n    return total\n",
    "def f(t):\n    return 0.9 if t.weather_state == 'RAIN' else 1.0\n",
    "def f(t):\n    return -t.weather_state\n",
    "import math\ndef f(t):\n    return math.log(t.roof_open_rate)\n",
])
def test_the_scan_catches_weather_reaching_a_number(snippet):
    """Mutation checks: each snippet wires weather or a roof into arithmetic."""

    assert arithmetic_on_weather(snippet, "projection.py")


@pytest.mark.parametrize("snippet", [
    "def f(state):\n    return 'weather_state must be ' + state.weather_state\n",
    "def f(a, b):\n    return a.weather_blockers + (b,)\n",
    "def f(raw, payload):\n    raw = payload.get('weather_state')\n    raw = payload.get('ticket')\n    return float(raw)\n",
    "def f(team):\n    return f'{team.weather_state}' + 'x'\n",
    "def f(t, states):\n    if t.weather_state not in states:\n        raise ValueError('WEATHER_STATE_UNSUPPORTED')\n    return t\n",
    "def f(weather_observed_at):\n    if weather_observed_at:\n        return weather_observed_at + timedelta(hours=6)\n",
])
def test_the_scan_leaves_text_and_reassigned_names_alone(snippet):
    assert not arithmetic_on_weather(snippet, "cowork.py")


# ----------------------------------------------------------------- R24, behavioural

def test_a_derived_roof_moves_no_prior_score(tmp_path):
    """Every weather state, the R26 derived one included, scores identically."""

    derived, basis = resolve_weather_state(
        {"home_team": "DAL", "roof": ""},
        None,
        venue_roof_history={"DAL": {"closed": 17}},
        venue_roof_seasons=(2025, 2026),
    )
    assert basis.startswith(VENUE_ROOF_BASIS)
    assert derived in WEATHER_STATES

    slate, model, _contract, splits = _prepared(tmp_path)
    baseline_scores = score_pool(slate, model, splits).by_dk_id
    baseline_volumes = team_volumes(model, splits)
    assert baseline_scores and any(value > 0 for value in baseline_scores.values())
    for state in sorted(WEATHER_STATES | {derived}):
        varied = replace(model, teams=tuple(replace(team, weather_state=state) for team in model.teams))
        assert all(team.weather_state == state for team in varied.teams)
        assert score_pool(slate, varied, splits).by_dk_id == baseline_scores, state
        assert team_volumes(varied, splits) == baseline_volumes, state


def test_an_unobserved_game_moves_no_prior_score(tmp_path):
    """Session 09 (R28): a game nobody observed resolves to UNOBSERVED instead of
    stopping, and it is a member the loop above already scores identically."""

    unobserved, basis = resolve_weather_state({"home_team": "GB", "roof": "outdoors"}, None)
    assert (unobserved, basis) == ("UNOBSERVED", "WEATHER_UNOBSERVED:roof=outdoors")
    assert unobserved in WEATHER_STATES

    slate, model, _contract, splits = _prepared(tmp_path)
    varied = replace(model, teams=tuple(replace(team, weather_state=unobserved) for team in model.teams))
    assert score_pool(slate, varied, splits).by_dk_id == score_pool(slate, model, splits).by_dk_id
    assert team_volumes(varied, splits) == team_volumes(model, splits)


# ================================================================= Session 03b
# The gate registry: every blocker code emitted under src/nfl_dfs/ has a family,
# and every family has a class, what it stops and the authority it answers to.

REPO = SRC.parent.parent

# What a blocker literal is. The text of a string that opens with an upper-snake
# token which ends the string or is followed by ":" (the repo's CODE:detail
# form). Any other continuation, a space and prose, is a message that happens to
# open with an enum name, not a code. It counts only where it is emitted:
#
#   raise     the first argument of a raised exception;
#   build     the first argument, or `code=`, of a call whose name says it builds
#             a blocker (an exception class, `_problem`, `_issue`, `QAFinding`,
#             `GateRegistry.limitation`, since Session 04);
#   collect   appended, extended, added or inserted onto, or `+=`-ed onto, a
#             holder: a name that says blocker, reason, problem and the like, or
#             a local that only ever holds one (`target = a if x else blockers`);
#             a display that spreads a holder (`[*blockers, "CODE"]`); the value
#             of a `"blockers"` key;
#   assign    assigned to a name like one; in a tuple target, a slot named
#             for blockers or problems, or `reason` beside the action "BLOCK"
#             (`action, reason = "BLOCK", "CODE"`), from a display or from the
#             tuples a called function returns;
#   keyword   a keyword argument named for a blocker or reason, or `code`;
#   blocking  compared inside a function or property named for blocking.
#
# Each position follows conditional expressions, `and`/`or`, collection
# displays and comprehensions, starred items, the left operand of `+` or `%`,
# nested builder calls, a local assigned a code, and a call to a function whose
# returned displays hold codes. An interpolation inside the token is resolved
# where the source fixes it: a parameter from the literal arguments at every
# call site, a loop variable from a literal it iterates (a display, a local
# bound to one, a dict's keys or items), `.upper()` applied. One that stays open
# is kept as `*`, and the code is a template whose codes the registry lists
# under `expansions`. The scan covers src/nfl_dfs/*.py, which is what the card
# names; scripts/ emit their own codes and are not in the registry.
BLOCKER_NAME = re.compile(r"block|reason|failure|problem|refus|error|issue|finding|limitation", re.I)
KEYWORD_NAME = re.compile(r"block|reason|refus|^code$", re.I)
KEY_NAME = re.compile(r"^blockers?$")
# A tuple slot is a blocker when named like a holder; a slot named `reason` only
# beside the literal action "BLOCK", since the same slot names why a person was
# selected, excluded or a model kept.
SLOT_NAME = re.compile(r"block|problem|refus|failure|error|issue|finding", re.I)
CODE_TEXT = re.compile(r"(?:[A-Z][A-Z0-9]*|\*)(?:_(?:[A-Z0-9]+|\*))+")
_DEPTH = 3

# Codes the scan cannot see, each with the source text that still emits it. A
# pin the scan starts to see is stale and fails, as does one whose text is gone.
UNSCANNED_CODES = {
    "NO_AUTHORIZED_ROWS": ("release.py", '_integrity("NO_AUTHORIZED_ROWS"',
                           "built through release._integrity, which hard-codes V, FILE and a provenance"),
    "UNFILLED_AUTHORIZED_ROWS": ("release.py", '_integrity("UNFILLED_AUTHORIZED_ROWS"',
                                 "built through release._integrity, which hard-codes V, FILE and a provenance"),
    "MODELED_BANK_INFEASIBILITY": ("classic_portfolio.py", '"MODELED_BANK_INFEASIBILITY"',
                                   "a C2 selection status; CLAUDE.md names it a rung trigger"),
    "INCOMPLETE_BANK_EXHAUSTION": ("classic_portfolio.py", '"INCOMPLETE_BANK_EXHAUSTION"',
                                   "a C2 selection status; CLAUDE.md names it a rung trigger"),
    "PORTFOLIO_SELECTION_TIMEOUT": ("classic_portfolio.py", 'status = "PORTFOLIO_SELECTION_TIMEOUT"',
                                    "a C2 selection status"),
    "PORTFOLIO_SELECTION_SEARCH_LIMIT": ("classic_portfolio.py", 'status = "PORTFOLIO_SELECTION_SEARCH_LIMIT"',
                                         "a C2 and SD3 selection status"),
    "PORTFOLIO_SELECTION_SOLVER_ERROR": ("classic_portfolio.py", 'status = "PORTFOLIO_SELECTION_SOLVER_ERROR"',
                                         "a C2 and SD3 selection status"),
    "PORTFOLIO_SELECTION_TIME_LIMIT": ("portfolio_enforcement.py", 'status = "PORTFOLIO_SELECTION_TIME_LIMIT"',
                                       "an SD3 selection status"),
    "MODELED_BANK_INFEASIBLE_PROVEN": ("portfolio_enforcement.py", '"MODELED_BANK_INFEASIBLE_PROVEN"',
                                       "an SD3 selection status"),
    "CANDIDATE_BANK_EXHAUSTED_INCOMPLETE": ("portfolio_enforcement.py", '"CANDIDATE_BANK_EXHAUSTED_INCOMPLETE"',
                                            "an SD3 selection status"),
    "CLASSIC_C3_SCALE_REPLAY_MISMATCH": ("classic_scale_acceptance.py", '"CLASSIC_C3_SCALE_REPLAY_MISMATCH"',
                                         "the C3 scale harness's replay status"),
    "REFEREE_SAFETY_OR_HARD_CONSTRAINT_FAILURE": ("qa.py", 'return True, "REFEREE_SAFETY_OR_HARD_CONSTRAINT_FAILURE"',
                                                  "qa.referee_blocks returns it as the reason beside True"),
    "REFEREE_SIGN_DISAGREEMENT": ("qa.py", '"REFEREE_SIGN_DISAGREEMENT"',
                                  "qa.referee_blocks returns it as the reason beside True"),
}

# Strings the scan reads that block nothing. The scan is flow-insensitive: in
# `offensive_roles`, `blocked.append(f"{reason}:...")` runs only when the action
# is BLOCK, but `reason` also takes the reasons for the other actions. A pin the
# scan stops seeing is stale and fails.
NOT_BLOCKERS = {
    code: ("offensive_roles.py", f'"{action}", "{code}"')
    for code, action in (
        ("HISTORICAL_ROLE_UNCONFIRMED", "DIAGNOSTIC"),
        ("PARTICIPATION_PRECEDENCE", "EXCLUDE"),
        ("EXPLICIT_TEAM_ALLOCATION", "SELECT"),
        ("OFFENSIVE_MISSING_HISTORY", "EXCLUDE"),
        ("OFFENSIVE_TRANSFER_PRIOR_UNVERIFIED", "DIAGNOSTIC"),
        ("OFFENSIVE_TRANSFER_PRIOR_ZERO", "EXCLUDE"),
        ("OFFENSIVE_OBSERVED_HISTORY_ZERO", "EXCLUDE"),
    )
}

# Emitted codes no registry can hold: the Entry ID is inside the token, so the
# code differs per row. Each is a defect for the session that next touches its
# emitter, which should write a fixed code such as `LINEUP_INVALID:<entry_id>:...`.
# Session 04 did that for `LINEUP_{entry_id}:` in certification and the review
# export; late swap's three are Session 12's.
UNREGISTRABLE_TEMPLATES = {
    "PRIOR_*": (("late_swap.py", 'f"{label}_{entry_id}:{problem}"'),),
    "CURRENT_*": (("late_swap.py", 'f"{label}_{entry_id}:{problem}"'),),
    "PROPOSED_*": (("late_swap.py", 'f"{label}_{entry_id}:{problem}"'),),
}


def _callee(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _head(text: str) -> str | None:
    """The code `text` opens with, or None when a message or nothing opens it."""

    head = re.match(r"[A-Z0-9_*]*", text).group(0)
    rest = text[len(head):]
    if rest and not rest.startswith(":"):
        return None
    if not CODE_TEXT.fullmatch(head) or not re.search(r"[A-Z]", head):
        return None
    return head


class _Scan:
    """Blocker literals across a set of modules, with the calls between them."""

    def __init__(self, sources: dict[str, str]):
        self.trees = {name: ast.parse(text) for name, text in sources.items()}
        self.parent: dict[ast.AST, ast.AST] = {}
        self.module: dict[ast.AST, str] = {}
        self.functions: dict[str, list[tuple[str, ast.AST]]] = {}
        self.calls: dict[str, list[tuple[str, ast.Call]]] = {}
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                self.module[node] = name
                for child in ast.iter_child_nodes(node):
                    self.parent[child] = node
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.functions.setdefault(node.name, []).append((name, node))
                elif isinstance(node, ast.Call) and _callee(node.func):
                    self.calls.setdefault(_callee(node.func), []).append((name, node))
        self.found: dict[str, set[str]] = {}

    # -- scope ---------------------------------------------------------------

    def _ancestors(self, node: ast.AST):
        while node in self.parent:
            node = self.parent[node]
            yield node

    def _function(self, node: ast.AST):
        return next((a for a in self._ancestors(node)
                     if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))), None)

    def _defs(self, name: str, at: ast.AST):
        """The functions a call to `name` at `at` can reach: its own module first."""

        local = [f for m, f in self.functions.get(name, ()) if m == self.module[at]]
        if local or name.startswith("_"):
            return local
        return [f for _m, f in self.functions.get(name, ())]

    def _assigned(self, name: str, at: ast.AST) -> list[ast.AST]:
        """Values a local `name` is assigned in the function around `at`, or its module."""

        scope = self._function(at) or self.trees[self.module[at]]
        values = []
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        values.append(node.value)
                    elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                        values += [v for t, v in zip(target.elts, node.value.elts)
                                   if isinstance(t, ast.Name) and t.id == name]
        return values

    def is_holder(self, node: ast.AST, depth: int = 2) -> bool:
        if BLOCKER_NAME.search(_callee(node)):
            return True
        if isinstance(node, ast.Name) and depth > 0:
            values = self._assigned(node.id, node)
            return bool(values) and all(self._only_holders(v, depth - 1) for v in values)
        return False

    def _only_holders(self, node: ast.AST, depth: int) -> bool:
        if isinstance(node, ast.IfExp):
            return self._only_holders(node.body, depth) and self._only_holders(node.orelse, depth)
        if isinstance(node, ast.BoolOp):
            return all(self._only_holders(v, depth) for v in node.values)
        return isinstance(node, (ast.Name, ast.Attribute)) and self.is_holder(node, depth)

    # -- the values an interpolation or a loop variable can take -------------

    def _values(self, node: ast.AST, at: ast.AST, depth: int) -> list[str] | None:
        if depth <= 0:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            return self._render(node, depth - 1)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "upper" and not node.args):
            inner = self._values(node.func.value, at, depth)
            return None if inner is None else [value.upper() for value in inner]
        if isinstance(node, ast.Name):
            return self._name_values(node.id, at, depth)
        return None

    def _name_values(self, name: str, at: ast.AST, depth: int) -> list[str] | None:
        for scope in self._ancestors(at):
            loops = [scope] if isinstance(scope, (ast.For, ast.AsyncFor)) else (
                scope.generators if isinstance(scope, (ast.GeneratorExp, ast.ListComp, ast.SetComp)) else [])
            for loop in loops:
                path = self._target_path(loop.target, name)
                if path is not None:
                    return self._iterated(loop.iter, path, loop, depth)
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = [a.arg for a in (*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs)]
                if name in params:
                    return self._argument_values(scope, name, depth)
                values = self._assigned(name, at)
                if values:
                    out: list[str] = []
                    for value in values:
                        got = self._values(value, value, depth - 1)
                        out += ["*"] if got is None else got
                    return out
                return None
        return None

    @staticmethod
    def _target_path(target: ast.AST, name: str) -> tuple[int, ...] | None:
        if isinstance(target, ast.Name):
            return () if target.id == name else None
        if isinstance(target, ast.Tuple):
            for index, item in enumerate(target.elts):
                inner = _Scan._target_path(item, name)
                if inner is not None:
                    return (index, *inner)
        return None

    def _elements(self, node: ast.AST, at: ast.AST, depth: int) -> list[ast.AST] | None:
        """The items a literal iterable yields, following a local bound to one."""

        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return list(node.elts)
        if isinstance(node, ast.Dict):
            return list(node.keys)
        if isinstance(node, ast.Call):
            if _callee(node.func) in {"sorted", "tuple", "list", "reversed", "set"} and len(node.args) == 1:
                return self._elements(node.args[0], at, depth)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"items", "keys", "values"}:
                source = node.func.value
                mapping = self._one_display(source, at) if isinstance(source, ast.Name) else source
                if isinstance(mapping, ast.Dict):
                    if node.func.attr == "keys":
                        return list(mapping.keys)
                    if node.func.attr == "values":
                        return list(mapping.values)
                    return [ast.Tuple(elts=[k, v]) for k, v in zip(mapping.keys, mapping.values)]
        if isinstance(node, ast.Name) and depth > 0:
            display = self._one_display(node, at)
            return None if display is None else self._elements(display, at, depth - 1)
        return None

    def _one_display(self, name: ast.Name, at: ast.AST) -> ast.AST | None:
        values = self._assigned(name.id, at)
        return values[0] if len(values) == 1 else None

    def _iterated(self, iterable: ast.AST, path: tuple[int, ...], at: ast.AST, depth: int) -> list[str] | None:
        items = self._elements(iterable, at, depth)
        if items is None:
            return None
        out: list[str] = []
        for item in items:
            for index in path:
                if not isinstance(item, ast.Tuple) or index >= len(item.elts):
                    return None
                item = item.elts[index]
            got = self._values(item, at, depth - 1)
            out += ["*"] if got is None else got
        return out

    def _argument_values(self, function: ast.AST, name: str, depth: int) -> list[str] | None:
        positional = [a.arg for a in (*function.args.posonlyargs, *function.args.args)]
        defaults = dict(zip(positional[len(positional) - len(function.args.defaults):], function.args.defaults))
        defaults.update({a.arg: d for a, d in zip(function.args.kwonlyargs, function.args.kw_defaults) if d})
        sites = [call for module, call in self.calls.get(function.name, ())
                 if module == self.module[function] or not function.name.startswith("_")]
        if not sites:
            return None
        out: list[str] = []
        for call in sites:
            argument = next((k.value for k in call.keywords if k.arg == name), None)
            if argument is None and name in positional:
                index = positional.index(name)
                if positional and positional[0] in {"self", "cls"} and isinstance(call.func, ast.Attribute):
                    index -= 1
                if 0 <= index < len(call.args) and not any(isinstance(a, ast.Starred) for a in call.args[:index + 1]):
                    argument = call.args[index]
            if argument is None:
                argument = defaults.get(name)
            got = None if argument is None else self._values(argument, call, depth - 1)
            out += ["*"] if got is None else got  # an open site keeps the template
        return out

    def _render(self, node: ast.JoinedStr, depth: int) -> list[str] | None:
        """Every text an f-string can open with; an open interpolation stays `*`."""

        texts = [""]
        for part in node.values:
            if all(re.match(r"[A-Z0-9_*]*", text).end() < len(text) for text in texts):
                break  # every text's code has ended; the rest is detail
            if isinstance(part, ast.Constant):
                texts = [text + str(part.value) for text in texts]
                continue
            values = self._values(part.value, part, depth)
            if values is None:
                values = ["*"]
            texts = [text + value for text in texts for value in values][:256]
        return texts

    # -- emitting positions ------------------------------------------------

    def _strings(self, node: ast.AST, depth: int = _DEPTH):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for item in node.elts:
                yield from self._strings(item, depth)
        elif isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            yield from self._strings(node.elt, depth)
        elif isinstance(node, ast.IfExp):
            yield from self._strings(node.body, depth)
            yield from self._strings(node.orelse, depth)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                yield from self._strings(value, depth)
        elif isinstance(node, ast.Starred):
            yield from self._strings(node.value, depth)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            yield from self._strings(node.left, depth)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield from self._render(node, _DEPTH + 1) or ()
        elif isinstance(node, ast.Name) and depth > 0:
            for value in self._assigned(node.id, node):
                yield from self._strings(value, depth - 1)
        elif isinstance(node, ast.Call) and depth > 0:
            if BLOCKER_NAME.search(_callee(node.func)):
                if node.args:
                    yield from self._strings(node.args[0], depth)
                for keyword in node.keywords:
                    if keyword.arg == "code":
                        yield from self._strings(keyword.value, depth)
            else:
                for function in self._defs(_callee(node.func), node):
                    for inner in ast.walk(function):
                        if isinstance(inner, ast.Return) and isinstance(
                                inner.value, (ast.Tuple, ast.List, ast.Set, ast.Constant)):
                            yield from self._strings(inner.value, depth - 1)

    def _record(self, node: ast.AST) -> None:
        for text in self._strings(node):
            code = _head(text)
            if code:
                self.found.setdefault(code, set()).add(self.module[node])

    def _returned_at(self, call: ast.Call, index: int):
        for function in self._defs(_callee(call.func), call):
            for inner in ast.walk(function):
                if (isinstance(inner, ast.Return) and isinstance(inner.value, ast.Tuple)
                        and index < len(inner.value.elts)):
                    yield inner.value.elts[index]

    def scan(self) -> dict[str, set[str]]:
        for tree in self.trees.values():
            for node in ast.walk(tree):
                self._visit(node)
        return self.found

    def _visit(self, node: ast.AST) -> None:
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
            self._record(node.exc.args[0])
        elif isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr in {"append", "extend", "add", "insert"}
                    and self.is_holder(func.value) and node.args):
                self._record(node.args[-1])
            elif BLOCKER_NAME.search(_callee(func)) and node.args:
                self._record(node.args[0])
            for keyword in node.keywords:
                if keyword.arg and KEYWORD_NAME.search(keyword.arg):
                    self._record(keyword.value)
        elif (isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add)
              and self.is_holder(node.target)):
            self._record(node.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if KEYWORD_NAME.search(_callee(target)):
                    self._record(node.value)
                elif isinstance(target, ast.Tuple):
                    blocking = isinstance(node.value, ast.Tuple) and any(
                        isinstance(v, ast.Constant) and v.value == "BLOCK" for v in node.value.elts)
                    for index, item in enumerate(target.elts):
                        name = _callee(item)
                        if not (SLOT_NAME.search(name) or (blocking and re.search("reason", name, re.I))):
                            continue
                        if isinstance(node.value, ast.Tuple) and index < len(node.value.elts):
                            self._record(node.value.elts[index])
                        elif isinstance(node.value, ast.Call):
                            for value in self._returned_at(node.value, index):
                                self._record(value)
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if any(isinstance(item, ast.Starred) and self.is_holder(item.value) for item in node.elts):
                for item in node.elts:
                    if not isinstance(item, ast.Starred):
                        self._record(item)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and KEY_NAME.match(key.value):
                    self._record(value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "block" in node.name:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Compare):
                    for comparator in inner.comparators:
                        self._record(comparator)


def blocker_literals(source: str) -> dict[str, set[str]]:
    """Every blocker literal in one source text, with the module that emits it."""

    return _Scan({"snippet.py": source}).scan()


@lru_cache(maxsize=1)
def scanned_codes() -> dict[str, frozenset[str]]:
    """Each blocker literal under src/nfl_dfs/ and the modules that emit it."""

    sources = {path.name: path.read_text(encoding="utf-8") for path in sorted(SRC.glob("*.py"))}
    return {code: frozenset(modules) for code, modules in _Scan(sources).scan().items()}


@lru_cache(maxsize=1)
def registry():
    return load_gate_registry()


def _module_strings(module: str) -> tuple[set[str], set[str]]:
    """A module's string constants, and its f-strings with `*` for each interpolation."""

    constants: set[str] = set()
    rendered: set[str] = set()
    for node in ast.walk(ast.parse((SRC / module).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            constants.add(node.value)
        elif isinstance(node, ast.JoinedStr):
            rendered.add("".join(v.value if isinstance(v, ast.Constant) else "*" for v in node.values))
    return constants, rendered


def _held(part: str, constants: set[str], rendered: set[str], depth: int = 1) -> bool:
    if part in constants or part.lower() in constants:
        return True
    return depth > 0 and any(
        all(_held(inner, constants, rendered, depth - 1) for inner in binding)
        for template in rendered if "*" in template and "_" in template
        for binding in template_bindings(template, part)
    )


# ----------------------------------------------------------------- the file

# The registry's bytes, pinned. A reclassification is a deliberate change, so
# it moves this line too; `docs/DATA_CONTRACTS.md` names the same hash.
REGISTRY_SHA256 = "941f6d471a39c8170529b2691f2f297445ef1f18c060b3e7c97910f50cfd9ce1"


def test_the_registry_is_the_pinned_bytes():
    raw = DEFAULT_REGISTRY_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REGISTRY_SHA256, (
        "config/gate_registry_v1.json changed; re-pin REGISTRY_SHA256 here and in "
        "docs/DATA_CONTRACTS.md with the change that moved it"
    )
    assert load_gate_registry(expected_sha256=REGISTRY_SHA256).sha256 == REGISTRY_SHA256
    assert REGISTRY_SHA256 in (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    assert DEFAULT_REGISTRY_PATH == REPO / "config" / "gate_registry_v1.json"
    assert json.loads(raw)["schema_version"] == "nfl_gate_registry_v1"
    with pytest.raises(GateRegistryError, match="GATE_REGISTRY_SHA256_MISMATCH"):
        load_gate_registry(expected_sha256="0" * 64)


def test_the_registry_lists_one_code_per_line():
    """Reviewable by diff: a code's family changes on its own line."""

    lines = DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8").splitlines()
    for code, family in registry().codes.items():
        assert f'    "{code}": "{family}",' in lines or f'    "{code}": "{family}"' in lines, code


# ----------------------------------------------------------------- completeness

def _emitted_codes() -> dict[str, frozenset[str]]:
    return {code: modules for code, modules in scanned_codes().items()
            if code not in NOT_BLOCKERS and code not in UNREGISTRABLE_TEMPLATES}


def test_every_blocker_literal_has_an_entry():
    codes, templates = set(registry().codes), set(registry().expansions)
    missing = {code: sorted(modules) for code, modules in _emitted_codes().items()
               if code not in (templates if "*" in code else codes)}
    unseen = sorted(code for code in UNSCANNED_CODES if code not in codes)
    assert not missing and not unseen, (
        "A blocker code has no entry in config/gate_registry_v1.json. Give it a family "
        "(class, stops, provenance) before it ships; a template the source leaves open "
        f"lists its codes under expansions: missing={missing} unseen={unseen}"
    )


def test_every_entry_is_still_emitted():
    """A registered code nothing emits any more is stale, and would hide a renamed one."""

    emitted = _emitted_codes()
    expanded = {code for codes in registry().expansions.values() for code in codes}
    stale = sorted(code for code in registry().codes
                   if code not in emitted and code not in UNSCANNED_CODES and code not in expanded)
    stale_templates = sorted(template for template in registry().expansions if template not in emitted)
    assert not stale and not stale_templates, (stale, stale_templates)


def test_every_expansion_names_values_its_module_holds():
    """An expansion is read off the source: each `*` part is a value the module spells."""

    for template, codes in registry().expansions.items():
        held = [_module_strings(module) for module in sorted(scanned_codes()[template])]
        for code in codes:
            assert any(
                all(_held(part, constants, rendered) for part in binding)
                for constants, rendered in held
                for binding in template_bindings(template, code)
            ), (template, code)


def test_every_pin_is_live():
    """Each pinned code or template is still in the source text that emits it."""

    scanned = scanned_codes()
    for code, (module, text, why) in UNSCANNED_CODES.items():
        assert why
        assert text in (SRC / module).read_text(encoding="utf-8"), (code, module, text)
        assert code not in scanned, f"the scan now sees {code}; drop its pin"
    for code, (module, text) in NOT_BLOCKERS.items():
        assert text in (SRC / module).read_text(encoding="utf-8"), (code, module, text)
        assert code in scanned, f"the scan no longer reads {code}; drop it from NOT_BLOCKERS"
        assert code not in registry().codes, code
    for template, sites in UNREGISTRABLE_TEMPLATES.items():
        assert template in scanned, template
        assert template not in registry().expansions, template
        for module, text in sites:
            assert text in (SRC / module).read_text(encoding="utf-8"), (template, module, text)


# ----------------------------------------------------------------- class rules

def test_a_v_entry_never_stops_certification():
    """The Session 03 card's rule, on the registry itself."""

    for name, family in registry().families.items():
        if family.gate_class is GateClass.V:
            assert family.stops is not GateStops.CERTIFICATION, name


def test_every_family_carries_its_class_pair():
    """V stops the file; S a construction preference; P certification. Nothing else."""

    assert dict(ALLOWED_PAIRS) == {
        GateClass.V: GateStops.FILE,
        GateClass.S: GateStops.CONSTRUCTION_PREFERENCE,
        GateClass.P: GateStops.CERTIFICATION,
    }
    for name, family in registry().families.items():
        assert ALLOWED_PAIRS[family.gate_class] is family.stops, name
    assert {family.gate_class for family in registry().families.values()} == set(GateClass)


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_every_provenance_names_a_real_authority():
    claude = _normalized((REPO / "CLAUDE.md").read_text(encoding="utf-8"))
    roadmap = (REPO / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    rulings = _normalized(roadmap.split("### 2.5 Rulings in force", 1)[1].split("### 2.6", 1)[0])
    contracts = {
        line.lstrip("#").strip()
        for line in (REPO / "docs" / "DATA_CONTRACTS.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    }
    for name, family in registry().families.items():
        ref = _normalized(family.provenance.ref)
        assert ref, name
        if family.provenance.kind is ProvenanceKind.CLAUDE_MD_BOUNDARY:
            assert len(ref.split()) >= 4 and ref in claude, (name, ref)
        elif family.provenance.kind is ProvenanceKind.RULING:
            assert re.search(rf"(?<![\w-]){re.escape(ref)}(?![\w-])", rulings), (name, ref)
        else:
            assert ref in contracts, (name, ref)


def test_the_codes_release_builds_match_their_entries():
    """`release._integrity` hard-codes V, FILE and a provenance; the registry agrees."""

    built = [
        *derive_delivery_state(file_valid=False, authorized_entry_ids=(),
                               delivered_entry_ids=()).delivery_limitations,
        *derive_delivery_state(file_valid=True, authorized_entry_ids=("1", "2"),
                               delivered_entry_ids=("1",)).delivery_limitations,
    ]
    assert {item.code for item in built} == {
        "NO_AUTHORIZED_ROWS", "FILE_VALIDATION_INCOMPLETE", "UNFILLED_AUTHORIZED_ROWS",
    }
    for item in built:
        assert registry().limitation(item.code, entry_ids=item.entry_ids, detail=item.detail) == item


# Audit section 4 (issue #40), row by row: codes that emit its condition, and the
# classes it names. "S/P" rows accept either; R29 moves cross-entry uniqueness
# to V. The Showdown and Classic standalone-QA rows are scripts/ codes, outside
# the registry.
AUDIT_SECTION_4 = [
    ("unknown official DK ID; wrong slate, mode or draft group", {"V"},
     ["DRAFT_GROUP_MIXED_OR_BLANK", "CLASSIC_C3_DRAFT_GROUP_MISMATCH", "PORTFOLIO_POLICY_UNKNOWN_DK_ID",
      "READABLE_REVIEW_UNKNOWN_DK_ID", "CLASSIC_C3_MODE_MISMATCH", "CURRENT_TEMPLATE_MODE_MISMATCH",
      "SELECTED_ID_NOT_IN_CURRENT_POOL"]),
    ("roster count, slot eligibility, salary cap, a person twice", {"V"},
     ["PORTFOLIO_AUDIT_LINEUP_ILLEGAL", "SOLVER_PRODUCED_ILLEGAL_LINEUP", "READABLE_REVIEW_LINEUP_INVALID",
      "CLASSIC_PORTFOLIO_SOLVER_PRODUCED_ILLEGAL_LINEUP", "CLASSIC_AUDIT_LINEUP_ILLEGAL", "CLASSIC_C3_LINEUP_ILLEGAL"]),
    ("Entry ID mapping, extra IDs, missing rows, header, damaged final bytes", {"V"},
     ["PORTFOLIO_AUDIT_EXTRA_ENTRY_ID", "PORTFOLIO_AUDIT_MISSING_ENTRY_ID", "ENTRY_AUTHORIZATION_MISMATCH",
      "CLASSIC_C3_EXPORT_UNAUTHORIZED_BYTES_CHANGED", "FINAL_BYTE_MISMATCH",
      "WRITTEN_BYTES_DID_NOT_MATCH_THE_AUDITED_BYTES"]),
    ("replacing prefilled or locked cells without authority", {"V"},
     ["CLASSIC_C3_EXPORT_PREFILLED_AUTHORIZED_ENTRY", "ENTRY_BLANK_CELL_AUTHORITY_REQUIRED",
      "PRIOR_OUTPUT_CHANGED_DURING_LATE_SWAP"]),
    ("single contest, single fee, mixed prefilled and blank rows", {"P"},
     ["MULTI_CONTEST_ENTRY_FILE_UNSUPPORTED", "MIXED_ENTRY_FEES_UNSUPPORTED",
      "CURRENT_TEMPLATE_MUST_CONTAIN_ONE_CONTEST_ID", "CURRENT_TEMPLATE_MUST_BE_FULLY_PREFILLED"]),
    ("prohibited DraftKings automation or upload artifact", {"V"},
     ["CLASSIC_C3_DK_UPLOAD_ARTIFACT_PROHIBITED", "CLASSIC_C3_DK_UPLOAD_NAME_PROHIBITED"]),
    ("approved-source refusal: optional data is omitted, the boundary holds", {"P"},
     ["SOURCE_LICENSE_UNAPPROVED", "PARSER_VERSION_UNAPPROVED", "WEATHER_SOURCE_UNAPPROVED"]),
    ("explicit operator restriction", {"V"},
     ["CLASSIC_C3_EXACT_EXCLUSION_SELECTED", "CLASSIC_AUDIT_EXACT_EXCLUSION_BREACH",
      "SOLVER_SELECTED_AN_EXCLUDED_ROW"]),
    ("source, assignment or output hashes disagree; reused output path", {"V"},
     ["CLASSIC_ASSIGNMENT_POST_WRITE_HASH_MISMATCH", "POST_WRITE_HASH_MISMATCH",
      "SALARY_INPUT_CHANGED_BEFORE_SELECTION", "RUN_ID_COLLISION", "OUTPUT_EXISTS", "CLASSIC_C3_OUTPUT_EXISTS",
      "INPUT_BINDING", "OUTPUT_BINDING", "BUILD_ASSIGNMENT_HASH_MISMATCH", "FINAL_BYTE_AUDIT"]),
    ("provider identity, team crosswalk, history and split coverage", {"P"},
     ["FUZZY_IDENTITY_FORBIDDEN", "IDENTITY_NOT_ACCEPTED", "TEAM_CROSSWALK_INCOMPLETE",
      "TEAM_SPLIT_COVERAGE_MISSING", "OFFENSIVE_HISTORY_COVERAGE_REQUIRED"]),
    ("unrecognized DraftKings status; role or depth ambiguity", {"S", "P"},
     ["UNKNOWN_DK_STATUS", "STATUS_CLASSIFIED_BOTH_WAYS", "QB_DEPTH_EXCERPT_STARTER_NOT_UNIQUE",
      "DEPTH_ORDER_EMPTY", "PARTICIPATION_REMOVES_EVERY_PERSON", "SELECTABLE_POOL_TOO_SMALL"]),
    ("official activity for every selected Classic person", {"S", "P"},
     ["OFFICIAL_STATUS_STALE", "OFFICIAL_STATUS_FUTURE", "OFFICIAL_STATUS_INVALID", "OFFICIAL_STATUS_REQUIRED",
      "CLASSIC_C3_SELECTED_ACTIVITY_COVERAGE_MISMATCH", "OFFICIAL_STATUS_INCOMPLETE_FOR_SELECTED"]),
    ("offensive, kicker and QB role packages; unsupported numeric allocation", {"S", "P"},
     ["OFFENSIVE_CURRENT_ROLE_UNRESOLVED", "KICKER_ROLE_UNRESOLVED", "QB_DEPTH_SOURCE_EXPIRED_DURING_SELECTION",
      "OFFENSIVE_ROLE_NUMERICAL_SOURCE_REQUIRED"]),
    ("weather capture, roof, six-hour expiry, source binding", {"P"},
     ["WEATHER_CAPTURE_REQUIRED", "WEATHER_CAPTURE_STALE", "WEATHER_UNOBSERVED",
      "WEATHER_EVIDENCE_SOURCE_HASH_MISMATCH", "WEATHER_STATE_CONFLICT"]),
    ("market spread and total, and freshness", {"P"},
     ["SOURCE_VALUE_ABSENT", "SOURCE_VALUE_NOT_NUMERIC", "FUTURE_MARKET_EVIDENCE"]),
    ("prior and projection package schema, hash, expiry, artifacts", {"P"},
     ["PRIOR_PACKAGE_EXPIRED", "PRIOR_ARTIFACT_HASH_MISMATCH", "PROJECTION_PACKAGE_NOT_FRESH",
      "PACKAGE_LEDGER_SCHEMA_UNSUPPORTED", "PRIOR_ARTIFACT_MISSING"]),
    ("ownership, field, payouts, advertised value, ticket value, field size", {"P"},
     ["CONTEST_PAYOUT_REQUIRED", "FIELD_SIZE_REQUIRED", "TICKET_FACE_VALUE_REQUIRED",
      "ADVERTISED_PRIZE_VALUE_REQUIRED"]),
    ("malformed optional policy input", {"P"},
     ["CLASSIC_POLICY_JSON_INVALID", "CLASSIC_POLICY_UNKNOWN_FIELD", "PORTFOLIO_POLICY_SCHEMA_UNSUPPORTED",
      "PORTFOLIO_POLICY_FRACTION_TYPE_INVALID", "CLASSIC_POLICY_UNIQUENESS_TYPE_INVALID",
      "PORTFOLIO_POLICY_UNIQUENESS_TYPE_INVALID", "PORTFOLIO_POLICY_ENTRY_SET_EMPTY"]),
    ("a policy applied to the wrong people or entries", {"V"},
     ["CLASSIC_POLICY_ENTRY_ID_BINDING_MISMATCH", "PORTFOLIO_POLICY_ENTRY_ID_BINDING_MISMATCH",
      "PORTFOLIO_POLICY_SALARY_HASH_MISMATCH", "CLASSIC_PORTFOLIO_POLICY_ENTRY_HASH_MISMATCH"]),
    ("exposure, captain, team, game, group, stack and overlap bounds", {"S"},
     ["CLASSIC_AUDIT_PLAYER_BOUND", "CLASSIC_AUDIT_STACK_BOUND", "PORTFOLIO_AUDIT_CAPTAIN_CAP_EXCEEDED",
      "PORTFOLIO_AUDIT_PAIRWISE_OVERLAP_EXCEEDED", "CLASSIC_POLICY_TEAM_EXPOSURE_CAPACITY_INSUFFICIENT",
      "READABLE_REVIEW_CAPTAIN_EXPOSURE_EXCEEDED", "OVERLAP_LIMIT_BREACHED", "DUPLICATE_CAPTAIN_SELECTED",
      "CLASSIC_POLICY_UNIQUE_LINEUP_CAPACITY_INSUFFICIENT"]),
    ("cross-entry uniqueness and a distinct-lineup shortfall (R29)", {"V"},
     ["DUPLICATE_LINEUP_SELECTED", "CLASSIC_C3_CANONICAL_LINEUP_DUPLICATE", "PORTFOLIO_AUDIT_CANONICAL_DUPLICATE",
      "DUPLICATE_SELECTED_LINEUPS", "SOLVER_RETURNED_NO_LINEUP", "LINEUP_COUNT_BELOW_RESERVED_ENTRIES"]),
    ("candidate target, time or search limit, incomplete bank", {"S", "P"},
     ["CANDIDATE_BANK_TIMEOUT", "CANDIDATE_BANK_SEARCH_LIMIT", "CANDIDATE_BANK_TIME_LIMIT",
      "MODELED_BANK_INFEASIBILITY", "INCOMPLETE_BANK_EXHAUSTION", "PORTFOLIO_SELECTION_TIMEOUT"]),
    ("portfolio optimality proof or solver gap", {"P"},
     ["CLASSIC_C3_C2_JOINT_SELECTION_NOT_OPTIMAL_ACTUAL_BANK", "SOLVER_PROOF_OUTSIDE_LIMIT",
      "SOLVER_TIME_LIMIT_ACCEPTED_LINEUPS"]),
    ("simulation, sensitivity, dependence, duplication, exposure QA, referee", {"S", "P"},
     ["MATERIAL_SENSITIVITY", "NEGATIVE_DEPENDENCE", "DUPLICATION_CHOPS_BELOW_FEE", "EXPOSURE_OUTSIDE_ENVELOPE",
      "DESIGN_SHARE_CONSERVATION_FAILED", "INTERVAL_COVERAGE", "INSUFFICIENT_SAMPLE", "REFEREE_SIGN_DISAGREEMENT"]),
    ("readable JSON and HTML, workbook, render or write failure", {"P"},
     ["READABLE_REVIEW_JSON_WRITE_MISMATCH", "CLASSIC_C3_READABLE_HTML_WRITE_MISMATCH",
      "READABLE_REVIEW_FAILED", "CLASSIC_C3_READABLE_REVIEW_FAILED"]),
    ("a readable review that reveals submission corruption", {"V"},
     ["READABLE_REVIEW_OUTPUT_ASSIGNMENT_ROSTER_MISMATCH", "READABLE_REVIEW_SALARY_REPARSE_MISMATCH",
      "READABLE_REVIEW_BULK_ENTRY_CSV_SHA256_MISMATCH"]),
    ("host probe and environment readiness", {"P"}, ["ENVIRONMENT_DOCTOR_FAILED"]),
    ("the prior quality certification a late swap starts from", {"P"},
     ["PRIOR_MANIFEST_NOT_CERTIFIED", "PRIOR_CERTIFIED_MANIFEST_HAS_BLOCKERS"]),
    ("swap eligibility, current state and unchanged locked cells", {"V"},
     ["CURRENT_TEMPLATE_INVALID", "CURRENT_CONTEST_ID_DIFFERS_FROM_CERTIFIED_PRIOR",
      "PRIOR_CERTIFIED_OUTPUT_HASH_MISMATCH", "PRIOR_OUTPUT_CHANGED_DURING_LATE_SWAP"]),
    ("a stale process budget", {"P"}, ["CERTIFICATION_DEADLINE_EXCEEDED", "LATE_SWAP_DEADLINE_EXCEEDED"]),
]


@pytest.mark.parametrize("row,classes,codes", AUDIT_SECTION_4, ids=[row for row, _c, _k in AUDIT_SECTION_4])
def test_the_audit_section_4_rows_land_in_the_classes_it_names(row, classes, codes):
    for code in codes:
        family = registry().family_of(code)
        assert family.gate_class.value in classes, (row, code, family.name, family.gate_class.value)


def test_cross_entry_uniqueness_is_v_by_r29():
    family = registry().families["distinct_lineups"]
    assert (family.gate_class, family.stops) == (GateClass.V, GateStops.FILE)
    assert (family.provenance.kind, family.provenance.ref) == (ProvenanceKind.RULING, "R29")


def test_r28_absorbs_the_p1_hard_stop():
    """Ben, 2026-09-23: R28 absorbs the 2026-09-19 P1 hard stop.

    The unresolved material role change is a current-role truth claim: the
    person is left out of the pool, never selected on the old-team share, the
    file ships, and the code travels as a named limitation. It stops
    certification, never the file. Session 09 makes the run do it.
    """

    family = registry().family_of("OFFENSIVE_UNRESOLVED_MATERIAL_ROLE_CHANGE")
    assert (family.gate_class, family.stops) == (GateClass.P, GateStops.CERTIFICATION)
    assert (family.provenance.kind, family.provenance.ref) == (ProvenanceKind.RULING, "R28")
    assert "role_change_hard_stop" not in registry().families


def test_the_rung_ladder_triggers_are_construction_preferences():
    """CLAUDE.md drops a rung on these four; the ladder relaxes only preferences."""

    for code in ("MODELED_BANK_INFEASIBILITY", "INCOMPLETE_BANK_EXHAUSTION",
                 "CANDIDATE_BANK_TIMEOUT", "CANDIDATE_BANK_SEARCH_LIMIT"):
        assert registry().family_of(code).stops is GateStops.CONSTRUCTION_PREFERENCE, code


# ----------------------------------------------------------------- building a limitation

def test_a_limitation_takes_its_metadata_from_the_registry():
    item = registry().limitation("CLASSIC_C3_EXPORT_ROSTER_MISMATCH", entry_ids=("100",),
                                 people=("123",), detail="slot 2")
    family = registry().family_of("CLASSIC_C3_EXPORT_ROSTER_MISMATCH")
    assert (item.gate_class, item.stops, item.provenance) == (family.gate_class, family.stops, family.provenance)
    assert (item.entry_ids, item.people, item.detail) == (("100",), ("123",), "slot 2")
    weather = registry().limitation("WEATHER_CAPTURE_STALE")
    assert (weather.gate_class, weather.stops) == (GateClass.P, GateStops.CERTIFICATION)


def test_every_registered_code_is_exact_and_every_template_expanded():
    assert not [code for code in registry().codes if "*" in code]
    assert set(registry().expansions) == {
        "*_PASSING_RECEIVING_ACCOUNTING_FAILED", "*_SHARE_CONSERVATION_FAILED",
    }
    assert registry().family_of("REFEREE_SHARE_CONSERVATION_FAILED").gate_class is GateClass.P


@pytest.mark.parametrize("code,error", [
    ("NOT_A_REGISTERED_CODE", "GATE_REGISTRY_CODE_UNREGISTERED"),
    ("CLASSIC_C3_WEATHER_CAPTURE_MISMATCH", "GATE_REGISTRY_CODE_UNREGISTERED"),
    ("READABLE_REVIEW_DK_ID_MISSING", "GATE_REGISTRY_CODE_UNREGISTERED"),
    ("OTHER_SHARE_CONSERVATION_FAILED", "GATE_REGISTRY_CODE_UNREGISTERED"),
    ("lowercase_code", "GATE_REGISTRY_CODE_INVALID"),
    ("CLASSIC_C3_*_BOUND", "GATE_REGISTRY_CODE_INVALID"),
    ("*_SHARE_CONSERVATION_FAILED", "GATE_REGISTRY_CODE_INVALID"),
])
def test_an_unregistered_code_builds_no_limitation(code, error):
    """Nothing resolves by pattern: a code a template would produce is still refused."""

    with pytest.raises(GateRegistryError, match=error):
        registry().limitation(code)


# ----------------------------------------------------------------- the loader refuses

def _minimal() -> dict:
    return {
        "schema_version": "nfl_gate_registry_v1",
        "registered_at": "2026-09-23",
        "families": {
            "entry_authority": {"class": "V", "stops": "FILE", "covers": "rows",
                                "provenance": {"kind": "CLAUDE_MD_BOUNDARY", "ref": "authority"}},
            "portfolio_bounds": {"class": "S", "stops": "CONSTRUCTION_PREFERENCE", "covers": "bounds",
                                 "provenance": {"kind": "RULING", "ref": "R28"}},
        },
        "codes": {"A_CODE": "entry_authority", "B_TEAM_BOUND": "portfolio_bounds",
                  "C_X_FAILED": "portfolio_bounds", "D_Y_FAILED": "entry_authority"},
        "expansions": {"*_FAILED": ["C_X_FAILED", "D_Y_FAILED"]},
    }


def _raw(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_the_minimal_registry_parses():
    parsed = parse_gate_registry(_raw(_minimal()))
    assert parsed.family_of("B_TEAM_BOUND").name == "portfolio_bounds"
    assert parsed.family_of("D_Y_FAILED").name == "entry_authority"
    with pytest.raises(GateRegistryError, match="GATE_REGISTRY_CODE_UNREGISTERED"):
        parsed.family_of("E_Z_FAILED")


def _mutated(change):
    payload = _minimal()
    change(payload)
    return payload


@pytest.mark.parametrize("payload,error", [
    (_mutated(lambda p: p.update(schema_version="nfl_gate_registry_v2")), "GATE_REGISTRY_SCHEMA_INVALID"),
    (_mutated(lambda p: p.update(extra=1)), "GATE_REGISTRY_SCHEMA_INVALID"),
    (_mutated(lambda p: p.pop("expansions")), "GATE_REGISTRY_SCHEMA_INVALID"),
    (_mutated(lambda p: p.update(registered_at="not a date")), "GATE_REGISTRY_SCHEMA_INVALID"),
    (_mutated(lambda p: p.update(registered_at=20260923)), "GATE_REGISTRY_SCHEMA_INVALID"),
    (_mutated(lambda p: p["families"]["entry_authority"].update(stops="CERTIFICATION")),
     "GATE_REGISTRY_CLASS_STOPS_INVALID"),
    (_mutated(lambda p: p["families"]["entry_authority"].update(stops="CONSTRUCTION_PREFERENCE")),
     "GATE_REGISTRY_CLASS_STOPS_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"].update(stops="CERTIFICATION")),
     "GATE_REGISTRY_CLASS_STOPS_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"].update(stops="FILE")),
     "GATE_REGISTRY_CLASS_STOPS_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"].update({"class": "P", "stops": "CONSTRUCTION_PREFERENCE"})),
     "GATE_REGISTRY_CLASS_STOPS_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"].update({"class": "X"})), "GATE_REGISTRY_FAMILY_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"].update(covers=" ")), "GATE_REGISTRY_FAMILY_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"].pop("covers")), "GATE_REGISTRY_FAMILY_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"]["provenance"].update(kind="VIBES")),
     "GATE_REGISTRY_FAMILY_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"]["provenance"].update(ref="")),
     "GATE_REGISTRY_FAMILY_INVALID"),
    (_mutated(lambda p: p["families"]["portfolio_bounds"]["provenance"].update(ref="   ")),
     "GATE_REGISTRY_FAMILY_INVALID"),
    (_mutated(lambda p: p["families"].update({"Bad-Name": p["families"]["portfolio_bounds"]})),
     "GATE_REGISTRY_FAMILY_INVALID"),
    (_mutated(lambda p: p["families"].update(unused=dict(p["families"]["portfolio_bounds"]))),
     "GATE_REGISTRY_FAMILY_UNUSED"),
    (_mutated(lambda p: p["codes"].update(E_CODE="nobody")), "GATE_REGISTRY_FAMILY_UNKNOWN"),
    (_mutated(lambda p: p["codes"].update(E_CODE=["entry_authority"])), "GATE_REGISTRY_FAMILY_UNKNOWN"),
    (_mutated(lambda p: p["codes"].update(lower_code="entry_authority")), "GATE_REGISTRY_CODE_INVALID"),
    (_mutated(lambda p: p["codes"].update({"B_*_BOUND": "portfolio_bounds"})), "GATE_REGISTRY_CODE_INVALID"),
    (_mutated(lambda p: p["codes"].update({"*_ANYTHING": "entry_authority"})), "GATE_REGISTRY_CODE_INVALID"),
    (_mutated(lambda p: p["expansions"].update({"*_FAILED": ["C_X_FAILED", "C_X_FAILED"]})),
     "GATE_REGISTRY_EXPANSION_INVALID"),
    (_mutated(lambda p: p["expansions"].update({"*_FAILED": ["A_CODE"]})), "GATE_REGISTRY_EXPANSION_INVALID"),
    (_mutated(lambda p: p["expansions"].update({"*_FAILED": ["Z_Q_FAILED"]})), "GATE_REGISTRY_EXPANSION_INVALID"),
    (_mutated(lambda p: p["expansions"].update({"*_FAILED": []})), "GATE_REGISTRY_EXPANSION_INVALID"),
    (_mutated(lambda p: p["expansions"].update({"NO_STAR": ["A_CODE"]})), "GATE_REGISTRY_EXPANSION_INVALID"),
])
def test_the_loader_refuses_a_registry_it_cannot_trust(payload, error):
    with pytest.raises(GateRegistryError, match=error):
        parse_gate_registry(_raw(payload))


def test_the_loader_refuses_a_duplicate_code_and_bad_bytes():
    text = _raw(_minimal()).decode("utf-8").replace('"A_CODE": "entry_authority"',
                                                    '"A_CODE": "entry_authority", "A_CODE": "portfolio_bounds"')
    with pytest.raises(GateRegistryError, match="GATE_REGISTRY_DUPLICATE_KEY:A_CODE"):
        parse_gate_registry(text.encode("utf-8"))
    with pytest.raises(GateRegistryError, match="GATE_REGISTRY_JSON_INVALID"):
        parse_gate_registry(b"\xff{")
    with pytest.raises(GateRegistryError, match="GATE_REGISTRY_UNREADABLE"):
        load_gate_registry(REPO / "config" / "no_such_registry.json")


def test_template_bindings_try_every_split():
    assert list(template_bindings("A_*_*_B", "A_X_Y_Z_B")) == [("X", "Y_Z"), ("X_Y", "Z")]
    assert list(template_bindings("A_*_B", "A_B")) == []
    assert list(template_bindings("*_FAILED", "DESIGN_SHARE_CONSERVATION_FAILED")) == [("DESIGN_SHARE_CONSERVATION",)]


# ----------------------------------------------------------------- the scan itself

@pytest.mark.parametrize("snippet,code", [
    ("def f():\n    raise ValueError('A_CODE')\n", "A_CODE"),
    ("def f(x):\n    raise ValueError(f'A_CODE:{x}')\n", "A_CODE"),
    ("def f(x):\n    raise ValueError(f'A_{x}_MISSING')\n", "A_*_MISSING"),
    ("def f(x):\n    raise ValueError(f'{x}_NOT_TIMEZONE_AWARE:{x}')\n", "*_NOT_TIMEZONE_AWARE"),
    ("def f(blockers):\n    blockers.append('A_CODE')\n", "A_CODE"),
    ("def f(self):\n    self._blockers.extend(['A_CODE', 'B_CODE'])\n", "B_CODE"),
    ("def f(problems):\n    problems.append(_problem('A_CODE', 1))\n", "A_CODE"),
    ("def f(findings):\n    findings.append(QAFinding('A_CODE', 'HIGH'))\n", "A_CODE"),
    ("def f(r, limitations):\n    limitations.append(r.limitation('A_CODE', detail='x'))\n", "A_CODE"),
    ("def f(r, limitations):\n    limitations += [r.limitation('A_CODE')]\n", "A_CODE"),
    ("def f(errors, x):\n    errors.append('A_CODE' if x else 'B_CODE')\n", "B_CODE"),
    ("def f(reasons):\n    reasons += ('A_CODE',)\n", "A_CODE"),
    ("def f():\n    return Outcome(blockers=('A_CODE',))\n", "A_CODE"),
    ("def f():\n    return Finding(code='A_CODE')\n", "A_CODE"),
    ("def f(self):\n    self.blocking_status = 'A_CODE'\n", "A_CODE"),
    ("class B:\n    def blocking(self):\n        return self.status in {'A_CODE', 'B_CODE'}\n", "A_CODE"),
    ("def f(x):\n    raise ValueError('A_CODE:%s' % x)\n", "A_CODE"),
    ("def f(x):\n    raise ValueError('A_CODE:' + x)\n", "A_CODE"),
    # the shapes the Session 03b review found
    ("def f(problems, xs):\n    problems.extend(f'A_CODE:{x}' for x in xs)\n", "A_CODE"),
    ("def f():\n    action, reason = 'BLOCK', 'A_CODE'\n", "A_CODE"),
    ("def f(a, b, x):\n    target = a_blockers if x else b_blockers\n    target.append('A_CODE')\n", "A_CODE"),
    ("def f(blockers):\n    return _unique([*blockers, 'A_CODE'])\n", "A_CODE"),
    ("def f(d):\n    return dict.fromkeys((*d.reasons, 'A_CODE'))\n", "A_CODE"),
    ("def f():\n    return {'blockers': ['A_CODE: detail']}\n", "A_CODE"),
    ("def _read(path, code):\n    raise ValueError(f'{code}:{path}')\ndef g(p):\n    return _read(p, 'A_CODE')\n", "A_CODE"),
    ("def f(xs):\n    for n in ('ONE', 'TWO'):\n        raise ValueError(f'A_{n}_BAD')\n", "A_TWO_BAD"),
    ("def f(d):\n    for name, v in {'first': 1}.items():\n        raise ValueError(f'A_{name.upper()}_BAD')\n", "A_FIRST_BAD"),
    ("def f():\n    message = 'A_CODE:detail'\n    raise ValueError(message)\n", "A_CODE"),
    ("def g():\n    return 1, 'A_CODE:x'\ndef f():\n    value, problem = g()\n", "A_CODE"),
    ("def g():\n    return ('A_CODE',)\ndef f(problems):\n    problems.extend(g())\n", "A_CODE"),
    ("def m(v, *, label):\n    raise ValueError(f'{label}_NOT_A_TIMESTAMP:{v}')\n"
     "def f(g):\n    m(1, label=f'W_OBSERVED_AT:{g}')\n", "W_OBSERVED_AT"),
])
def test_the_scan_sees_every_emitting_shape(snippet, code):
    assert code in blocker_literals(snippet)


@pytest.mark.parametrize("snippet", [
    "def f():\n    raise ValueError('FILE_VALID must be true')\n",
    "def f():\n    raise ValueError('roster contains a blank cell')\n",
    "def f(x):\n    raise ValueError(f'{x}: bad')\n",
    "def f(x):\n    raise ValueError(f'{x}_{x}')\n",
    "def f(rows):\n    rows.append('A_CODE')\n",
    "def f():\n    status = 'OPTIMAL_ACTUAL_CANDIDATE_BANK'\n",
    "def f():\n    return {'state': 'PRIOR_ONLY_LIMITATION'}\n",
    "def f(x):\n    return x == 'A_CODE'\n",
    "def f():\n    action, reason = 'SELECT', 'A_REASON'\n",
    "def g():\n    return True, 'A_REASON'\ndef f():\n    keep, reason = g()\n",
])
def test_the_scan_leaves_messages_and_other_strings_alone(snippet):
    assert not blocker_literals(snippet)
