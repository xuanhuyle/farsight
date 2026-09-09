"""The weeks 1-2 exit gate, on the real Psyche kernels. ADR-018, ADR-024.

`test_geometry_gate.py` runs the same machinery against a FarSight-authored synthetic SPK, so the
gate has a green leg that needs no downloads. This module is the other leg: the same `RunSpec`
path, against the nine publisher-verified kernels pinned in `kernels/pinned_kernels.json`, on the
actual Psyche reconstructed trajectory and the actual DSOC ground stations.

**Skips rather than fails when the kernels are absent**, because they are 46 MiB that CI does not
fetch and the cache is never garbage-collected. A skip here is not a silent pass: the synthetic
gate covers the machinery unconditionally, and what this module adds is that the machinery works
on real data -- which is a claim nobody should be able to make from a green CI run alone.

**What this still does not establish.** The numbers come from JPL's own reconstructed trajectory
and are computed by CSPICE; nothing here compares them to an independent source. ADR-015's
`ci-geometry-crosscheck` against Horizons is a different check and is not implemented. A green run
here means the pipeline computes what these kernels say, not that anyone else agrees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

spiceypy = pytest.importorskip("spiceypy", reason="the `spice` extra is not installed")

from farsight.cli.run_geometry import run_geometry
from farsight.engines.spice.config import SPICE_GEOMETRY_DIALECT, SpiceGeometryConfig
from farsight.hashing.canonical import hash_object
from farsight.registry.channels import read_channel
from farsight.registry.kernel_cache import KernelCache
from farsight.registry.paths import kernel_cache_root
from farsight.schemas.channels import UniformGrid

from ._guards import skip_or_fail_on_missing_kernels

REPO = Path(__file__).resolve().parents[2]

# Furnish order is the decision (ADR-016 decision 2), so this list is the order, not a set.
ORDER = ["naif0012.tls", "pck00010.tpc", "psyche_v01.tpc", "earth_000101_260827_260601.bpc",
         "psyche_fk_v10.tf", "de440s.bsp", "psyche_rec_231207-240304_240321_v1.bsp",
         "psyche_dsoc_palomar_v01.bsp", "psyche_dsoc_octl_v01.bsp"]

OBSERVER = "PSYC_DSOC_PALOMAR"
TOPO_FRAME = "PSYC_DSOC_PALOMAR_TOPO"

# `-255` (PSYC) is the SPACECRAFT. `PSYCHE` resolves to 2000016, the ASTEROID -- see
# docs/measurements/ADR-015-enforcement-4-deltas.md. Using the obvious spelling would compute
# geometry to a different body and pass every check.
SPACECRAFT = "-255"

# 2024-01-15T00:00:00 UTC in TDB seconds past J2000, and a 3-hour step over one day. Inside the
# reconstructed SPK's window and inside the Earth PCK's coverage.
EPOCH0 = "758548869.18431"
STEP = "10800"
N_SAMPLES = 9

TS = "2026-09-07T12:00:00+00:00"


def _pinned() -> dict:
    return {k["logical_name"]: k
            for k in json.loads((REPO / "kernels" / "pinned_kernels.json")
                                .read_text(encoding="utf-8"))["kernels"]}


@pytest.fixture(scope="module")
def kernels() -> dict:
    pinned = _pinned()
    cache = KernelCache(kernel_cache_root())
    missing = [n for n in ORDER if n not in pinned or not cache.has(pinned[n]["sha256"])]
    if missing:
        skip_or_fail_on_missing_kernels(f"real kernels not in the local cache: {missing}")
    return pinned


def _bundle(pinned: dict) -> dict:
    grid = {
        "kind": "uniform",
        "epoch0": {"scale": "TDB", "seconds_past_j2000": {"magnitude": EPOCH0, "unit": "s"}},
        "step": {"magnitude": STEP, "unit": "s"},
        "n_samples": N_SAMPLES,
    }
    grid_digest = hash_object(UniformGrid.model_validate(grid))

    def kernel(name: str) -> dict:
        k = pinned[name]
        return {
            "sha256": k["sha256"], "kernel_type": k["kernel_type"], "logical_name": name,
            "size_bytes": k["size_bytes"],
            # ADR-016 attribution: these are NAIF/PDS products, taken unmodified.
            "attribution": "third_party_unmodified", "modifier": None, "parent_sha256": None,
            "license_note": k["license_note"],
        }

    def request(frame: str, aberration: str, quantity_class: str, rationale=None) -> dict:
        return {"target": SPACECRAFT, "observer": OBSERVER, "frame": frame,
                "aberration": aberration, "quantity_class": quantity_class,
                "epochs": grid_digest, "rationale": rationale}

    config = {
        "schema_version": 1,
        "dialect": SPICE_GEOMETRY_DIALECT,
        "kernel_set": {"schema_version": 1,
                       "kernels": [kernel(n) for n in ORDER],
                       "frame_sources": {}},
        "quantities": [
            # A range uses the converged-Newtonian RECEPTION case and no stellar aberration:
            # ADR-015's flagship convention, and the schema refuses `+S` here.
            {"emit": "range", "unit": "km",
             "request": request(TOPO_FRAME, "CN", "range")},
            {"emit": "light_time", "unit": "s",
             "request": request(TOPO_FRAME, "CN", "light_time")},
            # An apparent DIRECTION carries stellar aberration. Measured at 18.4 arcsec here,
            # which is half AT-11's tolerance -- not negligible.
            {"emit": "apparent_direction", "unit": "1",
             "request": request(TOPO_FRAME, "CN+S", "direction")},
        ],
    }
    config_digest = hash_object(SpiceGeometryConfig.model_validate(config))

    run_spec = {
        "schema_version": 1,
        "experiment_hash": "e" * 64,   # dangling by policy: no ExperimentDesign type exists
        "run_index": 0,
        "stages": [{
            "stage_id": "geometry", "kind": "geometry", "provider_id": "spice",
            "config_dialect": SPICE_GEOMETRY_DIALECT, "config_ref": config_digest,
            "grid": {"grid_hash": grid_digest}, "bindings": {},
            "emits": sorted(q["emit"] for q in config["quantities"]),
            "models": [],
        }],
        "inputs": [],
    }
    return {"run_spec": run_spec, "objects": {grid_digest: grid, config_digest: config}}


@pytest.fixture()
def prepared(kernels, tmp_path):
    path = tmp_path / "psyche_run.json"
    path.write_text(json.dumps(_bundle(kernels), indent=2), encoding="utf-8")
    return path


def test_real_psyche_geometry_is_hash_stable(prepared, tmp_path):
    """The gate's own wording, on the real trajectory: run twice, compare."""
    first = run_geometry(design_path=prepared, out_dir=tmp_path / "a", ts_utc=TS)
    second = run_geometry(design_path=prepared, out_dir=tmp_path / "b", ts_utc=TS)

    assert first["channels"] == second["channels"]
    assert first["spec_hash"] == second["spec_hash"]
    for name in ("geometry.range", "geometry.light_time", "geometry.apparent_direction",
                 "run.t_elapsed"):
        assert (tmp_path / "a" / f"{name}.npy").read_bytes() == \
            (tmp_path / "b" / f"{name}.npy").read_bytes()


def test_the_numbers_are_the_psyche_pass_that_was_measured(prepared, tmp_path):
    """Anchored on the figures in docs/measurements/ADR-015-enforcement-4-deltas.md.

    Loose tolerances on purpose: this asserts the pipeline is pointed at the right bodies in the
    right frame, not that CSPICE is correct. A wrong target (the ASTEROID Psyche rather than the
    spacecraft), a wrong observer, or a wrong frame all move these by far more than the bounds.
    """
    import numpy as np

    run_geometry(design_path=prepared, out_dir=tmp_path / "a", ts_utc=TS)

    ranges = read_channel(tmp_path / "a", "geometry.range")
    light_time = read_channel(tmp_path / "a", "geometry.light_time")
    direction = read_channel(tmp_path / "a", "geometry.apparent_direction")

    assert ranges.shape == (N_SAMPLES,)
    assert direction.shape == (N_SAMPLES, 3)

    # 61.5-62.7 million km over this day, from the measurement run.
    assert 6.10e7 < ranges.min() < 6.30e7, ranges.min()
    assert 6.10e7 < ranges.max() < 6.30e7, ranges.max()
    assert ranges[0] < ranges[-1], "Psyche was receding over this day"

    # Light time is range / c, which ties the two channels together independently of SPICE.
    c_km_s = 299792.458
    np.testing.assert_allclose(light_time, ranges / c_km_s, rtol=1e-6)

    # A direction channel is a unit vector.
    np.testing.assert_allclose(np.linalg.norm(direction, axis=1), 1.0, atol=1e-12)

    # The pass: elevation is the topocentric z-component, and it must both rise and set.
    elevation_deg = np.degrees(np.arcsin(direction[:, 2]))
    assert elevation_deg.max() > 70, elevation_deg
    assert elevation_deg.min() < 0, elevation_deg


def test_the_spacecraft_and_the_asteroid_are_different_bodies(kernels):
    """The naming hazard, asserted so it cannot be forgotten.

    `PSYCHE` resolves to 2000016 -- the ASTEROID (16) Psyche. The spacecraft is -255 / `PSYC`. A
    request written with the obvious spelling computes geometry to a body a long way from the one
    intended, and passes every hash, schema and unit check on the way.
    """
    from farsight.engines.spice.kernels import furnished_pool
    from farsight.schemas.kernels import KernelRef

    pinned = kernels
    cache = KernelCache(kernel_cache_root())
    refs = [KernelRef(sha256=pinned[n]["sha256"], kernel_type=pinned[n]["kernel_type"],
                      logical_name=n, size_bytes=pinned[n]["size_bytes"],
                      attribution="third_party_unmodified", modifier=None, parent_sha256=None,
                      license_note=pinned[n]["license_note"]) for n in ORDER]

    with furnished_pool(refs, cache):
        assert spiceypy.bodn2c("PSYCHE") == 2000016
        assert spiceypy.bodc2n(-255) == "PSYC"
        assert spiceypy.bodn2c("PSYCHE") != -255
