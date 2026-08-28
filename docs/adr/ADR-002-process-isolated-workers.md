# ADR-002 — Process-isolated workers as the universal execution unit
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §5, §8, §11, §12, decision D2
**Related ADRs:** ADR-003 (declares the `isolation` and `reusable_worker` flags this ADR consumes; its References are the canonical restatement of engine facts), ADR-005 (all randomness is pre-planned, which is why the worker needs no RNG), ADR-006 (Tier A bitwise replay is only meaningful if the execution unit is uniform; it owns the worker-count invariance job), ADR-011 (the worker writes `.npy` channels and one ledger row, nothing else), ADR-001 (the worker re-verifies `spec_hash` before computing anything), ADR-012 (the worker makes zero network calls), ADR-018 (what a run is composed of — geometry provider plus engine stages — is decided there; this ADR decides only that all of it happens in one fresh process), ADR-019 (the pinned container is the Tier-A platform the process runs inside), ADR-023 (owns the run-outcome taxonomy this ADR writes `crashed` into)

## Context

The forcing question is what a RunSpec turns into, and whether that unit is the same for every engine.

Two of three engines answer it for us. The GMAT engine is a per-process singleton with no reliable in-process reset and is not thread-safe; community practice (gmat-sweep) is one run per fresh subprocess with file-based collection. CSPICE carries a global mutable kernel pool and is not thread-safe; one instance per process with kernels furnished per worker is the only supported shape, and Windows `spawn` requires per-worker furnishing anyway. Basilisk is the permissive one — driven from Python, mutated between segments, no mid-run checkpoint — so it *could* run in the parent, and the pure-Python link chain obviously could. (Engine facts are stated once in plan §5 and restated once in ADR-003 References; they are not re-derived here.)

The real decision is therefore not "isolate GMAT and SPICE" (forced) but "do Basilisk and the link chain get a different execution unit because they can". Say yes and three specific things break. The §12 determinism rules become engine-conditional, so the environment fingerprint means something different per engine. AT-4 (`kill -9` at 50%, resume, hashes identical to an uninterrupted campaign) stops being cheap, because a dead run now leaves residue in a live interpreter. And AT-7 (run #4242 re-executed standalone is bitwise identical to its in-campaign channels) stops being true by construction, because the in-campaign call and the standalone call are no longer the same call.

Crash containment is the other half. A segfault in CSPICE or a GMAT singleton in a bad state takes the interpreter with it. In-process that is a lost overnight campaign; out-of-process it is one ledger row with status `crashed`.

**The price, stated honestly and not yet measured.** An earlier draft of this record priced process isolation at "under 5% of wall time" and then, fifty lines later, at "a 10-30x tax on link-chain-class runs". Both cannot be the headline, and the first describes the workload that is *not* the flagship. The real shape is two workloads with two different answers, and neither cell below has been measured on our hardware:

| Run class | Per-run compute | Per-run isolation floor | Floor as a share of the run |
|---|---|---|---|
| Engine-class (Basilisk; GMAT post-MVP) | seconds to tens of seconds | process spawn, planning estimate 100-300 ms, **plus** a cold import of the engine SDK in every worker | small but unmeasured; the SDK import is the larger unknown |
| Link-chain-class (the flagship DSOC and DSN campaigns) | of order 10 ms | process spawn, planning estimate 100-300 ms, **plus** a cold re-import of pydantic, numpy, scipy and astropy on every run | dominant: the floor *is* the budget |

Three things about that table matter more than the numbers in it. First, **UNVERIFIED** — 100-300 ms is a planning estimate, not a measurement on the reference workstation, whose specification is itself an open question (§20 item 6). Second, the re-import cost is not inside the 100-300 ms at all: `max_tasks_per_child=1` under `spawn` means every run pays a cold interpreter plus the scientific stack, and that component is plausibly larger than the spawn floor it is being added to. Third, the campaign-level consequence is unpriced: at 10k link-chain runs the plan budgets "minutes" (§11), and a process overhead of a second or so per run divided across seven workers is a material fraction of that budget, not a rounding error.

This is a cost we are choosing to pay, so we have to know what it is. The measurement is twenty minutes of work and is currently scheduled nowhere; it is scheduled here, in week 1, before the runner is built.

## Decision

Every RunSpec executes in a fresh OS process. The pool is `ProcessPoolExecutor` with the `spawn` start method on **all** platforms, `max_workers = physical_cores - 1`, and — the part that is easy to get wrong — `max_tasks_per_child=1` by default, because `ProcessPoolExecutor` otherwise recycles workers across tasks and D2 would be quietly false. Nothing but bytes crosses the pool boundary: no engine object, no numpy array, no open handle returns to the parent.

```python
# farsight/engines/worker.py  (importable only by experiments.runner and cli)

def execute_run(payload: bytes) -> bytes:
    """payload = canonical JSON RunSpec; return = canonical JSON RunResultRecord."""
    _pin_environment()                      # MUST run before numpy / engine import
    spec = RunSpec.model_validate_json(payload)
    verify_spec_hash(spec, payload)         # ADR-001: re-canonicalize, compare run_id
    verify_input_artifacts(spec.inputs)     # kernels, referent files: SHA-256 per manifest
    units = resolve_run_composition(spec)   # ADR-018 decides what a run is composed OF;
                                            # this ADR decides only that all of it is in HERE
    for unit in units:                      # engine imports happen HERE, never in the parent
        unit.initialize(spec)               # ADR-003: raises UnhonorableSpec, never defaults
        for boundary in unit.segment_boundaries:
            unit.run_to(boundary)           # ADR-010's in-worker ConditionSchedule is evaluated
        unit.finalize()                     # on the declared cadence inside this loop, with no RNG
    out = collect_outputs(units)
    return write_channels_and_record(out, spec)   # temp -> fsync -> atomic rename (ADR-011)

_THREAD_ENV = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
               "NUMEXPR_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
               "TZ": "UTC", "LC_ALL": "C", "LANG": "C", "PYTHONHASHSEED": "0"}
```

The sketch deliberately does not decide how many execution units a run has. Whether a link-chain run obtains its geometry as a separate hashed input, from a SPICE call inside the adapter, or from an ordered stage list in the `RunSpec` is ADR-018's decision, and `resolve_run_composition` is the seam it lands on; whichever shape it chooses, the whole of it happens inside one fresh process, and the state-dependent fault triggers ADR-010 compiles into an in-worker `ConditionSchedule` are evaluated inside the segment loop above rather than in the parent. An earlier draft of this record loaded exactly one adapter and evaluated no schedule, which quietly contradicted both records.

`_THREAD_ENV` above is **the canonical list for the whole ADR set**. ADR-008 states the numerics rationale for pinning threads and cites this dict; it does not restate its contents, because two copies of one dict drift and `test_worker_environment_pins` needs a single source.

Four rules follow, none of them negotiable per adapter.

**`spawn` everywhere.** `fork` is forbidden even on Linux: forking a parent that has already touched CSPICE or a threaded BLAS inherits a kernel pool and thread state nobody can reason about.

**The worker sets environment policy, not the operator's shell.** The pins above are applied before the first numpy import, then read back *after* import and hashed into `worker_env_hash`, which lands on the ledger row and in `environment/fingerprint.json`. A machine with a hostile shell cannot silently emit Tier-A-labelled output.

**Crash is a status, not an exception.** Death by signal, OOM, or per-run timeout is recorded as `crashed` with the exit signal; the parent kills the process tree, marks the row, and continues. A campaign never dies because a run did. ADR-023 owns what `crashed` means downstream — whether it re-executes on resume and whether it participates in aggregation — and this ADR only guarantees that the parent survives to record it. Adapters may not create threads or processes; the worker is the only place FarSight forks.

**The escape hatch is `reusable_worker`.** An adapter may declare `EngineCapabilities.reusable_worker = True` (ADR-003), and the runner then raises `max_tasks_per_child` for that engine's pool. Exactly one adapter gets it in the MVP: the SPICE geometry service. It qualifies because its only cross-run state is the kernel pool, kernels are content-addressed and immutable, `KernelPool` gives a scoped furnish and clear, and re-furnishing a large SPK per run is the dominant cost of a geometry run. Even there the recycled worker must clear and re-furnish from hashes at each run boundary, and must pass an equality test against recycling forced off. `reusable_worker` is a claim that recycling is unobservable in the output hash, tested as such — not a performance preference.

## Options considered

### Option 1 — In-process execution with a thread pool — REJECTED
Shared address space, zero dispatch overhead, free array passing, and a debugger that works. It is what most Monte Carlo drivers do and it would make a 10k link-chain campaign genuinely fast. Dead on arrival: CSPICE and the GMAT engine are documented as not thread-safe, so two of three engines cannot use it at all, and a thread count that changes reduction order would leak into hashed results.

### Option 2 — Long-lived pooled workers with in-process reset between runs — REJECTED as default, retained as a flag
The real contender, and on the numbers above it is the one that wins the cost argument outright. It pays interpreter and scientific-stack import once per worker instead of once per run, which is precisely the component the table says is unpriced and possibly dominant; for the flagship link chain it would remove almost the entire tax this ADR spends. Rejected as the default because "reset" is a claim we cannot substantiate on two engines: GMAT has no reliable in-process reset, and Basilisk exposes no documented full state-clearing API and no checkpoint. Residual state is invisible in the output hash, so the failure mode is a run that reproduces only in the pool position it happened to occupy — the worst possible bug class for a product whose thesis is replay. It survives as the `reusable_worker` opt-in, granted only where recycling is testably unobservable, and the week-1 measurement below is what decides whether that opt-in needs to be extended to the link chain in week 5.

### Option 3 — Per-engine execution model (isolate GMAT and SPICE, run Basilisk and the link chain in-process) — REJECTED
The honest minimum: nothing forces the link chain into a subprocess, and the flagship DSOC campaign uses neither Basilisk nor GMAT, so this would make the flagship materially faster. Rejected because it makes reproducibility tier, environment fingerprint, and resume semantics engine-conditional, and because §6's contract suite runs identical tests against `FakeEngine`, the link chain, and Basilisk — that suite is what keeps "engine-neutral" honest, and it proves much less when the harness under test differs per engine.

### Option 4 — One container per run — REJECTED
Maximal isolation, and it matches Tier A exactly, since Tier A is defined by a container image digest (ADR-019). Rejected on cost and ergonomics: container start is seconds, roughly two orders of magnitude above process spawn; it requires a container runtime on every developer laptop; and Windows development becomes second-class in a plan that explicitly supports Windows dev with Linux-container Tier A. The container is the Tier-A *platform*; the process is the run unit.

## Consequences

**Buys us:** one worker harness contract-tested across `FakeEngine`, the link chain, and Basilisk; crash containment that turns an engine segfault into a ledger row; thread and locale policy that cannot be defeated by the operator's shell; a resume path with no in-memory state to reconstruct; and AT-7 essentially free, because standalone replay of run #4242 is the identical `execute_run` call the pool makes.

**Costs us:** a per-run isolation floor whose size we do not yet know and whose two components (spawn, and a cold scientific-stack re-import under `max_tasks_per_child=1`) are both unmeasured on our hardware; full serializability of RunSpec and results, so no closures, no live objects, no lazy handles; and post-mortem debugging from returned records and logs rather than a debugger on the parent. If the week-1 measurement puts the floor near a second, a 10k link-chain campaign is tens of minutes of pure overhead on a campaign the plan budgets as "minutes", and the honest response is to extend `reusable_worker` with a proof rather than to restate the estimate.

**Forecloses:** warm-started and chained runs. With no engine state crossing the pool boundary and no checkpoint API on Basilisk or GMAT, a run cannot begin from a previous run's final state — an adaptive or long-arc study must either be one longer RunSpec or re-integrate from t0, and that is a real loss. It also means any future engine with an expensive persistent context (a GPU-resident propagator, a JIT-warmed kernel) pays initialization on every single run until `reusable_worker` is extended to it with the accompanying proof.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Process isolation as the universal execution unit (one RunSpec, one fresh process, for every engine) | 0.90 | The `ci-worker-order-invariance` third leg (recycling forced off) cannot be made green by end of week 6, or the adapter-cost kill (§21) fires and the week-6 post-mortem attributes the cost to worker serialization rather than to Basilisk itself. |
| `spawn` on all platforms, `fork` forbidden even on Linux | 0.92 | A measured, reproducible case where `spawn` and `fork` produce identical output hashes across 100 runs *and* the fork path is the only way to meet the K3 week-3 timing — that is, the ban costs a hard gate rather than costing speed. |
| **The cost estimate: `max_tasks_per_child=1` is affordable at link-chain scale** | **0.60** | Fires on measurement, not on opinion: the week-1 `spawn-floor-spike` (below) records spawn plus scientific-stack import on the reference workstation. If the floor exceeds 25% of projected campaign wall time for a 10k link-chain campaign, `reusable_worker` is extended to the link chain in week 5 with the unobservability proof attached, or `max_tasks_per_child` is raised with the third CI leg as the guard. This row is the lowest number in the record because the earlier draft priced this decision three different ways, flagged its own figure UNVERIFIED, and omitted the largest component. |
| The `reusable_worker` escape hatch, granted to SPICE only | 0.72 | The SPICE recycling-off equality leg goes red once, or a second adapter requests the flag before week 6. Both mean the exemption is a performance preference rather than a tested claim, and it is withdrawn rather than widened. |
| Crash recorded as a ledger status rather than raised as an exception | 0.90 | AT-4 (`kill -9` at ~50%, resume, hashes identical) cannot be made green by end of week 6, or ADR-023 concludes that a crashed run must participate in aggregation, which would make silent continuation a scientific-honesty problem rather than a plumbing one. |

Two triggers that apply to the record as a whole: Basilisk publishes a documented full state-reset or serialization API, which would reopen Option 2 on its merits; and the runner seam is extended to a distributed backend, at which point the per-run process contract must survive unchanged or this ADR was wrong.

## Enforcement

- **Week-1 measurement gate `spawn-floor-spike`** (first green by week 1): a twenty-minute benchmark, checked in as `bench/spawn_floor.py`, that times (i) bare `spawn` of an empty worker and (ii) `spawn` plus `import` of pydantic, numpy, scipy and astropy, on the reference workstation and in the pinned container (ADR-019), and writes the two numbers plus the hardware description into this ADR's References. The runner is not built until the numbers exist. This is the instrument the 0.60 row above is waiting on.
- **CI job `ci-worker-order-invariance`** (defined in ADR-006; §12's most important regression test) — first green by **week 5**. A 100-run experiment at `--workers 1` and `--workers 8` must produce identical evidence root hashes. The third leg this ADR contributes — the same comparison with `reusable_worker` forced off for every adapter, which is what makes the SPICE recycling exemption falsifiable — is first green by **week 6**, because it needs every adapter to exist and the SPICE exemption to be in use.
- **`tests/engine_contract/test_worker_isolation.py`**, parametrized over `FakeEngine`, `linkchain`, Basilisk — `FakeEngine` leg first green by **week 2**, `linkchain` leg by **week 4**, Basilisk leg by **week 6** (and never, if Basilisk is descoped under §17's scope-cut order). Asserts inside the worker that `multiprocessing.get_start_method() == "spawn"`; asserts every `_THREAD_ENV` key reads back pinned *after* numpy import; asserts two consecutive runs of an adapter with `reusable_worker == False` report different PIDs.
- **`test_worker_environment_pins`** (unit tier, this ADR owns it; first green by **week 2**): applies `_THREAD_ENV`, imports numpy, reads every key back from `os.environ` and asserts each is pinned, and asserts the readback dict is what `worker_env_hash` is computed over. ADR-008 cites this test rather than restating the list.
- **AST lint `no-nested-concurrency`** (first green by week 1): `threading`, `concurrent.futures`, and `multiprocessing` imports are forbidden under `src/farsight/engines/**` except `worker.py`. **PARTIALLY MECHANIZED:** an import-name lint cannot see a thread created through a compiled extension, a `ctypes` call, or a `subprocess` spawned by an engine SDK on our behalf — and Basilisk and CSPICE are both compiled. The residue is review-checklist item **WORKER-1** ("does this adapter, or the SDK it drives, create a thread or process FarSight did not create?"), whose sign-off lands in the `review_signoffs` list on the frozen `ExperimentDesign` (ADR-000), so an unanswered item is an auditable absence rather than a forgotten norm.
- **import-linter contract `worker-is-private`** (this ADR owns it; it ships in the `.importlinter` file ADR-013 assembles and runs in CI job `boundaries`, defined in ADR-013). First green by **week 1**, vacuously — `farsight.engines.worker` is importable only from `farsight.experiments.runner` and `farsight.cli`, and it has real content to guard from week 5.
- **`farsight evidence verify`** (defined in ADR-007) exits nonzero, naming the run, when a run's `worker_env_hash` disagrees with the tier claimed for its run set in `environment/fingerprint.json`. First green by **week 4** (single-run package v0), meaningful from **week 6** when campaign packages carry more than one run set.
- **AT-4** (`kill -9` at ~50%, resume, compare hashes) runs nightly against the archived campaign fixture (ADR-014 decides where that fixture lives). First green by **week 6**.

## References

- FARSIGHT_FOUNDATION_PLAN.md §3 (D2, D12, D13), §5 (engine ground truth), §8 (environment pins in every worker), §11 (execution, ledger, scale check), §12 (determinism rules), §14 (contract-test suite), §17 (week-1 spikes), §18 (AT-4, AT-7), §20 item 6 (reference workstation unspecified), §21 (adapter-cost kill).
- Verified engine facts (checked 2026-08-26): the GMAT engine is a per-process singleton, has no reliable in-process reset, and is not thread-safe; gmat-sweep established one run per fresh subprocess with file-based collection as community practice (plan §5; its license is not stated in the plan and is UNVERIFIED here). CSPICE has a global mutable kernel pool and is not thread-safe; SpiceyPy provides a `KernelPool` context manager for scoped loads (plan §5; the version that introduced it is UNVERIFIED — confirm at implementation time). Basilisk has no mid-run state serialization or checkpoint API. ADR-003 References is the canonical restatement for the set.
- ADR-003, ADR-005, ADR-006, ADR-011, ADR-012, ADR-018, ADR-019, ADR-023.
- UNVERIFIED — confirm at implementation time: the exact behavior of `ProcessPoolExecutor(max_tasks_per_child=...)` under the `spawn` context on the pinned Python 3.12 build; and the measured spawn-plus-import floor on the reference workstation, which `spawn-floor-spike` produces in week 1 and which is written back into this record (100-300 ms is a planning estimate for spawn alone and excludes the scientific-stack import entirely).
- **PLAN AMENDMENT REQUESTED: §17** — add a fourth week-1 timeboxed item to the weeks 1-2 program: `spawn-floor-spike`, a twenty-minute measurement of the process-spawn and scientific-stack-import floor on the reference workstation and in the pinned container. §17 currently schedules two 2-day engine spikes and no measurement of the execution unit's own cost, and D2's confidence cannot be honestly stated without it.
