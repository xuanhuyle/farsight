"""Quantity, the decimal grammar, and envelope primitives (ADR-001, ADR-008).

The decimal-string magnitude is the decision that lets ADR-001 forbid JSON floats outright, so
the grammar is tested as a grammar: what it accepts, what it refuses, and -- the property that
actually matters in six months -- that it never quietly rewrites what an author wrote.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from farsight.hashing.canonical import canonicalize, content_hash
from farsight.schemas.common import (
    DECIMAL_RE,
    FrozenModel,
    IntervalQ,
    MAX_PATH_CHARS,
    MAX_PATH_SEGMENTS,
    Quantity,
    Ref,
    TimeSpanQ,
    ValidityEnvelope,
    VersionedDocument,
    is_ref,
    validate_path,
    normalize_decimal,
)

# --------------------------------------------------------------------------------------
# The decimal grammar
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "good",
    ["0", "1", "-1", "0.22", "-0.22", "1.5e+3", "-1.5503e-9", "123456789", "0.000001"],
)
def test_grammar_accepts(good):
    assert Quantity(magnitude=good, unit="m").magnitude == good


@pytest.mark.parametrize(
    "bad,why",
    [
        ("+1", "no leading plus"),
        ("01", "no leading zeros"),
        ("5.", "no bare trailing point"),
        (".5", "no bare leading point"),
        ("1E3", "exponent marker is lowercase"),
        ("1e3", "exponent sign is mandatory"),
        ("1,5", "no thousands separators or comma decimals"),
        ("", "empty is not a number"),
        (" 1", "no surrounding whitespace"),
        ("1 ", "no surrounding whitespace"),
        ("nan", "ignorance is structural, never numeric"),
        ("inf", "ignorance is structural, never numeric"),
        ("-inf", "ignorance is structural, never numeric"),
        ("0x1f", "not hexadecimal"),
        ("1_000", "no digit separators"),
    ],
)
def test_grammar_refuses(bad, why):
    with pytest.raises(ValidationError):
        Quantity(magnitude=bad, unit="m")


def test_float_magnitude_is_refused_not_converted():
    # The critical refusal. Accepting 0.1 here would write "0.1000000000000000055511151231257827"
    # or silently round it -- either way inventing significant figures the author never claimed.
    with pytest.raises(ValidationError):
        Quantity(magnitude=0.1, unit="m")


def test_int_and_decimal_magnitudes_are_accepted():
    assert Quantity(magnitude=42, unit="1").magnitude == "42"
    assert Quantity(magnitude=Decimal("0.220"), unit="m").magnitude == "0.220"


def test_significant_figures_survive_round_trip():
    # "0.220" is a claim about a measurement with three significant figures. It must come back
    # out exactly as it went in, or the claim has been edited by software.
    for text in ["0.22", "0.220", "0.2200", "22", "22.0"]:
        assert Quantity(magnitude=text, unit="m").magnitude == text


def test_equal_values_with_different_precision_are_different_objects():
    a = Quantity(magnitude="0.22", unit="m")
    b = Quantity(magnitude="0.220", unit="m")
    assert a != b
    assert a.as_decimal() == b.as_decimal()  # same value...
    assert content_hash(a.model_dump(mode="json")) != content_hash(b.model_dump(mode="json"))


@given(st.integers(min_value=-(10**12), max_value=10**12))
def test_property_int_magnitudes_round_trip(n):
    assert Quantity(magnitude=n, unit="1").as_decimal() == Decimal(n)


@given(st.text(min_size=1, max_size=12))
@settings(max_examples=400)
def test_property_grammar_is_the_only_gate(text):
    # Whatever Hypothesis produces, Quantity accepts it if and only if the grammar matches.
    # No coercion path may exist that admits a string the regex rejects.
    matches = bool(DECIMAL_RE.match(text))
    try:
        Quantity(magnitude=text, unit="m")
        accepted = True
    except ValidationError:
        accepted = False
    assert accepted == matches


@given(st.from_regex(DECIMAL_RE, fullmatch=True))
@settings(max_examples=300)
def test_property_accepted_magnitudes_are_never_rewritten(text):
    assume(len(text) < 100)
    assert Quantity(magnitude=text, unit="m").magnitude == text


@given(st.from_regex(DECIMAL_RE, fullmatch=True))
@settings(max_examples=200)
def test_property_quantities_canonicalize_without_floats(text):
    assume(len(text) < 100)
    q = Quantity(magnitude=text, unit="km")
    out = canonicalize(q.model_dump(mode="json"))  # raises if anything became a float
    assert text in out


# --------------------------------------------------------------------------------------
# Units, intervals, envelopes
# --------------------------------------------------------------------------------------


def test_unit_must_be_a_clean_symbol():
    with pytest.raises(ValidationError):
        Quantity(magnitude="1", unit="")
    with pytest.raises(ValidationError):
        Quantity(magnitude="1", unit=" m ")


def test_interval_requires_matching_units_and_ordering():
    IntervalQ(lower=Quantity(magnitude="0", unit="m"), upper=Quantity(magnitude="1", unit="m"))
    with pytest.raises(ValidationError, match="different units"):
        IntervalQ(
            lower=Quantity(magnitude="0", unit="m"), upper=Quantity(magnitude="1", unit="km")
        )
    with pytest.raises(ValidationError, match="exceeds upper"):
        IntervalQ(lower=Quantity(magnitude="2", unit="m"), upper=Quantity(magnitude="1", unit="m"))


def test_interval_may_be_degenerate():
    # lower == upper is a legitimate zero-width bound, not an error.
    IntervalQ(lower=Quantity(magnitude="1", unit="m"), upper=Quantity(magnitude="1", unit="m"))


def test_time_span_must_be_ordered():
    with pytest.raises(ValidationError):
        TimeSpanQ(
            start=Quantity(magnitude="100", unit="s"), end=Quantity(magnitude="0", unit="s")
        )


def test_envelope_defaults_are_empty_not_permissive():
    # An empty envelope claims nothing; it does not claim universal validity. The distinction
    # matters because ADR-026 flags excursions against `ranges`, and an absent range is a
    # statement that nothing was checked, which the violation register should show as such.
    env = ValidityEnvelope()
    assert env.conditions == [] and env.ranges == {} and env.not_validated_for == []


def test_envelope_conditions_must_be_reviewable_sentences():
    with pytest.raises(ValidationError):
        ValidityEnvelope(conditions=["   "])
    with pytest.raises(ValidationError, match="paragraph"):
        ValidityEnvelope(conditions=["x" * 401])


# --------------------------------------------------------------------------------------
# Ref: digests only, never aliases (ADR-001 rule 7)
# --------------------------------------------------------------------------------------


class _HasRef(BaseModel):
    ref: Ref


@pytest.mark.parametrize(
    "bad",
    [
        "sha256:" + "a" * 64,  # the prefix appears in CLI output, never in a document
        "A" * 64,  # uppercase
        "a" * 63,
        "a" * 65,
        "refs/model/link_budget",  # an alias
        "g" * 64,  # not hex
        "",
    ],
)
def test_ref_refuses_everything_that_is_not_a_bare_digest(bad):
    with pytest.raises(ValidationError):
        _HasRef(ref=bad)
    assert not is_ref(bad)


def test_ref_accepts_a_bare_lowercase_digest():
    good = "0123456789abcdef" * 4
    assert _HasRef(ref=good).ref == good
    assert is_ref(good)


def test_normalize_decimal_rejects_bool():
    with pytest.raises(ValueError):
        normalize_decimal(True)


# --------------------------------------------------------------------------------------
# Copy is construction (ADR-001: a content address is the address of a validated document)
# --------------------------------------------------------------------------------------


class _Small(FrozenModel):
    value: Quantity


def test_model_copy_runs_validators_on_every_frozen_model():
    """Not a Belief-specific repair. `model_copy(update=...)` is inherited by every hashed
    object in the system, and every one of them can be content-addressed, so the fix belongs on
    the base class rather than at the call sites anyone remembers."""
    m = _Small(value=Quantity(magnitude="0.22", unit="m"))
    with pytest.raises(ValidationError):
        m.model_copy(update={"value": 0.22})  # a float, which Quantity refuses
    with pytest.raises(ValidationError):
        m.model_copy(update={"value": "0.22"})  # a bare string where a Quantity belongs
    with pytest.raises(ValidationError):
        m.model_copy(update={"unexpected": 1})  # extra="forbid" applies to copies too

    assert m.model_copy().value == m.value  # no update: unchanged, and still cheap
    assert m.model_copy(update={"value": Quantity(magnitude="0.23", unit="m")}).value.magnitude == "0.23"


def test_versioned_document_carries_a_version_and_plain_models_do_not():
    class _Doc(VersionedDocument):
        pass

    assert _Doc().schema_version == 1
    assert "schema_version" not in _Small(value=Quantity(magnitude="1", unit="m")).model_dump()


# --------------------------------------------------------------------------------------
# The topology path grammar (ADR-017 decision 3)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "good",
    [
        "link",
        "link_margin",
        "ground.palomar.receiver.optical_train",
        "a.b.c.d.e.f.g",  # exactly at the 7-segment cap
    ],
)
def test_path_grammar_accepts_well_formed_paths(good):
    assert validate_path(good) == good


@pytest.mark.parametrize(
    "bad",
    [
        "Ground.Palomar",  # uppercase: filename collision on Windows, not on Linux
        "ground..palomar",  # empty segment
        ".ground",  # leading separator
        "ground.",  # trailing separator
        "ground.palomar_",  # trailing underscore
        "ground.pal__omar",  # doubled underscore
        "ground-station.rx",  # hyphen
        "a.b.c.d.e.f.g.h",  # over the segment cap
        "",
    ],
)
def test_path_grammar_refuses_malformed_paths(bad):
    with pytest.raises(ValueError):
        validate_path(bad)


def test_path_caps_are_enforced_by_length_not_only_by_shape():
    assert len("a" * MAX_PATH_CHARS) == MAX_PATH_CHARS
    with pytest.raises(ValueError, match="over the"):
        validate_path("a" * (MAX_PATH_CHARS + 1))
    with pytest.raises(ValueError, match="segments"):
        validate_path(".".join(["ab"] * (MAX_PATH_SEGMENTS + 1)))


def test_path_sort_is_byte_wise_over_the_whole_string():
    """ADR-017 decision 3: '.' (0x2E) sorts before digits and before '_' (0x5F), so `link`
    precedes `link.margin` precedes `link_x`. Arbitrary, but fixed -- and ADR-005 draws every
    aleatory value in this order, so the sort *is* the drawn values."""
    assert sorted(["link_x", "link.margin", "link"]) == ["link", "link.margin", "link_x"]


def test_decimal_below_the_fixed_point_floor_is_refused_naming_the_renderer():
    """The grammar itself has no exponent floor; this renderer does, because Python's fallback
    emits an uppercase "1E-31". The refusal has to say that, or the next reader edits the
    grammar to fix a problem the grammar does not have."""
    with pytest.raises(ValueError, match="fixed-point floor"):
        Quantity(magnitude=Decimal("1e-31"), unit="m")
    assert Quantity(magnitude=Decimal("1e-30"), unit="m").magnitude.startswith("0.000")
