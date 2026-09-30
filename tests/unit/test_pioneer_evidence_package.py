"""The Pioneer evidence workflow: build, verify, tamper, and the labelled counterfactual.

The claim this suite has to keep honest is narrow and easy to overstate. A verified package
means the files are the ones that were sealed, the documents satisfy their schemas, every
reference resolves, and recomputing from the packaged inputs reproduces the packaged results.
It does not mean the physics is right and it does not mean anyone reviewed it.

So the tests below are mostly attempts to make verification pass when it should not. The one
that matters most is ``test_recomputation_is_not_vacuous``: a check that recomputes and compares
is worthless if it would pass on a package whose code was swapped, and the only way to know is
to swap the code and watch it fail.

Packages are built with few Monte Carlo iterations because gate 1 -- the part every tamper test
exercises -- is closed-form arithmetic and does not depend on the sample count. The one test
that asserts agreement with the experiment itself compares gate 1 for that reason.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from farsight.evidence.manifest import seal

REPO = Path(__file__).resolve().parents[2]
PIONEER = REPO / "experiments" / "pioneer_thermal"
BUILT_AT = _dt.datetime(2026, 9, 30, 12, 0, tzinfo=_dt.UTC)
ITERATIONS = 200


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def builder():
    return _module(PIONEER / "build_evidence_package.py", "build_evidence_package")


def verifier():
    return _module(PIONEER / "verify_evidence_package.py", "verify_evidence_package")


def verify(package: Path) -> int:
    """Run the verifier exactly as the documented command does, and return its exit code."""
    module = verifier()
    argv = sys.argv
    sys.argv = ["verify_evidence_package.py", str(package)]
    try:
        return module.main()
    finally:
        sys.argv = argv


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("pkg") / "baseline"
    builder().build(out, counterfactual=None, seed=20260928, iterations=ITERATIONS,
                    built_at=BUILT_AT)
    return out


@pytest.fixture(scope="module")
def counterfactual(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("pkg") / "counterfactual"
    builder().build(out, counterfactual="w_rtgb_geometric", seed=20260928,
                    iterations=ITERATIONS, built_at=BUILT_AT)
    return out


@pytest.fixture
def scratch(baseline, tmp_path) -> Path:
    """A private copy, so a tamper test cannot damage the package another test is reading."""
    copy = tmp_path / "package"
    shutil.copytree(baseline, copy)
    return copy


def _read(package: Path, relative: str):
    return json.loads((package / relative).read_text(encoding="utf-8"))


def _write(package: Path, relative: str, content) -> None:
    (package / relative).write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------------------------
# The package says what the experiment says


def test_the_baseline_results_match_the_experiment_itself(baseline):
    """The package must not drift from the calculation it claims to describe."""
    model = _module(PIONEER / "reproduce_thermal_acceleration.py", "pioneer_model_reference")
    _, rows = model.gate_1()
    packaged = {
        row["scenario"]: float(row["computed"]["magnitude"])
        for row in _read(baseline, "metrics/results.json")["gate_1"]["scenarios"]
    }
    assert len(packaged) == 5
    for scenario, computed, _residual in rows:
        assert packaged[scenario.number] == pytest.approx(computed * 1e-10, rel=1e-12)


def test_packaging_a_failed_reproduction_succeeds(baseline):
    """The workflow's whole point: a scientifically failed result packages normally.

    Gate 1 fails on scenario 5 and gate 2 misses. Neither is an operational error, and a
    packager that could only package successes would be an advertising tool.
    """
    manifest = _read(baseline, "manifest.json")
    assert manifest["overall_verdict"] == "not_reproduced"
    results = _read(baseline, "metrics/results.json")
    assert results["gate_1"]["verdict"] == "fail"
    assert results["gate_2"]["verdict"] == "fail"
    assert verify(baseline) == 0, "a failed reproduction must still verify"


def test_an_intact_package_verifies(baseline):
    assert verify(baseline) == 0


def test_the_package_records_whether_the_checkout_was_dirty(baseline):
    code = _read(baseline, "manifest.json")["code"]
    assert code["commit_known"] is True
    assert isinstance(code["dirty"], bool)
    assert code["model_sha256"]


def test_two_builds_with_the_same_timestamp_are_byte_identical(tmp_path):
    """Identity is content, so the only thing that may differ between builds is the timestamp."""
    first, second = tmp_path / "a", tmp_path / "b"
    for out in (first, second):
        builder().build(out, counterfactual=None, seed=20260928, iterations=ITERATIONS,
                        built_at=BUILT_AT)
    assert (first / "hashes" / "root_hash.txt").read_text() == (
        second / "hashes" / "root_hash.txt"
    ).read_text()


def _reseal_like_a_competent_forger(package: Path) -> None:
    """Re-render the report from the tampered JSON, then re-seal.

    A naive edit is caught by the file manifest, and an edit plus a re-seal is caught by the
    generated report no longer matching. Both are real defences, and both are tested. This
    helper strips them away so the tests below reach the checks underneath -- recomputation and
    self-agreement -- which is where a forger who did their homework would arrive.
    """
    module = builder()
    from farsight.schemas.knowledge import Assumption

    manifest = _read(package, "manifest.json")
    results = _read(package, "metrics/results.json")
    declared = [
        Assumption.model_validate(a)
        for a in _read(package, "registers/assumptions.json")["assumptions"]
    ]
    (package / "report" / "summary.md").write_text(
        module.render_summary(manifest, results, declared), encoding="utf-8"
    )
    seal(package)


# --------------------------------------------------------------------------------------------
# Attempts to make verification pass when it should not


def test_tampering_with_a_result_is_detected(scratch):
    """The plainest attack: edit a number and hand the package on."""
    results = _read(scratch, "metrics/results.json")
    results["gate_1"]["scenarios"][4]["within_tolerance"] = True
    _write(scratch, "metrics/results.json", results)
    assert verify(scratch) == 2, "an edited file must fail file integrity"


def test_tampering_and_resealing_is_still_caught(scratch):
    """Re-sealing defeats the file manifest, which is exactly why recomputation exists."""
    results = _read(scratch, "metrics/results.json")
    results["gate_1"]["scenarios"][4]["computed"]["magnitude"] = "6.71e-10"
    results["gate_1"]["scenarios"][4]["residual_1e10"] = "0.0"
    results["gate_1"]["scenarios"][4]["within_tolerance"] = True
    _write(scratch, "metrics/results.json", results)
    seal(scratch)
    assert verify(scratch) == 3, "a stale generated report is caught first"
    _reseal_like_a_competent_forger(scratch)
    assert verify(scratch) in (4, 5), "and recomputation catches it underneath"


def test_tampering_with_an_input_is_detected(scratch):
    """Changing an input without changing the result it produced."""
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    inputs["scenarios"][0]["inputs"]["w_front"]["magnitude"] = "99.0"
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 4


def test_a_verdict_the_numbers_do_not_support_is_refused(scratch):
    """A package claiming success over failing numbers is a false claim, not a sad result."""
    results = _read(scratch, "metrics/results.json")
    results["gate_1"]["verdict"] = "pass"
    results["gate_2"]["verdict"] = "pass"
    _write(scratch, "metrics/results.json", results)
    manifest = _read(scratch, "manifest.json")
    manifest["overall_verdict"] = "reproduced"
    _write(scratch, "manifest.json", manifest)
    _reseal_like_a_competent_forger(scratch)
    assert verify(scratch) == 5


def test_a_missing_register_is_an_actionable_failure(scratch, capsys):
    (scratch / "registers" / "unknowns.json").unlink()
    seal(scratch)
    assert verify(scratch) == 3
    assert "unknowns.json" in capsys.readouterr().err


def test_an_unresolved_reference_is_an_actionable_failure(scratch, capsys):
    manifest = _read(scratch, "manifest.json")
    manifest["refs"]["criterion"] = "f" * 64
    _write(scratch, "manifest.json", manifest)
    seal(scratch)
    assert verify(scratch) == 3
    assert "ffffffffffffffff" in capsys.readouterr().err


def test_an_object_edited_in_place_is_detected(scratch):
    """The object store re-addresses what it reads; a filename is not a guarantee."""
    ref = _read(scratch, "manifest.json")["refs"]["criterion"]
    path = scratch / "objects" / ref[:2] / f"{ref}.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["object"]["both_gates_must_pass"] = False
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    seal(scratch)
    assert verify(scratch) == 3


def test_a_hand_edited_report_is_detected(scratch):
    """ADR-007 decision 5: the report is generated, so prose cannot contradict the JSON."""
    report = scratch / "report" / "summary.md"
    report.write_text(
        report.read_text(encoding="utf-8").replace("NOT_REPRODUCED", "REPRODUCED"),
        encoding="utf-8",
    )
    seal(scratch)
    assert verify(scratch) == 3


def test_recomputation_is_not_vacuous(scratch):
    """Swap a coefficient in the PACKAGED code and the recomputation must disagree.

    Without this, check 3 could be comparing the package to itself and would pass on anything.
    """
    code = scratch / "code" / "reproduce_thermal_acceleration.py"
    source = code.read_text(encoding="utf-8")
    assert "0.0537 * kd_ant" in source
    code.write_text(source.replace("0.0537 * kd_ant", "0.0500 * kd_ant", 1), encoding="utf-8")
    seal(scratch)
    assert verify(scratch) == 4


def test_a_package_that_is_not_one_fails_readably(tmp_path):
    empty = tmp_path / "not_a_package"
    empty.mkdir()
    assert verify(empty) == 6


# --------------------------------------------------------------------------------------------
# Offline, and no engine


def test_verification_opens_no_socket(scratch, monkeypatch):
    """ADR-007 decision 6: the verifier makes no network call. Enforced, not asserted."""
    def refuse(*args, **kwargs):
        raise AssertionError("verification attempted to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert verify(scratch) == 0


def test_verification_imports_no_engine_extra(scratch):
    """The commercially decisive rule: an auditor verifies on a zero-extras install.

    Run in a fresh interpreter, which is both the honest test and the only correct one. This
    process has already imported engines for other tests, and an earlier version of this test
    tried to correct for that by deleting them from ``sys.modules`` -- which broke two unrelated
    tests that patch those very modules. A subprocess is what the auditor does anyway.
    """
    probe = (
        "import runpy, sys",
        "package, verifier = sys.argv[1], sys.argv[2]",
        "sys.argv = ['verify_evidence_package.py', package]",
        "try:",
        "    runpy.run_path(verifier, run_name='__main__')",
        "except SystemExit as exc:",
        "    code = exc.code or 0",
        "else:",
        "    code = 0",
        "leaked = sorted(n for n in sys.modules",
        "                if n in ('spiceypy', 'bsk') or n.startswith('farsight.engines'))",
        "print('EXIT', code)",
        "print('LEAKED', leaked)",
    )
    done = subprocess.run(
        [
            sys.executable, "-c", "\n".join(probe),
            str(scratch), str(PIONEER / "verify_evidence_package.py"),
        ],
        capture_output=True, text=True, timeout=300, check=False,
    )
    assert "EXIT 0" in done.stdout, (
        f"verification failed in a clean interpreter:\n{done.stdout}\n{done.stderr}"
    )
    assert "LEAKED []" in done.stdout, f"verification imported an engine:\n{done.stdout}"


# --------------------------------------------------------------------------------------------
# The labelled counterfactual


def test_the_counterfactual_is_a_separate_package(baseline, counterfactual):
    """A sensitivity demonstration must not contaminate the baseline it is measured against."""
    assert baseline != counterfactual
    base_root = (baseline / "hashes" / "root_hash.txt").read_text().strip()
    cf_root = (counterfactual / "hashes" / "root_hash.txt").read_text().strip()
    assert base_root != cf_root
    assert _read(baseline, "manifest.json")["variant"] == "baseline"
    assert _read(counterfactual, "manifest.json")["variant"] == "counterfactual:w_rtgb_geometric"


def test_the_counterfactual_records_the_assumption_it_changed(baseline, counterfactual):
    ids = {
        a["assumption_id"]
        for a in _read(counterfactual, "registers/assumptions.json")["assumptions"]
    }
    assert "counterfactual_w_rtgb_geometric" in ids
    base_ids = {
        a["assumption_id"] for a in _read(baseline, "registers/assumptions.json")["assumptions"]
    }
    assert "counterfactual_w_rtgb_geometric" not in base_ids, "the baseline must stay clean"


def test_the_counterfactual_moves_the_results_and_verifies(counterfactual, baseline):
    """It changes the answer -- and it does not rescue the failed gate, which is the point."""
    assert verify(counterfactual) == 0
    base = _read(baseline, "metrics/results.json")["gate_1"]["scenarios"]
    changed = _read(counterfactual, "metrics/results.json")["gate_1"]["scenarios"]
    deltas = [
        float(c["computed"]["magnitude"]) - float(b["computed"]["magnitude"])
        for b, c in zip(base, changed, strict=True)
    ]
    assert all(delta != 0 for delta in deltas), "changing an input must change every result"
    # Scenario 5 was the failing one. The counterfactual must not be a quiet correction.
    assert changed[4]["within_tolerance"] is False
    assert _read(counterfactual, "manifest.json")["overall_verdict"] == "not_reproduced"


def test_verifying_does_not_modify_the_package(scratch):
    """MEASURED: importing the packaged code wrote __pycache__ into the package, so the first
    verification passed and the second failed on a file the first one had created."""
    before = {
        p.relative_to(scratch).as_posix(): p.read_bytes()
        for p in sorted(scratch.rglob("*")) if p.is_file()
    }
    assert verify(scratch) == 0
    assert verify(scratch) == 0, "verifying twice must give the same answer"
    after = {
        p.relative_to(scratch).as_posix(): p.read_bytes()
        for p in sorted(scratch.rglob("*")) if p.is_file()
    }
    assert set(after) - set(before) == set(), "verification created files inside the package"
    assert before == after, "verification changed the package it was checking"
