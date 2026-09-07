"""The work behind ``farsight geometry``. ADR-018, ADR-024, ADR-016, ADR-020, ADR-012.

**The document is a ``RunSpec``.** ADR-018 decision 1 is explicit that "a run with no engine stage
is a **geometry-only run**: the week-1 exit gate (`farsight geometry`, verb owned by ADR-024) ...
[is] this shape". An earlier version of this module read a parallel ``GeometryDesign``; that was a
second document type for a job an Accepted record already described, and it was retired here while
``spec_hash`` still had no archived instances. See DEV-21.

**Input is a bundle, not a bare spec.** A ``RunSpec`` is mostly references, and a week-1 probe has
no pre-populated object store to resolve them against, so the file carries the spec plus the
objects its digests name. Every one is re-hashed against the address that names it before anything
is computed (``registry/bundle.py``), which is the same check ``evidence verify`` performs over a
package.

Separated from ``cli/geometry.py`` so the Typer surface stays a thin argument parser and this half
is callable from a test without a CLI runner. The split also keeps every SPICE-touching import
inside a function, which is what lets ``farsight --help`` work on the auditor's zero-extras
install.

**Order of operations is the design, not an implementation detail.** Kernels are furnished in the
declared order (ADR-016 decision 2), the grid is expanded in exact arithmetic (ADR-020 decision
4), and the pool is cleared afterwards whatever happens -- the pool is process-global, so an
exception that skipped the clear would leave the next caller's numbers depending on which run
failed before it.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from farsight.schemas.errors import FarSightError

__all__ = ["GeometryDesignError", "run_geometry"]


class GeometryDesignError(FarSightError, ValueError):
    """The run spec cannot be read, does not validate, or is not one this verb can execute."""


def _load_bundle(path: Path):
    """Read the file, verify every object against its address, and validate the spec."""
    from farsight.registry.bundle import BundleError, RefBundle, object_half
    from farsight.schemas.execution import RunSpec

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GeometryDesignError(f"no run spec at {path}") from exc
    except json.JSONDecodeError as exc:
        raise GeometryDesignError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or "run_spec" not in raw:
        raise GeometryDesignError(
            f"{path} is not a run bundle. Expected an object with `run_spec` and `objects`, where "
            f"`objects` maps each content address the spec references to the document at that "
            f"address"
        )

    try:
        bundle = RefBundle(raw.get("objects") or {})
    except BundleError as exc:
        raise GeometryDesignError(str(exc)) from exc

    try:
        spec = RunSpec.model_validate(object_half(raw["run_spec"]))
    except Exception as exc:
        raise GeometryDesignError(f"{path} does not carry a valid RunSpec: {exc}") from exc

    return spec, bundle


def _geometry_stages(spec) -> list:
    """The stages this verb can execute, or a refusal naming why it cannot.

    ``farsight geometry`` is the geometry-only verb (ADR-018 decision 1). An engine stage is not a
    defect in the spec -- it is a perfectly legal ``RunSpec`` -- it is a spec for a different
    command, and saying so is more useful than reporting a validation failure.
    """
    engine = [s for s in spec.stages if s.kind == "engine"]
    if engine:
        raise GeometryDesignError(
            f"stage {engine[0].stage_id!r} has kind 'engine'. `farsight geometry` executes a "
            f"geometry-only run (ADR-018 decision 1); a run carrying an engine stage is `farsight "
            f"run`, which does not exist yet. The spec itself is valid"
        )
    for stage in spec.stages:
        if stage.provider_id != "spice":
            raise GeometryDesignError(
                f"stage {stage.stage_id!r} names provider {stage.provider_id!r}. The only "
                f"geometry provider that exists is 'spice' (ADR-003 keeps the provider set "
                f"explicit rather than discovered)"
            )
    return list(spec.stages)


def _resolve_stage(stage, bundle):
    """Resolve a geometry stage's grid and provider config, and check they agree with the stage.

    Two agreements are checked here and nowhere else, because this is the only place that sees
    both halves: the core's opaque ``config_dialect`` against the document it names, and the
    core's ``emits`` list against what the provider will actually produce. ADR-003 keeps config
    opaque to the core, which means the core alone cannot notice a stage promising channels its
    config does not compute.
    """
    from farsight.engines.spice.config import SPICE_GEOMETRY_DIALECT, SpiceGeometryConfig
    from farsight.registry.bundle import BundleError
    from farsight.schemas.channels import UniformGrid

    try:
        grid = bundle.resolve_as(stage.grid.grid_hash, UniformGrid,
                                 what=f"grid for stage {stage.stage_id!r}")
        config = bundle.resolve_as(stage.config_ref, SpiceGeometryConfig,
                                   what=f"config for stage {stage.stage_id!r}")
    except BundleError as exc:
        raise GeometryDesignError(str(exc)) from exc

    if stage.config_dialect != SPICE_GEOMETRY_DIALECT:
        raise GeometryDesignError(
            f"stage {stage.stage_id!r} declares config_dialect {stage.config_dialect!r}; this "
            f"provider speaks {SPICE_GEOMETRY_DIALECT!r}. ADR-003 makes the dialect the "
            f"provider's own schema name, so a mismatch means the core and the provider disagree "
            f"about what config_ref points at"
        )

    # ADR-020 decision 4: `GeometryRequest.epochs` references the sample grid by digest. A
    # request naming a different grid computes correct numbers against the WRONG TIME BASE, and
    # every channel it produced would then hash-verify clean against a header stating a grid the
    # numbers were not computed on. Caught here, where it is still a typo.
    for quantity in config.quantities:
        if quantity.request.epochs != stage.grid.grid_hash:
            raise GeometryDesignError(
                f"{stage.stage_id}.{quantity.emit} declares epochs="
                f"{quantity.request.epochs[:12]}... but this stage's grid hashes to "
                f"{stage.grid.grid_hash[:12]}.... A request naming a different grid computes "
                f"correct numbers against the wrong time base"
            )

    declared = sorted(stage.emits)
    produced = sorted(q.emit for q in config.quantities)
    if declared != produced:
        raise GeometryDesignError(
            f"stage {stage.stage_id!r} declares emits={declared} but its config computes "
            f"{produced}. ADR-020 decision 3 refuses a run whose collect() returns a channel not "
            f"on the declared list, or omits one that is; caught here instead, where it is still "
            f"a typo rather than a missing file in a package"
        )
    return grid, config


def run_geometry(
    *,
    design_path: Path,
    out_dir: Path,
    home: Path | None = None,
    shadow_units: bool = False,
    ts_utc: str,
    actor: str | None = None,
) -> dict[str, Any]:
    """Execute every geometry stage of a run bundle and write its channels under ``out_dir``.

    Returns a summary carrying the spec digest, the grid digest and every channel hash -- which is
    what a caller compares between two runs to test the gate.
    """
    from farsight.engines.spice.geometry import QUANTITY_UNITS, compute
    from farsight.engines.spice.kernels import furnished_pool
    from farsight.hashing.canonical import hash_object
    from farsight.registry.audit import AuditLog
    from farsight.registry.channels import write_channel, write_channels_manifest
    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import farsight_home, kernel_cache_root
    from farsight.schemas.channels import RUN_T_ELAPSED, elapsed_seconds, epoch_seconds

    spec, bundle = _load_bundle(design_path)
    stages = _geometry_stages(spec)

    # ADR-020 decision 4: ONE sample grid per run, shared by every channel, and never
    # interpolated. Strictly stronger than ADR-018 rule 4, which requires equal grids only along
    # binding edges -- and it subsumes it, because ADR-009's metrics consume channels from
    # different stages in one elementwise expression.
    #
    # Checked BEFORE anything is resolved, because it is a property of the spec alone. Resolving
    # first meant a second grid that happened to be absent from the bundle was reported as an
    # unresolvable reference, which sends the reader looking for a missing object instead of at
    # the second grid they declared.
    grid_refs = {stage.grid.grid_hash for stage in stages}
    if len(grid_refs) != 1:
        raise GeometryDesignError(
            f"this run declares {len(grid_refs)} different sample grids "
            f"{sorted(r[:12] + '...' for r in grid_refs)}. ADR-020 decision 4 gives a run exactly "
            f"one grid, shared by every channel, so that runs can be indexed against each other "
            f"elementwise without anyone interpolating"
        )
    grid_digest = next(iter(grid_refs))

    resolved = [(stage, *_resolve_stage(stage, bundle)) for stage in stages]
    grid = resolved[0][1]

    cache = KernelCache(kernel_cache_root(home))
    out_dir = Path(out_dir)

    # The single conversion point from the hashed epoch representation to the float64 the engine
    # boundary takes (ADR-008, ADR-015 decision 8). Exact in Decimal all the way to here.
    epochs_exact: list[Decimal] = [epoch_seconds(grid, i) for i in range(grid.n_samples)]
    epochs = [float(e) for e in epochs_exact]

    rows: list[dict] = []
    shadow: list[str] = []

    for stage, _grid, config in resolved:
        with furnished_pool(list(config.kernel_set.kernels), cache):
            for quantity in config.quantities:
                values = compute(quantity.request, epochs)
                produced = QUANTITY_UNITS[quantity.request.quantity_class]
                if quantity.unit != produced:
                    raise GeometryDesignError(
                        f"{stage.stage_id}.{quantity.emit} declares unit {quantity.unit!r} but a "
                        f"{quantity.request.quantity_class} through this provider is in "
                        f"{produced!r}. Refused rather than converted: a conversion here would be "
                        f"a second numeric path that no hash covers (ADR-008 puts conversion at "
                        f"the boundary)"
                    )
                rows.append(
                    write_channel(out_dir, f"{stage.stage_id}.{quantity.emit}", quantity.unit,
                                  values, grid_digest, expect_samples=grid.n_samples)
                )
            if shadow_units:
                shadow.extend(_shadow_checks(config, epochs_exact))

    # ADR-020 decision 5: mandatory, derived, exactly 0.0 at index 0, and written by the runner
    # rather than by any stage -- which is why `run` is a reserved namespace resolved against no
    # topology node.
    t_elapsed = np.array([elapsed_seconds(grid, i) for i in range(grid.n_samples)], dtype="<f8")
    rows.append(write_channel(out_dir, RUN_T_ELAPSED, "s", t_elapsed, grid_digest,
                              expect_samples=grid.n_samples))

    write_channels_manifest(out_dir, rows)
    spec_hash = hash_object(spec)

    # ADR-012: an append-only row for every mutating CLI action, from v0. The action is `run`
    # because ADR-012's enumeration is closed; the design path is what distinguishes this from a
    # campaign when an auditor reads the chain (ADR-024).
    #
    # ADR-011 decision 1: "One file per workspace, `registry.sqlite`".
    log = AuditLog(Path(farsight_home(home)) / "registry.sqlite")
    log.append(
        "run",
        {
            "design_path": design_path.as_posix(),
            "out_dir": out_dir.as_posix(),
            "verb": "geometry",
            "shadow_units": shadow_units,
        },
        object_hash=spec_hash,
        ts_utc=ts_utc,
        actor=actor,
    )

    summary = {
        "spec_hash": spec_hash,
        "grid_hash": grid_digest,
        "n_samples": grid.n_samples,
        "stages": [s.stage_id for s in stages],
        "kernels": [k.logical_name for _s, _g, c in resolved for k in c.kernel_set.kernels],
        "channels": [f"{r['name']}  {r['channel_hash']}"
                     for r in sorted(rows, key=lambda r: r["name"])],
        "out_dir": out_dir.as_posix(),
    }
    if shadow_units:
        # Labelled rather than tucked into a hashed-looking field, because ADR-008 forbids a
        # shadow-units run from reaching an evidence package at all.
        summary["shadow_units"] = "TRUE -- this run may not be offered to an evidence package"
        summary["shadow_findings"] = shadow or ["no dimensional inconsistency found"]
    return summary


def _shadow_checks(config, epochs_exact: list[Decimal]) -> list[str]:
    """ADR-008's debug shadow: a second, independent look at what the first path asserted.

    Two checks, and neither enters a hash:

    1. **Dimensional.** Each channel's declared unit is put through the units boundary against the
       one its ``quantity_class`` implies, so a range labelled in seconds is caught.
    2. **Epoch.** The grid's first and last epochs are round-tripped through SPICE to UTC and back
       through astropy, which is plan §14 item 3's independence executed rather than asserted. A
       leap-second or time-scale error shows here as a whole second or as 32.184; the two
       implementations otherwise differ only by their truncation of the TDB-TT periodic term,
       whose amplitude is about 1.7 ms.
    """
    from farsight.engines.spice.geometry import QUANTITY_UNITS
    from farsight.engines.spice.time import et_to_utc
    from farsight.units import same_dimension
    from farsight.units.time import utc_to_tdb_seconds

    findings: list[str] = []

    for quantity in config.quantities:
        expected = QUANTITY_UNITS[quantity.request.quantity_class]
        if not same_dimension(expected, quantity.unit):
            findings.append(
                f"{quantity.emit}: declared unit {quantity.unit!r} is not dimensionally a "
                f"{quantity.request.quantity_class} ({expected!r})"
            )

    for label, index in (("first", 0), ("last", len(epochs_exact) - 1)):
        et = float(epochs_exact[index])
        try:
            utc = et_to_utc(et, precision=6)
            back = utc_to_tdb_seconds(utc.replace("Z", ""))
        except Exception as exc:
            findings.append(f"{label} epoch: cross-check could not run: {exc}")
            continue
        delta = abs(Decimal(repr(et)) - back)
        # A time-SYSTEM error is a whole second or 32.184; anything under a millisecond is the two
        # implementations' different truncation of the same periodic term.
        verdict = "ok" if delta < Decimal("0.001") else "DISAGREEMENT"
        findings.append(f"{label} epoch et={et}: SPICE vs astropy differ by {delta} s -- {verdict}")

    return findings
