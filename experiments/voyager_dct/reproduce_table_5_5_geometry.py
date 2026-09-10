"""Stage 1, part B: reproduce Voyager 2's 1996 DSS-43 pass geometry through the FarSight pipeline.

Source: R. Ludwig and J. Taylor, DESCANSO Design and Performance Summary Series, Article 4, JPL,
March 2002.

  * Table 5-5, "Voyager 2 telecom predictions, 1996 DOY 030": DSS-43 elevation every 15 minutes
    from day 029 17:45 to day 030 08:00, 58 rows.
  * Tables 5-2 and 5-3, at 1996-01-01 00:00: "Elev Angle = 58.01 deg", "Range = 7.273+09 km".

Unlike part A, this runs THROUGH the system under test: a RunSpec bundle, `run_geometry`, channels
read back from disk. Part A was arithmetic on printed numbers and deliberately avoided FarSight;
this part points FarSight at a published answer.

PRE-REGISTERED CRITERIA, fixed in this docstring before the script was first run.

  Time convention. Table 5-5's times are taken as UTC at DSS-43, and geometry is computed at that
  observer epoch with converged light time (CN) -- the Earth-received-time reading. The article
  does not state its convention. If the residuals are small, that reading is identified by
  agreement: an inference, reported as one.

  Refraction. SPICE computes geometric elevation and models no atmosphere. The article does not
  say whether its elevations include refraction, which is about 0.08 degrees at 11 degrees.

  GATE 1  Every Table 5-5 row printed at 45 degrees or higher matches within 0.02 degrees.
          Refraction is under 0.017 degrees there and the table prints to 0.01 degrees, so this
          tolerance holds whichever way JPL treated refraction.
  GATE 2  At 1996-01-01 00:00 UTC, elevation matches 58.01 within 0.02 degrees, and range matches
          7.273e9 km within its printed precision, +/-0.0005e9 km.

  Reported, not gating: residuals below 45 degrees beside a standard refraction estimate, which
  indicates whether the table is geometric or apparent; and space loss recomputed from the SPICE
  range, against part A's printed -296.18 and -308.19 dB.

TRANSCRIPTION. The 58 elevations were extracted from JPL's PDF. 37 of them -- day 029 17:45 to day
030 00:30, and day 030 06:00 to 08:00 -- also agree digit for digit with the Internet Archive's OCR.
The OCR omits the continuation block, day 030 00:45 to 05:45, so those 21 rows have a single source
and are marked `*` in the output.

Kernels: the pinned Voyager 1996 set, all trust-on-first-use (DEV-16), with the pinned LSK, text PCK
and DE440s. Needs the `spice` extra. Writes one audit-log row per run to the default FarSight home,
because that is where the kernel cache lives and every CLI mutation is audited (ADR-012).

Exit status: 0 if both gates pass, 1 otherwise.
Status: internally cross-checked; not externally expert-reviewed (ADR-030).
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Furnish order is a decision (ADR-016 decision 2): later kernels take precedence.
ORDER = ["naif0012.tls", "pck00010.tpc", "earth_620120_260806.bpc", "earth_topo_260814.tf",
         "de440s.bsp", "earthstns_itrf93_260814.bsp", "Voyager_2.m05016u.merged.bsp"]
TARGET = "-32"               # Voyager 2
OBSERVER = "DSS-43"          # NAIF body 399043, named in earth_topo_260814.tf
TOPO_FRAME = "DSS-43_TOPO"   # +Z at zenith, so elevation = asin(z)

C_KM_S = 299_792.458
GATE_ELEVATION_FLOOR_DEG = 45.0
GATE_ELEVATION_TOL_DEG = 0.02
DCT_ELEVATION_DEG = 58.01
DCT_RANGE_KM = 7.273e9
DCT_RANGE_TOL_KM = 0.0005e9
TS_UTC = "2026-09-10T00:00:00+00:00"

# (day of year, hour, minute, printed elevation, single_source) -- Table 5-5.
TABLE_5_5 = [
    (29, 17, 45, 11.66, False), (29, 18, 0, 13.96, False), (29, 18, 15, 16.31, False),
    (29, 18, 30, 18.72, False), (29, 18, 45, 21.18, False), (29, 19, 0, 23.69, False),
    (29, 19, 15, 26.24, False), (29, 19, 30, 28.83, False), (29, 19, 45, 31.45, False),
    (29, 20, 0, 34.11, False), (29, 20, 15, 36.80, False), (29, 20, 30, 39.52, False),
    (29, 20, 45, 42.26, False), (29, 21, 0, 45.02, False), (29, 21, 15, 47.81, False),
    (29, 21, 30, 50.61, False), (29, 21, 45, 53.42, False), (29, 22, 0, 56.25, False),
    (29, 22, 15, 59.09, False), (29, 22, 30, 61.93, False), (29, 22, 45, 64.77, False),
    (29, 23, 0, 67.61, False), (29, 23, 15, 70.43, False), (29, 23, 30, 73.22, False),
    (29, 23, 45, 75.97, False), (30, 0, 0, 78.62, False), (30, 0, 15, 81.09, False),
    (30, 0, 30, 83.17, False),
    (30, 0, 45, 84.40, True), (30, 1, 0, 84.21, True), (30, 1, 15, 82.71, True),
    (30, 1, 30, 80.51, True), (30, 1, 45, 77.98, True), (30, 2, 0, 75.30, True),
    (30, 2, 15, 72.54, True), (30, 2, 30, 69.74, True), (30, 2, 45, 66.91, True),
    (30, 3, 0, 64.08, True), (30, 3, 15, 61.23, True), (30, 3, 30, 58.39, True),
    (30, 3, 45, 55.56, True), (30, 4, 0, 52.73, True), (30, 4, 15, 49.92, True),
    (30, 4, 30, 47.12, True), (30, 4, 45, 44.35, True), (30, 5, 0, 41.59, True),
    (30, 5, 15, 38.85, True), (30, 5, 30, 36.14, True), (30, 5, 45, 33.46, True),
    (30, 6, 0, 30.81, False), (30, 6, 15, 28.19, False), (30, 6, 30, 25.61, False),
    (30, 6, 45, 23.07, False), (30, 7, 0, 20.58, False), (30, 7, 15, 18.13, False),
    (30, 7, 30, 15.73, False), (30, 7, 45, 13.39, False), (30, 8, 0, 11.11, False),
]


def _pinned() -> dict[str, dict]:
    rows = json.loads((REPO / "kernels" / "pinned_kernels.json").read_text(encoding="utf-8"))
    return {k["logical_name"]: k for k in rows["kernels"]}


def _utc_to_tdb_seconds(pinned: dict[str, dict], utc_iso: str) -> str:
    """UTC -> TDB seconds past J2000 through the same pinned LSK the run furnishes."""
    import spiceypy

    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import kernel_cache_root

    lsk = KernelCache(kernel_cache_root()).get_path(pinned["naif0012.tls"]["sha256"])
    spiceypy.kclear()
    try:
        spiceypy.furnsh(str(lsk))
        return f"{spiceypy.str2et(utc_iso):.6f}"
    finally:
        spiceypy.kclear()


def _bundle(pinned: dict[str, dict], epoch0: str, step: str, n_samples: int) -> dict:
    from farsight.engines.spice.config import SPICE_GEOMETRY_DIALECT, SpiceGeometryConfig
    from farsight.hashing.canonical import hash_object
    from farsight.schemas.channels import UniformGrid

    grid = {
        "kind": "uniform",
        "epoch0": {"scale": "TDB", "seconds_past_j2000": {"magnitude": epoch0, "unit": "s"}},
        "step": {"magnitude": step, "unit": "s"},
        "n_samples": n_samples,
    }
    grid_digest = hash_object(UniformGrid.model_validate(grid))

    def kernel(name: str) -> dict:
        k = pinned[name]
        return {"sha256": k["sha256"], "kernel_type": k["kernel_type"], "logical_name": name,
                "size_bytes": k["size_bytes"], "attribution": "third_party_unmodified",
                "modifier": None, "parent_sha256": None, "license_note": k["license_note"]}

    def request(aberration: str, quantity_class: str) -> dict:
        return {"target": TARGET, "observer": OBSERVER, "frame": TOPO_FRAME,
                "aberration": aberration, "quantity_class": quantity_class,
                "epochs": grid_digest, "rationale": None}

    config = {
        "schema_version": 1,
        "dialect": SPICE_GEOMETRY_DIALECT,
        "kernel_set": {"schema_version": 1, "kernels": [kernel(n) for n in ORDER],
                       "frame_sources": {}},
        "quantities": [
            {"emit": "range", "unit": "km", "request": request("CN", "range")},
            {"emit": "apparent_direction", "unit": "1", "request": request("CN+S", "direction")},
        ],
    }
    config_digest = hash_object(SpiceGeometryConfig.model_validate(config))
    run_spec = {
        "schema_version": 1, "experiment_hash": "e" * 64, "run_index": 0,
        "stages": [{
            "stage_id": "geometry", "kind": "geometry", "provider_id": "spice",
            "config_dialect": SPICE_GEOMETRY_DIALECT, "config_ref": config_digest,
            "grid": {"grid_hash": grid_digest}, "bindings": {},
            "emits": sorted(q["emit"] for q in config["quantities"]), "models": [],
        }],
        "inputs": [],
    }
    return {"run_spec": run_spec, "objects": {grid_digest: grid, config_digest: config}}


def _run(pinned: dict[str, dict], epoch0: str, step: str, n: int, work: Path, tag: str):
    import numpy as np

    from farsight.cli.run_geometry import run_geometry
    from farsight.registry.channels import read_channel

    design = work / f"{tag}.json"
    design.write_text(json.dumps(_bundle(pinned, epoch0, step, n), indent=2), encoding="utf-8")
    out = work / tag
    summary = run_geometry(design_path=design, out_dir=out, ts_utc=TS_UTC)
    ranges = np.asarray(read_channel(out, "geometry.range"))
    direction = np.asarray(read_channel(out, "geometry.apparent_direction"))
    elevation = np.degrees(np.arcsin(direction[:, 2] / np.linalg.norm(direction, axis=1)))
    return summary, ranges, elevation


def _refraction_deg(true_elevation_deg: float) -> float:
    """Standard-atmosphere estimate (Saemundsson's formula). Reported only; never used in a gate."""
    h = true_elevation_deg
    return 1.02 / math.tan(math.radians(h + 10.3 / (h + 5.11))) / 60.0


def _post_hoc_time_shift(
    computed: list[float], deltas: list[float]
) -> tuple[float, float, float, float, float]:
    """POST-HOC: the single time shift that best removes the residuals. Reported, never gated.

    Elevation rate comes from the computed 15-minute profile by central differences. The shift is
    fitted to the same residuals it removes, so it can suggest a cause and can never pass a gate.
    """
    rate = []
    for i in range(len(computed)):
        lo, hi = max(0, i - 1), min(len(computed) - 1, i + 1)
        rate.append((computed[hi] - computed[lo]) / ((hi - lo) * 900.0))
    shift = sum(d * r for d, r in zip(deltas, rate, strict=True)) / sum(r * r for r in rate)
    after = [d - r * shift for d, r in zip(deltas, rate, strict=True)]

    def rms(values: list[float]) -> float:
        return math.sqrt(sum(v * v for v in values) / len(values))

    return (shift, max(map(abs, deltas)), max(map(abs, after)), rms(deltas), rms(after))


def main() -> int:  # noqa: PLR0915 - one linear report, clearer unsplit
    pinned = _pinned()
    missing = [n for n in ORDER if n not in pinned]
    if missing:
        print(f"REFUSED: not pinned in kernels/pinned_kernels.json: {missing}")
        return 1

    epoch_pass = _utc_to_tdb_seconds(pinned, "1996-01-29T17:45:00")
    epoch_dct = _utc_to_tdb_seconds(pinned, "1996-01-01T00:00:00")
    print("Voyager 2 at DSS-43, DESCANSO Article 4 -- through the FarSight geometry pipeline")
    print(f"  Table 5-5 grid: TDB {epoch_pass} s past J2000, 900 s x {len(TABLE_5_5)}")
    print(f"  DCT epoch     : TDB {epoch_dct} s past J2000")

    # The transcription must be the 15-minute sequence the grid assumes, or rows and samples
    # would be compared out of step without any error.
    for i, (doy, hh, mm, _el, _single) in enumerate(TABLE_5_5):
        minutes = (doy - 29) * 1440 + hh * 60 + mm - (17 * 60 + 45)
        if minutes != 15 * i:
            print(f"REFUSED: Table 5-5 row {i} ({doy} {hh:02d}:{mm:02d}) is out of sequence")
            return 1

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        pass_summary, _pass_range, pass_el = _run(pinned, epoch_pass, "900", len(TABLE_5_5),
                                                  work, "table_5_5")
        dct_summary, dct_range, dct_el = _run(pinned, epoch_dct, "60", 1, work, "dct_epoch")

    print("\n[Table 5-5] computed geometric elevation minus printed; * = single-source row")
    print("   doy hh:mm  printed  computed    delta   refraction est.")
    gate1_rows = gate1_fail = 0
    low_deltas: list[tuple[float, float]] = []
    for (doy, hh, mm, printed, single), computed in zip(TABLE_5_5, pass_el, strict=True):
        delta = float(computed) - printed
        gated = printed >= GATE_ELEVATION_FLOOR_DEG
        bad = gated and abs(delta) > GATE_ELEVATION_TOL_DEG
        gate1_rows += gated
        gate1_fail += bad
        if not gated:
            low_deltas.append((printed, delta))
        mark = "*" if single else " "
        print(f"  {mark}{doy:3d} {hh:02d}:{mm:02d} {printed:8.2f} {float(computed):9.3f} "
              f"{delta:+8.3f}   {_refraction_deg(float(computed)):6.3f}"
              f"{'   GATED' if gated else ''}{'  OUT' if bad else ''}")

    deltas = [float(c) - p for (_d, _h, _m, p, _s), c in zip(TABLE_5_5, pass_el, strict=True)]
    print(f"\n  all rows: max |delta| {max(abs(d) for d in deltas):.3f} deg, "
          f"mean delta {sum(deltas) / len(deltas):+.3f} deg")
    if low_deltas:
        worst = min(low_deltas)
        print(f"  below {GATE_ELEVATION_FLOOR_DEG:.0f} deg: "
              f"lowest printed {worst[0]:.2f} has delta "
              f"{worst[1]:+.3f}; refraction there would be about "
              f"-{_refraction_deg(worst[0]):.3f} if the table were apparent")
    gate1 = gate1_fail == 0
    print(f"GATE 1: {'PASS' if gate1 else 'FAIL'} -- "
          f"{gate1_rows - gate1_fail} of {gate1_rows} rows "
          f"at >= {GATE_ELEVATION_FLOOR_DEG:.0f} deg within {GATE_ELEVATION_TOL_DEG} deg")

    el0, rng0 = float(dct_el[0]), float(dct_range[0])
    el_ok = abs(el0 - DCT_ELEVATION_DEG) <= GATE_ELEVATION_TOL_DEG
    rng_ok = abs(rng0 - DCT_RANGE_KM) <= DCT_RANGE_TOL_KM
    print("\n[DCT epoch, 1996-01-01 00:00 UTC]")
    print(f"  elevation {el0:.3f} deg vs printed {DCT_ELEVATION_DEG} -> "
          f"delta {el0 - DCT_ELEVATION_DEG:+.3f}  {'ok' if el_ok else 'OUT'}")
    print(f"  range     {rng0:.6e} km vs printed {DCT_RANGE_KM:.3e} -> "
          f"delta {rng0 - DCT_RANGE_KM:+.3e} km  {'ok' if rng_ok else 'OUT'}")
    gate2 = el_ok and rng_ok
    print(f"GATE 2: {'PASS' if gate2 else 'FAIL'}")

    print("\n[Reported] space loss from the SPICE range")
    bands = (("S-band uplink", 2113.31, -296.18), ("X-band downlink", 8415.00, -308.19))
    for band, f_mhz, printed in bands:
        loss = -20 * math.log10(4 * math.pi * rng0 * (f_mhz * 1e6) / C_KM_S)
        rounds = abs(loss - printed) <= 0.005 + 1e-9
        print(f"  {band:16s} {f_mhz:8.2f} MHz: {loss:9.3f} dB vs printed {printed:8.2f} "
              f"-> {'rounds to printed' if rounds else 'does NOT round'}")

    print("\n[Provenance] channel hashes")
    for label, summary in (("table_5_5", pass_summary), ("dct_epoch", dct_summary)):
        print(f"  {label}: spec {summary['spec_hash'][:16]}")
        for line in summary["channels"]:
            print(f"    {line}")

    verdict = gate1 and gate2
    word = "REPRODUCED" if verdict else "NOT REPRODUCED"
    print(f"\nSTAGE 1 PART B: {word} under the pre-registered gates")
    # POST-HOC, added after the pre-registered verdict above was fixed and recorded.
    shift_s, max_before, max_after, rms_before, rms_after = _post_hoc_time_shift(
        [float(e) for e in pass_el], deltas)
    print()
    print("[POST-HOC] one least-squares time shift, fitted after the verdict; changes nothing")
    print(f"  computed profile matches the printed one advanced by {shift_s:+.2f} s")
    print(f"  residuals before: max {max_before:.4f} deg, rms {rms_before:.4f}")
    print(f"  residuals after : max {max_after:.4f} deg, rms {rms_after:.4f}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.path.insert(0, str(REPO / "src"))
    raise SystemExit(main())
