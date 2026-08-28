# ADR-018 — Run composition: geometry provider and engine stages inside one run
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §5 (SPICE modelled as a geometry service, not a sim engine), §4 (RunSpec as the complete causal input), §11 (planner purity, all randomness pre-planned), §17 (weeks 3-4, the first pipeline), decisions D2 and D3
**Related ADRs:** ADR-002 (the worker executes whatever this record composes; `resolve_run_composition` is the seam it left), ADR-003 (the `Engine` / `GeometryProvider` split this record makes operational, and the opaque per-dialect config a stage carries), ADR-001 (the stage list sits inside `spec_hash`, and the closed `(experiment_hash, run_index) -> spec_hash` derivation is what rules out Option 1), ADR-010 (the in-worker `ConditionSchedule` this record's segment loop evaluates), ADR-015 (the epoch representation the sample grid and every `state()` call are written in), ADR-016 (`KernelRef`, furnish order and coverage, carried inside a geometry stage's config), ADR-020 (the channel-name grammar this record qualifies by stage id, and the sample grid stages are bound across), ADR-023 (whether a composition failure is a freeze-time refusal or a run outcome), ADR-006 (tier claims are stamped per run set, and a run set's engine is derived from its stage list), ADR-013 (owns the `.importlinter` file the `geometry_is_not_an_engine` contract ships in), ADR-024 (the `farsight geometry` verb a geometry-only run is spelled with)

## Context

The forcing question is invisible until someone writes the code, and then it stops everything: **a DSOC link run needs SPICE geometry and the link chain, and no record says how one run obtains both.**

Two accepted-shaped decisions collide. ADR-002's worker takes one serialized `RunSpec` and executes it in one fresh process; its earlier draft loaded exactly one adapter for one `engine_id`. ADR-003 declares `GeometryProvider` a separate protocol and says in as many words that it is *deliberately not an* `Engine` — it has no `run_to`, no `collect`, no segment model, because SPICE is a deterministic lookup service over a kernel pool and pretending otherwise would make three of five methods raise. Both records are right on their own terms, and together they admit exactly one engine per run and no geometry.

The flagship is the case that breaks. Plan §1 is explicit that the DSOC benchmark uses neither Basilisk nor GMAT: its geometry comes from reconstructed Psyche SPKs and its physics is FarSight's own link chain. So the single most important run in the eight weeks is precisely the run the harness cannot express. The same shape recurs immediately in the DSN RF anchor (§17, weeks 3-4), which the plan says shares the geometry pipeline.

Three further things are decided by whatever answer we give, which is why it cannot be deferred to the implementer. First, identity: `RunSpec` is the most-hashed document in the system, and its shape is inside `spec_hash`, inside `experiment_hash`, inside every root hash and every golden. Changing it in week 5 invalidates the Tier-A golden corpus and any pre-registration hash (ADR-001, §16). Second, the auditor boundary: whether a stranger can recompute the link margin from package content with zero engine extras depends on whether geometry is stored as channels or recomputed on demand. Third, ADR-002's `reusable_worker` exemption — granted to SPICE alone, and defensible only because it is falsifiable — quietly widens to whatever else ends up sharing a process with SPICE, unless composition says otherwise.

There is one more collision to clear in the same pass. ADR-002's worker sketch iterates `for boundary in unit.segment_boundaries`, and ADR-010 compiles state-dependent triggers into an in-worker `ConditionSchedule` evaluated on a declared cadence. The two records were written against different worker loops: one has boundaries and no predicate evaluation, the other has predicate evaluation and no stated boundaries. Composition is where they have to agree.

## Decision

**A `RunSpec` carries an ordered list of stages, and the worker composes them in one process.**

```python
class GridRef(BaseModel):                      # ADR-020 owns the grid descriptor itself
    grid_id: str

class ChannelSource(BaseModel):
    kind: Literal["channel"] = "channel"
    from_stage: str                            # a STRICTLY EARLIER stage_id in this run
    channel: str                               # a path relative to that stage's node, from its `emits`

class ArtifactSource(BaseModel):
    kind: Literal["artifact"] = "artifact"
    artifact_ref: ContentHash                  # a DataArtifact listed in RunSpec.inputs

class ValueSource(BaseModel):
    kind: Literal["value"] = "value"
    value: Quantity                            # decimal string + unit (ADR-001)

StageInput = Annotated[ChannelSource | ArtifactSource | ValueSource,
                       Field(discriminator="kind")]
# There is deliberately NO `run_output` member. See "the closed derivation" below.

class StageSpec(BaseModel):                    # frozen=True, extra="forbid"
    stage_id: str                              # unique in the run; the channel-name qualifier
    kind: Literal["geometry", "engine"]
    provider_id: str                           # "spice" | "linkchain" | "basilisk" | "gmat"
    config_dialect: str                        # ADR-003: names the provider's OWN schema
    config_ref: ContentHash                    # opaque engine-native config document
    grid: GridRef                              # ADR-020
    bindings: dict[str, StageInput]            # provider-dialect parameter name -> source
    emits: list[str]                           # channel paths RELATIVE to this stage's node (ADR-020)

class RunSpec(BaseModel):
    ...
    stages: list[StageSpec]                    # ordered; AT MOST ONE with kind == "engine"
    ...
```

`RunSpec.engine_id` is **removed**. The engine a run belongs to — for capability resolution, fault lowering, tier claims and cross-engine comparison — is computed, never stored:

```python
def run_engine_id(spec: RunSpec) -> str | None:
    return next((s.provider_id for s in spec.stages if s.kind == "engine"), None)
```

A run with no engine stage is a **geometry-only run**: the week-1 exit gate (`farsight geometry`, verb owned by ADR-024) and the geometry half of a cross-engine matched configuration are both this shape. `None` is a legitimate answer, and it keeps ADR-003's statement that a `GeometryProvider` is not an `Engine` literally true — nothing anywhere calls a geometry provider an engine, and no code path routes faults or tier-C comparisons to one.

**Six composition rules, all validated at freeze, all raising `SpecCompositionError` (a freeze-time error, ADR-023).**

1. `stage_id` values are unique within a run, each resolves to a node path in the run's `SystemTopology`, and the stage nodes are **pairwise non-overlapping** — no stage's node may equal or be an ancestor of another's (ADR-020).
2. At most one stage has `kind == "engine"`, and if present it is the last element of the list. There is no third stage kind, and the absence of one is the mechanical form of "this is not a workflow engine".
3. Every `ChannelSource.from_stage` names a strictly earlier stage and a `channel` that appears in that stage's `emits`. Order is total, so acyclicity is structural rather than checked.
4. For every `ChannelSource` binding, the producing and consuming stages declare the same `grid.grid_id`. Elementwise consumption of a channel computed on a different time base is the silent-killer class this rule exists to close.
5. A run whose `ConditionSchedule` predicate (ADR-010) references a channel of the **engine** stage requires that provider to declare `supports_stepping` (ADR-003). If it does not, the run is refused at freeze and lowering falls back to `config_time` or to `refusal` — ADR-003's four modes, unchanged, applied at the composition layer.
6. A run must contain at least one stage.

**Channel names are stage-qualified.** A stage emitting `range` under `stage_id: "geometry"` produces the run-level channel `geometry.range`; the link stage's `margin` becomes `link.margin`. Because stage ids are unique within a run, qualified names cannot collide, and ADR-009's existing examples (`geometry.in_view`, `link.margin`, `link.supportable_rate`) are already exactly this spelling. ADR-020 owns the grammar of both halves and the separator; this record owns only the rule that the qualifier is the stage id.

**The closed derivation survives, and that is the decisive property.** The planner emits the complete stage list, with every binding resolved to a channel of an earlier stage in the same run, to a hash-addressed input artifact, or to a literal `Quantity`. No stage input is ever another *run's* output — `StageInput` has no member that could express it — so `(experiment_hash, run_index) -> spec_hash` remains a pure derivation with no execution and no lookup table (ADR-001 rule 5). AT-7 stays a two-line operation on an auditor's laptop.

**Stage execution semantics, which is where ADR-002 and ADR-010 are reconciled.**

A geometry stage is evaluated in one shot over the run's sample grid. The worker furnishes the stage's ordered `KernelRef` list (ADR-016), evaluates the SPICE-native request document referenced by `config_ref` at every grid epoch through ADR-003's `state(req: GeometryRequest, et: SimTime)` — the `GeometryRequest` carrying target, observer, frame, `aberration` and quantity class, and ADR-015 owning its shape — emits the declared channels, and clears the pool. Frame, time scale and aberration conventions live inside that request document and are ADR-015's decision, not this record's. A geometry stage has no segments, no interventions and no RNG.

An engine stage runs a segment loop whose boundary set is fixed at plan time:

```
B = sorted( pre-drawn intervention epochs (ADR-010 InterventionSchedule)
            U  campaign-declared evaluation_period cadence points (ADR-010)
            U  {spec.end_time} )      restricted to the run's time span
```

For each `b` in `B` the worker calls `run_to(b)`, then evaluates the `ConditionSchedule` and applies any newly fired `Intervention` at that boundary — ADR-003 permits intervention at segment boundaries only. Predicate visibility is exact and asymmetric: **earlier stages' channels are fully materialized and visible at every index; the engine stage's own channels are visible only up to the current boundary.** A predicate over a future sample of the engine stage is a `SpecCompositionError` at freeze. The fire epoch recorded in `FaultActivationRecord.fire_offset` is the boundary at which the predicate was first observed true, never an interpolated crossing — which is precisely ADR-010's "the condition was true between samples is unresolvable" made operational. If `supports_stepping` is false, `B` must reduce to `{end_time}` or rule 5 has already refused the run.

The consequence worth naming: because geometry is materialized before the engine stage begins, a state-dependent fault trigger *can* reference geometry (`link.range > 2.5 AU`) without in-worker RNG and without a second SPICE call inside the engine.

**`reusable_worker` is the conjunction over a run's stages.** A worker may be recycled for a run only if every stage's provider declares `reusable_worker == True` (ADR-003's flag, consumed by ADR-002). A DSOC link run therefore never recycles, because the link chain does not declare it; a geometry-only run set may. ADR-002's exemption stays exactly as wide as it was written — SPICE alone — and its falsifiability leg (`ci-worker-order-invariance` with recycling forced off, defined in ADR-006) keeps testing what it was meant to test.

**Geometry channels are run outputs and package content.** They are written as `.npy` files like any other channel (ADR-011) and ship in the package. This is what lets an auditor with zero engine extras recompute `link.margin` from `geometry.range` and `geometry.in_view` without CSPICE, and it is the single largest thing this composition buys.

## Options considered

### Option 1 — Geometry is a separate run whose channels become a hashed `DataArtifact` input to the link run — REJECTED
The cleanest separation on offer, and it has a real economic argument the chosen option does not: geometry for a given pass is identical across every inner aleatory draw, so computing it *once* and referencing it from 400 runs (ADR-004's illustrative inner count) is 399 fewer trajectory evaluations per outer point. It also makes geometry a citable, reusable, cross-campaign object — two campaigns over the same passes could demonstrably share one geometry artifact by hash, which under the chosen option they cannot.

Rejected because it breaks the derivation that the identity scheme rests on. A link run's `RunSpec` would contain the *output* hash of a geometry run, which is not known until that run has executed, so `(experiment_hash, run_index) -> spec_hash` stops being a pure function of the design and becomes a two-phase plan-execute-plan protocol with a dependency graph nothing in the set describes. ADR-001 rule 5 calls that derivation "a derivation, not a database join", and AT-7 is written against it. It also doubles the ledger's population with runs of a second kind that resume, cancellation and the outcome taxonomy (ADR-023) would each need special cases for, and it puts an inter-run dependency edge into the execution plane, which plan §4 deliberately keeps free of everything except the single `ExperimentDesign -> RunSpec[i]` containment edge.

### Option 2 — The link-chain adapter furnishes kernels and calls SPICE itself — REJECTED
This is the option that happens by default under schedule pressure in week 3, and it deserves its strongest statement, which is not "it is a shortcut". Engines that carry their own ephemeris already do this: Basilisk has SPICE interface modules configured through its own topology, and GMAT configures ephemeris sources in its script. For those engines a FarSight-owned geometry stage in front of the engine is a *second* source of ephemeris in one run, and two sources that can disagree is worse than one source we did not choose.

Rejected on three grounds. It collapses the distinction ADR-003 drew one record earlier, and the collapse is not free: `GeometryProvider` exists because SPICE has no segment model, and re-admitting it as an engine-internal call means every future adapter re-implements kernel furnishing, furnish order (ADR-016) and frame and aberration conventions (ADR-015) privately, inside an opaque `engine_config` blob FarSight promises never to read — which is exactly where the domain's most common silent killers live (§14 item 3). It drags `spiceypy`, whose wheel bundles a compiled CSPICE, into the link chain's dependency closure, so the pure-Python flagship engine acquires a compiled NASA toolkit. And it quietly extends ADR-002's `reusable_worker` exemption to the link chain: a link-chain process that holds a kernel pool is a SPICE process, the exemption's SPICE-only wording stops meaning anything, and the recycling-off equality leg that makes the exemption falsifiable no longer tests the thing it names.

The steelman survives in one form, and the chosen design accommodates it rather than fighting it: an engine that owns its ephemeris simply has no geometry stage in its stage list, its kernel set is declared as a run input artifact and as a matched-configuration item (§14.7), and the *absence* of the stage is visible in the hashed `RunSpec` instead of being implicit in a config blob.

### Option 3 — `RunSpec` carries an ordered list of stages and the worker composes them — CHOSEN
The most general of the three, and it is chosen knowing that it changes the shape of the most-hashed document in the system. That cost is real and is the reason this record exists in week 3 rather than week 5: the change is nearly free now and invalidates the Tier-A golden corpus later.

### Option 4 — FarSight does not compute geometry in a link run at all; the user supplies a hashed geometry `DataArtifact` — REJECTED
Strictly the cleanest architecture available and close to what the 200-line notebook of §21's standing kill actually does. No composition, no second provider protocol in the worker, no `spiceypy` anywhere in the run path, and the package is self-contained and auditable with zero extras by construction.

Rejected because it moves the provenance of the geometry outside the tool at exactly the point where the product's claim is provenance. Replay could not regenerate the geometry, so AT-1's "re-execute from package content only" would mean re-executing everything except the input that dominates the answer; AT-11's SPICE-versus-Horizons and SPICE-versus-Astropy cross-checks would have nothing inside FarSight to check; and geometry could not vary with an epistemic coordinate, so a station-position or epoch-offset interval would have to be pre-expanded by hand into one supplied file per outer point. The week-1 exit gate exists precisely to produce hash-stable geometry *inside* the system.

## Consequences

**Buys us:** the flagship run becomes expressible, in the shape the plan already assumes. Geometry is stored as ordinary channels, so a zero-extras auditor can recompute the link metrics from package content without CSPICE. Composition is declared in a hashed document rather than hidden inside an adapter, so "which geometry did this run use" is answerable from `runspec_<i>.json` alone. State-dependent fault triggers can reference geometry with no extra machinery. And ADR-002's `reusable_worker` exemption keeps the exact scope it was granted.

**Costs us:** `RunSpec` gains a nested, ordered structure, so the planner, the freeze validator and the worker each grow a composition stage with its own tests and failure modes. Geometry is recomputed for every run that declares it: at ADR-004's own illustrative plan the same pass geometry is evaluated 400 times per outer point, and those 400 identical channel sets are all stored, which lands directly on ADR-011's package-size and file-count risk row rather than beside it. Two provider protocols now run inside one process, so an isolation failure has two candidate owners. And the composition rules are six more freeze-time refusals a customer can hit while authoring.

**Forecloses:** stage-output reuse, permanently in the MVP. There is no memo cache keyed on a stage's input hash, so identical geometry is recomputed and re-stored rather than shared, and adding one later is not a configuration flag — it is a claim that a cached stage is unobservable in the output hash, of exactly the kind ADR-002 demands a proof for.

Multi-engine runs are foreclosed by rule 2, and the loss is concrete and will be felt: a run that propagates attitude in Basilisk and then computes the optical link from that attitude is **not expressible as one run**. Attitude-to-link is two runs and a manual join, or a superseding record. Cross-engine comparison stays post-hoc; co-simulation is not a thing FarSight does.

Feedback between stages is foreclosed by rule 3's strict ordering: the pipeline is one-directional, so a geometry quantity that depends on an engine-produced state (a body-fixed pointing vector computed from propagated attitude, then fed back into a geometry-derived link term) cannot be expressed at all.

And Option 1's virtue is genuinely lost: geometry is not a citable knowledge-plane object. Two campaigns over identical passes have no way to say "these used the same geometry" other than comparing channel hashes after the fact, and every package carries its own full copy.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| An ordered stage list on `RunSpec`, replacing a single `engine_id` | 0.80 | The week-3 pipeline needs a binding that `StageInput`'s three members cannot express, or the composition validator exceeds two dev-days to make green before K3 (end wk 3). Either means the generality was bought at the wrong price and Option 2 with an explicit `spice` dependency in `linkchain` is the fallback. |
| At most one engine stage per run (the anti-workflow-engine cap) | 0.72 | Any of: the week-6 Basilisk work needs attitude-to-link in one run; >=2 of the 8 K5 interviews (end wk 6) describe a study that chains two engines within one case. Lifting the cap is a superseding record, not an incremental relaxation, because it changes what a tier claim and a matched configuration are about. |
| **No stage-output reuse: geometry is recomputed and re-stored per run** | **0.62** | Fires on measurement: `bench_geometry_stage_share` (below, week 4) records the geometry stage's share of a link-chain run's wall time and of package bytes. It fires if geometry exceeds 50 percent of either, or if the 10k-run campaign misses the overnight budget with the geometry stage named as the cause (§21 throughput kill). This is the lowest row in the record because the chosen design pays a 400x recomputation on the flagship's own sampling plan and nothing has measured what that costs. |
| `reusable_worker` as the conjunction over a run's stages | 0.88 | The SPICE recycling-off equality leg of `ci-worker-order-invariance` (defined in ADR-006) goes red, or a geometry-only run set is found to be the only place recycling ever applies, which would make the conjunction rule true and useless. |
| Stage-qualified channel names (`<stage_id>.<name>`) | 0.82 | ADR-020's grammar cannot admit the separator without ambiguity against a topology path (ADR-017), or the week-4 metric definitions need to name a channel without knowing which stage produced it. |
| Condition visibility: earlier stages whole, engine stage up to the current boundary | 0.78 | The week-5 fault campaign needs a predicate over an engine channel at a future index (a look-ahead trigger), which this rule refuses at freeze; that would mean the cadence model, not the visibility rule, is what needs changing. |
| Grid equality as the binding validity rule (rule 4) | 0.80 | ADR-020 decides that channels legitimately carry per-channel grids, in which case rule 4 becomes a resampling policy and resampling is a physics decision this record must not be making. |

## Enforcement

1. **`test_run_composition_schema`** (unit tier, Windows and Linux; **first green by week 3**): asserts all six composition rules as constructor and freeze validators — unique stage ids resolving to pairwise non-overlapping topology nodes, at most one engine stage and it is last, bindings referencing strictly earlier stages and declared `emits`, grid equality across every `ChannelSource`, stepping required for engine-channel predicates, non-empty stage list. Each failure raises `SpecCompositionError` (ADR-023) naming the stage id.
2. **`test_stage_binding_closure`** (**first green by week 3**): asserts that `StageInput`'s discriminated union has exactly three members and that none of them can name a run, a run index or an output hash. The closed derivation is enforced by the absence of a way to express its violation, in the same style as ADR-006's golden-attestation `source` enum; this test is what keeps that absence from being edited away.
3. **`tests/engine_contract/test_stage_composition.py`** (**first green by week 4**), a leg of `engine-contract-full` (defined in ADR-003): executes a two-stage DSOC-shaped run — `spice` geometry followed by `linkchain` — inside one worker, and asserts that both stages' channels are present under their qualified names, that the geometry channels are byte-identical to the same geometry evaluated as a geometry-only run, and that the link stage received the geometry arrays through its bindings rather than by reading a file.
4. **import-linter contract `geometry_is_not_an_engine`** (this record owns it; it ships in the `.importlinter` file ADR-013 assembles and runs in CI job `boundaries`, defined in ADR-013). **First green by week 3**: `spiceypy` may be imported nowhere under `src/farsight/` except `farsight.engines.spice.**`. This is the mechanical prevention of Option 2 — the architecture that happens by default under schedule pressure is blocked by a contract rather than by anybody remembering this record exists.
5. **`test_reusable_worker_conjunction`** (**first green by week 4**): a run whose stages include a provider with `reusable_worker == False` must execute in a fresh process — asserted by comparing worker PIDs across two consecutive such runs — while a geometry-only run set with recycling enabled may share one. The equality half (recycling on versus off produces identical channel hashes) is the third leg of `ci-worker-order-invariance` (defined in ADR-006), **first green by week 6**.
6. **Freeze validator `stage_capability_resolution`** (**first green by week 5**, when `faults/` exists): resolves each engine stage's declared capabilities against the run's compiled schedules and refuses at freeze, naming the stage and the provider, when a `ConditionSchedule` requires stepping the provider does not declare. Lowering then falls through to ADR-003's `config_time` or `refusal`; there is no path that silently evaluates a predicate once at the end.
7. **`bench_geometry_stage_share`** (**due week 4**, a measurement task rather than a pass/fail gate; **first green by week 4**): for one DSOC-shaped run and for a 960-run scaled campaign, records the geometry stage's share of wall time and of stored bytes, and writes both numbers into this record's Confidence table. It shares its fixture with `bench_package_scale` (defined in ADR-011) so the campaign is built once. The 0.62 row above is waiting on this instrument, and a measurement with no scheduled date is an intention.
8. **PARTIALLY MECHANIZED: COMPOSE-1** — whether a geometry stage's frame, time-scale and aberration conventions agree with an engine stage's own internal ephemeris configuration. Both live inside opaque per-dialect `config_ref` documents that FarSight validates against the provider's schema and never reads physically (ADR-003), so no check we can write compares them; a run whose geometry stage uses `LT+S` while the engine's internal SPICE modules use `NONE` passes every mechanical gate and produces plausible wrong numbers at the scale AT-11's 10 km tolerance is measured against. Residue: cross-provider convention agreement within one run. Review-checklist item **COMPOSE-1** — "do all providers in this run's stage list resolve geometry under the same frame, time scale and aberration correction, and is that stated in the matched-configuration document?" — whose sign-off lands in the `review_signoffs` list on the frozen `ExperimentDesign` (ADR-000), so an unanswered item is an auditable absence rather than a forgotten norm.

## References

- FARSIGHT_FOUNDATION_PLAN.md §1 (the DSOC flagship uses neither Basilisk nor GMAT; its geometry is reconstructed Psyche SPKs), §2 (product boundary; no universal physics ontology), §4 (four planes, the single containment edge, RunSpec as complete causal input), §5 (SPICE as a geometry service and the one place worker recycling is safe; the two-level contract sketch), §6 (repository tree; `engines/spice`, `engines/linkchain`), §11 (planner purity, all randomness pre-planned), §14 item 3 and §14.7 (frame and time-system errors as the domain's silent killers; matched-configuration declaration), §17 (week 1-2 `farsight geometry` exit gate; weeks 3-4 first pipeline), §18 (AT-1, AT-7, AT-11), §21 (K3, throughput kill).
- Engine and platform facts relied on here (CSPICE global kernel pool and one instance per process; GMAT per-process singleton; Basilisk segment model with no checkpoint) are stated once in plan §5 and restated once in ADR-003 References; they are not repeated in this record.
- ADR-001, ADR-002, ADR-003, ADR-006, ADR-010, ADR-011, ADR-013, ADR-015, ADR-016, ADR-020, ADR-023, ADR-024.
- UNVERIFIED — confirm at implementation time: whether a geometry stage evaluated over a full pass grid in one shot stays inside a worker's memory budget for the longest DSOC pass at the campaign's declared cadence (the sample counts implied by §17's pass geometry are not stated in the plan); and whether Basilisk's SPICE interface modules can be configured to consume a FarSight-supplied kernel set rather than furnishing their own, which decides whether a Basilisk run can ever carry a geometry stage or must always be the Option 2 shape with its kernel set declared as a matched-configuration item.
- **PLAN AMENDMENT REQUESTED: §4** — `RunSpec` gains an ordered `stages: list[StageSpec]` and loses `engine_id`, and `RunSpec.engine_config` moves onto `StageSpec` as `config_dialect` + `config_ref`; the engine a run belongs to is derived from its stage list, and a run with no engine stage is a legitimate geometry-only run. §4 describes `RunSpec` as the complete causal input without saying how a run that needs both a geometry service and an engine expresses that, and §5's `GeometryProvider` is deliberately not an `Engine`, so as written the flagship DSOC link run is not expressible.
- **PLAN AMENDMENT REQUESTED: §6** — extras become `spice`, `basilisk`, `gmat`, `analysis`, `dev`. This record puts `spiceypy` behind the `spice` extra and forbids it everywhere outside `farsight.engines.spice` (Enforcement item 4), which presupposes it is an optional extra rather than a core dependency; §6 lists extras as `basilisk, gmat, analysis, dev`. The consequence for the audit path is stated plainly and is ADR-007's to carry: replaying a run that has a geometry stage requires the `spice` extra, while verifying it does not. ADR-014 owns the dependency table.
- Refinement of §13, not a departure: geometry channels are ordinary run channels and appear at `runs/channels/<i>/<name>.npy` under their stage-qualified names, so a package containing a link campaign contains the geometry it used.
