"""Verify a Pioneer evidence package, offline, on the zero-extras base install.

Four checks, kept separate because they answer different questions and an auditor needs to know
which one failed:

1. **File integrity** -- are these the bytes that were sealed?
2. **Schema, references and cross-file consistency** -- does every document satisfy its schema,
   does every reference resolve, and does each operational JSON file agree with the
   content-addressed object that holds the same content?
3. **Numerical recomputation** -- from the packaged inputs, with the packaged code and the
   packaged execution settings, do the packaged results come back? Deterministic scenarios *and*
   the Monte Carlo.
4. **Scientific agreement** -- do the *recomputed* results meet the pre-registered targets, and
   does every verdict recorded anywhere in the package match what they give?

**Only checks 1 to 3 can fail on a scientific miss.** This package's verdict is that two gates
were missed. That is a result, not a fault. Check 4 fails only on *contradiction*: a package
whose recorded verdicts, booleans, claim results or report disagree with what its own numbers
produce.

**MEASURED 2026-09-30, and the reason this file was rewritten.** An earlier version read stored
residuals and stored Monte Carlo statistics instead of deriving them. A reviewer set scenario
5's residual to "0.0", its ``within_tolerance`` to true, both gate verdicts to "pass", the Monte
Carlo central to "5.8" and both half-widths to "1.3", set ``overall_verdict`` to "reproduced",
re-rendered the report and re-sealed -- without touching the calculation, the accelerations, the
targets or any content-addressed object. Verification returned 0 and reported both gates passed.
Every number it trusted is now derived: residuals come from recomputed accelerations and the
targets in the content-addressed referent objects, and the Monte Carlo is re-run from the
recorded seed and settings.

**What verification does not do.** It does not authenticate the package. The root hash is
unsigned, so anyone who can rewrite a file can re-seal the manifest; recomputation catches
*inconsistency*, not a coherent replacement of code, inputs and claims together. It also proves
nothing about whether the physics is right or whether anyone competent has read it.

This imports no engine and opens no socket.

Usage::

    python experiments/pioneer_thermal/verify_evidence_package.py <package dir>

Exit codes: 0 verified, 2 integrity, 3 schema, reference or cross-file inconsistency,
4 recomputation mismatch, 5 the package contradicts its own numbers, 6 unreadable.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from farsight.evidence.manifest import check_integrity
from farsight.registry.objects import ObjectStore, ObjectStoreError
from farsight.schemas.common import Quantity
from farsight.schemas.design import Claim, ClaimResult
from farsight.schemas.knowledge import Assumption, Source
from farsight.units import UnitError, convert, same_dimension

EXIT_OK = 0
EXIT_INTEGRITY = 2
EXIT_SCHEMA = 3
EXIT_RECOMPUTATION = 4
EXIT_CONTRADICTION = 5
EXIT_UNREADABLE = 6

REQUIRED_REGISTERS = (
    "assumptions.json", "unknowns.json", "collapses.json",
    "validity_violations.json", "excluded_runs.json",
)
TYPED = {"source_id": Source, "assumption_id": Assumption, "claim_id": Claim,
         "claim_ref": ClaimResult}

# The canonical unit of each scenario input, and the scenarios that must be present. Held HERE
# rather than read from the package: a checker that takes its expectations from the artifact
# under test cannot detect a substituted or missing scenario. `test_pioneer_evidence_package`
# pins this against the builder's table so the two cannot drift apart silently.
EXPECTED_UNITS = {
    "w_rtgb": "W", "w_front": "W", "w_lat": "W", "w_back": "W",
    "kd_ant": "1", "ks_ant": "1", "ks_lat": "1",
}
EXPECTED_SCENARIOS = (1, 2, 3, 4, 5)
POWER_INPUTS = ("w_rtgb", "w_front", "w_lat", "w_back")
COEFFICIENT_INPUTS = ("kd_ant", "ks_ant", "ks_lat")

# **Execution tolerance, not a scientific tolerance.** This is the slack allowed between a number
# recorded in the package and the same number recomputed here; it exists because a float64 sum
# may differ in its last bit or two across platforms, and for no other reason. The pre-registered
# scientific thresholds (0.005 and 0.05, in units of 1e-10 m/s2) are untouched and live in the
# package's acceptance criteria, where they always have. The gap between them is eleven orders of
# magnitude, which is what stops this from concealing anything: the forged Monte Carlo central
# differed from the true one by 0.096e-10, which is 1e11 times this tolerance.
EXECUTION_TOLERANCE = 1e-12


class Failure(Exception):
    """A verification failure carrying the exit code that names which check failed."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Recomputation:
    """What this verifier derived for itself, independent of what the package asserts."""

    accelerations: dict[int, float] = field(default_factory=dict)
    monte_carlo: dict[str, float] = field(default_factory=dict)
    converted_units: list[str] = field(default_factory=list)


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise Failure(EXIT_SCHEMA, f"required file missing: {path.name} (looked at {path})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Failure(EXIT_SCHEMA, f"{path} is not valid JSON: {exc}") from exc


def _import_path(path: Path, name: str) -> Any:
    """Import a module from a file without writing anything beside it.

    MEASURED: importing the packaged code wrote ``code/__pycache__/`` INTO the package, so the
    first verification passed and every one after it failed on an unlisted file. Verification
    that modifies the thing it is verifying is not verification.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise Failure(EXIT_UNREADABLE, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=EXECUTION_TOLERANCE, abs_tol=EXECUTION_TOLERANCE)


# ------------------------------------------------------------------------------------------
# 1. File integrity


def check_1_integrity(root: Path) -> str:
    problems = check_integrity(root)
    if problems:
        lines = "\n".join(f"  {p}" for p in problems)
        raise Failure(
            EXIT_INTEGRITY, f"{len(problems)} file(s) do not match the sealed manifest:\n{lines}"
        )
    return (root / "hashes" / "root_hash.txt").read_text(encoding="utf-8").strip()


# ------------------------------------------------------------------------------------------
# 2. Schema, references, and cross-file consistency


def check_2_schema_and_references(root: Path) -> dict[str, Any]:  # noqa: PLR0912
    """Every document valid, every reference resolvable, every operational file backed.

    One function with many branches on purpose: each branch is a distinct way a package can be
    inconsistent, and splitting them into helpers would scatter the list an auditor reads.
    """
    manifest = _load_json(root / "manifest.json")
    for key in ("package_format", "refs", "claim_statements", "overall_verdict", "execution"):
        if key not in manifest:
            raise Failure(EXIT_SCHEMA, f"manifest.json has no {key!r}")

    store = ObjectStore(root)
    stored = set(store.refs())
    if not stored:
        raise Failure(EXIT_SCHEMA, "the package contains no objects/ documents at all")

    documents: dict[str, Any] = {}
    for ref in sorted(stored):
        try:
            documents[ref] = store.get(ref)
        except ObjectStoreError as exc:
            raise Failure(EXIT_SCHEMA, str(exc)) from exc
        for marker, model in TYPED.items():
            if marker in documents[ref]:
                try:
                    model.model_validate(documents[ref])
                except Exception as exc:  # pydantic ValidationError, kept broad deliberately
                    raise Failure(
                        EXIT_SCHEMA,
                        f"object {ref[:16]}... does not satisfy {model.__name__}:\n{exc}",
                    ) from exc
                break

    unresolved = [
        f"{name} -> {value[:16]}..."
        for name, value in _iter_refs(manifest["refs"])
        if value not in stored
    ]
    if unresolved:
        raise Failure(
            EXIT_SCHEMA,
            "the manifest references objects that are not in this package:\n  "
            + "\n  ".join(unresolved),
        )

    for claim in manifest["claim_statements"]:
        if not claim.get("falsifier", "").strip():
            raise Failure(EXIT_SCHEMA, f"claim {claim.get('claim_id')} has no falsifier")
        for ref in claim.get("referent_refs", []):
            if ref not in stored:
                raise Failure(
                    EXIT_SCHEMA,
                    f"claim {claim.get('claim_id')} cites referent {ref[:16]}..., "
                    f"which is not in this package",
                )

    for register in REQUIRED_REGISTERS:
        path = root / "registers" / register
        if not path.exists():
            raise Failure(
                EXIT_SCHEMA,
                f"register {register} is missing. An empty register asserts there is nothing to "
                f"declare; a missing one is a verification failure (ADR-007 decision 4).",
            )
        _load_json(path)

    # Every operational file that duplicates an addressed object must agree with it, byte for
    # byte after canonicalisation. Without this, an editor can rewrite the file the calculation
    # reads while the addressed copy -- the one the claims cite -- still says something else.
    refs = manifest["refs"]
    for relative, ref_name in (
        ("experiment/acceptance_criteria.json", "criterion"),
        ("experiment/execution_settings.json", "execution_settings"),
        ("metrics/results.json", "results"),
    ):
        if ref_name not in refs:
            raise Failure(EXIT_SCHEMA, f"manifest refs has no {ref_name!r}")
        operational = _load_json(root / relative)
        addressed = documents[refs[ref_name]]
        if operational != addressed:
            raise Failure(
                EXIT_SCHEMA,
                f"{relative} does not match the content-addressed object it claims to copy "
                f"({refs[ref_name][:16]}...). The addressed object is the record; an operational "
                f"file that disagrees with it is the whole reason this check exists.",
            )

    packaged_claims = {c["claim_id"]: c for c in manifest["claim_statements"]}
    addressed_claims = {
        documents[ref]["claim_id"]: documents[ref]
        for ref in refs.get("claims", []) if "claim_id" in documents[ref]
    }
    if packaged_claims != addressed_claims:
        raise Failure(
            EXIT_SCHEMA,
            "manifest.claim_statements does not match the addressed Claim objects it references",
        )

    declared = _load_json(root / "registers" / "assumptions.json")
    addressed_assumptions = [documents[ref] for ref in refs.get("assumptions", [])]
    if declared["assumptions"] != addressed_assumptions:
        raise Failure(
            EXIT_SCHEMA,
            "registers/assumptions.json does not match the addressed Assumption objects",
        )

    _check_summary_is_generated(root, manifest)
    return manifest


def _iter_refs(refs: Any, prefix: str = "refs") -> list[tuple[str, str]]:
    """Every 64-hex string anywhere in the manifest's refs block, with where it came from."""
    found: list[tuple[str, str]] = []
    if isinstance(refs, str):
        found.append((prefix, refs))
    elif isinstance(refs, list):
        for index, item in enumerate(refs):
            found.extend(_iter_refs(item, f"{prefix}[{index}]"))
    elif isinstance(refs, dict):
        for key, item in refs.items():
            found.extend(_iter_refs(item, f"{prefix}.{key}"))
    return found


def _check_summary_is_generated(root: Path, manifest: dict[str, Any]) -> None:
    """Re-render the report and compare (ADR-007 decision 5): prose cannot drift from the JSON."""
    builder = _import_path(
        Path(__file__).resolve().parent / "build_evidence_package.py", "build_evidence_package"
    )
    results = _load_json(root / "metrics" / "results.json")
    declared = [
        Assumption.model_validate(a)
        for a in _load_json(root / "registers" / "assumptions.json")["assumptions"]
    ]
    expected = builder.render_summary(manifest, results, declared)
    actual = (root / "report" / "summary.md").read_text(encoding="utf-8")
    if expected != actual:
        raise Failure(
            EXIT_SCHEMA,
            "report/summary.md is not what the package JSON renders to. The report is generated, "
            "never written by hand, so this means either the JSON or the report was edited.",
        )


# ------------------------------------------------------------------------------------------
# 3. Numerical recomputation


def _validated_scenario_inputs(  # noqa: PLR0912
    root: Path,
) -> tuple[dict[int, dict[str, float]], list[str]]:
    """Load the inputs the calculation consumes, and refuse anything the model cannot mean.

    MEASURED: relabelling scenario 1's ``w_front`` from "W" to "kg" passed every check, because
    recomputation pulled the magnitude out and dropped the unit on the floor. A unit that is
    accepted and then ignored is worse than no unit at all -- it reads as a checked claim.

    A quantity in a compatible unit is converted explicitly and the conversion is reported. A
    dimensional mismatch is refused, naming the scenario and the input.
    """
    rows = _load_json(root / "experiment" / "scenario_inputs.json").get("scenarios")
    if not isinstance(rows, list) or not rows:
        raise Failure(EXIT_SCHEMA, "experiment/scenario_inputs.json has no scenarios list")

    numbers = [row.get("scenario") for row in rows]
    if sorted(numbers) != list(EXPECTED_SCENARIOS):
        raise Failure(
            EXIT_SCHEMA,
            f"expected scenarios {list(EXPECTED_SCENARIOS)}, found {numbers}. A duplicated, "
            f"missing or substituted scenario changes which claims are being evidenced.",
        )

    converted: list[str] = []
    validated: dict[int, dict[str, float]] = {}
    for row in rows:
        number = row["scenario"]
        inputs = row.get("inputs")
        if not isinstance(inputs, dict):
            raise Failure(EXIT_SCHEMA, f"scenario {number} has no inputs object")
        if set(inputs) != set(EXPECTED_UNITS):
            missing = sorted(set(EXPECTED_UNITS) - set(inputs))
            extra = sorted(set(inputs) - set(EXPECTED_UNITS))
            raise Failure(
                EXIT_SCHEMA,
                f"scenario {number} inputs are wrong: missing {missing}, unexpected {extra}",
            )
        values: dict[str, float] = {}
        for name, expected_unit in EXPECTED_UNITS.items():
            try:
                quantity = Quantity.model_validate(inputs[name])
            except Exception as exc:
                raise Failure(
                    EXIT_SCHEMA, f"scenario {number} input {name!r} is not a Quantity: {exc}"
                ) from exc
            if quantity.unit != expected_unit:
                if not same_dimension(quantity.unit, expected_unit):
                    raise Failure(
                        EXIT_SCHEMA,
                        f"scenario {number} input {name!r} is given in {quantity.unit!r}, which "
                        f"is not a {expected_unit!r}. This experiment's model reads it as "
                        f"{expected_unit!r}; a unit that is accepted and then ignored would let "
                        f"a mislabelled quantity change the answer silently.",
                    )
                try:
                    quantity = convert(quantity, expected_unit)
                except UnitError as exc:
                    raise Failure(
                        EXIT_SCHEMA,
                        f"scenario {number} input {name!r}: {exc}",
                    ) from exc
                converted.append(f"scenario {number} {name}: {inputs[name]['unit']} "
                                 f"-> {expected_unit}")
            value = float(Decimal(quantity.magnitude))
            if not math.isfinite(value):
                raise Failure(
                    EXIT_SCHEMA, f"scenario {number} input {name!r} is not finite"
                )
            if name in POWER_INPUTS and value < 0:
                raise Failure(
                    EXIT_SCHEMA,
                    f"scenario {number} input {name!r} is {value} W. A surface cannot radiate "
                    f"negative power, and the model would return a plausible wrong number.",
                )
            if name in COEFFICIENT_INPUTS and not 0.0 <= value <= 1.0:
                raise Failure(
                    EXIT_SCHEMA,
                    f"scenario {number} input {name!r} is {value}; a reflection coefficient is a "
                    f"fraction in [0, 1].",
                )
            values[name] = value
        validated[number] = values
    return validated, converted


def _checked_execution_settings(root: Path, model: Any) -> dict[str, Any]:
    """The Monte Carlo parameters, checked against the packaged code before they are used.

    Recording a parameter is not enough: if the recorded value and the constant the sampler
    actually reads can disagree, then "recomputed from the recorded settings" is a sentence
    about a file rather than about the calculation.
    """
    settings = _load_json(root / "experiment" / "execution_settings.json")
    for key in ("seed", "iterations", "parameters"):
        if key not in settings:
            raise Failure(EXIT_SCHEMA, f"execution_settings.json has no {key!r}")
    if not isinstance(settings["seed"], int) or not isinstance(settings["iterations"], int):
        raise Failure(EXIT_SCHEMA, "seed and iterations must be integers")
    if settings["iterations"] < 1:
        raise Failure(EXIT_SCHEMA, f"iterations is {settings['iterations']}")

    parameters: dict[str, float] = {}
    for name, raw in settings["parameters"].items():
        try:
            quantity = Quantity.model_validate(raw)
        except Exception as exc:
            raise Failure(
                EXIT_SCHEMA, f"execution setting {name!r} is not a Quantity: {exc}"
            ) from exc
        parameters[name] = float(Decimal(quantity.magnitude))

    against_code = {
        "w_equip": model.W_EQUIP_T26,
        "w_front_mean": model._S4.w_front,
        "w_front_sigma": 7.5,
        "w_rtgb_relative_sigma": 0.25,
        "kd_ant_low": 0.6,
        "kd_ant_high": 0.8,
        "k_total": 0.8,
        "ks_lat": model._S4.ks_lat,
        "lateral_share": model.LATERAL_SHARE,
    }
    for name, expected in against_code.items():
        if name not in parameters:
            raise Failure(EXIT_SCHEMA, f"execution_settings.json has no parameter {name!r}")
        if not _close(parameters[name], expected):
            raise Failure(
                EXIT_RECOMPUTATION,
                f"execution setting {name!r} is recorded as {parameters[name]}, but the packaged "
                f"code uses {expected}. The recomputation would not be the recorded run.",
            )
    settings["_parameters"] = parameters
    return settings


def check_3_recomputation(root: Path) -> Recomputation:
    """Recompute the scenarios AND the Monte Carlo, from packaged inputs and packaged code."""
    model = _import_path(
        root / "code" / "reproduce_thermal_acceleration.py", "packaged_pioneer_model"
    )
    inputs, converted = _validated_scenario_inputs(root)
    settings = _checked_execution_settings(root, model)
    recorded = _load_json(root / "metrics" / "results.json")
    out = Recomputation(converted_units=converted)

    stored_scenarios = {row["scenario"]: row for row in recorded["gate_1"]["scenarios"]}
    if sorted(stored_scenarios) != list(EXPECTED_SCENARIOS):
        raise Failure(
            EXIT_SCHEMA,
            f"metrics/results.json records scenarios {sorted(stored_scenarios)}, "
            f"expected {list(EXPECTED_SCENARIOS)}",
        )

    mismatches = []
    for number, values in sorted(inputs.items()):
        recomputed = model.thermal_acceleration(**values)
        out.accelerations[number] = recomputed
        stored = float(Decimal(stored_scenarios[number]["computed"]["magnitude"]))
        if not _close(recomputed, stored):
            mismatches.append(
                f"  scenario {number}: package says {stored!r}, recomputation gives {recomputed!r}"
            )
    if mismatches:
        raise Failure(
            EXIT_RECOMPUTATION,
            "recomputing from the packaged inputs does not reproduce the packaged accelerations:\n"
            + "\n".join(mismatches),
        )

    import numpy as np

    parameters = settings["_parameters"]
    samples = model.sample_accelerations(
        np.random.default_rng(settings["seed"]),
        settings["iterations"],
        w_rtgb_mean=parameters["w_rtgb_mean"],
        w_equip=parameters["w_equip"],
        w_front_mean=parameters["w_front_mean"],
        w_front_sigma=parameters["w_front_sigma"],
    )
    stats = model.summarise(samples)
    out.monte_carlo = stats

    gate_2 = recorded["gate_2"]
    for key, recorded_key in (
        ("mean", "central_1e10"),
        ("half_width_1p96_sigma", "half_width_1p96_sigma_1e10"),
        ("half_width_percentile", "half_width_percentile_1e10"),
    ):
        stored_value = float(Decimal(gate_2[recorded_key]))
        if not _close(stats[key], stored_value):
            raise Failure(
                EXIT_RECOMPUTATION,
                f"Monte Carlo {recorded_key} is recorded as {stored_value}, but recomputing "
                f"{settings['iterations']} iterations under seed {settings['seed']} gives "
                f"{stats[key]}. The recorded statistic is not what the recorded run produces.",
            )
    return out


# ------------------------------------------------------------------------------------------
# 4. Scientific agreement, derived from the recomputation


def check_4_scientific_agreement(  # noqa: PLR0912, PLR0915
    root: Path, manifest: dict[str, Any], recomputed: Recomputation
) -> list[str]:
    """Derive every residual and verdict, then compare against everything the package asserts.

    Nothing here reads a stored residual or a stored verdict as an input. The targets come from
    the content-addressed referent objects, the tolerances from the addressed criterion, and the
    accelerations from check 3. What the package recorded is only ever the thing being checked.
    """
    store = ObjectStore(root)
    refs = manifest["refs"]
    criteria = store.get(refs["criterion"])
    results = _load_json(root / "metrics" / "results.json")
    lines = []

    referents = refs.get("referents", {})
    if sorted(int(k) for k in referents) != list(EXPECTED_SCENARIOS):
        raise Failure(
            EXIT_SCHEMA,
            f"expected a referent per scenario {list(EXPECTED_SCENARIOS)}, "
            f"found {sorted(referents)}",
        )
    targets: dict[int, float] = {}
    for key, ref in referents.items():
        document = store.get(ref)
        if document.get("scenario") != int(key):
            raise Failure(
                EXIT_SCHEMA,
                f"referent {ref[:16]}... is filed under scenario {key} but names scenario "
                f"{document.get('scenario')}",
            )
        targets[int(key)] = float(Decimal(document["a_th"]["magnitude"])) / 1e-10

    criterion_targets = [float(Decimal(t)) for t in criteria["gate_1"]["targets_1e10"]]
    for index, number in enumerate(EXPECTED_SCENARIOS):
        if not _close(criterion_targets[index], targets[number]):
            raise Failure(
                EXIT_CONTRADICTION,
                f"scenario {number}: the acceptance criteria say the published value is "
                f"{criterion_targets[index]}, the referent object says {targets[number]}",
            )

    tolerance = float(Decimal(criteria["gate_1"]["tolerance_1e10"]))
    stored_scenarios = {row["scenario"]: row for row in results["gate_1"]["scenarios"]}
    misses = []
    for number in EXPECTED_SCENARIOS:
        derived_residual = recomputed.accelerations[number] / 1e-10 - targets[number]
        derived_within = abs(derived_residual) <= tolerance
        stored = stored_scenarios[number]
        stored_residual = float(Decimal(stored["residual_1e10"]))
        if not _close(derived_residual, stored_residual):
            raise Failure(
                EXIT_CONTRADICTION,
                f"scenario {number} records residual {stored_residual}, but the recomputed "
                f"acceleration against the published target gives {derived_residual}. The "
                f"residual is derived, never taken on trust.",
            )
        if bool(stored["within_tolerance"]) is not derived_within:
            raise Failure(
                EXIT_CONTRADICTION,
                f"scenario {number} records within_tolerance={stored['within_tolerance']}, "
                f"but |{derived_residual}| against the pre-registered {tolerance} gives "
                f"{derived_within}",
            )
        if not derived_within:
            misses.append(number)
        lines.append(
            f"  scenario {number}: residual {derived_residual:+.4f} (derived), "
            f"{'within' if derived_within else 'OUTSIDE'} the pre-registered +/-{tolerance}"
        )
    derived_gate_1 = "fail" if misses else "pass"

    gate_2_tolerance = float(Decimal(criteria["gate_2"]["tolerance_1e10"]))
    target_central = float(Decimal(criteria["gate_2"]["target_central_1e10"]))
    target_half_width = float(Decimal(criteria["gate_2"]["target_half_width_1e10"]))
    central = recomputed.monte_carlo["mean"]
    central_ok = abs(central - target_central) <= gate_2_tolerance
    half_width_ok = min(
        abs(recomputed.monte_carlo["half_width_1p96_sigma"] - target_half_width),
        abs(recomputed.monte_carlo["half_width_percentile"] - target_half_width),
    ) <= gate_2_tolerance
    derived_gate_2 = "pass" if (central_ok and half_width_ok) else "fail"
    lines.append(
        f"  monte carlo: central {central:.4f} (recomputed) against {target_central} "
        f"({'within' if central_ok else 'OUTSIDE'} +/-{gate_2_tolerance}), "
        f"half-width {'within' if half_width_ok else 'OUTSIDE'}"
    )

    for name, derived, stored_verdict in (
        ("gate_1", derived_gate_1, results["gate_1"]["verdict"]),
        ("gate_2", derived_gate_2, results["gate_2"]["verdict"]),
    ):
        if derived != stored_verdict:
            raise Failure(
                EXIT_CONTRADICTION,
                f"the package records {name} as {stored_verdict!r}; its own recomputed numbers "
                f"against its own criteria give {derived!r}.",
            )

    both_passed = derived_gate_1 == derived_gate_2 == "pass"
    derived_overall = "reproduced" if both_passed else "not_reproduced"
    if derived_overall != manifest["overall_verdict"]:
        raise Failure(
            EXIT_CONTRADICTION,
            f"manifest claims {manifest['overall_verdict']!r}; the derived gates give "
            f"{derived_overall!r}",
        )

    # The ClaimResult objects are the package's formal verdicts. They must say the same thing.
    claim_ids = {ref: store.get(ref)["claim_id"] for ref in refs.get("claims", [])}
    by_claim = {"pioneer_gate_1_scenarios": derived_gate_1,
                "pioneer_gate_2_monte_carlo": derived_gate_2}
    seen = set()
    for ref in refs.get("claim_results", []):
        result = store.get(ref)
        claim_id = claim_ids.get(result["claim_ref"])
        if claim_id is None:
            raise Failure(
                EXIT_SCHEMA,
                f"claim result {ref[:16]}... references a claim that is not in the manifest",
            )
        expected = by_claim.get(claim_id)
        if expected is None:
            raise Failure(EXIT_SCHEMA, f"unexpected claim {claim_id!r} in claim results")
        if result["verdict"] != expected:
            raise Failure(
                EXIT_CONTRADICTION,
                f"the ClaimResult for {claim_id} records {result['verdict']!r}; the derived "
                f"verdict is {expected!r}",
            )
        seen.add(claim_id)
    if seen != set(by_claim):
        raise Failure(
            EXIT_SCHEMA,
            f"expected a claim result for each of {sorted(by_claim)}, found {sorted(seen)}",
        )

    lines.append(f"  verdict: {derived_overall} (gate 1 {derived_gate_1}, gate 2 {derived_gate_2})")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Pioneer evidence package offline.")
    parser.add_argument("package", type=Path, help="the package directory")
    args = parser.parse_args()
    root: Path = args.package

    if not root.is_dir():
        print(f"VERIFY FAILED: {root} is not a directory", file=sys.stderr)
        return EXIT_UNREADABLE

    try:
        root_hash = check_1_integrity(root)
        print(f"1. file integrity            OK   root hash {root_hash}")

        manifest = check_2_schema_and_references(root)
        print("2. schema, refs, cross-file  OK   documents valid, references resolved, and "
              "each operational file matches its addressed object")

        recomputed = check_3_recomputation(root)
        settings = _load_json(root / "experiment" / "execution_settings.json")
        print(f"3. numerical recomputation   OK   {len(recomputed.accelerations)} scenario "
              f"accelerations recomputed from validated inputs, and the Monte Carlo re-run "
              f"({settings['iterations']} iterations, seed {settings['seed']})")
        for note in recomputed.converted_units:
            print(f"     unit converted: {note}")

        lines = check_4_scientific_agreement(root, manifest, recomputed)
        print("4. scientific agreement      DERIVED (a miss is reported; a contradiction fails)")
        for line in lines:
            print(line)
    except Failure as failure:
        print(f"VERIFY FAILED ({failure.code}): {failure}", file=sys.stderr)
        return failure.code
    except (OSError, ValueError, KeyError) as exc:
        print(f"VERIFY FAILED ({EXIT_UNREADABLE}): the package could not be read: {exc}",
              file=sys.stderr)
        return EXIT_UNREADABLE

    print()
    print("VERIFIED. What was checked, precisely:")
    print("  - these files are the ones that were sealed, and none has changed;")
    print("  - every document satisfies its schema, every reference resolves inside the package,")
    print("    and each operational file agrees with its content-addressed object;")
    print("  - every scenario input carries the unit the model reads it as;")
    print("  - the accelerations and the Monte Carlo statistics were recomputed here, from the")
    print("    packaged inputs, code and recorded seed, and match what the package records;")
    print("  - every residual and verdict was DERIVED from those recomputed numbers and the")
    print(f"    pre-registered targets, and agrees with the recorded "
          f"{manifest['overall_verdict']!r}.")
    print("  This does NOT authenticate the package: the root hash is unsigned, so anyone able to")
    print("  rewrite a file can re-seal it. It shows internal consistency and reproducibility,")
    print("  not that the physics is right or that anyone external has reviewed it.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
