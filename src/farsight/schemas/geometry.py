"""Epochs, durations, frames and aberration corrections. ADR-015.

Four conventions live here, and each one is a number-mover that would otherwise be a constant
near the top of a geometry module.

**An epoch is TDB seconds past J2000, and nothing else.** ADR-015 decision 1. UTC is an input and
a display spelling, never a stored scale, because UTC is not uniform: ``23:59:60`` is a legal UTC
time with no counterpart in any uniform scale, and an epoch authored today for a date two years
out converts against a leapsecond table that may gain an entry before that date arrives. For a
content-addressed system that last property is the fatal one -- the bytes of the frozen document
would not change while its *meaning* did.

**A duration is not an epoch.** ADR-015 decision 2. Both are ``Quantity{unit: "s"}`` and nothing
but a type stops one being assigned to the other, so they are two types.

**Aberration correction is mandatory, with no default anywhere in the code path.** ADR-015
decision 6. A default would be invisible in the evidence package: the number changes, the hash
changes, and nothing says why. At the flagship's ranges the light time is of order twenty minutes
and the target moves a long way during it, so the difference between a geometric separation and
the distance photons actually travelled is orders of magnitude larger than the acceptance
tolerance. That is a silent wrong number, not a crash.

**Frames are named per request and never inherited from an adapter default.** ADR-015 decision 5.

What this module cannot check, stated rather than implied: whether the declared frame and
aberration are the *right* ones for the observable a channel claims to represent. That is a claim
about physics stated in prose, and ADR-015 Enforcement 8 makes it review-checklist item TIME-1
rather than pretending a validator settles it. What is mechanized here is that a convention was
declared and that it is internally consistent with the ``quantity_class``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator

from farsight.schemas.common import FrozenModel, Quantity, Ref

__all__ = [
    "ABERRATION_MEMBERS",
    "EARTH_FIXED_FRAME",
    "INERTIAL_FRAME",
    "Aberration",
    "Duration",
    "Epoch",
    "GeometryRequest",
    "QuantityClass",
]

# ADR-015 decision 6, reception cases then transmission cases. This module is the ONLY place in
# `src/farsight/` where these spellings may appear as string literals; an AST lint enforces that,
# which is what mechanically prevents a convention from being re-introduced as a constant
# somewhere in an adapter.
Aberration = Literal[
    "NONE", "LT", "LT+S", "CN", "CN+S",
    "XLT", "XLT+S", "XCN", "XCN+S",
]

ABERRATION_MEMBERS: tuple[str, ...] = (
    "NONE", "LT", "LT+S", "CN", "CN+S",
    "XLT", "XLT+S", "XCN", "XCN+S",
)

# ADR-015 decision 5. `ITRF93` rather than `IAU_EARTH`: the latter is a low-precision rotation
# model, the former is realized by a binary Earth-orientation PCK, which is how Earth orientation
# enters FarSight -- as a hash-pinned kernel rather than an ambient table.
INERTIAL_FRAME = "J2000"
EARTH_FIXED_FRAME = "ITRF93"

QuantityClass = Literal["range", "light_time", "direction", "state"]

# The unit spelling an epoch and a duration must carry. `schemas` is a leaf package (import
# contract `schemas_is_leaf`), so it cannot reach `farsight.units` to ask astropy whether a symbol
# is dimensionally a time. It therefore enforces the spelling ADR-015 names rather than the
# dimension -- narrower than a dimensional check, and deliberately so: `Quantity{unit: "min"}`
# would be dimensionally fine and is still not what the record says an epoch is.
SECONDS = "s"


class Epoch(FrozenModel):
    """TDB seconds past J2000. ADR-015 decision 1.

    The magnitude is a decimal string under ADR-001 rule 2, like every other physical quantity in
    the system, because an epoch **is** a physical quantity. A carve-out here would be the first
    crack in a rule whose whole value is that it has none.
    """

    scale: Literal["TDB"]
    seconds_past_j2000: Quantity

    @field_validator("seconds_past_j2000")
    @classmethod
    def _check_unit(cls, v: Quantity) -> Quantity:
        if v.unit != SECONDS:
            raise ValueError(
                f"an Epoch carries seconds past J2000, so its unit is {SECONDS!r}, not {v.unit!r} "
                f"(ADR-015 decision 1)"
            )
        return v


class Duration(FrozenModel):
    """An interval on the TDB timeline. ADR-015 decision 2.

    ``anchor`` of ``None`` means the ``ScenarioTemplate``'s ``epoch_start``. A ``Duration`` added
    to an ``Epoch`` is a TDB-timeline interval and not proper time; ADR-015 records the TDB-vs-TT
    rate difference as periodic and bounded far below any tolerance in this MVP, with the exact
    bound marked UNVERIFIED in that record and not restated as settled here.
    """

    seconds: Quantity
    anchor: Ref | None

    @field_validator("seconds")
    @classmethod
    def _check_unit(cls, v: Quantity) -> Quantity:
        if v.unit != SECONDS:
            raise ValueError(
                f"a Duration is an interval in {SECONDS!r}, not {v.unit!r} (ADR-015 decision 2)"
            )
        return v


class GeometryRequest(FrozenModel):
    """What to compute, against which conventions. ADR-015 decision 6.

    Every field is required. There is no default for ``aberration``, for ``frame``, or for
    anything else, and omission is a validation error rather than a fallback -- the same
    discipline AT-6 imposes on unknown parameters, applied to conventions.
    """

    target: str        # NAIF name or integer id as a string
    observer: str
    frame: str         # "J2000" | "ITRF93" | "<STATION>_TOPO"
    aberration: Aberration
    quantity_class: QuantityClass
    epochs: Ref        # the sample grid's digest (ADR-020 decision 4)
    rationale: str | None

    @field_validator("target", "observer", "frame")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or v.strip() != v:
            raise ValueError(
                "target, observer and frame are SPICE names and carry no surrounding whitespace; "
                "an empty one is an omission wearing a value (ADR-015 decision 6)"
            )
        return v

    @model_validator(mode="after")
    def _convention_matches_quantity(self) -> GeometryRequest:
        """ADR-015 decision 6's consistency rule.

        Stellar aberration displaces an apparent *direction* and does not change a range. So a
        ``+S`` member on a range or a light time is not a stricter choice, it is a statement that
        does not typecheck against the physics -- and a `direction` computed without it is a
        geometric direction rather than an apparent one, which is admissible only when the author
        says why.
        """
        stellar = self.aberration.endswith("+S")

        if self.quantity_class in ("range", "light_time") and stellar:
            raise ValueError(
                f"aberration {self.aberration!r} carries a stellar-aberration term, which "
                f"displaces an apparent direction and does not change a "
                f"{self.quantity_class}. ADR-015 decision 6 rejects this at construction rather "
                f"than letting it produce a number that looks more careful than the one without "
                f"it. Use the reception or transmission converged-Newtonian case without '+S'."
            )

        if self.quantity_class == "direction" and not stellar and not self.rationale:
            raise ValueError(
                f"aberration {self.aberration!r} has no stellar-aberration term, so this is a "
                f"geometric direction rather than an apparent one. ADR-015 decision 6 admits that "
                f"only with a stated reason: set `rationale` to say why the geometric direction "
                f"is the observable this request represents."
            )

        return self
