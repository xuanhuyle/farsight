# FarSight — Self-Auditability Architecture Review

**Status:** `research-reviewed; internally cross-checked; not externally expert-reviewed` (ADR-030)
**Date:** 2026-09-01 · **Scope:** architecture review only; no production code modified, per the brief's §16.
**Method:** three parallel surveys of the 31-record ADR corpus and the implemented code, plus direct verification — every code defect below was reproduced by execution, every ADR contradiction by citation.

---

## 1. Executive conclusion

**The Self-Auditability Principle is already about eighty percent supported by the architecture and about zero percent machine-readable.** The corpus was built by people who believed this principle before it was written down: metric/threshold separation is enforced by an AST check that catches a threshold smuggled in under a physical-sounding name; verdicts are three-valued with `indeterminate` as a *result*; excluded runs widen a distribution as bounding mass rather than vanishing from it; the referent-laundering prohibition forbids binding our own output as observation; and `report/summary.md` is renderer-generated with its digest pinned in the manifest, so hand-edited narrative in a package is structurally impossible. None of that needs inventing.

What is missing is that most of the audit surface exists as **prose commitments inside ADRs rather than as schemas**, so none of it answers the queries the brief's §8 asks for. The work this principle implies is not to change what FarSight concludes. It is to make what FarSight already produces machine-readable, and to close one entity-shaped hole: a Claim has fields but no identity.

**The most important result of this review was produced by the principle itself.** Applying it to FarSight's own implementation — the first time anything has audited the auditor — found within minutes that **the identity guarantee is false in the current code**. `model_copy(update=...)` re-runs no validators, and it sits on the production path in `Aleatory.at()`, so `content_hash` will mint a 64-hex address for a `Deterministic` whose `value` is the string `'not-a-quantity'`. Everything in FarSight rests on a content address being the address of a *validated* document. Right now it is not. That single finding is both the most urgent item in this review and the strongest available argument for adopting the principle.

The principle's text needs three amendments before ratification: one undefined word that decides whether it becomes discipline or theater, one clause that demands unachievable completeness, and one clause that is unsound as literally written. Those are §3 and §2 below.

---

## 2. Interpretation of the Self-Auditability Principle

The principle as offered is a constitutional statement in four clauses. Read carefully, it makes one strong architectural demand and three supporting ones.

The strong demand is **structural, not documentary**: a conclusion must arrive with enough *structured* evidence that a stranger can attack it without our help. That is a claim about the shape of persisted data, not about report quality — which is why the brief is right to say it is "more fundamental than report generation or logging." A beautifully written report over unstructured evidence satisfies nothing; a terse JSON document over a complete evidence graph satisfies almost everything, because a reviewer can query it.

The three supporting demands are: that FarSight actively try to break its own conclusions rather than merely documenting them; that the reviewer's path to the weak points be short; and that internal consistency never be dressed up as external validation.

One interpretive point matters for everything downstream. The brief says the principle "should influence the domain model, experiment architecture, evidence model, uncertainty handling, validation logic, and APIs from the beginning." Taken literally today, that would mean reopening 31 accepted records — which ADR-000 forbids (an accepted Decision is never edited; reversal means a new record). It would also be unnecessary, because those records already encode most of the principle. The honest reading is: **ratify the principle as constitutional, repair what is broken, add the one missing entity, and preserve seams for the rest.** That is what this review recommends.

---

## 3. Self-audit is not self-validation — and a critical evaluation of the principle

The brief's distinction is correct and should be constitutional. FarSight can establish provenance completeness, deterministic replay, unit consistency, numerical stability, sensitivity, model disagreement, envelope excursions, missing assumptions, unsupported probability assignments, and counterexamples *within* an admissible space. It cannot establish that the physical model is right, that the literature has no shared blind spot, that an extrapolated technology will work, or that anything is flight-qualified. ADR-030 already codifies this and a lint enforces the vocabulary.

The principle's text, however, needs work in three places. Taking each clause in turn:

### 3.1 "Material" is undefined, and it is load-bearing

Every requirement in the principle is scoped by the word *material*. Undefined, it collapses to one of two failures: applied to everything, it is the compliance theater §15 forbids; applied at author discretion, it is a loophole that swallows the rule. This is the single most important gap in the principle as written.

**Proposed operational test, reusing machinery that already exists.** A conclusion is material if any of these hold: it leaves the team (published, shipped, or shown to an outsider); it is cited as a reason in a decision (a gate, a design choice, a go/no-go); or another artifact references it as evidence. That test is checkable at exactly the chokepoint FarSight already has — `evidence_grade: evidence`. **Materiality is approximately evidence-grade**, and the exploratory lane is where non-material work lives, unburdened. A working result in the exploratory lane carries what it already carries, which is a great deal, and nothing more is demanded of it.

### 3.2 Clause 1 demands completeness that cannot be achieved; it should demand declared coverage

The clause requires "enough structured evidence to identify its provenance, assumptions, uncertainty classes, validity conditions, sensitivity, reproducibility status, independent checks, known contradictions, falsification attempts, and outstanding expert-review requirements."

Most of those ten are producible. **"Known contradictions" is not**, in general: FarSight knows only the contradictions it computed or was told about, never one lurking in a paper nobody read. A completeness requirement over an unbounded set invites either false completeness or paralysis.

**Proposed reformulation: require declared coverage, not completeness.** For each dimension, the artifact carries either the assessment or an explicit *not assessed*. This is achievable, and it is strictly more honest, because it distinguishes "we checked and found nothing" from "we never looked" — a distinction that is currently invisible and that matters enormously to a reviewer.

The corpus already contains this idea and states it beautifully. ADR-007 decision 4, on the five registers: *"An empty register is an assertion that there is nothing to declare; a missing register is a verification failure."* Generalize that one sentence to every audit dimension and clause 1 becomes implementable.

It is worth noting that the gap is not hypothetical. It exists today in one line of shipped code: `_BeliefBase.validity: ValidityEnvelope = Field(default_factory=ValidityEnvelope)` (`belief.py:181`). A belief whose author never considered validity silently acquires an *empty* envelope, which then reads as "the author asserts no constraints." The freeze check passes, because an empty envelope is an envelope. Missing has silently become empty — precisely the collapse ADR-007 forbids one layer up.

### 3.3 Clause 2 is the best clause, and needs one caveat

"FarSight should actively attempt to falsify material conclusions" is what separates this system from provenance tooling. Keep it.

The caveat: **a falsification attempt must record the space it searched, and a negative result must never be reported without it.** "No counterexample found" over the wrong admissible space is worse than no search at all, because it manufactures assurance.

Our own recent history proves the failure mode rather than merely suggesting it. The original K2 envelope was built over an admissible space that was *wrong* — three terms were silently fitted (a half-power transmitter, a 12.5% aperture obscuration, a range error). Any counterexample search over that space would have returned a confident, reassuring, meaningless result.

### 3.4 Clause 3 is unsound as written

> "The system should make it easier for an external expert to challenge a result than to accept it."

This is the most quotable line in the brief and the one I would not ratify. Three problems. It is an asymmetry claim about human effort, unmeasurable as stated. Taken literally it is perverse — a system optimized so that challenging is easier than accepting is a system that has made acceptance artificially hard. And it is not what the brief actually wants: §7 states the real objective, "reducing the amount of expert time required to identify the real weak points of an analysis."

**Proposed replacement:**

> A reviewer must be able to reach a conclusion's weakest supporting element faster than they could re-derive the conclusion themselves — and the artifact must surface that element without being asked.

This is measurable (a variant of AT-9: time-to-first-weakness against time-to-reconstruct), non-perverse, and it converts §10's weakness-first ordering from a stylistic preference into a structural requirement on the artifact.

### 3.5 Clause 4 is sound and already implemented

"Internal consistency and self-auditability must never be represented as external validation" is ADR-030, and `test_no_false_validation` enforces the vocabulary today. Keep it verbatim.

### 3.6 Two clauses I would add

**Independent recomputability.** Transparency is not auditability. A reviewer who can *read* the evidence but not *recompute* it is still trusting us. ADR-007's zero-extras `verify` — which recomputes every hash and every metric from stored channels on a clean install with no engine present — is arguably FarSight's single strongest audit property, and the principle never mentions it. Unnamed, it will be treated as an implementation detail and eroded the first time it is inconvenient.

**Durability of negative results.** A falsification attempt that *succeeded* must be as permanent as one that failed. Without this there is a ratchet: inconvenient counterexamples get re-run under slightly different conditions until they disappear. This is the same failure the tolerance-inflation kill guards against (allowed count: zero), applied to searches rather than tolerances.

### 3.7 The reformulated principle

> **Self-Auditability Principle**
>
> A FarSight conclusion is **material** if it leaves the team, is cited as a reason in a decision, or is referenced by another artifact as evidence.
>
> No material conclusion may be presented without structured, machine-readable evidence that either establishes or explicitly declares *not assessed* for each of: provenance, assumptions, uncertainty classification, validity conditions, sensitivity, reproducibility status, independent checks, known contradictions, falsification attempts, and outstanding expert-review requirements. An absent assessment is a recorded state, never a silent gap.
>
> FarSight should actively attempt to falsify material conclusions through boundary testing, alternative models, counterexample search and adversarial analysis. Every falsification attempt records the space it searched, and no negative result is reported without it.
>
> A reviewer must be able to reach a conclusion's weakest supporting element faster than they could re-derive the conclusion, and the artifact must surface that element without being asked. A reviewer must also be able to **recompute** the conclusion independently, from the artifact alone, without our tooling for the physics.
>
> A falsification attempt that succeeded is as permanent as one that failed.
>
> Internal consistency and self-auditability must never be represented as external validation.

---

## 4. Current architecture assessment

Three findings frame everything below.

**First: the corpus already practises the principle, in prose.** The K2 Deep Review, produced by hand last week, satisfies eight of the principle's ten evidence dimensions — provenance (every bound carries a URL and an evidence-taxonomy label), assumptions (six terms enumerated), uncertainty classification (per-term confidence tied to evidence, not eloquence), sensitivity (a pin-decomposition showing what each purchase buys), reproducibility (a standalone script), independent checks (independent reconstruction plus triangulation against two flight-program budgets), known contradictions (ten disagreements reported un-averaged), and expert-review residue (ten hand-over questions on the backlog). It lacks only counterexample search and formal validity conditions.

And it is **entirely prose**. It answers none of §8's queries. That is this review in one observation.

**Second: the strongest existing machinery is exactly where the brief expects the most work.** §3 asks that structured data come first and reports be generated from it. That is not merely gestured at — it is already mandatory and mechanized. `report/summary.md` is produced by a deterministic renderer from package JSON; the manifest records the renderer version *and the expected `summary.md` digest*; `verify` re-renders and fails on byte difference. A customer cannot hand-add narrative to their own package. On top of that, all seventeen CLI commands must emit a `cli_result/1` object on `--json`, with stdout carrying exactly one JSON object and nothing else.

**Third: the assessment layer is where the prose lives.** `Verdict`, `ExcludedRun`, `Assumption`, `manifest.json` itself, and the contents of `metric_results.json`, `acceptance_results.json`, `sensitivity.json` and `comparison_results.json` exist as *described content with no field list*. Three of the five register file formats are prose-only. The shapes become permanent at the first shipped package.

---

## 5. GREEN / YELLOW / RED matrix

| Area | Status | Current assumption | Future requirement | Recommendation |
|---|---|---|---|---|
| **Domain model** | **RED** | `claim_statement` is a 10-field sub-object of `manifest.json`: singular, no id, no hash, no supersession, unreferenceable | Claims must be identifiable, cross-referenceable, superseded, and pre-registerable | **CHANGE NOW** — `Claim` as a content-addressed object frozen with the design (§12) |
| **Assumptions** | **RED** | `Assumption` has no schema, while `AssumptionRef` is live inside hashed documents | Assumptions must be traceable and enumerable by pedigree | **CHANGE NOW** — schema, per the ADR-026 precedent (§7) |
| **Sources** | **RED** | Same: `Source` has no schema; `SourceRef` is live in `Pedigree.sources` | Two citations of one paper must be recognizably the same object | **CHANGE NOW** — schema |
| **Models** | **YELLOW** | ADR-026 gives `ModelVersion` a validity envelope and verification status — but `StageSpec` has no field naming a model | The Model→Run edge must exist as a reference | **CHANGE NOW** — D1, a field addition resolving a contradiction between two accepted records |
| **Uncertainty** | **GREEN** with one defect | Five-kind union with asymmetric API, implemented and tested; no `to_distribution`; `EpistemicSet` unweighted, asserted by an absence test | Epistemic weakness must propagate visibly | Keep. **Repair C3** — collapse `scope` cannot carry paths, so taint recomputation is unimplementable |
| **Experiments** | **YELLOW** | `(experiment_hash, run_index) → spec_hash` is a pure derivation; aleatory draws keep their topology path | Every result traces to exact inputs — *including deterministic ones* | **CHANGE NOW** — G1, path-preserving lowering |
| **Metrics** | **GREEN** | Calculation and threshold separated, enforced three ways including an AST check on constants used as comparison operands | Unchanged | Keep; do not rebuild |
| **Evidence** | **YELLOW** | Five registers with empty-vs-missing semantics; bounding-mass aggregation; zero-extras `verify` | A reviewer reconstructs the causal chain | **CHANGE NOW** — G4 schematize; **SEAM** — materialized reverse index |
| **Faults** | **GREEN** | `FaultActivationRecord` with digest-keyed `factor_state`; zero-magnitude paired counterfactual as the causal instrument | Active faults appear in claim lineage | Keep. Excellent as-is |
| **Comparison** | **GREEN** | Matched-config declaration enumerating *unmatched* items; Richardson discrimination; referent-laundering prohibition | Independent checks representable | Keep |
| **Audit** | **RED** | No first-class audit concept anywhere; five disjoint ingredients, nothing joins them | Multidimensional audit status per claim | **SEAM** — derived `EvidenceAssessment` (§13), never authored |
| **Reporting** | **GREEN** | Renderer-generated, digest-pinned, hand-editing impossible; uniform `--json` | Weakness-first ordering | **SEAM** — two views over one dataset (§19) |

---

## 6. Existing capabilities we should preserve

These are load-bearing and a self-audit programme must not disturb them:

- **Metric purity by construction.** `MetricContext` carries channels, metadata, run facts and declared constants — no filesystem, no engine handle, no RNG, no clock, no threshold. `thresholds: null` is a required field. `test_metric_purity` fails on any numeric literal not declared in `constants`, **and on any constant appearing as an operand of a comparison** — which is how a threshold would be smuggled in under a physical-sounding name.
- **Three-valued verdicts.** `indeterminate` is a result with its own report column, and the CLI exits zero for it. A band that straddles a criterion is not rounded to a decision.
- **Bounding-mass aggregation.** Excluded runs enter the CDF at the metric's admissible extremes, so exclusion *widens* the band rather than deleting evidence. Zero exclusions makes the two bounds byte-identical.
- **The referent-laundering prohibition** (ADR-021 8a): nothing produced by FarSight may be bound as a `Referent`. This is the shortcut a schedule-pressed implementer reaches for, and one shipped package taking it would retroactively compromise the sharpest honesty claim in the corpus.
- **The golden-attestation enum.** Four admissible sources, and *"there is deliberately no `farsight_output` member, so the rule is enforced by the absence of a way to express its violation."* That design pattern — closure by inexpressibility — recurs throughout and should be the default technique for new audit rules.
- **Zero-extras `verify`.** The auditor's install has no engine and no compiled physics; `verify` recomputes hashes and metrics from stored arrays and never executes physics.
- **Refusal at freeze with no fifth mode.** Fault lowering is native, config-time, segment-split, or refusal. *"There is no fifth mode called 'approximate'."*

---

## 7. Foundational gaps

Beyond the defects in §8, four structural gaps:

**G1 — lineage dies at the engine boundary (load-bearing).** `StageSpec.bindings` lowers a parameter into `ValueSource{kind, value: Quantity}`, carrying the value **but not the topology path it came from**. Only *aleatory* draws retain their path, via `seeds_<i>.json.aleatory_values` and the materialized `draw_order`. Every **deterministic and every derived** parameter therefore has no reconstructible edge into any run; you could only join by matching decimal strings, and ADR-001 guarantees `"0.220" != "0.22"` precisely so that such a join is meaningless. This is why the collapse-taint recomputation is unimplementable even after C3 is repaired, and it is the reason "show all claims materially dependent on speculative assumptions" cannot be answered for the majority of beliefs.

**G2 — `Source` and `Assumption` have no schema.** `SourceRef` and `AssumptionRef` appear inside hashed documents with undefined referents. This is verbatim the hazard ADR-026 was commissioned to close for `ModelVersionRef` — *"the reference is live in a hashed document and its referent is undefined"* — closed for models, left open for these two. Without them you can traverse *to* a Source digest but cannot say what a Source is, whether two citations are the same paper, or what a speculative assumption node looks like.

**G3 — Claim has fields but no identity.** Detailed in §12.

**G5 — no reverse index.** Every edge is a forward pointer from dependent to dependency, which is correct and unavoidable: a back-pointer would change the hash of the object pointed at, and ADR-001 forecloses annotating frozen objects. The corpus promises exactly one reverse index — one clause of one bullet in ADR-007, `registers/assumptions.json` carrying "the objects that depend on it" — with no schema, no row type, and no enforcement test.

---

## 8. Changes required now

All are pre-freeze schema work or defect repair. Five are defects, not features.

### 8.1 Code defects (reproduced by execution)

**C1 — content addresses can be minted for documents that never passed a validator. Material.**
`model_copy(update=...)` re-runs no validators, and `Aleatory.at()` (`belief.py:240`) uses it on the production path. Reproduced:

```
Deterministic.model_copy(update={'value': 'not-a-quantity'})
  -> .value is str 'not-a-quantity'
  -> content_hash(...) == 3b1572bece571dff...     (Pydantic emits only a serializer warning)
```

`frozen=True` blocks attribute *assignment* — which is what `test_beliefs_are_frozen` asserts, so the test passes for the wrong reason — but not construction of an invalid copy, and construction is what identity depends on. It also bypasses the `Distribution` guard: constructing a distribution with an `Aleatory` hyperparameter is refused, while `at()` accepts one. **Fix:** validate on copy (`model_validate(self.model_dump() | update)`) or ban `model_copy(update=)` on hashed models by lint and route `at()` through construction.

**C2 — `at()` silently overwrites an already-pinned hyperparameter.** Reproduced: a `sigma` fixed at `0.16 urad` is rewritten to `99` with no refusal. The method checks unknown names and unresolved leftovers, never that its target was epistemic. An outer-scan point should resolve epistemic coordinates only.

**C3 — `EpistemicCollapse` drifted from ADR-004 in the field the taint check needs.** Code has `scope: Literal["exploration_only","evidence"]` (`belief.py:399`) — a lane label. ADR-004 specifies a scope carrying `experiment_hash` plus explicit parameter paths, and requires `verify` to recompute taint by intersecting that scope with the paths a result depends on, treating a contradicted stored `false` as an integrity failure. With no paths in scope, the recomputation is unimplementable and the taint degrades to a stored boolean — the advisory-flag failure ADR-004's own Option 2 rejects. The justification minimum also drifted (60 vs 120 characters).

**C4 — `enumerate_outer(plan)` accepts a sampling plan and silently ignores it**, returning the two interval vertices unconditionally. Its sibling `Aleatory.sample()` raises `NotImplementedError` for its unbuilt half: two unimplemented paths, two failure disciplines, and this one under-delivers silently. A truncated outer scan yields a **narrower** envelope, which makes AT-5's width criterion *easier* to pass — the exact direction of error the `outer_scan_convergence` gate exists to catch.

**C5 — no `schema_version` on any implemented model.** ADR-005 and ADR-006 both require in-band versions, and ADR-005 makes `verify` fail on an unknown `stream_registry_version`. A hashed FarSight document today is self-consistent but unversioned. Cheapest item here while `schemas/` holds two modules.

### 8.2 Contradictions between accepted records

**D1 — ADR-026's validator targets a field ADR-018 does not define.** `model_binding_consistent` checks "every `StageSpec` (ADR-018) naming that model"; `StageSpec` has eight fields and none names a `ModelVersion`. Add `model_ref` (or `model_refs`) to `StageSpec`.

**D2 — a stated capability with no field.** ADR-007 line 126 says a claim may name other packages' root hashes as cited evidence; `claim_statement` has no such field. Add `cited_packages: list[Ref]`.

**D3 — a stale ADR, where the code is right.** ADR-004 says `ValidityEnvelope.conditions` is "required and non-empty"; the implementation makes it optional and defends the choice in its docstring and in `test_envelope_defaults_are_empty_not_permissive`. Record the drift; the ADR is what should move.

### 8.3 Structural changes

**G1 — path-preserving lowering.** Add `path: str` to `ValueSource`, or `bound_from: dict[str, str]` to `StageSpec`. Without it the deterministic half of the parameter space has no edge into any run.

**G2 — `Source` and `Assumption` schemas**, shaped like ADR-026's model trio.

**G3 — `Claim` as a content-addressed object** (§12).

**G4 — schematize the assessment surface**: `Verdict`, `ExcludedRun`, `manifest.json`, the four `metrics/*.json` files, the three prose registers, and the `evidence_grade` enum.

**Coverage declaration** — generalize ADR-007's empty-vs-missing rule so "not assessed" is a recorded state on every audit dimension, and remove the `validity` default that currently converts *never considered* into *asserts nothing*.

---

## 9. Extension seams to preserve now

Each is text or a single optional field; none requires implementation.

1. **`EvidenceAssessment` is derived, never authored** (§13). The single largest theater risk in the brief is a 13-field form filled in per claim.
2. **The evidence-graph index is a materialized freeze-time artifact**, recomputed by `verify` and refused on disagreement — the pattern `draw_order` (ADR-017) and derived bindings (ADR-029) already use. No database, no ontology (§15).
3. **Counterexample search is the external driver above the campaign layer** that ADR-005 already sanctions, with its two hard constraints preserved (§17).
4. **Boundary analysis is a declared reduction** over per-outer-point verdicts the campaign already computes (§16.F).
5. **The falsifier↔rule correspondence becomes a computed check.** ADR-009 says the claim's falsifier "is the exact restatement of" the acceptance rule; `verify` today checks only that a falsifier is *present*, and the correspondence is delegated to checklist item EV-1. Since `comparator`, `target` and `tolerance` are all structured, the restatement is mechanically checkable.
6. **Two renderer views** over one dataset, both deterministic and digest-pinned (§19).
7. **Audit dimensions are computed by `verify`, not authored.**

---

## 10. Changes to defer

Query CLI verbs (`farsight claims where …`); cross-package contradiction detection; optimizer-driven counterexample search; cross-campaign dominance indexing; anything requiring a second engine. All are additive once the graph is queryable, and none is needed before the first package ships.

---

## 11. Ideas rejected as audit theater

The brief's §15 invites this list, and it is the most useful section for protecting the principle from itself.

- **Any scalar confidence rollup — including `min(inputs)`.** The brief already resists this; I would reject it outright. Sensitivity *computation* subsumes it: perturb an input across its declared range and see whether the verdict flips. That is what the two-loop propagation already does, it produces an answer grounded in the model rather than in bookkeeping, and it cannot be gamed by relabelling an input.
- **"Assumptions dominating more than five downstream claims"** as a query. Fan-out count is a weaker proxy for what `sensitivity.json` already measures properly — dominance in FarSight is a computed share of envelope width, not a degree in a graph. Keep the sensitivity measure; drop the count.
- **A graph database or ontology.** The brief pre-empts this and is right: the graph is a freeze-time traversal over digests plus one materialized reverse index.
- **A separate "audit report" document type.** The evidence package *is* the audit artifact. A second document is a second source of truth, and ADR-007's whole renderer discipline exists to prevent exactly that.
- **Mandatory authored `EvidenceAssessment` forms.** A form is filled in once, rots, and becomes ritual. A derived projection is free per claim and always current.
- **Approval workflow beyond `review_signoffs`.** The existing structured sign-off is enough; sign-off *chains* are bureaucracy.
- **AI-generated validation statements**, per ADR-030 and ADR-025.
- **Arbitrary trust percentages** in any form.

---

## 12. Claim-domain recommendation

**Do not introduce a new plane. Promote `claim_statement` from a manifest field to a content-addressed object, and freeze it with the design rather than building it with the package.**

`claim_statement` is already about 70% of a Claim *as fields* — `sentence`, `referent_refs`, `comparator`, `tolerance_ref`, `tier`, `scope_conditions`, `falsifier`, `evidence_grade`, `partial`, `contains_epistemic_collapse` — and 0% as identity. What it lacks:

- **an identity**: no `claim_id`, no `schema_version`, no content hash, so nothing can reference it, contradict it, or supersede it. Every one of the brief's §8 queries requires this.
- **plurality**: one package supports exactly one claim; there is no `claims: []`.
- **downward pointers**: it names its criterion and its referents but *not its verdict, run set or aggregate*. The tie from a claim to the runs supporting it is directory co-membership — files in the same folder — rather than a reference. That is the single edge a reviewer most wants to walk.
- **pre-registration.** This is the deepest issue. Because the claim is built at package time, *after* results are seen, **HARKing is structurally invisible** — even though ADR-021 already provides pre-registration machinery for referents. FarSight can today pre-register *what it will measure against* but not *what it will claim*. For a platform whose thesis is falsification, that is backwards.

```python
# src/farsight/schemas/design.py -- frozen, extra="forbid", content-addressed (ADR-001)

class Claim(FrozenModel):
    schema_version: int
    claim_id: str                     # segment grammar; a name, never dispatched on
    sentence: str                     # the exact falsifiable statement
    falsifier: str                    # prose; must correspond to criterion_ref (checked, see 9.5)
    scope_conditions: list[str]       # the admissible-assumption envelope it holds within
    criterion_ref: Ref                # ADR-009 AcceptanceCriterion -- what decides it
    referent_refs: list[Ref] = []     # ADR-021 observations it is scored against
    cited_packages: list[Ref] = []    # closes D2
    supersedes: Ref | None = None
    revision_reason: str | None = None
```

In the package the claim is then *referenced*, with the execution-side pointers the manifest is entitled to add after the fact:

```jsonc
"claims": [
  {"claim_ref": "<64-hex>",        // frozen with the design, before any run
   "verdict": "pass|fail|indeterminate",
   "run_set": "<selector>",        // closes the missing downward edge
   "aggregate_ref": "<64-hex>",
   "tier": "B",
   "assessment": { /* derived; section 13 */ }}
]
```

**The lane rule that makes this work.** A conclusion nobody anticipated is legitimate and common — but it is a **finding**, not a claim. Findings live in the exploratory lane; a finding becomes a claim only by freezing a new design that tests it. This maps FarSight's existing `evidence_grade: exploratory | evidence` split precisely onto the confirmatory/exploratory distinction in experimental science, at no cost, using machinery that already exists. A claim whose digest is not in the frozen design is by construction post-hoc, and `verify` can say so.

**Retrofit cost: CHANGE NOW.** Claim identity is identity, and ADR-001 makes the identity scheme effectively permanent once packages ship. Today it is a schema addition; after the first package it is a migration of every shipped artifact.

---

## 13. EvidenceAssessment recommendation

**Derived, never authored.** This is the line between the principle and compliance theater, and it is worth being blunt: a mandatory 13-field object filled in per claim would be filled in once, rot, and become ritual — the "dozens of mandatory forms" §15 forbids. A *computed projection* over the evidence graph is free per claim, always current, and cannot be gamed by writing optimistic prose in a box.

```
farsight evidence assess <package> [--claim <ref>]  ->  evidence_assessment/1  (JSON, derived)
```

```jsonc
{"schema_version": "evidence_assessment/1",
 "claim_ref": "<64-hex>",
 "verdict": "indeterminate",
 "coverage": {                              // section 3.2: assessed, or explicitly not
   "provenance":        "complete",
   "assumptions":       "complete",
   "uncertainty":       "complete",
   "validity":          "violations_present",
   "sensitivity":       "complete",
   "reproducibility":   "tier_b",
   "independent_check": "not_assessed",     // the honest state, not a silent gap
   "contradictions":    "complete",
   "falsification":     "not_assessed",
   "expert_review":     "outstanding"},
 "evidence_quality": {"experimentally_established": 11, "peer_reviewed_model": 6,
                      "engineering_estimate": 4, "speculative": 2},
 "dominant_dependencies": [                 // from sensitivity.json: computed share, not fan-out
   {"path": "ground.palomar.receiver.optical_train", "share_of_envelope_db": 4.15,
    "pedigree": "engineering_estimate", "confidence": "LOW"}],
 "material_weak_dependencies": [            // section 14: computed, not propagated
   {"path": "...", "verdict_flips_within_declared_range": true}],
 "validity_violations": [],
 "unresolved_disagreements": [],
 "audit_status": {                          // the brief's section 6, kept multidimensional
   "provenance_complete": true, "reproducible": "tier_b", "numerically_stable": "not_assessed",
   "within_model_validity": false, "independent_check_available": false,
   "counterexample_search_completed": false, "epistemic_dependencies_identified": true,
   "external_expert_review_completed": false, "experimental_validation_completed": false},
 "expert_review_required": ["optical communications"],
 "reproduce": {"package_root": "<64-hex>", "command": "farsight evidence verify <pkg>"}}
```

Every field is computed from data already required to exist. `coverage` is the §3.2 reformulation made mechanical. `audit_status` is the brief's §6, kept multidimensional and deliberately never collapsed to a score.

---

## 14. Evidence-inheritance recommendation

The brief is right to reject `final_confidence = min(inputs)`, and the right answer goes further: **do not aggregate confidence at all. Compute the dependency instead.**

"Does this conclusion depend materially on a weak assumption?" is not a bookkeeping question about metadata. It is an empirical question about the model, and it has a computation: **perturb the input across its declared range and see whether the verdict changes.** FarSight already has that machinery — the outer epistemic scan evaluates every criterion at every outer point, so the answer is a *reduction over results the campaign already produced*, not a new analysis.

Evidence inheritance therefore becomes four computed facts per claim, none of them a number on a scale:

1. **Material dependency on low-confidence inputs** — the verdict flips somewhere within the declared range of an input whose pedigree is `expert_judgment` or `speculative`.
2. **Sensitivity share** — from `sensitivity.json`: how much of the envelope width each named epistemic term contributes. This is what "dominant" means here, and it is why fan-out counting is the weaker measure.
3. **Unsupported extrapolation** — a model used outside its `ValidityEnvelope.ranges`, from the validity-violation register.
4. **Unresolved model disagreement** — a Tier-C comparison whose non-shrinking residual maps to no declared unmatched item.

The brief's worry — that a mission conclusion becomes HIGH-confidence because the downstream mathematics is precise — is answered structurally rather than by propagation: if the verdict flips within a speculative input's declared range, fact (1) fires no matter how precise anything downstream is. The evidence graph preserves the lineage so a reviewer can walk it, which is the durable requirement.

---

## 15. Evidence / dependency graph assessment

**The graph is about 70% reconstructible today, forward-only, from one package.** These edges already exist as hashed references or as validated single-valued paths: Source→Belief (`Pedigree.sources`), Source→Model and Assumption→Model (`ModelVersion.source_refs`, `assumption_refs`), Assumption→Unknown (`bounding_assumption_ref`), Belief→Parameter (`ParameterBinding.path`), Design→Run (the `plan_run` derivation), Parameter→Run for *aleatory* draws (`seeds_<i>.json`, `draw_order`), Run→Metric (`output_hash`), Metric→Channel (`MetricSpec.inputs[].channel`), Metric→Criterion (`metric_ref`), Criterion→Claim (`tolerance_ref`), Claim→Referent (`referent_refs`), Model→excursion (`validity_flags`), and supersession throughout.

**Four edges are broken** — §7's G1–G3 plus the missing Claim→evidence pointer: Model→Run (no `model_ref` on `StageSpec`), Parameter→Run for deterministic and derived values (the path is dropped at `ValueSource`), Assumption→any non-`Unknown` belief (no edge type exists), and Claim→Verdict/run-set.

**The reverse direction is absent by construction, and should stay that way.** A back-pointer would change the hash of the object pointed at, and ADR-001 forecloses annotating frozen objects.

**Recommendation — a materialized reverse index, not a database.** Build the dependency index at freeze, write it into the hashed record, and have `verify` recompute it and refuse disagreement. That is exactly the pattern `draw_order` (ADR-017) and materialized derived bindings (ADR-029) already use, twice, successfully. `registers/assumptions.json` is already mandatory and already promises the reverse half in prose — give it a row schema and an enforcement test, and the graph becomes queryable per package with no ontology, no graph store, and no new plane.

Cross-*package* queries (the brief's "dominates in five studies") need an index over many packages. That index is a **regenerable cache**, never a source of truth — which keeps ADR-011's deliberate no-database decision intact, because a cache can be deleted and rebuilt by walking packages.

---

## 16. Automatic challenge-suite architecture

Mapping the brief's six classes onto what exists:

**A. Integrity — GREEN, the strongest class, partly implemented.** Canonical JSON with five distinct refusals each naming a JSON pointer; cross-process hash stability proven by a subprocess test under a different `PYTHONHASHSEED`; Tier A/B/C with the environment fingerprint as the Tier-A predicate; `ci-worker-order-invariance` (identical root hashes at `--workers 1` and `--workers 8`); the golden attestation with no `farsight_output` enum member; the re-golding guard, described in its own record as "the tolerance-inflation kill in mechanical form." **Add:** `schema_version` (C5) and the C1 validation-on-copy repair, without which integrity checking rests on unvalidated objects.

**B. Numerical — designed, unbuilt.** Tier-B tolerances with mandatory per-channel rationale; Richardson discrimination (run at τ and τ/100 — if the delta shrinks it is integration error, if it does not it is model mismatch that must map to a declared unmatched item or the comparison does not ship); replay at both tiers. Nothing to add architecturally.

**C. Model — GREEN.** Capability flags as the planning surface with a paired behavioural test per flag (`supports_midrun_intervention == False` requires that `apply_intervention` *raises* — a silent no-op fails the suite); `state_handoff` gating `segment_split`; matched configuration enumerating *unmatched* items; refusal at freeze naming the fault and the engine. **Add D1**, so "which model produced this number" is answerable.

**D. Assumption — YELLOW.** Mandatory `Pedigree` with at least one source unless `speculative`; `Unknown.freeze_ready()`; the unknowns invariant (no point value for a declared unknown appears anywhere in the package). **Add G2** so assumptions are objects, and the coverage declaration so "not assessed" is recorded.

**E. Uncertainty — GREEN with one defect.** The asymmetric API is implemented and guarded by *absence* tests; `outer_scan_convergence` gates evidence-grade packages on a width still growing between n/2 and n; `vertex_selection` is hashed spec content with a determinism test. **Repair C3 and C4.**

**F. Boundary — the cheapest new capability in the brief.** "Where does the conclusion stop being true?" is already computed and merely unnamed: criteria are evaluated at every outer point, so the pass/fail boundary over the admissible set is a *reduction over verdicts the campaign already produced*. Reserve `metrics/boundary.json` and a declared reduction. No new sampling, no optimizer.

**G. Counterexample — section 17.**

---

## 17. Counterexample-search seam

Adaptive search is **structurally excluded** from a campaign, deliberately: all randomness is pre-planned, so Bayesian optimization, importance sampling with a fitted proposal, and adaptive stratification "cannot be expressed at all." That exclusion is what makes run #4242 addressable, and it should not be relaxed.

The seam already exists and is precisely specified: **an external driver above the campaign layer.** It sits outside FarSight, treats one frozen `ExperimentDesign` as one function evaluation, reads results from package JSON or the `--json` contract, and emits the next design as a new draft. Every probe remains a fully hashed, replayable campaign; iteration happens in the exploratory lane; frontier points the team stands behind are re-frozen *attended* into evidence-grade campaigns. **This requires no schema change and could be built today.**

Two constraints must be carried into any such driver, both already stated in the corpus: no preference weights inside a hashed design or criterion (that would put scalarization into the scientific record), and **criteria held fixed across a series** — an optimizer that tunes acceptance thresholds is automated tolerance-shopping, and the allowed count of undocumented loosenings is zero.

One addition from §3.3: **a counterexample search records the space it searched**, and a negative result is never reported without it. ADR-004 already admits the matching blind spot — one-at-a-time corner screening "will miss a corner that is only extreme through an interaction, and nothing in this design detects that case" — so "no counterexample found" must always carry the caveat that makes it honest.

---

## 18. Expert-review integration

ADR-030 and `EXPERT_REVIEW_BACKLOG.md` already do this work: deferred external gates, a closed claim vocabulary enforced by lint, and a ledger of seven entries including the ten hand-over questions from the K2 review.

The one addition self-auditability implies: **`expert_review_required` becomes a computed field of the assessment, not only a hand-maintained ledger.** When a claim depends materially on an input whose pedigree is `expert_judgment` or `speculative`, the assessment names the discipline required and cross-references the backlog entry. Per the brief's §11, that output is a *successful audit result*, not a failure. The backlog remains the human-readable ledger; the assessment is how a claim announces its own outstanding review requirements without anyone having to remember to write them down.

---

## 19. Reporting implications

The brief's §10 asks reports to lead with weaknesses. There is a real tension to resolve rather than a preference to assert: **plan §9 mandates margin-first presentation** — "here is your margin against the requirement, here is the guaranteed bound, and here, one click down, is which unknown is eating your margin" — on the grounds that interval-only refusal is how the p-box literature stayed academic. §10 mandates weakness-first. ADR-007 pins exactly one renderer and one `summary.md` digest.

**Resolution: two deterministic views over one dataset, both digest-pinned.** They answer different questions from the same JSON. The *decision* view answers "does my link close, and what is eating my margin". The *audit* view answers "should I believe this", ordered per §10: claim, audit status, dominant assumptions, low-confidence dependencies, validity violations, counterexamples and failure boundaries, conflicting evidence, outstanding expert review, and only then the supporting numbers. Neither is hand-editable; both are re-rendered and byte-compared by `verify`.

This is additive but schema-affecting — a second rendered artifact needs a second digest field in the manifest — so it is cheaper before packages ship than after.

---

## 20. Concrete code areas affected

| Area | Change |
|---|---|
| `src/farsight/schemas/belief.py` | C1 (validate on copy in `Aleatory.at`), C2 (refuse resolving an already-pinned hyperparameter), C3 (`CollapseScope` carrying parameter paths; justification 120), C4 (`enumerate_outer` raises rather than under-delivering), C5 (`schema_version`), and removal of the `validity` default that erases *not assessed* |
| `src/farsight/schemas/common.py` | `schema_version` on `FrozenModel`; name the validator length constants and tie each to its ADR; document the `-30` exponent threshold in `normalize_decimal` |
| `src/farsight/schemas/design.py` *(new)* | `Claim`, `ClaimResult`; `ValueSource.path` (G1) |
| `src/farsight/schemas/knowledge.py` *(new)* | `Source`, `Assumption` (G2); `StageSpec.model_ref` (D1) |
| `src/farsight/schemas/execution.py` *(new)* | `Verdict`, `ExcludedRun`, `AggregateResult` (G4) |
| `src/farsight/evidence/` | `assess.py` (the derived assessment); the manifest schema; the reverse-index builder and its `verify` recomputation; the falsifier-to-rule correspondence check |
| `tests/unit/` | `test_model_copy_cannot_mint_identities`, `test_at_refuses_pinned_hyperparameter`, `test_collapse_scope_carries_paths`, `test_enumerate_outer_refuses_unimplemented_plan`, `test_schema_version_present_on_hashed_models` |

---

## 21. ADRs to add or amend

**New records:**
- **ADR-031 — The Self-Auditability Principle.** The reformulated text (§3.7), the materiality test, the coverage-declaration rule, the derived-not-authored constraint on assessments, and the explicit rejection list from §11 so that future proposals have text to argue against.
- **ADR-032 — Claim identity and the evidence graph.** `Claim` as a design-plane content-addressed object; the finding-versus-claim lane rule; the materialized reverse index; the regenerable cross-package cache.

**Amendment lines** (in References, per ADR-000 — no accepted Decision is edited):
- **ADR-007** — `claims: []` replacing the singular `claim_statement`; `cited_packages` (D2); the second renderer view; coverage fields on the registers.
- **ADR-009** — the falsifier-to-rule correspondence promoted from checklist item EV-1 to a computed check.
- **ADR-018** — `StageSpec.model_ref` and `ValueSource.path` (D1, G1).
- **ADR-026** — a note that its `model_binding_consistent` validator presupposed the field D1 adds.
- **ADR-004** — the C3 repair, and the D3 drift where the code is right and the ADR is stale.

---

## 22. Migration impact

**None, and that is the point of doing it now.** No package has been built, no design frozen, no golden hash recorded; `tests/golden/` and `tests/engine_contract/` are empty directories. Every change above is a schema addition to objects that have never been hashed. The same work after the first evidence-grade package ships would be a migration of every shipped artifact plus a permanent reader for the old shape — and ADR-001 says the identity scheme cannot change once customers hold packages.

The five code repairs touch two modules and the 112 currently-passing tests. C1 in particular requires a new test, because the existing `test_beliefs_are_frozen` passes for the wrong reason.

---

## 23. Ordered implementation recommendations

1. **C1** — validation on copy. Everything else assumes a content address means a validated document.
2. **C2–C5** — the remaining code repairs, all within `belief.py` and `common.py`.
3. **ADR-031** — ratify the reformulated principle, so subsequent work has a decided scope.
4. **G2, D1, G1** — `Source`/`Assumption` schemas, `model_ref`, path-preserving lowering: the three broken graph edges.
5. **ADR-032 and `Claim`** — identity, the lane rule, and the reverse index, before the first design freeze.
6. **G4** — schematize the assessment surface, before the first package build.
7. **The derived `assess`** and the coverage declaration.
8. **Seams as text**: the boundary reduction, the external-driver constraints, the second renderer view.

Items 1–2 are hours of work. Items 3–6 belong in the week-2/3 schema window. Items 7–8 follow the evidence package in week 4.

---

## 24. Risks of doing too little

The identity guarantee stays false, and every downstream claim about reproducibility inherits that (C1). Deterministic and derived parameters remain invisible in lineage, so the first honest answer to "what does this conclusion depend on" is "we can tell you about the random half" (G1). Claims cannot be referenced, contradicted or pre-registered, so HARKing stays structurally invisible in a platform whose entire thesis is falsification (G3). The assessment surface hardens as prose at the first package, and the brief's §8 queries become permanently unavailable (G4). And the corpus's two internal contradictions (D1, D2) surface in week 5 as a validator that cannot run and a capability with no field — discovered under schedule pressure rather than now.

---

## 25. Risks of over-engineering

Larger, and more likely, than the risk of doing too little. The brief's §15 is the right instinct and this review has tried to honour it. The specific failure would be: a mandatory `EvidenceAssessment` form per claim; a confidence score nobody can defend; a graph database for a graph that is a freeze-time traversal; an approval workflow layered on `review_signoffs`; and a second "audit report" document competing with the evidence package for authority. Each would add ceremony while *reducing* useful inspectability, because effort would move from computing facts to filling in boxes.

The discipline that prevents this is one the corpus already uses twice: **closure by inexpressibility.** The golden attestation has no `farsight_output` enum member, so the rule cannot be violated rather than merely being forbidden; `StageInput`'s three members cannot name a run. New audit rules should be built the same way — make the wrong thing unsayable — rather than by adding a field that asks an author to promise they did the right thing.

---

## 26. Final recommendation

**Ratify the principle with the three amendments in §3** — define materiality, require declared coverage rather than completeness, and replace the "easier to challenge than to accept" clause with a measurable one — **and add the two missing clauses** on independent recomputability and durable negative results.

Then repair the five code defects, close the two ADR contradictions, add the three broken graph edges, and give Claim an identity before the first design is frozen. Everything else — assessments, boundary analysis, counterexample search, queries — is derived or external, and needs seams rather than construction.

The strongest evidence for this principle is what happened the first time it was applied. Pointed at FarSight's own implementation, it found within minutes that content addresses can be minted for documents that never passed a validator — in code written by the same process that wrote the tests meant to catch it. A system that finds that about itself, on the first run, is worth building.

**Status of this document:** `research-reviewed; internally cross-checked; not externally expert-reviewed`. Every code defect here was reproduced by execution and every ADR contradiction verified by citation; none of it has been reviewed by an external software architect, and per ADR-030 that review remains a deferred gate.
