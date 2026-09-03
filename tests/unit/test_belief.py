"""The Belief union and the honesty guarantees (ADR-004, ADR-001).

The tests that matter most here are the *absence* tests: that there is no way to turn an
epistemic belief into a probability, and no way to sample one. They assert a property of the
type system rather than of a function, which is unusual, and it is the point -- if these ever
start passing for the wrong reason (because someone added a helpful method), the product's
central claim has quietly stopped being true.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from farsight.hashing.canonical import canonicalize, content_hash
from farsight.schemas.belief import (
    Aleatory,
    CollapseScope,
    Deterministic,
    Distribution,
    EpistemicCollapse,
    EpistemicInterval,
    EpistemicSet,
    Pedigree,
    PerGroup,
    SweepDeclaration,
    Unknown,
    is_epistemic,
)
from farsight.schemas.common import Quantity, ValidityEnvelope, VersionedDocument

HEX = "a" * 64
RATIONALE = (
    "Lab measurement gives 0.16 urad; flight publications state a qualitative sub-microradian "
    "bound only. The upper edge reads that bound as 1.0 urad. NOT FITTED to any achieved rate."
)


def ped(level: str = "published_design") -> Pedigree:
    return Pedigree(
        level=level,
        sources=[] if level == "speculative" else [HEX],
        assessor="operator:test",
        assessed_on=dt.date(2026, 8, 28),
    )


def q(mag: str, unit: str = "m") -> Quantity:
    return Quantity(magnitude=mag, unit=unit)


# --------------------------------------------------------------------------------------
# The asymmetry: what each kind can and cannot do
# --------------------------------------------------------------------------------------


def test_epistemic_kinds_have_no_sample_method():
    interval = EpistemicInterval(lower=q("0.16"), upper=q("1.0"), rationale=RATIONALE, pedigree=ped())
    eset = EpistemicSet(members=[q("1"), q("2")], rationale=RATIONALE, pedigree=ped())
    unknown = Unknown(
        what_is_missing="Ground-receiver optical-train throughput is not published anywhere.",
        pedigree=ped("speculative"),
    )
    for belief in (interval, eset, unknown):
        assert not hasattr(belief, "sample"), f"{type(belief).__name__} must not be samplable"


def test_no_to_distribution_anywhere_on_any_belief_kind():
    # The named method the ADR forbids by name. Checked on every kind, because the danger is
    # that someone adds it to just one as a convenience.
    kinds = [
        Deterministic(value=q("0.22"), pedigree=ped()),
        Aleatory(
            distribution=Distribution(family="rayleigh", params={"sigma": q("0.16", "urad")}),
            pedigree=ped(),
        ),
        EpistemicInterval(lower=q("0.16"), upper=q("1.0"), rationale=RATIONALE, pedigree=ped()),
        EpistemicSet(members=[q("1"), q("2")], rationale=RATIONALE, pedigree=ped()),
        Unknown(
            what_is_missing="Ground-receiver optical-train throughput is not published anywhere.",
            pedigree=ped("speculative"),
        ),
    ]
    for belief in kinds:
        assert not hasattr(belief, "to_distribution")


def test_unknown_exposes_neither_sampling_nor_enumeration():
    unknown = Unknown(
        what_is_missing="Ground-receiver optical-train throughput is not published anywhere.",
        pedigree=ped("speculative"),
    )
    assert not hasattr(unknown, "sample")
    assert not hasattr(unknown, "enumerate_outer")


def test_epistemic_kinds_enumerate_instead():
    interval = EpistemicInterval(lower=q("0.16"), upper=q("1.0"), rationale=RATIONALE, pedigree=ped())
    assert interval.enumerate_outer() == [q("0.16"), q("1.0")]
    eset = EpistemicSet(members=[q("1"), q("2"), q("3")], rationale=RATIONALE, pedigree=ped())
    assert len(eset.enumerate_outer()) == 3


def test_deterministic_samples_its_own_value():
    d = Deterministic(value=q("0.22"), pedigree=ped())
    assert d.sample(rng=None) == 0.22


def test_is_epistemic_covers_exactly_the_unsamplable_kinds():
    assert is_epistemic(EpistemicInterval(lower=q("0"), upper=q("1"), rationale=RATIONALE, pedigree=ped()))
    assert is_epistemic(EpistemicSet(members=[q("1"), q("2")], rationale=RATIONALE, pedigree=ped()))
    assert is_epistemic(Unknown(what_is_missing="x" * 25, pedigree=ped("speculative")))
    assert not is_epistemic(Deterministic(value=q("1"), pedigree=ped()))


# --------------------------------------------------------------------------------------
# The flagship pattern: an aleatory distribution with an epistemic hyperparameter
# --------------------------------------------------------------------------------------


def test_aleatory_with_epistemic_hyperparameter_is_unresolved_and_refuses_to_sample():
    jitter = Aleatory(
        distribution=Distribution(
            family="rayleigh",
            params={
                "sigma": EpistemicInterval(
                    lower=q("0.16", "urad"),
                    upper=q("1.0", "urad"),
                    rationale=RATIONALE,
                    pedigree=ped(),
                )
            },
        ),
        pedigree=ped(),
    )
    assert not jitter.is_resolved()
    assert jitter.distribution.unresolved_params() == ["sigma"]
    with pytest.raises(ValueError, match="unresolved"):
        jitter.sample(rng=None)


def test_at_point_resolves_the_hyperparameter():
    jitter = Aleatory(
        distribution=Distribution(
            family="rayleigh",
            params={
                "sigma": EpistemicInterval(
                    lower=q("0.16", "urad"), upper=q("1.0", "urad"),
                    rationale=RATIONALE, pedigree=ped(),
                )
            },
        ),
        pedigree=ped(),
    )
    resolved = jitter.at({"sigma": q("0.16", "urad")})
    assert resolved.is_resolved()
    assert jitter is not resolved and not jitter.is_resolved()  # the original is untouched


def test_at_point_refuses_to_leave_a_hyperparameter_open():
    a = Aleatory(
        distribution=Distribution(
            family="normal",
            params={
                "mu": EpistemicInterval(lower=q("0"), upper=q("1"), rationale=RATIONALE, pedigree=ped()),
                "sigma": EpistemicInterval(lower=q("1"), upper=q("2"), rationale=RATIONALE, pedigree=ped()),
            },
        ),
        pedigree=ped(),
    )
    with pytest.raises(ValueError, match="still open"):
        a.at({"mu": q("0.5")})


def test_at_point_refuses_unknown_parameter_names():
    a = Aleatory(
        distribution=Distribution(family="normal", params={"mu": q("0"), "sigma": q("1")}),
        pedigree=ped(),
    )
    with pytest.raises(KeyError, match="does not have"):
        a.at({"nonexistent": q("1")})


def test_at_point_refuses_to_overwrite_an_already_pinned_hyperparameter():
    """An outer point resolves epistemic coordinates. Rewriting a value the author pinned is an
    edit to the belief, and it is invisible afterwards: the result is a concrete Quantity either
    way, so nothing downstream can tell a resolved coordinate from a substituted one."""
    jitter = Aleatory(
        distribution=Distribution(family="rayleigh", params={"sigma": q("0.16", "urad")}),
        pedigree=ped(),
    )
    with pytest.raises(ValueError, match="already concrete"):
        jitter.at({"sigma": q("99", "urad")})

    # Mixed case: one open coordinate, one pinned. The open one alone is fine; naming the
    # pinned one alongside it is still refused.
    mixed = Aleatory(
        distribution=Distribution(
            family="normal",
            params={
                "mu": EpistemicInterval(
                    lower=q("0"), upper=q("1"), rationale=RATIONALE, pedigree=ped()
                ),
                "sigma": q("1"),
            },
        ),
        pedigree=ped(),
    )
    assert mixed.at({"mu": q("0.5")}).is_resolved()
    with pytest.raises(ValueError, match="already concrete"):
        mixed.at({"mu": q("0.5"), "sigma": q("99")})


def test_at_point_cannot_smuggle_an_invalid_value_past_the_validators():
    """`at` builds a new belief by copy, and a copy is a construction. Before FrozenModel
    validated copies, this route accepted an Aleatory hyperparameter that direct construction
    refuses -- two doors into the same object with different locks."""
    jitter = Aleatory(
        distribution=Distribution(
            family="rayleigh",
            params={
                "sigma": EpistemicInterval(
                    lower=q("0.16", "urad"), upper=q("1.0", "urad"),
                    rationale=RATIONALE, pedigree=ped(),
                )
            },
        ),
        pedigree=ped(),
    )
    inner = Aleatory(
        distribution=Distribution(family="normal", params={"mu": q("0"), "sigma": q("1")}),
        pedigree=ped(),
    )
    with pytest.raises(ValidationError):
        jitter.at({"sigma": inner})


def test_enumerate_outer_refuses_a_plan_it_cannot_honour():
    """ADR-022's design module is unbuilt. Accepting a plan and returning the two vertices
    anyway would report a *narrower* envelope, which makes AT-5's 6 dB width criterion easier
    to pass -- an unbuilt path failing in the flattering direction."""
    interval = EpistemicInterval(
        lower=q("0.16", "urad"), upper=q("1.0", "urad"), rationale=RATIONALE, pedigree=ped()
    )
    assert interval.enumerate_outer() == [q("0.16", "urad"), q("1.0", "urad")]
    with pytest.raises(NotImplementedError, match="ADR-022"):
        interval.enumerate_outer({"sampler": "lhs", "n": 24})

    members = EpistemicSet(
        members=[q("1"), q("2")], rationale=RATIONALE, pedigree=ped()
    )
    assert len(members.enumerate_outer()) == 2
    with pytest.raises(NotImplementedError, match="ADR-022"):
        members.enumerate_outer({"sampler": "lhs", "n": 24})


def test_aleatory_hyperparameter_rejected_at_construction():
    # A hierarchical model needs marginalization semantics we are not building; explicit
    # decomposition is the honest alternative (ADR-004).
    inner = Aleatory(
        distribution=Distribution(family="normal", params={"mu": q("0"), "sigma": q("1")}),
        pedigree=ped(),
    )
    with pytest.raises(ValidationError):
        Distribution(family="rayleigh", params={"sigma": inner})


def test_unknown_hyperparameter_rejected_at_construction():
    # An Unknown has no bracket to scan, so there is nothing for the outer loop to enumerate.
    u = Unknown(what_is_missing="No measurement exists for this term at all.", pedigree=ped("speculative"))
    with pytest.raises(ValidationError):
        Distribution(family="rayleigh", params={"sigma": u})


def test_distribution_family_must_be_permitted():
    with pytest.raises(ValidationError, match="permitted set"):
        Distribution(family="weibull", params={"k": q("1")})


# --------------------------------------------------------------------------------------
# Refusals that keep "unknown" from becoming a default
# --------------------------------------------------------------------------------------


def test_unknown_needs_a_sweep_or_a_bounding_assumption_to_be_freeze_ready():
    bare = Unknown(
        what_is_missing="Ground-receiver optical-train throughput is not published anywhere.",
        pedigree=ped("speculative"),
    )
    assert not bare.freeze_ready()

    swept = bare.model_copy(
        update={
            "sweep_declaration": SweepDeclaration(
                points=[q("0.3", "1"), q("0.5", "1"), q("0.8", "1")]
            )
        }
    )
    assert swept.freeze_ready()
    assert bare.model_copy(update={"bounding_assumption_ref": HEX}).freeze_ready()


def test_epistemic_set_is_never_weighted():
    # There is no weights field, and there must never be one: the moment members carry weights
    # a percentile can be computed and the laundering path reopens.
    eset = EpistemicSet(members=[q("1"), q("2")], rationale=RATIONALE, pedigree=ped())
    assert "weights" not in type(eset).model_fields
    with pytest.raises(ValidationError):
        EpistemicSet(members=[q("1"), q("2")], weights=[0.7, 0.3], rationale=RATIONALE, pedigree=ped())


def test_epistemic_set_needs_at_least_two_alternatives():
    with pytest.raises(ValidationError, match="at least two"):
        EpistemicSet(members=[q("1")], rationale=RATIONALE, pedigree=ped())


def test_epistemic_bounds_need_a_real_rationale():
    with pytest.raises(ValidationError, match="rationale"):
        EpistemicInterval(lower=q("0"), upper=q("1"), rationale="unknown", pedigree=ped())


def test_epistemic_interval_bounds_must_be_ordered_and_share_a_unit():
    with pytest.raises(ValidationError):
        EpistemicInterval(lower=q("2"), upper=q("1"), rationale=RATIONALE, pedigree=ped())
    with pytest.raises(ValidationError):
        EpistemicInterval(lower=q("0", "m"), upper=q("1", "km"), rationale=RATIONALE, pedigree=ped())


def test_pedigree_requires_sources_unless_speculative():
    with pytest.raises(ValidationError, match="must cite at least one source"):
        Pedigree(level="published_design", sources=[], assessor="x", assessed_on=dt.date(2026, 1, 1))
    Pedigree(level="speculative", sources=[], assessor="x", assessed_on=dt.date(2026, 1, 1))


JUSTIFICATION = (
    "Sobol screening only; no basis exists for any interior weighting of this interval, and the "
    "result may not support an evidence-grade verdict. Recorded so the screening rank is "
    "reproducible and so the taint reaches every result computed from it."
)


def collapse(**over):
    """A valid collapse, overridable field by field."""
    base = dict(
        collapse_id="dsoc_jitter_screen",
        original_belief=EpistemicInterval(
            lower=q("0.16", "urad"), upper=q("1.0", "urad"), rationale=RATIONALE, pedigree=ped()
        ),
        chosen=Deterministic(value=q("0.58", "urad"), pedigree=ped()),
        justification=JUSTIFICATION,
        authorizer="operator:jh",
        authorized_on=dt.datetime(2026, 8, 28, 14, 30, tzinfo=dt.timezone.utc),
        scope=CollapseScope(
            experiment_hash=HEX, parameter_paths=["spacecraft.dsoc.pointing.jitter_sigma"]
        ),
        lane="evidence",
    )
    return EpistemicCollapse(**{**base, **over})


def test_collapse_requires_a_named_human_and_a_real_justification():
    collapse()
    with pytest.raises(ValidationError):
        collapse(justification="because")
    with pytest.raises(ValidationError, match="never by nobody"):
        collapse(authorizer="  ")


def test_collapse_scope_carries_paths_so_taint_can_be_recomputed():
    """ADR-004 line 160: `verify` recomputes taint by intersecting scope with the paths a
    result depends on. A scope reduced to a lane label leaves nothing to intersect, and the
    taint degrades into the advisory boolean ADR-004's Option 2 rejected."""
    c = collapse()
    depends_on = ["ground.palomar.throughput", "spacecraft.dsoc.pointing.jitter_sigma"]
    assert c.scope.covers(depends_on) == {"spacecraft.dsoc.pointing.jitter_sigma"}
    assert c.scope.covers(["ground.palomar.throughput"]) == frozenset()

    # Exact match, never subtree: a scope must not silently extend over parameters added under
    # a covered node later, because that is authorization by accident.
    assert c.scope.covers(["spacecraft.dsoc.pointing.jitter_sigma.tail"]) == frozenset()

    with pytest.raises(ValidationError, match="at least one parameter path"):
        CollapseScope(experiment_hash=HEX, parameter_paths=[])
    # Required, not merely validated when supplied. A default would be exempt from the
    # validator above unless `validate_default` is set, and a scope covering nothing is the
    # shape a taint recomputation reads as "this collapse touched no result".
    with pytest.raises(ValidationError):
        CollapseScope(experiment_hash=HEX)
    with pytest.raises(ValidationError, match="sorted"):
        CollapseScope(experiment_hash=HEX, parameter_paths=["b.two", "a.one"])
    with pytest.raises(ValidationError, match="repeats"):
        CollapseScope(experiment_hash=HEX, parameter_paths=["a.one", "a.one"])
    with pytest.raises(ValidationError, match="ADR-017 grammar"):
        CollapseScope(experiment_hash=HEX, parameter_paths=["Ground.Palomar"])


def test_machine_authored_collapse_cannot_reach_the_evidence_lane():
    """ADR-004 permits an auto-collapse to the midpoint for screening, in the exploratory lane
    only. Without the reserved prefix, that permission and "signed by a named human"
    contradict each other, and the contradiction resolves in whichever direction nobody is
    watching."""
    collapse(authorizer="auto:oat_screening_midpoint", lane="exploratory")
    with pytest.raises(ValidationError, match="a rule, not a person"):
        collapse(authorizer="auto:oat_screening_midpoint", lane="evidence")


def test_collapse_refuses_a_belief_that_is_already_samplable():
    with pytest.raises(ValidationError, match="nothing to collapse"):
        collapse(original_belief=Deterministic(value=q("0.58", "urad"), pedigree=ped()))


def test_collapse_reproduces_the_original_belief_verbatim():
    """ADR-004 line 150: the original is carried verbatim, hashed, and reproduced in the
    package -- not cited by reference. A reference would resolve only against a store the
    auditor may not have, and `verify` is specified to need no extras."""
    c = collapse()
    assert isinstance(c.original_belief, EpistemicInterval)
    assert c.original_belief.lower == q("0.16", "urad")
    assert "original_belief_ref" not in c.model_dump()


def test_collapse_timestamp_must_be_unambiguous():
    with pytest.raises(ValidationError, match="UTC offset"):
        collapse(authorized_on=dt.datetime(2026, 8, 28, 14, 30))


def test_collapse_expiry_is_after_authorization_and_lapses():
    with pytest.raises(ValidationError, match="never valid"):
        collapse(expires_on=dt.date(2026, 8, 28))
    c = collapse(expires_on=dt.date(2026, 12, 31))
    assert not c.is_expired(dt.date(2026, 12, 31))
    assert c.is_expired(dt.date(2027, 1, 1))
    assert not collapse().is_expired(dt.date(2099, 1, 1))


def test_collapse_carries_a_schema_version_in_band():
    """ADR-005 makes `verify` exit nonzero on a schema version it does not recognise, which it
    can only do if the version travels in the bytes."""
    c = collapse()
    assert isinstance(c, VersionedDocument)
    assert c.model_dump()["schema_version"] == 1
    assert '"schema_version"' in canonicalize(c.model_dump(mode="json"))


# --------------------------------------------------------------------------------------
# Interaction with identity (ADR-001)
# --------------------------------------------------------------------------------------


def test_beliefs_serialize_without_any_json_float():
    a = Aleatory(
        distribution=Distribution(family="rayleigh", params={"sigma": q("0.16", "urad")}),
        sampling_scope=PerGroup(per_group="passes"),
        pedigree=ped(),
    )
    # Would raise CanonicalizationError if any field serialized as a float.
    out = canonicalize(a.model_dump(mode="json"))
    assert "0.16" in out
    assert content_hash(a.model_dump(mode="json"))


def test_significant_figures_are_part_of_identity():
    # "0.220" and "0.22" are different engineering claims, so they are different objects.
    a = Deterministic(value=q("0.22"), pedigree=ped())
    b = Deterministic(value=q("0.220"), pedigree=ped())
    assert a != b
    assert content_hash(a.model_dump(mode="json")) != content_hash(b.model_dump(mode="json"))


def test_field_order_does_not_affect_a_belief_hash():
    kw = dict(value=q("0.22"), pedigree=ped(), validity=ValidityEnvelope(conditions=["a", "b"]))
    a = Deterministic(**kw)
    b = Deterministic(validity=kw["validity"], pedigree=kw["pedigree"], value=kw["value"])
    assert content_hash(a.model_dump(mode="json")) == content_hash(b.model_dump(mode="json"))


def test_beliefs_are_frozen():
    d = Deterministic(value=q("0.22"), pedigree=ped())
    with pytest.raises(ValidationError):
        d.value = q("0.23")


def test_model_copy_cannot_mint_an_unvalidated_identity():
    """The guarantee is not "attributes cannot be assigned" -- it is "a content address is the
    address of a validated document". Pydantic's `model_copy(update=...)` runs no validators,
    so before FrozenModel overrode it this produced a Deterministic whose `value` was a bare
    string, and `content_hash` addressed it happily.

    The test above passes with or without that hole, which is exactly why this one exists.
    """
    d = Deterministic(value=q("0.22"), pedigree=ped())
    with pytest.raises(ValidationError):
        d.model_copy(update={"value": "not-a-quantity"})
    with pytest.raises(ValidationError):
        d.model_copy(update={"no_such_field": 1})

    good = d.model_copy(update={"value": q("0.23")})
    assert good.value == q("0.23")
    assert content_hash(good.model_dump(mode="json")) != content_hash(d.model_dump(mode="json"))


def test_unknown_fields_are_errors_not_extras():
    with pytest.raises(ValidationError):
        Deterministic(value=q("0.22"), pedigree=ped(), typo_field=1)
