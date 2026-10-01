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
# package's acceptance criteria, where they always have.
#
# **It is RELATIVE, and that is the whole point.** MEASURED 2026-10-01: an earlier version passed
# `abs_tol=1e-12` as well, which is an absolute floor in whatever units the numbers happen to
# carry. Accelerations are stored in SI, around 5e-10 m/s2, so that floor was 0.2% of the value
# and -- decisively -- larger than the tightest scientific threshold, 0.005e-10 = 5e-13 m/s2. A
# package whose recorded acceleration had been moved by 9e-13 m/s2, more than the threshold,
# verified. An absolute tolerance chosen without reference to the scale of what it compares is
# not a tolerance, it is a hole.
#
# `abs_tol` is therefore 0.0: two values are close only if they agree to one part in 1e12. Exact
# zeros still compare equal, because `math.isclose(0.0, 0.0)` is True; a zero against anything
# non-zero is a disagreement, which is the answer we want.
#
# The margin, stated as a ratio rather than as a count of orders: for the scenario accelerations
# the tightest scientific threshold is 0.005 against values of 2.27 to 6.92 (units of 1e-10), so
# in relative terms it is between 7.2e-4 and 2.2e-3 -- at least 7.2e8 times this tolerance.
# `test_a_discrepancy_at_the_scientific_threshold_is_always_detected` checks the property that
# actually matters, per scenario, instead of relying on that arithmetic.
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
    """Relative agreement only. See EXECUTION_TOLERANCE for why there is no absolute floor."""
    return math.isclose(a, b, rel_tol=EXECUTION_TOLERANCE, abs_tol=0.0)


def _one_row_per_scenario(rows: Any, where: str) -> dict[int, Any]:
    """Index rows by scenario, after proving there is exactly one of each.

    MEASURED 2026-10-01: ``{row["scenario"]: row for row in rows}`` silently keeps the last
    occurrence, so a forged scenario 5 prepended to the list vanished from every check while
    staying in the file -- and the report printed scenario 5 twice, once passing at 6.7100 and
    once failing at 6.9166. The uniqueness check that existed ran on the *deduplicated* keys,
    which is to say on the evidence after the damage.

    So the list is validated before any lookup is built from it, and the diagnostic names which
    scenarios are duplicated, missing or unexpected rather than reporting that something is
    wrong somewhere.
    """
    if not isinstance(rows, list) or not rows:
        raise Failure(EXIT_SCHEMA, f"{where} is not a non-empty list of scenario rows")
    numbers = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or "scenario" not in row:
            raise Failure(EXIT_SCHEMA, f"{where}[{index}] has no scenario number")
        numbers.append(row["scenario"])

    expected = list(EXPECTED_SCENARIOS)
    duplicated = sorted({n for n in numbers if numbers.count(n) > 1})
    missing = [n for n in expected if n not in numbers]
    unexpected = sorted({n for n in numbers if n not in expected})
    if duplicated or missing or unexpected or len(numbers) != len(expected):
        raise Failure(
            EXIT_SCHEMA,
            f"{where} must hold exactly one row for each of {expected}, and holds "
            f"{numbers}."
            + (f" Duplicated: {duplicated}." if duplicated else "")
            + (f" Missing: {missing}." if missing else "")
            + (f" Unexpected: {unexpected}." if unexpected else "")
            + " A duplicate row is not a harmless copy: the reader sees both, and a lookup "
              "built from the list sees only one of them.",
        )
    return {row["scenario"]: row for row in rows}

# Every Quantity-shaped document in the package, and the unit the calculation reads it as. This
# is the bounded inventory: if a quantity is consumed or compared anywhere in verification, its
# unit appears here. MEASURED 2026-10-01: `execution_settings.parameters.w_front_mean` and the
# recorded `computed` acceleration were both unchecked, so relabelling either as "kg" verified.
ACCELERATION_UNIT = "m / s2"
SETTING_UNITS = {
    "w_rtgb_mean": "W",
    "w_equip": "W",
    "w_front_mean": "W",
    "w_front_sigma": "W",
    "w_rtgb_relative_sigma": "1",
    "kd_ant_low": "1",
    "kd_ant_high": "1",
    "k_total": "1",
    "ks_lat": "1",
    "lateral_share": "1",
}
# Keys inside stored objects that hold content addresses. Every one must resolve inside the
# package; a reference that points nowhere is not a reference.
REFERENCE_KEYS = frozenset({
    "source_refs", "referent_refs", "artifact_refs", "cited_packages", "assumption_refs",
    "criterion_ref", "claim_ref", "aggregate_ref", "sources", "supersedes",
})


def _quantity_in(raw: Any, expected_unit: str, where: str,
                 converted: list[str] | None = None) -> float:
    """Validate a Quantity document and return its magnitude in ``expected_unit``.

    One place, so that every quantity the calculation consumes is checked the same way: it must
    be a well-formed ``Quantity``, its unit must measure the right dimension, and a compatible
    unit is converted explicitly rather than assumed. ``where`` names the offender.
    """
    try:
        quantity = Quantity.model_validate(raw)
    except Exception as exc:
        raise Failure(EXIT_SCHEMA, f"{where} is not a Quantity: {exc}") from exc
    if quantity.unit != expected_unit:
        if not same_dimension(quantity.unit, expected_unit):
            raise Failure(
                EXIT_SCHEMA,
                f"{where} is given in {quantity.unit!r}, which is not a {expected_unit!r}. The "
                f"calculation reads this value as {expected_unit!r}; accepting the number and "
                f"discarding the unit would let a mislabelled quantity change the answer "
                f"silently.",
            )
        try:
            quantity = convert(quantity, expected_unit)
        except UnitError as exc:
            raise Failure(EXIT_SCHEMA, f"{where}: {exc}") from exc
        if converted is not None:
            converted.append(f"{where}: {raw['unit']} -> {expected_unit}")
    value = float(Decimal(quantity.magnitude))
    if not math.isfinite(value):
        raise Failure(EXIT_SCHEMA, f"{where} is not finite")
    return value



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
    # MEASURED 2026-10-01: only the manifest's own refs block was walked, so a reference held
    # INSIDE a stored object could point nowhere and still verify -- a ClaimResult whose
    # aggregate_ref was sixty-four f's passed every check. A reference that resolves to nothing
    # is not a reference.
    for ref, document in sorted(documents.items()):
        for name, value in _iter_object_references(document, f"object {ref[:16]}..."):
            if value not in stored:
                unresolved.append(f"{name} -> {value[:16]}...")
    if unresolved:
        raise Failure(
            EXIT_SCHEMA,
            "references that do not resolve inside this package:\n  "
            + "\n  ".join(sorted(set(unresolved))),
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

    _check_displayed_values_match_the_record(root, manifest)
    _check_summary_is_generated(root, manifest)
    return manifest


# Every scientific or execution value the report displays that is stored in more than one place,
# with the record that is authoritative for it. MEASURED 2026-10-01: the report rendered the
# seed, iteration count, gate-1 tolerance and all three gate-2 targets from copies that nothing
# compared against the originals, so a package advertising seed 123, one iteration and a
# tolerance of 999 verified while the verification used the real values. Regenerating Markdown
# from unchecked JSON moves the problem; it does not close it.
#
# (displayed copy, authoritative record, dotted path in each)
DUPLICATED_DISPLAY_VALUES = (
    ("manifest.json", "experiment/execution_settings.json", "execution.seed", "seed"),
    ("manifest.json", "experiment/execution_settings.json",
     "execution.iterations", "iterations"),
    ("metrics/results.json", "experiment/acceptance_criteria.json",
     "gate_1.tolerance_1e10", "gate_1.tolerance_1e10"),
    ("metrics/results.json", "experiment/acceptance_criteria.json",
     "gate_2.target_central_1e10", "gate_2.target_central_1e10"),
    ("metrics/results.json", "experiment/acceptance_criteria.json",
     "gate_2.target_half_width_1e10", "gate_2.target_half_width_1e10"),
    ("metrics/results.json", "experiment/acceptance_criteria.json",
     "gate_2.tolerance_1e10", "gate_2.tolerance_1e10"),
)


def _dotted(document: Any, path: str, where: str) -> Any:
    for part in path.split("."):
        if not isinstance(document, dict) or part not in document:
            raise Failure(EXIT_SCHEMA, f"{where} has no {path}")
        document = document[part]
    return document


def _check_displayed_values_match_the_record(root: Path, manifest: dict[str, Any]) -> None:
    """Each duplicated display value against the record verification actually uses.

    Checked per field, so one disagreement cannot mask another: every pair is compared and all
    the mismatches are reported together.
    """
    documents = {
        "manifest.json": manifest,
        "experiment/execution_settings.json": _load_json(
            root / "experiment" / "execution_settings.json"),
        "experiment/acceptance_criteria.json": _load_json(
            root / "experiment" / "acceptance_criteria.json"),
        "metrics/results.json": _load_json(root / "metrics" / "results.json"),
    }
    mismatches = []
    for shown_file, record_file, shown_path, record_path in DUPLICATED_DISPLAY_VALUES:
        shown = _dotted(documents[shown_file], shown_path, shown_file)
        record = _dotted(documents[record_file], record_path, record_file)
        same = (
            Decimal(str(shown)) == Decimal(str(record))
            if isinstance(shown, (int, float, str)) and isinstance(record, (int, float, str))
            else shown == record
        )
        if not same:
            mismatches.append(
                f"  {shown_file}:{shown_path} shows {shown!r}, but "
                f"{record_file}:{record_path} -- the record verification uses -- says {record!r}"
            )
    if mismatches:
        raise Failure(
            EXIT_SCHEMA,
            "the report would display values that disagree with the record they come from:\n"
            + "\n".join(mismatches),
        )


def _iter_object_references(document: Any, prefix: str) -> list[tuple[str, str]]:
    """Every content address held in a reference-shaped field of a stored document.

    Keyed by field name rather than by hunting for anything 64 hex characters long: a digest
    that is not a reference -- a file's sha256, say -- names bytes that are deliberately not
    package content, and demanding that it resolve here would be wrong.
    """
    found: list[tuple[str, str]] = []
    if isinstance(document, dict):
        for key, value in document.items():
            if key in REFERENCE_KEYS:
                for item in (value if isinstance(value, list) else [value]):
                    if isinstance(item, str) and len(item) == 64:
                        found.append((f"{prefix}.{key}", item))
            else:
                found.extend(_iter_object_references(value, f"{prefix}.{key}"))
    elif isinstance(document, list):
        for index, item in enumerate(document):
            found.extend(_iter_object_references(item, f"{prefix}[{index}]"))
    return found


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


def _validated_scenario_inputs(
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

    _one_row_per_scenario(rows, "experiment/scenario_inputs.json scenarios")

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
            value = _quantity_in(
                inputs[name], expected_unit, f"scenario {number} input {name!r}", converted
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
        if "published_a_th" in row:
            _quantity_in(
                row["published_a_th"], ACCELERATION_UNIT,
                f"scenario {number} published_a_th", converted,
            )
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

    if set(settings["parameters"]) != set(SETTING_UNITS):
        missing = sorted(set(SETTING_UNITS) - set(settings["parameters"]))
        extra = sorted(set(settings["parameters"]) - set(SETTING_UNITS))
        raise Failure(
            EXIT_SCHEMA,
            f"execution settings are wrong: missing {missing}, unexpected {extra}",
        )
    parameters: dict[str, float] = {}
    for name, expected_unit in SETTING_UNITS.items():
        parameters[name] = _quantity_in(
            settings["parameters"][name], expected_unit, f"execution setting {name!r}"
        )

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

    stored_scenarios = _one_row_per_scenario(
        recorded["gate_1"]["scenarios"], "metrics/results.json gate_1.scenarios"
    )

    mismatches = []
    for number, values in sorted(inputs.items()):
        recomputed = model.thermal_acceleration(**values)
        out.accelerations[number] = recomputed
        stored = _quantity_in(
            stored_scenarios[number]["computed"], ACCELERATION_UNIT,
            f"scenario {number} recorded acceleration", out.converted_units,
        )
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
        targets[int(key)] = _quantity_in(
            document["a_th"], ACCELERATION_UNIT, f"referent for scenario {key}"
        ) / 1e-10

    # The same relationship check one level up: a claim must cite the criterion that was applied.
    for claim_ref in refs.get("claims", []):
        claim = store.get(claim_ref)
        if claim["criterion_ref"] != refs["criterion"]:
            raise Failure(
                EXIT_CONTRADICTION,
                f"claim {claim['claim_id']} cites criterion {claim['criterion_ref'][:16]}..., "
                f"but the criteria applied here are {refs['criterion'][:16]}...",
            )

    criterion_targets = [float(Decimal(t)) for t in criteria["gate_1"]["targets_1e10"]]
    for index, number in enumerate(EXPECTED_SCENARIOS):
        if not _close(criterion_targets[index], targets[number]):
            raise Failure(
                EXIT_CONTRADICTION,
                f"scenario {number}: the acceptance criteria say the published value is "
                f"{criterion_targets[index]}, the referent object says {targets[number]}",
            )

    tolerance = float(Decimal(criteria["gate_1"]["tolerance_1e10"]))
    stored_scenarios = _one_row_per_scenario(
        results["gate_1"]["scenarios"], "metrics/results.json gate_1.scenarios"
    )
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
        # Existence is not enough. The verdict has to be about the results this run actually
        # recomputed; a ClaimResult aggregating some other document is a verdict on something
        # else, wearing this package's name.
        if result["aggregate_ref"] != refs["results"]:
            raise Failure(
                EXIT_CONTRADICTION,
                f"the ClaimResult for {claim_id} aggregates "
                f"{result['aggregate_ref'][:16]}..., but the results verified here are "
                f"{refs['results'][:16]}.... The verdict is not about these numbers.",
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
    print("  - every quantity consumed or compared -- scenario inputs, published targets,")
    print("    execution settings and recorded results -- carries the unit the calculation")
    print("    reads it as, converted explicitly where it was given in a compatible one;")
    print("  - every reference inside every stored object resolves here, and the claim results")
    print("    aggregate the results that were actually recomputed;")
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
