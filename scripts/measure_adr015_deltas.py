"""Measure ADR-015's three UNVERIFIED convention deltas. Enforcement item 4.

Run this to regenerate the figures in `docs/measurements/ADR-015-enforcement-4-deltas.md`:

    python scripts/measure_adr015_deltas.py

Requires the `spice` extra and the nine kernels in `kernels/pinned_kernels.json` present in the
local cache; fetch them with `farsight fetch kernel --url ... --expect-md5 ...`. Prints a table and
exits 1 if any kernel is missing, so a stale or partial cache is a failure rather than a subset.

Deliberately a script rather than a test: it needs 46 MiB of kernels that CI does not have, and a
test that skips silently in CI is a measurement nobody takes.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]

OBSERVER = "PSYC_DSOC_PALOMAR"
TOPO_FRAME = "PSYC_DSOC_PALOMAR_TOPO"
SPACECRAFT = "-255"  # PSYC. NOT "PSYCHE", which is the ASTEROID (2000016).

EPOCHS = [
    "2023-12-20T04:00:00", "2024-01-05T04:00:00", "2024-01-15T00:00:00",
    "2024-01-15T06:00:00", "2024-01-15T12:00:00", "2024-02-01T04:00:00",
    "2024-02-20T04:00:00", "2024-03-01T04:00:00",
]
REFERENCE_EPOCH = "2024-01-15T04:00:00"

# Furnish order is the decision (ADR-016 decision 2): later kernels override earlier ones.
ORDER = ["naif0012.tls", "pck00010.tpc", "psyche_v01.tpc", "earth_000101_260827_260601.bpc",
         "psyche_fk_v10.tf", "de440s.bsp", "psyche_rec_231207-240304_240321_v1.bsp",
         "psyche_dsoc_palomar_v01.bsp", "psyche_dsoc_octl_v01.bsp"]


def main() -> int:
    import spiceypy

    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import kernel_cache_root

    pinned = {k["logical_name"]: k
              for k in json.loads((REPO / "kernels" / "pinned_kernels.json")
                                  .read_text(encoding="utf-8"))["kernels"]}
    cache = KernelCache(kernel_cache_root())

    missing = [n for n in ORDER if n not in pinned or not cache.has(pinned[n]["sha256"])]
    if missing:
        print(f"missing from the cache: {missing}", file=sys.stderr)
        return 1

    spiceypy.kclear()
    try:
        for name in ORDER:
            spiceypy.furnsh(str(cache.get_path(pinned[name]["sha256"])))

        def azel(frame: str, aberration: str, et: float) -> tuple[float, float]:
            position, _lt = spiceypy.spkpos(SPACECRAFT, et, frame, aberration, OBSERVER)
            if frame != TOPO_FRAME:
                position = spiceypy.mxv(spiceypy.pxform(frame, TOPO_FRAME, et), position)
            _r, lon, lat = spiceypy.reclat(position)
            return math.degrees(lon), math.degrees(lat)

        print("1. ITRF93 vs IAU_EARTH (sky separation of the apparent direction)\n")
        print(f"{'UTC':22}{'elev ITRF93':>13}{'d(elev)\"':>11}{'sky sep\"':>10}")
        worst_elev = worst_sep = 0.0
        for utc in EPOCHS:
            et = spiceypy.str2et(utc)
            a1, e1 = azel(TOPO_FRAME, "CN+S", et)
            a2, e2 = azel("IAU_EARTH", "CN+S", et)
            sep = math.degrees(spiceypy.vsep(
                spiceypy.latrec(1.0, math.radians(a1), math.radians(e1)),
                spiceypy.latrec(1.0, math.radians(a2), math.radians(e2)))) * 3600
            worst_elev = max(worst_elev, abs(e1 - e2) * 3600)
            worst_sep = max(worst_sep, sep)
            print(f"{utc:22}{e1:13.5f}{(e1 - e2) * 3600:11.2f}{sep:10.2f}")
        print(f"\n   worst |d(elev)| = {worst_elev:.2f}\" = {worst_elev / 3600:.6f} deg")
        print(f"   worst sky separation = {worst_sep:.2f}\"")
        print(f"   AT-11 tolerance 0.01 deg = 36\" -> "
              f"{'LARGER' if worst_elev > 36 else 'well inside'}")

        et = spiceypy.str2et(REFERENCE_EPOCH)
        r_none = spiceypy.vnorm(spiceypy.spkpos(SPACECRAFT, et, TOPO_FRAME, "NONE", OBSERVER)[0])
        r_cn = spiceypy.vnorm(spiceypy.spkpos(SPACECRAFT, et, TOPO_FRAME, "CN", OBSERVER)[0])
        print(f"\n2. NONE vs CN range at {REFERENCE_EPOCH}")
        print(f"   NONE {r_none:>18,.3f} km")
        print(f"   CN   {r_cn:>18,.3f} km")
        print(f"   delta {abs(r_none - r_cn):>17,.3f} km   AT-11 tolerance 10 km -> "
              f"{'LARGER' if abs(r_none - r_cn) > 10 else 'inside'}")

        e_cn = azel(TOPO_FRAME, "CN", et)[1]
        e_cns = azel(TOPO_FRAME, "CN+S", et)[1]
        print(f"\n3. CN vs CN+S elevation at {REFERENCE_EPOCH}")
        print(f"   CN   {e_cn:.6f} deg")
        print(f"   CN+S {e_cns:.6f} deg")
        print(f"   delta {abs(e_cn - e_cns) * 3600:.2f}\" = {abs(e_cn - e_cns):.6f} deg   "
              f"AT-11 tolerance 0.01 deg -> "
              f"{'LARGER' if abs(e_cn - e_cns) > 0.01 else 'inside, same order'}")
    finally:
        spiceypy.kclear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
