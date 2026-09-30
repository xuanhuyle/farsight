"""Verify a Pioneer evidence package, offline, on the zero-extras base install.

Four checks, kept separate because they answer different questions and an auditor needs to know
which one failed:

1. **File integrity** -- are these the bytes that were sealed?
2. **Schema and reference consistency** -- does every document satisfy its schema, and does
   every reference resolve to something in this package?
3. **Numerical recomputation** -- recomputing from the packaged inputs, with the packaged code,
   do the packaged results come back?
4. **Scientific agreement** -- do those results meet the pre-registered targets?

**Only the first three can fail this command.** Check 4 reports a scientific verdict, and this
package's verdict is that two gates were missed. That is a result, not a fault, and a verifier
that exited nonzero for it would be unusable on exactly the packages worth publishing. What
check 4 *can* fail on is disagreement: if the package records `pass` where recomputation gives
`fail`, the package is lying about its own numbers, and that is an integrity failure with a
scientific costume on.

**A hash match proves neither physical correctness nor external review.** It proves the files
are the ones that were sealed. Everything this command can and cannot establish is printed at
the end of a successful run, so the claim cannot be overstated by a reader in a hurry.

This imports no engine: not spiceypy, not Basilisk, not GMAT, and it opens no socket. The
``auditor_boundary`` import contract enforces the first for ``farsight.evidence``; this script
stays on the same side of that line.

Usage::

    python experiments/pioneer_thermal/verify_evidence_package.py <package dir>

Exit codes: 0 verified, 2 integrity, 3 schema or reference, 4 recomputation mismatch,
5 the package disagrees with its own numbers, 6 the package could not be read at all.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from farsight.evidence.manifest import check_integrity
from farsight.registry.objects import ObjectStore, ObjectStoreError
from farsight.schemas.design import Claim, ClaimResult
from farsight.schemas.knowledge import Assumption, Source

EXIT_OK = 0
EXIT_INTEGRITY = 2
EXIT_SCHEMA = 3
EXIT_RECOMPUTATION = 4
EXIT_DISAGREEMENT = 5
EXIT_UNREADABLE = 6

REQUIRED_REGISTERS = (
    "assumptions.json", "unknowns.json", "collapses.json",
    "validity_violations.json", "excluded_runs.json",
)
# Which schema each stored document is validated against. A document whose "document" key names
# a plain record (criteria, referents, results) has no schema here and is checked structurally.
TYPED = {"source_id": Source, "assumption_id": Assumption, "claim_id": Claim,
         "claim_ref": ClaimResult}


class Failure(Exception):
    """A verification failure carrying the exit code that names which check failed."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise Failure(EXIT_SCHEMA, f"required file missing: {path.name} (looked at {path})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Failure(EXIT_SCHEMA, f"{path} is not valid JSON: {exc}") from exc


def check_1_integrity(root: Path) -> str:
    problems = check_integrity(root)
    if problems:
        lines = "\n".join(f"  {p}" for p in problems)
        raise Failure(
            EXIT_INTEGRITY,
            f"{len(problems)} file(s) do not match the sealed manifest:\n{lines}",
        )
    recorded = (root / "hashes" / "root_hash.txt").read_text(encoding="utf-8").strip()
    return recorded


def check_2_schema_and_references(root: Path) -> dict[str, Any]:  # noqa: PLR0912
    """Every document valid, every reference resolvable, every register present.

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

    # Re-addressing every object is what makes the store's address a guarantee rather than a
    # filename; ObjectStore.get raises if the bytes no longer hash to the path they sit at.
    for ref in sorted(stored):
        try:
            document = store.get(ref)
        except ObjectStoreError as exc:
            raise Failure(EXIT_SCHEMA, str(exc)) from exc
        for marker, model in TYPED.items():
            if marker in document:
                try:
                    model.model_validate(document)
                except Exception as exc:  # pydantic ValidationError, kept broad deliberately
                    raise Failure(
                        EXIT_SCHEMA,
                        f"object {ref[:16]}... does not satisfy {model.__name__}:\n{exc}",
                    ) from exc
                break

    # Every reference the manifest makes has to land inside this package.
    unresolved = []
    for name, value in _iter_refs(manifest["refs"]):
        if value not in stored:
            unresolved.append(f"{name} -> {value[:16]}...")
    if unresolved:
        raise Failure(
            EXIT_SCHEMA,
            "the manifest references objects that are not in this package:\n  "
            + "\n  ".join(unresolved),
        )

    # A claim without a falsifier is a sentence, not a claim (ADR-007 decision 3).
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


def _import_path(path: Path, name: str) -> Any:
    """Import a module from a file without writing anything beside it.

    MEASURED: importing the packaged code wrote ``code/__pycache__/`` INTO the package, so the
    first verification passed and every one after it failed on an unlisted file. Verification
    that modifies the thing it is verifying is not verification, and an auditor would reasonably
    conclude the package was tampered with -- by us, correctly, at the moment they checked it.
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


def check_3_recomputation(root: Path) -> list[tuple[int, str, str]]:
    """Recompute every scenario from the packaged inputs, using the packaged code.

    This is the substantive check: it does not compare the package to itself, it re-derives the
    numbers from the inputs as recorded and sees whether the recorded results come back. The
    code comes from ``code/`` inside the package, so nothing outside the package is consulted.
    """
    model = _import_path(
        root / "code" / "reproduce_thermal_acceleration.py", "packaged_pioneer_model"
    )
    inputs = _load_json(root / "experiment" / "scenario_inputs.json")["scenarios"]
    recorded = {
        row["scenario"]: row["computed"]["magnitude"]
        for row in _load_json(root / "metrics" / "results.json")["gate_1"]["scenarios"]
    }
    builder = _import_path(
        Path(__file__).resolve().parent / "build_evidence_package.py", "build_evidence_package"
    )

    rows = []
    mismatches = []
    for row in inputs:
        scenario = row["scenario"]
        values = {
            key: float(Decimal(quantity["magnitude"]))
            for key, quantity in row["inputs"].items()
        }
        recomputed = builder.decimal_string(model.thermal_acceleration(**values))
        rows.append((scenario, recorded.get(scenario, "<absent>"), recomputed))
        if recorded.get(scenario) != recomputed:
            mismatches.append(
                f"  scenario {scenario}: package says {recorded.get(scenario)}, "
                f"recomputation gives {recomputed}"
            )
    if not rows:
        raise Failure(EXIT_RECOMPUTATION, "no scenarios were recomputed; the inputs file is empty")
    if mismatches:
        raise Failure(
            EXIT_RECOMPUTATION,
            "recomputing from the packaged inputs does not reproduce the packaged results:\n"
            + "\n".join(mismatches),
        )
    return rows


def check_4_scientific_agreement(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Compare the results against the pre-registered targets. Reports; does not fail on a miss.

    Returns human-readable lines. Raises only when the package's recorded verdict disagrees with
    what its own numbers produce -- a package that says `pass` over failing numbers is not a
    scientific disappointment, it is a false claim.
    """
    criteria = _load_json(root / "experiment" / "acceptance_criteria.json")
    results = _load_json(root / "metrics" / "results.json")
    lines = []

    tolerance = Decimal(criteria["gate_1"]["tolerance_1e10"])
    targets = [Decimal(t) for t in criteria["gate_1"]["targets_1e10"]]
    misses = []
    for row, _target in zip(results["gate_1"]["scenarios"], targets, strict=True):
        residual = Decimal(row["residual_1e10"])
        within = abs(residual) <= tolerance
        if not within:
            misses.append(f"scenario {row['scenario']} off by {residual:+f}")
        lines.append(
            f"  scenario {row['scenario']}: residual {residual:+.4f}, "
            f"{'within' if within else 'OUTSIDE'} the pre-registered +/-{tolerance}"
        )
    derived_gate_1 = "fail" if misses else "pass"

    central = Decimal(results["gate_2"]["central_1e10"])
    target_central = Decimal(criteria["gate_2"]["target_central_1e10"])
    gate_2_tolerance = Decimal(criteria["gate_2"]["tolerance_1e10"])
    half_width_ok = min(
        abs(Decimal(results["gate_2"]["half_width_1p96_sigma_1e10"])
            - Decimal(criteria["gate_2"]["target_half_width_1e10"])),
        abs(Decimal(results["gate_2"]["half_width_percentile_1e10"])
            - Decimal(criteria["gate_2"]["target_half_width_1e10"])),
    ) <= gate_2_tolerance
    central_ok = abs(central - target_central) <= gate_2_tolerance
    derived_gate_2 = "pass" if (central_ok and half_width_ok) else "fail"
    lines.append(
        f"  monte carlo: central {central:.4f} against {target_central} "
        f"({'within' if central_ok else 'OUTSIDE'} +/-{gate_2_tolerance}), "
        f"half-width {'within' if half_width_ok else 'OUTSIDE'}"
    )

    for name, derived, recorded in (
        ("gate_1", derived_gate_1, results["gate_1"]["verdict"]),
        ("gate_2", derived_gate_2, results["gate_2"]["verdict"]),
    ):
        if derived != recorded:
            raise Failure(
                EXIT_DISAGREEMENT,
                f"the package records {name} as {recorded!r}, but its own numbers against its "
                f"own criteria give {derived!r}. The package disagrees with itself.",
            )
    both_passed = derived_gate_1 == derived_gate_2 == "pass"
    derived_overall = "reproduced" if both_passed else "not_reproduced"
    if derived_overall != manifest["overall_verdict"]:
        raise Failure(
            EXIT_DISAGREEMENT,
            f"manifest claims {manifest['overall_verdict']!r}; the gates give {derived_overall!r}",
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
        print("2. schema and references     OK   every document valid, every reference resolved")

        rows = check_3_recomputation(root)
        print(f"3. numerical recomputation   OK   {len(rows)} scenarios recomputed from packaged "
              f"inputs, all matching")

        lines = check_4_scientific_agreement(root, manifest)
        print("4. scientific agreement      REPORTED (this check never fails the command)")
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
    print("VERIFIED. What that means, precisely:")
    print("  - these files are the ones that were sealed, and none has changed;")
    print("  - every document satisfies its schema and every reference resolves inside;")
    print("  - recomputing from the packaged inputs reproduces the packaged results;")
    print(f"  - the recorded scientific verdict is {manifest['overall_verdict']!r}, and it "
          f"matches what the numbers give.")
    print("  It does NOT mean the physics is right, that the reproduction succeeded, or that "
          "anyone external has reviewed it.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
