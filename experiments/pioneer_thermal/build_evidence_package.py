"""Build an evidence package for the Pioneer thermal reproduction.

This is the first end-to-end evidence workflow in FarSight, and it is deliberately one
experiment rather than a general campaign runner. What it demonstrates is narrow: that the
reusable machinery -- content-addressed identity, the typed vocabulary, the file manifest --
adds something checkable to a calculation that already worked without it.

**The original calculation stays authoritative.** Every number here comes from
``reproduce_thermal_acceleration.py``, imported and called. No formula is restated in this file;
if one were, the package could disagree with the science it claims to describe.

**A failed reproduction packages normally.** The Pioneer reproduction misses two of its
pre-registered gates, and that is its result, not an error. Packaging refuses only on
operational problems -- a missing input, an unwritable directory, an object that fails its own
schema. The scientific verdict is content, and it is recorded as ``fail`` without the build
treating it as one. A packager that could only package successes would be an advertising tool.

**Partial format.** This writes a labelled subset of ADR-007; see ``PARTIAL_FORMAT.md`` in any
built package for exactly what is and is not supported.

Usage::

    python experiments/pioneer_thermal/build_evidence_package.py --out <dir>
    python experiments/pioneer_thermal/build_evidence_package.py --out <dir> \\
        --counterfactual w_rtgb_geometric

Exit codes: 0 built, 2 an operational failure (never a scientific verdict).
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from farsight.evidence.manifest import seal
from farsight.hashing.canonical import content_hash
from farsight.registry.atomic import write_atomic
from farsight.registry.objects import ObjectStore
from farsight.schemas.belief import Pedigree
from farsight.schemas.common import Provenance, Quantity
from farsight.schemas.design import Claim, ClaimResult
from farsight.schemas.knowledge import Assumption, Source, SourceIdentifier

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODEL_PATH = HERE / "reproduce_thermal_acceleration.py"
PREREGISTRATION_PATH = HERE / "PREREGISTRATION.md"

PACKAGE_FORMAT = "farsight-evidence-partial/1"
ACCELERATION_UNIT = "m / s2"
# Every number is recorded as a decimal string, never a JSON float (ADR-001 rule 2).


class BuildError(RuntimeError):
    """An operational failure. Never raised for a scientific verdict."""


def load_model() -> Any:
    """The authoritative calculation, imported rather than reimplemented."""
    spec = importlib.util.spec_from_file_location("reproduce_thermal_acceleration", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot import the model at {MODEL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def decimal_string(value: float) -> str:
    """A float as a decimal string that reads back as the identical float.

    MEASURED while building the counterfactual: rounding to twelve digits made the package
    un-recomputable. The counterfactual's W_RTGb is 2024/14 = 144.5714285714..., and a scenario
    recomputed from the *rounded* input landed a digit away from the recorded result, so
    verification failed on a package that was perfectly honest.

    The cause was a category error on my part: if the package records rounded inputs, then the
    recorded inputs are not the inputs that produced the recorded results, and no amount of
    tolerance-fiddling fixes that -- it just hides it. Python's ``repr`` gives the shortest
    string that reads back as the same float, so what the package records IS what was computed
    with, exactly, and recomputation is bit-for-bit.
    """
    text = repr(float(value))
    # `repr` can emit forms the DECIMAL_RE grammar refuses ("inf", "1e-10" is fine but "1E-10"
    # or a bare "5." would not be). Round-tripping through Decimal proves the spelling parses,
    # and the equality check proves nothing was lost.
    if float(Decimal(text)) != float(value):
        raise BuildError(f"{value!r} does not round-trip through its decimal spelling {text!r}")
    return text


def code_identity() -> dict[str, Any]:
    """Which commit produced this, and whether the tree was dirty when it did.

    A dirty checkout is recorded, not refused. Refusing would push the operator into committing
    noise to get a package built; recording lets a reader discount the claim appropriately.
    """
    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=20, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return {
        "commit": commit,
        "commit_known": commit is not None,
        "dirty": None if status is None else bool(status.strip()),
        "dirty_paths": [] if not status else sorted(
            line[3:] for line in status.splitlines() if line[3:]
        )[:50],
        "model_file": MODEL_PATH.name,
        "model_sha256": content_hash(MODEL_PATH.read_text(encoding="utf-8")),
    }


def environment_fingerprint() -> dict[str, Any]:
    """Enough of the environment to tell whether a difference is the machine or the science."""
    import numpy

    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": numpy.__version__,
        "engine_extras_installed": _installed_extras(),
    }


def _installed_extras() -> dict[str, bool]:
    """Recorded so a reader can see the package was not built against an engine it never used."""
    found = {}
    for name in ("spiceypy", "bsk", "pandas", "matplotlib"):
        found[name] = importlib.util.find_spec(name) is not None
    return found


# ------------------------------------------------------------------------------------------
# The records. Existing schemas wherever one fits.


def sources() -> dict[str, Source]:
    """The publications this reproduction reads. `Source` is the citation of record (ADR-021)."""
    return {
        "modelling_2012": Source(
            schema_version=1,
            source_id="francisco_2012_thermal",
            title=(
                "Modelling the reflective thermal contribution to the acceleration of the "
                "Pioneer spacecraft"
            ),
            origin="published_literature",
            issued="2012",
            identifiers=[
                SourceIdentifier(scheme="arxiv", value="1103.5222", part=None),
                SourceIdentifier(scheme="doi", value="10.1016/j.physletb.2012.04.034", part=None),
            ],
            artifact_refs=[],
        ),
        "method_2008": Source(
            schema_version=1,
            source_id="bertolami_2008_method",
            title=(
                "Thermal Analysis of the Pioneer Anomaly: A Method to estimate radiative "
                "momentum transfer"
            ),
            origin="published_literature",
            issued="2008",
            identifiers=[SourceIdentifier(scheme="arxiv", value="0807.0041", part=None)],
            artifact_refs=[],
        ),
        "anomaly_2002": Source(
            schema_version=1,
            source_id="anderson_2002_anomaly",
            title="Study of the anomalous acceleration of Pioneer 10 and 11",
            origin="published_literature",
            issued="2002",
            identifiers=[
                SourceIdentifier(scheme="doi", value="10.1103/PhysRevD.65.082004", part=None)
            ],
            artifact_refs=[],
        ),
    }


def assumptions(source_refs: dict[str, str], counterfactual: str | None) -> list[Assumption]:
    """What this reproduction assumes, each with what breaks if it is wrong.

    These are the judgements that are not in the paper's equations. They are the reason the
    package is worth more than the script's stdout: the script applies them, and only this
    register says they were applied at all.
    """
    pedigree = Pedigree(
        level="published_design",
        sources=[source_refs["modelling_2012"]],
        assessor="h. le",
        assessed_on=dt.date(2026, 9, 28),
    )
    declared = [
        Assumption(
            schema_version=1,
            assumption_id="eq16_half_life_governs",
            statement=(
                "The plutonium half-life is 87.72 years, the value Eq. (16) computes with, not "
                "the 87.74 years the prose of section 3.4 states."
            ),
            consequence_if_false=(
                "Every power at t > 0 shifts by about 0.005% at t = 26 years, which is far "
                "inside every tolerance here and would change no verdict."
            ),
            bound=None,
            review_by=None,
            pedigree=pedigree,
            source_refs=[source_refs["modelling_2012"]],
        ),
        Assumption(
            schema_version=1,
            assumption_id="coefficients_are_inputs",
            statement=(
                "The reflection and shadow coefficients of Eqs. (10) to (14) are taken as "
                "printed and used as inputs; this reproduction does not derive them from the "
                "spacecraft geometry."
            ),
            consequence_if_false=(
                "Nothing here would detect an error in the paper's geometric integrals. Every "
                "result is conditional on those coefficients being what the paper says."
            ),
            bound=None,
            review_by=None,
            pedigree=pedigree,
            source_refs=sorted([source_refs["modelling_2012"], source_refs["method_2008"]]),
        ),
        Assumption(
            schema_version=1,
            assumption_id="w_rtgb_as_published",
            statement=(
                "W_RTGb is 143.86 W, the value Eq. (18) prints without a derivation."
            ),
            consequence_if_false=(
                "The scenario accelerations move. The stated geometry gives 144.57 W, which is "
                "0.49% higher; the counterfactual package built with "
                "--counterfactual w_rtgb_geometric shows the effect."
            ),
            bound=None,
            review_by=None,
            pedigree=pedigree,
            source_refs=[source_refs["modelling_2012"]],
        ),
    ]
    if counterfactual == "w_rtgb_geometric":
        declared.append(
            Assumption(
                schema_version=1,
                assumption_id="counterfactual_w_rtgb_geometric",
                statement=(
                    "COUNTERFACTUAL: W_RTGb is instead 144.571 W, the inward-facing RTG base "
                    "share reconstructed from the stated cylinder geometry, which is exactly "
                    "one fourteenth of the RTG thermal power."
                ),
                consequence_if_false=(
                    "This is a sensitivity demonstration, not a correction and not a claim "
                    "about which value is right. It exists to show what the packaged results "
                    "do when one stated assumption is changed, and it makes the published "
                    "scenarios agree less well, not better."
                ),
                bound=None,
                review_by=None,
                pedigree=pedigree,
                source_refs=[source_refs["modelling_2012"]],
            )
        )
    return declared


def scenario_inputs(model: Any, w_rtgb_override: float | None) -> list[dict[str, Any]]:
    """Every scenario's inputs as decimal-string quantities -- no JSON float anywhere."""
    rows = []
    for scenario in model.SCENARIOS:
        values = scenario.inputs()
        if w_rtgb_override is not None:
            values = {**values, "w_rtgb": w_rtgb_override}
        rows.append({
            "scenario": scenario.number,
            "label": scenario.label,
            "published_a_th": Quantity(
                magnitude=decimal_string(scenario.published_a_th * 1e-10),
                unit=ACCELERATION_UNIT,
            ).model_dump(mode="json"),
            "inputs": {
                "w_rtgb": Quantity(magnitude=decimal_string(values["w_rtgb"]), unit="W"),
                "w_front": Quantity(magnitude=decimal_string(values["w_front"]), unit="W"),
                "w_lat": Quantity(magnitude=decimal_string(values["w_lat"]), unit="W"),
                "w_back": Quantity(magnitude=decimal_string(values["w_back"]), unit="W"),
                "kd_ant": Quantity(magnitude=decimal_string(values["kd_ant"]), unit="1"),
                "ks_ant": Quantity(magnitude=decimal_string(values["ks_ant"]), unit="1"),
                "ks_lat": Quantity(magnitude=decimal_string(values["ks_lat"]), unit="1"),
            },
        })
    for row in rows:
        row["inputs"] = {k: v.model_dump(mode="json") for k, v in row["inputs"].items()}
    return rows


def compute(model: Any, w_rtgb_override: float | None, seed: int,
            iterations: int) -> dict[str, Any]:
    """Run the authoritative calculation. Every number below is returned by the model module."""
    import numpy as np

    scenario_results = []
    for scenario in model.SCENARIOS:
        values = scenario.inputs()
        if w_rtgb_override is not None:
            values = {**values, "w_rtgb": w_rtgb_override}
        computed = model.thermal_acceleration(**values)
        residual = computed / 1e-10 - scenario.published_a_th
        scenario_results.append({
            "scenario": scenario.number,
            "computed": Quantity(
                magnitude=decimal_string(computed), unit=ACCELERATION_UNIT
            ).model_dump(mode="json"),
            "residual_1e10": decimal_string(residual),
            "within_tolerance": bool(abs(residual) <= model.GATE1_TOLERANCE),
        })

    samples = model.sample_accelerations(
        np.random.default_rng(seed), iterations,
        w_rtgb_mean=w_rtgb_override if w_rtgb_override is not None else model._S4.w_rtgb,
        w_equip=model.W_EQUIP_T26, w_front_mean=model._S4.w_front, w_front_sigma=7.5,
    )
    stats = model.summarise(samples)
    low, high = model.interval_bounds()
    return {
        "gate_1": {
            "scenarios": scenario_results,
            "tolerance_1e10": decimal_string(model.GATE1_TOLERANCE),
            "verdict": "pass" if all(r["within_tolerance"] for r in scenario_results) else "fail",
        },
        "gate_2": {
            "central_1e10": decimal_string(stats["mean"]),
            "half_width_1p96_sigma_1e10": decimal_string(stats["half_width_1p96_sigma"]),
            "half_width_percentile_1e10": decimal_string(stats["half_width_percentile"]),
            "target_central_1e10": decimal_string(model.GATE2_CENTRAL),
            "target_half_width_1e10": decimal_string(model.GATE2_HALF_WIDTH),
            "tolerance_1e10": decimal_string(model.GATE2_TOLERANCE),
            "verdict": _gate_2_verdict(model, stats),
        },
        "reported_not_gating": {
            "interval_worst_corner_low_1e10": decimal_string(low),
            "interval_worst_corner_high_1e10": decimal_string(high),
            "monte_carlo_p2p5_1e10": decimal_string(stats["p2p5"]),
            "monte_carlo_p97p5_1e10": decimal_string(stats["p97p5"]),
        },
    }


def _gate_2_verdict(model: Any, stats: dict[str, float]) -> str:
    central_ok = abs(stats["mean"] - model.GATE2_CENTRAL) <= model.GATE2_TOLERANCE
    width_ok = min(
        abs(stats["half_width_1p96_sigma"] - model.GATE2_HALF_WIDTH),
        abs(stats["half_width_percentile"] - model.GATE2_HALF_WIDTH),
    ) <= model.GATE2_TOLERANCE
    return "pass" if central_ok and width_ok else "fail"


def acceptance_criteria(model: Any) -> dict[str, Any]:
    """The pre-registered thresholds, as a document with its own address.

    A plain document rather than a typed acceptance rule: ADR-009's metric registry is not
    implemented, and inventing a half-typed stand-in would claim an integration that does not
    exist. PARTIAL_FORMAT.md records this.
    """
    return {
        "document": "pioneer_thermal_acceptance_criteria",
        "preregistration": "experiment/PREREGISTRATION.md",
        "gate_1": {
            "statement": "the five Table 3 scenario accelerations, to printed precision",
            "tolerance_1e10": decimal_string(model.GATE1_TOLERANCE),
            "targets_1e10": [decimal_string(s.published_a_th) for s in model.SCENARIOS],
        },
        "gate_2": {
            "statement": "the Monte Carlo at t = 26 yr, central value and 95% half-width",
            "tolerance_1e10": decimal_string(model.GATE2_TOLERANCE),
            "target_central_1e10": decimal_string(model.GATE2_CENTRAL),
            "target_half_width_1e10": decimal_string(model.GATE2_HALF_WIDTH),
        },
        "both_gates_must_pass": True,
    }


def claims(model: Any, criterion_ref: str, referent_refs: dict[int, str],
           source_refs: dict[str, str]) -> list[Claim]:
    """The falsifiable sentences this package stands behind (ADR-007 decision 3).

    Each carries its falsifier. "The rebuild is close to the paper" is not a claim; the schema
    refuses it, and so does the pre-registration it comes from.
    """
    return [
        Claim(
            schema_version=1,
            claim_id="pioneer_gate_1_scenarios",
            sentence=(
                "Each of the five scenario accelerations printed in Table 3 of arXiv:1103.5222 "
                "is reproduced, from the inputs that paper prints, to within 0.005e-10 m/s2."
            ),
            falsifier=(
                "any scenario whose rebuilt acceleration differs from its printed value by more "
                "than 0.005e-10 m/s2"
            ),
            scope_conditions=[
                "the paper's own coefficients are used as inputs, not derived",
                "arithmetic only; no spacecraft geometry is integrated",
            ],
            criterion_ref=criterion_ref,
            referent_refs=sorted(referent_refs[s.number] for s in model.SCENARIOS),
            run_set="pioneer_thermal_scenarios",
            tier="C",
            cited_packages=[],
            supersedes=None,
            revision_reason=None,
        ),
        Claim(
            schema_version=1,
            claim_id="pioneer_gate_2_monte_carlo",
            sentence=(
                "The Monte Carlo result at t = 26 years, (5.8 +/- 1.3)e-10 m/s2 in Eq. (20) of "
                "arXiv:1103.5222, is reproduced to within 0.05e-10 m/s2 in both its central "
                "value and its 95 percent half-width."
            ),
            falsifier=(
                "a rebuilt central value differing from 5.8e-10 m/s2 by more than 0.05e-10, or "
                "both half-width readings differing from 1.3e-10 by more than 0.05e-10"
            ),
            scope_conditions=[
                "Scenario 4 means, as section 4.2 states",
                "10^4 iterations under one recorded seed",
                "the equipment power is conserved at 56 W when W_front is sampled",
            ],
            criterion_ref=criterion_ref,
            referent_refs=[source_refs["modelling_2012"]],
            run_set="pioneer_thermal_monte_carlo",
            tier="C",
            cited_packages=[],
            supersedes=None,
            revision_reason=None,
        ),
    ]


def registers(declared: list[Assumption], assumption_refs: list[str]) -> dict[str, Any]:
    """The five registers of ADR-007 decision 4. An empty one asserts there is nothing to declare.

    Four are empty here and that is a claim, not an omission: this experiment declares no
    unknown with a swept bracket, performs no epistemic collapse, declares no validity envelope
    to violate, and excludes no run. Saying so is the point -- a missing register is a
    verification failure, precisely so that silence cannot be mistaken for nothing to report.
    """
    return {
        "assumptions.json": {
            "count": len(declared),
            "assumption_refs": assumption_refs,
            "assumptions": [a.model_dump(mode="json") for a in declared],
        },
        "unknowns.json": {
            "count": 0,
            "unknowns": [],
            "note": (
                "No parameter is carried as a swept Unknown. Every input is a published value or "
                "a stated assumption; the epistemic ranges the paper gives are carried as "
                "intervals in the reported-not-gating section, beside the Monte Carlo result and "
                "never in place of it."
            ),
        },
        "collapses.json": {
            "count": 0,
            "collapses": [],
            "note": (
                "No EpistemicCollapse. Nothing here turns an interval into a distribution: the "
                "Monte Carlo samples the distributions the paper itself declares, and the "
                "interval treatment is reported separately without being sampled."
            ),
        },
        "validity_violations.json": {
            "count": 0,
            "violations": [],
            "note": "No validity envelope is declared for this arithmetic, so none is exited.",
        },
        "excluded_runs.json": {
            "count": 0,
            "excluded": [],
            "note": (
                "No run is excluded. The Monte Carlo draws every sample into the statistics; no "
                "draw is rejected or resampled."
            ),
        },
    }


def render_summary(manifest: dict[str, Any], results: dict[str, Any],
                   declared: list[Assumption]) -> str:
    """``report/summary.md``, generated from the JSON (ADR-007 decision 5).

    Deterministic, and never hand-edited: the verifier re-renders it and fails on any
    difference, so prose in this package cannot say something the JSON does not.
    """
    gate_1 = results["gate_1"]
    gate_2 = results["gate_2"]
    dirty_note = " (WORKING TREE DIRTY)" if manifest["code"]["dirty"] else ""
    lines = [
        "# Pioneer thermal reproduction -- evidence summary",
        "",
        ("GENERATED FROM THE PACKAGE JSON. Do not edit: the verifier re-renders this file "
         "and fails on any difference."),
        "",
        (f"- Package format: `{manifest['package_format']}`, a labelled subset of ADR-007; "
         "see `PARTIAL_FORMAT.md`"),
        f"- Variant: **{manifest['variant']}**",
        f"- Built from commit: `{manifest['code']['commit'] or 'unknown'}`{dirty_note}",
        (f"- Seed: `{manifest['execution']['seed']}`, iterations: "
         f"`{manifest['execution']['iterations']}`"),
        "",
        "## Verdict",
        "",
        (f"**{manifest['overall_verdict'].upper()}** -- gate 1 `{gate_1['verdict']}`, "
         f"gate 2 `{gate_2['verdict']}`."),
        "",
        ("A failed gate is a scientific result, not an operational error. This package was "
         "built and sealed normally."),
        "",
        "## Gate 1 -- the five scenarios of Table 3",
        "",
        "| Scenario | Rebuilt (1e-10 m/s2) | Residual | Within tolerance |",
        "| --- | --- | --- | --- |",
    ]
    for row in gate_1["scenarios"]:
        magnitude = Decimal(row["computed"]["magnitude"]) / Decimal("1e-10")
        residual = Decimal(row["residual_1e10"])
        lines.append(
            f"| {row['scenario']} | {magnitude:.4f} | {residual:+.4f} | "
            f"{'yes' if row['within_tolerance'] else '**NO**'} |"
        )
    lines += [
        "",
        f"Tolerance: +/-{gate_1['tolerance_1e10']} in units of 1e-10 m/s2.",
        "",
        "## Gate 2 -- the Monte Carlo at t = 26 years",
        "",
        f"- Rebuilt central: `{gate_2['central_1e10']}`, target `{gate_2['target_central_1e10']}`",
        (f"- Rebuilt half-width at 1.96 sigma: `{gate_2['half_width_1p96_sigma_1e10']}`, "
         f"target `{gate_2['target_half_width_1e10']}`"),
        f"- Tolerance: `{gate_2['tolerance_1e10']}`",
        "",
        "## Assumptions on record",
        "",
    ]
    for assumption in declared:
        lines.append(f"- **{assumption.assumption_id}** -- {assumption.statement}")
    lines += [
        "",
        "## What this package does not establish",
        "",
        ("- It does not show the source paper is wrong. A difference between a printed number "
         "and a rebuild from printed inputs is equally well explained by a convention the "
         "paper does not state."),
        "- It does not check the paper's geometry: those coefficients are inputs here.",
        ("- It carries no external review. Internal cross-checking is not validation, and a "
         "hash match proves neither physical correctness nor that a competent reader agreed."),
        "",
    ]
    return "\n".join(lines)


PARTIAL_FORMAT_NOTE = """# What this package implements, and what it does not

This is a **labelled partial** of ADR-007, written for one experiment. ADR-007 describes the
full evidence package; this directory implements the subset the Pioneer reproduction needs, and
names the rest rather than leaving a reader to discover the gaps.

## Implemented

- The directory-of-files layout, and the one-level Merkle root: `hashes/file_hashes.json` maps
  every relative POSIX path to its SHA-256, and `root_hash = sha256(JCS(file_hashes.json))`
  (decision 2). Reproducible with `sha256sum` and any JCS implementation.
- A structured claim statement per gate, each with a falsifier and resolvable referent
  references (decision 3), as `Claim` documents in the object store.
- All five registers, each present, each an explicit assertion (decision 4). Four are empty and
  say why.
- `report/summary.md` generated from the JSON, with the verifier re-rendering it and failing on
  any difference (decision 5).
- Verification on the zero-extras base install, making no network call (decisions 6 and 7).
- Content-addressed objects in the two-key `{object, provenance}` envelope (ADR-001), with the
  address taken over the `object` half only.

## Not implemented, and what that costs

- **`schemas/*.json`**: the package does not ship the JSON Schemas it was written against, so
  the verifier validates against the *installed* FarSight schemas. An auditor with a different
  FarSight version is therefore not validating against the schema this was written to. ADR-007
  decision 7 requires the shipped copies; this is the largest single gap.
- **`runs/`, `campaign.json`, channels, `.npy` recomputation**: there is no run protocol here.
  This experiment is closed-form arithmetic plus one Monte Carlo, executed in-process, so there
  are no per-run channels to recompute a metric from.
- **`metrics/metric_registry.json`**: ADR-009's metric registry is not implemented. The
  acceptance criteria are a plain document with its own address rather than typed metric and
  acceptance-rule records.
- **Tier claims (ADR-006) and `environment/numeric_environment.json`**: the claim tier is
  recorded as `C`. Nothing here runs in the reference container, so no Tier-A or Tier-B claim is
  made.
- **`replay`**: not implemented. The package records the command that re-executes the
  calculation; it does not ship a replayer.
- **`inputs/data/<sha256>` closure**: the sources are publications, not bytes. No `DataArtifact`
  bytes are embedded and `Source.artifact_refs` is empty, which is the weakness ADR-021 names --
  a source with no artifact is an author's word about where a number came from. The papers are
  public and identified here by arXiv id and DOI.
- **Signing (`root_hash.txt.minisig`)**: not implemented. The root hash travels with the package
  rather than being signed, so it attests to internal consistency only. Anyone who can rewrite a
  file can re-seal.
- **`NOTICES.md`, `epoch_labels.json`, `sensitivity.json`, `failure_groups.json`,
  `comparison_results.json`**: absent, with nothing in this experiment to put in them.

## What a verified package means

That the files are the ones that were sealed, that the documents satisfy their schemas, that
every reference resolves, and that recomputing from the packaged inputs reproduces the packaged
results.

**It does not mean the physics is right, that the reproduction succeeded, or that anyone
external has reviewed it.** This reproduction misses two of its pre-registered gates, and its
package verifies cleanly while saying so.
"""


def build(destination: Path, *, counterfactual: str | None, seed: int, iterations: int,
          built_at: dt.datetime) -> dict[str, Any]:
    """Build one package. Returns the manifest that was written."""
    if destination.exists() and any(destination.iterdir()):
        raise BuildError(
            f"{destination} already exists and is not empty. Refusing to write a package over "
            f"another one: the result would be a mixture of two builds with one root hash."
        )
    model = load_model()
    w_rtgb_override = None
    variant = "baseline"
    if counterfactual == "w_rtgb_geometric":
        w_rtgb_override, _ = model.rtgb_from_geometry(model.W_RTG_T26)
        variant = "counterfactual:w_rtgb_geometric"
    elif counterfactual is not None:
        raise BuildError(f"unknown counterfactual {counterfactual!r}")

    destination.mkdir(parents=True, exist_ok=True)
    store = ObjectStore(destination)
    provenance = Provenance(
        created_at=built_at,
        frozen_by="build_evidence_package.py",
        authorization="unattended",
        tool_version=PACKAGE_FORMAT,
    )

    source_refs = {name: store.put(src, provenance) for name, src in sources().items()}
    declared = assumptions(source_refs, counterfactual)
    assumption_refs = [store.put(a, provenance) for a in declared]

    criteria = acceptance_criteria(model)
    criterion_ref = store.put(criteria, provenance)

    # One referent per scenario: the published number this claim is measured against, with its
    # own address, so a claim's referent_refs resolve to documents rather than to prose.
    referent_refs = {}
    for scenario in model.SCENARIOS:
        referent_refs[scenario.number] = store.put(
            {
                "document": "published_scenario_acceleration",
                "source": "arXiv:1103.5222 Table 3",
                "scenario": scenario.number,
                "a_th": Quantity(
                    magnitude=decimal_string(scenario.published_a_th * 1e-10),
                    unit=ACCELERATION_UNIT,
                ).model_dump(mode="json"),
            },
            provenance,
        )

    results = compute(model, w_rtgb_override, seed, iterations)
    results_ref = store.put(results, provenance)

    declared_claims = claims(model, criterion_ref, referent_refs, source_refs)
    claim_refs = [store.put(c, provenance) for c in declared_claims]
    claim_results = [
        ClaimResult(
            claim_ref=claim_refs[0], verdict=results["gate_1"]["verdict"], aggregate_ref=results_ref
        ),
        ClaimResult(
            claim_ref=claim_refs[1], verdict=results["gate_2"]["verdict"], aggregate_ref=results_ref
        ),
    ]
    claim_result_refs = [store.put(r, provenance) for r in claim_results]

    overall = "reproduced" if all(
        r.verdict == "pass" for r in claim_results
    ) else "not_reproduced"

    manifest = {
        "package_format": PACKAGE_FORMAT,
        "partial_format_note": "PARTIAL_FORMAT.md",
        "experiment": "pioneer_thermal",
        "variant": variant,
        "built_at": built_at.isoformat(),
        "code": code_identity(),
        "execution": {
            "seed": seed,
            "iterations": iterations,
            "command": (
                "python experiments/pioneer_thermal/build_evidence_package.py --out <dir>"
                + (f" --counterfactual {counterfactual}" if counterfactual else "")
            ),
            "verify_command": (
                "python experiments/pioneer_thermal/verify_evidence_package.py <dir>"
            ),
            "reproduce_command": (
                "python experiments/pioneer_thermal/reproduce_thermal_acceleration.py "
                "--alternatives"
            ),
        },
        "environment": environment_fingerprint(),
        "refs": {
            "sources": source_refs,
            "assumptions": assumption_refs,
            "criterion": criterion_ref,
            "referents": {str(k): v for k, v in referent_refs.items()},
            "claims": claim_refs,
            "claim_results": claim_result_refs,
            "results": results_ref,
        },
        "claim_statements": [c.model_dump(mode="json") for c in declared_claims],
        "overall_verdict": overall,
        "verdict_meaning": (
            "A scientific verdict about this reproduction, not a statement about the package's "
            "integrity. 'not_reproduced' packages verify normally."
        ),
    }

    _write_json(destination / "manifest.json", manifest)
    _write_json(destination / "experiment" / "scenario_inputs.json",
                {"scenarios": scenario_inputs(model, w_rtgb_override)})
    _write_json(destination / "experiment" / "acceptance_criteria.json", criteria)
    _write_json(destination / "metrics" / "results.json", results)
    for name, content in registers(declared, assumption_refs).items():
        _write_json(destination / "registers" / name, content)

    (destination / "code").mkdir(parents=True, exist_ok=True)
    shutil.copy2(MODEL_PATH, destination / "code" / MODEL_PATH.name)
    (destination / "experiment").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PREREGISTRATION_PATH, destination / "experiment" / "PREREGISTRATION.md")

    write_atomic(destination / "PARTIAL_FORMAT.md", PARTIAL_FORMAT_NOTE.encode("utf-8"))
    write_atomic(
        destination / "report" / "summary.md",
        render_summary(manifest, results, declared).encode("utf-8"),
    )

    root_hash = seal(destination)
    manifest["root_hash"] = root_hash
    return manifest


def _write_json(path: Path, content: Any) -> None:
    """Indented and sorted, so a human can read it and a diff is meaningful."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, (json.dumps(content, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Pioneer evidence package.")
    parser.add_argument("--out", required=True, type=Path, help="package directory to create")
    parser.add_argument(
        "--counterfactual", default=None, choices=["w_rtgb_geometric"],
        help="build the labelled sensitivity variant instead of the baseline",
    )
    parser.add_argument("--seed", type=int, default=20260928)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument(
        "--built-at", default=None,
        help="ISO-8601 build timestamp; pass one to make two builds byte-identical",
    )
    args = parser.parse_args()

    built_at = (
        dt.datetime.fromisoformat(args.built_at)
        if args.built_at
        else dt.datetime.now(dt.UTC)
    )
    if built_at.tzinfo is None:
        built_at = built_at.replace(tzinfo=dt.UTC)

    try:
        manifest = build(
            args.out, counterfactual=args.counterfactual, seed=args.seed,
            iterations=args.iterations, built_at=built_at,
        )
    except BuildError as exc:
        print(f"BUILD FAILED (operational): {exc}", file=sys.stderr)
        return 2

    print(f"package:      {args.out}")
    print(f"variant:      {manifest['variant']}")
    print(f"root hash:    {manifest['root_hash']}")
    print(f"verdict:      {manifest['overall_verdict']}  (a scientific result, not a build error)")
    print(f"verify with:  python experiments/pioneer_thermal/verify_evidence_package.py "
          f"{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
