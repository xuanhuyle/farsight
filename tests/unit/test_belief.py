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
from farsight.schemas.common import Quantity, ValidityEnvelope

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


def test_collapse_requires_a_named_human_and_a_real_justification():
    good = dict(
        original_belief_ref=HEX,
        chosen_distribution=Distribution(family="uniform", params={"lower": q("0"), "upper": q("1")}),
        justification=(
            "Sobol screening only; no basis exists for any interior weighting of this interval, "
            "and the result may not support an evidence-grade verdict."
        ),
        authorized_by="operator:jh",
        authorized_on=dt.date(2026, 8, 28),
        scope="exploration_only",
    )
    EpistemicCollapse(**good)
    with pytest.raises(ValidationError):
        EpistemicCollapse(**{**good, "justification": "because"})
    with pytest.raises(ValidationError):
        EpistemicCollapse(**{**good, "authorized_by": "  "})


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


def test_unknown_fields_are_errors_not_extras():
    with pytest.raises(ValidationError):
        Deterministic(value=q("0.22"), pedigree=ped(), typo_field=1)
