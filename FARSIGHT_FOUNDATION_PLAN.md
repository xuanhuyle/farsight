# FarSight Foundation Plan

**Deep-Space Autonomy Verification & Mission Evidence Platform — foundation architecture and MVP plan**

Date: 2026-08-26 · Status: approved for review · Author: founding technical architecture (planning phase — no implementation yet)

Basis: verified research (all sources checked 2026-08-26) on dependency licensing and redistribution, DSOC public-data feasibility, Basilisk/GMAT/SPICE API ground truth, prior art (Basilisk MC Controller, gmat-sweep, JPL MONTE, Dakota, Sedaro, NOS3, NASA-STD-7009 practice), plus an adversarial red-team of the product thesis. Three plan-shaping decisions confirmed by the founder: **(1)** DSOC flagship benchmark + DSN RF precision anchor with pre-registration; **(2)** pure-Python link chain first, minimal Basilisk adapter in weeks 5–6, GMAT post-MVP; **(3)** a commercial-validation track runs in parallel as a first-class deliverable.

---

## 1. Executive recommendation

Build an **8-week thesis test, not a product**. The brief conflates two loosely-coupled MVPs — an *evidence pipeline* (SPICE geometry → link model → uncertainty decomposition → verifiable package) and an *engine-orchestration platform* (Basilisk/GMAT adapters, fault injection, cross-validation). The flagship DSOC benchmark uses **neither Basilisk nor GMAT** (its geometry comes from reconstructed Psyche SPICE kernels — no propagation occurs). Sequence them explicitly: evidence pipeline first (weeks 1–4), engine orchestration second (weeks 5–6), external-quality demonstration last (weeks 7–8), with a commercial-discovery track in parallel throughout.

Verified conclusions underpinning this plan:

- **The DSOC benchmark is feasible without fitting undocumented parameters.** Psyche reconstructed SPKs cover the full DSOC prime mission at NAIF's PDS4 archive — which even ships the Palomar/OCTL/Helmos/Kryoneri ground-station SPKs. Public data supports an honest **±2–3 dB envelope** (one discrete rate-ladder step), *not* 20% agreement. The testable claim is "achieved rate ≤ predicted supportable envelope, within N ladder steps" — achieved rates are operationally chosen with unpublished margin, and the 267 Mbps points are hardware-capped.
- **The DSN RF benchmark (810-005 + DESCANSO, fully public, ±1 dB, zero unknowns) runs first** as the precision anchor: any miss there is a bug, not an "unknown." Two benchmarks tell one story: *tight when parameters are known, honest when they aren't.*
- **The headline deliverable is the uncertainty decomposition, not the prediction**: "at 2.6 AU the envelope is X dB wide and Y dB of that is GLR optical-train throughput; here is the measurement that would halve it." No existing tool produces that artifact; it wins whether the envelope is tight or wide.
- **Pre-registration**: publish the predicted envelope with content hashes *before* purchasing the paywalled per-pass SPIE 13355 / IEEE JSTQE papers (~$300), then score against them. Converts a weak consistency check into a circularity-proof falsification narrative.
- **The moat is unproven but testable in 8 weeks.** Every mechanism exists in pieces (Basilisk's MC Controller: dispersions/seeds/JSON archives; gmat-sweep: SHA-256 manifests + subprocess isolation; GMAT's V&V program: the cross-tool methodology; Dakota: UQ). Nothing combines cross-engine validation + aleatory/epistemic separation + fault injection + independently verifiable evidence. Whether that combination is a *purchasable product* is answered by discovery interviews and the engineer-hours ledger, not by code.

Confidence: high on technical feasibility; genuinely uncertain on the commercial thesis — which is why the kill criteria (§21) are dated gates, not aspirations.

## 2. Product boundary

**FarSight owns:** experiment definition and immutable composition; the model/provenance registry; uncertainty representation and propagation semantics (the aleatory/epistemic type system); fault definition, activation, and lowering; seeded deterministic sampling and the run ledger; engine adapters and the capability-flag contract; metrics and acceptance rules as versioned pure functions; cross-engine and model-vs-referent comparison semantics; evidence-package format, verification, and replay; the CLI.

**External engines own:** all physics. Orbit propagation, attitude dynamics, GNC algorithms (Basilisk); trajectory reference (GMAT); geometry/frames/time/ephemerides (SPICE). FarSight never reimplements physics that a validated engine provides — the sole exception is *simple, closed-form-testable subsystem models* (link budget, battery ODE) where no engine offers them and every equation has a hand-checked worked example.

**Customers provide:** mission definitions, spacecraft parameters with sources, uncertainty inputs with pedigree, referent data for validation, acceptance thresholds. FarSight refuses to invent any of these — a parameter without provenance enters as `unknown`, never as a default.

**Explicitly refused initially:** thermal FEA, CFD, radiation transport, structural sim, laser-sail material physics, universal component libraries, RL controllers, Starshot digital twin, certification claims, HWIL, replacements for STK/Sedaro/GMAT/Basilisk. Also refused: **a universal spacecraft ontology** (the documented graveyard of cross-simulator frameworks — adapter configs stay engine-native; FarSight standardizes the run protocol and evidence format, not the physics schema).

**Scope-creep hot spots, ranked, with tripwires:**
1. *Universal physics ontology* — tripwire: any shared schema model containing physical quantities (mass, thrust, force model) rather than run-protocol fields (times, seeds, hashes, channels) is rejected in review.
2. *Third engine before the second earns its keep* — tripwire: no Tudat/F Prime tracker item until one cross-engine comparison with pre-stated tolerance has shipped inside an evidence package.
3. *Evidence crypto becoming a PKI project* — tripwire: MVP crypto = SHA-256 manifest + one optional detached minisign signature; any key-management document over one page is cut.
4. *Adversarial-search sophistication* — tripwire: MVP sampling = seeded LHS/MC only; any optimizer/surrogate import (scikit-optimize, BoTorch, GPy) is an automatic revert.
5. *UI polish* — tripwire: no frontend framework dependency for 8 weeks; one static generated report template, frozen by week 5.

## 3. Key architecture decisions

| # | Decision | Recommendation | Conf. |
|---|---|---|---|
| D1 | Overall shape | Modular monolith, Python, single `farsight` package (src layout), engine adapters behind optional extras | 0.9 |
| D2 | Execution unit | **Process isolation universally**: every engine run = fresh OS process fed a serialized RunSpec (GMAT and CSPICE require it; uniform for all) | 0.95 |
| D3 | Adapter contract | Two-level: minimal universal core + optional capability protocols with declared flags; **refusal is a first-class outcome**, never silent approximation | 0.9 |
| D4 | Identity | Content addressing: SHA-256 over canonical JSON (RFC 8785/JCS profile); draft→frozen lifecycle; names are mutable aliases (git-ref model) | 0.9 |
| D5 | Quantities in specs | Decimal strings + unit (`{"magnitude": "0.22", "unit": "m"}`) — never JSON floats in hashed documents; NaN/Inf forbidden | 0.85 |
| D6 | Units | Astropy-backed typed boundaries; raw SI float64 in all inner loops; per-adapter explicit conversion tables | 0.9 |
| D7 | Uncertainty | Tagged-union `Belief` type + two-loop propagation (outer epistemic scan, inner seeded aleatory MC); no `.to_distribution()` on epistemic types; authorized `EpistemicCollapse` records | 0.85 |
| D8 | Faults | `FaultMode` (catalog) / `FaultActivation` (design) / `FaultActivationRecord` (execution); common cause via shared latent factors; restricted predicate AST, no embedded Python | 0.85 |
| D9 | Seeding | 128-bit root seed → `SeedSequence` spawn-key derivation by (run, stream) — O(1) addressable, Philox generator; derived seeds archived per run | 0.9 |
| D10 | Storage | Evidence = files; channels as canonical little-endian float64 `.npy`; SQLite (WAL) only for the local run ledger + alias registry + audit log. No PostgreSQL roadmap line — packages are files | 0.85 |
| D11 | Sampling ownership | FarSight owns all sampling; Basilisk's MC Controller is *not* used (its dispersion-application classes may be reused inside the adapter) | 0.9 |
| D12 | Tooling | uv + hatchling, PEP 621; Python 3.12 pinned (inside GMAT's 3.9–3.12 ceiling, Basilisk's <3.15); `uv.lock` SHA-256 goes into every evidence package | 0.85 |
| D13 | Reproducibility | Three tiers: A bitwise-in-pinned-container, B cross-platform tolerance-bounded, C cross-engine physical tolerances (§12) | 0.9 |
| D14 | LLM boundary | Enforced structurally: no LLM SDK dependency anywhere; import-linter CI rule. Nothing in the MVP uses an LLM — the claim is an architectural absence, not a feature | 0.95 |

## 4. Domain model

The proposed linear hierarchy (Mission → ModelSet → Scenario → UncertaintySet → FaultCampaign → Experiment → Runs → Metrics → Evidence) is **rejected** — it is factually wrong about dependencies: UncertaintySpec and FaultCampaign are composable siblings, not levels (the DSOC benchmark has no faults; forcing a FaultCampaign level makes it a mandatory pass-through); ModelSet under Mission kills cross-mission model reuse; "Metrics under Runs" conflates spec with value (making "metric changed mid-campaign" undetectable — fatal for evidence); Evidence is not a leaf but a Merkle closure over the whole graph; and the **Referent** (the observed real-world data being compared against — the NASA-STD-7009 term) is missing entirely from the candidate list.

**Replacement: four planes connected as a DAG** (the git model — immutable objects, mutable refs), with exactly one containment edge (`ExperimentDesign → RunSpec[i]`):

- **Knowledge plane** (immutable, content-addressed, mission-independent): `Source`, `DataArtifact` (kernels, referent files — SHA-256), `Referent` (+`ReferentPoint`: epoch, value, stated uncertainty, caveats), `Assumption`, `Model`/`ModelVersion` (with validity envelope, engine binding, verification status), `ParameterDecl`, `SystemTopology` (the naming authority: typed node tree spanning flight *and ground* — replaces Vehicle/Environment, which break on DSOC where two ground stations are half the system), `FaultMode`, `CommonCauseFactor`, `EngineBuild`.
- **Design plane** (draft → frozen): `ScenarioTemplate` (epoch span, initial states, model wiring, no free-floating literals), `UncertaintySpec` (beliefs + correlation groups + latent factors), `FaultCampaign`, `MetricSpec`, `AcceptanceCriterion` (verdict domain **pass | fail | indeterminate** — "epistemic band straddles the criterion" is a first-class result, not an error), `ComparisonSpec` (matched-configuration declaration), `ExperimentDesign` (the composition root; UI alias "Study"; `evidence_grade: evidence | exploratory`).
- **Execution plane** (append-only, produced, never authored): `RunSpec` (complete causal input; `run_id = sha256(RunSpec)`), `RunResult` (status incl. `diverged`, validity flags, channel hashes), `MetricValue`, `AggregateResult` (per-outer-point inner distributions + cross-outer envelope — an empirical p-box), `ComparisonResult`, `Verdict` (with `contains_epistemic_collapse` taint), `FaultActivationRecord`, `EvidencePackage`.
- **Context plane** (mutable): `Mission` workspace (organizes, never owns), alias registry, annotations. Deprecation = new pointer records, never edits.

```
ExperimentDesign = compose( ScenarioTemplate, UncertaintySpec, [FaultCampaign],
                            SamplingPlan, MetricSpecs, AcceptanceCriteria, [ComparisonSpecs] )
   └─ expand+sample ─> RunSpec[i] ─worker─> RunResult[i] ─> MetricValue[i,k]
                                   └──────── aggregate ──> AggregateResult ─> Verdicts ─> EvidencePackage
```

**Immutability invariant:** nothing frozen may reference anything mutable or draft. Freezing computes the hash, validates completeness (no silent defaults — adapters demand full bindings), and records the freezing human identity. LLM-assisted authoring is permitted at draft stage; **freeze authorization is always a human act**.

## 5. Simulation-engine integration strategy

**Ground truth (verified against current docs/releases):**
- *Basilisk* (ISC license, pip `bsk` wheels, Windows supported, Py ≥3.9 <3.15): run-to-time via repeated `ConfigureStopTime`/`ExecuteSimulation`; mid-run injection via attribute mutation between segments, `createNewEvent` condition/action hooks, `enableTask`/`disableTask`; per-module `RNGSeed` (pin a version ≥ the post-construction seed fix); message recorders → numpy; integrators RK4 default, RKF45/78 selectable with tolerances. **No mid-run checkpoint** — replay-from-log is the checkpoint model. Its built-in MonteCarlo Controller (dispersions, seed dispersal, JSON IC archive, `reRunCases`) is the closest in-house competitor feature: FarSight must exceed it (cross-engine, epistemic/aleatory split, evidence, search) and not rebuild its plumbing.
- *GMAT* (Apache 2.0 since R2016a; API production since R2022a; Py 3.9–3.12): engine is a **per-process singleton, no reliable reset, not thread-safe**; community-standard pattern (gmat-sweep) is one run per fresh subprocess with file-based collection. Not pip-installable — the adapter shells out to a user-installed GMAT tree (also sidesteps redistribution audit of its bundled third-party components). Cross-check engine only, post-MVP.
- *SPICE/SpiceyPy* (MIT wrapper; CSPICE embedded per NAIF rules): global kernel pool, **not thread-safe** — one instance per process, kernels furnished per worker (Windows spawn requires it anyway), `KernelPool` context manager for scoped loads. Deterministic given kernels: the easiest Tier-A component. Modeled as a **geometry service** (`GeometryProvider`), not a sim engine; the one place worker recycling is safe.

**Contract (two-level):**

```python
class Engine(Protocol):          # universal core — every adapter implements exactly this
    @classmethod
    def capabilities(cls) -> EngineCapabilities: ...   # flags: supports_stepping,
        # supports_midrun_intervention, supports_native_dispersions,
        # seed_scope, isolation, reusable_worker, deterministic tier
    def initialize(self, spec: RunSpec) -> None: ...   # fail loudly on anything unhonorable
    def run_to(self, t: SimTime) -> SegmentReport: ... # non-steppers accept only end_time
    def collect(self) -> RunOutput: ...                # typed channels + engine manifest
    def finalize(self) -> None: ...

class SupportsIntervention(Protocol): ...              # optional capability protocols
class SupportsNativeDispersions(Protocol): ...
class GeometryProvider(Protocol): ...                  # SPICE service, SPICE-native surface
```

The orchestrator plans around declared flags rather than a lowest common denominator: common-cause fault studies route to engines with mid-run intervention (Basilisk); cross-validation uses injection-free or config-time-fault scenarios both engines express. **Fault lowering** has four modes: native (Basilisk segments/events), config-time (any engine, faults active from t0), segment-splitting (GMAT, limited, must verify complete state handoff or refuse), and **refusal** (`unsupported_on: [gmat]` reported at freeze — never silently approximated). Engine-specific surfaces are never abstracted: Basilisk task topology/message wiring, GMAT script templates/dotted paths, SPICE kernel/frame curation.

## 6. Repository architecture

```
farsight/
├── pyproject.toml            # PEP 621; extras: basilisk, gmat, analysis, dev
├── uv.lock                   # SHA-256 recorded in every evidence package
├── src/farsight/
│   ├── schemas/              # Pydantic v2; the ONLY typed vocabulary; imports nothing else
│   │   ├── common.py         #   Quantity(magnitude: str, unit), Pedigree, ValidityEnvelope, refs
│   │   ├── belief.py         #   Deterministic|Aleatory|EpistemicInterval|EpistemicSet|Unknown,
│   │   │                     #   Distribution, CorrelationGroup, EpistemicCollapse
│   │   ├── knowledge.py      #   Source, DataArtifact, Referent, Assumption, Model(Version),
│   │   │                     #   SystemTopology, EngineBuild
│   │   ├── faults.py         #   FaultMode, FaultActivation, CommonCauseFactor, PredicateAST
│   │   ├── design.py         #   ScenarioTemplate, UncertaintySpec, FaultCampaign, MetricSpec,
│   │   │                     #   AcceptanceCriterion, ComparisonSpec, SamplingPlan, ExperimentDesign
│   │   ├── execution.py      #   RunSpec, RunResult, MetricValue, AggregateResult, Verdict, records
│   │   ├── evidence.py       #   EvidencePackage + four registers (§13)
│   │   └── versioning.py     #   schema_version registry + on-read migrations
│   ├── units/                # boundary converters (astropy-backed), adapter conversion tables
│   ├── hashing/              # JCS canonicalizer, canonical array bytes, content addressing
│   ├── registry/             # object store (SQLite: objects/aliases/edges), kernel cache, audit log
│   ├── engines/
│   │   ├── base.py           # protocols, capability flags        ├── worker.py  # subprocess harness
│   │   ├── spice/            # geometry service                    ├── basilisk/  # adapter
│   │   ├── linkchain/        # FarSight-native link-budget engine  └── gmat/      # post-MVP
│   ├── faults/               # DSL → InterventionSchedule compiler; per-engine lowering
│   ├── uncertainty/          # outer-scan/inner-sample planner, sensitivity decomposition
│   ├── experiments/          # planner.py (pure), seeding.py, runner.py (pool), ledger.py
│   ├── metrics/              # versioned pure functions; compensated summation
│   ├── comparison/           # matched-config declarations, epoch-based diffing, tiers
│   ├── evidence/             # package builder, verifier, replayer — never imports engines
│   ├── cli/                  # typer: plan/run/resume/replay/verify/show/diff/fetch
│   └── analysis/             # quarantined: pandas/matplotlib allowed HERE ONLY
├── tests/{unit, engine_contract, golden}/
└── experiments/              # versioned experiment definitions (dsn_rf_benchmark/, dsoc_link/)
```

**Boundary rules, enforced by import-linter in CI from the first commit:** `schemas` imports nothing internal; `evidence`/`hashing` never import `engines` (**`farsight verify` must run on an auditor's laptop with zero engine extras installed**); `experiments` knows adapters only via `engines.base` protocols; `faults`/`uncertainty` are pure compilers that never touch engines; nothing in the truth loop imports `analysis`; no LLM SDK anywhere. The contract-test suite runs identical tests against a `FakeEngine`, the link chain, and Basilisk — this is what keeps "engine-neutral" honest.

## 7. Data/schema design

- **Pydantic v2 is the source of truth**; `model_config = ConfigDict(extra="forbid", frozen=True)` on everything hashed. JSON Schema exports ship inside every evidence package so third parties validate without Python.
- **Canonical serialization:** RFC 8785 (JCS) profile — UTF-8, sorted keys, no insignificant whitespace. **All physical quantities in hashed specs are decimal strings + unit**, never JSON floats (sidesteps float-canonicalization ambiguity); NaN/Infinity are forbidden by validator — unknowns are represented structurally as `Unknown` beliefs, never as NaN (which conveniently serves the honesty feature). Binary channel arrays are hashed as canonical little-endian IEEE-754 float64 bytes with a (name, unit, dtype, shape) header.
- **Bulk run output:** one `.npy` per channel per run (canonical LE float64, C-order), written to temp + fsync + atomic rename. Trivially specified, byte-stable, readable with one line of NumPy, and hashing the file is hashing the numbers. Parquet reconsidered at scale phase — not before. (Drops pyarrow from the MVP trust surface.)
- **Two-layer identity:** `spec_hash` (RunSpec canonical JSON) and `output_hash` (Merkle root over channel hashes + metrics doc). `experiment_hash` includes planner version + root seed + generation rules, so `(experiment_hash, run_index) → spec_hash` is a pure derivation. Timestamps live in an unhashed provenance block — otherwise nothing is ever reproducible by construction.
- **Versioning/migration:** every persisted document embeds `schema_version`; migrations are pure `v_n → v_{n+1}` functions applied **on read only**; evidence packages are never migrated in place — verifiers keep old-version readers, contract-tested against archived fixtures. Hashes are over bytes-as-written, so old packages verify forever.
- **Provenance metadata is mandatory at freeze:** every `ParameterBelief` carries a `pedigree` block (level ∈ measured_flight | measured_ground_test | published_design | derived_analysis | expert_judgment | speculative; sources; assessor; date) and a `validity_envelope` (conditions, ranges, time span). Runs exiting an envelope set validity flags and land in the violation register — extrapolation happens, never silently.

## 8. Units and numerical conventions

- **Boundary-typed, raw-core:** every schema field carries declarative unit metadata (astropy-backed `Annotated` types); validators accept `Quantity` or `(value, unit)` and normalize at construction. Inside `engines/`, `metrics/`, and numeric kernels: **raw SI float64 + numpy only** — astropy/Pint Quantity costs 20–100× per scalar op (fatal at 10k-run scale) and every engine boundary takes raw floats in engine-native units anyway. Each adapter owns an explicit, tested conversion table ("Basilisk task rates are ns; GMAT field X is km/s"). Channel metadata carries unit strings so analysis re-hydrates quantities for humans.
- **Tolerances:** every comparison declares absolute + relative tolerance with a one-line rationale comment; convergence-order assertions (halve the step → error drops ~2^p) are preferred over single-point tolerances where applicable.
- **Reductions:** all aggregation over runs iterates in sorted `run_index` order with compensated (Kahan/Neumaier/`math.fsum`) summation — FarSight's own code must not be the reproducibility weak link.
- **Environment pins in every worker:** `OMP_NUM_THREADS=1`, single-threaded BLAS, no `-ffast-math` in anything FarSight builds, locale/TZ pinned; CPU model + ISA flags recorded.

## 9. Uncertainty model

**Core type — a Pydantic discriminated union (`Belief`):**

```
Deterministic(value)  |  Aleatory(distribution, sampling_scope)
EpistemicInterval(interval, rationale)  |  EpistemicSet(members: values or ModelVersion refs)
Unknown(bounding_assumption_ref and/or sweep_declaration — required at freeze)
```

Rules that make it honest, enforced in the type system:
- `sample(rng)` exists only on `Aleatory`/`Deterministic`. Epistemic kinds expose only `enumerate_outer(plan)`. **There is no `.to_distribution()` on epistemic types.** `Unknown` cannot be sampled at all.
- Distribution hyperparameters may themselves be epistemic (`Aleatory(rayleigh, sigma=EpistemicInterval(...))` — the flagship pattern: DSOC pointing jitter is lab-measured 0.16 µrad but flight-published only as "sub-microradian").
- **Propagation = two loops:** outer deterministic scan over the epistemic space (LHS + interval vertices + model-family enumeration; no RNG), inner seeded aleatory MC per outer point. A run is addressed by (epistemic point, aleatory draw index). Results are a family of CDFs whose envelope is an **empirical p-box** — p-boxes appear as an *output summary*, without p-box input arithmetic (which is a research project and commercially unadopted). Sampling epistemic unknowns into one blended distribution and reporting a percentile would be *laundering ignorance into probability* — structurally impossible here.
- **`EpistemicCollapse`:** the legitimate epistemic→probabilistic conversion is a first-class, content-addressed, human-authorized record (original belief, chosen distribution, justification, authorizer, scope). Downstream results inherit `contains_epistemic_collapse: true`; the evidence package's judgment register lists every collapse verbatim. **Escape valve:** `evidence_grade: exploratory` experiments may auto-collapse intervals for sensitivity screening only — their outputs are tainted and cannot feed an evidence-grade verdict. (An honesty system that makes daily engineering painful gets forked around; the exploratory lane keeps the evidence lane pure.)
- **Dependence:** aleatory — named `CorrelationGroup` (Gaussian copula + PSD-validated rank matrix; only Gaussian in MVP). Epistemic/common-cause — **shared latent variables**, the same mechanism the fault model uses.
- **Presentation (commercial survival):** the answer to "just give me the probability" is *margin-first*: "here is your margin against the requirement, here is the guaranteed bound, and here — one click down — is which unknown is eating your margin and what measurement buys it back." One number + ritualized qualifier is how GUM and NASA PRA succeeded; interval-only-refusal is how the p-box literature stayed academic. This is a presentation-layer choice, never a type-system weakening.

## 10. Fault model

Three-way split mirroring FMECA practice:
- **`FaultMode`** (knowledge plane, reusable catalog): target = abstract `SystemTopology` path + aspect (parameter | output | function); effect ∈ bias | scale | stuck_at | zero_output | dropout | noise_inflation | latency | intermittent | ramp_degradation | custom(content-hashed plugin); magnitude as a *declared parameter*; detection observables; recovery (none | self_clearing | autonomous | ground_intervention(delay: Belief)); optional FMECA severity/likelihood; mandatory pedigree.
- **`FaultActivation`** (design plane): trigger ∈ at_time | after_elapsed | on_condition(restricted predicate AST — comparisons, and/or/not, `for_duration` hysteresis; **never embedded Python**) | stochastic_hazard(rate: Belief); magnitude/duration as Beliefs.
- **`FaultActivationRecord`** (execution plane): what actually fired with drawn times/magnitudes — this is what makes deterministic replay of stochastic fault campaigns possible.

**The unifying move: every stochastic fault quantity is a `Belief`.** A fault's occurrence draw is aleatory (seeded); its rate or severity may be epistemic. "We do not know this component's degradation rate" is expressible and non-collapsible in fault space too — no second uncertainty system exists.

**Common cause:** `CommonCauseFactor` = a shared latent variable (aleatory occurrence/severity for environmental events; *epistemic existence* for design defects — "the firmware defect is in both transceivers or in neither, enumerated, never weighted") with declared couplings modulating hazard/magnitude/duration of multiple activations. Activations are conditionally independent *given* the factors. MVP: one-layer graph (factors → faults). Beta-factor PRA models are expressible as a special case — worth documenting for PRA-literate customers.

**Engine binding:** faults target topology paths, never engine internals; adapters supply `FaultBindingImpl` (mechanism ∈ attribute_mutation | task_disable | message_intercept | parameter_override | native_model_hook | unsupported). A campaign referencing a fault with no binding for its routed engine **fails at freeze** — never a silent skip. Boundary definition to prevent taxonomy rot: a fault is a deviation of *system* behavior from design intent; environmental extremes are scenario/uncertainty inputs (but an environmental factor may couple *into* faults).

## 11. Experiment/run architecture

- **Planner** (`ExperimentSpec → list[RunSpec]`): pure and deterministic; all randomness pre-planned — every sampled value is derived and written into RunSpecs before dispatch; the pool never draws.
- **Seeding:** 128-bit root seed per experiment → `np.random.SeedSequence(root, spawn_key=(run_index, stream_id))` — direct spawn-key construction (O(1) addressing, no predecessor generation), Philox generator (cross-version stream stability per NumPy's policy). Named streams: `aleatory_draws`, `engine_module_seeds` (→ sorted Basilisk module names → `RNGSeed` ints), `sampler_internal`. Derived values archived in each RunSpec — replay never depends on NumPy's derivation still existing.
- **Execution:** `ProcessPoolExecutor`, spawn context (Windows-required; avoids fork/CSPICE hazards), default `physical_cores − 1` workers. Worker: verify input hashes → set env policy → run → write `.npy` to temp → atomic rename → return a small result record. No engine state crosses the pool boundary.
- **Ledger:** SQLite (WAL): `(experiment_hash, run_index, spec_hash, status ∈ pending|running|ok|failed|diverged|crashed, output_hash, wall_time, worker_env_hash)` + append-only JSONL manifest (the gmat-sweep pattern, adopted platform-wide; the JSONL ships in the evidence package). Runs are idempotent: `resume` re-plans, skips verified-`ok` rows, re-executes the rest.
- **Cancellation:** cooperative; in-flight runs finish (bounded by per-run timeout), rest marked pending. **Partial results are first-class**: packages built from partial experiments are stamped `partial: true` with the completed set enumerated — never silently presented as complete.
- **Scale check:** 10k runs ≈ minutes for link-chain-class runs, overnight worst case for Basilisk-class. `ProcessPoolExecutor` + SQLite is deliberately boring; the runner interface is the seam where a distributed backend plugs in later. The target is restated honestly: **"10,000 seeded runs of a named campaign with full evidence manifest and bitwise replay of any single run"** — the differentiator is the last clause, not the count.

## 12. Reproducibility specification

Three tiers, stamped per claim into the evidence package:
- **Tier A — replay identity:** same container image digest (or identical pinned env), same CPU ISA feature set, threads=1, same engine versions ⇒ **bitwise-equal output hashes**, machine-verified by `farsight evidence replay`. Claimed for SPICE geometry, the link chain, FarSight metrics, single Basilisk runs. The pinned Linux CI container is the canonical Tier-A platform (dev on Windows is fine; golden hashes are per-platform from day one).
- **Tier B — portability envelope:** across OS/CPU/compiler ⇒ per-metric stated tolerances at **defined comparison epochs** (never end-of-chaotic-horizon), accounting for FMA/libm/reduction-order divergence. Verified by a cross-platform CI matrix.
- **Tier C — cross-engine agreement:** matched-configuration declaration + physically motivated per-channel tolerances; never bitwise; unmatched configuration elements enumerated in the package.

Determinism rules: no hashed value may depend on completion order, wall clock, dict/`os.listdir` iteration order, PID, or hostname; ordered compensated reductions; single-threaded workers. **The runner's most important regression test: a 100-run experiment at `--workers 1` and `--workers 8` must produce identical evidence root hashes.**

Terminology note (auditors will pounce): say **"content-addressed, independently re-executable"** — not "cryptographically traceable" — until a signing story exists. Hashes prove integrity relative to a hash someone independently holds; identity and timestamping come later (minisign seam is in place, §13).

## 13. Evidence/provenance model

Package layout (directory or zip, named by root-hash prefix):

```
evidence_pkg_<root8>/
  manifest.json                # root document: schema version, package id (= root hash),
                               # tool + commit, tier claims per run set, and THE CLAIM STATEMENT —
                               # the exact falsifiable sentence this package supports
  experiment/  experiment_spec.json, matched_config.json,
               unknowns_ledger.json          # every flagged unknown: why, interval, source, "NOT FITTED"
  runs/        runspec_<i>.json, seeds_<i>.json, status_<i>.json, channels/<i>/<name>.npy
  campaign.json                # master seed, sampling design (outer grid + inner dists), JSONL ledger
  inputs/      kernels.manifest.json (metakernel text + per-kernel SHA-256/size/source URL/modified flag),
               reference_data/  # frozen Referent datasets, each with citation + hash
  environment/ fingerprint.json # container digest, CPU+ISA, OS, python, engine versions, thread env
  metrics/     metric_registry.json, metric_results.json, acceptance_results.json,
               sensitivity.json (which epistemic terms dominate), failure_groups.json
  report/      summary.md      # GENERATED from the JSON; "if prose and JSON disagree, JSON is the record"
  hashes/      file_hashes.json, root_hash.txt, root_hash.txt.minisig (optional)
```

Four mandatory registers: **Assumption register, Unknown register, Epistemic-collapse (judgment) register, Validity-violation register.** Plus license/attribution notices (NAIF/ISC/Apache obligations ride along automatically).

Audit path (CLI only, no web UI): `farsight evidence verify` (recompute all hashes, validate schemas, recompute metrics from raw channels; nonzero exit naming the item on any discrepancy) → `show` (read the claim and unknowns ledger *first*) → `replay --runs … --tier A|B` (re-execute **from package content only** — a clean checkout is explicitly not allowed) → independently recompute one metric from a `.npy` in a plain Python session → check one referent point against its cited public source. Target: a competent outsider completes this in ≤2 hours.

**Metrics and rules:** a metric is a versioned pure function (no I/O, clock, RNG, thresholds, engine access); identity = canonical hash of its declarative definition, with implementation source hash recorded alongside; CI enforces "implementation changed ⇒ version bumped." Acceptance criteria are separate versioned rule objects referencing `metric_id@version` + comparator + threshold + tier + rationale — thresholds live *only* there. **Root-cause grouping is deliberately dumb:** failure signature = ordered tuple (violated rule ids, active faults at first violation, epistemic bin); grouping is exact signature match — reproducible, auditable, explainable. Clustering/ML grouping is out of MVP scope: it would be the first thing an auditor couldn't reproduce.

## 14. Verification & validation strategy

Pyramid (cheapest at bottom, every commit; expensive layers nightly/weekly):
1. **Unit tests** — every function touching a physical quantity or hash is pure and tested; <30 s tier; Windows + Linux CI both.
2. **Dimensional tests** — wrong-dimension inputs rejected at every boundary; mixed-unit smoke test vs hand-computed SI.
3. **Analytical anchors** (the only tests with machine-precision truth): two-body vs SPICE `prop2b` (RKF78 @1e-12: <1 m over 10 orbits; fixed-step RK4: assert the convergence *order*, stronger than any point tolerance); energy/momentum conservation (<1e-9 drift); Hohmann Δv through burn plumbing (post-Basilisk); **optical link budget vs a hand-written worked example checked into docs, computed independently by a second person** + limiting-case identities (double the range → exactly −6.0206 dB); battery ODE closed forms (linear discharge, RC transient, eclipse square-wave); **SPICE-vs-Astropy station elevation cross-check (<0.01°)** — frame/time-system errors are the domain's most common silent killers and only an independent implementation catches them.
4. **Property-based (Hypothesis):** unit round-trips to 1 ULP; canonical-hash invariance to key order/process boundary (NaN payloads, −0.0, ±inf, denormals pinned); seed derivation collision-free and enumeration-order-independent; metric invariance to channel chunking; declared monotonicities (link margin strictly decreases with range).
5. **Golden cases** — hard rule: **a golden number may never originate from our own code** (admissible: archived Horizons responses, cited papers, the hand-calc notebook, a second library). Psyche range on DSOC milestone dates vs Horizons (<10 km, actual delta logged); frozen cited datasets for the DSOC points and SNSPD parameters, hash-pinned.
6. **Regression pinning** — Tier A bitwise in the pinned container; Tier B with per-channel rationale-commented tolerances. **Re-golding requires an `EXPECTED-CHANGE` note with the physical/numerical reason, second-dev reviewed; CI fails on silent golden changes.**
7. **Cross-engine methodology** (ships in MVP as method + schema; GMAT execution post-MVP): matched-configuration declaration is a schema object (GM values set numerically identical — never trust engine defaults; declared *unmatched* items); comparison at defined epochs; **Richardson-style discrimination** (run both engines at τ and τ/100 — delta shrinks ⇒ integration error; doesn't ⇒ model mismatch, must map to a declared unmatched item or it's a defect); itemized legitimate divergence sources with expected magnitudes.
8. **Deterministic replay tests** — nightly: replay 5 random runs *from the evidence package alone*; weekly on the second machine (Tier B).
9. **Mutation tests for the injector and the harness:** zero-magnitude fault ⇒ bitwise identical to baseline (proves injection plumbing doesn't perturb state); directional sensitivity per fault type; declared common-cause correlation appears in outputs; **corrupt one byte of any package file ⇒ verification refuses loudly and names the item** — if verification passes on mutated evidence, we built theater.

**Trust preconditions (all must hold before any FarSight result is trusted):** analytical anchors green on the exact versions in use; RunSpec hash re-canonicalizes; every input matches its manifest hash; environment fingerprint matches a declared tier; every draw traces to the master seed (no naked RNG — lint-enforced); metrics recompute from raw channels; every `unknown` appears in the ledger with no point value anywhere (schema-enforced); cross-implementation checks within declared envelopes; claim semantics written in the package; `verify` exits zero with no warnings. Any failure ⇒ the result is untrusted, full stop.

## 15. Dependency/licensing assessment (verified 2026-08-26)

| Dependency | License | Verdict | Conditions |
|---|---|---|---|
| CSPICE | Custom NASA/Caltech public release (not OSI) | OK-with-conditions | Embedding in a product allowed; **mirroring the standalone toolkit requires written NAIF clearance**; acknowledgement encouraged |
| SpiceyPy | MIT (wheel bundles CSPICE) | OK | Notice retention; NAIF terms flow through the embedded CSPICE |
| SPICE kernels | NAIF rules (US gov data) | OK | Unmodified redistribution free; **modified kernels must be re-attributed to the modifier** (aligns with our provenance feature) |
| Basilisk | ISC (CU Boulder) | OK | Notice retention; pip `bsk` wheels; Py ≥3.9 <3.15; Windows supported |
| GMAT | Apache 2.0 (since R2016a) | OK / conditions | Orchestrating a user-installed GMAT: OK. Redistributing GMAT binaries: audit bundled third-party notices first (unverified inventory) — our adapter design avoids this entirely |
| TudatPy | BSD-3 (TU Delft) | OK (legal) | Conda-only distribution is the practical constraint; later phase |
| Astropy | BSD-3 | OK | Notice retention |
| F Prime | Apache 2.0 (Caltech) | OK-with-conditions | Confirm Caltech "ALL RIGHTS RESERVED" boilerplate interplay during legal review |

**Items requiring legal confirmation:** (1) FarSight's own export classification once proprietary/non-published — **US EAR ECCN 9D515 vs EAR99** (2024 space-controls rulemaking expanded 9D515; a non-published commercial product loses the open-source "published" carve-out); (2) EU dual-use Regulation 2021/821 Annex I Cat 9 for EU distribution; (3) handling customer export-controlled mission data in on-prem deployments; (4) NAIF written clearance if an offline installer ever ships standalone CSPICE; (5) GMAT third-party inventory if binaries are ever bundled; (6) F Prime notice. **Strategic implication (red-team, serious):** the sovereign-EU wedge may be self-undermining if FarSight lands under 9D515 — a US-license-controlled "sovereignty tool" is a contradiction a buyer discovers mid-procurement. Counsel engagement (~$3–5k) starts week 1 in parallel, not post-MVP (gate K7, §21).

## 16. Security/deployment considerations

**Bake in now (days now, months of retrofit later):**
1. **Offline-first / no-network in the truth loop** — runner and verifier make zero network calls, ever; acquisition is an explicit `farsight fetch` recording URL+hash; CI runs the suite with sockets disabled.
2. **Hash-tree + signing seam** — the manifest/Merkle structure ships in MVP; `SignatureBlock` is a defined interface with a no-op backend (minisign optional). Changing the evidence *identity scheme* after customers hold packages is near-impossible; adding a signer to a stable hash tree is trivial.
3. **No telemetry, structurally** — no phone-home code path exists (absent, not defaulted-off), documented as such.
4. **Append-only audit log + data/config separation** — hash-chained SQLite audit rows for every CLI mutation from v0; mission data only under user-designated roots; paths not contents in logs; customer inputs listed by hash + declared label only (customer data may itself be ITAR/EAR technical data — never smear it into logs, temp dirs, or crash dumps).

**Explicitly deferred:** RBAC/auth (single-operator CLI), encryption at rest (customer disk controls), FIPS modules, container tooling beyond a reference Dockerfile + digest recording, PostgreSQL, any web UI.

## 17. 8-week MVP

Assumes 3 devs; Claude Code leverage ~2× on schemas/CLI/tests/scaffolding, ~1× on physics and tolerance decisions — a human owns every golden number and every tolerance rationale.

**Weeks 1–2 — Foundations.** Repo + CI (Windows + Linux + pinned container); schema pack (`common`, `belief`, `knowledge`, `execution` core); JCS canonicalizer + hashing with the Hypothesis suite; units boundary layer; seed derivation; SPICE geometry service (KernelPool-scoped, per-worker furnishing); content-addressed kernel cache; Psyche + station kernels from NAIF PDS4; golden geometry vs Horizons; SPICE-vs-Astropy cross-check. *Timeboxed 2-day spikes:* (a) `pip install bsk` → seeded scenario → mid-run mutation → hash-compare twice; (b) GMAT R2025a subprocess round-trip (information-gathering only). *Parallel:* K2 envelope hand-calc spreadsheet; mock evidence package → 5 discovery calls; counsel engaged (K7). **Exit gate:** `farsight geometry` emits hash-stable Psyche pass geometry, bitwise-reproducible in container.

**Weeks 3–4 — First pipeline.** Link-chain engine (pure Python/SI): Tx (4 W, 22 cm, 1550 nm), free-space, Rx (5.1 m Hale), SNSPD efficiency + blocking model from the open-access detector paper, background/dark terms, CCSDS 142.0-B-1 SCPPM rate ladder → supportable-rate function; closed-form tests + hand-calc notebook. Belief tagging of every parameter (the DSOC unknowns enter as epistemic intervals with citations). **DSN RF anchor benchmark** (810-005 + DESCANSO spacecraft, shared geometry pipeline, ±1 dB class). Single-run evidence package v0 + `verify`/`show`. **Exit gate:** DSN comparison decided at published tolerances; DSOC envelope vs frozen public points in a verifiable package.

**Weeks 5–6 — Campaign machinery + faults + minimal Basilisk.** MC runner (pool, JSONL ledger, resume, order-independence proof); 10k-run campaign as outer epistemic grid × inner aleatory samples; sensitivity decomposition (variance-based on aleatory + interval-width contribution on epistemic → "which unknowns dominate" table); fault framework + 3 link-chain fault types (pointing degradation, dark-rate spike, weather common-cause across consecutive passes) + mutation suite; failure-signature grouping; campaign evidence v1 + `replay`/`diff`; **minimal Basilisk adapter** (two-body vs `prop2b` golden + one mid-run fault + RNGSeed map — ~1 dev-week scope). **Exit gate:** 10k-run campaign overnight, resumable after hard kill, replay-verified.

**Weeks 7–8 — DSOC hardening + external demo.** All dated points + aggregate envelope; claim semantics locked; **pre-registration** (publish hashed predictions, then buy the SPIE/JSTQE papers and score); **falsifiability counterfactual** (deliberately wrong aperture ⇒ points fall outside the envelope — proves the test can fail); second-machine Tier-B replay; report renderer; **external cold audit** by an aerospace engineer not on the team (their friction list = week-8 punch list); writeup with the honest precision statement (±2–3 dB, one rate step — we do not claim 20%). **Exit gate:** all acceptance tests green; demo runs from the CLI only.

**Parallel commercial track (weeks 1–6):** mock package in 5 calls (week 1); ≥8 interviews with V&V/mission-assurance engineers asking exactly two questions ("what does producing the equivalent cost you today?", "who in your org would be forced to accept or reject this artifact?"); engineer-hours ledger of what the evidence pipeline cost to build; week-6 gate K5.

**Scope-cut order if behind:** (1) minimal Basilisk → post-MVP (engine-independence criterion downgraded *and stated honestly*); (2) Sobol → one-at-a-time + interval sweep; (3) `evidence diff`; (4) minisign; (5) fault types 3→2 (keep the common-cause one); (6) report polish. **Never cut:** canonical hashing, unknowns ledger, replay verification, the counterfactual test, the DSN anchor, the 10k-run target (cheap for the link engine; inability to hit it is information we need).

## 18. Acceptance tests for the MVP

- **AT-1** Cross-machine replay of the DSOC package from package content only → Tier-B tolerances; any outside-package fetch = fail.
- **AT-2** Same-container replay of ≥5 runs → bitwise-equal channel hashes (Tier A).
- **AT-3** Tamper: flip 1 byte in any channel/kernel/registry file, one seed, one metric version → `verify` exits nonzero naming the exact item.
- **AT-4** 10k-run campaign ≤12 h on the reference workstation; `kill -9` at ~50% + resume → channel and metric hashes identical to an uninterrupted campaign.
- **AT-5** All frozen DSOC points satisfy "achieved ≤ predicted supportable envelope" within 1 rate-ladder step of its lower edge; **envelope width ≤ 6 dB** (else vacuous); counterfactual with 11 cm aperture violates the envelope — if it still passes, the test tests nothing.
- **AT-6** A RunSpec assigning a point value to a flagged-`unknown` parameter is rejected by schema; the ledger lists every unknown with interval + citation; no default value for any of them exists in the codebase.
- **AT-7** Run #4242 re-executed standalone from its RunSpec + seed map → bitwise identical to its in-campaign channels.
- **AT-8** CI: metric implementation mutated without version bump → registry-consistency check fails.
- **AT-9** External engineer, given only package + CLI + README, completes the audit and independently recomputes one metric in ≤2 hours, and states in writing whether the claim semantics are honest.
- **AT-10** Zero-magnitude fault bitwise-identical to baseline; each fault moves its declared metric in the declared direction; all evidence mutations caught.
- **AT-11** SPICE vs Horizons range <10 km on all benchmark dates; SPICE vs Astropy elevation <0.01°; actual deltas logged.
- **AT-12** (If Basilisk not cut) two-body via adapter vs `prop2b` <1 m over 10 orbits (RKF78 @1e-12); mid-run fault at t=T changes post-T channels only, pre-T bitwise identical.
- **AT-13** DSN anchor: predicted Pt/N0 and supportable rate vs documented achieved DSN performance within the pre-stated ±dB tolerance — a decided pass/fail, no unknowns bucket.

## 19. Major technical risks (ranked)

1. **Cross-engine matched configuration is the 3-week sink** (gravity degree/order, DE440 vs defaults, EOP, time systems — silent mismatches give km-level divergence a non-specialist can't diagnose). Mitigated: GMAT post-MVP; when it lands, one deliberately trivial matched case (two-body + J2, 30-day arc, pre-stated <10 m at epochs) as the existence proof — not a physics-matching campaign.
2. **Missing-term risk in the link budget** — an omitted term is a silently-fitted zero, the exact sin the product prevents; the first credibility hit will be a domain reviewer finding one. Mitigation: **pay an optical-comms expert ~2 hours in week 2 (parameter table review) and week 7 (final package)** — the highest-ROI spend in the plan (~$1–2k).
3. **Epistemic treatment is the flagship's actual load-bearing wall** — DSOC's dominant uncertainties are almost all epistemic; the aleatory machinery is barely exercised. The two-loop design must land in weeks 3–4, not be retrofitted.
4. **Canonicalization edge cases** (float strings, unicode, cross-language) — property-test the canonicalizer in week 1; fall back to deterministic CBOR if JSON proves fragile (architecture unchanged).
5. **Windows-dev / Linux-container skew** — per-platform golden hashes from day one; the container defines Tier A.
6. **Authoring ergonomics of tagged-union YAML** — mitigate with schema-validated templates; never by weakening types.
7. **GMAT API brittleness** (post-MVP, but the week-1 spike prices it) — copy the gmat-sweep subprocess pattern wholesale.

## 20. Open questions

1. Which named buyer class has an assurance obligation documents alone no longer satisfy (autonomy certification? EU sovereign programs? underwriting?) — answered by the discovery track, not engineering.
2. Company/entity jurisdiction for the export posture (US vs EU origin changes the 9D515 calculus) — blocked on counsel (K7).
3. Whether to purchase and incorporate the paywalled per-pass data pre- or post-week-7 (pre-registration protocol says: predict first, buy second — the buy date is the open item).
4. Basilisk version pin (must be ≥ the post-construction RNGSeed fix; verify current release notes at implementation time).
5. Whether `EpistemicSet` members need weights *ever* (current stance: enumerated, never weighted — revisit only on customer evidence).
6. Reference workstation spec for the ≤12 h AT-4 bound.
7. Name collision check on "FarSight" (trademark search) — flagged for the commercial track.

## 21. Kill criteria (dated gates + standing kills; do not rationalize)

**Dated gates:**
- **K1 (end wk 1):** seeded Basilisk scenario reruns bitwise-identically within 3 dev-days of spike start. Fail → descope Basilisk from MVP demo.
- **K2 (end wk 2):** hand-computed DSOC epistemic envelope at 3 epochs. **>12 dB at 2.6 AU using all free published constraints → DSOC demoted to secondary; DSN becomes flagship.**
- **K3 (end wk 3, HARD GATE):** full pipeline rerun in same container yields bitwise-identical evidence root hash, twice, including once after reboot. Fail → all feature work stops until fixed; reproducibility *is* the product.
- **K4 (post-MVP, when GMAT lands):** Basilisk-vs-GMAT two-body+J2 30-day arc within pre-stated tolerance after ≤1 dev-week of matching. Fail → cut cross-engine from the roadmap honestly.
- **K5 (end wk 6):** ≥8 discovery interviews done; **≥2 interviewees name a budgeted, current cost the evidence package displaces.** Fail → thesis unproven; pivot decision (tool-plus-consulting) before demo polish.
- **K6 (end wk 8):** the published DSOC package contains ≥1 dominant unknown with quantified sensitivity AND the pre-registered claim scored against per-pass data. "Everything inside a huge envelope, nothing learned" = the demo failed as evidence of value even if technically complete.
- **K7 (by wk 6, parallel):** preliminary export read from counsel. Likely 9D515-with-license-to-EU → restructure the sovereign-EU go-to-market **before** pitching it as the wedge.

**Standing kills:**
- **The 200-line-notebook test:** post-demo, an external engineer given the same public inputs and 2 days produces an equivalent comparison in ≤200 lines *and*, shown both, sees no additional value they'd pay for in replay/tamper-evidence/unknowns-ledger/decomposition → **kill the evidence-platform thesis** (the notebook will always exist; the product is only real if the auditability delta is worth money to a named buyer).
- **Unfalsifiable-envelope kill:** honest DSOC envelope >6 dB → fall back to DSN; if DSN *also* can't produce a decided pass/fail → "falsification as a product" is dead.
- **Reproducibility kill:** Tier-A bitwise replay unachievable for the pure-Python engine within 2 calendar weeks of first attempt → stop feature work or kill.
- **Throughput kill:** 10k link-chain runs can't finish overnight after one optimization pass → rescope the quantitative promise before any external demo.
- **Adapter-cost kill:** the *minimal* Basilisk adapter exceeds 2 dev-weeks → the "orchestrate existing engines" cost model is wrong by >2×; re-evaluate the multi-engine premise deliberately (fallback: single-engine + evidence packaging is a different, smaller company).
- **Tolerance-inflation kill (dishonesty tripwire):** tolerances loosened after seeing a failing result without documented physical rationale, second-dev reviewed. Allowed count: **zero.** Recurrence → the team cannot be trusted with the honesty pitch, and the honesty pitch is the company.
- **Commercial kill:** 8 weeks post-demo, no aerospace org has committed a concrete next step (funded pilot, LOI, or a named engineer ≥1 day/week). One retry (DSN-anchored pitch), then kill or pivot to services.
- **Audit-usability kill:** two consecutive external auditors fail the ≤2 h audit or say the evidence didn't increase their trust → the package is compliance theater; fix or kill the format.
- The founder's original list (thin-UI-around-Basilisk, unobtainable uncertainty inputs, per-customer bespoke modeling, integration cost > orchestration value) remains in force; K1–K7 are their measurable instantiations.

## 22. ADRs to write before implementation

- **ADR-001** Content-addressed identity + freeze protocol (JCS profile, decimal-string quantities, draft/frozen lifecycle)
- **ADR-002** Process-isolated worker as universal execution unit
- **ADR-003** Two-level adapter contract + capability flags + fault-lowering refusal
- **ADR-004** Belief tagged union + two-loop propagation + EpistemicCollapse (evidence vs exploratory lanes)
- **ADR-005** Seeding scheme (SeedSequence spawn-keys, Philox, archived derived values)
- **ADR-006** Reproducibility tiers A/B/C + determinism rules
- **ADR-007** Evidence package format + four registers + claim statement
- **ADR-008** Units at boundaries, SI float64 core, adapter conversion tables
- **ADR-009** Metric/rule separation + versioning + deterministic failure signatures
- **ADR-010** FaultMode/Activation/Record split + latent-factor common cause
- **ADR-011** Storage: files + `.npy` channels + SQLite ledger only (no DB roadmap)
- **ADR-012** Offline-first, no-telemetry, signing seam, audit log

## 23. Recommended first implementation task

**Week-1 vertical slice, three parallel timeboxed items:**
1. **Main code deliverable:** `farsight.schemas.common` + `farsight.schemas.belief` + the JCS canonicalizer/hashing module, with the full Hypothesis property suite (hash invariance, quantity round-trips, discriminated-union serialization, NaN/−0.0/Inf rejection) and the import-linter boundary config. This is ADR-001/-004 made real, and everything else sits on it.
2. **K2 gate (no code):** the DSOC envelope hand-calc spreadsheet at 3 epochs — decides the flagship before heavy investment.
3. **Engine spikes (2 days each, information-gathering):** Basilisk seeded-rerun bitwise check (K1); GMAT subprocess round-trip.

Plus, non-engineering: mock evidence package for discovery calls; counsel engaged (K7).

---

## Things we must get right before writing significant code

1. **Content-addressed identity and the canonicalization rules** — every product claim (replay, tamper-evidence, provenance) rests on hash stability; retrofitting identity is impossible.
2. **The Belief type system with no epistemic→probability path except an authorized, registered collapse** — this is the scientific-honesty feature as code, not documentation.
3. **Two-loop uncertainty propagation (outer epistemic, inner aleatory)** — a flat Monte Carlo over mixed unknowns would launder ignorance into probability in the flagship's very first result.
4. **The Referent as a first-class entity with claim semantics written into the package** — "achieved ≤ supportable envelope" vs naive equality is the difference between falsification and theater.
5. **Process isolation + capability flags + refusal-over-approximation in the adapter layer** — forced by GMAT/CSPICE ground truth; also what keeps engine independence honest.
6. **Seed discipline: all randomness pre-planned, O(1) addressable, archived** — deterministic replay of run #4242 is the demo *and* the debugging story.
7. **Evidence verifiable with zero engines installed** — the auditor-laptop boundary (`evidence`/`hashing` never import `engines`) is the most commercially important import rule in the codebase.
8. **No universal physics ontology** — standardize the run protocol and evidence format; the moment a shared schema grows a `mass` field, we are building the thing that killed every predecessor.
9. **Metric/threshold separation and the no-silent-re-golding rule** — hidden thresholds and quietly loosened tolerances are the two ways scientific codebases rot; both are mechanically prevented, not policed.
10. **The order of proof: pipeline honesty on DSN (±1 dB, no unknowns) before DSOC (honest envelope), with pre-registration** — sequencing is what makes the demo evidence rather than a demo.

**Recommendation for what to implement first:** item 1 of §23 — the schema/canonicalization/hashing core with its property suite — started in parallel with the K2 envelope spreadsheet and the two 2-day engine spikes. Nothing else in the system can be built honestly until object identity is stable, and the K2 spreadsheet decides the flagship before any heavy code is written. Awaiting review before implementation.
