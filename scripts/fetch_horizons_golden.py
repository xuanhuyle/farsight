"""Retrieve the Horizons golden for `ci-geometry-crosscheck`. ADR-015 Enforcement 3.

Run this only to REFRESH the archived response; the cross-check itself
(`tests/unit/test_horizons_crosscheck.py`) reads the archived file and makes no network call,
because ADR-012 forbids the truth loop one.

    python scripts/fetch_horizons_golden.py

Writes `tests/fixtures/horizons/psyche_palomar_2024-01-15.txt` and prints its SHA-256. If the
digest changes, `GOLDEN_SHA256` in the test must be updated **deliberately** -- a golden that
drifts silently is a cross-check against whatever it drifted to.

The station coordinates below are not a published site: they are the position of
`PSYC_DSOC_PALOMAR` read out of `psyche_dsoc_palomar_v01.bsp` and converted to geodetic with
`pck00010.tpc`'s Earth radii. Using our own station rather than Horizons' Palomar site keeps the
comparison about the trajectory and the conventions. It leaves one artefact, which the test
quantifies: Horizons rebuilds a Cartesian position from these numbers with a slightly different
Earth radius, displacing the station by ~0.41 m.
"""

from __future__ import annotations

import hashlib
import pathlib
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "fixtures" / "horizons" / "psyche_palomar_2024-01-15.txt"

BASE = "https://ssd.jpl.nasa.gov/api/horizons.api"
SITE_COORD = "-116.864880,33.356300118,1.709704"   # PSYC_DSOC_PALOMAR, from the SPK

QUERY = {
    "format": "text",
    "COMMAND": "'-255'",              # the Psyche SPACECRAFT. 'PSYCHE' is the ASTEROID, 2000016.
    "EPHEM_TYPE": "OBSERVER",
    "CENTER": "'coord@399'",
    "COORD_TYPE": "GEODETIC",
    "SITE_COORD": f"'{SITE_COORD}'",
    "START_TIME": "'2024-01-15 00:00'",
    "STOP_TIME": "'2024-01-16 00:00'",
    "STEP_SIZE": "'3 h'",
    "QUANTITIES": "'4,20'",           # 4 = apparent azimuth/elevation, 20 = range & range-rate
    "APPARENT": "'AIRLESS'",          # SPICE models no atmosphere, so neither may Horizons
    "ANG_FORMAT": "'DEG'",
    "CSV_FORMAT": "'YES'",
    "REF_SYSTEM": "'ICRF'",
    "TIME_DIGITS": "'FRACSEC'",
    "EXTRA_PREC": "'YES'",
}


def main() -> int:
    url = BASE + "?" + urllib.parse.urlencode(QUERY)
    request = urllib.request.Request(url, headers={"User-Agent": "farsight-crosscheck/0.0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:  # https, fixed host
        body = response.read()

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    previous = GOLDEN.read_bytes() if GOLDEN.exists() else None
    GOLDEN.write_bytes(body)

    digest = hashlib.sha256(body).hexdigest()
    print(f"bytes  : {len(body)}")
    print(f"sha256 : {digest}")
    if previous is not None and previous != body:
        print("\nTHE GOLDEN CHANGED. Update GOLDEN_SHA256 in "
              "tests/unit/test_horizons_crosscheck.py only after reading the diff: a changed "
              "response can mean a re-solved trajectory, which is a finding rather than a chore.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
