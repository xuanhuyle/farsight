"""One implementation of "the scan actually found something".

MEASURED 2026-09-09. This suite's source-scanning lints work by walking `src/farsight`, collecting
offenders, and asserting there are none. An empty walk has no offenders, so the lint passes while
checking nothing -- and the failure is invisible, because a lint that scans nothing and a lint that
scans everything and finds nothing print the same thing.

The scan roots were pointed at a directory that does not exist, and **seven of the nine scanners
still passed**. The two that failed did so incidentally, on a second assertion, not because
anything checked that the scan had found files.

That is the same shape as three other defects found the day before: the container gate piped into
a closed stdin (it ran an empty program and exited 0), an ISA pin whose rejection arrived as a
warning Python hides, and a deprecated NumPy alias whose removal would have emptied a measured
field through a bare `except`. In each case "did nothing" and "succeeded" were indistinguishable.

A moved package, a renamed directory, or a suite run against an installed wheel rather than the
tree all produce exactly this. The floor below makes it loud.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "farsight"

# A FLOOR, deliberately well under the true count (54 at the time of writing) rather than equal to
# it. An exact count would have to be edited every time a module is added, which is the kind of
# maintenance that gets a check deleted; anything far below the truth still catches a scan that
# found nothing or nearly nothing, which is the failure this exists for.
MINIMUM_MODULES = 25


def python_sources(root: Path | None = None, *, minimum: int = MINIMUM_MODULES) -> list[Path]:
    """Every ``.py`` file under ``root``, refusing a scan that found implausibly little.

    Use this instead of ``root.rglob("*.py")`` in any test that collects offenders and asserts
    there are none. Pass ``minimum`` when scanning a subtree that genuinely holds fewer files.
    """
    scan_root = SRC if root is None else root
    files = sorted(scan_root.rglob("*.py"))
    if len(files) < minimum:
        raise AssertionError(
            f"the source scan found {len(files)} python file(s) under {scan_root}, fewer than the "
            f"{minimum} expected. This is not a finding about the code under test -- it means the "
            f"scan itself is looking at the wrong place, and a lint that scans nothing reports no "
            f"offenders and passes. Check the scan root before trusting any green from this test."
        )
    return files


REQUIRE_KERNELS_ENV = "FARSIGHT_REQUIRE_KERNELS"


def skip_or_fail_on_missing_kernels(detail: str) -> None:
    """Skip when the real kernels are absent — unless the caller has said they must be present.

    A skip is the right DEFAULT. The pinned set is 46 MiB and ADR-016 decision 5 never garbage
    collects it, so a developer who has not spent that disk should still get a useful suite, and
    committing NAIF kernels to the repository is something ADR-016 rejects outright.

    It is the wrong behaviour in a job whose PURPOSE is to run these legs.
    `FARSIGHT_REQUIRE_KERNELS=1` turns the skip into a failure, and CI sets it wherever it has
    just populated the cache.

    Exactly the shape DEV-26 found in the `spice` job's `importorskip`: the mechanism that keeps a
    suite usable without an optional dependency is the same mechanism that hides that dependency's
    absence in the one place it must not be absent. Both are now opt-in strict.
    """
    import os

    import pytest

    if os.environ.get(REQUIRE_KERNELS_ENV) == "1":
        raise AssertionError(
            f"{detail}\n"
            f"{REQUIRE_KERNELS_ENV}=1 is set, so this is a FAILURE rather than a skip: the caller "
            f"stated the kernels would be present. Either the fetch step did not run, or it ran "
            f"and did not populate the cache. A skip here would report a green run that exercised "
            f"none of the real-ephemeris legs -- including the Horizons cross-check."
        )
    pytest.skip(detail)
