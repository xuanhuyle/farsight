# ADR-004 — Belief tagged union, two-loop propagation, and authorized EpistemicCollapse
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §9, decision D7 (also §7 pedigree/validity, §13 registers, §19 risk 3)
**Related ADRs:** ADR-001 (beliefs are hashed spec content, so decimal-string quantities and the freeze protocol define when an `Unknown` must resolve), ADR-005 (seed derivation is what makes the inner aleatory loop replayable and outer-point addressable), ADR-006 (the outer loop draws no random numbers, which is what keeps Tier A bitwise), ADR-007 (the unknown and judgment registers are this ADR's output contract), ADR-008 (units and the SI float64 core define what `sample()` returns), ADR-009 (the `indeterminate` verdict exists because an epistemic band can straddle a threshold), ADR-010 (the fault model reuses this type rather than defining a second uncertainty system), ADR-013 (`schemas` imports nothing internal, so `belief.py` is the bottom of the stack), ADR-017 (topology paths are what a `ParameterDecl` binds to and what breaks ties in the vertex-selection rule), ADR-021 (a `ReferentPoint`'s stated uncertainty is a `Belief`, or this ADR's guarantee has a hole at the comparison step), ADR-022 (the distribution families and the sampler stream stability the inner loop rests on), ADR-023 (which run outcomes are permitted to enter the aggregate the p-box is built from)

## Context

The forcing question is what type a parameter has when we do not know its value. FarSight's flagship benchmark makes this concrete and unavoidable: the DSOC link prediction is dominated by quantities that are not random variables at all. Per-pass atmospheric transmission, seeing and sky radiance; ground-receiver optical-train throughput; the flight terminal's actual EIRP and its degradation; the per-pass pointing-loss distribution; and the operational margin policy that governs which rate the operators actually selected. The fact pack is explicit that these must never be fitted. They have no measurement, no published distribution, and no defensible prior. What we do have is a public rate ladder, published achieved points frozen as cited, hash-pinned `DataArtifact`s per plan §14 item 5 (the 267 Mbps points are hardware-capped), and an honest achievable precision of plus or minus 2-3 dB, about one ladder step — the figure plan §1 commits to, against the 20% agreement it explicitly refuses.

If those unknowns are given uniform priors and pushed through a flat Monte Carlo, the first number FarSight ever prints is a P95 supportable rate. That number would be an invented fact with a probability attached to it, produced by the tool whose entire commercial claim is that it does not invent facts. Plan §19 risk 3 says it plainly: the epistemic treatment is the flagship's load-bearing wall, and the aleatory machinery is barely exercised. There genuinely is aleatory content in the model (SNSPD counting statistics, per-run pointing jitter realization, per-pass weather draw), so an interval-only system would throw away structure we actually know.

Concretely, getting this wrong breaks: AT-6 (a RunSpec assigning a point value to a flagged unknown must be rejected by schema); AT-5 (the envelope must be decidable and at most 6 dB wide, so bound construction must be a designed scan, not a worst-corner stack); K6 (the shipped package must name at least one dominant unknown with quantified sensitivity); and the "which measurement would halve this" artifact that plan §1 calls the headline deliverable. It also breaks the acceptance verdict domain, since `indeterminate` (ADR-009) only means something if the band that straddles the threshold is a real object rather than a percentile.

There is a second, sharper forcing question hiding inside the first, and it is the one this record was weakest on before review. AT-5 passes when the envelope is **at most** 6 dB wide and K2 kills DSOC when the hand-computed envelope **exceeds** 12 dB. Both are criteria on a width, and the width we report is a finite-sample *inner* bound on the true p-box. An under-sampled outer scan therefore makes the flagship's acceptance test **easier** to pass. Any design that leaves the outer scan's coverage unspecified has put the honesty product's headline number at the mercy of an unstated input.

## Decision

Uncertainty is a Pydantic v2 discriminated union, `Belief`, with five members and a deliberately asymmetric API. There is no method anywhere in the codebase named `to_distribution`.

```python
# src/farsight/schemas/belief.py  -- all models: ConfigDict(extra="forbid", frozen=True)

PedigreeLevel = Literal["measured_flight", "measured_ground_test", "published_design",
                        "derived_analysis", "expert_judgment", "speculative"]

class Pedigree(BaseModel):
    level: PedigreeLevel
    sources: list[SourceRef]          # >= 1 required unless level == "speculative"
    assessor: str
    assessed_on: date

class ValidityEnvelope(BaseModel):
    conditions: list[str]             # free text, but required and non-empty
    ranges: dict[str, IntervalQ]      # e.g. {"range_au": ("0.10", "3.00")}
    time_span: TimeSpan | None

class Deterministic(BaseModel):
    kind: Literal["deterministic"] = "deterministic"
    value: Quantity                   # decimal string + unit, per ADR-001
    pedigree: Pedigree
    validity: ValidityEnvelope
    def sample(self, rng: Generator) -> float: ...        # SI float64

class Aleatory(BaseModel):
    kind: Literal["aleatory"] = "aleatory"
    distribution: Distribution
    sampling_scope: SamplingScope   # "per_run" | "per_experiment" | {"per_group": "<name>"}
                                   # ADR-027: `per_pass` is retired in favour of the group form,
                                   # which names a ScenarioEnumeration the scenario declares.
    correlation_group: str | None = None
    pedigree: Pedigree
    validity: ValidityEnvelope
    def at(self, point: OuterPoint) -> "Aleatory": ...    # returns a resolved Aleatory
    def sample(self, rng: Generator) -> float: ...        # resolved instances only

class EpistemicInterval(BaseModel):
    kind: Literal["epistemic_interval"] = "epistemic_interval"
    lower: Quantity
    upper: Quantity
    rationale: str                    # >= 40 chars, validator-enforced
    pedigree: Pedigree
    validity: ValidityEnvelope
    def enumerate_outer(self, plan: OuterPlan) -> list[OuterCoordinate]: ...

class EpistemicSet(BaseModel):
    kind: Literal["epistemic_set"] = "epistemic_set"
    members: list[Quantity] | list[ModelVersionRef]   # enumerated, NEVER weighted
    rationale: str
    pedigree: Pedigree
    validity: ValidityEnvelope
    def enumerate_outer(self, plan: OuterPlan) -> list[OuterCoordinate]: ...

class Unknown(BaseModel):
    kind: Literal["unknown"] = "unknown"
    what_is_missing: str              # the sentence that lands in the unknown register
    sweep_declaration: SweepDeclaration | None = None
    bounding_assumption_ref: AssumptionRef | None = None
    pedigree: Pedigree                # level is typically "speculative"
    # freeze validator: at least one of sweep_declaration / bounding_assumption_ref

Belief = Annotated[
    Deterministic | Aleatory | EpistemicInterval | EpistemicSet | Unknown,
    Field(discriminator="kind"),
]
```

`sample(rng)` exists only on `Deterministic` and `Aleatory`. The epistemic kinds expose only `enumerate_outer(plan)`. `Unknown` exposes neither and cannot be sampled at all; at freeze it must resolve to a declared sweep or a named bounding assumption, and it keeps its `unknown` identity in the register even after it acquires a numeric bracket. That distinction is deliberate: an `EpistemicInterval` is a knowledge claim about where the value lies, while an `Unknown` with a sweep declaration is an admission that we have no measurement and are scanning a bracket we chose, stamped "NOT FITTED" in the package.

Distribution hyperparameters may themselves be epistemic. This is the flagship pattern:

```yaml
- decl: tx.pointing_jitter_sigma
  belief:
    kind: aleatory
    sampling_scope: per_run
    distribution:
      family: rayleigh
      params:
        sigma:
          kind: epistemic_interval
          lower: {magnitude: "0.16", unit: "urad"}     # lab-measured
          upper: {magnitude: "1.0",  unit: "urad"}     # flight published only as "sub-microradian"
          rationale: >
            Lab measurement gives 0.16 urad. Flight publications state a qualitative
            sub-microradian bound only. Upper edge reads that bound as 1.0 urad.
            NOT FITTED to any achieved-rate point.
```

`Distribution.params` accepts `Quantity | EpistemicInterval | EpistemicSet` and nothing else. An `Aleatory` hyperparameter (a hierarchical model) and an `Unknown` hyperparameter are both rejected at construction: the first needs marginalization semantics we are not building, the second has no bracket to scan. An `Aleatory` with any non-`Quantity` parameter is *unresolved*; `Aleatory.at(point)` returns the resolved copy with the outer coordinate substituted, and `RunSpec` construction rejects any unresolved `Aleatory`, any epistemic kind, and any `Unknown`. A RunSpec is by construction fully pinned, which is the schema half of AT-6.

Propagation is two loops. The outer loop is a deterministic scan over the epistemic space with no RNG whatsoever: Latin hypercube points across interval-valued coordinates, plus the interval vertices (capped), plus exhaustive enumeration of every `EpistemicSet` and model family. The inner loop is a seeded aleatory Monte Carlo per outer point, addressed by `(outer_index, inner_index)` and derived from the root seed per ADR-005.

```yaml
sampling_plan:                  # illustrative values, not a commitment
  outer:
    design: lhs_plus_vertices
    lhs_points: 24
    include_interval_vertices: true
    vertex_cap: 64
    vertex_selection:                        # hashed spec content, not an implementation detail
      rule: oat_screening_rank
      screening_lane: exploratory
      tie_break: sorted_topology_path        # ADR-017
    set_enumeration: exhaustive
    convergence_report: [quarter, half, full]
    latent_factors: [wx_palomar_seasonal]     # shared epistemic/common-cause variables
  inner:
    draws_per_outer_point: 400
    sampler: lhs
    correlation_groups: [detector_chain]      # Gaussian copula, PSD-validated rank matrix
```

**The vertex-selection rule is spec content, not an implementation detail.** With d interval-valued epistemic coordinates the vertex set is 2^d, and the DSOC parameter table already carries roughly a dozen, so `vertex_cap` binds from the first campaign. Which vertices survive determines the reported bound, so the rule that picks them is declared in the frozen design and covered by `experiment_hash`. The MVP rule is `oat_screening_rank`: a one-at-a-time screening pass ranks the interval coordinates by the magnitude of their individual effect on the reported metric, the top k coordinates whose full 2^k enumeration fits under the cap are enumerated exhaustively, every remaining coordinate is held at the edge that was worse in screening, and ties are broken by sorted topology path. The screening pass runs in the `exploratory` lane; no value from it enters an evidence-grade result, only the choice of which corners get evaluated, so the exploratory taint does not propagate — but the choice is recorded and hashed, and changing the rule is a different `experiment_hash`, not a different run of the same experiment.

**The outer scan reports its own convergence.** `metrics/sensitivity.json` carries a mandatory `outer_scan_convergence` block giving the envelope width computed over the first quarter, the first half, and all of the outer points, in the deterministic order the design generates them. An evidence-grade package whose envelope width is still growing materially between n/2 and n fails `test_outer_convergence`. This does not prove enclosure and is not claimed to. It is the only instrument that distinguishes a narrow envelope from an unconverged one, and without it AT-5's 6 dB ceiling is a criterion an under-sampled scan passes by default.

Twenty-four outer points times four hundred inner draws is 9,600 runs, which is why the plan's 10k-run target (§11) is the ordinary shape of an evidence-grade campaign rather than a benchmark number invented for a demo.

The output is a family of empirical CDFs, one per outer point, plus their envelope. That envelope is reported as an **empirical p-box** with `n_outer`, the outer design, the vertex-selection rule and the convergence block recorded alongside it, and it is explicitly a *finite-sample inner bound* on the true p-box, not a proof of enclosure. There is no p-box arithmetic on inputs.

Dependence is split by kind. Aleatory dependence uses named `CorrelationGroup` objects (Gaussian copula over a PSD-validated rank matrix; Gaussian only in the MVP). Epistemic and common-cause dependence uses shared latent variables that appear as outer coordinates, the same mechanism ADR-010 uses for `CommonCauseFactor`.

The one legitimate epistemic-to-probabilistic conversion is a first-class record:

```python
class EpistemicCollapse(BaseModel):
    collapse_id: ContentHash
    original_belief: Belief                     # verbatim, hashed, reproduced in the package
    chosen: Deterministic | Aleatory
    justification: str                          # >= 120 chars, validator-enforced
    authorizer: HumanIdentity                   # the same identity the freeze protocol records
    authorized_on: datetime
    scope: CollapseScope                        # experiment_hash + explicit parameter paths
    lane: Literal["evidence", "exploratory"]
    expires_on: date | None
```

Every downstream `AggregateResult`, `ComparisonResult` and `Verdict` inherits `contains_epistemic_collapse: true`, and `registers/collapses.json` lists each collapse verbatim. The stored boolean is a convenience, never the authority: `verify` recomputes the taint by intersecting each collapse's `scope` with the parameter paths a result actually depends on, and a stored `false` that the recomputation contradicts is an integrity failure, not a discrepancy to report. The escape valve is the `evidence_grade` lane on `ExperimentDesign`: an `exploratory` experiment may auto-collapse intervals to their midpoint for sensitivity screening, recording a machine-authored collapse with `lane: exploratory`. Any verdict whose lineage touches an exploratory result is barred from an evidence-grade claim statement. This exists because an honesty system that makes daily engineering painful gets forked around; the exploratory lane is the pressure-relief valve that keeps the evidence lane pure.

Presentation is margin-first, and this is a renderer rule that never weakens a type rule. The answer to "just give me the probability" is a `MarginStatement` **object** with required fields — margin against the stated requirement, the guaranteed bound across the outer scan, the dominant contributing unknown with its share of the envelope width, and the measurement that would shrink it. A percentile for a quantity with epistemic lineage may enter `report/summary.md` only through that object's template block, so the dishonest render is unrepresentable rather than discouraged. GUM and NASA PRA succeeded by giving one number with a ritualized qualifier; interval-only refusal is why the p-box literature stayed academic.

**Review sign-offs are records, not norms.** The residues this record cannot mechanize (UNC-1, COLLAPSE-1, PRES-1 below) are recorded as rows in a `review_signoffs: list[{checklist_item_id, reviewer, date}]` field on the frozen `ExperimentDesign` and `EvidencePackage`. We cannot mechanize whether a rationale is honest; we can mechanize that a named human answered it, on a date, inside a hashed document.

## Options considered

### Option 1a — Flat Monte Carlo with uniform priors over everything — REJECTED (the naive baseline)
Put a uniform prior on every unknown, sample jointly, report percentiles. It is dispatched in two sentences because it is the naive baseline and is listed only so the real competitor below is not confused with it: a uniform distribution over ground-receiver optical-train throughput is not ignorance expressed neutrally, it is a specific and unjustified claim that emerges as a hard number in a report. The product exists to refuse exactly this operation.

### Option 1b — Robust Bayes: a documented prior family with a Gamma-minimax / prior-sensitivity scan — REJECTED
This is the version a competent statistician actually proposes, and it is the strongest rejected option in this record. For each epistemic quantity, declare an admissible prior *family* — an epsilon-contamination class, a quantile class, or a parametric family with its hyperparameters ranged over — compute the posterior (or posterior predictive) under each prior in the family, and report both the posterior summary and the range of that summary across the family. This is prior-robustness analysis, with Gamma-minimax as its decision rule. It has a long literature, real practitioners in reliability and risk analysis, and shipping tooling.

Four things must be conceded before it can be rejected honestly.

First, it gives customers the single number they ask for: a posterior percentile, plus a robustness range around it, which is a strictly richer answer than an interval-only refusal.

Second, it produces the *same headline artifact this record claims as unique*. The spread of the reported summary attributable to each quantity's prior choice is exactly a "which assumption is eating the margin" decomposition. FarSight does not have a monopoly on that deliverable and this ADR should not have implied it did.

Third — and a reviewer will see this immediately, so it is said here first — **FarSight's two-loop propagation is structurally almost identical to a robust-Bayes scan.** The outer deterministic scan over the epistemic space plays exactly the role of the prior-robustness loop; the inner seeded Monte Carlo plays the role of the predictive sampler. The geometry is the same. Stated plainly: **FarSight's outer loop is an unweighted robust-Bayes scan.** The difference is a single missing object — a measure over the outer space — and that absence is the whole decision.

Fourth, it is cheaper than the honest framing suggests, because the machinery is the machinery we are building anyway.

Rejected on two defeating grounds, both of which survive the steelman.

It still requires an admissible prior *family*, and for the quantities that dominate the flagship we have no basis on which to bound the family. Per-pass atmospheric transmission at Palomar over an arbitrary night has no measured distribution, no published distribution, and no principled contamination neighbourhood around anything. Whatever Gamma we write down is the unjustified claim of Option 1a moved one level up, and the width of the reported robustness range is then set by how wide we chose to make Gamma rather than by evidence. That is worse than an interval, because it looks derived.

And the moment a weight exists, a percentile can be computed. Give the outer space a measure — even an explicitly "uninformative" one over the family — and a mixture posterior is one line of code away, and someone will write that line at 6pm in week 7 with a customer call in the morning. That is the laundering path the type system exists to close. The unweighted scan closes it structurally: with no measure on the outer points, a percentile over outer points is not merely discouraged, it is undefined.

What we lose by rejecting it is real and named in Forecloses: a coherent posterior, the decision-theoretic vocabulary customers trained in Bayesian methods already speak, and direct access to the robust-Bayes literature's machinery for anything we later want to compute.

### Option 2 — One `Belief` class with an `is_epistemic: bool` flag — REJECTED
Keep a single type and mark its epistemic status. Cheap, fewer classes, trivial YAML, and it can be added in an afternoon. Rejected because a boolean is advisory. Every consuming code path is free to ignore it, and the failure mode is silent: someone writes `if b.is_epistemic: sigma = b.midpoint()` inside a sensitivity helper at week 6 and the taint never appears. A union makes the dishonest call an `AttributeError` at import-test time rather than a code-review question.

### Option 3 — Full p-box / Dempster-Shafer input arithmetic — REJECTED, named growth path
Represent every input as a probability box or belief-function structure and propagate bounds exactly, with Frechet bounds where dependence is unknown. This is mathematically the right answer to imprecise probability and it is rigorous without dependence assumptions — and unlike our scan, it can make a genuine enclosure claim. Rejected for the MVP on two grounds. First, propagating bounds through a black-box engine such as Basilisk is not possible; we would be restricted to the pure-Python link chain, abandoning the cross-engine premise. Second, despite decades of literature, commercial adoption is near zero, which is evidence that the artifact customers act on is the output envelope, not the input algebra. The two-loop scan delivers the output envelope at a small fraction of the cost. Full p-box inputs remain the named growth path if a customer arrives holding one.

### Option 4 — Interval-only, worst-case bounding — REJECTED
Represent everything as an interval and report the corner-stacked bound. Cheap, honest, and no distribution ever has to be defended. Rejected because stacking corners across a dozen terms produces envelopes wide enough to be vacuous, which trips AT-5's 6 dB ceiling and K2's 12 dB kill, and because it discards aleatory structure we genuinely know (SNSPD counting statistics, jitter realization). Being uselessly honest is still useless.

### Option 5 — Discriminated union with asymmetric API plus two-loop propagation — CHOSEN
Keeps the aleatory structure we know, refuses to invent the structure we do not have, makes the dishonest operation structurally absent rather than discouraged, and produces the output p-box that customers actually read. It costs a run-count multiplication, real authoring friction, and an enclosure claim we cannot make — all accepted below.

## Consequences

**Buys us:** the decomposition artifact that plan §1 calls the headline deliverable, because the outer scan directly attributes envelope width to named epistemic terms while the inner loop gives variance-based sensitivity on aleatory ones. A verdict domain where `indeterminate` is a real result. A schema-level guarantee behind AT-6. A single uncertainty vocabulary that the fault model (ADR-010) reuses instead of forking. And a reported envelope that carries its own convergence evidence, so a reader can see whether a narrow answer is an answer.

**Costs us:** run count is the product of two loops, so a modest epistemic space and a modest inner sample already reach five figures. Authoring tagged-union YAML is genuinely unpleasant (plan §19 risk 6), and the mitigation is schema-validated templates, never weaker types. Every parameter needs a pedigree block and a validity envelope before it can be frozen, which is real data-entry friction on day one. Two sampling code paths and a resolve step must both be tested. The convergence report costs the design at least three envelope computations rather than one, and the screening pass that ranks vertices is an additional exploratory run set that must be planned, executed and hashed before the evidence-grade campaign can be frozen.

**Forecloses:** FarSight cannot ever emit a single probability for a quantity with epistemic lineage without a human-authorized, content-addressed collapse record. That will lose deals where a buyer wants one number in a slide and will not accept the qualifier. It also forecloses the robust-Bayes vocabulary entirely: we cannot report a posterior, a Gamma-minimax decision, or any quantity that presupposes a measure on the outer space, so a customer whose in-house method is prior-robustness analysis gets our envelope and not their number. Interoperating with tools that consume a single distribution per input (Dakota, customer in-house Monte Carlo pipelines) requires a collapse at the boundary, so FarSight is a poor drop-in upstream component. Hierarchical Bayesian calibration, where hyperparameters are fitted from observed data, is structurally excluded: `Distribution.params` refuses an `Aleatory`. For DSOC that is aligned with "never fitted", but a future customer who wants principled Bayesian updating needs a schema change, not a config change.

And the sharpest one: because the outer scan is finite, the reported p-box is an inner bound, so FarSight cannot make a mathematical enclosure claim — **which means AT-5's width criterion is a criterion on an inner bound and can be met by under-sampling. The convergence report is the only defence, and it is a report, not a proof.** The vertex-selection rule inherits the same limit: ranking corners by one-at-a-time screening is a local criterion and will miss a corner that is only extreme through an interaction, and nothing in this design detects that case.

## Confidence and revisit triggers

This record decides six separable things and they are not equally safe. Each carries its own number and its own trigger; the triggers are keyed to the plan's dated gates so that every one of them can fire while the decision is still cheap to change.

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Five-member discriminated union with an asymmetric API and no `to_distribution` | 0.90 | K5 (end wk 6): 3 or more of the 8 discovery interviews name the refusal to emit a single probability, unprompted, as a stated reason they could not adopt. |
| Two-loop propagation: deterministic outer scan, seeded inner MC | 0.85 | The week-5 campaign shows the outer scan dominating badly enough that a 9,600-run campaign cannot finish overnight on the reference workstation (plan §21 throughput kill), which would force adaptive outer search and break the no-RNG-in-the-outer-loop rule ADR-006 depends on. |
| Outer-scan coverage: that the reported inner bound is close enough to the true p-box for a width criterion to mean anything | 0.65 | Either of: the K2 hand-computed envelope (end wk 2) and the first machine-computed envelope (wk 4) differ by more than 2 dB at the same epoch; or the week-5 `outer_scan_convergence` block shows envelope width still growing by more than 10 percent between n/2 and n. Both dates precede AT-5 being scored. |
| `oat_screening_rank` as the vertex-selection rule when `vertex_cap` binds | 0.60 | The week-4 screening pass produces a materially different coordinate ranking at two different design centres, which would mean the reported bound is an artifact of where we screened rather than of the epistemic space. |
| `EpistemicCollapse` plus the exploratory lane as the pressure-relief valve | 0.75 | The first evidence-grade campaign (wk 4 DSN package) requires more than three authorized collapse records, counted directly from `registers/collapses.json` — evidence the type system is being routed around rather than used. |
| `EpistemicSet` members enumerated, never weighted (plan §20 item 5) | 0.70 | Either of: 2 or more of the 8 K5 interviews (end wk 6) describe an in-house model-family weighting they would need preserved; or the week-5 sensitivity table cannot rank two competing model families without a weight, which would make the decomposition artifact unusable in the one place it matters. |

## Enforcement

A named CI job, `honesty-suite`, gates merges. Each item states the week by which it can first be green; an item marked for a later week does not run on earlier commits and does not pretend to.

1. `tests/unit/test_belief_api_surface.py` (first green by week 1) — an AST scan of `src/farsight/` asserting that the identifier `to_distribution` is defined nowhere, and a reflection test asserting `sample` is absent on `EpistemicInterval`, `EpistemicSet` and `Unknown`, and that `Unknown` implements neither protocol.
2. `tests/unit/test_runspec_fully_resolved.py` (first green by week 2) — constructing a `RunSpec` containing an unresolved `Aleatory`, any epistemic kind, or any `Unknown` must raise. This is the schema half of AT-6; the "no default exists in the codebase" half of AT-6 is ADR-007's problem and is not claimed here.
3. A Hypothesis property in `tests/unit/test_belief_freeze.py` (first green by week 2) — for arbitrary generated belief trees, `freeze()` fails if and only if some `Unknown` lacks both `sweep_declaration` and `bounding_assumption_ref`, and no `Distribution.params` entry is `Aleatory` or `Unknown`.
4. `tests/unit/test_taint_propagation.py` (first green by week 4) — over a synthetic lineage, any result whose dependency set intersects an `EpistemicCollapse.scope` carries `contains_epistemic_collapse: true`, and any evidence-grade `Verdict` descended from an `exploratory` result fails the build. `farsight evidence verify` (defined in ADR-007) recomputes the same intersection from `registers/collapses.json` on a real package rather than trusting the stored boolean, and exits nonzero naming the verdict.
5. `tests/unit/test_margin_statement_structure.py` (first green by week 5, when the report template freezes per §2 tripwire 5) — the renderer emits a `MarginStatement` object with all four required fields, and the only template block able to emit a percentile for an epistemically-derived quantity is that object's. The test asserts on the object and on the template, never on rendered prose. PARTIALLY MECHANIZED: nothing stops a human pasting a bare percentile into hand-written prose elsewhere in a package. Review-checklist item **PRES-1** — "every percentile in customer-facing material for an epistemically-derived quantity carries its bound and its dominant contributor" — covers that residue and is recorded in `review_signoffs`.
6. `tests/unit/test_outer_convergence.py` (first green by week 5, when the campaign machinery exists) — an `evidence_grade: evidence` package whose `metrics/sensitivity.json` lacks the `outer_scan_convergence` block, or whose envelope width grew by more than the design's declared fraction between n/2 and n, fails. This is the mechanical guard on the inner-bound problem and it gates the grade, not the merge.
7. `tests/unit/test_vertex_selection_deterministic.py` (first green by week 5) — the surviving vertex set is a pure function of the frozen design: same design, same set, in the same order, across two processes and two platforms; and a design whose `vertex_cap` binds without a `vertex_selection` block fails to freeze.
8. mypy strict over `farsight.schemas` plus a Protocol-conformance test (first green by week 1), so the asymmetry is a type error and not only a runtime one.

Two residues are not mechanizable and are named rather than implied.

NOT MECHANIZABLE: whether an `EpistemicInterval.rationale` states what is actually not known and why no distribution is defensible, rather than restating the interval in words. The validator enforces length, not content. Review-checklist item **UNC-1**, recorded in `review_signoffs`.

NOT MECHANIZABLE: whether an `EpistemicCollapse.justification` is honest, or whether the chosen distribution is defensible. The schema enforces that a named human authorized it, on a date, with a scope and a 120-character statement, and `verify` enforces that the record exists and is reproduced verbatim in the package. Review-checklist item **COLLAPSE-1**, recorded in `review_signoffs`. The earlier claim that no part of this ADR relies on human judgement was wrong and is withdrawn: three parts do, and they are listed here instead.

## References

- FARSIGHT_FOUNDATION_PLAN.md §9 (uncertainty model, decision D7), §7 (mandatory pedigree and validity envelope), §4 (design and execution planes, `AggregateResult` as empirical p-box, `evidence_grade`), §13 (four registers, judgment register), §14 items 4 and 9, §17 weeks 3-6, §18 AT-5 and AT-6, §19 risks 3 and 6, §20 item 5, §21 K2 and K6, §23 item 1.
- DSOC persistent unknowns that must never be fitted, and the plus or minus 2-3 dB honest precision statement: verified fact pack, 2026-08-26.
- SNSPD efficiency and blocking model come from the open-access detector paper named in plan §17 (weeks 3-4) and enter as a hash-pinned, cited `DataArtifact` per §14 item 5. UNVERIFIED — the paper identifier and its efficiency figure are not stated in the plan; the citation is fixed when the dataset is frozen, and no number is taken from this record.
- Robust Bayes, prior-sensitivity analysis and Gamma-minimax are named here as the steelmanned form of Option 1b. UNVERIFIED — no specific text, author or result is asserted; confirm any citation before it appears in external material.
- GUM and NASA PRA are named in plan §9 as the precedent for margin-first presentation; no URL is asserted here.
- PLAN AMENDMENT REQUESTED: §13 — `metrics/sensitivity.json` gains a required `outer_scan_convergence` block (envelope width at n_outer/4, n_outer/2, n_outer) and the frozen design gains a `vertex_selection` block. §13 currently describes `sensitivity.json` only as "which epistemic terms dominate". Reason: AT-5 and K2 are pass criteria on envelope *width*, an under-sampled outer scan makes both easier to pass, and without these two items in the hashed record a reader cannot distinguish a narrow envelope from an unconverged one.
- PLAN AMENDMENT REQUESTED: §4 and §13 — `ExperimentDesign` and `EvidencePackage` gain a `review_signoffs` list of `{checklist_item_id, reviewer, date}`. Reason: this record's non-mechanizable residues (UNC-1, COLLAPSE-1, PRES-1) are otherwise norms with no home, and a norm that gates `evidence_grade` but lives in no schema is not a gate.
- PLAN AMENDMENT REQUESTED: §13 — the four registers live together under `registers/` (`assumptions.json`, `unknowns.json`, `collapses.json`, `validity_violations.json`), one copy each, no mirror. §13 shows only `experiment/unknowns_ledger.json`. Reason: two of the four are this record's output contract and they need exactly one authoritative path for `verify` to name. ADR-023 separately requests a fifth register in the same directory (`excluded_runs.json`), so `registers/` holds five files once that request is granted; nothing in this record depends on which way that one goes.
- ADR-001, ADR-005, ADR-006, ADR-007, ADR-008, ADR-009, ADR-010, ADR-013, ADR-017, ADR-021, ADR-022, ADR-023.
