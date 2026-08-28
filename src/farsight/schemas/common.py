"""Shared schema primitives: quantities, references, intervals, envelopes.

ADR-001 and ADR-008. This module is the bottom of the stack: ``farsight.schemas`` imports
nothing else inside FarSight (enforced by the ``schemas_is_leaf`` import-linter contract), so
everything else in the system can depend on it and it can depend on nothing.

The single most consequential decision expressed here is that **a physical quantity in a
hashed document is a decimal string plus a unit, never a float**. That is what lets ADR-001
forbid JSON floats outright, which in turn removes the least portable part of canonical JSON
from the trust surface. The cost is paid in this module: a `Quantity` is compared, sorted and
hashed as a string, so ``"0.220"`` and ``"0.22"`` are different objects. That is intentional.
Significant figures are an engineering claim -- a 22.0 cm aperture and a 22 cm aperture are
different statements about what somebody measured -- and normalizing them away would discard
the claim silently.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "FrozenModel",
    "Quantity",
    "IntervalQ",
    "TimeSpanQ",
    "ValidityEnvelope",
    "Ref",
    "DECIMAL_RE",
    "SEGMENT_RE",
    "is_ref",
    "normalize_decimal",
]

# ADR-001 rule 2. Exact, and validated rather than described:
#   decimal := "-"? int frac? exp?
#   int     := "0" | [1-9] [0-9]*
#   frac    := "." [0-9]+
#   exp     := "e" ("+" | "-") [0-9]+
# No leading "+", no leading zeros, no bare "5." or ".5", lowercase "e", mandatory exponent
# sign. Anything outside the grammar is rejected, never coerced.
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:e[+-][0-9]+)?$")

# ADR-017 rule 3, reproduced here because `Ref` and identifier fields need it and schemas is a
# leaf package. Lowercase ASCII, digits and single underscores; no leading/trailing underscore,
# no doubled underscore, at most 32 characters.
SEGMENT_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def is_ref(s: str) -> bool:
    """True when ``s`` is a bare lowercase 64-hex content address (ADR-001 rule 7)."""
    return bool(_HEX64_RE.match(s))


def normalize_decimal(value: Any) -> str:
    """Coerce an author-supplied magnitude into the decimal grammar, or raise.

    Accepts a string already in the grammar (returned unchanged -- the author's significant
    figures survive), an ``int``, or a ``Decimal``. It deliberately does **not** accept a
    ``float``: converting one here would silently invent digits the author never wrote, which
    is the precise failure the string form exists to prevent. Callers holding a float have to
    say what precision they mean, which is what ADR-022's shortest-round-trip rule is for.
    """
    if isinstance(value, bool):
        raise ValueError("a bool is not a magnitude")
    if isinstance(value, str):
        if not DECIMAL_RE.match(value):
            raise ValueError(
                f"magnitude {value!r} is outside the decimal grammar (ADR-001 rule 2): "
                f"no leading '+', no leading zeros, no bare '5.' or '.5', lowercase 'e', "
                f"mandatory exponent sign"
            )
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("magnitude must be finite (ADR-001 rule 3)")
        text = format(value, "f") if value.as_tuple().exponent >= -30 else str(value)
        if not DECIMAL_RE.match(text):
            raise ValueError(f"Decimal {value!r} does not render into the decimal grammar")
        return text
    if isinstance(value, float):
        # ValueError, not TypeError: Pydantic wraps ValueError into ValidationError, so every
        # magnitude refusal reaches a caller as one exception type rather than two.
        raise ValueError(
            "a float is not an acceptable magnitude: it would invent significant figures the "
            "author did not write. Pass a string in the decimal grammar, an int, or a Decimal "
            "(ADR-001 rule 2)."
        )
    raise ValueError(f"cannot interpret {type(value).__name__} as a magnitude")


class FrozenModel(BaseModel):
    """Base for every hashed schema object: immutable, and unknown fields are errors.

    ``extra="forbid"`` is not tidiness. A document carrying a field we do not understand would
    hash to something stable while meaning something we did not validate, which is exactly the
    kind of quiet disagreement content addressing is supposed to make impossible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class Quantity(FrozenModel):
    """A physical quantity: a decimal-string magnitude and a unit symbol.

    Equality and hashing are string equality on the magnitude, so significant figures are
    preserved and are part of identity.
    """

    magnitude: str
    unit: str  # astropy-parseable symbol; "1" for dimensionless (ADR-008)

    @field_validator("magnitude", mode="before")
    @classmethod
    def _check_magnitude(cls, v: Any) -> str:
        return normalize_decimal(v)

    @field_validator("unit")
    @classmethod
    def _check_unit(cls, v: str) -> str:
        if v == "" or v.strip() != v:
            raise ValueError("unit must be a non-empty symbol with no surrounding whitespace")
        return v

    def as_decimal(self) -> Decimal:
        """The magnitude as an exact ``Decimal``.

        For validation and comparison. The numeric core works in SI float64 (ADR-008); the
        conversion boundary lives in ``farsight.units``, not here, because this package is a
        leaf and may not import a unit library.
        """
        return Decimal(self.magnitude)

    def __str__(self) -> str:
        return f"{self.magnitude} {self.unit}"


class IntervalQ(FrozenModel):
    """A closed interval of a physical quantity, used for admissible ranges and bounds."""

    lower: Quantity
    upper: Quantity

    @model_validator(mode="after")
    def _check_ordered(self) -> "IntervalQ":
        if self.lower.unit != self.upper.unit:
            raise ValueError(
                f"interval bounds carry different units: {self.lower.unit!r} and "
                f"{self.upper.unit!r}. Convert at the boundary before constructing the interval."
            )
        if self.lower.as_decimal() > self.upper.as_decimal():
            raise ValueError(f"interval lower bound {self.lower} exceeds upper bound {self.upper}")
        return self


class TimeSpanQ(FrozenModel):
    """A span of coordinate time, as two epochs.

    Epochs are the concern of ADR-015 and land with the time module; this carries them as
    opaque decimal-string quantities so that ``ValidityEnvelope`` can exist before then.
    """

    start: Quantity
    end: Quantity

    @model_validator(mode="after")
    def _check_ordered(self) -> "TimeSpanQ":
        if self.start.as_decimal() > self.end.as_decimal():
            raise ValueError("time span starts after it ends")
        return self


class ValidityEnvelope(FrozenModel):
    """Where a belief or a model is entitled to be believed.

    ADR-004 attaches this to a ``Belief``; ADR-026 attaches the same type to a
    ``ModelVersion``. The split between the two halves is deliberate and is the whole design:
    ``ranges`` is mechanical, and is what fires silently in the middle of a ten-thousand-run
    campaign where no human is looking; ``conditions`` and ``not_validated_for`` are prose,
    because most of what makes a model trustworthy is not expressible as an interval and
    pretending otherwise would be worse than admitting it.

    An excursion is recorded, never blocking (ADR-026 decision 3). Extrapolation is legitimate
    and constant in this domain; the product's position is only that it must never happen
    invisibly.
    """

    conditions: list[str] = Field(default_factory=list)
    ranges: dict[str, IntervalQ] = Field(default_factory=dict)
    time_span: TimeSpanQ | None = None
    not_validated_for: list[str] = Field(default_factory=list)

    @field_validator("conditions", "not_validated_for")
    @classmethod
    def _check_prose(cls, v: list[str]) -> list[str]:
        for line in v:
            if not line.strip():
                raise ValueError("an envelope condition may not be blank")
            if len(line) > 400:
                raise ValueError(
                    "an envelope condition is one sentence a reviewer can check; "
                    f"{len(line)} characters is a paragraph"
                )
        return v


Ref = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{64}$",
        description=(
            "A bare lowercase 64-hex content address. Accepts only digests, never aliases, "
            "so a mutable name cannot syntactically appear inside a frozen document "
            "(ADR-001 rule 7)."
        ),
    ),
]
