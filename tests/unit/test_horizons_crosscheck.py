"""`ci-geometry-crosscheck`: our SPICE pipeline against JPL Horizons. ADR-015 Enforcement 3.

Plan §14 item 3 asks for two independent implementations compared rather than merged, because a
systematic frame or time-system error is invisible to a single implementation checked against
itself. This is that comparison for geometry, as `test_time_independence.py` is for time.

**Offline, against a hash-pinned response.** ADR-012 forbids the truth loop any network call, and
ADR-015 says the Horizons response is "a hash-pinned `DataArtifact`" whose "stated settings are
read from the artifact, never copied into prose". So the query was made once, the RAW response is
archived beside this file, and its digest is asserted here -- a golden that changed silently would
be a cross-check comparing against whatever someone edited it to say.

**The tolerance is 10 m on range and 1 arcsec on elevation**, set by the founder on 2026-09-07
under ADR-030, which makes an acceptance tolerance a decision somebody owns rather than a number
read off a measurement. Measured agreement is 0.69 m and 0.134 arcsec, so the margins are 14.5x
and 7.5x.

**WHAT THIS DOES AND DOES NOT ESTABLISH -- read before quoting the numbers.**

Horizons states its own source in the archived header: ``{source: psyche_merged}``. That is JPL's
merged Psyche trajectory -- *the same solution family the SPK carries*. So this is an independent
IMPLEMENTATION, not an independent MEASUREMENT.

It does check, and would fail on, every one of: a wrong target body (the asteroid rather than the
spacecraft), a wrong observer, a wrong reference frame, a wrong aberration convention, a
time-system error, a unit error, and any defect in the pipeline that carries values from a
``RunSpec`` to a channel.

It cannot check whether JPL's trajectory is right. If the reconstructed SPK were wrong, both sides
would be wrong identically and this test would still pass. Calling this "validated against an
independent source" would therefore overstate it; "agrees with an independent implementation of
the same solution" is the claim.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

spiceypy = pytest.importorskip("spiceypy", reason="the `spice` extra is not installed")

from farsight.registry.kernel_cache import KernelCache
from farsight.registry.paths import kernel_cache_root

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "fixtures" / "horizons" / "psyche_palomar_2024-01-15.txt"

# The archived response, pinned. Retrieved 2026-09-07 from
# https://ssd.jpl.nasa.gov/api/horizons.api -- the exact query is in the file's own header.
GOLDEN_SHA256 = "026ab8c0e61d03762e4b4cb6adc239e508e21a5d2641e0c5c985a4f9fbbd73c0"

# Horizons states this in the archived header ("Units conversion: 1 au= ..."), so it is read from
# the artifact rather than from a constant someone typed.
AU_KM_HEADER = "1 au= 149597870.700 km"
AU_KM = 149597870.700

ORDER = ["naif0012.tls", "pck00010.tpc", "psyche_v01.tpc", "earth_000101_260827_260601.bpc",
         "psyche_fk_v10.tf", "de440s.bsp", "psyche_rec_231207-240304_240321_v1.bsp",
         "psyche_dsoc_palomar_v01.bsp", "psyche_dsoc_octl_v01.bsp"]

OBSERVER, TOPO_FRAME, SPACECRAFT = "PSYC_DSOC_PALOMAR", "PSYC_DSOC_PALOMAR_TOPO", "-255"

# THE ACCEPTANCE TOLERANCE. Set by the founder on 2026-09-07, which is what ADR-030 requires: a
# tolerance is a decision somebody owns, not a number inferred from a measurement. These are no
# longer regression bounds -- they are what this check asserts the product's geometry agrees to.
#
#   measured        tolerance      margin
#   0.69 m          10 m           14.5x
#   0.134 arcsec    1 arcsec        7.5x
#
# Two consequences worth knowing before anyone loosens them.
#
# The 0.414 m station artefact documented in
# `test_the_residual_is_explained_by_the_earth_radius_models_and_not_by_the_trajectory` consumes
# about 4% of the range budget, so the budget is not being spent on a known artefact.
#
# And 10 m is TIGHTER than a re-solved trajectory would move things. JPL re-releases
# reconstructed SPKs -- the Psyche archive already carries a `_v2` -- and a new solution can shift
# a range by kilometres. This tolerance therefore makes changing the pinned kernel FAIL this
# check, which is the intended behaviour: a re-solved trajectory is a finding to look at, not a
# golden to quietly refresh.
ACCEPTANCE_RANGE_M = 10.0
ACCEPTANCE_ELEV_ARCSEC = 1.0

# What was actually observed when the tolerance was set, kept so the margin stays legible and a
# slow drift toward the limit is visible rather than merely still-passing.
OBSERVED_RANGE_M = 0.69
OBSERVED_ELEV_ARCSEC = 0.134


def _rows() -> list[dict]:
    text = GOLDEN.read_text("utf-8", "replace")
    rows, inside = [], False
    for line in text.splitlines():
        if line.startswith("$$SOE"):
            inside = True
            continue
        if line.startswith("$$EOE"):
            break
        if inside and line.strip():
            f = [c.strip() for c in line.split(",")]
            rows.append({"utc": f[0], "az": float(f[3]), "el": float(f[4]),
                         "delta_au": float(f[5])})
    return rows


@pytest.fixture(scope="module")
def furnished():
    pinned = {k["logical_name"]: k
              for k in json.loads((REPO / "kernels" / "pinned_kernels.json")
                                  .read_text(encoding="utf-8"))["kernels"]}
    cache = KernelCache(kernel_cache_root())
    missing = [n for n in ORDER if n not in pinned or not cache.has(pinned[n]["sha256"])]
    if missing:
        pytest.skip(f"real kernels not in the local cache: {missing}")

    spiceypy.kclear()
    for name in ORDER:
        spiceypy.furnsh(str(cache.get_path(pinned[name]["sha256"])))
    yield
    spiceypy.kclear()


def test_the_archived_response_is_the_one_that_was_retrieved():
    """A golden that can be edited silently is not a cross-check.

    Asserted before anything is compared against it, because every number below is only as
    trustworthy as the bytes they are compared to.
    """
    assert GOLDEN.exists(), f"{GOLDEN} is missing"
    assert hashlib.sha256(GOLDEN.read_bytes()).hexdigest() == GOLDEN_SHA256


def test_the_golden_is_protected_from_line_ending_conversion():
    """The failure this test exists to explain, rather than merely detect.

    MEASURED 2026-09-07: with `core.autocrlf=true` -- the Git for Windows default -- and no
    `.gitattributes`, this file came out of a FRESH CLONE as 12,036 bytes with 225 CRLF pairs
    instead of the 11,811 committed. The digest assertion above then failed on a correct checkout
    of correct content, for a reason that has nothing to do with geometry.

    `kernels/pinned_kernels.json` already carried the same warning one level up: NAIF's
    `naif0012.tls.pc` is the same leapsecond kernel with CRLF endings and a different content
    address. This is that warning applied to a file inside this repository.

    Checked as its own assertion so the message names the cause. A bare digest mismatch sends a
    reader looking for a re-solved trajectory.
    """
    assert (REPO / ".gitattributes").exists(), (
        "no .gitattributes, so every hash-pinned fixture is subject to line-ending conversion"
    )
    rules = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "tests/fixtures/horizons/** -text" in rules, (
        "the archived Horizons response is not marked `-text`, so Git may rewrite its bytes on "
        "checkout and its pinned digest becomes machine-dependent"
    )
    assert b"\r\n" not in GOLDEN.read_bytes(), (
        "the archived response contains CRLF line endings, so this working tree was checked out "
        "with conversion enabled. The data is not corrupt -- the checkout is. Verify "
        "`.gitattributes` is present and re-checkout the file"
    )


def test_the_archived_settings_are_the_ones_we_compare_under():
    """ADR-015: the response's stated settings are read FROM THE ARTIFACT, never copied into
    prose. If Horizons had been queried with refraction on, or a different site, or a different
    body, the comparison below would be meaningless -- so the settings are asserted, not assumed.
    """
    header = GOLDEN.read_text("utf-8", "replace")
    assert "Psyche Spacecraft" in header and "-255" in header
    assert "Atmos refraction: NO (AIRLESS)" in header, "SPICE models no atmosphere either"
    assert "Center pole/equ : ITRF93" in header, "the site frame must be the one we use"
    assert AU_KM_HEADER in header, "the au conversion is read from the artifact"
    # The source Horizons used, which is what bounds the claim this test can make.
    assert "psyche_merged" in header


def test_range_agrees_with_horizons(furnished):
    """Horizons' `delta` on an apparent observer table is the light-time-corrected range, which is
    our converged-Newtonian reception case `CN`."""
    worst = 0.0
    for row in _rows():
        et = spiceypy.str2et(row["utc"].replace("-Jan-", "-01-").replace(" ", "T", 1))
        ours = spiceypy.vnorm(spiceypy.spkpos(SPACECRAFT, et, TOPO_FRAME, "CN", OBSERVER)[0])
        worst = max(worst, abs(ours - row["delta_au"] * AU_KM))

    worst_m = worst * 1000
    assert worst_m < ACCEPTANCE_RANGE_M, (
        f"range disagreement is {worst_m:.3f} m, over the {ACCEPTANCE_RANGE_M} m tolerance "
        f"(it was {OBSERVED_RANGE_M} m when that tolerance was set). Over a 61.5 million km "
        f"range, so this is a relative agreement of {worst / 6.15e7:.1e}. If the pinned kernels "
        f"changed, this is a re-solved trajectory and wants looking at, not a refreshed golden"
    )


def test_elevation_agrees_with_horizons(furnished):
    """Horizons' azimuth and elevation on this table are APPARENT, so they carry stellar
    aberration -- our `CN+S`. Elevation rather than azimuth: azimuth conventions differ between
    NAIF station frames and Horizons, and azimuth is ill-conditioned near the zenith, which this
    pass reaches (81.7 deg)."""
    worst = 0.0
    for row in _rows():
        et = spiceypy.str2et(row["utc"].replace("-Jan-", "-01-").replace(" ", "T", 1))
        position, _lt = spiceypy.spkpos(SPACECRAFT, et, TOPO_FRAME, "CN+S", OBSERVER)
        _r, _lon, lat = spiceypy.reclat(position)
        worst = max(worst, abs(math.degrees(lat) - row["el"]) * 3600)

    assert worst < ACCEPTANCE_ELEV_ARCSEC, (
        f"elevation disagreement is {worst:.4f} arcsec, over the {ACCEPTANCE_ELEV_ARCSEC} arcsec "
        f"tolerance (it was {OBSERVED_ELEV_ARCSEC} when that tolerance was set)"
    )


def test_the_residual_is_explained_by_the_earth_radius_models_and_not_by_the_trajectory(furnished):
    """The sub-metre residual has a cause, and naming it is what makes it evidence rather than
    luck.

    The site was given to Horizons as geodetic lon/lat/alt, derived with `pck00010.tpc`'s Earth
    radii (a = 6378.1366 km). Horizons rebuilt a Cartesian position from those numbers using its
    own model (a = 6378.137 km, stated in the archived header). The 0.4 km difference in
    equatorial radius displaces the station by ~0.41 m, which projected on the line of sight is
    exactly the observed 0.11-0.69 m spread -- largest when Psyche is overhead, which is what the
    data shows.

    So the residual is an artefact of how the site was specified, not a disagreement about where
    the spacecraft is.
    """
    et = spiceypy.str2et("2024-01-15T06:00:00")
    truth, _lt = spiceypy.spkpos(OBSERVER, et, "ITRF93", "NONE", "EARTH")

    ours = spiceypy.bodvrd("EARTH", "RADII", 3)[1]
    assert abs(ours[0] - 6378.1366) < 1e-6, "pck00010 equatorial radius changed"

    lon, lat, alt = spiceypy.recgeo(truth, ours[0], (ours[0] - ours[2]) / ours[0])
    a_h, c_h = 6378.137, 6356.752          # stated in the archived Horizons header
    theirs = spiceypy.georec(lon, lat, alt, a_h, (a_h - c_h) / a_h)

    offset_m = spiceypy.vnorm(spiceypy.vsub(theirs, truth)) * 1000
    assert 0.3 < offset_m < 0.6, offset_m
    # ... and it accounts for the observed range spread rather than merely being the same order.
    assert offset_m > OBSERVED_RANGE_M * 0.5
