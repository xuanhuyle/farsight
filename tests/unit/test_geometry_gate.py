"""The weeks 1-2 exit gate: `farsight geometry` emits hash-stable geometry.

**What this measures, stated exactly, because the gate's own wording promises more.**

The plan's gate is *"`farsight geometry` emits hash-stable Psyche pass geometry, bitwise-
reproducible in container"*. Three words in that sentence are not met here and saying so is part
of passing honestly:

* **Psyche** -- no Psyche SPK has been downloaded. This runs against a FarSight-authored synthetic
  SPK of two fictional bodies on a straight line. It exercises the machinery end to end with real
  CSPICE arithmetic, including the light-time solver, and it is *not evidence about Psyche* or
  about any real ephemeris.
* **in container** -- ADR-019's reference container image is not built. What is demonstrated is
  bitwise stability within one machine, across two runs and across two processes.
* **pass geometry** -- there is no station, no visibility model and no pass. A range and a light
  time between two bodies is what a two-kernel set can support (ADR-015 needs a PCK and an FK for
  anything body-fixed).

What IS demonstrated: the same frozen design produces byte-identical channels, in a second
process, with the audit chain intact -- and the numbers agree with a closed form that owes nothing
to SPICE.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

spiceypy = pytest.importorskip("spiceypy", reason="the `spice` extra is not installed")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.synthetic_spk import (
    BODY_A,
    BODY_B,
    analytic_range,
    synthetic_spk_bytes,
    synthetic_spk_sha256,
)

from farsight.cli.run_geometry import run_geometry
from farsight.registry.audit import AuditLog
from farsight.registry.channels import grid_hash, read_channel
from farsight.registry.kernel_cache import KernelCache
from farsight.registry.paths import kernel_cache_root

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LSK_FIXTURE = FIXTURES / "farsight_authored.tls"

# Inside the synthetic SPK's window (2017-01 .. 2034-01) and after the fixture LSK's leapsecond
# table begins, so neither coverage check refuses it.
EPOCH0 = "772416000"
STEP = "3600"
N_SAMPLES = 25

TS = "2026-09-07T12:00:00+00:00"


def _populate_cache(home: Path) -> tuple[str, str, int, int]:
    """Insert both kernels through ``KernelCache.put``, which is the cache's one writer.

    A generator writing into the cache root directly would be the second writer ADR-016 decision 5
    forbids; returning bytes and inserting them exactly as a fetched kernel is inserted keeps that
    rule true.
    """
    import hashlib

    cache = KernelCache(kernel_cache_root(home))

    lsk_bytes = LSK_FIXTURE.read_bytes()
    lsk_digest = hashlib.sha256(lsk_bytes).hexdigest()
    cache.put(lsk_bytes, lsk_digest)

    spk_bytes = synthetic_spk_bytes()
    spk_digest = synthetic_spk_sha256()
    cache.put(spk_bytes, spk_digest)

    return lsk_digest, spk_digest, len(lsk_bytes), len(spk_bytes)


def _design_dict(lsk_digest: str, spk_digest: str, lsk_size: int, spk_size: int) -> dict:
    grid = {
        "kind": "uniform",
        "epoch0": {"scale": "TDB", "seconds_past_j2000": {"magnitude": EPOCH0, "unit": "s"}},
        "step": {"magnitude": STEP, "unit": "s"},
        "n_samples": N_SAMPLES,
    }
    from farsight.schemas.channels import UniformGrid

    digest = grid_hash(UniformGrid.model_validate(grid))

    def kernel(sha: str, kind: str, name: str, size: int) -> dict:
        return {
            "sha256": sha,
            "kernel_type": kind,
            "logical_name": name,
            "size_bytes": size,
            "attribution": "farsight_authored",
            "modifier": "FarSight",
            "parent_sha256": None,
            "license_note": "Authored by FarSight for testing. Not a NAIF product.",
        }

    return {
        "schema_version": 1,
        "kernel_set": {
            "schema_version": 1,
            "kernels": [
                kernel(lsk_digest, "lsk", "farsight_authored.tls", lsk_size),
                kernel(spk_digest, "spk", "farsight_synthetic.bsp", spk_size),
            ],
            "frame_sources": {},
        },
        "grid": grid,
        "channels": [
            {
                "channel": "geometry.range",
                "unit": "km",
                "request": {
                    "target": str(BODY_B), "observer": str(BODY_A), "frame": "J2000",
                    "aberration": "CN", "quantity_class": "range",
                    "epochs": digest, "rationale": None,
                },
            },
            {
                "channel": "geometry.light_time",
                "unit": "s",
                "request": {
                    "target": str(BODY_B), "observer": str(BODY_A), "frame": "J2000",
                    "aberration": "CN", "quantity_class": "light_time",
                    "epochs": digest, "rationale": None,
                },
            },
            {
                "channel": "geometry.geometric_range",
                "unit": "km",
                "request": {
                    "target": str(BODY_B), "observer": str(BODY_A), "frame": "J2000",
                    "aberration": "NONE", "quantity_class": "range",
                    "epochs": digest, "rationale": None,
                },
            },
        ],
    }


@pytest.fixture()
def prepared(tmp_path):
    home = tmp_path / "home"
    lsk, spk, lsk_size, spk_size = _populate_cache(home)
    design_path = tmp_path / "design.json"
    design_path.write_text(
        json.dumps(_design_dict(lsk, spk, lsk_size, spk_size), indent=2), encoding="utf-8"
    )
    return home, design_path


def test_two_runs_of_one_design_produce_identical_channel_hashes(prepared, tmp_path):
    """The gate. Bitwise stability across two runs on one machine."""
    home, design_path = prepared

    first = run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)
    second = run_geometry(design_path=design_path, out_dir=tmp_path / "b", home=home, ts_utc=TS)

    assert first["channels"] == second["channels"]
    assert first["design_hash"] == second["design_hash"]
    assert first["grid_hash"] == second["grid_hash"]

    # ... and byte-identical on disk, which is a stronger statement than equal hashes.
    for name in ("geometry.range", "geometry.light_time", "run.t_elapsed"):
        assert (tmp_path / "a" / f"{name}.npy").read_bytes() == \
            (tmp_path / "b" / f"{name}.npy").read_bytes()


def test_hash_stability_survives_a_process_boundary(prepared, tmp_path):
    """One process cannot detect process-local state leaking into a digest.

    Hash randomization, dict iteration order and the SPICE kernel pool are all process-scoped, and
    a same-process comparison would be blind to every one of them.
    """
    home, design_path = prepared
    in_process = run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home,
                              ts_utc=TS)

    script = tmp_path / "child.py"
    script.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[2] / 'src')!r})\n"
        "from pathlib import Path\n"
        "from farsight.cli.run_geometry import run_geometry\n"
        f"r = run_geometry(design_path=Path({str(design_path)!r}), "
        f"out_dir=Path({str(tmp_path / 'c')!r}), home=Path({str(home)!r}), ts_utc={TS!r})\n"
        "print(json.dumps(r['channels']))\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, encoding="utf-8",
        env={"PYTHONHASHSEED": "12345", "PATH": ""},
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == in_process["channels"]


def test_the_numbers_agree_with_a_closed_form_that_owes_nothing_to_spice(prepared, tmp_path):
    """A hash-stability test alone would pass on a stable wrong answer.

    The synthetic bodies move on straight lines, so the geometric range has a closed form. This
    compares CSPICE's answer to that form -- which is the only assertion here that could fail
    because the *physics path* is wrong rather than because the bytes moved.
    """
    from decimal import Decimal

    home, design_path = prepared
    run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)

    geometric = read_channel(tmp_path / "a", "geometry.geometric_range")
    assert geometric.shape == (N_SAMPLES,)

    for i in range(N_SAMPLES):
        et = float(Decimal(EPOCH0) + i * Decimal(STEP))
        assert abs(geometric[i] - analytic_range(et)) < 1e-6, (
            f"sample {i}: CSPICE and the closed form disagree by "
            f"{abs(geometric[i] - analytic_range(et))} km"
        )

    # The light-time correction must actually change the range, or the aberration argument is
    # being ignored and every `CN` channel is silently a `NONE` channel.
    corrected = read_channel(tmp_path / "a", "geometry.range")
    assert not np.array_equal(corrected, geometric), (
        "the CN-corrected range equals the geometric range, so the aberration argument is not "
        "reaching SPICE -- which is exactly the silent-convention failure ADR-015 exists to stop"
    )


def test_t_elapsed_is_written_and_starts_at_zero(prepared, tmp_path):
    home, design_path = prepared
    run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)
    t = read_channel(tmp_path / "a", "run.t_elapsed")
    assert t[0] == 0.0
    assert t[-1] == float(int(STEP) * (N_SAMPLES - 1))


def test_the_manifest_records_every_channel_with_its_grid(prepared, tmp_path):
    home, design_path = prepared
    result = run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)
    manifest = json.loads((tmp_path / "a" / "channels_manifest.json").read_text(encoding="utf-8"))

    assert [r["name"] for r in manifest] == sorted(r["name"] for r in manifest)
    assert {r["name"] for r in manifest} == {
        "geometry.range", "geometry.light_time", "geometry.geometric_range", "run.t_elapsed",
    }
    for row in manifest:
        assert row["grid_hash"] == result["grid_hash"]
        assert row["dtype"] == "<f8"
        assert row["nonfinite_count"] == 0


def test_the_run_writes_one_audit_row_carrying_the_design_path(prepared, tmp_path):
    """ADR-012 requires a row for every mutating CLI action from v0; ADR-024 says geometry writes
    the `run` action and distinguishes itself by the design path in detail_json."""
    home, design_path = prepared
    result = run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)

    log = AuditLog(home / "registry.sqlite")
    rows = log.rows()
    assert len(rows) == 1
    assert rows[0]["action"] == "run"
    assert rows[0]["object_hash"] == result["design_hash"]

    detail = json.loads(rows[0]["detail_json"])
    assert detail["verb"] == "geometry"
    assert detail["design_path"] == design_path.as_posix()
    log.verify_chain()

    run_geometry(design_path=design_path, out_dir=tmp_path / "b", home=home, ts_utc=TS)
    assert len(log.rows()) == 2
    log.verify_chain()


def test_a_request_naming_a_different_grid_is_refused(prepared, tmp_path):
    """ADR-020 decision 6's failure, caught at design time: a request pointing at another grid
    computes correct numbers against the wrong time base."""
    from farsight.registry.channels import ChannelWriteError

    home, design_path = prepared
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design["channels"][0]["request"]["epochs"] = "f" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(design), encoding="utf-8")

    with pytest.raises(ChannelWriteError, match="wrong time base"):
        run_geometry(design_path=bad, out_dir=tmp_path / "x", home=home, ts_utc=TS)


def test_the_kernel_pool_is_empty_after_a_run(prepared, tmp_path):
    """The pool is process-global (ADR-002, ADR-016). A run that left it furnished would make the
    next run's numbers depend on which run preceded it."""
    from farsight.engines.spice.kernels import loaded_count

    home, design_path = prepared
    run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)
    assert loaded_count() == 0


# ------------------------------------------------------------------------------------------
# The CLI layer. ADR-024's surface is shipped contract: command names and exit codes are printed
# into evidence packages, so an untested wiring layer is an untested part of the product.
# ------------------------------------------------------------------------------------------


def _cli(*args):
    from typer.testing import CliRunner

    from farsight.cli.main import app

    return CliRunner().invoke(app, list(args))


def test_geometry_is_a_leaf_command_and_not_a_group():
    """ADR-024 decision 1 spells it `farsight geometry --design PATH --out DIR`. A group would
    make every invocation `farsight geometry <something>`, which is a different published
    surface."""
    result = _cli("geometry", "--help")
    assert result.exit_code == 0
    assert "--design" in result.output and "--out" in result.output
    assert "--shadow-units" in result.output


def test_the_command_runs_and_exits_zero(prepared, tmp_path):
    home, design_path = prepared
    result = _cli("--json", "geometry", "--design", str(design_path),
                  "--out", str(tmp_path / "cli"), "--home", str(home))
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert len(summary["channels"]) == 4
    assert summary["grid_hash"] == grid_hash(
        __import__("farsight.schemas.channels", fromlist=["UniformGrid"]).UniformGrid
        .model_validate(json.loads(design_path.read_text(encoding="utf-8"))["grid"])
    )


def test_a_malformed_design_exits_with_the_schema_failure_code(tmp_path):
    """ADR-024's registry is append-only and its codes are printed into shipped reports, so the
    mapping from failure to code is contract rather than convenience."""
    from farsight.cli import exit_codes

    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": 1}', encoding="utf-8")
    result = _cli("geometry", "--design", str(bad), "--out", str(tmp_path / "o"))
    assert result.exit_code == exit_codes.SCHEMA_FAILURE

    missing = _cli("geometry", "--design", str(tmp_path / "nope.json"), "--out", str(tmp_path))
    assert missing.exit_code == exit_codes.SCHEMA_FAILURE


def test_shadow_units_marks_the_run_as_unpackageable(prepared, tmp_path):
    """ADR-008: `--shadow-units` is a debugging instrument whose limit is absolute -- never in the
    production loop, never in an evidence package. The run has to say so about itself, because the
    week-4 package builder refuses on exactly this flag."""
    home, design_path = prepared
    result = run_geometry(design_path=design_path, out_dir=tmp_path / "s", home=home,
                          shadow_units=True, ts_utc=TS)
    assert "may not be offered to an evidence package" in result["shadow_units"]

    # The epoch cross-check ran and is reported with a verdict, not just a number.
    findings = result["shadow_findings"]
    assert len(findings) == 2
    assert all("SPICE vs astropy differ by" in f for f in findings)
    assert all(f.endswith("ok") for f in findings), findings

    plain = run_geometry(design_path=design_path, out_dir=tmp_path / "p", home=home, ts_utc=TS)
    assert "shadow_units" not in plain
    # The flag must not change a single number: it is a second look, not a second computation.
    assert plain["channels"] == result["channels"]


def test_the_global_home_option_reaches_the_command(prepared, tmp_path):
    """ADR-024 makes `--home` global, accepted on every command.

    `geometry` also declared it locally and read only the local value, so
    `farsight --home X geometry ...` silently used the DEFAULT home -- looking for kernels in one
    place and writing the audit chain to another, with no error and no warning. Every existing
    test called `run_geometry()` directly and so was blind to it; this one goes through the CLI,
    which is the only place the bug could live.
    """
    home, design_path = prepared

    before = _cli("--home", str(home), "--json", "geometry", "--design", str(design_path),
                  "--out", str(tmp_path / "g1"))
    assert before.exit_code == 0, before.output
    assert (home / "registry.sqlite").exists(), (
        "the global --home was ignored: the audit chain was written somewhere else"
    )

    # Both spellings must mean the same thing.
    after = _cli("geometry", "--design", str(design_path), "--out", str(tmp_path / "g2"),
                 "--home", str(home))
    assert after.exit_code == 0, after.output
    assert len(AuditLog(home / "registry.sqlite").rows()) == 2


def test_the_declared_unit_is_a_hashed_design_input(prepared, tmp_path):
    """A unit that lives only in the adapter enters every channel hash and no design hash.

    Editing it would then move every channel hash while the design hash stood still -- "the
    number changes, the hash changes, and nothing in the package says why", which is exactly the
    shape ADR-015 Option 7 was rejected for, one layer up.
    """
    home, design_path = prepared
    design = json.loads(design_path.read_text(encoding="utf-8"))
    baseline = run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)

    # Changing a declared unit must move the DESIGN hash, not only the channel hashes.
    design["channels"][0]["unit"] = "m"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(design), encoding="utf-8")

    from farsight.cli.run_geometry import GeometryDesignError
    from farsight.hashing.canonical import hash_object
    from farsight.schemas.probe import GeometryDesign

    assert hash_object(GeometryDesign.model_validate(design)) != baseline["design_hash"]

    # ... and it is refused rather than converted, because a conversion here would be a second
    # numeric path that no hash covers.
    with pytest.raises(GeometryDesignError, match="Refused rather than converted"):
        run_geometry(design_path=changed, out_dir=tmp_path / "b", home=home, ts_utc=TS)


def test_the_manifest_records_samples_written(prepared, tmp_path):
    """ADR-020 decision 8. Equal to shape[0] here because a short channel is refused outright,
    but present so a reader never infers it and the manifest model is not closed at eight keys."""
    home, design_path = prepared
    run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)
    manifest = json.loads((tmp_path / "a" / "channels_manifest.json").read_text(encoding="utf-8"))
    for row in manifest:
        assert row["samples_written"] == N_SAMPLES == row["shape"][0]


def test_t_elapsed_is_derived_from_the_descriptor_and_not_from_the_epoch_array(prepared, tmp_path):
    """The invariant two honest implementations would otherwise disagree about.

    ``run.t_elapsed[i]`` is ``float(i * step)``; the epoch handed to SPICE is
    ``float(epoch0 + i * step)``. Both honour ADR-020's "never accumulate" and they are **not**
    related by float64 subtraction -- reconstructing an absolute epoch as
    ``epochs[0] + t_elapsed[i]`` gives different last bits than the stage actually used.

    ADR-020 decision 5 settles which is authoritative: ``t_elapsed`` is derived from the
    descriptor, and `farsight evidence verify` re-expands the descriptor rather than the array.
    Stated as a test so the two paths cannot quietly swap.
    """
    from decimal import Decimal

    home, design_path = prepared
    run_geometry(design_path=design_path, out_dir=tmp_path / "a", home=home, ts_utc=TS)
    t = read_channel(tmp_path / "a", "run.t_elapsed")

    epoch0 = Decimal(EPOCH0)
    step = Decimal(STEP)
    for i in range(N_SAMPLES):
        assert t[i] == float(Decimal(i) * step), f"t_elapsed[{i}] is not float(i * step)"

    # The subtraction route is a different computation, and this says so rather than assuming it
    # happens to agree at this step size.
    reconstructed = [float(epoch0 + Decimal(i) * step) - float(epoch0) for i in range(N_SAMPLES)]
    assert reconstructed[0] == t[0] == 0.0
    assert all(isinstance(v, float) for v in reconstructed)
