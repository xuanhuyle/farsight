"""The units boundary (ADR-008) and the drawn-value encoding rule (ADR-022 decision 4).

Two properties carry this module. Conversion happens once, at the boundary, and is a refusal
rather than a coercion when dimensions disagree. And a machine-produced float becomes a decimal
string by the shortest round-tripping representation -- which is inside `spec_hash`, so it may
not depend on a formatter's default precision.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from farsight.schemas.common import DECIMAL_RE, Quantity
from farsight.units import (
    UnitError,
    convert,
    encode_float,
    from_si,
    same_dimension,
    si_unit,
    to_si,
)


def q(mag: str, unit: str) -> Quantity:
    return Quantity(magnitude=mag, unit=unit)


# --------------------------------------------------------------------------------------
# Conversion into SI
# --------------------------------------------------------------------------------------


def test_conversion_is_a_real_conversion_not_an_identity():
    """The guard against this suite passing for the wrong reason. A round-trip test over
    already-SI or dimensionless quantities exercises no conversion at all, so at least one case
    must move the number."""
    assert to_si(q("0.16", "urad")) == pytest.approx(1.6e-07, rel=1e-15)
    assert to_si(q("2.58", "km")) == pytest.approx(2580.0, rel=1e-15)
    assert to_si(q("4", "W")) == pytest.approx(4.0, rel=1e-15)
    assert to_si(q("0.75", "1")) == pytest.approx(0.75, rel=1e-15)


def test_the_authors_digits_are_read_as_a_decimal_not_a_float():
    """The magnitude is parsed by Decimal before scaling, so the value rounds to float64 ONCE
    rather than twice.

    The discriminating case matters: with a scale of 1 the two paths agree on everything, so a
    test using metres proves nothing. Multiplying in float rounds the parse and then rounds the
    product; multiplying in Decimal rounds only the product, and the results differ in the last
    place. This case was found by brute force precisely because the obvious examples do not
    separate the implementations.
    """
    assert to_si(q("535.8820043066892", "km")) == 535882.0043066893
    assert float("535.8820043066892") * 1000.0 == 535882.0043066891  # the path NOT taken

    assert to_si(q("0.1", "m")) == 0.1
    # A magnitude with more digits than float64 can hold must not raise; it is read exactly and
    # only the result is float64.
    assert to_si(q("0.12345678901234567890123", "m")) == pytest.approx(0.12345678901234568)


def test_si_unit_reduces_to_the_base():
    assert si_unit("urad") == "rad"
    assert si_unit("km") == "m"
    assert si_unit("1") == "1"


def test_same_dimension_is_compatibility_not_equality():
    assert same_dimension("m", "km")
    assert same_dimension("urad", "rad")
    assert not same_dimension("m", "s")
    assert not same_dimension("W", "m")


# --------------------------------------------------------------------------------------
# Refusals, never coercions
# --------------------------------------------------------------------------------------


def test_a_dimensional_mismatch_is_refused():
    """Silently reinterpreting one dimension as another is the class of error the plan names
    among the domain's most common silent killers."""
    convert(q("2.58", "km"), "m")
    with pytest.raises(UnitError, match="cannot convert"):
        convert(q("1", "m"), "s")
    with pytest.raises(UnitError, match="cannot convert"):
        convert(q("1", "W"), "rad")


def test_an_unparseable_unit_is_refused_naming_the_symbol():
    for bad in ("flurbles", "not a unit"):
        with pytest.raises(UnitError, match="not parseable"):
            si_unit(bad)


def test_the_empty_string_is_not_a_second_spelling_for_dimensionless():
    """astropy parses "" as dimensionless, which would give FarSight two spellings for one thing.
    ADR-008 and `Quantity._check_unit` both fix the dimensionless spelling as "1"."""
    assert si_unit("1") == "1"
    for bad in ("", " ", " m"):
        with pytest.raises(UnitError, match="empty or padded"):
            si_unit(bad)


def test_a_non_finite_value_cannot_be_encoded():
    """ADR-001 rule 3: ignorance is structural, never numeric. An unknown is an Unknown belief,
    not a sentinel float."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(UnitError, match="non-finite"):
            encode_float(bad, "m")


# --------------------------------------------------------------------------------------
# The encoding rule (ADR-022 decision 4)
# --------------------------------------------------------------------------------------


def test_encoding_is_the_shortest_round_tripping_decimal():
    assert encode_float(0.1, "m").magnitude == "0.1"
    assert encode_float(1e-05, "m").magnitude == "1e-05"
    assert encode_float(1e20, "m").magnitude == "1e+20"
    assert encode_float(2580.0, "m").magnitude == "2580.0"


@given(st.floats(allow_nan=False, allow_infinity=False, width=64))
@settings(max_examples=300, deadline=None)
def test_every_encoded_float_round_trips_and_obeys_the_grammar(value: float):
    """ADR-022 enforcement item 8. Two assertions, and the second is the one that matters for
    identity: the string must parse back to the identical binary64, and it must satisfy ADR-001's
    magnitude grammar -- because this string is hashed."""
    encoded = encode_float(value, "m")
    assert DECIMAL_RE.match(encoded.magnitude)
    assert float(encoded.magnitude) == value


def test_no_rounding_to_significant_figures_happens():
    """ADR-022 rejected rounding to a declared precision. A value needing 17 digits keeps them."""
    value = 0.1 + 0.2  # 0.30000000000000004
    assert encode_float(value, "1").magnitude == "0.30000000000000004"


# --------------------------------------------------------------------------------------
# Round trips
# --------------------------------------------------------------------------------------


def test_si_round_trip_preserves_the_value():
    original = q("0.16", "urad")
    assert from_si(to_si(original), "urad").magnitude == "0.16"

    kilometres = q("2.58", "km")
    assert from_si(to_si(kilometres), "km").magnitude == "2.58"


def test_convert_moves_the_number_and_keeps_the_dimension():
    converted = convert(q("2.58", "km"), "m")
    assert converted.unit == "m"
    assert float(converted.magnitude) == 2580.0
    assert to_si(converted) == to_si(q("2.58", "km"))


@given(st.floats(min_value=1e-30, max_value=1e30, allow_nan=False, allow_infinity=False))
@settings(max_examples=400, deadline=None)
def test_the_si_round_trip_is_within_one_ulp_but_not_exact(value: float):
    """The property that is TRUE, asserted instead of the one that reads better.

    `to_si` narrows to float64 because that is what the core computes in, and that rounding
    cannot be undone by any care in the other direction. Hypothesis found the counterexample in
    seconds: 5749259923628352.0 km returns as 5749259923628351.0 km.

    This matters because a magnitude is hashed. A value authored in km, converted to SI and
    re-encoded in km can differ in the last digit and produce a different `spec_hash` -- which is
    why the rule is that values are encoded once, in the unit they were authored or drawn in, and
    `convert` is for reading rather than for re-minting a hashed magnitude.
    """
    assume(math.isfinite(value))
    encoded = encode_float(value, "km")
    returned = float(from_si(to_si(encoded), "km").magnitude)
    original = float(encoded.magnitude)
    assert abs(returned - original) <= math.ulp(original)


def test_from_si_divides_as_a_decimal_so_fewer_values_lose_a_bit():
    """`from_si` mirrors `to_si`'s Decimal multiplication rather than dividing in float. It does
    not make the round trip exact -- nothing can, since `to_si` already narrowed to float64 --
    but it removes one of the two roundings, and this value is one that float division loses."""
    original = encode_float(3.997976309699061e16, "km")
    assert from_si(to_si(original), "km").magnitude == original.magnitude


def test_encoding_alone_is_exact_which_is_the_property_identity_rests_on():
    """The round trip that must be exact is the one identity actually uses: a float encoded in
    its own unit and read back. No conversion, no narrowing, no ulp."""
    for value in (0.1, 5749259923628352.0, 3.997976309699061e16, 1e-300, 2580.0):
        assert float(encode_float(value, "km").magnitude) == value
