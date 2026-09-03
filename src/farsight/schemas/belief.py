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
from collections.abc import Iterable
from typing import Annotated, Any, Literal, Union

from pydantic import Field, field_validator, model_validator

from farsight.schemas.common import (
    FrozenModel,
    IntervalQ,
    MAX_SEGMENT_CHARS,
    MIN_JUSTIFICATION_CHARS,
    MIN_RATIONALE_CHARS,
    MIN_UNKNOWN_STATEMENT_CHARS,
    Quantity,
    Ref,
    SEGMENT_RE,
    ValidityEnvelope,
    VersionedDocument,
    validate_path,
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
    "CollapseScope",
    "EpistemicCollapse",
    "MACHINE_AUTHORIZER_PREFIX",
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
        if not SEGMENT_RE.match(v) or len(v) > MAX_SEGMENT_CHARS:
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
        # An outer point resolves epistemic coordinates. It does not get to rewrite a
        # hyperparameter the author already pinned: that would let a scan silently replace a
        # stated value with one nobody declared, and the substitution would be invisible in the
        # resulting document because the result is a concrete Quantity either way.
        already_pinned = sorted(set(point) & (set(self.distribution.params) - unresolved))
        if already_pinned:
            raise ValueError(
                f"outer point would overwrite hyperparameters that are already concrete: "
                f"{already_pinned}. An outer point resolves epistemic coordinates only; "
                f"changing a pinned value is an edit to the belief, not a scan of it."
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


def _refuse_unimplemented_plan(plan: Any) -> None:
    """Refuse a sampling plan rather than ignoring it (ADR-022's design module is unbuilt).

    The sibling discipline is ``Aleatory.sample``, which raises for its unbuilt half. Two
    unimplemented paths should fail the same way; the one that under-delivers silently is the
    dangerous one, because nothing downstream can tell a truncated scan from a complete one.
    """
    if plan is not None:
        raise NotImplementedError(
            "outer-scan plans (Latin-hypercube interior points, vertex caps, screening ranks) "
            "land with ADR-022's design module in weeks 3-5. Until then this returns vertices "
            "only, and silently honouring a plan by ignoring it would narrow the envelope."
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
        if len(v.strip()) < MIN_RATIONALE_CHARS:
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
        addressable as (epistemic point, aleatory draw index).

        A supplied ``plan`` is **refused**, not ignored. Latin-hypercube interior points come
        from ADR-022's design module, which does not exist yet; returning only the two vertices
        while accepting a 24-point plan would silently under-sample the outer scan. That error
        makes the reported envelope *narrower*, which makes AT-5's width criterion easier to
        pass -- an unbuilt path must not fail in the direction that flatters the result.
        """
        _refuse_unimplemented_plan(plan)
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
        """Every member. Exhaustive by construction -- there is no sampling mode.

        A ``plan`` is refused for the same reason as on the interval kind: an enumeration that
        quietly returned a subset would narrow the envelope without saying so.
        """
        _refuse_unimplemented_plan(plan)
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
        if len(v.strip()) < MIN_UNKNOWN_STATEMENT_CHARS:
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


# Reserved prefix for an authorizer that is a rule rather than a person. ADR-004 permits an
# `exploratory` experiment to auto-collapse intervals to their midpoint for sensitivity
# screening, "recording a machine-authored collapse with lane: exploratory". Without a way to
# say in the document that the authorizer was a process, that permission and the rule that a
# collapse is signed by a named human contradict each other, and one of them gets quietly
# dropped. The prefix makes the distinction expressible, and the lane validator below makes
# machine authorship structurally unable to reach the evidence lane.
MACHINE_AUTHORIZER_PREFIX = "auto:"


class CollapseScope(FrozenModel):
    """Where a collapse applies: one experiment, and the exact parameter paths it covers.

    This is the field the taint machinery is built on. ADR-004 requires ``verify`` to
    **recompute** the taint by intersecting each collapse's scope with the parameter paths a
    result actually depends on, and to treat a stored ``contains_epistemic_collapse: false``
    that the recomputation contradicts as an integrity failure rather than a discrepancy to
    report. That intersection needs a set of paths to intersect. A scope reduced to a lane label
    leaves nothing to compute against, and the taint degrades into a stored boolean -- the
    "advisory flag" outcome ADR-004's Option 2 considered and rejected.

    Matching is **exact, not by subtree**. Subtree semantics would be more convenient to author
    and would silently extend an existing signed judgement over parameters added to that subtree
    later, which is authorization by accident. A collapse covering several parameters names them
    all; the cost is a longer list in a document a human signs anyway.
    """

    experiment_hash: Ref
    parameter_paths: list[str]

    @field_validator("parameter_paths")
    @classmethod
    def _check_paths(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError(
                "a collapse scope names at least one parameter path. An empty list reads as "
                "either 'everything' or 'nothing' depending on the reader, and the taint "
                "recomputation would silently take the second."
            )
        for path in v:
            validate_path(path)
        if len(set(v)) != len(v):
            duplicates = sorted({p for p in v if v.count(p) > 1})
            raise ValueError(f"collapse scope repeats parameter paths: {duplicates}")
        if v != sorted(v):
            raise ValueError(
                "collapse scope paths must be byte-wise sorted, so that two scopes covering the "
                "same parameters are the same document and hash alike (ADR-017 decision 5)"
            )
        return v

    def covers(self, paths: Iterable[str]) -> frozenset[str]:
        """The paths in ``paths`` this scope covers -- the intersection ADR-004's `verify` needs.

        Returning the overlap rather than a bool is deliberate: when a stored taint disagrees
        with the recomputation, the failure has to say *which* parameters caused it, or an
        auditor is left re-deriving it by hand.
        """
        return frozenset(self.parameter_paths) & frozenset(paths)


class EpistemicCollapse(VersionedDocument):
    """A human-authorized conversion of an epistemic belief into a distribution.

    The escape valve, and it is deliberately expensive: content-addressed, naming a human,
    reproducing the original belief verbatim, and tainting every downstream verdict via
    ``contains_epistemic_collapse``. The ``lane`` is what keeps the evidence lane clean -- an
    ``exploratory`` collapse may drive a sensitivity screen but may never feed an evidence-grade
    verdict -- and the ``scope`` is what lets ``verify`` prove that separation held rather than
    take a stored flag's word for it.

    An honesty system that makes daily engineering painful gets forked around; this is the lane
    that stops that happening, and its taint is what stops the lane from leaking.

    Two deliberate deviations from ADR-004's sketch, recorded here rather than left as drift:

      * the record lists ``collapse_id: ContentHash``, which cannot be a field -- a document
        containing its own hash is circular. The content address *is* the identity (ADR-001);
        ``collapse_id`` is instead a short authored name in the segment grammar, matching
        ``claim_id`` and ``metric_id`` elsewhere in the corpus, so that a register entry and a
        review comment can refer to a collapse without quoting 64 hex characters.
      * ``authorizer`` is typed ``str``, because ADR-004 names a ``HumanIdentity`` that no
        record defines. It becomes that type when the freeze protocol's identity type lands;
        the field name is already right, so that change is a type change and not a rename.

    Both are recorded in ``docs/adr/IMPLEMENTATION_DEVIATIONS.md`` (DEV-1, DEV-2) rather than
    silently absorbed, because ADR-000 forbids editing an accepted record and a departure that
    lives only in a docstring is one refactor away from living nowhere.
    """

    collapse_id: str
    original_belief: Belief
    chosen: Union[Deterministic, Aleatory]
    justification: str
    authorizer: str
    authorized_on: _dt.datetime
    scope: CollapseScope
    lane: Literal["evidence", "exploratory"]
    expires_on: _dt.date | None = None

    @field_validator("collapse_id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not SEGMENT_RE.match(v) or len(v) > MAX_SEGMENT_CHARS:
            raise ValueError(f"collapse_id {v!r} is outside the segment grammar (ADR-017 rule 3)")
        return v

    @field_validator("original_belief")
    @classmethod
    def _check_original_is_epistemic(cls, v: Any) -> Any:
        if not is_epistemic(v):
            raise ValueError(
                f"a collapse converts an epistemic belief into a distribution; "
                f"{type(v).__name__} is already samplable, so there is nothing to collapse and "
                f"the taint this record carries would be a false alarm"
            )
        return v

    @field_validator("justification")
    @classmethod
    def _check_justification(cls, v: str) -> str:
        if len(v.strip()) < MIN_JUSTIFICATION_CHARS:
            raise ValueError(
                f"a collapse converts ignorance into a probability and needs a justification "
                f"of at least {MIN_JUSTIFICATION_CHARS} characters saying on what basis; it is "
                f"what a reviewer reads when deciding whether to trust the number"
            )
        return v

    @field_validator("authorized_on")
    @classmethod
    def _check_aware(cls, v: _dt.datetime) -> _dt.datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError(
                "authorized_on must carry a UTC offset. A naive timestamp in a hashed document "
                "means something different to every reader, and this one records when a human "
                "signed off."
            )
        return v

    @model_validator(mode="after")
    def _check_authorization(self) -> "EpistemicCollapse":
        authorizer = self.authorizer.strip()
        if not authorizer:
            raise ValueError("a collapse is authorized by a named human, never by nobody")
        machine = authorizer.startswith(MACHINE_AUTHORIZER_PREFIX)
        if machine and self.lane != "exploratory":
            raise ValueError(
                f"authorizer {self.authorizer!r} is a rule, not a person, and a machine-authored "
                f"collapse is confined to the exploratory lane (ADR-004). An evidence-grade "
                f"collapse is a judgement somebody signs."
            )
        if self.expires_on is not None and self.expires_on <= self.authorized_on.date():
            raise ValueError(
                f"expires_on {self.expires_on} is not after the authorization date "
                f"{self.authorized_on.date()}; a collapse that expires on or before the day it "
                f"was signed was never valid"
            )
        return self

    def is_expired(self, on: _dt.date) -> bool:
        """True when this collapse's authorization has lapsed as of ``on``.

        Expiry is the answer to the collapse justified by "pending the Q3 measurement": without
        it, a stopgap judgement outlives the circumstance that justified it and nothing ever
        says so. A lapsed collapse is not deleted -- the package that used it stays valid and
        auditable -- it simply may not authorize a new evidence-grade result.
        """
        return self.expires_on is not None and on > self.expires_on
