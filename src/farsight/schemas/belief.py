"""The Belief union: how FarSight represents what it knows, suspects, and does not know.

ADR-004. This is the scientific heart of the product, and the design goal is narrow and
unusual: **make the dishonest operation impossible to write, rather than discouraged.**

The mechanism is an asymmetric API on a five-member discriminated union.

  * ``Deterministic`` and ``Aleatory`` expose ``sample(rng)``.
  * ``EpistemicInterval`` and ``EpistemicSet`` expose only ``enumerate_outer(plan)``.
  * ``Unknown`` exposes neither and cannot be sampled at all.

There is no method named ``to_distribution`` anywhere in this codebase, and no code path turns
an interval into a probability. Converting epistemic uncertainty into a distribution is a
judgement a human makes and signs (``EpistemicCollapse``), which taints every downstream
verdict; it is not something a sampler does at 3 a.m. inside a ten-thousand-run campaign.

The distinction between ``EpistemicInterval`` and ``Unknown`` is worth stating because it is
easy to lose: an interval is a *knowledge claim* about where a value lies, while an ``Unknown``
carrying a sweep declaration is an *admission* that we have no measurement and are scanning a
bracket we chose. The second keeps its `unknown` identity in the register even after it
acquires a numeric bracket, and is stamped NOT FITTED in the evidence package.
"""

from __future__ import annotations

import datetime as _dt
from typing import Annotated, Any, Literal, Union

from pydantic import Field, field_validator, model_validator

from farsight.schemas.common import (
    FrozenModel,
    IntervalQ,
    Quantity,
    Ref,
    SEGMENT_RE,
    ValidityEnvelope,
)

__all__ = [
    "PedigreeLevel",
    "Pedigree",
    "SamplingScope",
    "PerGroup",
    "Distribution",
    "SweepDeclaration",
    "Deterministic",
    "Aleatory",
    "EpistemicInterval",
    "EpistemicSet",
    "Unknown",
    "Belief",
    "EpistemicCollapse",
    "is_epistemic",
    "PERMITTED_FAMILIES",
]

# ADR-022 decision 1: a closed family list, because FarSight implements every transformation
# from Philox raw words to a drawn value in its own source. A sixth family requires an
# inverse-CDF implementation and an accuracy suite -- a decision, not a feature.
PERMITTED_FAMILIES = frozenset(
    {"uniform", "normal", "truncated_normal", "lognormal", "rayleigh"}
)

PedigreeLevel = Literal[
    "measured_flight",
    "measured_ground_test",
    "published_design",
    "derived_analysis",
    "expert_judgment",
    "speculative",
]


class Pedigree(FrozenModel):
    """Where a belief came from, and who decided that.

    Mandatory on every belief. A parameter without provenance does not become a default -- it
    becomes an ``Unknown`` (ADR-001 rule 6, AT-6). ``speculative`` is the only level that may
    carry no sources, and it is the honest label for a number somebody made up to see what
    would happen.
    """

    level: PedigreeLevel
    sources: list[Ref] = Field(default_factory=list)
    assessor: str
    assessed_on: _dt.date

    @model_validator(mode="after")
    def _sources_required(self) -> "Pedigree":
        if self.level != "speculative" and not self.sources:
            raise ValueError(
                f"pedigree level {self.level!r} claims provenance and must cite at least one "
                f"source; use level 'speculative' for a value with none"
            )
        if not self.assessor.strip():
            raise ValueError("pedigree requires a named assessor")
        return self


class PerGroup(FrozenModel):
    """Draw once per member of a declared scenario enumeration (ADR-027)."""

    per_group: str

    @field_validator("per_group")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not SEGMENT_RE.match(v) or len(v) > 32:
            raise ValueError(f"enumeration name {v!r} is outside the segment grammar")
        return v


# ADR-027 retires `per_pass`: it had no referent, since no record defined how a scenario
# declares a pass, and it put comms-mission vocabulary in the bottom of the schema stack.
SamplingScope = Union[Literal["per_run", "per_experiment"], PerGroup]


class Distribution(FrozenModel):
    """An aleatory distribution: a permitted family and its parameters.

    ``params`` accepts ``Quantity | EpistemicInterval | EpistemicSet`` and nothing else. Two
    rejections carry the design:

      * an ``Aleatory`` hyperparameter would be a hierarchical model, needing marginalization
        semantics we are not building -- explicit decomposition is more honest;
      * an ``Unknown`` hyperparameter has no bracket to scan, so there is nothing to enumerate.

    An epistemic hyperparameter is the flagship pattern, not an edge case: a Rayleigh jitter
    whose sigma is an interval spanning a lab measurement and a qualitative published bound is
    exactly how the DSOC pointing term is represented.
    """

    family: str
    params: dict[str, Union[Quantity, "EpistemicInterval", "EpistemicSet"]]

    @field_validator("family")
    @classmethod
    def _check_family(cls, v: str) -> str:
        if v not in PERMITTED_FAMILIES:
            raise ValueError(
                f"distribution family {v!r} is not in the permitted set "
                f"{sorted(PERMITTED_FAMILIES)}. Adding one requires an inverse-CDF "
                f"implementation and an accuracy suite (ADR-022), not a string."
            )
        return v

    def is_resolved(self) -> bool:
        """True when every parameter is a concrete ``Quantity``."""
        return all(isinstance(p, Quantity) for p in self.params.values())

    def unresolved_params(self) -> list[str]:
        """Names of parameters still carrying an epistemic coordinate, sorted."""
        return sorted(k for k, v in self.params.items() if not isinstance(v, Quantity))


class SweepDeclaration(FrozenModel):
    """An explicit scan over a bracket we chose, for a value we do not know.

    The points are authored, not derived. That is the honesty: an ``Unknown`` with a sweep is
    saying "we have no measurement, and here is the bracket we are scanning", which is a
    different statement from an ``EpistemicInterval``'s "we believe the value lies here".
    """

    outer_axis: bool = True
    points: list[Quantity]

    @field_validator("points")
    @classmethod
    def _check_points(cls, v: list[Quantity]) -> list[Quantity]:
        if len(v) < 2:
            raise ValueError("a sweep declares at least two points; one point is a value")
        units = {q.unit for q in v}
        if len(units) > 1:
            raise ValueError(f"sweep points carry mixed units: {sorted(units)}")
        return v


class _BeliefBase(FrozenModel):
    pedigree: Pedigree
    validity: ValidityEnvelope = Field(default_factory=ValidityEnvelope)


class Deterministic(_BeliefBase):
    """A value we claim to know."""

    kind: Literal["deterministic"] = "deterministic"
    value: Quantity

    def sample(self, rng: Any) -> float:  # noqa: ARG002 - signature parity with Aleatory
        """The value in its declared unit, as float64.

        Takes ``rng`` it does not use, so that the planner can call ``sample`` uniformly across
        the two samplable kinds. SI conversion happens at the ``farsight.units`` boundary, not
        here: this package is a leaf and may not import a unit library (ADR-008, ADR-013).
        """
        return float(self.value.as_decimal())


class Aleatory(_BeliefBase):
    """A quantity that genuinely varies, with a distribution we can defend.

    An instance whose distribution still carries an epistemic hyperparameter is *unresolved*:
    ``sample`` refuses it, and ``at(point)`` returns the resolved copy. ``RunSpec``
    construction rejects anything unresolved, which is the schema half of AT-6 -- a run spec is
    fully pinned by construction, so there is no code path in which an outer coordinate is
    still floating when a number gets drawn.
    """

    kind: Literal["aleatory"] = "aleatory"
    distribution: Distribution
    sampling_scope: SamplingScope = "per_run"
    correlation_group: str | None = None

    def is_resolved(self) -> bool:
        return self.distribution.is_resolved()

    def at(self, point: dict[str, Quantity]) -> "Aleatory":
        """Return a copy with epistemic hyperparameters substituted from an outer point.

        ``point`` maps parameter name to the concrete quantity that outer coordinate takes.
        Substituting a parameter the distribution does not declare is an error rather than a
        no-op, because it means the caller and the belief disagree about what is being scanned.
        """
        unresolved = set(self.distribution.unresolved_params())
        extra = set(point) - set(self.distribution.params)
        if extra:
            raise KeyError(
                f"outer point names parameters this distribution does not have: {sorted(extra)}"
            )
        missing = unresolved - set(point)
        if missing:
            raise ValueError(
                f"outer point does not resolve every epistemic hyperparameter; still open: "
                f"{sorted(missing)}"
            )
        new_params: dict[str, Any] = dict(self.distribution.params)
        for name, value in point.items():
            new_params[name] = value
        return self.model_copy(
            update={"distribution": self.distribution.model_copy(update={"params": new_params})}
        )

    def sample(self, rng: Any) -> float:
        """Draw one value. Resolved instances only.

        The transformation from bits to a value is FarSight's own (ADR-022) and lands with the
        sampler module; this method is the contract the planner calls, and its refusal of an
        unresolved instance is the part that matters now.
        """
        if not self.is_resolved():
            raise ValueError(
                f"cannot sample an unresolved Aleatory: parameters "
                f"{self.distribution.unresolved_params()} still carry epistemic coordinates. "
                f"Call at(point) first; the outer scan resolves them (ADR-004)."
            )
        raise NotImplementedError(
            "the inverse-CDF samplers land with ADR-022's sampling module in weeks 3-5"
        )


class _EpistemicBase(_BeliefBase):
    """Shared behaviour of the two epistemic kinds.

    Note what is absent and must stay absent: no ``sample``, and no ``to_distribution``. The
    only way out of an epistemic kind is ``enumerate_outer``, which produces scan coordinates,
    or a human-authorized ``EpistemicCollapse`` that taints everything downstream.
    """

    rationale: str

    @field_validator("rationale")
    @classmethod
    def _check_rationale(cls, v: str) -> str:
        if len(v.strip()) < 40:
            raise ValueError(
                "an epistemic bound needs a rationale of at least 40 characters saying where "
                "the bound came from; this text lands in the evidence package and is what a "
                "reviewer reads"
            )
        return v


class EpistemicInterval(_EpistemicBase):
    """We believe the value lies in this range, and we cannot say more."""

    kind: Literal["epistemic_interval"] = "epistemic_interval"
    lower: Quantity
    upper: Quantity

    @model_validator(mode="after")
    def _check_bounds(self) -> "EpistemicInterval":
        IntervalQ(lower=self.lower, upper=self.upper)  # reuse the ordering and unit checks
        return self

    def enumerate_outer(self, plan: Any = None) -> list[Quantity]:
        """Scan coordinates for the outer loop: the interval vertices.

        The outer loop consumes no randomness at all (ADR-005), which is what makes a run
        addressable as (epistemic point, aleatory draw index). Latin-hypercube interior points
        come from the sampling plan and land with ADR-022's design module.
        """
        return [self.lower, self.upper]


class EpistemicSet(_EpistemicBase):
    """One of these, and we do not know which -- enumerated, never weighted.

    The moment members carry weights, a percentile can be computed over them, and the
    laundering path this whole type system exists to close is reopened. A firmware defect is
    present in both units or in neither; a model family is right or it is not.
    """

    kind: Literal["epistemic_set"] = "epistemic_set"
    members: list[Quantity] | list[Ref]

    @field_validator("members")
    @classmethod
    def _check_members(cls, v: list[Any]) -> list[Any]:
        if len(v) < 2:
            raise ValueError("an epistemic set enumerates at least two alternatives")
        kinds = {isinstance(m, Quantity) for m in v}
        if len(kinds) > 1:
            raise ValueError(
                "an epistemic set is all quantities or all model-version references, never a "
                "mixture: the two enumerate different things"
            )
        if all(isinstance(m, Quantity) for m in v):
            units = {m.unit for m in v}
            if len(units) > 1:
                raise ValueError(f"epistemic set members carry mixed units: {sorted(units)}")
        return v

    def enumerate_outer(self, plan: Any = None) -> list[Any]:
        """Every member. Exhaustive by construction -- there is no sampling mode."""
        return list(self.members)


class Unknown(_BeliefBase):
    """We do not know this, and we are not going to pretend otherwise.

    Cannot be sampled, and has no distribution. At freeze it must resolve to a declared sweep
    or a named bounding assumption, or the design is refused naming the path -- which is how
    "unknown" stays a stated fact rather than becoming a silent default.
    """

    kind: Literal["unknown"] = "unknown"
    what_is_missing: str
    sweep_declaration: SweepDeclaration | None = None
    bounding_assumption_ref: Ref | None = None

    @field_validator("what_is_missing")
    @classmethod
    def _check_statement(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError(
                "state what is missing in a sentence: this text is what lands in the unknown "
                "register and is what an external reviewer reads first"
            )
        return v

    def freeze_ready(self) -> bool:
        """True when this ``Unknown`` may enter a frozen design (ADR-004, ADR-001 rule 6)."""
        return self.sweep_declaration is not None or self.bounding_assumption_ref is not None


Belief = Annotated[
    Union[Deterministic, Aleatory, EpistemicInterval, EpistemicSet, Unknown],
    Field(discriminator="kind"),
]

# Distribution.params refers to the epistemic classes by name; resolve the forward references
# now that they exist.
Distribution.model_rebuild()


def is_epistemic(belief: Any) -> bool:
    """True for the kinds that may never be sampled."""
    return isinstance(belief, (EpistemicInterval, EpistemicSet, Unknown))


class EpistemicCollapse(FrozenModel):
    """A human-authorized conversion of an epistemic belief into a distribution.

    The escape valve, and it is deliberately expensive: content-addressed, naming a human, and
    tainting every downstream verdict via ``contains_epistemic_collapse``. ``scope`` is what
    keeps the evidence lane clean -- an ``exploration_only`` collapse may drive a sensitivity
    screen but may never feed an evidence-grade verdict.

    An honesty system that makes daily engineering painful gets forked around; this is the lane
    that stops that happening, and its taint is what stops the lane from leaking.
    """

    original_belief_ref: Ref
    chosen_distribution: Distribution
    justification: str
    authorized_by: str
    authorized_on: _dt.date
    scope: Literal["exploration_only", "evidence"]

    @field_validator("justification")
    @classmethod
    def _check_justification(cls, v: str) -> str:
        if len(v.strip()) < 60:
            raise ValueError(
                "a collapse converts ignorance into a probability and needs a justification "
                "of at least 60 characters saying on what basis; it is read at review"
            )
        return v

    @field_validator("authorized_by")
    @classmethod
    def _check_human(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a collapse is authorized by a named human, never by a process")
        return v
