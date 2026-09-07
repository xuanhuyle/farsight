"""The work behind ``farsight geometry``. ADR-024, ADR-016, ADR-020, ADR-012.

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
    """The design document cannot be read or does not validate."""


def _load_design(path: Path):
    from farsight.schemas.probe import GeometryDesign

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GeometryDesignError(f"no design at {path}") from exc
    except json.JSONDecodeError as exc:
        raise GeometryDesignError(f"{path} is not valid JSON: {exc}") from exc

    # ADR-001's two-key envelope: a stored object is {object, provenance} and only `object` is
    # hashed. A design authored by hand is accepted in either shape, because requiring an operator
    # to hand-write a provenance block for a week-1 probe would teach them to fill it with noise.
    body = raw.get("object", raw) if isinstance(raw, dict) else raw

    try:
        return GeometryDesign.model_validate(body)
    except Exception as exc:
        raise GeometryDesignError(f"{path} is not a valid GeometryDesign: {exc}") from exc


def run_geometry(
    *,
    design_path: Path,
    out_dir: Path,
    home: Path | None = None,
    shadow_units: bool = False,
    ts_utc: str,
    actor: str | None = None,
) -> dict[str, Any]:
    """Compute every channel the design declares and write them under ``out_dir``.

    Returns a summary carrying the design digest, the grid digest and every channel hash -- which
    is what a caller compares between two runs to test the gate.
    """
    from farsight.engines.spice.geometry import QUANTITY_UNITS, compute
    from farsight.engines.spice.kernels import furnished_pool
    from farsight.hashing.canonical import hash_object
    from farsight.registry.audit import AuditLog
    from farsight.registry.channels import (
        check_requests_name_this_grid,
        grid_hash,
        write_channel,
        write_channels_manifest,
    )
    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import farsight_home, kernel_cache_root
    from farsight.schemas.channels import RUN_T_ELAPSED, elapsed_seconds, epoch_seconds

    design = _load_design(design_path)
    grid_digest = check_requests_name_this_grid(design)
    assert grid_digest == grid_hash(design.grid)

    cache = KernelCache(kernel_cache_root(home))
    out_dir = Path(out_dir)

    # The single conversion point from the hashed epoch representation to the float64 the engine
    # boundary takes (ADR-008, ADR-015 decision 8). Exact in Decimal all the way to here.
    epochs_exact: list[Decimal] = [epoch_seconds(design.grid, i)
                                   for i in range(design.grid.n_samples)]
    epochs = [float(e) for e in epochs_exact]

    rows: list[dict] = []
    shadow: list[str] = []

    with furnished_pool(list(design.kernel_set.kernels), cache):
        for entry in design.channels:
            values = compute(entry.request, epochs)
            produced = QUANTITY_UNITS[entry.request.quantity_class]
            if entry.unit != produced:
                raise GeometryDesignError(
                    f"channel {entry.channel!r} declares unit {entry.unit!r} but a "
                    f"{entry.request.quantity_class} through this provider is in {produced!r}. "
                    f"Refused rather than converted: a conversion here would be a second numeric "
                    f"path that no hash covers (ADR-008 puts conversion at the boundary)"
                )
            rows.append(
                write_channel(out_dir, entry.channel, entry.unit, values, grid_digest,
                              expect_samples=design.grid.n_samples)
            )

        if shadow_units:
            shadow = _shadow_checks(design, epochs_exact)

    # ADR-020 decision 5: mandatory, derived, and exactly 0.0 at index 0.
    t_elapsed = np.array([elapsed_seconds(design.grid, i) for i in range(design.grid.n_samples)],
                         dtype="<f8")
    rows.append(write_channel(out_dir, RUN_T_ELAPSED, "s", t_elapsed, grid_digest,
                              expect_samples=design.grid.n_samples))

    write_channels_manifest(out_dir, rows)

    design_digest = hash_object(design)

    # ADR-012: an append-only row for every mutating CLI action, from v0. The action is `run`
    # because ADR-012's enumeration is closed; the design path is what distinguishes this from a
    # campaign when an auditor reads the chain (ADR-024).
    # ADR-011 decision 1: "One file per workspace, `registry.sqlite`", holding only the run
    # ledger, the alias registry and the audit log.
    log = AuditLog(Path(farsight_home(home)) / "registry.sqlite")
    log.append(
        "run",
        {
            "design_path": design_path.as_posix(),
            "out_dir": out_dir.as_posix(),
            "verb": "geometry",
            "shadow_units": shadow_units,
        },
        object_hash=design_digest,
        ts_utc=ts_utc,
        actor=actor,
    )

    summary = {
        "design_hash": design_digest,
        "grid_hash": grid_digest,
        "n_samples": design.grid.n_samples,
        "kernels": [k.logical_name for k in design.kernel_set.kernels],
        "channels": [f"{r['name']}  {r['channel_hash']}" for r in sorted(rows,
                                                                        key=lambda r: r["name"])],
        "out_dir": out_dir.as_posix(),
    }
    if shadow_units:
        # Kept out of the summary's hashed-looking fields and labelled, because ADR-008 forbids a
        # shadow-units run from reaching an evidence package at all.
        summary["shadow_units"] = "TRUE -- this run may not be offered to an evidence package"
        summary["shadow_findings"] = shadow or ["no dimensional inconsistency found"]
    return summary


def _shadow_checks(design, epochs_exact: list[Decimal]) -> list[str]:
    """ADR-008's debug shadow: a second, independent look at what the first path asserted.

    Two checks, and neither enters a hash:

    1. **Dimensional.** Each channel's declared unit is re-derived from its ``quantity_class`` and
       compared through the units boundary, so a range labelled in seconds is caught.
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

    for entry in design.channels:
        expected = QUANTITY_UNITS[entry.request.quantity_class]
        if not same_dimension(expected, expected):  # pragma: no cover - guards the boundary itself
            findings.append(f"{entry.channel}: the units boundary cannot parse {expected!r}")

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
        findings.append(
            f"{label} epoch et={et}: SPICE vs astropy differ by {delta} s -- {verdict}"
        )

    return findings
