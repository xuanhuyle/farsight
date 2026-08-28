# ADR-003 — Two-level engine adapter contract, capability flags, and refusal over approximation
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §5, §2 (refused: universal spacecraft ontology), §10 (engine binding), decisions D3 and D11
**Related ADRs:** ADR-002 (adapters run inside the isolated worker and declare `isolation`/`reusable_worker` to it), ADR-010 (`FaultBindingImpl` and the freeze-time binding check are the fault half of this contract), ADR-005 (`seed_scope` decides how FarSight-drawn seeds reach the engine, and adapters never sample), ADR-001 (refusal is recorded into the frozen design, so it is content-addressed), ADR-008 (each adapter owns its unit conversion table), ADR-013 (owns the `auditor_boundary` and `adapters_only_via_base` contracts this record's Enforcement cites), ADR-015 (defines `SimTime` and the epoch representation `run_to` takes), ADR-016 (defines `KernelRef` and furnish order for `GeometryProvider`), ADR-018 (run composition: how a `GeometryProvider` and an `Engine` coexist inside one run), ADR-020 (the channel model `collect()` emits), ADR-023 (the outcome taxonomy `UnhonorableSpec` and a refused lowering resolve into)

## Context

The forcing question: what is the smallest interface Basilisk, GMAT, the FarSight link chain, and SPICE can all honor **without any of them lying**?

They are not variations of one thing. Basilisk is steppable (repeated `ConfigureStopTime` plus `ExecuteSimulation`), supports mid-run mutation of any SWIG-exposed module attribute between segments, offers `createNewEvent` condition/action hooks and `enableTask`/`disableTask`, seeds per module via `RNGSeed` with no global seed, and has no checkpoint. GMAT is a per-process singleton with no reliable reset, not thread-safe, script-driven, realistically one run per process. SPICE is not a simulation engine at all — it is a deterministic geometry service over a global kernel pool. The link chain is ours and can do anything we ask.

Pick the wrong shape and one of two failures follows. Size the universal interface for the richest engine and GMAT and SPICE implement half of it as `NotImplementedError`, which converts a plan-time fact ("this campaign cannot run on GMAT") into a crash at run 8,300 of an overnight campaign. Size it for the weakest and mid-run fault injection disappears from Basilisk, the only engine that has it — and the fault framework is the weeks-5-6 deliverable and the main thing distinguishing FarSight from Basilisk's own MonteCarlo Controller.

A third failure has killed this entire product category: cross-simulator meta-frameworks die when they grow a universal spacecraft ontology and spend their lives translating physics between engines that disagree about what a force model is. §2 names it as scope-creep hot spot #1 with an explicit review tripwire. The contract has to standardize the run protocol without ever acquiring an opinion about spacecraft.

## Decision

**Level 1 — a universal core every adapter implements exactly, and nothing more.**

```python
@runtime_checkable
class Engine(Protocol):
    @classmethod
    def capabilities(cls) -> EngineCapabilities: ...
    def initialize(self, spec: RunSpec) -> None: ...   # raise UnhonorableSpec, never default
    def run_to(self, t: SimTime) -> SegmentReport: ... # non-steppers accept only spec.end_time
    def collect(self) -> RunOutput: ...                # typed channels + engine manifest
    def finalize(self) -> None: ...
```

**Level 2 — optional capability protocols, claimed by flag and verified by contract test.**

```python
@runtime_checkable
class SupportsIntervention(Protocol):
    def apply_intervention(self, iv: Intervention) -> InterventionAck: ...  # segment boundary only

@runtime_checkable
class SupportsNativeDispersions(Protocol):
    def apply_dispersions(self, values: Mapping[str, float]) -> None: ...   # CONCRETE values only

@runtime_checkable
class GeometryProvider(Protocol):          # SPICE service; deliberately NOT an Engine
    def furnish(self, kernels: Sequence[KernelRef]) -> None: ...   # KernelRef: ADR-016
    def state(self, req: GeometryRequest, et: SimTime) -> tuple[float, ...]: ...   # GeometryRequest: ADR-015 (target, observer, frame, aberration, quantity_class)
```

`SimTime` and the epoch representation it carries are defined by ADR-015, not here, and so is `GeometryRequest` — `state` takes a request object rather than loose arguments because ADR-015 makes `aberration` a mandatory field with no default anywhere in the code path, and an adapter handed only `target`, `observer` and `frame` would have to invent the value that record forbids it to have. `KernelRef` and the significance of furnish order are defined by ADR-016. This record owns only the shape of the call.

**The flags are the planning surface.**

```python
class EngineCapabilities(BaseModel, frozen=True, extra="forbid"):
    engine_id: str                      # "basilisk" | "gmat" | "linkchain" | "spice"
    config_dialect: str                 # names the adapter's OWN config schema; opaque to FarSight
    supports_stepping: bool
    supports_midrun_intervention: bool
    supports_native_dispersions: bool
    seed_scope: Literal["none", "global", "per_module", "per_stream"]
    isolation: Literal["process_required", "process_preferred"]
    reusable_worker: bool                                   # consumed by ADR-002
    best_reproducibility_tier: Literal["A", "B", "C"]       # a ceiling; packagers may only downgrade
    fault_mechanisms: frozenset[Literal["attribute_mutation", "task_disable",
        "message_intercept", "parameter_override", "native_model_hook"]]
    state_handoff: Literal["complete", "partial", "none"]   # gates segment_split lowering
```

Declared flags, not `isinstance` probing, are what the planner reads; a mismatch between a declared flag and the implemented protocol is a contract-test failure rather than a runtime surprise. Because planning happens in the parent process while ADR-002 keeps engine imports inside workers, **`capabilities()` must be importable without importing the engine SDK** — `farsight.engines.<name>.capabilities` imports no `bsk`, no GMAT tree, no `spiceypy`. That is what lets `farsight plan` run on a laptop with no extras installed, and it is the same property that ADR-013's `auditor_boundary` contract enforces one layer down.

**Fault lowering has exactly four modes,** chosen at freeze by the pure compiler in `farsight/faults/`:

1. `native` — the engine offers a real mechanism (Basilisk: attribute mutation between segments, `enableTask`/`disableTask`, `createNewEvent`).
2. `config_time` — the fault is active from t0 and expressible as an initial-condition or model-parameter change. Available on any engine.
3. `segment_split` — the run is cut at the activation epoch and restarted with mutated state. Permitted **only** when the adapter declares `state_handoff == "complete"` and has passed the zero-magnitude mutation test (AT-10) on that engine build; otherwise the mode is unavailable and lowering falls through to refusal.
4. `refusal` — no mode applies. Freeze records `unsupported_on: ["gmat"]` on the affected `FaultActivation`, the planner generates no runs for that (fault, engine) pair, and the evidence package carries the refusal verbatim. A campaign whose routing *requires* an unsupported pair fails at freeze, naming the fault id and the engine. There is no fifth mode called "approximate".

**Two non-goals, stated as decisions because they will be re-proposed.**

*No universal physics ontology.* `StageSpec.config_ref` (ADR-018) names an opaque, content-addressed, engine-native document; `config_dialect` names the adapter's own JSON Schema. FarSight validates the blob against that schema and hashes it, and never reads a physical quantity out of it. Basilisk task topology and message wiring, GMAT script templates and dotted paths, and SPICE kernel and frame curation are never abstracted.

*No engine-owned sampling.* FarSight owns all sampling (D11); Basilisk's `MonteCarlo.Controller` is not used for it. `SupportsNativeDispersions` exists purely so an adapter may reuse Basilisk's dispersion-**application** classes to write FarSight-drawn values into modules — hence a signature taking `Mapping[str, float]` of concrete numbers, never a distribution and never a seed. The `float` there is deliberate and is not a violation of ADR-001: this is an in-memory call at the engine boundary, not a hashed document, and the hashed form of the same value is the decimal-string `Quantity` in the RunSpec that the adapter converted from.

## Options considered

### Option 1 — One fat interface sized for the richest engine — REJECTED
A single mental model, no flag algebra, no capability-resolution stage in the planner; it is what most orchestration frameworks ship and it is genuinely simpler for three devs in week five. Rejected because GMAT and SPICE would implement over half of it as `NotImplementedError`, relocating every capability question from freeze time to run time. Refusal must be a fact printed at freeze, before an overnight campaign starts, or the honesty property is decorative.

### Option 2 — Lowest common denominator sized for the weakest engine (initialize, run once, collect) — REJECTED
Small, honest, easy to contract-test, and sufficient for the entire flagship: the DSOC benchmark propagates nothing and needs no intervention, so this would ship weeks 1-4 with a smaller surface. Rejected because it deletes mid-run fault injection from Basilisk, the only engine that has it, and the fault framework plus the common-cause weather campaign are what separate us from Basilisk's own MC Controller. Choosing it means an orchestrator whose capability set equals its weakest member forever.

### Option 3 — Per-engine bespoke drivers, no shared protocol — REJECTED
No abstraction tax; each engine driven exactly as its own documentation says, which is how the fastest prototype gets written and how gmat-sweep works. Rejected because the contract suite that runs identical tests against `FakeEngine`, the link chain, and Basilisk (§6) is precisely what keeps "engine-neutral" from being marketing, and with bespoke drivers that suite cannot exist. Cross-engine comparison also needs a common notion of "the same run at the same epochs" to mean anything.

### Option 4 — Universal physics ontology plus per-engine translators — REJECTED
The only design that could auto-generate matched configurations, and §19 ranks matched configuration as the number-one three-week sink (gravity degree and order, DE440 versus defaults, EOP, time systems). It attacks the hardest real problem in the plan. Rejected anyway: it is the documented graveyard of this category, and §14.7 already has a non-ontological answer — matched configuration is a declared schema object that enumerates the *unmatched* items, making mismatch visible instead of pretending it was translated away.

## Consequences

**Buys us:** refusal at freeze rather than failure at run 8,300; a planner that routes common-cause fault studies to engines declaring `supports_midrun_intervention` and routes cross-validation to injection-free or config-time scenarios both engines express; an adapter surface small enough that the "minimal Basilisk adapter, about one dev-week" estimate in §17 is testable against the adapter-cost kill; and engine neutrality that is falsifiable rather than asserted.

**Costs us:** the planner gains a capability-resolution stage with its own tests and failure modes. The flags are a coarse model of engine reality and will need extension, and every extension is a schema-version bump on a frozen, content-addressed document. Two adapters can declare identical flags and still differ in ways the flags do not capture, so contract tests must probe behavior, not presence. And customers will read `unsupported_on: ["gmat"]` and ask for the approximation anyway; we will be saying no repeatedly, in sales conversations.

**Forecloses:** FarSight can never translate a scenario between engines. A customer with a GMAT mission who wants the same case in Basilisk gets nothing from us — they author both configs and declare the unmatched items by hand, and a competitor will claim otherwise. Second, and it must appear in the claim statement of any package comparing engines: **common-cause and mid-run fault campaigns are Basilisk-only in the MVP**, so every cross-engine result we ship in the first eight weeks is an injection-free result. Cross-validation and fault injection do not overlap yet.

Third, and it is a foreclosure with a date on it: **the falsifiability of engine neutrality is hostage to Basilisk surviving §17's scope-cut order, where it is item 1.** If Basilisk is cut, `engine-contract-full` parametrizes over `FakeEngine` and the link chain — two components FarSight wrote — and the suite becomes a test that our code agrees with our code. It would still be worth running; it would no longer be evidence of anything about third-party engines. In that event the engine-neutrality claim is withdrawn from external materials in the same commit that descopes the adapter, and the mechanical guard is that `engine-contract-full` emits the list of adapters it actually exercised into `environment/fingerprint.json`, so a package claiming cross-engine neutrality with fewer than two third-party adapters in that list fails verification.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Two levels (a minimal universal core plus optional capability protocols) rather than one interface | 0.88 | A third engine lands (Tudat, F Prime) and cannot be expressed without either widening the core or adding a third level — that is, the two-level split stops being a partition of the real capability space. |
| Declared flags read by the planner, rather than `isinstance` probing of the adapter | 0.85 | Any flag acquires an engine-dependent meaning — that is, the same `True` means different things for two adapters — at which point capabilities become a declared, versioned document rather than a struct. (The earlier trigger, "the flag set exceeds roughly ten booleans", is retired: `EngineCapabilities` has eleven fields but only four booleans, so it was calibrated an order of magnitude past any plausible growth and could never fire.) |
| Four lowering modes with `refusal` as the fourth, and no "approximate" mode ever | 0.90 | >=3 of the 8 K5 discovery interviews (end wk 6) name refusal-without-approximation as a reason they could not adopt. The only admissible answer then is a fifth mode that is permanently tainted and confined to `evidence_grade: exploratory`, argued in a superseding ADR — never an exception granted quietly. |
| No universal physics ontology; the per-stage engine config (`StageSpec.config_ref`, ADR-018) stays an opaque per-dialect blob | 0.90 | A cross-engine comparison ships and the declared-unmatched-items list (§14.7) is longer than the matched list, meaning the non-ontological answer is not actually producing comparable runs. This is observable at K4, not before. |
| `capabilities()` importable with no engine SDK present | 0.85 | `test_capabilities_import_is_engine_free` requires a sentinel-mocking apparatus that exceeds one dev-day to maintain across two adapters, or an engine SDK is found to be imported transitively through a type annotation that cannot be deferred. |
| `segment_split` gated on `state_handoff == "complete"` | 0.70 | GMAT's file-based state handoff is proven complete during the week-1 GMAT spike or at K4, which would move fault campaigns off Basilisk-only; or the week-5 fault work finds that no engine we have can honestly declare `complete`, in which case the mode is dead code and should be deleted rather than carried as an aspiration. This is the lowest row because the flag's only consumer is an engine that is post-MVP and behind a kill gate. |

One trigger applies to the record as a whole: the adapter-cost kill (§21) fires — the minimal Basilisk adapter exceeds two dev-weeks — in which case the question is whether this contract's surface, rather than Basilisk, is what cost the time.

## Enforcement

- **`tests/engine_contract/`**, parametrized over `FakeEngine`, `linkchain`, and Basilisk, required in the Linux container job **`engine-contract-full`** (skipped locally only when the extra is absent): every adapter satisfies `Engine`, and **every declared flag has a paired behavioral test**. `supports_midrun_intervention == True` requires passing AT-10 (zero-magnitude fault bitwise identical to baseline) and AT-12 (mid-run fault at t=T changes post-T channels only, pre-T bitwise identical). `supports_midrun_intervention == False` requires that `apply_intervention` raises; a silent no-op fails the suite. First green: `FakeEngine` leg by **week 2**, `linkchain` leg by **week 4**, Basilisk leg by **week 6** — and never, if Basilisk is descoped under §17's scope-cut order, which is the event the third Forecloses paragraph is about. The job also writes the adapters it exercised into `environment/fingerprint.json`.
- **`test_capabilities_import_is_engine_free`** (first green by **week 2** for `spice` and `FakeEngine`, **week 6** for all adapters): importing `farsight.engines.<name>.capabilities` with the engine SDK replaced by an import-raising sentinel in `sys.modules` must succeed for every adapter.
- **Freeze validator `fault_binding_completeness`** (first green by **week 5**, when `faults/` exists): a `FaultCampaign` referencing a fault with no `FaultBindingImpl` for its routed engine fails at freeze, exits nonzero, and names the fault id and engine id (§10). A silent skip is impossible because the planner enumerates runs only from lowered activations.
- **import-linter contracts** (first green by **week 1**; the contracts are owned by ADR-013 and ship in the `.importlinter` file it assembles, run by CI job `boundaries`, defined in ADR-013): `farsight.faults`, `farsight.uncertainty` and `farsight.experiments` may not import any concrete adapter package (`farsight.engines.spice|basilisk|linkchain|gmat`) — they see adapters only through `farsight.engines.base` protocols. `farsight.engines.worker` is deliberately outside that ban: it is subprocess plumbing, importable from `farsight.experiments.runner` and `farsight.cli` only (ADR-002, ADR-013 contract `adapters_only_via_base`). `farsight.evidence` and `farsight.hashing` may not import `farsight.engines` at all (the auditor-laptop rule, §6; import-linter contract `auditor_boundary`, defined in ADR-013).
- **`no-naked-rng` AST lint** (defined in ADR-005; first green by **week 1**): `numpy.random`, `random`, and `secrets` are forbidden under `src/farsight/engines/**`, mechanically preventing an adapter from sampling.
- **Ontology tripwire `no-physics-in-shared-schema`** (first green by **week 1**): an AST test over `farsight.schemas` asserting no field name matches a physical-quantity denylist (mass, thrust, area, isp, gm, force, inertia, and similar) outside `Quantity` itself and outside the opaque engine-native config blobs a `StageSpec` names by `config_ref` (ADR-018). The denylist also carries **fleet-structure** names — `population`, `count`, `attrition`, `survival`, `generation`, `swarm`, `route`, `topology_edge` — for the same reason and with the same scope: they are banned as *Python field names in `farsight.schemas`*, never as customer node or channel names, which remain strings we sort and print (ADR-017 rules 7 and 8). Fleet vocabulary is the form the ontology arrives in when the stress case is a swarm rather than a spacecraft, and the tripwire should recognize it by name. **PARTIALLY MECHANIZED:** a denylist recognizes names, not concepts, and a physical quantity arriving under an innocent name (`payload_figure`, `budget_term`) passes it cleanly. The residue is review-checklist item **PHYS-1** ("does this schema field describe the run protocol or the spacecraft?"), which §2 states as the review tripwire for scope-creep hot spot #1, and whose sign-off lands in the `review_signoffs` list on the frozen `ExperimentDesign` (ADR-000), so an unanswered item is an auditable absence rather than a forgotten norm.

## References

- FARSIGHT_FOUNDATION_PLAN.md §2 (product boundary; refused universal spacecraft ontology and its tripwire), §3 (D3, D11), §5 (engine ground truth and the two-level contract sketch), §6 (boundary rules, contract-test suite), §10 (fault binding mechanisms, freeze-time failure), §14.7 (matched-configuration methodology), §17 (minimal Basilisk adapter scope; scope-cut order), §18 (AT-10, AT-12), §19 (risk 1), §21 (adapter-cost kill, K4, K5).
- **Verified engine facts (checked 2026-08-26) — this block is the canonical restatement for the ADR set; other records cite it rather than repeating it.** Basilisk (ISC, pip `bsk`, Python >=3.9 <3.15, Windows supported) supports repeated `ConfigureStopTime` plus `ExecuteSimulation`, mid-run mutation of SWIG-exposed attributes between segments, `createNewEvent(name, rate, active, conditionList, actionList)`, `enableTask`/`disableTask`, per-module `RNGSeed` with no global seed, message recorders to numpy, and no mid-run checkpoint or state serialization; it ships `MonteCarlo.Controller` (dispersions, seed dispersal, JSON IC archive, `reRunCases`), which FarSight does not use for sampling. GMAT (Apache 2.0, Python API production-quality since R2022a, Python 3.9-3.12) is a per-process singleton with no reliable in-process reset, not thread-safe, and not pip-installable; the community pattern is one run per fresh subprocess with file-based collection (gmat-sweep; its license is not stated in the plan and is UNVERIFIED here). CSPICE has a global mutable kernel pool and is not thread-safe, so one instance per process with kernels furnished per worker is the only supported shape; SpiceyPy (MIT wrapper, bundled CSPICE) provides a `KernelPool` context manager for scoped loads (the version that introduced it is UNVERIFIED — confirm at implementation time). All of the above is plan §5; nothing here is asserted beyond it.
- ADR-002, ADR-005, ADR-006, ADR-008, ADR-010, ADR-013, ADR-015, ADR-016, ADR-018, ADR-020, ADR-023.
- UNVERIFIED — confirm at implementation time: whether GMAT's file-based state handoff is complete enough for `segment_split` (the plan calls it "limited, must verify complete state handoff or refuse"); the Basilisk version pin required for the post-construction `RNGSeed` fix (§20 open question 4).
