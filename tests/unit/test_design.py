"""Claim identity, pre-registration, and the honest limit of containment (finding G3).

The most important test in this module is the one asserting what containment does NOT prove.
A pre-registration mechanism that overstates its guarantee is worse than none, because a reader
trusts it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from farsight.hashing.canonical import canonicalize, content_hash
from farsight.schemas.common import Quantity, VersionedDocument
from farsight.schemas.design import (
    NEGATED,
    Claim,
    ClaimResult,
    canonical_falsifier_condition,
    falsifier_restates,
    unregistered_claim_refs,
)

CRITERION = "a" * 64
REFERENT = "b" * 64
AGGREGATE = "c" * 64
OTHER = "d" * 64

METRIC = "dsoc.rate_ladder_step_delta"
TARGET = Quantity(magnitude="-1", unit="step")
FALSIFIER = (
    "any frozen point whose achieved rate exceeds the predicted supportable envelope by more "
    "than one CCSDS 142.0-B-1 ladder step, i.e. dsoc.rate_ladder_step_delta < -1"
)


def claim(**over) -> Claim:
    base = dict(
        claim_id="dsoc_envelope",
        sentence=(
            "At each frozen DSOC pass epoch, the achieved downlink rate is less than or equal to "
            "the predicted supportable-rate envelope, within one ladder step of its lower edge."
        ),
        falsifier=FALSIFIER,
        scope_conditions=["frozen public pass points only", "no per-pass atmospheric data used"],
        criterion_ref=CRITERION,
        referent_refs=[REFERENT],
        run_set="dsoc_link",
        tier="B",
        cited_packages=[],
        supersedes=None,
        revision_reason=None,
    )
    return Claim(**{**base, **over})


# --------------------------------------------------------------------------------------
# Identity: the 0% half of the finding
# --------------------------------------------------------------------------------------


def test_a_claim_is_a_content_addressed_document():
    """claim_statement had ~70% of a Claim as fields and 0% as identity: nothing could reference
    it, contradict it, or supersede it."""
    c = claim()
    assert isinstance(c, VersionedDocument)
    assert c.model_dump()["schema_version"] == 1
    assert content_hash(c.model_dump(mode="json"))


def test_claims_are_distinguishable_and_supersedable():
    a = claim()
    b = claim(sentence=claim().sentence + " Measured at X-band only.")
    assert content_hash(a.model_dump(mode="json")) != content_hash(b.model_dump(mode="json"))

    revised = claim(supersedes=OTHER, revision_reason="scope_narrowed")
    assert revised.supersedes == OTHER
    with pytest.raises(ValidationError, match="travel together"):
        claim(supersedes=OTHER)
    with pytest.raises(ValidationError, match="travel together"):
        claim(revision_reason="scope_narrowed")


def test_a_claim_cannot_be_withdrawn_by_revision():
    """A registered claim cannot be withdrawn from a frozen design -- the design is frozen -- and
    a later design that omits it does not supersede anything. Offering the member would name an
    operation with no implementation."""
    assert "withdrawn" not in getattr(
        Claim.model_fields["revision_reason"].annotation, "__args__", (None,)
    )[0].__args__
    with pytest.raises(ValidationError):
        claim(supersedes=OTHER, revision_reason="withdrawn")


# --------------------------------------------------------------------------------------
# The design/package split: every field on exactly one side
# --------------------------------------------------------------------------------------


def test_execution_facts_cannot_be_frozen_into_a_claim():
    """The test for whether a field belongs on a Claim is whether it is knowable before a run
    executes. ADR-001 fails freeze on a reference to a draft object, so a verdict could not be
    filled at freeze; and it forecloses in-place annotation, so it could not be filled later."""
    for execution_fact in ("verdict", "partial", "contains_epistemic_collapse", "aggregate_ref"):
        assert execution_fact not in Claim.model_fields
        with pytest.raises(ValidationError):
            claim(**{execution_fact: "pass"})


def test_a_result_restates_nothing_from_its_claim():
    """ADR-007 refuses two hash-verified copies of one datum by name: they create a precedence
    question, and any answer is worse than not having the second copy."""
    assert set(ClaimResult.model_fields) == {"claim_ref", "verdict", "aggregate_ref"}
    result = ClaimResult(claim_ref=content_hash(claim().model_dump(mode="json")),
                         verdict="indeterminate", aggregate_ref=AGGREGATE)
    assert result.verdict == "indeterminate"


def test_the_verdict_is_three_valued():
    """`indeterminate` is a result, not an error: a band straddling the threshold has not been
    decided, and saying so is the honest output."""
    for verdict in ("pass", "fail", "indeterminate"):
        ClaimResult(claim_ref=CRITERION, verdict=verdict, aggregate_ref=AGGREGATE)
    with pytest.raises(ValidationError):
        ClaimResult(claim_ref=CRITERION, verdict="inconclusive", aggregate_ref=AGGREGATE)


def test_the_run_set_is_frozen_with_the_claim():
    """Closing HARKing while letting the author choose WHICH RUNS support the claim after seeing
    them is the same problem wearing a different hat: post-hoc sample selection."""
    assert "run_set" in Claim.model_fields
    assert "run_set" not in ClaimResult.model_fields


def test_a_claim_commits_to_a_tier():
    """ADR-006: every claim carries exactly one. A pre-registered claim committing to no tier has
    not committed to the thing that bounds what the verifier may assert."""
    assert claim().tier == "B"
    with pytest.raises(ValidationError):
        claim(tier="D")


# --------------------------------------------------------------------------------------
# The falsifier correspondence: generated, then contained
# --------------------------------------------------------------------------------------


def test_the_canonical_condition_matches_the_records_own_example():
    """ADR-007's worked falsifier already ends "i.e. dsoc.rate_ladder_step_delta < -1", so this
    generates a convention the corpus writes by hand rather than imposing a new one."""
    assert canonical_falsifier_condition(METRIC, ">=", TARGET) == f"{METRIC} < -1"
    assert claim().falsifier_matches(METRIC, ">=", TARGET)


def test_the_falsifier_must_negate_the_rule_not_repeat_it():
    """A falsifier restating the rule rather than its negation names the condition under which
    the claim HOLDS, which is not a falsifier at all."""
    restates_rule = claim(falsifier=f"holds when {METRIC} >= -1")
    assert not restates_rule.falsifier_matches(METRIC, ">=", TARGET)


def test_the_falsifier_check_refuses_the_wrong_metric_direction_and_magnitude():
    c = claim()
    assert not c.falsifier_matches("other.metric", ">=", TARGET)          # wrong metric
    assert not c.falsifier_matches(METRIC, "<=", TARGET)                  # wrong direction
    assert not c.falsifier_matches(METRIC, ">=", Quantity(magnitude="-2", unit="step"))


def test_negation_is_total_over_the_comparator_set():
    """Closed and total, so the correspondence is computed rather than matched against prose."""
    for comparator, negated in NEGATED.items():
        assert NEGATED[negated] == comparator      # negation is an involution
    with pytest.raises(ValueError, match="unknown comparator"):
        canonical_falsifier_condition(METRIC, "=~", TARGET)


def test_a_claim_states_a_sentence_and_a_falsifier():
    for blank in ("", "   "):
        with pytest.raises(ValidationError, match="not a claim; it is marketing"):
            claim(sentence=blank)
        with pytest.raises(ValidationError, match="not a claim; it is marketing"):
            claim(falsifier=blank)


def test_there_is_no_length_floor_on_the_falsifier():
    """A floor stands in for sharpness and gets the sign wrong: the bare condition is a better
    falsifier than sixty characters of hedging, and a minimum length would refuse the first and
    admit the second."""
    terse = claim(falsifier=f"{METRIC} < -1")
    assert terse.falsifier_matches(METRIC, ">=", TARGET)


# --------------------------------------------------------------------------------------
# The lane rule, and the limit of what containment proves
# --------------------------------------------------------------------------------------


def test_a_claim_absent_from_the_design_is_reported_as_unregistered():
    design = [CRITERION, REFERENT]
    assert unregistered_claim_refs(design, [CRITERION]) == frozenset()
    assert unregistered_claim_refs(design, [CRITERION, OTHER]) == {OTHER}
    assert unregistered_claim_refs([], [OTHER]) == {OTHER}


def test_containment_is_tamper_evidence_not_proof_of_order():
    """The finding that changed this design. ADR-005 seeds every stream from
    `SeedSequence(entropy=root_seed, spawn_key=(run_index, stream_id))` -- experiment_hash is NOT
    an input -- so re-freezing a design with a new claim changes every spec_hash while leaving
    every drawn value and channel byte identical. Post-hoc insertion costs a re-PLAN, which is a
    pure derivation, not a re-RUN.

    This test pins the docstring rather than the code, because the failure it guards against is a
    future reader believing the mechanism proves more than it does.
    """
    import farsight.schemas.design as design_module

    doc = design_module.__doc__ or ""
    assert "proof that the claim was written before the results were seen" in doc
    assert "tamper-evidence" in doc
    assert "external witness" in doc
    # The specific mechanism, named so a reader can check the reasoning rather than trust it.
    assert "spawn_key=(run_index, stream_id)" in doc
    # And the function that computes it says the same thing where a caller will read it.
    assert "written afterwards" in (unregistered_claim_refs.__doc__ or "")


def test_a_claim_is_scored_against_something_external():
    """ADR-007: verify fails a package whose claim statement lacks a resolvable referent_ref. A
    claim with nothing external to be wrong against is a statement about our own arithmetic."""
    with pytest.raises(ValidationError, match="at least one Referent"):
        claim(referent_refs=[])


def test_references_are_sorted_and_unique():
    with pytest.raises(ValidationError, match="repeated reference"):
        claim(referent_refs=[REFERENT, REFERENT])
    with pytest.raises(ValidationError, match="sorted"):
        claim(cited_packages=[OTHER, CRITERION])


def test_cited_packages_closes_the_stated_capability():
    """Finding D2: ADR-007 says a claim may name other packages' root hashes as cited evidence,
    and claim_statement had no such field."""
    assert claim(cited_packages=[CRITERION, OTHER]).cited_packages == [CRITERION, OTHER]


def test_a_claim_canonicalizes_without_a_float():
    out = canonicalize(claim().model_dump(mode="json"))
    assert METRIC in out
    assert content_hash(claim().model_dump(mode="json"))
