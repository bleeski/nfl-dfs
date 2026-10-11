"""Every subcommand's `--help` renders.

Week 5 Classic (2026-10-11): `run-slate --help` raised `TypeError: must be real number, not dict` because the
`--contest-facts-csv` help text carried a bare `5%`, which argparse reads as a format specifier. The operator
looking for a flag got a traceback instead of the flag list.
"""

import argparse

import pytest

from nfl_dfs import cli


def _subcommands():
    parser = cli.build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return sorted(action.choices.items())


@pytest.mark.parametrize("name,subparser", _subcommands(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_subcommand_help_renders(name, subparser):
    text = subparser.format_help()
    assert text.startswith("usage:"), name


def test_run_slate_help_names_the_contest_facts_flag():
    parser = dict(_subcommands())["run-slate"]
    assert "--contest-facts-csv" in parser.format_help()
    assert "pays under 5% FIRST_PLACE_OBJECTIVE" in " ".join(parser.format_help().split())
