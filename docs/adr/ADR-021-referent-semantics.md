# ADR-021 — Referent, ReferentPoint, and referent-comparison semantics
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §4 (knowledge plane: `Referent` and `ReferentPoint`), §13 (`inputs/reference_data/`, claim statement, audit path), §14 item 5 (a golden or referent number may never originate from our own code), §17 weeks 3-4 and 7-8, §18 AT-5 / AT-9 / AT-13, "Things we must get right" item 4
**Related ADRs:** ADR-000 (the escape-hatch tokens and the `review_signoffs` rows this record's checklist items land in), ADR-001 (a frozen document may reference only 64-hex digests, which is the constraint this record has to satisfy rather than route around), ADR-004 (a referent's stated uncertainty is a `Belief`, or the no-second-uncertainty-system guarantee has a hole at the comparison step), ADR-006 (a comparison is claimed at a named tier and happens at defined epochs), ADR-007 (the claim statement's `referent_refs`, `inputs/reference_data/`, and the closure rule that ships referent bytes), ADR-009 (metrics declare a referent slot and criteria score the resulting band; this record settles the reference form ADR-009 deferred), ADR-013 (`comparison` and `evidence` verify with zero engine extras), ADR-015 (the epoch representation a `ReferentPoint` carries and the timescale conversion it records), ADR-020 (the run's sample grid that a referent epoch must align to), ADR-023 (which run outcomes may participate in the run set a comparison is evaluated over)

## Context

The forcing question is what object holds the observed world. Plan §4 lists the `Referent` as the entity the rejected hierarchy was missing entirely, and the plan's own "Things we must get right" list puts it at item 4: the Referent as a first-class entity with claim semantics written into the package, because "achieved at or below supportable envelope" versus naive equality is the difference between falsification and theater. Both benchmarks land in weeks 3-4. The DSN RF anchor is the precision case, with a plus-or-minus 1 dB class tolerance and, per AT-13, a decided pass or fail and no unknowns bucket. The DSOC flagship is the honest-envelope case, scored against frozen public points that enter as cited, hash-pinned `DataArtifact`s under plan §14 item 5.

Four facts constrain the answer and none of them is optional.

The stated uncertainty on an observation is uncertainty, and ADR-004 already decided what uncertainty is. The DSN anchor's plus-or-minus 1 dB is a stated observational bound. If it enters as a bare tolerance number on a comparison, then at the exact moment the honesty type system first meets the outside world there is a second, untyped uncertainty representation in the codebase, and ADR-004's guarantee is false where it matters most. Worse, reading a bare plus-or-minus as a standard deviation is an epistemic-to-probabilistic conversion performed by whoever wrote the comparison, which is precisely the operation ADR-004 makes impossible everywhere else.

The plan's verified facts make the DSOC comparison one-sided and partly uninformative by construction: achieved rates are operationally chosen with unpublished margin, and the 267 Mbps points are hardware-capped. A point at a system ceiling cannot say anything about how tight the prediction is. If the package does not say which points can constrain the envelope and which cannot, AT-5 can be satisfied by a set of observations that could not have failed, and K6 ("everything inside a huge envelope, nothing learned") becomes unjudgeable from the artifact.

A referent point has an epoch and a run has a sample grid, and nothing in the set connects them. ADR-006 requires comparison at defined epochs, ADR-020 owns the grid, and no record says what happens when the referent's epoch falls between two samples.

And there is a hard collision with an accepted rule. ADR-009 writes `{"referent": "dsoc.achieved_points@v3", "field": "achieved_rate_bps"}` into a hashed metric definition. ADR-001 rule 7 admits only 64-hex digests inside a frozen document, so that line is, as written, syntactically impossible. ADR-009 explicitly deferred the reference form to this record and states that the metric registry cannot be frozen in week 3 until it is settled.

What breaks concretely if this is wrong: referent identity, its uncertainty representation and the comparison semantics all live inside metric definitions, criteria, claim statements and `inputs/reference_data/`, and all of those are package-permanent (§16 item 2). AT-9 asks the week-8 external auditor to check one referent point against its cited public source, which is an operation that has to be defined before it can be performed.

## Decision

**1. A `Referent` is an immutable, content-addressed knowledge-plane object that reads a hash-pinned artifact; it never computes one.**

```python
# src/farsight/schemas/knowledge.py -- ConfigDict(extra="forbid", frozen=True) throughout

class ReferentField(BaseModel):
    name: str                       # e.g. "achieved_rate_bps"
    unit: str                       # astropy-parseable symbol (ADR-008)
    description: str                # >= 40 chars, validator-enforced

class ReferentValue(BaseModel):
    value: Quantity                          # decimal string + unit (ADR-001 rule 2)
    stated_uncertainty: Belief               # ADR-004's union, NOT a tolerance number
    uncertainty_interpretation: str          # >= 40 chars: how the source's words were read
    censoring: Literal["none", "left", "right"] = "none"
    distribution_stated_by_source: bool = False

class ReferentPoint(BaseModel):
    point_id: str                            # stable within this referent
    epoch: Epoch                             # ADR-015's representation
    epoch_as_published: str                  # verbatim string as the source prints it
    epoch_window: EpochWindow | None         # observations integrate; instants are the exception
    values: dict[str, ReferentValue]         # keyed by declared ReferentField.name
    conditions: list[str]                    # observing conditions as stated by the source
    caveats: list[str]                       # required; ["none stated by the source"] is a caveat
    informativeness: Literal["two_sided", "one_sided_upper",
                             "one_sided_lower", "saturated"]
    informativeness_reason: str              # >= 40 chars
    locator: str                             # where in the artifact this was read from
    admissible: bool                         # does this point satisfy the declared rule below

class Referent(BaseModel):
    referent_id: str                         # semantic name, e.g. "dsoc.achieved_points"
    revision: int                            # monotone; identity is still the digest
    title: str
    source_refs: list[Ref]                   # Source objects, by digest
    artifact_refs: list[Ref]                 # DataArtifact digests: the bytes the numbers live in
    fields: list[ReferentField]
    admissibility_rule: str                  # >= 80 chars: which points from the artifact are in
    points: list[ReferentPoint]              # sorted by (epoch, point_id)
    commitment: ReferentCommitment | None    # see item 7
    supersedes: Ref | None
    revision_reason: Literal["points_added", "points_added_under_commitment",
                             "transcription_corrected", "uncertainty_restated",
                             "caveat_added", "source_superseded"] | None
```

The numbers appear twice on purpose: once in the artifact's bytes, hash-pinned and cited, and once transcribed into this JSON with a `locator` naming where in the artifact each came from. The transcription is the auditable object and the artifact is the authority. This is what makes AT-9's step - check one referent point against its cited public source - a defined operation rather than an aspiration: the auditor reads a value and a locator out of JSON they can open in a text editor and goes to that place in the cited source. FarSight does not parse the source. Nothing in `src/farsight/` may write a `ReferentPoint` value, which is the mechanical form of plan §14 item 5.

**2. Stated uncertainty is a `Belief`, and reading a bare plus-or-minus as a distribution requires a collapse record.** A source that states a bound and no distribution yields `EpistemicInterval`. A source that states a distribution and its parameters may yield `Aleatory`, and only then: `stated_uncertainty` of kind `aleatory` is rejected at freeze unless `distribution_stated_by_source` is true and the `locator` names the statement, or the field carries an `EpistemicCollapse` reference (ADR-004), which taints every downstream verdict. `Unknown` is admissible and is the honest kind for a published number with no stated uncertainty at all; it lands in the unknown register like any other. `uncertainty_interpretation` states in words how the source's phrasing was mapped, because that mapping is a judgement and it should be visible next to the number rather than in a commit message.

**3. Reference by digest, and metrics name a slot rather than a referent.** There is no exception to ADR-001 rule 7. Two changes make the digest form workable, and the second is the one that matters.

A metric definition (ADR-009) declares a **referent slot**: a name, a field, a unit, and its monotonicity in that slot.

```json
"inputs": [
  {"channel": "link.supportable_rate", "unit": "bit/s"},
  {"referent_slot": "achieved", "field": "achieved_rate_bps", "unit": "bit/s",
   "monotonicity": "decreasing"}
]
```

The binding of a slot to a concrete referent lives in the frozen `ComparisonSpec`, as a digest:

```json
{"comparison_id": "dsoc.envelope_vs_achieved",
 "referent_bindings": {"achieved": "<64-hex>"},
 "alignment": {"policy": "window_reduction", "reduction": "max",
               "max_offset": {"magnitude": "0", "unit": "s"}},
 "run_set": "outer_scan_full", "tier": "B"}
```

The human-readable `dsoc.achieved_points@v3` spelling survives only as **display derived from content**: `farsight evidence show` resolves the digest, reads `referent_id` and `revision` out of the object, and prints `dsoc.achieved_points@v3 (sha256:ab12...)`. The name is inside the object, never a key into a registry the auditor does not hold. ADR-009's example line is therefore wrong as written and must be restated in the slot form; that record already says it consumes whatever this one decides.

The slot indirection is not decoration. If a metric definition named a referent digest, then adding a pass point in week 7 would change the referent digest, change the metric definition hash, and re-version every metric that scores against it - orphaning the pre-registered metric registry at exactly the moment the pre-registration is supposed to be scored. Slots keep metric identity a property of the arithmetic and put "which data did we score against" in the experiment, where it belongs and where it is still covered by `experiment_hash`.

**4. Alignment is declared, and the referent is never interpolated.** Interpolating a referent would manufacture an observation from our own code, which §14 item 5 forbids. The permitted alignment policies reduce the *model* side to the referent's epoch or window:

- `exact_epoch` - the run's sample grid (ADR-020) must contain the referent epoch exactly. This is the default and the recommended shape, because the design controls its own grid and can plant the comparison epochs on it.
- `window_reduction` - reduce the model channel over the referent's `epoch_window` with a declared reduction (`min`, `max`, `mean`, compensated per ADR-008). This is the honest policy for an observation integrated over a pass.
- `nearest_sample` with a mandatory `max_offset` quantity. If the nearest sample is farther away than `max_offset`, the comparison is `indeterminate` with reason `no_aligned_sample`. A nearest match is never silent: the actual offset is recorded per point in `metrics/comparison_results.json` and any nonzero offset lands a row in `registers/assumptions.json`.

Model-side interpolation is not implemented and there is no code path for it. The epoch itself is carried in ADR-015's representation, with `epoch_as_published` and the conversion recorded, so an auditor can see the published string and the timescale step separately rather than inferring both from one number.

**5. A comparison where both sides have width is a set predicate with three outcomes.** The model side already has width: ADR-004's outer scan produces a band, and the criterion names the inner aleatory summary (ADR-009). The referent side has width from `stated_uncertainty`. They combine by evaluating the metric at the edges of the referent band, which is exact because the metric declares its monotonicity in the slot:

- The referent band is `[value - u_lo, value + u_hi]` from the `Belief`, with a `right`-censored value giving an unbounded-above edge and a `left`-censored value an unbounded-below edge. An unbounded edge is carried as an explicit marker; no infinity is ever written as a number (ADR-001 rule 3).
- The metric is evaluated at both edges for every run. With `monotonicity: increasing` or `decreasing` the metric's image of the referent interval is exactly the interval between the two edge evaluations. With `monotonicity: unspecified` the comparison returns `indeterminate` with reason `referent_uncertainty_not_propagable`. Refusal over approximation, as in ADR-003.
- The joint band is the union over referent edges and outer points of the per-run summary. ADR-009's rule then applies unchanged: the criterion holding at every point of the joint band is `pass`, holding at no point is `fail`, anything else is `indeterminate`.

For interval bands and a one-sided comparator this is one line: `pass` iff `sup(R) <= inf(P) + tol`, `fail` iff `inf(R) > sup(P) + tol`, otherwise `indeterminate`. AT-13's demand for a decided pass or fail on the DSN anchor is met without weakening anything, because the DSN model band is narrow by construction - that benchmark has no unknowns bucket - so the three-valued rule returns `pass` or `fail` there rather than straddling.

**6. Informativeness is declared per point and reported.** `two_sided` constrains the prediction from both directions (the DSN anchor). `one_sided_upper` can only refute an over-prediction, which is what an operationally selected achieved rate is. `saturated` sits at a system or instrument ceiling and constrains nothing beyond it, which is what a hardware-capped point is. A `saturated` point may satisfy a one-sided criterion and may never be cited as evidence that the envelope is tight. `metrics/acceptance_results.json` carries the counts by class, and `claim_statement.scope_conditions` (ADR-007) must enumerate them, so a reader can see how much of a passing result was carried by points that could not have failed.

**7. A pre-registration commits to a referent before it holds one.** Plan §17 publishes hashed predictions before the paywalled per-pass data is purchased. That is expressible as a `Referent` with `points: []` and a `commitment` block:

```json
"commitment": {"source_description": "per-pass achieved-rate points from the named publications",
               "fields": ["achieved_rate_bps"],
               "admissibility_rule": "<the same >=80-char rule the populated revision must carry>",
               "acceptance_criterion_ref": "<64-hex>",
               "alignment": {"policy": "exact_epoch"}}
```

The scoring package carries the populated revision with `supersedes` pointing at the commitment digest, `revision_reason: points_added_under_commitment`, and the commitment object itself embedded under `inputs/reference_data/` so the check is self-contained. `farsight evidence verify` (defined in ADR-007) fails the scoring package if `fields`, `admissibility_rule`, `alignment` or `acceptance_criterion_ref` differ from the commitment. That is the mechanical half of plan §1's circularity-proof falsification narrative: the rule that selects the points and the rule that scores them were both hashed before the data existed.

**8a. A model is never a referent, and model-versus-model comparison is a different object.** The rule first: **nothing produced by FarSight may be bound as a `Referent`.** A `ReferentPoint` value originates in a hash-pinned external artifact and in nothing else (decision 1, plan §14 item 5), so an aggregate population law validated against explicit-agent runs, a fast surrogate checked against a high-fidelity model, or this year's engine compared against last year's is **not** expressible by pointing a `ComparisonSpec` at our own output. That shortcut is the one a schedule-pressed implementer reaches for the first time cross-fidelity validation is needed, and one shipped package that took it retroactively compromises the sharpest honesty claim the corpus makes.

The right shape, reserved and not built: a future `ComparisonSpec` variant whose two sides are both **run sets**, each named by `experiment_hash` plus a run-set selector, reusing what already exists rather than inventing semantics — ADR-006's matched-configuration declaration with its enumerated *unmatched* items (for a cross-fidelity pair, "aggregation itself" is the headline unmatched item), `grid_hash` equality as the mechanical check that both sides speak of the same epochs (ADR-020), a declared reduction in the style of decision 4's `window_reduction` but taken over the run axis where one side is a distribution and the other a single series, physically motivated tolerances, and the three-valued verdict of decision 5. It is Tier C by construction (ADR-006) and it is **post-hoc**: it references two frozen experiments and adds no edge to the execution plane, because ADR-018 deliberately has no way for one run to read another's output. Building it waits for the first real aggregate-versus-sample validation to design against; forbidding the referent route does not wait.

**8. Revisions are new objects, never edits.** A new revision is a new digest with `supersedes` and a `revision_reason`. `refs/referent/<referent_id>` is a mutable alias pointing at the newest, usable for authoring and never appearing inside a frozen document (ADR-001 rule 7). A `transcription_corrected` revision means every verdict scored against the prior revision was scored against a number now known to be wrong; `farsight diff` can show it between two packages, and there is no mechanism that reaches into a package a customer already holds (see Forecloses).

## Options considered

### Option 1 — No `Referent` type: a hash-pinned `DataArtifact` plus a tolerance number on the rule — REJECTED
This is what a competent V&V comparison script does today, and it is close to what the plan's own 200-line-notebook standing kill describes. The file is cited and hashed, so provenance survives; the acceptance rule carries the tolerance; there is no new schema, no transcription step and no sign-off. In week 3 it is at least two dev-days cheaper. Rejected because the stated uncertainty then has nowhere to live except as that tolerance number, which is the ADR-004 hole this record exists to close, and because caveats, admissibility and informativeness become prose in a README rather than fields anything can check. Plan §4 names the missing entity explicitly; this option is the state the plan already rejected.

### Option 2 — Uncertainty as a value plus an expanded uncertainty with a coverage factor (the GUM convention) — REJECTED
This is the strongest rejected option and it is a named, shipping, standard thing: the GUM expresses a measurement result as a value with an expanded uncertainty and a stated coverage factor, metrology and NASA-STD-7009 practice both use it, and plan §9 cites GUM approvingly as the precedent for margin-first presentation. It maps cleanly onto a Gaussian, it is what an instrument engineer expects to see, and it would let referent uncertainty combine with model uncertainty into one number. Rejected on one defeating ground: it presumes a probabilistic model that most of our sources do not state. Where a source *does* state a coverage factor, our design expresses it exactly - `Aleatory` with `distribution_stated_by_source: true` and a locator - so nothing is lost in the case GUM was written for. Where the source states only a bound, adopting GUM means reading that bound as a sigma, which is an unauthorized collapse performed silently at the boundary. We take the GUM shape where the source supports it and refuse to manufacture it where it does not.

### Option 3 — Reference by `name@version` alias with a stated ADR-001 exception — REJECTED
ADR-009's written form, and it has real merits: registry-scoped semantic versioning is exactly how mature package ecosystems name immutable artifacts, the metric registry stays human-legible, and - the strongest point - the reference remains stable when a referent gains a point, which a digest does not. Rejected because resolution requires a registry the auditor does not hold: the audit path is a package, a plain Python session and two hours, and a name that resolves only against our store is a dangling pointer in that setting. It also reintroduces a mutable alias inside a frozen document, which is the immutability invariant plan §4 states. Its genuine merit is what produced the chosen design: the slot indirection delivers stability across revisions without an alias.

### Option 4 — Metric definitions name a referent digest directly — REJECTED
One object fewer, and the metric definition becomes fully self-describing: an auditor reading it sees exactly which dataset it scores against, with no join. There is a defensible argument that "the metric that scores against this dataset" simply is a different metric. Rejected because metric identity would then churn with data: buying the per-pass papers in week 7 and adding their points re-versions every metric in the registry, which breaks the pre-registration comparison at the moment it is being made, and orphans every `MetricValue` computed in weeks 3-6 for a reason that has nothing to do with the arithmetic.

### Option 5 — Collapse both sides to a point and compare with a tolerance — REJECTED
Crisp, universally understood, no `indeterminate` column, and AT-13 literally asks for a decided pass or fail with no unknowns bucket, so this option can claim the acceptance test's own wording. Rejected because collapsing the model band is the laundering ADR-004 exists to prevent, and it would be performed at the one step where the result is shown to a customer. The concession that matters: AT-13 is satisfied anyway, because the DSN anchor's model band is narrow by construction and the set predicate returns a decided verdict there. We do not need to weaken the semantics to get the demo.

### Option 6 — Typed `Referent` with `Belief` uncertainty, slot binding by digest, and a three-valued set predicate — CHOSEN
Keeps one uncertainty system across the boundary where it first meets observation, satisfies ADR-001 rule 7 with no exception, keeps metric identity stable across data revisions, and refuses rather than approximates when a metric's monotonicity is undeclared. It costs transcription work, a sign-off per referent, and an alignment policy authored per comparison.

## Consequences

**Buys us:** ADR-004's guarantee survives the comparison step, which is the one place it was previously broken. AT-9's referent check becomes a defined two-minute operation with a locator rather than a treasure hunt. ADR-001 rule 7 stands with no exception, so the "no alias in a frozen document" invariant remains a schema fact. Pre-registration becomes a hash-checkable binding rather than a promise. And the weakest part of the flagship claim - how many scored points could not have failed - is a mandatory count in the package instead of a thing a reader has to notice.

**Costs us:** every referent point is transcribed by a human, with a locator, a caveat list and an informativeness classification, and a review sign-off covering the transcription. Every referent revision is a new object plus a supersedes edge, so correcting one digit in one point is a new digest and a new binding in every `ComparisonSpec` that used it. Metric definitions grow a monotonicity declaration that has to be property-tested to be worth anything. The alignment policy is authored per comparison rather than defaulted, which is friction on every new benchmark. And an `Unknown` stated uncertainty on a published number - the honest kind for a number with no stated error bar - makes the comparison `indeterminate` far more often than a tolerance number would have.

**Forecloses:** model-side interpolation, permanently in the MVP. A run whose sample grid does not contain the referent epochs cannot be compared at those epochs without re-running on a grid that does, which will bite in weeks 5-6 when a Basilisk run at a fixed task rate is compared against a referent whose epochs fall between samples; the escape is `nearest_sample` with a stated offset and an assumption-register row, which is a worse claim, honestly labelled. It also forecloses any combined-uncertainty statement: we never fold referent uncertainty and model uncertainty into a single band, so we cannot report a combined standard uncertainty in the GUM sense, and a customer whose acceptance process requires one gets a set predicate instead of their number.

And the sharpest one: **a shipped package can never be corrected.** A transcription error found in week 9 produces a new referent revision and a new package, and there is no channel that reaches a customer holding the old one. Content addressing means the old package still verifies perfectly - it is an accurate record of a comparison against a wrong number. Nothing in this design detects that case from inside the artifact, and the only mitigation is the sign-off that is supposed to prevent it.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Stated uncertainty is a `Belief`, and `Aleatory` requires a source-stated distribution or a collapse | 0.90 | The week-3 DSN 810-005 import or the week-4 DSOC point freeze produces a source whose uncertainty statement fits none of the five kinds without distortion, i.e. the union is the wrong shape for observational data rather than for parameters |
| Transcription into hashed JSON with a locator, rather than parsing the artifact | 0.70 | The week-4 DSOC point set exceeds roughly 40 points, at which point hand transcription stops being credible and a parser plus a checked-in extraction fixture is cheaper than the sign-off it replaces |
| Reference by digest, with a slot in the metric and the binding in `ComparisonSpec` | 0.75 | The week-3 metric registry freeze cannot express a comparison that legitimately needs two referents in one metric, or the ADR-009 owner rejects the slot form; either forces the digest-in-metric shape of Option 4 and its re-versioning cost |
| Three-valued set predicate over the joint model-and-referent band | 0.80 | The week-4 DSN anchor returns `indeterminate` (AT-13 demands a decided verdict), which would mean the anchor's model band is not as narrow as the no-unknowns framing assumes and the benchmark, not the semantics, needs rework |
| Alignment policies with no model-side interpolation | 0.65 | The weeks 5-6 Basilisk comparison cannot place its sample grid on the referent epochs, so every point falls to `nearest_sample`; that is the case this rule was written against and it is also the case most likely to force it open |
| `informativeness` classification and its effect on how AT-5 is reported | 0.60 | The week-4 frozen DSOC point set has 3 or more `saturated` points out of the frozen total, or fewer than 3 points that are not `saturated`. Either means the flagship's pass is carried by points that could not fail, which is a K6 finding at week 4 rather than at week 8 |
| `ReferentCommitment` as the pre-registration mechanism | 0.70 | The week-7 pre-registration cannot be expressed without naming a point count or an epoch list the commitment does not yet know, which would mean the commitment has to bind less than we assumed and the circularity argument weakens |
| Revisions are new objects with a `supersedes` edge and a typed reason | 0.85 | A `transcription_corrected` revision becomes necessary after the week-4 DSN package or the week-7 pre-registration package has left the team, which is the case with no remedy and would force a published-errata mechanism before the week-8 external cold audit rather than after it |

## Enforcement

The test modules below run in the existing `honesty-suite` CI job (defined in ADR-004); this record adds legs rather than a job.

1. `tests/unit/test_referent_schema.py` (**first green by week 2**) - `stated_uncertainty` is a `Belief` and a `float`-typed uncertainty field exists nowhere in `schemas/knowledge.py`; an `aleatory` stated uncertainty without `distribution_stated_by_source` and a locator, or without an `EpistemicCollapse` reference, fails at construction; every `ReferentPoint` carries a non-empty `caveats`, a `locator`, an `epoch_as_published` and an `informativeness` value; every magnitude satisfies ADR-001's decimal grammar.
2. `tests/unit/test_referent_reference_form.py` (**first green by week 3**, when the metric registry exists) - no hashed model has a field capable of holding a `name@version` referent reference; a `Ref` field rejects anything that is not 64 lowercase hex (ADR-001 enforcement 5); a metric definition containing a `referent` digest rather than a `referent_slot` fails schema validation; a `ComparisonSpec` whose bindings do not cover every slot of every metric it names fails at freeze.
3. `tests/unit/test_comparison_band_semantics.py` (**first green by week 3**) - a Hypothesis property suite over generated interval pairs asserting the three-way rule exactly as stated, that widening either band can only move a verdict toward `indeterminate`, that a right-censored referent never yields `pass` under a comparator bounded above, and that a slot with `monotonicity: unspecified` yields `indeterminate(referent_uncertainty_not_propagable)` rather than a number.
4. `tests/unit/test_declared_monotonicity.py` (**first green by week 3**) - the property test plan §14 item 4 already calls for, applied to the slot declaration: for each metric declaring monotonicity in a referent slot, generated inputs must not violate it. This is what makes the two-edge propagation exact rather than assumed.
5. `tests/unit/test_referent_alignment.py` (**first green by week 3**) - a referent epoch with no sample inside `max_offset` yields `indeterminate(no_aligned_sample)`; `exact_epoch` with an absent epoch fails rather than falling back; an AST scan asserts no interpolation call reachable from `farsight.comparison`; every nonzero applied offset appears in `registers/assumptions.json`.
6. `tests/unit/test_prereg_commitment_binding.py` (schema half **first green by week 3**; the end-to-end check **first green by week 7**, since pre-registration is a weeks 7-8 activity and there is nothing to score before it) - a package whose referent carries `revision_reason: points_added_under_commitment` must embed the superseded commitment object and match it field by field on `fields`, `admissibility_rule`, `alignment` and `acceptance_criterion_ref`.
7. `farsight evidence verify` (defined in ADR-007; **first green by week 4**) - every `referent_ref` in the claim statement and in every `ComparisonSpec` resolves inside the package; under `closure: self_contained` every `artifact_refs` digest is present under `inputs/data/`; the per-class `informativeness` counts in `acceptance_results.json` recompute from the bound referents; any mismatch exits nonzero naming the point.
8. `PARTIALLY MECHANIZED: REF-1` - transcription fidelity. Mechanically checkable: the artifact is present, its digest matches, the locator is non-empty and well-formed, the magnitude parses, the unit is dimensionally consistent with the declared field. Not checkable: that the number in the JSON is the number at that place in the artifact, which is a human reading a paper. Residue: the correspondence between each transcribed value and its locator. Review-checklist item **REF-1** - *"every value and uncertainty in this referent revision was read from the cited artifact at the stated locator by a named person, and the units and significant figures are the source's"* - lands in `review_signoffs` on the frozen `EvidencePackage` (ADR-000) and gates `evidence_grade: evidence`. **First green by week 2** for the mechanical half, week 4 for the `verify` gate.
9. `NOT MECHANIZABLE: REF-2` - whether a published epoch string means what we read it as. `2024-04-08` may be a pass start, a pass midpoint, the date of the report, or a local date at the station; the conversion from `epoch_as_published` to ADR-015's representation is mechanical once the reading is fixed, and the reading is not. Review-checklist item **REF-2** - *"the epoch reading and timescale recorded for each point is the one the source states, and where the source is ambiguous the ambiguity is a caveat"* - lands in `review_signoffs`.
10. `PARTIALLY MECHANIZED: REF-3` - whether the points selected from a newly obtained source are the points the pre-registered `admissibility_rule` actually selects. Item 6 checks that the rule text is unchanged; parsing an English admissibility rule and applying it to a PDF is not a check. Residue: the selection step itself. Review-checklist item **REF-3** - *"the admitted point set is exactly what the pre-registered admissibility rule selects from the obtained source, and every excluded point is listed with its exclusion reason"* - lands in `review_signoffs`.

## References

- FARSIGHT_FOUNDATION_PLAN.md §1 (the DSN anchor at plus-or-minus 1 dB as the precision case; achieved rates operationally chosen with unpublished margin; the 267 Mbps points hardware-capped; pre-registration as the circularity-proof narrative), §2 (FarSight owns model-versus-referent comparison semantics; customers provide referent data for validation), §4 (`Referent` and `ReferentPoint` in the knowledge plane; `ComparisonSpec` in the design plane; the immutability invariant), §13 (`inputs/reference_data/`, the claim statement, the four-step audit path including checking one referent point against its cited public source), §14 item 5 (a golden or referent number may never originate from our own code) and item 4 (declared monotonicities as property tests), §17 weeks 3-4 and 7-8, §18 AT-5, AT-9 and AT-13, §21 K2 and K6, "Things we must get right" item 4.
- The DSOC and DSN referent numbers themselves are not written into this record. They enter as cited, hash-pinned `DataArtifact`s at the time the datasets are frozen (plan §14 item 5). UNVERIFIED - confirm at implementation time: which specific published points are censored as opposed to merely saturated, and the exact source wording for each stated uncertainty, both of which are fixed when the artifacts are obtained and transcribed.
- Cross-reference, and a correction ADR-009 invited: ADR-009's metric-definition example writes `{"referent": "dsoc.achieved_points@v3", ...}`. Under this record the canonical form is `{"referent_slot": "achieved", "field": ..., "unit": ..., "monotonicity": ...}` with the digest binding in `ComparisonSpec`. ADR-009 states it consumes whatever this record decides; the example line still needs restating there. The identical rule-7 argument applies to ADR-009's `"metric": "dsoc.rate_ladder_step_delta@1.0.0"` criterion field, but the metric reference form is ADR-009's to own and is not decided here.
- ADR-000, ADR-001, ADR-004, ADR-006, ADR-007, ADR-009, ADR-013, ADR-015, ADR-020, ADR-023.
- PLAN AMENDMENT REQUESTED: §4 - `ComparisonSpec` gains `referent_bindings` (slot name to referent digest) and a declared `alignment` policy with `max_offset`. §4 describes `ComparisonSpec` only as a matched-configuration declaration, which covers cross-engine comparison but not model-versus-referent comparison, and the plan's own "Things we must get right" item 4 requires the latter to be first-class.
- PLAN AMENDMENT REQUESTED: §4 - `ReferentPoint` gains `epoch_as_published`, `locator`, `informativeness` with its reason, `admissible`, and per-value `censoring` and `uncertainty_interpretation`; `Referent` gains `revision`, `admissibility_rule`, `artifact_refs`, `supersedes`, `revision_reason` and the optional `commitment` block. §4 gives the parenthetical field list "epoch, value, stated uncertainty, caveats", which cannot express transcription provenance, a pre-registration commitment, or which points can constrain the envelope.
- PLAN AMENDMENT REQUESTED: §13 - the `metrics/` block gains `comparison_results.json`, which decision 4 writes the per-point applied alignment offsets into. Reason: §13's `metrics/` block ends at `failure_groups.json`, so the one file that records how far each model sample sat from its referent epoch has no declared home; a stated offset that is not package content cannot be audited, and `nearest_sample` is exactly the policy a reader has most reason to check. ADR-007 owns the layout and carries the same addition.
- PLAN AMENDMENT REQUESTED: §18 - AT-5 is reported with per-class `informativeness` counts alongside its verdict, and a `saturated` point may satisfy the criterion but may never be cited as evidence that the envelope is tight. Reason: §1's own verified facts make some frozen points incapable of failing, and without the counts AT-5 can pass on evidence that could not have falsified it, which is the failure K6 is meant to catch two weeks later.
