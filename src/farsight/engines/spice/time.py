"""Time conversion through the pinned LSK, and the coverage check that makes it honest.

ADR-015 makes SPICE the authoritative UTC-to-TDB path under the pinned leapsecond kernel, and
ADR-016 decision 6 requires exactly one LSK per ``KernelSet`` so that "the pinned LSK" denotes a
single file.

**Why the coverage check exists, in one measured fact.** SPICE does **not** refuse an epoch before
its leap-second table. It extrapolates from the earliest entry and returns a plausible number.
Measured against a table beginning in 2015:

    epoch          truncated table    full naif0012.tls    error
    1980-01-01     67.183918 s        51.183918 s          16 seconds
    2000-01-01     67.183913 s        64.183913 s           3 seconds

A sixteen-second time error propagates into a trajectory as thousands of kilometres, and nothing
in SPICE says a word about it. That is the silent-wrong-number class this product exists to
prevent, and it is why ADR-016's ``kernel_coverage_completeness`` is specified as a **freeze**
validator: at run time there is nothing left to catch, because the wrong answer is
indistinguishable from the right one.

:func:`check_epoch_covered` is that check at the granularity this module can enforce today. The
full validator additionally spans SPK and PCK windows and belongs with ADR-016's coverage
attestation; this is the leapsecond half, which is the half that was silently wrong.
"""

from __future__ import annotations

from typing import Final

from farsight.schemas.errors import UnhonorableSpec

__all__ = [
    "EpochCoverageError",
    "utc_to_et",
    "et_to_utc",
    "delta_et_utc",
    "leapsecond_table",
    "coverage_start_et",
    "check_epoch_covered",
    "DEFINITIONAL_TT_MINUS_TAI",
]

# The definitional TT - TAI offset. Not measured, not read from a kernel: fixed by the definition
# of Terrestrial Time. It appears here so a caller can hand-check a conversion without a kernel.
DEFINITIONAL_TT_MINUS_TAI: Final = 32.184


class EpochCoverageError(UnhonorableSpec):
    """An epoch falls outside what the furnished kernels actually cover.

    A ``WorkerError`` by way of :class:`UnhonorableSpec`, not a ``FreezeTimeError`` -- ADR-023
    Enforcement 6 forbids a freeze-time exception under ``engines/``, because an engine runs
    inside a worker and nothing but bytes crosses the pool boundary.

    That typing carries the right meaning rather than a lesser one. Reaching this exception means
    a spec got past freeze that should not have, and ADR-023 says such a failure "is a report that
    the freeze-time completeness check has a hole". The parent-side refusal is ADR-016's
    ``kernel_coverage_completeness``, raising :class:`~farsight.schemas.errors.KernelCoverageError`
    -- not yet built, and named here rather than implied.
    """


def _spiceypy():
    from farsight.engines.spice.kernels import _spiceypy as _get  # noqa: PLC0415

    return _get()


def leapsecond_table() -> list[tuple[float, float]]:
    """The furnished leap-second table as ``(offset_seconds, transition_et)`` pairs.

    Read from the pool rather than from the file, so it reflects what SPICE will actually use --
    including any override by a later kernel in the furnish order.
    """
    spiceypy = _spiceypy()
    from spiceypy.utils.exceptions import NotFoundError  # noqa: PLC0415 - see module docstring

    try:
        count, _kind = spiceypy.dtpool("DELTET/DELTA_AT")
    except NotFoundError:
        # An unfurnished pool, reported as an empty table rather than as a SPICE lookup failure.
        # Without this the guard in `coverage_start_et` was unreachable in the one situation its
        # message describes: `dtpool` raises first, so the caller got `NotFoundError: Spice
        # returns not found for function: dtpool` instead of a sentence naming the missing LSK.
        # A mutation test found it -- removing that guard changed nothing, because nothing could
        # reach it.
        return []
    values = spiceypy.gdpool("DELTET/DELTA_AT", 0, int(count))
    return [(float(values[i]), float(values[i + 1])) for i in range(0, len(values), 2)]


def coverage_start_et() -> float:
    """The earliest epoch the furnished leap-second table actually describes.

    Before this, SPICE extrapolates rather than refusing, so this value is the boundary between
    an answer and a plausible fiction.
    """
    table = leapsecond_table()
    if not table:
        raise EpochCoverageError(
            "no leapsecond table is furnished, so no UTC conversion is defined. ADR-016 requires "
            "exactly one LSK per kernel set precisely so this cannot be silently absent."
        )
    return min(transition for _offset, transition in table)


def check_epoch_covered(et: float) -> None:
    """Refuse an epoch the furnished leap-second table does not cover.

    The refusal SPICE does not perform. See the module docstring for the measured cost of its
    absence.
    """
    start = coverage_start_et()
    if et < start:
        spiceypy = _spiceypy()
        raise EpochCoverageError(
            f"epoch et={et} ({spiceypy.et2utc(et, 'ISOC', 0)}) is before the furnished "
            f"leapsecond table, which begins at et={start} "
            f"({spiceypy.et2utc(start, 'ISOC', 0)}). SPICE would not refuse this: it "
            f"extrapolates from the earliest entry and returns a plausible, wrong number -- "
            f"measured at 16 seconds of error for a 1980 epoch against a table starting in 2015, "
            f"which is thousands of kilometres once it reaches a trajectory."
        )


def utc_to_et(utc: str, *, check_coverage: bool = True) -> float:
    """Convert a UTC string to ephemeris time (TDB seconds past J2000).

    ``check_coverage`` defaults to on. It exists as a parameter only so that
    :func:`coverage_start_et` itself can convert without recursing, and turning it off is not an
    escape hatch for an uncovered epoch.
    """
    et = float(_spiceypy().str2et(utc))
    if check_coverage:
        check_epoch_covered(et)
    return et


def et_to_utc(et: float, *, precision: int = 3) -> str:
    """Convert ephemeris time back to an ISO UTC string."""
    return str(_spiceypy().et2utc(et, "ISOC", precision))


def delta_et_utc(et: float) -> float:
    """``ET - UTC`` at ``et``: the leap seconds plus the definitional offset plus periodic terms.

    Worth a hand check whenever a kernel set changes: the value should be
    ``(TAI - UTC) + 32.184`` to within the ~1.7 ms periodic relativistic term, and both of those
    inputs are published facts rather than kernel contents.
    """
    return float(_spiceypy().deltet(et, "ET"))
