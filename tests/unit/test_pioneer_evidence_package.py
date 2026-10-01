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

from ._guards import skip_or_fail_without_git

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
    """Make a tampered package internally consistent, the way a forger who did their homework
    would: re-store the results as a content-addressed object, repoint the manifest at it,
    re-render the report, then re-seal.

    Each layer this strips away is a real defence and is tested on its own -- a naive edit fails
    the file manifest, an edit plus a re-seal fails the generated report, and an edit that leaves
    the addressed object behind fails the cross-file check. This helper exists so the tests below
    reach the layer underneath all of them: recomputation, and verdicts derived rather than read.
    That layer is the one the reviewer's forgery walked straight through.
    """
    module = builder()
    from farsight.registry.objects import ObjectStore
    from farsight.schemas.common import Provenance
    from farsight.schemas.knowledge import Assumption

    results = _read(package, "metrics/results.json")
    store = ObjectStore(package)
    new_ref = store.put(
        results,
        Provenance(
            created_at=_dt.datetime(2026, 9, 30, tzinfo=_dt.UTC),
            frozen_by="forger", authorization="unattended", tool_version="forge/1",
        ),
    )
    manifest = _read(package, "manifest.json")
    manifest["refs"]["results"] = new_ref
    _write(package, "manifest.json", manifest)

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


def test_verification_works_when_the_engine_extras_are_absent(scratch):
    """Stronger than "did not import it": make them unimportable and verify anyway.

    The zero-extras claim is about an auditor's laptop, where spiceypy and Basilisk are not
    installed at all. This environment has the spice extra, so absence is simulated with a
    meta-path finder that raises ImportError for those names -- which is what the auditor's
    interpreter does on its own. Without this, the test would only show that verification
    happens not to touch an engine that is sitting right there.
    """
    probe = (
        "import runpy, sys",
        "BLOCKED = ('spiceypy', 'bsk', 'gmat', 'pandas', 'matplotlib')",
        "class Blocker:",
        "    def find_module(self, name, path=None):",
        "        return None",
        "    def find_spec(self, name, path=None, target=None):",
        "        if name.split('.')[0] in BLOCKED:",
        "            raise ImportError('simulated zero-extras install: ' + name)",
        "        return None",
        "sys.meta_path.insert(0, Blocker())",
        "package, verifier = sys.argv[1], sys.argv[2]",
        "sys.argv = ['verify_evidence_package.py', package]",
        "try:",
        "    runpy.run_path(verifier, run_name='__main__')",
        "except SystemExit as exc:",
        "    code = exc.code or 0",
        "else:",
        "    code = 0",
        "print('EXIT', code)",
    )
    done = subprocess.run(
        [
            sys.executable, "-c", "\n".join(probe),
            str(scratch), str(PIONEER / "verify_evidence_package.py"),
        ],
        capture_output=True, text=True, timeout=300, check=False,
    )
    assert "EXIT 0" in done.stdout, (
        f"verification failed with the engine extras unavailable:\n{done.stdout}\n{done.stderr}"
    )


def test_the_blocker_itself_works(scratch):
    """The guard on the guard: if the blocker did nothing, the test above proves nothing."""
    probe = (
        "import sys",
        "class Blocker:",
        "    def find_spec(self, name, path=None, target=None):",
        "        if name.split('.')[0] == 'spiceypy':",
        "            raise ImportError('blocked')",
        "        return None",
        "sys.meta_path.insert(0, Blocker())",
        "try:",
        "    import spiceypy",
        "except ImportError:",
        "    print('BLOCKED OK')",
        "else:",
        "    print('BLOCKER DID NOTHING')",
    )
    done = subprocess.run(
        [sys.executable, "-c", "\n".join(probe)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert "BLOCKED OK" in done.stdout, done.stdout + done.stderr


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


# --------------------------------------------------------------------------------------------
# The reviewer's forgery, and each of its independent failure modes
#
# MEASURED 2026-09-30 against f10b597: setting scenario 5's residual to "0.0" and its
# within_tolerance to true, both gate verdicts to "pass", the Monte Carlo central to "5.8" and
# both half-widths to "1.3", the manifest's overall_verdict to "reproduced", then re-rendering
# the report and re-sealing, produced a package that verified with exit 0 and reported both
# gates passed -- without touching the calculation, the accelerations, the targets or any
# content-addressed object. Each test below isolates one reason that worked.


def _restore_object(package: Path, relative: str, ref_name: str) -> str:
    """Re-store an operational file as its content-addressed object and repoint the manifest."""
    from farsight.registry.objects import ObjectStore
    from farsight.schemas.common import Provenance

    document = _read(package, relative)
    ref = ObjectStore(package).put(
        document,
        Provenance(
            created_at=_dt.datetime(2026, 9, 30, tzinfo=_dt.UTC),
            frozen_by="forger", authorization="unattended", tool_version="forge/1",
        ),
    )
    manifest = _read(package, "manifest.json")
    manifest["refs"][ref_name] = ref
    _write(package, "manifest.json", manifest)
    return ref


def _forge_results(package: Path, mutate) -> None:
    """Edit results.json, then make the package internally consistent about it."""
    results = _read(package, "metrics/results.json")
    mutate(results)
    _write(package, "metrics/results.json", results)
    _reseal_like_a_competent_forger(package)


def test_a_changed_residual_with_an_unchanged_acceleration_is_derived_away(scratch, capsys):
    """The residual is now computed from the recomputed acceleration and the published target."""
    def mutate(results):
        results["gate_1"]["scenarios"][4]["residual_1e10"] = "0.0"
        results["gate_1"]["scenarios"][4]["within_tolerance"] = True
        results["gate_1"]["verdict"] = "pass"

    _forge_results(scratch, mutate)
    assert verify(scratch) == 5
    err = capsys.readouterr().err
    assert "residual is derived" in err and "scenario 5" in err


def test_a_forged_within_tolerance_boolean_is_rejected(scratch):
    """The boolean is derived from the residual and the pre-registered tolerance."""
    def mutate(results):
        results["gate_1"]["scenarios"][4]["within_tolerance"] = True
        results["gate_1"]["verdict"] = "pass"

    _forge_results(scratch, mutate)
    assert verify(scratch) == 5


def test_a_forged_monte_carlo_summary_is_recomputed_away(scratch, capsys):
    """Gate 2 had no recomputation at all; the statistics were taken as written."""
    def mutate(results):
        results["gate_2"]["central_1e10"] = "5.8"
        results["gate_2"]["half_width_1p96_sigma_1e10"] = "1.3"
        results["gate_2"]["half_width_percentile_1e10"] = "1.3"
        results["gate_2"]["verdict"] = "pass"

    _forge_results(scratch, mutate)
    assert verify(scratch) == 4
    assert "not what the recorded run produces" in capsys.readouterr().err


def test_the_reviewers_full_forgery_is_rejected(scratch):
    """The exact reported sequence, made internally consistent at every layer."""
    def mutate(results):
        results["gate_1"]["scenarios"][4]["residual_1e10"] = "0.0"
        results["gate_1"]["scenarios"][4]["within_tolerance"] = True
        results["gate_1"]["verdict"] = "pass"
        results["gate_2"]["central_1e10"] = "5.8"
        results["gate_2"]["half_width_1p96_sigma_1e10"] = "1.3"
        results["gate_2"]["half_width_percentile_1e10"] = "1.3"
        results["gate_2"]["verdict"] = "pass"

    manifest = _read(scratch, "manifest.json")
    manifest["overall_verdict"] = "reproduced"
    _write(scratch, "manifest.json", manifest)
    _forge_results(scratch, mutate)
    assert verify(scratch) != 0, "the reported false positive must not verify"
    assert verify(scratch) in (4, 5)


def test_a_forged_claim_result_verdict_is_rejected(scratch):
    """The ClaimResult objects are the package's formal verdicts and must agree too."""
    from farsight.registry.objects import ObjectStore
    from farsight.schemas.common import Provenance
    from farsight.schemas.design import ClaimResult

    manifest = _read(scratch, "manifest.json")
    store = ObjectStore(scratch)
    provenance = Provenance(
        created_at=_dt.datetime(2026, 9, 30, tzinfo=_dt.UTC),
        frozen_by="forger", authorization="unattended", tool_version="forge/1",
    )
    forged = []
    for ref in manifest["refs"]["claim_results"]:
        result = store.get(ref)
        forged.append(store.put(
            ClaimResult(claim_ref=result["claim_ref"], verdict="pass",
                        aggregate_ref=result["aggregate_ref"]),
            provenance,
        ))
    manifest["refs"]["claim_results"] = forged
    _write(scratch, "manifest.json", manifest)
    seal(scratch)
    assert verify(scratch) == 5


def test_an_operational_file_that_disagrees_with_its_addressed_object_is_rejected(scratch):
    """The addressed object is the record; the file the calculation reads must match it."""
    criteria = _read(scratch, "experiment/acceptance_criteria.json")
    criteria["gate_1"]["tolerance_1e10"] = "1.0"
    _write(scratch, "experiment/acceptance_criteria.json", criteria)
    seal(scratch)
    assert verify(scratch) == 3


def test_a_loosened_tolerance_cannot_rescue_a_failed_gate(scratch):
    """Even made fully consistent, widening the criterion changes the claim, not the result.

    The tolerance is pre-registered; this test exists to show what happens if someone edits it
    anyway. The package still has to be self-consistent, so the forger must also flip the stored
    verdict -- and then the derived verdict and the stored one are compared as usual.
    """
    criteria = _read(scratch, "experiment/acceptance_criteria.json")
    criteria["gate_1"]["tolerance_1e10"] = "1.0"
    _write(scratch, "experiment/acceptance_criteria.json", criteria)
    _restore_object(scratch, "experiment/acceptance_criteria.json", "criterion")
    _reseal_like_a_competent_forger(scratch)
    # gate 1 now derives as "pass" against the widened tolerance while the file still records
    # "fail", which is a contradiction the verifier must report rather than paper over.
    assert verify(scratch) == 5


# --------------------------------------------------------------------------------------------
# Units are read, not merely carried


def test_watts_relabelled_as_kilograms_is_rejected(scratch, capsys):
    """MEASURED: this passed all four checks, because recomputation dropped the unit."""
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    inputs["scenarios"][0]["inputs"]["w_front"]["unit"] = "kg"
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 3
    err = capsys.readouterr().err
    assert "scenario 1" in err and "w_front" in err and "kg" in err


def test_a_compatible_unit_is_converted_explicitly(scratch):
    """Conversion is supported and performed before the calculation, never assumed."""
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    first = inputs["scenarios"][0]["inputs"]["w_front"]
    watts = float(first["magnitude"])
    first["magnitude"] = repr(watts / 1000.0)
    first["unit"] = "kW"
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 0, "a dimensionally correct unit must be converted, not refused"


def test_a_nonsense_magnitude_is_rejected(scratch):
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    inputs["scenarios"][0]["inputs"]["w_front"]["magnitude"] = "-5.0"
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 3


def test_a_coefficient_outside_zero_to_one_is_rejected(scratch):
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    inputs["scenarios"][0]["inputs"]["kd_ant"]["magnitude"] = "1.5"
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 3


def test_a_duplicated_scenario_is_rejected(scratch, capsys):
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    inputs["scenarios"][4]["scenario"] = 1
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 3
    assert "substituted scenario" in capsys.readouterr().err


def test_a_missing_scenario_is_rejected(scratch):
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    inputs["scenarios"] = inputs["scenarios"][:4]
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 3


def test_a_missing_input_field_is_rejected(scratch):
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    del inputs["scenarios"][0]["inputs"]["ks_lat"]
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 3


# --------------------------------------------------------------------------------------------
# The execution settings are explicit, and checked against the code that uses them


def test_an_execution_setting_that_disagrees_with_the_packaged_code_is_rejected(scratch, capsys):
    """Recording a parameter is only worth something if it must match what the sampler reads."""
    settings = _read(scratch, "experiment/execution_settings.json")
    settings["parameters"]["ks_lat"]["magnitude"] = "0.5"
    _write(scratch, "experiment/execution_settings.json", settings)
    _restore_object(scratch, "experiment/execution_settings.json", "execution_settings")
    seal(scratch)
    assert verify(scratch) == 4
    assert "the packaged code uses" in capsys.readouterr().err


def test_a_changed_seed_is_caught_by_recomputation(scratch):
    settings = _read(scratch, "experiment/execution_settings.json")
    settings["seed"] = settings["seed"] + 1
    _write(scratch, "experiment/execution_settings.json", settings)
    _restore_object(scratch, "experiment/execution_settings.json", "execution_settings")
    seal(scratch)
    assert verify(scratch) == 4


def test_the_verifier_expectations_do_not_drift_from_the_builder(scratch):
    """The verifier holds its own unit table on purpose; this stops the two silently diverging."""
    assert verifier().EXPECTED_UNITS == builder().SCENARIO_INPUT_UNITS
    assert tuple(verifier().EXPECTED_SCENARIOS) == builder().EXPECTED_SCENARIO_NUMBERS


# --------------------------------------------------------------------------------------------
# Code provenance: clean, dirty, and absent
#
# MEASURED 2026-09-30, GitHub Actions run 36714681896: the container job failed on
# `assert code["commit_known"] is True`. The container has no git metadata, which the
# implementation already handles correctly -- the test was asserting a property of the machine
# it happened to run on. The three states are now each tested against a controlled checkout, and
# the absent one must stay visibly absent rather than be smoothed into "clean".


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def clean_checkout(tmp_path) -> Path:
    skip_or_fail_without_git(
        "building a controlled clean or dirty checkout needs a git binary, and the reference "
        "image has none. The absent-git case -- which is that image's own condition -- is "
        "covered by tests that need no binary and are never skipped."
    )
    repo = tmp_path / "clean"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "file.txt").write_text("content", encoding="utf-8")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def test_a_clean_checkout_is_recorded_as_clean(clean_checkout):
    identity = builder().code_identity(clean_checkout)
    assert identity["commit_known"] is True
    assert identity["dirty"] is False
    assert identity["dirty_paths"] == []
    assert len(identity["commit"]) == 40


def test_a_dirty_checkout_is_recorded_as_dirty(clean_checkout):
    (clean_checkout / "file.txt").write_text("edited after the commit", encoding="utf-8")
    identity = builder().code_identity(clean_checkout)
    assert identity["commit_known"] is True
    assert identity["dirty"] is True
    assert "file.txt" in identity["dirty_paths"]


def test_without_git_metadata_provenance_stays_visibly_unknown(tmp_path):
    """The container's situation. Unknown must not be reported as clean, or invented."""
    identity = builder().code_identity(tmp_path)
    assert identity["commit"] is None
    assert identity["commit_known"] is False
    assert identity["dirty"] is None, "unknown is not False; a reader must see the difference"
    assert identity["model_sha256"], "the code's own digest does not depend on git"


def test_the_report_says_when_git_metadata_was_unavailable(baseline):
    """Whatever the machine, the generated report has to state which of the three states held."""
    module = builder()
    from farsight.schemas.knowledge import Assumption

    manifest = _read(baseline, "manifest.json")
    results = _read(baseline, "metrics/results.json")
    declared = [
        Assumption.model_validate(a)
        for a in _read(baseline, "registers/assumptions.json")["assumptions"]
    ]
    for dirty, expected in (
        (True, "WORKING TREE DIRTY"),
        (None, "GIT METADATA UNAVAILABLE"),
    ):
        altered = {**manifest, "code": {**manifest["code"], "dirty": dirty}}
        assert expected in module.render_summary(altered, results, declared)
    clean = {**manifest, "code": {**manifest["code"], "dirty": False}}
    rendered = module.render_summary(clean, results, declared)
    assert "WORKING TREE DIRTY" not in rendered
    assert "GIT METADATA UNAVAILABLE" not in rendered


def test_a_package_builds_and_verifies_without_git_metadata(tmp_path):
    """The container path, end to end: no git, package still builds and still verifies.

    This is the case that broke CI. Building must not depend on git being present, and the
    resulting package must carry the unknown honestly and still pass every check.
    """
    module = builder()
    out = tmp_path / "package"
    manifest = module.build(out, counterfactual=None, seed=20260928, iterations=ITERATIONS,
                            built_at=BUILT_AT, repo=tmp_path / "not-a-repo")
    assert manifest["code"]["commit_known"] is False
    assert manifest["code"]["dirty"] is None
    assert "GIT METADATA UNAVAILABLE" in (out / "report" / "summary.md").read_text(encoding="utf-8")
    assert verify(out) == 0, "a package from an unidentifiable checkout must still verify"


# --------------------------------------------------------------------------------------------
# The comparison tolerance, the unit inventory, and reference relationships
#
# MEASURED 2026-10-01 against a046c64. Three more ways a resealed package verified when it
# should not have:
#
#   * `math.isclose(..., abs_tol=1e-12)` put an ABSOLUTE floor under a comparison of SI
#     accelerations around 5e-10 m/s2. The tightest scientific threshold is 0.005e-10 = 5e-13
#     m/s2, so the floor was larger than the threshold: a recorded acceleration moved by 9e-13
#     m/s2, with its residual and verdict left alone, verified.
#   * Units were checked on scenario inputs but nowhere else, so `w_front_mean` in the execution
#     settings, and a recorded acceleration, could each be relabelled "kg".
#   * Only the manifest's refs block was walked for resolution, so a `ClaimResult.aggregate_ref`
#     of sixty-four f's resolved to nothing and passed.


def _perturb_recorded_acceleration(package: Path, scenario_index: int, delta: float) -> None:
    """Move one recorded acceleration by `delta` m/s2, leaving its residual and verdict alone."""
    def mutate(results):
        row = results["gate_1"]["scenarios"][scenario_index]
        row["computed"]["magnitude"] = repr(float(row["computed"]["magnitude"]) + delta)

    _forge_results(package, mutate)


@pytest.mark.parametrize("scenario_index", range(5))
def test_a_discrepancy_at_the_scientific_threshold_is_always_detected(scratch, scenario_index):
    """The property that matters, checked per scenario instead of counted in orders of magnitude.

    The pre-registered gate-1 tolerance is 0.005 in units of 1e-10 m/s2. Moving a recorded
    acceleration by exactly that much must never pass, whatever the comparison's internals are.
    """
    criteria = _read(scratch, "experiment/acceptance_criteria.json")
    threshold_si = float(criteria["gate_1"]["tolerance_1e10"]) * 1e-10
    _perturb_recorded_acceleration(scratch, scenario_index, threshold_si)
    assert verify(scratch) == 4


def test_the_reported_nine_hundred_femto_discrepancy_is_detected(scratch):
    """The reviewer's exact number: 9e-13 m/s2 on scenario 2, residual and verdict untouched."""
    _perturb_recorded_acceleration(scratch, 1, 9e-13)
    assert verify(scratch) == 4


def test_the_comparison_has_no_absolute_floor():
    """An absolute tolerance chosen without reference to scale is a hole, not a tolerance."""
    module = verifier()
    typical = 5e-10                      # a Pioneer acceleration, in SI
    threshold = 5e-13                    # the tightest scientific threshold, in SI
    assert not module._close(typical, typical + threshold), (
        "a discrepancy at the scientific threshold must never compare equal"
    )
    assert not module._close(typical, typical + 9e-13)
    # Last-bit float noise still passes, which is the only thing the tolerance is for.
    assert module._close(typical, typical * (1 + 1e-14))
    assert module._close(0.0, 0.0)
    assert not module._close(0.0, 1e-20), "zero against non-zero is a disagreement"


def test_the_execution_tolerance_is_relative_and_far_below_the_scientific_threshold(scratch):
    """Stated as a ratio against the actual quantities, not as a vague count of orders."""
    module = verifier()
    assert module.EXECUTION_TOLERANCE <= 1e-12
    criteria = _read(scratch, "experiment/acceptance_criteria.json")
    tolerance_1e10 = float(criteria["gate_1"]["tolerance_1e10"])
    targets = [float(t) for t in criteria["gate_1"]["targets_1e10"]]
    # The loosest relative scientific threshold across the five scenarios.
    tightest_relative = min(tolerance_1e10 / target for target in targets)
    assert tightest_relative / module.EXECUTION_TOLERANCE > 1e8, (
        "the scientific threshold must stay many orders above the execution tolerance"
    )


# --- the unit inventory -----------------------------------------------------------------


def test_a_relabelled_execution_setting_unit_is_rejected(scratch, capsys):
    settings = _read(scratch, "experiment/execution_settings.json")
    settings["parameters"]["w_front_mean"]["unit"] = "kg"
    _write(scratch, "experiment/execution_settings.json", settings)
    _restore_object(scratch, "experiment/execution_settings.json", "execution_settings")
    seal(scratch)
    assert verify(scratch) == 3
    err = capsys.readouterr().err
    assert "w_front_mean" in err and "kg" in err


def test_a_relabelled_recorded_acceleration_unit_is_rejected(scratch, capsys):
    def mutate(results):
        results["gate_1"]["scenarios"][0]["computed"]["unit"] = "kg"

    _forge_results(scratch, mutate)
    assert verify(scratch) == 3
    err = capsys.readouterr().err
    assert "scenario 1 recorded acceleration" in err and "kg" in err


def test_a_relabelled_published_target_unit_is_rejected(scratch):
    """The referent holds the published value the residual is measured against."""
    from farsight.registry.objects import ObjectStore
    from farsight.schemas.common import Provenance

    manifest = _read(scratch, "manifest.json")
    store = ObjectStore(scratch)
    ref = manifest["refs"]["referents"]["1"]
    document = store.get(ref)
    document["a_th"]["unit"] = "kg"
    manifest["refs"]["referents"]["1"] = store.put(
        document,
        Provenance(created_at=_dt.datetime(2026, 10, 1, tzinfo=_dt.UTC), frozen_by="forger",
                   authorization="unattended", tool_version="forge/1"),
    )
    _write(scratch, "manifest.json", manifest)
    seal(scratch)
    assert verify(scratch) == 3


def test_a_relabelled_published_a_th_in_the_inputs_is_rejected(scratch):
    inputs = _read(scratch, "experiment/scenario_inputs.json")
    inputs["scenarios"][0]["published_a_th"]["unit"] = "kg"
    _write(scratch, "experiment/scenario_inputs.json", inputs)
    seal(scratch)
    assert verify(scratch) == 3


def test_a_missing_execution_setting_is_rejected(scratch):
    settings = _read(scratch, "experiment/execution_settings.json")
    del settings["parameters"]["ks_lat"]
    _write(scratch, "experiment/execution_settings.json", settings)
    _restore_object(scratch, "experiment/execution_settings.json", "execution_settings")
    seal(scratch)
    assert verify(scratch) == 3


def test_a_compatible_setting_unit_is_converted(scratch):
    """Conversion is supported here too, and must not be mistaken for acceptance-and-ignore."""
    settings = _read(scratch, "experiment/execution_settings.json")
    watts = float(settings["parameters"]["w_front_sigma"]["magnitude"])
    settings["parameters"]["w_front_sigma"]["magnitude"] = repr(watts / 1000.0)
    settings["parameters"]["w_front_sigma"]["unit"] = "kW"
    _write(scratch, "experiment/execution_settings.json", settings)
    _restore_object(scratch, "experiment/execution_settings.json", "execution_settings")
    _reseal_like_a_competent_forger(scratch)
    assert verify(scratch) == 0


def test_the_unit_inventory_does_not_drift_from_the_builder(scratch):
    """Every quantity the verifier reads has a declared unit, and it is the one written."""
    checker, maker = verifier(), builder()
    assert checker.ACCELERATION_UNIT == maker.ACCELERATION_UNIT
    settings = _read(scratch, "experiment/execution_settings.json")
    assert set(checker.SETTING_UNITS) == set(settings["parameters"]), (
        "a parameter the builder writes with no expected unit would go unchecked"
    )


# --- references: existence, and relationship --------------------------------------------


def _reforge_claim_results(package: Path, mutate) -> None:
    from farsight.registry.objects import ObjectStore
    from farsight.schemas.common import Provenance

    manifest = _read(package, "manifest.json")
    store = ObjectStore(package)
    provenance = Provenance(
        created_at=_dt.datetime(2026, 10, 1, tzinfo=_dt.UTC), frozen_by="forger",
        authorization="unattended", tool_version="forge/1",
    )
    forged = []
    for ref in manifest["refs"]["claim_results"]:
        document = store.get(ref)
        mutate(document, manifest)
        forged.append(store.put(document, provenance))
    manifest["refs"]["claim_results"] = forged
    _write(package, "manifest.json", manifest)
    seal(package)


def test_an_unresolvable_reference_inside_an_object_is_rejected(scratch, capsys):
    """MEASURED: aggregate_ref of sixty-four f's resolved to nothing and verified."""
    _reforge_claim_results(scratch, lambda doc, _m: doc.update(aggregate_ref="f" * 64))
    assert verify(scratch) == 3
    assert "do not resolve" in capsys.readouterr().err


def test_a_claim_result_aggregating_other_results_is_rejected(scratch, capsys):
    """Existence is not the test: the verdict must be about the results actually verified."""
    _reforge_claim_results(
        scratch, lambda doc, manifest: doc.update(aggregate_ref=manifest["refs"]["criterion"])
    )
    assert verify(scratch) == 5
    assert "not about these numbers" in capsys.readouterr().err


def test_a_claim_citing_other_criteria_is_rejected(scratch):
    """The same relationship one level up: a claim must cite the criterion that was applied."""
    from farsight.registry.objects import ObjectStore
    from farsight.schemas.common import Provenance

    manifest = _read(scratch, "manifest.json")
    store = ObjectStore(scratch)
    provenance = Provenance(
        created_at=_dt.datetime(2026, 10, 1, tzinfo=_dt.UTC), frozen_by="forger",
        authorization="unattended", tool_version="forge/1",
    )
    forged = []
    for ref in manifest["refs"]["claims"]:
        document = store.get(ref)
        document["criterion_ref"] = manifest["refs"]["results"]
        forged.append(store.put(document, provenance))
    manifest["refs"]["claims"] = forged
    manifest["claim_statements"] = [store.get(ref) for ref in forged]
    _write(scratch, "manifest.json", manifest)
    _reseal_like_a_competent_forger(scratch)
    assert verify(scratch) == 5


def test_an_unresolvable_source_reference_in_an_assumption_is_rejected(scratch):
    """The reference walk covers every stored object, not just the claim results."""
    from farsight.registry.objects import ObjectStore
    from farsight.schemas.common import Provenance

    manifest = _read(scratch, "manifest.json")
    store = ObjectStore(scratch)
    ref = manifest["refs"]["assumptions"][0]
    document = store.get(ref)
    document["source_refs"] = ["e" * 64]
    manifest["refs"]["assumptions"][0] = store.put(
        document,
        Provenance(created_at=_dt.datetime(2026, 10, 1, tzinfo=_dt.UTC), frozen_by="forger",
                   authorization="unattended", tool_version="forge/1"),
    )
    _write(scratch, "manifest.json", manifest)
    registers = _read(scratch, "registers/assumptions.json")
    registers["assumptions"][0] = document
    registers["assumption_refs"] = manifest["refs"]["assumptions"]
    _write(scratch, "registers/assumptions.json", registers)
    _reseal_like_a_competent_forger(scratch)
    assert verify(scratch) == 3
