"""Claims: what a package asserts, frozen before the runs that test it.

Finding G3. ``claim_statement`` is a ten-field sub-object of ``manifest.json`` (ADR-007 decision
3). It is roughly 70% of a Claim as *fields* and 0% as *identity*: no ``claim_id``, no
``schema_version``, no content hash, so nothing can reference it, contradict it or supersede it;
one package supports exactly one claim; and it names its criterion and referents but not its
verdict, run set or aggregate, so the tie from a claim down to its supporting runs is directory
co-membership rather than a reference.

The deepest gap is that the claim is built at **package** time, after results are seen. ADR-021
decision 7 already lets FarSight pre-register what it will *measure against*
(``ReferentCommitment``); nothing lets it pre-register what it will *claim*. For a platform whose
thesis is falsification, that is backwards.

So a :class:`Claim` is a content-addressed object belonging to the **design**, frozen before any
run exists, and a :class:`ClaimResult` is the package-side entry that adds only what execution
can know.

**What containment does and does not prove -- stated first, because the tempting claim is false.**

A claim frozen into ``ExperimentDesign`` sits inside ``design_hash``, hence inside
``experiment_hash``, hence inside the address of every run. It is therefore true that *a claim
absent from the design is visibly unregistered*, and that adding one to a frozen design changes
the identity of every run in the campaign. That is tamper-evidence, and it is worth having.

It is **not** proof that the claim was written before the results were seen, and this module does
not say that it is. ADR-005 derives every bit stream from ``SeedSequence(entropy=root_seed,
spawn_key=(run_index, stream_id))`` -- ``experiment_hash`` is not an input. So re-freezing a
design with a new claim changes every ``spec_hash`` while leaving every drawn value and every
channel byte **identical**: the campaign does not have to be re-run, only re-planned, and
re-planning is a pure derivation. An author who ran first, looked, then wrote the claim and
re-froze produces a package that verifies.

What closes that gap is an **external witness**, and FarSight already has the pattern: plan §17
publishes hashed predictions before the paywalled per-pass data is purchased, and ADR-021's
``ReferentCommitment`` is the same move for referents. Pre-registration is *containment plus a
published digest*; containment alone is the tamper-evident half. A record that promised more
would be doing precisely what this product exists to prevent.

**The lane rule.** A conclusion nobody anticipated is legitimate and common -- and it is not a
pre-registered claim. Rather than invent a ``Finding`` type, the distinction falls out of the
containment fact: :func:`unregistered_claim_refs` reports the claims a package asserts that its
design does not contain. An exploratory package may carry them; an evidence-grade package may
not. That maps the existing ``evidence_grade`` split onto the confirmatory/exploratory
distinction in experimental science using machinery that already exists, and it deliberately does
**not** couple claim-*optionality* to the lane: making an exploratory package the one place a
result needs no claim at all would make the exploratory lane the cheapest legal home for a real
finding, which is the opposite of the intent.

**Not built here, and named rather than implied.** ``ExperimentDesign`` itself, so the containment
this module describes is asserted by a freeze validator that does not yet exist;
``AcceptanceCriterion`` (ADR-009), so :func:`falsifier_restates` takes the criterion's parts
rather than resolving its digest; and the link from a confirmatory design back to the exploratory
work that prompted it, which ADR-007 line 126 says must **not** be a hashed back-link -- "a hashed
back-link would make a design's identity depend on its own search history" -- and therefore
belongs in the unhashed provenance half of the object file.
"""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import field_validator, model_validator

from farsight.schemas.common import (
    FrozenModel,
    MAX_SEGMENT_CHARS,
    Quantity,
    Ref,
    SEGMENT_RE,
    VersionedDocument,
)

__all__ = [
    "Verdict",
    "Comparator",
    "NEGATED",
    "ReproducibilityTier",
    "ClaimRevisionReason",
    "Claim",
    "ClaimResult",
    "canonical_falsifier_condition",
    "falsifier_restates",
    "unregistered_claim_refs",
]

# ADR-009's three-valued verdict. `indeterminate` is a result, not an error: a band that
# straddles the threshold has not been decided, and saying so is the honest output.
Verdict = Literal["pass", "fail", "indeterminate"]

Comparator = Literal["<", "<=", ">", ">=", "==", "!="]

# The falsifier is the exact restatement of the rule (ADR-009), and a rule's restatement as a
# falsifiable condition is its negation: a criterion testing `step_delta >= -1` is falsified by
# `step_delta < -1`. Closed and total over the comparator set, so the correspondence is computed
# rather than matched against prose.
NEGATED: dict[str, str] = {
    "<": ">=",
    "<=": ">",
    ">": "<=",
    ">=": "<",
    "==": "!=",
    "!=": "==",
}

ReproducibilityTier = Literal["A", "B", "C"]

# No `withdrawn` member. A registered claim cannot be withdrawn from a frozen design -- the
# design is frozen -- and a later design that omits it does not supersede anything, it simply
# does not contain it. Withdrawing a *shipped conclusion* is a package-level act: a new package
# naming the superseded root hash. Offering `withdrawn` here would name an operation with no
# implementation, which is how a field becomes a lie.
ClaimRevisionReason = Literal[
    "sentence_clarified",
    "falsifier_corrected",
    "scope_narrowed",
    "criterion_revised",
    "referent_added",
]


def canonical_falsifier_condition(
    metric_display: str, comparator: str, target: Quantity
) -> str:
    """The machine-readable condition a falsifier must contain, generated from the rule.

    ADR-007's own worked example already ends this way -- "... by more than one ladder step,
    **i.e. dsoc.rate_ladder_step_delta < -1**" -- so this generates the convention the corpus
    already writes by hand rather than imposing a new one.

    Generation-and-containment, not parsing. The check never reads the author's prose: it
    computes what the restatement must say and asks whether the sentence contains it. That
    refuses a falsifier naming the wrong metric, the wrong direction or the wrong magnitude,
    and it says nothing at all about whether the surrounding sentence is honest.
    """
    if comparator not in NEGATED:
        raise ValueError(f"unknown comparator {comparator!r}; expected one of {sorted(NEGATED)}")
    return f"{metric_display} {NEGATED[comparator]} {target.magnitude}"


def falsifier_restates(
    falsifier: str, metric_display: str, comparator: str, target: Quantity
) -> bool:
    """True when ``falsifier`` contains the rule's negation, generated from the rule's parts.

    Takes the criterion's parts rather than an ``AcceptanceCriterion`` because ADR-009's object
    does not exist yet and because a schema-layer function may not resolve a digest. The freeze
    validator that holds both objects is what pairs them; this is the half that can be written
    today and tested.

    **What it cannot do.** It cannot tell whether the rule is the right rule, whether the
    sentence around the condition is honest, or whether a claim is weak enough to be unfalsifiable
    in practice. That last one is the failure mode this whole mechanism is most likely to produce
    -- a claim written so cautiously it cannot fail -- and no schema check catches it. It is a
    review-checklist residue, not a validator.
    """
    return canonical_falsifier_condition(metric_display, comparator, target) in falsifier


class Claim(VersionedDocument):
    """A falsifiable assertion, frozen with the design that will test it.

    Every field here is knowable before a single run executes. That is the test for whether a
    field belongs on this object, and it is why ``verdict``, ``partial`` and
    ``contains_epistemic_collapse`` are absent: each is a fact about an execution that has not
    happened. ADR-001 rule 6 fails freeze on a reference to a draft object, so a ``verdict`` field
    could not be filled at freeze; and ADR-001 forecloses in-place annotation of frozen objects,
    so it could not be filled afterwards either. Those facts live on :class:`ClaimResult`.

    ``run_set`` is on the claim rather than the result, and the reason is the whole point of
    pre-registering. A claim that fixes its sentence and its criterion but chooses *which runs
    support it* after seeing them has closed HARKing and left post-hoc sample selection wide
    open, which is the same problem wearing a different hat.

    ``tier`` likewise: ADR-006 says every claim carries exactly one, and a pre-registered claim
    that commits to no reproducibility tier has not committed to the thing that "bounds what the
    verifier may assert".
    """

    claim_id: str
    sentence: str
    falsifier: str
    scope_conditions: list[str]
    criterion_ref: Ref
    referent_refs: list[Ref]
    run_set: str
    tier: ReproducibilityTier
    cited_packages: list[Ref]
    supersedes: Ref | None
    revision_reason: ClaimRevisionReason | None

    @field_validator("claim_id", "run_set")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not SEGMENT_RE.match(v) or len(v) > MAX_SEGMENT_CHARS:
            raise ValueError(
                f"{v!r} is outside the segment grammar (ADR-017 rule 3). It is a label a human "
                f"says out loud; identity is the digest."
            )
        return v

    @field_validator("sentence", "falsifier")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        # Non-blank, and no length floor. A floor stands in for sharpness and gets the sign
        # wrong: "dsoc.rate_ladder_step_delta < -1" is a better falsifier than sixty characters
        # of hedging, and a minimum length would refuse the first and admit the second.
        if not v.strip():
            raise ValueError(
                "a claim states a sentence and the condition that would falsify it. "
                "'Achieved is close to predicted' is not a claim; it is marketing (ADR-007)."
            )
        return v

    @field_validator("scope_conditions")
    @classmethod
    def _check_scope(cls, v: list[str]) -> list[str]:
        for line in v:
            if not line.strip():
                raise ValueError("a scope condition may not be blank")
        return v

    @field_validator("referent_refs", "cited_packages")
    @classmethod
    def _sorted_unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError(f"repeated reference: {sorted({r for r in v if v.count(r) > 1})}")
        if v != sorted(v):
            raise ValueError(
                "references must be byte-wise sorted, so two claims citing the same things are "
                "the same document and hash alike"
            )
        return v

    @model_validator(mode="after")
    def _check(self) -> "Claim":
        if not self.referent_refs:
            raise ValueError(
                "a claim is scored against at least one Referent (ADR-007: verify fails a "
                "package whose claim statement lacks a resolvable referent_ref). A claim with "
                "nothing external to be wrong against is a statement about our own arithmetic."
            )
        if (self.supersedes is None) != (self.revision_reason is None):
            raise ValueError(
                "supersedes and revision_reason travel together: a superseded claim with no "
                "stated reason is an unexplained change to a conclusion somebody may have read"
            )
        return self

    def falsifier_matches(
        self, metric_display: str, comparator: str, target: Quantity
    ) -> bool:
        """Whether this claim's falsifier restates the criterion it names.

        ADR-009 says the falsifier "is the exact restatement of" the rule and ``verify`` today
        checks only that one is *present*. This is the check that can actually be computed, given
        the criterion's parts.
        """
        return falsifier_restates(self.falsifier, metric_display, comparator, target)


class ClaimResult(FrozenModel):
    """What execution learned about one registered claim.

    Carries **only** what could not be known at freeze. It deliberately restates nothing from the
    :class:`Claim` -- not the sentence, not the falsifier, not the scope conditions -- because
    ADR-007 refuses two hash-verified copies of one datum by name: "two hash-verified copies of
    the same data create a precedence question", and any answer to that question is worse than
    not having the second copy.

    ``aggregate_ref`` is the downward edge a reviewer most wants to walk: the tie from a claim to
    the runs supporting it, which today is directory co-membership.
    """

    claim_ref: Ref
    verdict: Verdict
    aggregate_ref: Ref


def unregistered_claim_refs(
    design_claim_refs: Iterable[str], asserted_claim_refs: Iterable[str]
) -> frozenset[str]:
    """Claims a package asserts that its frozen design does not contain.

    The lane computation. An evidence-grade package with a non-empty result here is asserting a
    conclusion its design never registered; an exploratory package may legitimately do so, which
    is what the exploratory lane is for.

    Set membership over digests, which is the strongest thing available and weaker than it looks:
    it establishes that a claim is *not part of the design these runs were addressed by*, not
    that it was written afterwards. See the module docstring on why containment is
    tamper-evidence rather than proof of order, and what an external witness adds.
    """
    return frozenset(asserted_claim_refs) - frozenset(design_claim_refs)
