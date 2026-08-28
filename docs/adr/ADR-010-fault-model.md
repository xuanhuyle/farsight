# ADR-010 — FaultMode / FaultActivation / FaultActivationRecord split and latent-factor common cause
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §10, decision D8 (also §4 planes, §5 fault lowering, §11 planner purity)
**Related ADRs:** ADR-004 (every stochastic fault quantity is a `Belief`, so no second uncertainty system exists), ADR-003 (fault lowering modes and refusal-over-approximation live in the adapter contract), ADR-001 (the restricted predicate AST is hashable spec content, which embedded Python would not be), ADR-005 (activation draws come from the `aleatory_draws` stream, pre-planned before dispatch; ADR-005 owns the registry), ADR-002 (bindings execute inside the isolated worker, never in the planner), ADR-009 (the failure signature includes the faults active at first violation), ADR-011 (activation records are files in the package, readable with no engine installed), ADR-013 (`faults` is a pure compiler that never imports `engines`; it owns the `auditor_boundary` contract), ADR-015 (the epoch representation an `at_time` trigger is written in), ADR-017 (`SystemTopology` path grammar and the `environment` subtree the boundary rule tests against), ADR-020 (the channel names predicate leaves resolve against)

## Context

The forcing question is what a fault *is* as a data structure, given that the same fault has to survive three very different journeys. It has to be authored once and reused across missions. It has to be lowered onto engines with incompatible intervention models: Basilisk offers attribute mutation between segments, `createNewEvent(name, rate, active, conditionList, actionList)`, and `enableTask`/`disableTask`, but has no mid-run checkpoint API; GMAT's per-process-singleton reality (plan §5, ADR-003) makes mid-run intervention a segment-splitting problem or a refusal; the FarSight-native link chain can do whatever we design. And it has to be replayable by an auditor on a laptop with zero engine extras installed — import-linter contract `auditor_boundary`, defined in ADR-013, which the plan's "Things we must get right" item 7 calls the most commercially important import rule in the codebase (the rule itself is stated in §6).

Three things break concretely if this is wrong. First, cross-engine fault campaigns become impossible: if faults are engine-native config blobs, a fault campaign is not a comparable object and the Tier C comparison story (ADR-003, ADR-006) has nothing to compare. Second, stochastic fault campaigns become unreplayable: a campaign where activation times are drawn cannot be re-executed run-for-run unless the drawn values are recorded, and AT-7 requires run #4242 re-executed standalone to be bitwise identical to its in-campaign channels. Third, and least obvious, a fault DSL that embeds executable code destroys both hashability and the deployment story. FarSight ships to customers who will not run arbitrary code that arrived in a spec file, and FarSight's own export posture is unsettled (a proprietary non-published product may fall under ECCN 9D515 under the 2024 space-controls rulemaking; that is a lawyer question, not a settled one). An `eval()` surface in the fault path is a liability in every one of those conversations.

There is also a taxonomy hazard. Every simulator framework that tried to build a fault library eventually could not answer "is bad weather a fault?", and the catalog rotted into a junk drawer. We need a boundary rule that a schema validator can partially enforce.

## Decision

Three objects, one per plane, mirroring FMECA practice, which already separates failure modes as catalog items from their occurrence in a specific analysis.

### FaultMode (knowledge plane, content-addressed, mission-independent)

```python
class TopologyTarget(BaseModel):
    path: str                       # "ground.palomar.receiver.optical_train" (ADR-017)
    aspect: Literal["parameter", "output", "function"]

EffectKind = Literal["bias", "scale", "stuck_at", "zero_output", "dropout",
                     "noise_inflation", "latency", "intermittent",
                     "ramp_degradation", "custom"]

class EffectSpec(BaseModel):
    kind: EffectKind
    plugin_ref: ContentHash | None = None      # required iff kind == "custom"

class FaultMode(BaseModel):                    # frozen=True, extra="forbid"
    mode_id: ContentHash                       # = sha256(canonical JSON), ADR-001
    name: str
    target: TopologyTarget
    effect: EffectSpec
    parameters: list[ParameterDecl]            # DECLARED, never valued: magnitude,
                                               # recovery_delay, ... with unit + admissible range
    detection: list[ObservableRef]             # channels that would reveal it
    recovery: Literal["none", "self_clearing", "autonomous", "ground_intervention"]
    fmeca: FmecaClassification | None          # severity / likelihood, optional
    pedigree: Pedigree                         # MANDATORY, per ADR-004
```

A mode declares parameters; it never holds values. Magnitude is a `ParameterDecl` with a unit and an admissible range, and so is a `ground_intervention` recovery delay. That symmetry is what keeps the catalog identity meaningful: two campaigns citing `mode_id` X are citing the same physical failure mode, not two similar-looking ones with different numbers baked in.

**Boundary rule.** A fault is a deviation of *system* behaviour from design intent. If a quantity could take that value in a nominally functioning system under some admissible environment, it is a scenario or uncertainty input, not a fault. Cloud cover over Palomar is environment. A cryocooler losing lock is a fault. `SystemTopology` has an `environment` subtree (ADR-017), and a `FaultMode` whose `target.path` resolves under it is rejected at validation with `FaultTargetsEnvironment`. Environmental conditions may still couple into faults, but only through a `CommonCauseFactor`.

### FaultActivation (design plane, inside a FaultCampaign)

```python
class AtTime(BaseModel):
    trigger: Literal["at_time"] = "at_time"
    t: Epoch                                   # ADR-015 owns the epoch representation

class AfterElapsed(BaseModel):
    trigger: Literal["after_elapsed"] = "after_elapsed"
    after: Quantity
    of: Literal["scenario_start", "mode_entry"]

class OnCondition(BaseModel):
    trigger: Literal["on_condition"] = "on_condition"
    predicate: PredicateAST
    for_duration: Quantity | None = None       # hysteresis, top level only
    latch: bool = True

class StochasticHazard(BaseModel):
    trigger: Literal["stochastic_hazard"] = "stochastic_hazard"
    rate: Belief                               # may be epistemic; ADR-004
    window: TimeWindow | None = None
    max_occurrences: int = 1

class FaultActivation(BaseModel):
    activation_id: str                         # stable label within the campaign
    mode_ref: ContentHash
    trigger: AtTime | AfterElapsed | OnCondition | StochasticHazard   # discriminated
    bindings: dict[str, Belief]                # parameter name -> Belief (magnitude, duration, ...)
    coupling_refs: list[str] = []
```

The predicate AST is a closed grammar, and nothing else is admissible:

```json
{"op": "and", "args": [
  {"op": "gt", "lhs": {"channel": "link.range"},        "rhs": {"const": {"magnitude": "2.5", "unit": "AU"}}},
  {"op": "not", "args": [
     {"op": "eq", "lhs": {"channel": "gnc.pointing_mode"}, "rhs": {"const": "safe"}}]},
  {"op": "eq",  "lhs": {"factor": "wx_palomar_seasonal"}, "rhs": {"const": true}}
]}
```

Leaves are `{"channel": path}`, `{"const": Quantity | enum | bool}`, or `{"factor": factor_id}`. Comparisons are `lt le gt ge eq ne`. Boolean operators are `and or not`. `for_duration` is a hysteresis wrapper on the whole predicate and may not be nested. There is deliberately **no arithmetic**: `range_rate > 0 and range > X` is expressible, `range / 2 + drift > X` is not, and the answer is to declare the derived quantity as a model output channel. Arbitrary logic enters exactly one way, as a content-hashed plugin referenced by `EffectSpec.plugin_ref`, installed out of band, with its hash recorded in the environment fingerprint. Never as an embedded expression in a spec file.

The whole grammar is thirteen node kinds: six comparisons, three boolean operators, three leaf shapes and one hysteresis wrapper. That size is the argument for building it, and it is also the ceiling: a fourteenth kind is a decision to revisit, not an incremental feature.

Predicates are evaluated on a campaign-declared `evaluation_period` grid. "The condition was true between samples" is unresolvable and engine-dependent, so the cadence is a declared matched-configuration item for cross-engine comparison (ADR-003), and the record stores which sample fired.

**All randomness is pre-planned.** Plan §11 requires the pool never to draw, so the fault compiler splits triggers at plan time. `at_time`, `after_elapsed(scenario_start)` and `stochastic_hazard` are time-resolvable: the hazard is drawn in the planner from the `aleatory_draws` seed stream (ADR-005, stream id 0 — fault randomness is not special) and becomes a concrete fire time, or no fire, written into the RunSpec as a static `InterventionSchedule`. `on_condition` and `after_elapsed(mode_entry)` are state-dependent and become a `ConditionSchedule` evaluated in-worker with zero RNG; their *magnitudes* are still pre-drawn, so only the fire time is state-determined.

### FaultActivationRecord (execution plane, produced, never authored)

```python
class FaultActivationRecord(BaseModel):
    run_id: ContentHash
    activation_id: str
    mode_ref: ContentHash
    fired: bool
    fire_offset: Duration | None               # ADR-015; anchored to ScenarioTemplate.epoch_start
    cleared_offset: Duration | None
    drawn_parameters: dict[str, Quantity]      # SI, decimal-string magnitudes as applied
    outer_point_index: int
    inner_draw_index: int
    seed_stream: Literal["aleatory_draws"]
    trigger_evidence: TriggerEvidence          # hazard draw value, or the predicate sample index
    factor_state: dict[str, Quantity | bool]   # realized latent factor values for this run.
                                               # KEYS ARE `CommonCauseFactor.factor_id` (the
                                               # 64-hex digest), never the display `name`.
    binding_used: FaultBindingId               # the mechanism the adapter actually applied
```

This is the object that makes deterministic replay of a stochastic fault campaign possible, and it is also what lets `farsight evidence verify` reconstruct "which faults were active at first violation" for the failure signature (ADR-009) without an engine installed.

**`factor_state` keys are factor digests.** Stated explicitly because the join depends on it and the type alone does not say so: the key is the `factor_id` resolved from the frozen campaign, matching `Coupling.factor_ref` and the `{"factor": ...}` predicate leaf, so a reader assembling "which latent conditions held in this run" joins records to factors by digest rather than by a display string that two campaigns may spell differently. `name` remains the human label and appears in reports.

**Attributing an outcome to a fault is done by paired counterfactual, not by co-occurrence.** The failure signature records the faults active at first violation, which is a temporal-coincidence claim and should never be reported as a cause. The deterministic instrument is the zero-magnitude pairing: the same frozen design with one activation's magnitude bound to zero. Because a zero-magnitude fault is byte-transparent — `fault-mutation-suite` and AT-10 exist to prove exactly that — the two campaigns share every drawn value, and the whole difference in every metric is attributable to that one activation, as arithmetic rather than inference. Note the trap this avoids: simply *removing* an activation is not draw-matched, because activation lists feed the sorted draw order and deleting one shifts every aleatory draw downstream of it (ADR-005). `farsight evidence diff` over the paired packages is the reporting path.

### Common cause via shared latent factors

```python
class CommonCauseFactor(BaseModel):
    factor_id: ContentHash
    name: str
    nature: Literal["aleatory_event", "epistemic_existence"]
    occurrence: Belief | None      # aleatory_event: occurrence and optional severity Beliefs
    severity: Belief | None
    members: list[Literal["present", "absent"]] | None   # epistemic_existence: ENUMERATED
    pedigree: Pedigree

class Coupling(BaseModel):
    factor_ref: ContentHash
    activation_ref: str
    modulates: Literal["hazard_rate", "magnitude", "duration"]
    law: Literal["multiplicative", "additive", "replace"]
    coefficient: Belief
```

Activations are conditionally independent **given** the factors. Environmental common causes are aleatory: one weather factor drawn per pass, coupled multiplicatively into the hazard rate of the pointing-loss and dropout activations on consecutive passes, which is the week-5/6 fault type the plan explicitly says never to cut. Design defects use *epistemic existence*: the firmware defect is present in both transceivers or in neither, entering the outer scan as a two-member enumeration (ADR-004), never as a probability of existing. In the MVP the graph is one layer, factors to activations; a factor may not couple to another factor. Plan §10 fixes that restriction and this record does not depart from it — but see the confidence table, because it is the shakiest thing here.

The classical beta-factor PRA model is representable as a special case: give each of N activations an independent hazard at `(1 - beta) * lambda` and add one aleatory factor firing at `beta * lambda` coupled with `law: replace` to all N. FarSight ships no beta-factor helper in the MVP; the mapping is documented for PRA-literate customers, not automated.

### Engine binding

```python
class FaultBindingImpl(BaseModel):             # supplied by the adapter, not by the user
    engine: str                                # "linkchain" | "basilisk" | "gmat"
    mode_ref: ContentHash
    mechanism: Literal["attribute_mutation", "task_disable", "message_intercept",
                       "parameter_override", "native_model_hook", "unsupported"]
    lowering_mode: Literal["native", "config_time", "segment_split", "refusal"]
    target_resolution: str                     # engine-native handle
    verified_by: list[TestId]                  # the mutation tests proving this binding
```

`farsight freeze` resolves every (campaign fault, routed engine) pair. A missing binding, or one declaring `unsupported`, **fails the freeze** with `unsupported_on: [gmat]` in the message. There is no silent skip and no silent approximation.

**Review sign-offs are records, not norms.** The one residue this record cannot mechanize (FAULT-BOUNDARY below) is recorded as a row in the `review_signoffs: list[{checklist_item_id, reviewer, date}]` field on the frozen `ExperimentDesign` and `EvidencePackage`. We cannot mechanize whether a proposed mode describes a deviation from design intent; we can mechanize that a named human answered the question, on a date, inside a hashed document.

## Options considered

### Option 1 — One `Fault` object combining catalog and occurrence — REJECTED
Author the mode and its trigger together. It is the obvious first design, produces far shorter YAML, and for a single one-off campaign the split is pure ceremony. Rejected because catalog reuse dies. A `FaultMode` is knowledge-plane and mission-independent by plan §4; fusing it with an activation means every campaign re-authors "what a stuck-at gyro is" with its own pedigree, so two campaigns' nominally identical fault is two different content hashes, and the failure signatures in ADR-009 stop being comparable across campaigns. The catalog is the thing a customer's reliability group actually owns.

### Option 2 — Two objects, with the record derived on demand from seeds — REJECTED
Store only mode and activation; regenerate what fired from the seed and the spec whenever it is needed. This is a real argument: the record is redundant by construction, storing it duplicates truth, and it keeps packages smaller. Rejected because derivation of a state-dependent trigger requires re-running the engine, and the auditor's laptop has zero engine extras installed (import-linter contract `auditor_boundary`, defined in ADR-013). Recomputing "which faults were active at first violation" would silently become an engine-gated operation, which is precisely the boundary we are selling.

### Option 3a — Embedded Python callables or eval strings for triggers — REJECTED
Let the trigger be a Python expression or a callable path. Infinite expressiveness, no DSL to build, and it is the engine-native idiom: Basilisk's own `createNewEvent` takes condition and action strings. Rejected on three counts. A hash of Python source is not a hash of semantics, because closures, imports and interpreter version change behaviour without changing bytes, which breaks ADR-001's identity claim. Determinism becomes hostage to arbitrary code that can read the clock, call a naked RNG, or touch the filesystem, breaking ADR-006. And a sovereign or on-prem customer executing code that arrived in a data file is a security conversation FarSight cannot win. This option is listed on its own because "embedded Python is dangerous" is *not* an argument against the option below, and previously the two were fused so that the weak version carried the rejection for both.

### Option 3b — A sandboxed hermetic expression language with a published grammar and a shipping implementation — REJECTED
This is the real competitor to a hand-rolled AST, and it is close. Google CEL exists precisely for restricted predicates in configuration; Starlark exists precisely for hermetic, deterministic evaluation of declarative configuration; a WASM-hosted evaluator is a third shape of the same idea. Taking CEL as the representative: it is non-Turing-complete by construction rather than by our restraint, it has no filesystem, clock or RNG surface at all, it is deterministic by design, it has a published grammar with defined semantics — so a hash of the predicate source *is* a hash of its meaning, which is exactly the objection that defeats Option 3a and does not apply here — and multi-language implementations mean an auditor could in principle evaluate a shipped predicate without FarSight installed. It is a shipping, standard thing maintained by people whose job it is, and this record's own Consequences concede that the chosen path costs "a compiler and an evaluator we must build and test inside the week-5/6 campaign-machinery budget" and "will be the source of a class of bugs". Choosing to hand-build, in the tightest week of the schedule, a smaller version of something that already ships is a decision that has to be argued, not assumed.

It is rejected on two honest grounds and one that follows from our own rules.

A Python-embeddable CEL or Starlark runtime is a new non-stdlib dependency **inside the truth loop**, and the truth loop's dependency surface is a product claim, not a preference: `farsight evidence verify` runs on the no-extras base install (ADR-007, ADR-013), and a predicate evaluator is needed wherever a `ConditionSchedule` is reconstructed. Its version then becomes part of the reproducibility surface — a runtime version bump that changes an evaluation-order or coercion detail changes which sample a predicate fired on, which changes channel bytes, which changes hashes, and the environment fingerprint would have to carry it as a first-class tier input alongside the engine versions. We would be trading a class of bugs we can fix for a class of divergence we can only observe.

Our predicate needs are thirteen node kinds wide. The grammar above is the entire requirement, it is a closed Pydantic discriminated union rather than a parser, and the fuzz test that proves closure is cheap. A general expression language is a large surface adopted to serve a small one, and every construct it has that we do not need is a construct someone will eventually use in a spec file we then have to lower onto three engines.

And the value model collides with ADR-001. Our constants are `Quantity` documents with decimal-string magnitudes and units, precisely so that no float appears in a hashed document. A hosted language brings its own value model of integers, strings and machine numbers, so either the predicate compares raw doubles — reintroducing the float comparison ADR-001 removed — or we write a `Quantity`-aware extension layer inside the host language, which is most of the compiler we were trying not to write, with a foreign-language debugging story attached. UNVERIFIED — the exact numeric model, licence and Python-embeddable implementation maturity of any specific candidate runtime are not stated in the plan; confirm before naming one in external material.

This is the closest call in the record, and the confidence table says so.

### Option 4 — Faults get their own uncertainty representation (point rates, PRA-style) — REJECTED
Express hazard rates and severities as plain floats, the way FMECA spreadsheets and classical PRA do, and handle uncertainty in a separate analysis step. It is simpler, and it matches the artifacts customers already have. Rejected because it opens a laundering path straight around ADR-004: "we do not know this component's degradation rate" would become a fitted point value the moment it crossed into fault space, and the honesty guarantee would hold everywhere except the one place a failure analysis actually lives. Reusing `Belief` costs nothing except that fault authors must supply pedigree.

### Option 5 — Common cause as an explicit correlation matrix over activations — REJECTED
Declare pairwise correlations between fault occurrences directly. Familiar, compact, and it is what most engineers reach for. Rejected because a correlation coefficient does not specify a joint distribution over binary events, so the sampler would have to invent one; it cannot express epistemic existence at all, since "present in both or neither" is not a correlation; and it carries no explanation, so the sensitivity view has nothing to name when it reports which factor is eating the margin. A latent factor is both a specification and an answer. Note honestly that the one-layer restriction below has this option as its fallback, which is why the restriction is scored low.

### Option 6 — Three-way split, `Belief` reuse, latent factors, restricted AST — CHOSEN
Accepts more objects and a small compiler in exchange for catalog reuse, engine-portable campaigns, engine-free replay, one uncertainty system, and an explainable common-cause story.

## Consequences

**Buys us:** fault campaigns that are comparable across engines and across missions; deterministic replay of stochastic fault campaigns, including reconstruction of the failure signature with no engine installed; one uncertainty vocabulary rather than two; a common-cause model that survives the "why did these fail together" question; and freeze-time refusal in place of silent approximation, which is the behaviour that makes the adapter contract credible.

**Costs us:** the predicate AST is a compiler and an evaluator we must build and test inside the week-5/6 campaign-machinery budget, and it will be the source of a class of bugs that a hosted evaluator would not have had. Every fault mode needs a per-engine binding written by an adapter author, so onboarding a new engine costs O(number of fault modes), not O(1) — this is a direct tax on the multi-engine premise and feeds the adapter-cost kill criterion. Predicate evaluation cadence becomes another matched-configuration item to declare and defend in Tier C comparisons. Pre-drawing hazards at plan time fixes the run count before execution, so there is no adaptive stopping.

One further cost belongs to this record even though the decision is ADR-005's. Fault randomness shares the `aleatory_draws` stream with physics randomness, and the stream registry is frozen at three entries. The honest consequence is that adding or removing a fault activation changes what a run asks of `aleatory_draws`, so a campaign re-planned with one more activation is not draw-for-draw comparable to its predecessor at the same `run_index` unless ADR-005's draw addressing makes each parameter's draw independent of its neighbours. That is ADR-005's question to answer, and it is booked here because it is this record's cost.

**Forecloses:** a hazard rate that varies with a live channel is not expressible, because hazards are drawn in the planner; the best available approximation is `on_condition` with a fixed magnitude, and lifting the restriction would require in-worker RNG and a redesign of ADR-005's stream discipline. Multi-layer common-cause graphs, where a factor drives another factor, are out — and the concrete thing that costs us is autocorrelated weather: a seasonal or synoptic regime driving per-pass realizations is canonically two layers, and with one layer the consecutive-pass weather campaign gets either a single campaign-wide factor, which forces perfect correlation across passes, or per-pass factors whose correlation has to be hand-encoded into their occurrence `Belief`s, which is Option 5 wearing a different name. Any fault logic needing arithmetic over channels is out until someone adds a model output channel. Environment-targeted faults are out by construction, which will feel wrong to at least one customer whose FMECA sheet lists "solar storm" as a failure mode. And having declined a hosted expression language, a customer who wants to reuse predicates they already hold in CEL or Starlark has to re-author them in our grammar, by hand, with no translator.

**Two boundaries, stated so they are decisions rather than omissions** (from `FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §15). *Factor-to-parameter coupling does not exist in this record*: `Coupling` reaches fault activations only, while plan §9 and ADR-004 describe shared latent factors as the mechanism for epistemic dependence between ordinary parameters too. That half is ADR-027's, and until it lands the only honest expressions are an `EpistemicSet` enumerated in the outer scan or — the thing to avoid — correlation hand-encoded into occurrence `Belief`s, which is the invisible-dependence rot the latent-factor design exists to prevent. *A high-dimensional correlated environment is not a fault campaign*: dust density along a corridor, a radiation field, a weather field over many sites are model inputs, and the sanctioned route is engine-side realization seeded from `engine_module_seeds` (ADR-005) with the field's correlation structure a pedigreed model parameter. Where a spatial profile must be visible to FarSight, it is K scalar factors with per-coupling coefficients — a truncated modal expansion, expressible today — never a field, mesh or covariance-kernel type in a shared schema. `CorrelationGroup` (ADR-022) is sized for a handful of parameters and is not the vehicle for a thousand-hop corridor.

## Confidence and revisit triggers

This record decides six separable things and the single number it previously carried averaged over all of them. Two of the six are genuinely shaky and are scored as such; triggers are keyed to dated gates so each can fire while the decision is still cheap.

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Three-way split: `FaultMode` / `FaultActivation` / `FaultActivationRecord` | 0.90 | The week-6 fault campaign authors more `FaultMode`s than it uses activations, meaning the catalog layer is pure overhead for the way campaigns are actually written. |
| `Belief` reuse for every stochastic fault quantity (no second uncertainty system) | 0.90 | Authoring the three week-5/6 link-chain fault types requires more than one authorized `EpistemicCollapse` in fault space, which would say the shared vocabulary is being routed around exactly where it was meant to bind. |
| Hand-built restricted AST rather than a hosted hermetic expression language (Option 3b) | 0.65 | Any of: the compiler and evaluator exceed three dev-days inside the week-5/6 budget; the grammar acquires a fourteenth node kind; or the week-6 mutation suite finds a predicate-evaluation defect that a published-grammar evaluator would not have had. This is the closest call in the record and the trigger is deliberately easy to trip. |
| Latent factors rather than a correlation matrix over activations | 0.85 | The week-6 sensitivity view cannot name a factor as the cause of a correlated failure group, which is the whole reason the factor was preferred to a coefficient. |
| One-layer common-cause graph in the MVP (plan §10) | 0.60 | The week-5 Palomar consecutive-pass weather campaign — the one fault type §17's scope-cut order says never to cut — cannot be expressed one-layer without hand-encoding a correlation into per-pass occurrence `Belief`s. That is a week-5 design task with a known date, and its fallback is the option this record rejected, which is why the number is low. |
| Freeze-time refusal for a missing or `unsupported` binding | 0.90 | `FaultBindingImpl` authorship exceeds 30 percent of the measured hours of the minimal Basilisk adapter, against §21's existing two-dev-week adapter budget which is already being tracked; that is early evidence for the adapter-cost kill. |

Two further triggers apply to the record as a whole, and both are dated rather than gated on a customer population that does not yet exist. First: 2 or more of the 8 K5 discovery interviews (end wk 6) describe a fault campaign whose hazard rate varies with a live channel, which is the one thing the pre-planned-draw design forecloses outright and which cannot be added later without in-worker RNG. Second: the week-6 `fault-mutation-suite` cannot be made to pass a zero-magnitude fault through Basilisk's `attribute_mutation` mechanism, which would mean the mechanism is not state-transparent and lowering must change before the adapter is accepted.

## Enforcement

Each item states the week by which it can first be green. The fault framework lands in weeks 5-6 (§17), so most of this section is honestly late rather than falsely claiming every commit.

1. `tests/unit/test_fault_ast_closed.py` (first green by week 5) — the AST is a closed Pydantic discriminated union; a fuzz test asserts every node shape outside the grammar fails validation, and an `ast`-module scan of `src/farsight/faults/` asserts that `eval`, `exec` and `compile` are never called. PARTIALLY MECHANIZED: the scan catches direct calls and imports of those names but cannot detect a dynamically constructed one. The residue is closed by constraining the input rather than deepening the analysis — a companion lint forbids `getattr` on `builtins` and any `__import__` call anywhere under `faults/`, which makes the scan sound over the code it is allowed to see. Review-checklist item **FAULT-AST**, recorded in `review_signoffs`, covers a plugin's own source, which is out of band by design.
2. `tests/engine_contract/test_fault_binding_completeness.py` (first green by week 6) — for every (`FaultMode` in the repository catalog, adapter) pair, either a `FaultBindingImpl` exists or the adapter explicitly declares `unsupported`; and freezing a campaign routed to an engine with no binding must raise `FaultLoweringRefused` naming the engine. Silent skip is a test failure.
3. Nightly CI job `fault-mutation-suite` (plan §14 item 9, AT-10; first green by week 6) — a zero-magnitude fault run must produce channel hashes bitwise equal to the baseline run; each fault type must move its declared metric in its declared direction; and a declared common-cause coupling must appear in outputs as a rank correlation above a pre-stated floor. If a zero-magnitude injection perturbs state, the injection plumbing is wrong and the build fails.
4. Schema validator `FaultTargetsEnvironment` (first green by week 5, once `SystemTopology` exists per ADR-017) — a `FaultMode` whose `target.path` resolves under the `environment` subtree is rejected at construction.
5. `tests/unit/test_records_are_engine_free.py` (first green by week 6) — replaying a fault campaign's records with no engine extras installed reproduces the same `FaultActivationRecord` set and the same failure signatures. The import-linter contract `auditor_boundary` (defined in ADR-013) is what keeps this honest; this test exercises it rather than restating it.
6. `tests/unit/test_no_worker_rng_in_faults.py` (first green by week 5) — the compiler's `InterventionSchedule` output must contain no unresolved draw, and a lint rule forbids RNG construction anywhere under `src/farsight/faults/`.
7. `tests/unit/test_fault_stream_registry_agreement.py` (first green by week 5) — asserts `FaultActivationRecord.seed_stream`'s literal is a key of ADR-005's `STREAMS` registry and that no code path under `faults/` constructs a stream name or id absent from it. This is the mechanical guard against this record and ADR-005 drifting into two different bit streams for the same draws.

NOT MECHANIZABLE: whether a proposed `FaultMode` describes a deviation from design intent or an admissible environment. The topology check catches the clear cases only, and the interesting cases are exactly the unclear ones. The residue is review-checklist item **FAULT-BOUNDARY**, which asks the author to state in one sentence what design intent is being deviated from; a mode that cannot answer it is an environment input. The answer is recorded in `review_signoffs` on the frozen design, so the sign-off is an auditable row rather than a habit.

## References

- FARSIGHT_FOUNDATION_PLAN.md §10 (fault model, decision D8), §4 (knowledge/design/execution planes, `SystemTopology` as naming authority), §5 (four lowering modes and refusal), §11 (planner purity, all randomness pre-planned, named seed streams), §14 item 9 (mutation tests), §18 AT-7, AT-10 and AT-12, §17 weeks 5-6 (three link-chain fault types, weather common cause), §21 (adapter-cost kill).
- Basilisk intervention surface (`ConfigureStopTime`/`ExecuteSimulation` segments, attribute mutation between segments, `createNewEvent(name, rate, active, conditionList, actionList)`, `enableTask`/`disableTask`, per-module `RNGSeed`, no mid-run checkpoint API): verified fact pack, 2026-08-26. The GMAT and CSPICE platform facts this record leans on are stated once in plan §5 and restated once in ADR-003 References; they are not repeated here.
- Hermetic expression languages considered under Option 3b (Google CEL, Starlark, a WASM-hosted evaluator) are named as the steelmanned alternative. UNVERIFIED — their licences, Python-embeddable implementations, maturity and numeric models are not stated in the plan and none is asserted here; confirm at implementation time before any of them is named in external material.
- Export posture (a proprietary non-published FarSight may fall under ECCN 9D515 under the 2024 space-controls rulemaking; unsettled, counsel gate K7 in plan §15 and §21) as one reason the fault DSL carries no executable surface.
- PLAN AMENDMENT REQUESTED: §10 — `recovery: ground_intervention(delay: Belief)` becomes `recovery: Literal[...]` on the mode plus a declared `recovery_delay` `ParameterDecl`, valued per campaign as a `Belief` in `FaultActivation.bindings`. Reason: a knowledge-plane catalog entry declares parameters and never holds values; an inline delay would bake a campaign-specific number into a mission-independent mode and split `mode_id` across campaigns that mean the same failure.
- PLAN AMENDMENT REQUESTED: §4 and §13 — `ExperimentDesign` and `EvidencePackage` gain a `review_signoffs` list of `{checklist_item_id, reviewer, date}`. Reason: FAULT-BOUNDARY and FAULT-AST are otherwise norms with no home, and the taxonomy-rot failure this record exists to prevent is exactly the kind that a norm without a record does not prevent.
- ADR-001, ADR-002, ADR-003, ADR-004, ADR-005, ADR-006, ADR-009, ADR-011, ADR-013, ADR-015, ADR-017, ADR-020.
