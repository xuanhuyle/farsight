# ADR-023 — Run outcomes: taxonomy, resume policy, aggregation participation, and the error hierarchy
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §11 (ledger status enum, idempotent resume, partial results first-class), §4 (execution plane; `RunResult` status including `diverged`, `AggregateResult`), §13 (registers, audit path), §18 (AT-4, AT-6), decision D3 (refusal is a first-class outcome, never silent approximation)
**Related ADRs:** ADR-011 (fixes the ledger `status` enum in DDL and owns the ledger-as-arbiter crash model; this record defines what the values mean), ADR-002 (the worker returns a record rather than raising, and the parent writes `crashed`), ADR-003 (`UnhonorableSpec` is raised by `initialize`, and refusal at freeze is what makes a run-time refusal a defect), ADR-010 (`FaultLoweringRefused` and `FaultTargetsEnvironment` are freeze-time members of this hierarchy), ADR-001 (freeze-time validation failures, and the rule that attempt history is unhashed provenance), ADR-004 (the empirical p-box this record decides who is allowed into), ADR-009 (owns metric and acceptance-rule identity and the three-valued verdict this record widens), ADR-007 (owns the package layout the fifth register is requested into, and the `partial` manifest flag), ADR-018 (`SpecCompositionError` is a freeze-time member), ADR-012 (owns the logging mechanism and the content rule the failure payload obeys), ADR-024 (the exit-code space a terminal outcome maps to)

## Context

ADR-011 fixes the ledger's status column in DDL — `pending`, `running`, `ok`, `failed`, `diverged`, `crashed` — and defines exactly one of the six (`diverged` when `nonfinite_count > 0`). It says so deliberately: the column needed a `CHECK` constraint, and what the values *mean* was left to this record. The enum lands in the week 1-2 `execution` schema pack, the runner that produces the values lands in weeks 5-6, and four questions have to be answered before either.

**What separates `failed` from `diverged`?** An energy blow-up with no NaN in it is physically diverged and numerically finite, so the non-finite rule cannot be the whole definition. If divergence is decided by looking at the numbers after the campaign ran, it is a post-hoc judgement about which results to keep, made by the people whose claim depends on the answer. That is the same shape as the tolerance-inflation kill (§21, allowed count zero), and it needs the same structural answer.

**Where does `UnhonorableSpec` land?** ADR-003 raises it from `initialize` and elsewhere insists that refusal is "a fact printed at freeze, before an overnight campaign starts". Both cannot be casual: if a run refuses its own spec at run time, freeze validation has a hole, and a package that says the design froze complete while containing a run that refused it is internally inconsistent.

**Does `resume` re-execute `diverged` and `failed` rows?** AT-4 requires hashes identical to an uninterrupted campaign after `kill -9` at fifty percent, and it is a nightly gate. Whether that test is stable or flaky is decided entirely here: a deterministic outcome re-executed is the same outcome, but a `crashed` row caused by a timeout or by memory exhaustion may well succeed on the second attempt, and a resumed campaign that differs from an uninterrupted one is not a bug in the hasher.

**Do diverged runs enter the `AggregateResult`?** This is the only one of the four that is not plumbing. Dropping diverged runs from an empirical CDF and reporting the survivors is survivorship bias inside the p-box — the laundering ADR-004 exists to prevent, reappearing one layer below the type system, where no type can catch it. And the bias is not random: the runs that diverge are the ones near the boundary where the model breaks, which is where the verdict is decided. There is currently no register for excluded runs; the four cover assumptions, unknowns, collapses and validity violations.

Underneath all four, the exception surface is scattered: `UnhonorableSpec` (ADR-003), `FaultLoweringRefused` and `FaultTargetsEnvironment` (ADR-010), unnamed freeze failures (ADR-001), `SpecCompositionError` (ADR-018). No base class, no rule about which are raised in the parent and which inside a worker, and no statement of what crosses the pool boundary — where, per ADR-002, nothing but bytes may cross at all.

## Decision

**1. Six ledger statuses; four of them terminal; only terminal ones appear in a package.**

- `pending` — planned, never dispatched, or reset by `resume`. Ledger only.
- `running` — claimed by the parent and dispatched. Ledger only. A `running` row found by `resume` is stale by definition (the parent that claimed it is gone) and is treated as `pending`; ADR-011's rule that the ledger is the arbiter means any files it left are garbage.
- `ok` — the worker returned a complete record: every channel in every stage's `emits` (ADR-018) present, `nonfinite_count == 0` on all of them, and no declared divergence criterion violated. A run may be `ok` and still carry validity flags: exiting a declared validity envelope is recorded in the validity-violation register and does not make the run invalid, because extrapolation is a stated fact, not a failure.
- `failed` — the run did not produce usable output for a reason that is a **deterministic function of the spec and the environment**. Re-executing reproduces it exactly.
- `diverged` — the run *completed* its numeric work and its output is unusable by a rule declared before the campaign ran. Deterministic, like `failed`, and distinguished from it because the two participate differently in aggregation (below) and answer different questions for a reader.
- `crashed` — the process died: signal, out-of-memory, or per-run timeout. No record was returned; the parent writes the row (ADR-002). This is the one status that is **not** guaranteed deterministic, and everything awkward below follows from that.

The discriminator is stated once and used everywhere: **`failed` and `diverged` are properties of the run; `crashed` is a property of the machine.**

**2. Divergence is declared in advance, hashed, and recomputable with no engine installed.**

A run is `diverged` when either of these holds:

- the structural rule: any emitted channel has `nonfinite_count > 0` (ADR-011 decision 3); or
- a **declared divergence criterion** is violated.

**The structural rule is unconditional, which makes one modelling convention mandatory: an entity that does not exist is a code, never a NaN.** In a campaign with attrition, staggered deployment or dormancy, some entities are absent for part of the grid. An engine that writes NaN into their columns marks the whole run `diverged` under the rule above — it is then excluded from realized aggregation and enters as bounding mass, widening every envelope and pushing verdicts to `indeterminate`, precisely for the runs in which the attrition physics behaved exactly as designed. The rule is not being relaxed: a non-finite sample means the numbers stopped being meaningful, and that must stay unconditional. Absence is expressed instead by a lifecycle channel with a `code_map` alongside a physical channel that holds its last value or zero (ADR-020), with metrics gating on the lifecycle code. This is a convention rather than a validator, because no check can tell an engine's honest NaN from its lazy one — but a Stage-5 campaign that returns all-`indeterminate` for no discoverable reason is the failure it prevents, and that failure is expensive to diagnose from the far end.

```python
class DivergenceCriterion(BaseModel):          # design plane, frozen, extra="forbid"
    criterion_ref: ContentHash                 # an AcceptanceCriterion (ADR-009)
    on_violation: Literal["diverged"] = "diverged"

# on ExperimentDesign:
divergence_criteria: list[DivergenceCriterion]
```

A divergence criterion **is** an ADR-009 `AcceptanceCriterion` in a distinguished role: it references `metric_ref` plus comparator plus threshold plus rationale, its subject is a single run rather than an aggregate, and its violation maps to a run outcome rather than to a claim. Nothing here is a rival home for thresholds — ADR-009's rule that thresholds live only in acceptance rules is preserved exactly, and so is its versioning, its diff and its no-silent-loosening machinery. Editing a divergence threshold after seeing results is the same object, the same audit trail, and the same kill criterion as loosening any other tolerance.

Because the criteria sit on the frozen `ExperimentDesign`, they are inside `experiment_hash` (ADR-001), so "we decided afterwards which runs to call diverged" is not expressible: the rule that excluded a run was fixed before the run existed, and an auditor can read it. Evaluation happens in the worker at collect time, on the arrays already in memory, using `farsight.metrics` pure functions — and because the metric is a pure function of stored channels, `verify` recomputes the divergence decision from package content on a zero-extras install, with no engine and no re-execution.

**3. `UnhonorableSpec` at run time is `failed`, and in an evidence-grade package it is an integrity failure.**

ADR-003's refusal is a freeze-time fact. A run that raises `UnhonorableSpec` from `initialize` is therefore recorded `failed` with `failure_class: unhonorable_spec` **and** is a report that the freeze-time completeness check has a hole. A package whose frozen design asserts complete binding and whose runs contain an `unhonorable_spec` failure contradicts itself, and `verify` exits nonzero naming the run. This is not a content judgement smuggled into the verifier: two documents in the same package assert incompatible things, which is exactly what integrity checking is for. `internal_error` — any exception that is not a `FarSightError` — is treated the same way, because our own bug is not a scientific result.

**4. The terminal record, and what is inside the hash.**

```python
class RunOutcome(BaseModel):                   # the "object" half of runs/status_<i>.json
    run_id: ContentHash
    run_index: int
    status: Literal["ok", "failed", "diverged", "crashed"]
    output_hash: ContentHash | None            # present iff status == "ok"
    worker_env_hash: ContentHash
    divergence: DivergenceReport | None
    failure: FailureReport | None
    validity_flags: list[ValidityFlagRef]

class DivergenceReport(BaseModel):
    rule: Literal["nonfinite", "declared_criterion"]
    criterion_ref: ContentHash | None          # required iff rule == "declared_criterion"
    channel: str | None                        # stage-qualified (ADR-018, ADR-020)
    first_index: int | None                    # sample index, an exact integer
    observed: Quantity | None                  # decimal string + unit (ADR-001)

class FailureReport(BaseModel):
    failure_class: Literal["unhonorable_spec", "input_artifact_mismatch", "stage_binding_error",
                           "engine_failure", "timeout", "killed_by_signal", "out_of_memory",
                           "internal_error"]
    detail: str                                # identifiers, paths and hashes only (ADR-012)
    traceback_sha256: ContentHash | None
```

The provenance half of the same file — never hashed, per ADR-001 rule 4 — carries `attempt_count`, `wall_time_s`, timestamps, worker PID and exit signal. **That placement is what makes AT-4 stable:** a run that crashed once and succeeded on resume produces a byte-identical `RunOutcome` object to one that succeeded on the first attempt, so the evidence root hash cannot see the interruption.

**5. Resume re-executes everything except verified `ok`.** `ok` is skipped only when its recorded `output_hash` recomputes from the files on disk; otherwise the row is garbage and it re-executes. `pending`, stale `running`, `failed`, `diverged` and `crashed` all re-execute. This is plan §11's rule, unchanged, and it is correct precisely because `failed` and `diverged` are deterministic — re-executing them costs time and reproduces the same terminal record. There is **no automatic retry inside one campaign invocation**: a crashed run stays crashed until an operator runs `resume`, which is an explicit act with an audit row (ADR-012).

AT-4's claim is therefore restated exactly, because the loose version is not true and pretending otherwise makes a nightly gate flaky: **for every run that reaches a deterministic terminal outcome, the interrupted campaign's channel hashes, metric hashes and `RunOutcome` objects equal the uninterrupted campaign's.** A resource-caused `crashed` run can legitimately become `ok` on a second attempt, and no hashing design can make that identical — the outcome genuinely differed. `test_crash_resume` (defined in ADR-011) therefore additionally asserts that the crashed set is empty in the uninterrupted arm and fails naming a resource-configuration defect rather than a hash mismatch when it is not.

**6. Excluded runs enter the aggregate as bounding mass, never as a deletion.**

Only `ok` runs contribute realized metric values. Every other run still contributes, as an interval:

```python
class MetricBound(BaseModel):                  # design plane, frozen
    metric_ref: ContentHash
    minimum: Quantity | None
    maximum: Quantity | None
    rationale: str                             # why these are the admissible physical bounds

class ParticipationPolicy(BaseModel):          # on ExperimentDesign
    aggregate_over: Literal["ok_only"] = "ok_only"
    excluded_treatment: Literal["bounding_mass"] = "bounding_mass"
    bounds: list[MetricBound]

class AggregateResult(BaseModel):              # execution plane
    outer_point_index: int
    n_planned: int
    n_ok: int
    excluded: list[ExcludedRun]                # run_index, terminal status, reason ref
    cdf_lower: EmpiricalCdf
    cdf_upper: EmpiricalCdf
```

Per outer point, the inner empirical CDF is computed over all `n_planned` runs. Each excluded run is placed at the metric's **maximum** admissible value to produce `cdf_lower`, and at its **minimum** to produce `cdf_upper`; the true CDF for any completion of the missing runs lies between them. With zero exclusions the two coincide exactly and nothing about the happy path changes. If the metric declares no bound on the relevant side, the corresponding edge is undefined and every criterion evaluated over it returns `indeterminate`.

The verdict rule is ADR-009's, applied to a wider band: the criterion holds for every CDF in the box gives `pass`, holds for none gives `fail`, anything else gives `indeterminate`. A campaign with many diverged runs therefore produces `indeterminate` rather than a clean-looking `pass`, which is the entire point. Exclusion is distinct from `partial` (ADR-007): `partial: true` means planned runs were never executed at all, typically after cancellation; exclusion means executed runs produced no usable value. Both are enumerated; only the first sets the flag.

**7. A fifth register: `registers/excluded_runs.json`.** Every terminal run that is not `ok` appears exactly once, with its `run_index`, status, `failure_class` or divergence report, the outer and inner indices it occupied, and the criterion that excluded it. The four existing registers answer what we assumed, what we did not know, where we exercised judgement and where we extrapolated; this one answers **what we did not count**, and it is the question an auditor asks about any CDF. It belongs beside the other four because ADR-007's audit path has the reader open `registers/` first; a fact that decides whether a distribution is honest cannot live only in a file reached at step four. ADR-007 owns the package layout, so the fifth register is requested there and in plan §13; the whole set is `Proposed` and reviewed as one act (ADR-000), which is where that coordination lands.

**8. One exception hierarchy, three branches, and nothing crosses the pool boundary.**

```python
class FarSightError(Exception): ...            # base; never raised directly

class FreezeTimeError(FarSightError): ...      # raised in the parent; no run is ever planned
class IncompleteDesign(FreezeTimeError): ...        # ADR-001 freeze validation
class UnresolvedReference(FreezeTimeError): ...     # a draft or an alias inside a frozen doc
class FaultLoweringRefused(FreezeTimeError): ...    # ADR-010 / ADR-003
class FaultTargetsEnvironment(FreezeTimeError): ... # ADR-010 boundary validator
class SpecCompositionError(FreezeTimeError): ...    # ADR-018 stage, binding, grid, capability
class KernelCoverageError(FreezeTimeError): ...     # ADR-016 coverage window

class WorkerError(FarSightError): ...          # raised inside the worker process
class UnhonorableSpec(WorkerError): ...             # ADR-003 initialize
class InputArtifactMismatch(WorkerError): ...       # an input hash disagrees with the manifest
class StageBindingError(WorkerError): ...           # ADR-018 binding failure at execute
class EngineFailure(WorkerError): ...               # an adapter reports an engine-side error

class VerificationError(FarSightError): ...    # raised by verify / replay in the audit path
```

Two rules make the hierarchy load-bearing rather than decorative.

*Freeze-time errors abort `farsight freeze` in the parent, name the offending object id, and exit nonzero (code space: ADR-024). No run is planned, so they can never appear in a ledger, in a package, or in a worker.* That is what "refusal at freeze, not failure at run 8,300" means mechanically.

*No exception crosses the pool boundary.* The worker's top level catches `BaseException`, maps it to a `failure_class`, and returns a canonical-JSON `RunOutcome` with `status: failed`; ADR-002's contract that only bytes cross is preserved without exception. The `detail` string is restricted to identifiers, paths and hashes — never rendered locals, never a magnitude — because customer inputs may themselves be export-controlled technical data (§16 item 4, ADR-012's `LOG-CONTENT` rule). The traceback text goes to the run-scoped log file ADR-012 governs and is deliberately **not** package content; only its SHA-256 is recorded, so a support conversation can confirm two operators are looking at the same traceback without the package carrying it.

## Options considered

### Option 1 — Two states, `ok` and `not_ok`, plus a free-text reason — REJECTED
This is what most Monte Carlo drivers ship, and it has a genuine argument behind it: every failure taxonomy rots into a junk drawer, exactly as fault catalogues do (ADR-010's Context says so), and a boolean plus a sentence is never *wrong*. It would also delete this entire record. Rejected because two of the downstream decisions need a machine-readable distinction that the sentence cannot carry: aggregation must treat "never ran" differently from "ran and produced physically unusable output" (decision 6), and resume must treat a deterministic outcome differently from a machine-caused one (decision 5). The enum is already in ADR-011's DDL; what it lacked was meaning, not values.

### Option 2 — Exclude non-`ok` runs from the aggregate and report the count — REJECTED
The default answer, the one every tool in the category gives, and it is not indefensible: the CDF over successful runs is a well-defined object — the conditional distribution given that the run completed — and disclosing the count is more than most tools do. Rejected because the conditional distribution is not the quantity the claim is about. The claim is about the system, not about the system given that our integrator converged, and the two differ precisely where it matters: divergence is not independent of the metric, it concentrates near the failure boundary, so dropping those runs biases the reported distribution toward optimism exactly where the verdict is decided. A footnote saying "37 runs excluded" beside a percentile does not repair a biased percentile; it documents it. This is the survivorship bias ADR-004's type system cannot reach, and it is the reason this record exists.

### Option 3 — Re-run diverged runs with a tightened integrator or fallback settings until they converge — REJECTED
The strongest version is what a careful engineer does by hand and it has real physics behind it: most divergence in a well-posed problem is a numerical artifact, a diverged run at a loose tolerance is evidence about the integrator rather than about the spacecraft, and re-running at `tau/100` is the same move ADR-006 already blesses as Richardson-style discrimination for Tier C. Rejected because it makes a run's spec a function of that run's result. `(experiment_hash, run_index) -> spec_hash` stops being a derivation (ADR-001 rule 5), AT-7 dies, and replay of run #4242 becomes a question about which attempt you meant. It also converts a possible physical instability into a numerical one with no evidence that it was one. The honest path remains available and is a different thing: declare a tighter tolerance and run a **new** campaign, with a new `experiment_hash` that says so.

### Option 4 — `ok`-only realized values plus bounding mass for exclusions, verdicts from the widened band — CHOSEN
Reuses ADR-009's three-valued verdict and ADR-004's p-box vocabulary rather than inventing a third way to talk about incompleteness, makes silent dropping structurally impossible, and degrades to the ordinary CDF exactly when nothing was excluded.

### Option 5 — Record exclusions only in `status_<i>.json` and the metrics documents; keep four registers — REJECTED
Attractive because it departs from neither plan §13 nor ADR-007, and because the data is already present and already hashed — a determined auditor can reconstruct the exclusion set from files they already have. Rejected on where a reader looks. ADR-007's audit path is `show` first (claim and registers), then `verify`, and the whole design of the registers is that the four questions an auditor must ask are answered in one directory before anything else is opened. A fact that decides whether the headline distribution is honest, reachable only by cross-referencing ten thousand status files, is available rather than disclosed.

### Option 6 — No exception hierarchy; use standard-library exceptions and error codes — REJECTED
Genuinely tempting: `ValueError` and `RuntimeError` are what every Python developer already catches, Pydantic raises `ValidationError` regardless so a custom base does not achieve uniformity anyway, and a base class no one catches is ceremony. Rejected because the worker boundary needs a closed mapping from exception type to `failure_class`, and a closed mapping over the standard library's open set is not writable — every new error site would invent its own spelling and the enum would drift from the code. The base class also buys the one lint that matters: an exception defined under `src/farsight/` that does not subclass `FarSightError` is a site nobody classified.

## Consequences

**Buys us:** an outcome vocabulary the ledger, the package, the aggregate and the CLI all read the same way; a divergence rule that was fixed before the numbers existed and can be recomputed by a stranger with no engine installed; an aggregate that cannot silently drop the runs nearest the failure boundary; a resume policy under which AT-4's claim is precisely true rather than approximately true; and one error hierarchy in which every scattered exception in the set now has a branch, a raising site and a defined fate at the pool boundary.

**Costs us:** every campaign must declare divergence criteria and metric bounds up front, which is authoring friction at exactly the moment (week 3-4) when nobody yet knows what the metric's admissible range is, and a missing bound turns into `indeterminate` verdicts rather than into an error. The bounding-mass construction is a second aggregation path to implement and test. The fifth register is a departure from a plan section and from an already-written ADR-007, and coordinating it costs a founder-review item. And `verify` gains work: it recomputes divergence decisions from channels, which on a 10k-run campaign is a full pass over the channel bytes, landing on ADR-011's `verify`-wall-time risk row rather than beside it.

**Forecloses:** the clean narrow envelope, whenever runs are excluded. Bounding mass **widens** the reported p-box in proportion to the excluded fraction, and AT-5 fails a DSOC envelope wider than 6 dB while K2 kills the flagship above 12 dB. So this decision can cost us the flagship acceptance test for an honest reason — a campaign with a five percent divergence rate may report an envelope that Option 2 would have reported as narrow and decided. We are choosing the answer that can fail. It also forecloses automatic recovery of any kind: no retry with different settings, no adaptive tolerance, no salvaging a partially written channel set, forever, because each of those makes the executed spec depend on the observed result. And a `crashed` run remains permanently outside the determinism claim — the honest statement in every package is that terminal outcomes are reproducible except where the machine, rather than the model, decided.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Six ledger statuses with these meanings; four terminal ones in a package | 0.88 | The week-5 runner needs a fifth terminal value — most likely `skipped` for a refused (fault, engine) pair that the planner nevertheless enumerated — which would mean ADR-003's refuse-at-freeze rule is not holding all the way to the ledger. |
| `failed` versus `diverged` split on determinism plus a declared criterion | 0.78 | The week-5 campaign finds that every diverged run is caught by the structural non-finite rule and no declared criterion ever fires, which would make the criteria ceremony; or a physically obvious divergence cannot be expressed as an ADR-009 metric plus comparator. Both are visible in the week-5 campaign, before any package ships. |
| Resume re-executes everything but verified `ok`; attempt history unhashed | 0.85 | `test_crash_resume` (defined in ADR-011) is red twice for a cause traced to re-execution rather than to a hashing bug, or the week-6 campaign spends more than ten percent of its wall time re-executing deterministic failures, at which point skipping `failed` and `diverged` rows on resume is reconsidered with the AT-4 argument re-made. |
| **Excluded runs enter as bounding mass rather than being dropped** | **0.70** | Fires on the week-5 campaign: if bounding mass widens the flagship envelope past AT-5's 6 dB ceiling while the `ok`-only envelope is inside it, we have a decision to make in public rather than a bug to fix, and the only admissible alternative is a declared, hashed, register-recorded exclusion policy argued in a superseding record — never a quiet switch to `ok`-only. Also fires if >=3 of the 8 K5 interviews (end wk 6) say a bounded envelope is unusable to them. |
| A fifth register rather than a field in an existing one | 0.72 | The founder review of this set rejects a fifth register, in which case the content moves to `registers/validity_violations.json` under a distinct entry kind plus the `AggregateResult.participation` block, and the audit path's step 1 gains an explicit instruction to read it. This row is low because it is the one decision here that plan §13 already answers differently, and it is the only amendment in the set that contradicts a written text rather than adding to one, so it needs an explicit founder yes rather than a batch nod. |
| Three-branch exception hierarchy with nothing crossing the pool boundary | 0.85 | An adapter's SDK raises a C-level fault that neither the worker's `BaseException` handler nor the parent's signal handling can classify, so `failure_class` acquires an `unclassified` member — which would mean the closed mapping is not closed and the lint is guarding a fiction. |
| `unhonorable_spec` and `internal_error` as integrity failures in an evidence-grade package | 0.75 | The week-6 campaign produces an `unhonorable_spec` run whose cause is a legitimately unfreezable condition that only the worker can detect (a kernel coverage edge, a provider-side capability that cannot be introspected in the parent), which would mean the rule punishes an honest limit rather than catching a hole. |

## Enforcement

1. **`test_outcome_taxonomy_agreement`** (unit tier, every commit; **first green by week 2**): asserts that the `status` `Literal` in the execution schema pack is exactly the set in ADR-011's `CREATE TABLE runs` `CHECK` clause, parsed out of the DDL string rather than retyped, and that `RunOutcome.status` admits exactly the four terminal values. Two records cannot drift into two enums.
2. **`test_divergence_is_declared`** (**first green by week 4**): asserts that `divergence_criteria` is a field of the frozen `ExperimentDesign` and therefore inside `experiment_hash`; that no code path sets `status = "diverged"` except the structural non-finite rule and a criterion evaluation; and that `verify` reproduces every `DivergenceReport` from the stored `.npy` channels on a no-extras install, with `farsight.engines` absent from `sys.modules`.
3. **`test_resume_outcome_policy`** (**first green by week 5**, when the runner and ledger exist): parametrized over all six statuses, asserts which rows `resume` re-executes and that a verified-`ok` row is skipped while an `ok` row whose `output_hash` no longer recomputes is not. AT-4's end-to-end half is `test_crash_resume` (defined in ADR-011), which this test does not duplicate; the two are the policy and the property.
4. **`test_aggregate_participation_bounds`** (**first green by week 5**): over a synthetic campaign, asserts that zero exclusions make `cdf_lower` and `cdf_upper` byte-identical; that k exclusions out of N separate them by exactly k/N in probability mass; that a missing `MetricBound` on the relevant side yields `indeterminate` rather than a silently narrowed edge; and that `n_planned` equals the ledger's row count for the outer point, so an aggregate cannot be computed over a set the ledger does not know about.
5. **`test_excluded_runs_register`** (**first green by week 5**): every terminal run that is not `ok` appears exactly once in `registers/excluded_runs.json`, with a resolvable reason reference; a run present in the ledger and absent from the register fails `verify` naming the run index.
6. **`test_exception_hierarchy_closed`** (**first green by week 2**): every exception class defined under `src/farsight/` subclasses `FarSightError`; no `FreezeTimeError` subclass is raised or imported anywhere under `src/farsight/engines/`; and, by injecting each `WorkerError` subclass and one bare `RuntimeError` into a `FakeEngine` run, that the worker returns a valid `RunOutcome` in every case and lets nothing propagate across the pool boundary.
7. **`test_self_contradiction_integrity`** (**first green by week 4**): an otherwise valid `evidence_grade: evidence` package containing a run with `failure_class` of `unhonorable_spec` or `internal_error` makes `farsight evidence verify` (defined in ADR-007) exit nonzero naming the run.
8. **PARTIALLY MECHANIZED: DIV-1** — whether a declared divergence criterion is the right physics. Everything about the criterion is checkable — that it exists, that it is hashed before the campaign runs, that it is an ADR-009 acceptance rule with a rationale, that it was not edited after results appeared, that `verify` reproduces its evaluation — and none of that touches whether an energy drift threshold of the declared magnitude actually separates a broken integration from a real trajectory. Residue: the physical adequacy of each criterion. Review-checklist item **DIV-1** — "does this criterion exclude runs that are numerically broken rather than runs that are physically inconvenient?" — recorded in the `review_signoffs` list on the frozen `ExperimentDesign` (ADR-000), so the judgement is an auditable row rather than a habit.
9. **PARTIALLY MECHANIZED: LOG-CONTENT** — that `FailureReport.detail` carries no physical magnitude. The mechanical half is a validator rejecting any `detail` string matching the decimal grammar of ADR-001 rule 2 outside a recognized hash or index, plus the leak canary of `LOG-CONTENT` (defined in ADR-012), **first green by week 2**. Residue: a magnitude spelled in words, or a customer identifier that is itself sensitive; ADR-012 owns that item and this record does not restate its rule.

## References

- FARSIGHT_FOUNDATION_PLAN.md §4 (execution plane; `RunResult` status including `diverged`; `AggregateResult` as per-outer-point inner distributions plus cross-outer envelope), §11 (ledger schema and status set, idempotent resume that skips verified-`ok` rows, cooperative cancellation, partial results first-class), §13 (four registers, audit path, "if prose and JSON disagree, JSON is the record"), §14 trust preconditions, §18 (AT-4, AT-6, AT-7), §21 (tolerance-inflation kill, allowed count zero; K2's 12 dB and AT-5's 6 dB width criteria), decision D3.
- ADR-001, ADR-002, ADR-003, ADR-004, ADR-007, ADR-009, ADR-010, ADR-011, ADR-012, ADR-016, ADR-018, ADR-024.
- Coordination item, not a plan departure: decision 2 evaluates divergence criteria inside the worker, so `farsight.engines.worker` imports `farsight.metrics`. ADR-013's contracts are `forbidden`-type, so `farsight.engines.worker` importing `farsight.metrics` is already permitted and needs no edit; what does need stating there is that the reverse ban (`metrics-purity`) is unchanged and that this edge is deliberate, so a future `layers` contract does not sever it silently.
- UNVERIFIED — confirm at implementation time: whether a per-run timeout and an out-of-memory kill are distinguishable from the parent on Windows well enough to populate `failure_class` correctly, or whether both collapse to `killed_by_signal` on that platform, which would make the two members' distinction Linux-only and would need saying in the record rather than discovering in week 6.
- **PLAN AMENDMENT REQUESTED: §13** — a fifth register, `registers/excluded_runs.json`, alongside the four §13 names. Reason: the four registers answer what was assumed, what was unknown, where judgement was exercised and where the model was extrapolated; none of them answers what was not counted, and an empirical CDF with silent exclusions is the one failure in this product that survives every mechanical check and is found by a reader. ADR-007 owns the package layout and carries the fifth register in its own list, requested in the same review pass.
- **PLAN AMENDMENT REQUESTED: §4** — `AggregateResult` gains a participation block (`n_planned`, `n_ok`, the enumerated excluded set) and reports a bounding CDF pair rather than a single empirical CDF per outer point, and `ExperimentDesign` gains `divergence_criteria` and a `ParticipationPolicy` with per-metric admissible bounds. §4 describes `AggregateResult` as inner distributions plus an envelope without saying which runs are in it.
- **PLAN AMENDMENT REQUESTED: §18** — AT-4's "channel and metric hashes identical to an uninterrupted campaign" is qualified to runs that reach a deterministic terminal outcome, with attempt history held in the unhashed provenance block so that a crash-then-succeed run hashes identically to a first-attempt success, and with an added assertion that the uninterrupted arm's crashed set is empty. Reason: as written the criterion is falsified by any resource-caused crash, which is a property of the machine and not of FarSight, and a nightly gate that can go red for a reason no code change can fix will be rationalized away within two weeks.
