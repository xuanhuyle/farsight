"""The units boundary: the one place a hashed decimal string becomes an SI float.

ADR-008. Units are declarative metadata on schema fields, normalized to SI at the boundary;
**nothing in the numeric core sees a unit-carrying object**. Inside ``engines/``, ``metrics/``
and ``uncertainty/`` it is raw SI float64 and numpy, and the ``no_units_lib_in_core`` import
contract enforces that by forbidding ``astropy`` and ``pint`` there. This module is the other
side of that contract -- the boundary the contract exists to protect -- and the only place in
``src/farsight/`` that a unit library is imported for conversion.

The reason for the split is stated in ADR-008 as a cost, not a preference: a unit library in an
inner loop is "a 20-100x tax and a correctness illusion". Correctness comes from converting once,
at construction, and testing that conversion -- not from carrying a unit object through
arithmetic that will be numpy anyway.

**Placement deviates from ADR-008's sketch, and the shipped code already chose this.** The record
puts ``to_si()`` as a method on ``Quantity`` in ``schemas/common.py``. It cannot live there:
``schemas`` is a leaf package (the ``schemas_is_leaf`` contract), and ``common.py``'s own
docstring already says "the conversion boundary lives in ``farsight.units``, not here, because
this package is a leaf and may not import a unit library". Recorded as DEV-10.

**Conversion through SI is not bit-reversible, and nothing may depend on it being so.**
:func:`to_si` narrows to float64 because that is what the core computes in, and that narrowing is
a rounding no care in the other direction can undo. A Hypothesis property found the counterexample
immediately: ``5749259923628352.0 km`` returns as ``5749259923628351.0 km``, one ulp away.

The consequence is a real hazard rather than a curiosity, because a magnitude is hashed: a value
authored in km, converted to SI for the core, and re-encoded in km for a hashed document can
differ in the last digit and therefore produce a different ``spec_hash``. **The rule is that
values are encoded once, in the unit they are authored or drawn in** -- ADR-022's encoding rule
applies to a machine-produced float already expressed in its target unit, not to a value that has
made a round trip. :func:`convert` is for reading, not for re-minting a hashed magnitude.

**Two directions, and they are not symmetric.**

:func:`to_si` reads a hashed ``Quantity`` and returns the float the core computes with. The
decimal string is parsed by :class:`decimal.Decimal` first, so the author's written digits are not
rounded through binary before scaling -- ``"0.1"`` is the decimal one tenth here, not the float
nearest to it, until the last step where it must become float64 because that is what the core
computes in.

:func:`from_si` goes the other way, and that is where identity is at stake: a machine-produced
float becoming a decimal string is part of ``spec_hash``. ADR-022 decision 4 fixes the rule --
**the shortest decimal string that round-trips to the same binary64**, normalized into ADR-001's
magnitude grammar. That is what ``repr()`` produces in Python, and it is used deliberately rather
than a format specifier with a chosen precision, because ADR-022 rejected rounding to a declared
precision precisely so the encoding cannot depend on a formatter's default.
"""

from __future__ import annotations

import math
from decimal import Decimal

from farsight.schemas.common import DECIMAL_RE, Quantity
from farsight.schemas.errors import FarSightError

__all__ = [
    "UnitError",
    "to_si",
    "from_si",
    "encode_float",
    "si_unit",
    "same_dimension",
    "convert",
]


class UnitError(FarSightError, ValueError):
    """A unit cannot be parsed, or two units are not dimensionally compatible.

    Both bases are load-bearing, as on ``CanonicalizationError``. ``FarSightError`` because
    ADR-023 decision 8 requires every exception defined under ``src/farsight/`` to sit in the
    hierarchy -- one that does not is a site the worker's exception-to-``failure_class`` mapping
    cannot classify, and ``test_exception_hierarchy_closed`` caught this class the moment it was
    written. ``ValueError`` because every raising site here is reachable from inside a Pydantic
    validator, and Pydantic folds only ``ValueError`` and ``AssertionError`` into a
    ``ValidationError``; dropping it would make a unit refusal escape as a second exception type.
    """


def _unit(symbol: str):
    """Parse a unit symbol with astropy, or refuse naming the symbol.

    Imported inside the function so that importing ``farsight.units`` stays cheap and the astropy
    dependency is visible at its point of use rather than at module scope.
    """
    from astropy import units as u  # noqa: PLC0415 - deliberate; see docstring

    if not symbol or symbol.strip() != symbol:
        # astropy parses "" as dimensionless, which would give FarSight two spellings for one
        # thing. ADR-008 and `Quantity._check_unit` both fix the dimensionless spelling as "1",
        # and one meaning with two representations is the ambiguity the decimal grammar and the
        # path grammar are both written to prevent.
        raise UnitError(
            f"unit {symbol!r} is empty or padded. A dimensionless quantity is spelled '1' "
            f"(ADR-008); the empty string is not a second spelling for it."
        )
    try:
        return u.Unit(symbol, parse_strict="raise")
    except Exception as exc:  # astropy raises several types for a malformed symbol
        raise UnitError(
            f"unit {symbol!r} is not parseable by astropy (ADR-008). A dimensionless quantity is "
            f"spelled '1'; a unit FarSight should understand but astropy does not is a "
            f"conversion-table row (ADR-008), not a special case here."
        ) from exc


def si_unit(symbol: str) -> str:
    """The SI unit that ``symbol`` reduces to. ``'urad'`` -> ``'rad'``, ``'km'`` -> ``'m'``."""
    return str(_unit(symbol).si.bases[0]) if _unit(symbol).si.bases else "1"


def same_dimension(a: str, b: str) -> bool:
    """True when two unit symbols measure the same physical dimension.

    Dimensional compatibility, not equality: ``'km'`` and ``'m'`` are compatible; ``'m'`` and
    ``'s'`` are not. This is the check a schema boundary wants before it converts anything.
    """
    return _unit(a).physical_type == _unit(b).physical_type


def to_si(q: Quantity) -> float:
    """The quantity's magnitude in SI base units, as float64.

    The single conversion point ADR-008 names.
    """
    scale = _unit(q.unit).si.scale
    value = float(Decimal(q.magnitude) * Decimal(repr(scale)))
    if not math.isfinite(value):
        raise UnitError(
            f"converting {q} to SI produced a non-finite value. Ignorance is structural, never "
            f"numeric (ADR-001 rule 3): a quantity that overflows float64 in SI is a modelling "
            f"error, not a number to carry forward."
        )
    return value


def encode_float(value: float, unit: str) -> Quantity:
    """Encode a float already expressed in ``unit`` as a hashed ``Quantity``.

    ADR-022 decision 4: the shortest decimal string that round-trips to the same binary64,
    normalized into ADR-001's magnitude grammar. ``repr`` is that string in Python, and it is used
    rather than a format specifier because this step sits inside ``spec_hash`` and must not depend
    on a formatter's default precision.
    """
    if not math.isfinite(value):
        raise UnitError(
            f"cannot encode non-finite value {value!r} as a magnitude. NaN and Infinity are "
            f"forbidden in every hashed document (ADR-001 rule 3); an unknown is an Unknown "
            f"belief, never a sentinel float."
        )
    text = repr(float(value))
    if not DECIMAL_RE.match(text):
        raise UnitError(
            f"repr({value!r}) is {text!r}, outside ADR-001's magnitude grammar. The shortest "
            f"round-tripping decimal is the rule (ADR-022 decision 4); where repr and the grammar "
            f"disagree the grammar is the authority, and closing the gap is a decided "
            f"normalization rather than a silent reformat."
        )
    q = Quantity(magnitude=text, unit=unit)
    if float(q.magnitude) != float(value):
        raise UnitError(f"encoding {value!r} did not round-trip: got {q.magnitude!r}")
    return q


def from_si(value: float, unit: str) -> Quantity:
    """Build a ``Quantity`` in ``unit`` from a value expressed in SI base units.

    The inverse of :func:`to_si`, encoded by :func:`encode_float`.
    """
    scale = _unit(unit).si.scale
    if scale == 0:
        raise UnitError(f"unit {unit!r} has a zero SI scale and cannot be inverted")
    # Divided as Decimal, matching `to_si`'s multiplication. Float division here loses a bit on
    # values near the top of the float64 range -- caught by the round-trip property test, which
    # failed on 3.997976309699061e+16 km until this was Decimal. The asymmetry mattered because
    # the two directions are meant to compose.
    return encode_float(float(Decimal(repr(value)) / Decimal(repr(scale))), unit)


def convert(q: Quantity, to_unit: str) -> Quantity:
    """Convert a quantity into ``to_unit``, refusing a dimensional mismatch.

    A refusal, never a coercion. Silently reinterpreting one dimension as another is the class of
    error the plan names among the domain's most common silent killers, and it is cheap to refuse
    at the boundary rather than to discover in a plausible wrong number.
    """
    if not same_dimension(q.unit, to_unit):
        raise UnitError(
            f"cannot convert {q} to {to_unit!r}: {_unit(q.unit).physical_type} is not "
            f"{_unit(to_unit).physical_type}. Units are checked here precisely so a dimensional "
            f"error is refused at the boundary."
        )
    return from_si(to_si(q), to_unit)
