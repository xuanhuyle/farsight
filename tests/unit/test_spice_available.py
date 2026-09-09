"""SPICE is installed, isolated, and agrees with a hand-computed value (ADR-014, ADR-015).

Everything here skips when ``spiceypy`` is absent, because that absence is a **feature**: ADR-007
requires ``verify`` to run on the base install with no extras, and three records call the
resulting property -- an auditor's install that pulls no compiled CSPICE -- the most commercially
important one in the codebase. A test suite that failed without the extra would quietly make the
extra mandatory.

The kernel used is authored by FarSight rather than redistributed. ADR-016 rejects a curated
FarSight kernel bundle and requires real kernels to be fetched by hash from a publisher URL; its
own Enforcement item 2 uses FarSight-authored text kernels for fixtures, which is what
``tests/fixtures/farsight_authored.tls`` is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._guards import skip_or_fail_on_missing_kernels

spiceypy = pytest.importorskip(
    "spiceypy",
    reason="the `spice` extra is not installed -- which is the auditor's install, and is fine",
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE_LSK = REPO / "tests" / "fixtures" / "farsight_authored.tls"

# The DSOC benchmark epoch from the K2 envelope work.
DSOC_EPOCH_UTC = "2024-06-24T00:00:00"

# ET - UTC is definitionally (TAI - UTC) + 32.184 s. TAI - UTC has been 37 s since 2017-01-01,
# and 32.184 is the definitional TT - TAI offset -- so 69.184 s is hand-computed from two
# published facts, not read out of the kernel. The residual is the periodic relativistic term of
# the TDB - TT series, bounded by roughly 1.7 ms.
HAND_COMPUTED_ET_MINUS_UTC = 37 + 32.184
RELATIVISTIC_TERM_BOUND_S = 0.002


@pytest.fixture
def furnished():
    """Furnish the authored fixture and clear the pool afterwards.

    Clearing matters: CSPICE keeps one global kernel pool per process, which is the reason
    ADR-002 grants SPICE its single ``reusable_worker`` exemption and the reason a leaked pool
    would make one test's kernels visible to the next.
    """
    spiceypy.furnsh(str(FIXTURE_LSK))
    try:
        yield spiceypy
    finally:
        spiceypy.kclear()


def test_the_toolkit_is_the_version_we_think_it_is():
    """Pinned loosely: the wheel bundles a compiled CSPICE, and which one it bundles is a fact
    about the install rather than about our code. Recorded so a silent toolkit change is visible
    in a diff rather than in a divergent number."""
    assert spiceypy.__version__.startswith("6.")
    assert spiceypy.tkvrsn("TOOLKIT").startswith("CSPICE_N")


def test_the_pool_starts_and_ends_empty(furnished):
    """One kernel furnished, and the fixture clears it. A leaked pool is how one test's kernels
    become another's silent input."""
    assert furnished.ktotal("ALL") == 1


def test_a_time_conversion_matches_a_hand_computed_value(furnished):
    """The check that is worth having: 69.184 s is computed from the definitional 32.184 s offset
    and the published 37 leap seconds, NOT read out of the kernel. Comparing SPICE against itself
    would show only that it is self-consistent."""
    et = furnished.str2et(DSOC_EPOCH_UTC)
    delta = furnished.deltet(et, "ET")
    assert abs(delta - HAND_COMPUTED_ET_MINUS_UTC) < RELATIVISTIC_TERM_BOUND_S


def test_utc_round_trips_through_ephemeris_time(furnished):
    et = furnished.str2et(DSOC_EPOCH_UTC)
    assert furnished.et2utc(et, "ISOC", 3) == DSOC_EPOCH_UTC + ".000"


def test_an_epoch_outside_the_fixtures_table_is_silently_wrong(furnished):
    """SPICE does NOT refuse an epoch before the leap-second table. It extrapolates from the
    earliest entry and returns a plausible number.

    This test asserted a refusal when it was written, and the refusal does not happen. The real
    behaviour is worse and worth pinning: with a table starting in 2015, converting a 1980 epoch
    is wrong by **16 seconds** and nothing says so. Against the full naif0012.tls the same call
    gives 51.183918 s; this fixture gives 67.183918 s.

    That is the silent-wrong-number class this whole product exists to prevent, sitting inside
    our own test fixture -- and it is the concrete argument for ADR-016's
    `kernel_coverage_completeness` being a freeze validator rather than a runtime check. A
    16-second time error propagates into a trajectory as thousands of kilometres and looks
    entirely normal on the way through.
    """
    outside = furnished.deltet(furnished.str2et("1980-01-01T00:00:00"), "ET")
    inside = furnished.deltet(furnished.str2et(DSOC_EPOCH_UTC), "ET")

    # No exception was raised -- that is the finding.
    assert outside == pytest.approx(67.183918, abs=1e-5)
    # And it is wrong by the difference between the 1980 leap-second count and the fixture's
    # earliest entry: 36 - 20 = 16 seconds.
    assert abs(outside - 51.183918) == pytest.approx(16.0, abs=1e-5)
    assert inside == pytest.approx(69.184303, abs=1e-5)


def test_the_fixture_is_ours_and_says_so():
    """ADR-016 rejects bundling NAIF kernels. A fixture that did not say it was authored here
    would be indistinguishable from a redistributed one after the first person copies it."""
    text = FIXTURE_LSK.read_text(encoding="utf-8")
    assert "AUTHORED BY FARSIGHT" in text
    assert "NOT A NAIF PRODUCT" in text


# --------------------------------------------------------------------------------------
# The real kernel, when it has been fetched
# --------------------------------------------------------------------------------------

NAIF_LSK_SHA = "678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b"


def _cached_naif_lsk() -> Path | None:
    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import kernel_cache_root

    cache = KernelCache(kernel_cache_root())
    return cache.get_path(NAIF_LSK_SHA) if cache.has(NAIF_LSK_SHA) else None


def test_the_authored_fixture_agrees_with_the_real_kernel():
    """The fixture's whole claim is that it is equivalent for the epochs it covers. Asserted
    against the real kernel where it has been fetched, and skipped where it has not -- because
    the alternative is committing a NAIF kernel to the repo, which ADR-016 rejects.
    """
    real = _cached_naif_lsk()
    if real is None:
        skip_or_fail_on_missing_kernels("naif0012.tls has not been fetched into this cache")

    spiceypy.furnsh(str(FIXTURE_LSK))
    try:
        authored = spiceypy.deltet(spiceypy.str2et(DSOC_EPOCH_UTC), "ET")
    finally:
        spiceypy.kclear()

    spiceypy.furnsh(str(real))
    try:
        genuine = spiceypy.deltet(spiceypy.str2et(DSOC_EPOCH_UTC), "ET")
    finally:
        spiceypy.kclear()

    assert authored == pytest.approx(genuine, abs=1e-9)
