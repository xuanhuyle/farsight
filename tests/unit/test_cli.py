"""The CLI surface and the exit-code contract (ADR-024).

The exit-code registry is unusual in that it is **printed into shipped evidence packages**:
`report/summary.md` carries the audit instructions, so a code's meaning has to still be true
years after the package left. That is why the registry is append-only and why these tests assert
the numbers themselves rather than only the behaviour.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from farsight.cli import exit_codes
from farsight.cli.main import app

runner = CliRunner()


# --------------------------------------------------------------------------------------
# The entry point exists (it did not, and CI never noticed)
# --------------------------------------------------------------------------------------


def test_the_declared_entry_point_resolves():
    """pyproject.toml declared `farsight = "farsight.cli.main:app"` while that module did not
    exist, so the installed console script raised ModuleNotFoundError. CI ran pytest and
    lint-imports and never invoked the command, so nothing caught it."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == exit_codes.OK
    assert result.stdout.strip()


def test_version_is_machine_readable_under_json():
    result = runner.invoke(app, ["--version", "--json"])
    assert result.exit_code == exit_codes.OK
    assert "version" in json.loads(result.stdout)


def test_the_global_options_are_accepted():
    """ADR-024 fixes these as global on every command."""
    result = runner.invoke(app, ["--no-color", "--quiet", "--home", ".", "--version"])
    assert result.exit_code == exit_codes.OK


# --------------------------------------------------------------------------------------
# The exit-code registry
# --------------------------------------------------------------------------------------


def test_the_registry_matches_the_record():
    """Transcribed from ADR-024 decision 2. Asserting the numbers is the point: they are printed
    into packages, so a renumbering would silently falsify shipped instructions."""
    expected = {
        0: "ok", 1: "internal_error", 2: "usage_error",
        10: "integrity_failure", 11: "schema_failure", 12: "completeness_failure",
        13: "recomputation_mismatch", 14: "environment_refusal",
        15: "signature_policy_failure", 20: "precondition_refusal", 21: "work_remains",
        22: "verdict_fail", 23: "verdict_indeterminate", 30: "acquisition_failure",
    }
    assert {e.code: e.symbol for e in exit_codes.REGISTRY} == expected


def test_every_registry_entry_has_a_meaning_a_stranger_can_read():
    for entry in exit_codes.REGISTRY:
        assert exit_codes.meaning(entry.code) == entry.meaning
        assert len(entry.meaning.split()) >= 5


def test_an_unregistered_code_is_refused_rather_than_guessed():
    with pytest.raises(KeyError, match="append-only"):
        exit_codes.meaning(99)


def test_resolution_returns_the_smallest_applicable_code_above_two():
    """ADR-024: tamper (10) dominates everything, which is the ordering an auditor wants, and it
    is deterministic -- the same package on the same install always yields the same code."""
    assert exit_codes.resolve([]) == exit_codes.OK
    assert exit_codes.resolve([exit_codes.OK]) == exit_codes.OK
    assert exit_codes.resolve([21, 10, 30]) == exit_codes.INTEGRITY_FAILURE
    assert exit_codes.resolve([23, 22]) == exit_codes.VERDICT_FAIL
    assert exit_codes.resolve([12, 11]) == exit_codes.SCHEMA_FAILURE


def test_zero_and_usage_error_never_win_resolution():
    """0 and 2 are excluded from resolution: 0 is not a finding, and 2 is Typer's own code and is
    not reassigned. If either could win, a real failure could be reported as success."""
    assert exit_codes.resolve([exit_codes.OK, exit_codes.INTEGRITY_FAILURE]) == 10
    assert exit_codes.resolve([exit_codes.USAGE_ERROR, exit_codes.WORK_REMAINS]) == 21
    assert exit_codes.resolve([exit_codes.USAGE_ERROR]) == exit_codes.OK


def test_the_registry_prints_for_an_auditor():
    result = runner.invoke(app, ["--exit-codes"])
    assert result.exit_code == exit_codes.OK
    assert "integrity_failure" in result.stdout

    as_json = runner.invoke(app, ["--exit-codes", "--json"])
    payload = json.loads(as_json.stdout)
    assert {e["code"] for e in payload} == {e.code for e in exit_codes.REGISTRY}


# --------------------------------------------------------------------------------------
# What is deliberately absent
# --------------------------------------------------------------------------------------


def test_no_verb_exists_before_its_implementation():
    """A stub verb that accepts its arguments and does nothing is, to a script, indistinguishable
    from one that succeeded. Verbs land with their implementations -- the same reasoning that made
    `enumerate_outer` refuse a plan it could not honour rather than quietly return two vertices."""
    result = runner.invoke(app, ["geometry", "--design", "x", "--out", "y"])
    assert result.exit_code != exit_codes.OK
