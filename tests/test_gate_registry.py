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

Session 03b adds `config/gate_registry_v1.json`, its loader, the completeness
test and the class rules on registry entries to this file.
"""

from __future__ import annotations

import ast
import re
from dataclasses import replace
from pathlib import Path

import pytest

from nfl_dfs.opportunity import WEATHER_STATES
from nfl_dfs.prior_score import score_pool, team_volumes
from nfl_dfs.priors import resolve_weather_state
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
    ("prior_review.py", "run_prior_review", "weather_blockers + gate.blockers"):
        "concatenates two tuples of blocker strings",
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
