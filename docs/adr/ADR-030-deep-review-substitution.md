# ADR-030 — Deep Review substitution under expert unavailability
**Status:** Accepted 2026-08-29 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-29
**Deciders:** FarSight founding engineering, on founder direction
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §17 (week-2/week-7 expert review), §18 AT-9 (external audit), §19 risk 2 (missing-term risk, "the highest-ROI spend"), §21 (gates)
**Related ADRs:** ADR-000 (`review_signoffs` and the checklist-id machinery this record extends), ADR-004 (pedigree levels; Deep Review outputs carry evidence-taxonomy labels that refine `expert_judgment`), ADR-021 (referents and the pre-registration discipline Deep Reviews must respect), ADR-006 (golden provenance — a Deep Review may never be a golden source), ADR-026 (`VerificationStatus.level`, which this record's vocabulary constrains)

## Context

The plan assumes access to domain experts at specific points: an optical-communications specialist reviews the DSOC parameter table in week 2 and the final package in week 7 (§19 risk 2 calls this "the highest-ROI spend in the plan"), and an external aerospace engineer performs the week-8 cold audit (AT-9). The founder has now directed that **no reliable expert access exists for the current phase** — not optical comms, not aerospace V&V, not propulsion, not mission assurance.

The naive responses are both wrong. Skipping the review steps silently converts every `expert_judgment` pedigree into an unexamined assumption — the exact rot the product exists to prevent. Waiting for access stalls a gate (K2) that is currently blocking the flagship decision. The founder's directive threads this: substitute the strongest available research process, under one strict rule that decides everything else in this record — **the absence of an expert must increase epistemic uncertainty, never lower the bar for claiming something is known.** A research process that produces tighter bounds than an expert would have is not a substitute; it is a leak.

What concretely breaks if this is done badly: a bound narrowed on a secondary source ships inside a pre-registered envelope; a document says "validated" where nothing was; the temporary absence of experts hardens into permanent forgotten debt because nothing tracked what was skipped. Each failure mode gets a mechanism below.

## Decision

**1. The Deep Review protocol substitutes wherever the plan or an ADR calls for external domain review.** A Deep Review is a stored artifact (committed to the repo, under the experiment or decision it reviews) executing, in order: (1) state the claim under review; (2) identify the assumptions it depends on; (3) find the strongest primary evidence for it; (4) find the strongest evidence against it; (5) reconstruct the key calculations independently; (6) compare alternative models; (7) identify validity envelopes; (8) identify unresolved disagreements — reported, never averaged away; (9) assign an evidence-referenced confidence; (10) state what an eventual human expert would specifically need to review, verbatim, so it can be handed over without this context. Primary sources only where they exist (agency publications, peer-reviewed papers, official documentation, standards, mission reports); every material number triangulated across independent sources; paywalled sources used at abstract level are labelled as such.

**2. Every research-derived number carries an evidence-taxonomy label**, from exactly this closed set: `experimentally-established | flight-demonstrated | ground-demonstrated | peer-reviewed-model | engineering-estimate | extrapolation | expert-judgment-in-literature | speculative`. This refines, and does not replace, ADR-004's `PedigreeLevel` on beliefs: a `ParameterBelief` whose bound comes from a Deep Review keeps its pedigree machinery and gains the taxonomy label in its rationale text.

**3. Confidence is evidence-referenced, on a four-level scale:** `HIGH` (demonstrated physics, multiple independent sources, or independent reconstruction), `MEDIUM` (strong support with meaningful extrapolation remaining), `LOW` (limited data, early technology, significant model dependence), `SPECULATIVE` (conceptually plausible, insufficient evidence for an engineering assessment). Confidence refers to the evidence supporting the claim, never to how persuasive the reasoning reads — a beautifully argued extrapolation is still an extrapolation.

**4. The claim vocabulary is closed, and the forbidden half is linted.** Permitted status terms for research-derived conclusions: `research-reviewed`, `internally cross-checked`, `literature-supported`, `independently reconstructed`, `not externally expert-reviewed`. Forbidden, unless the event has genuinely occurred: `expert validated`, `expert-reviewed` (as a claim of human expert review), `independently validated`, `certified`, `flight qualified`, `verified by aerospace experts`. A Deep Review is research. It is never described as equivalent to expert review, independent V&V, certification, flight qualification, or formal engineering validation — including in commit messages, READMEs, and demo material.

**5. External review converts to deferred gates, not deletions.** The standing gate list, verbatim:

```text
EXTERNAL REVIEW REQUIRED BEFORE:
- claiming a validated physical model
- publishing strong engineering conclusions
- entering mission-critical use
- claiming flight relevance
- certification / assurance usage
```

AT-9's external cold audit remains in the acceptance tests, marked **deferred gate: satisfiable only when external access exists**; until then, the week-8 demo claim downgrades from "externally audited" to "audit-ready, research-reviewed", and the audit's role is filled by an internal cold audit performed by whoever did not build the package, recorded as such. The founder's Stage-gate claims (validated model, flight relevance) are unreachable this phase by construction, which is the honest position.

**6. `EXPERT_REVIEW_BACKLOG.md` (repo root) is mandatory and append-biased.** Every topic that would materially benefit from eventual human review gets an entry: topic, specific claim/question, discipline, why review matters, current evidence state, current confidence, unresolved questions, consequence if wrong, priority (`CRITICAL | HIGH | MEDIUM | LOW`). Entries are updated when evidence changes and closed only by an actual external review. A Deep Review's step-10 hand-over questions land here the day the review is stored — that is what keeps the temporary constraint from becoming invisible debt.

**7. Interaction with pre-registration (ADR-021) stated once:** a Deep Review that revises a pre-registered artifact never edits it — it produces a superseding artifact, itself committed before any data purchase it motivates. And a Deep Review respects the referent boundary absolutely: sources may constrain hardware and environment inputs; achieved-performance data that will later score the prediction may not be used to tune anything, and each review's artifact states that audit explicitly.

## Options considered

### Option 1 — Pause every gate that names an expert until access exists — REJECTED
The conservative reading, and it has one virtue: no risk of over-claiming. Rejected because it converts a resourcing constraint into a schedule stall on the project's critical path (K2 was blocking the flagship decision), and because "paused" reviews rot silently — the parameter table would have shipped into week 3 with `expert_judgment` bounds nobody re-examined, which is *worse* than a disciplined research pass, not safer.

### Option 2 — Proceed on the existing judgment bounds and flag them — REJECTED
Cheapest. Rejected because the first Deep Review's actual result refutes it empirically: research on the K2 table found the judgment bounds were not merely imprecise but *structurally wrong* — three silently-fitted terms (a half-power transmitter, a 12.5% aperture obscuration, a range error) that no amount of flagging would have surfaced. Flagged wrong numbers are still wrong numbers.

### Option 3 — Treat Claude-assisted research as equivalent to the expert review and close the gates — REJECTED
The tempting over-claim, rejected on the founder's own strict rule. A research process cannot answer the ten questions the K2 review itself hands over (was the filter installed on that pass? what convention does "sub-microradian" use?) — those need a human with access to unpublished data. Describing research as validation would also poison the product's central pitch: a company selling scientific honesty cannot practice grade inflation internally.

### Option 4 — Deep Review protocol + closed vocabulary + deferred gates + backlog — CHOSEN
Proceeds without stalling, widens rather than narrows under uncertainty, keeps the eventual human review as a first-class future gate, and leaves an auditable boundary between what we established ourselves and what still requires an expert or an experiment.

## Consequences

**Buys us:** unblocked gates with better-grounded numbers than the judgment bounds they replace (the first Deep Review moved every K2 bound onto cited sources and found three material errors). A permanent, auditable record of what was *not* expert-reviewed, so the constraint cannot silently become the norm. Vocabulary discipline that survives into demos and sales material mechanically rather than by memory.

**Costs us:** Deep Reviews are expensive — the K2 review consumed a four-agent research campaign over ~225 source fetches, versus two hours of a specialist's time; that ratio is the price of the constraint. Wider bounds in the near term: the honest direction, but demos get less impressive (K2's envelope *widened* past the demote threshold under this policy). And a standing risk this record can only mitigate: research reads persuasively, and the confidence-refers-to-evidence rule is enforced by discipline plus review, not by a compiler.

**Forecloses:** any claim of validated physics, flight relevance, or certification during this phase, no matter how strong the research looks — the deferred gates are absolute. It also forecloses using Deep Review output as golden data: ADR-006's rule that a golden number may never originate from our own code extends to our own research syntheses; goldens still come only from archived primary artifacts.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Deep Review protocol as the substitute (vs pausing) | 0.85 | A Deep Review ships a bound later shown wrong in a direction an expert would have caught — one occurrence forces a protocol post-mortem, two reopen Option 1 for gate-critical items |
| Widen-never-narrow as the operating rule | 0.9 | None expected; this is the founder's directive and the product's own philosophy |
| Closed claim vocabulary + lint | 0.8 | The lint's false-positive rate makes authors route around it (>3 allowlist additions in a month), or a forbidden phrase ships in external material anyway — either means the mechanism, not the rule, needs rework |
| Deferred gates rather than deleted steps | 0.9 | Expert access materializes — then each backlog item converts to a scheduled review and this record's substitution clause sunsets for that discipline |
| Backlog as the debt ledger | 0.75 | The wk-8 internal cold audit finds a research-derived claim in the demo with no backlog entry — the ledger failed silently, which is its one job |
| Internal cold audit as the AT-9 stand-in | 0.7 | The internal auditor cannot complete the two-hour audit or judges it theater — then AT-9 has no honest substitute and the demo claim must say so outright |

## Enforcement

1. **`test_no_false_validation_claims`** (unit tier, **first green immediately** — it ships with this record): scans every `.md` under `docs/`, `experiments/`, and the repo root for the forbidden phrases of decision 4. A line matching a forbidden phrase fails unless it is a quotation, negation, or definition context (the line also matches a negation/quoting pattern) or is explicitly allowlisted in the test with a reason. **PARTIALLY MECHANIZED: REVIEW-1** — a grep recognizes phrases, not claims; a forbidden claim in novel wording passes it cleanly. Review-checklist item **REVIEW-1** — *"does any external-facing text claim a validation event that did not occur?"* — is a second-person sign-off recorded in `review_signoffs` on every evidence-grade package and before any external demo.
2. **`test_expert_review_backlog_exists`** (same module): `EXPERT_REVIEW_BACKLOG.md` exists at the repo root, is non-empty, and every entry carries the required fields (topic, claim, discipline, evidence state, confidence, consequence, priority) — checked structurally by section headers.
3. **Deep Review artifact convention** (NOT MECHANIZABLE: REVIEW-2): every Deep Review artifact carries the status line `research-reviewed; internally cross-checked; NOT externally expert-reviewed` and its step-10 hand-over questions must appear in the backlog in the same commit. Item **REVIEW-2** — *"does this review's residue actually reach the backlog, and does its confidence cite evidence rather than eloquence?"* — recorded in `review_signoffs` per review.
4. **ADR-026 coupling:** `VerificationStatus.level` may not be raised to `referent_compared` or `cross_model` on Deep Review evidence alone unless the underlying comparison actually ran; a Deep Review never raises a verification level by itself (it is literature, not a run).

## References

- Founder directive, 2026-08-29 (this record is its codification; the directive text is the authority on the protocol steps, the taxonomy, the confidence scale, the vocabulary, and the backlog format).
- FARSIGHT_FOUNDATION_PLAN.md §17, §18 AT-9, §19 risk 2, §21.
- First executed instance: `experiments/dsoc_k2/K2_DEEP_REVIEW.md` (the DSOC parameter table review that this policy's rules shaped, and whose outcome — a *widened* envelope crossing the demote threshold — is the empirical case that the widen-never-narrow rule has teeth).
- PLAN AMENDMENT REQUESTED: §17 — the week-2 and week-7 optical-comms expert reviews are replaced this phase by Deep Reviews (the week-2 instance is executed), with the human reviews converted to backlog entries; §19 risk 2's "highest-ROI spend" note stands as a statement about the future purchase, not a current step.
- PLAN AMENDMENT REQUESTED: §18 — AT-9 becomes a deferred gate; its interim substitute is an internal cold audit by a non-author, and the demo claim downgrades to "audit-ready, research-reviewed; not externally expert-reviewed".
- PLAN AMENDMENT REQUESTED: §22 — the ADR list runs to ADR-030 (thirty-one records).
