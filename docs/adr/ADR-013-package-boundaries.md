# ADR-013 — Modular monolith: package boundaries and dependency rules
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §6, §3 decision D1, §2, "Things we must get right" items 7 and 8
**Related ADRs:** ADR-014 (extras and the lock are how "optional engine" becomes an installable fact), ADR-003 (`engines.base` is the only adapter surface anything upstream may see), ADR-002 (the subprocess worker is where adapter code actually executes; it owns `worker-is-private`), ADR-007 (the auditor must verify a package with zero engines installed), ADR-001 (one distribution keeps code identity a single hash), ADR-012 (owns `no-network-in-truth-loop`, the contract that governs `acquire/`), ADR-018 (owns `geometry_is_not_an_engine`, which ships in the file assembled here), ADR-022 (owns `no_sampler_libraries`, likewise), ADR-025 (the LLM exclusion, which this record carried in an earlier draft and no longer decides), ADR-000 (this ADR's Enforcement section is the template's motivating case)

## Context

The forcing question is not "monolith or microservices" — nobody is deploying services here. It is: how do we carve a single Python codebase so that *"`farsight evidence verify` runs on an auditor's laptop with zero engine extras installed"* is a property the build system guarantees, rather than a sentence in a README that happens to be true on the day someone last checked.

The verified engine landscape makes engine availability genuinely heterogeneous, and that is what forces the shape. Basilisk installs from PyPI as `bsk` with prebuilt wheels, Windows supported (plan §5), and constrains the interpreter to >=3.9,<3.15. GMAT is not pip-installable at all: R2025a is an application-tree install driven through its Python API entry point (the exact entry-point filename is UNVERIFIED — fixed during the week-1 GMAT spike, ADR-014). SpiceyPy is an MIT wrapper with a bundled compiled CSPICE. TudatPy is conda-only. There is no world in which a person auditing an evidence package installs all of that, and there is no world in which we ask them to. (The engine behaviour facts — GMAT's singleton engine, CSPICE's global kernel pool — are load-bearing in ADR-002 and ADR-003 and are stated once there; only install shape matters here.)

What breaks if we get this wrong is AT-9 (§18): an external engineer, given only the package, the CLI and the README, completes the audit in under two hours. If `import farsight.evidence` transitively pulls `bsk`, that person's `pip install farsight` either fails outright or drags in a compiled simulation framework to check some SHA-256 sums, and the product's central claim — independently verifiable evidence — dies at the install step, in front of exactly the audience it was built for. Worse, the failure is invisible to us: every developer machine has the extras installed, so an accidental `from farsight.engines.spice import ...` inside `evidence/` passes the entire test suite locally and fails only on the auditor's laptop.

An earlier draft of this record also carried the LLM exclusion (D14). It has been split out: the two decisions share no forcing question, no revisit trigger and no likely lifetime, and bundling them meant that acting on an LLM trigger would require superseding the `auditor_boundary` contract along with it. The exclusion is now ADR-025, and nothing about it is decided here.

## Decision

**One distribution, one package, src layout.** A single PEP 621 distribution named `farsight` containing one importable package at `src/farsight/`, with the subpackage tree of §6 plus `acquire/`: `schemas/`, `units/`, `hashing/`, `registry/`, `acquire/` (the `farsight fetch` code path, and the only package permitted an HTTP import — ADR-012), `engines/{base,worker,spice,basilisk,linkchain,gmat}`, `faults/`, `uncertainty/`, `experiments/`, `metrics/`, `comparison/`, `evidence/`, `cli/`, `analysis/`. Engine and analysis dependencies live in optional extras (`spice`, `basilisk`, `gmat`, `analysis`, `dev`; see ADR-014).

Plain `pip install farsight` installs everything except the engine SDKs and the analysis stack: `schemas`, `units`, `hashing`, `registry`, `acquire`, `faults`, `uncertainty`, `experiments`, `metrics`, `comparison`, `evidence`, `engines.base`, `engines.worker`, `engines.linkchain` and `cli`. No compiled engine and no plotting stack arrives with it. That is the whole of the install-time guarantee, and it is deliberately a statement about *distributions on disk*, not only about imports: an installed-but-unimported CSPICE still appears in the auditor's `pip list` and still costs us the sentence.

**Boundary rules, as import-linter contracts, in CI from the first commit.** The contracts below are the ones this ADR decides; seven more live in the records that own them and ship in the same `.importlinter` file — `worker-is-private` (ADR-002), `metrics-purity` (ADR-009), `no-units-lib-in-core` (ADR-008), `no-network-in-truth-loop` (ADR-012), `no_llm_sdk` (ADR-025), `geometry_is_not_an_engine` (ADR-018) and `no_sampler_libraries` (ADR-022). The file is assembled here and run by one CI job; the contracts are owned where their rationale lives. The configuration is the decision:

```ini
[importlinter]
root_package = farsight
include_external_packages = True

[importlinter:contract:schemas_is_leaf]
name = schemas is the typed vocabulary and imports nothing internal
type = forbidden
source_modules = farsight.schemas
forbidden_modules =
    farsight.units
    farsight.hashing
    farsight.registry
    farsight.acquire
    farsight.engines
    farsight.faults
    farsight.uncertainty
    farsight.experiments
    farsight.metrics
    farsight.comparison
    farsight.evidence
    farsight.cli
    farsight.analysis

[importlinter:contract:auditor_boundary]
name = evidence and hashing verify with zero engine extras installed
type = forbidden
source_modules =
    farsight.evidence
    farsight.hashing
forbidden_modules =
    farsight.engines
    farsight.experiments.runner
    farsight.acquire
    farsight.analysis
    bsk
    Basilisk
    spiceypy
    pandas
    matplotlib

[importlinter:contract:adapters_only_via_base]
name = upstream code knows adapters only through engines.base protocols
type = forbidden
source_modules =
    farsight.experiments
    farsight.metrics
    farsight.comparison
    farsight.uncertainty
    farsight.faults
forbidden_modules =
    farsight.engines.spice
    farsight.engines.basilisk
    farsight.engines.linkchain
    farsight.engines.gmat

[importlinter:contract:pure_compilers]
name = faults and uncertainty are pure compilers
type = forbidden
source_modules =
    farsight.faults
    farsight.uncertainty
forbidden_modules =
    farsight.engines
    farsight.registry
    farsight.cli
    farsight.evidence

[importlinter:contract:analysis_quarantine]
name = nothing in the truth loop imports analysis or its heavy deps
type = forbidden
source_modules =
    farsight.schemas
    farsight.units
    farsight.hashing
    farsight.registry
    farsight.engines
    farsight.faults
    farsight.uncertainty
    farsight.experiments
    farsight.metrics
    farsight.comparison
    farsight.evidence
forbidden_modules =
    farsight.analysis
    pandas
    matplotlib
```

Each rule earns its place. `schemas` imports nothing internal because it is the only typed vocabulary and every other package depends on it; a back-edge would make the dependency graph a cycle and would let a physical quantity leak into the shared schema layer, which is scope-creep tripwire #1 (§2). `evidence` and `hashing` never import `engines` because of the auditor laptop — **this is the most commercially important import rule in the codebase**, and it is the one rule whose violation is invisible on every developer machine; `auditor_boundary` is its name, and every other record that relies on the rule cites it by that name rather than restating it. `acquire` is on the same forbidden list because `verify` makes zero network calls, ever (§16) — but the general no-network rule is ADR-012's `no-network-in-truth-loop`, not this block, and `acquire` appears here only as the auditor-boundary half of it. `experiments` knows adapters only via `engines.base` protocols so that the contract-test suite can run the identical tests against a `FakeEngine`, the link chain and Basilisk (§6); `engines.worker` is deliberately not on that forbidden list, because the subprocess harness is plumbing rather than an adapter (ADR-002, which owns `worker-is-private`). `faults` and `uncertainty` are pure compilers — a `FaultCampaign` lowers to an `InterventionSchedule` and a declared `FaultBindingImpl` mechanism, which are *data*; the adapter interprets that data, so the compiler never needs an engine import, and keeping it that way is what lets fault lowering be unit-tested with no engine installed and lets refusal (`unsupported_on: [gmat]`) be computed at freeze time. `analysis` is quarantined as the only place pandas and matplotlib may live, because a DataFrame in the truth loop makes column dtype and ordering implicit exactly where §12 requires that no hashed value depend on iteration order.

**Replay is inverted, not exempted.** §6 places the replayer in `evidence/` and forbids `evidence/` from importing engines. These are reconcilable only by dependency inversion, and this ADR chooses it: `farsight.evidence.replay` defines a `RunExecutor` protocol and re-executes runs through an executor handed to it by the caller; `farsight.cli` is the only place that constructs a concrete executor from `experiments` plus an adapter. The verification-only half of the audit path (recompute hashes, revalidate schemas, recompute metrics from raw `.npy` channels) needs no executor at all, and that is precisely the half the zero-extras auditor runs. The half they do *not* get is named under Forecloses, where it belongs.

**The LLM exclusion is not decided here.** ADR-025 records it, owns the `no_llm_sdk` contract that ships in the `.importlinter` file above, and owns the lock-file scan that backs it. This record's contribution is only the mechanism: the quarantine that makes `analysis/` a place where a heavy dependency can be confined is the same mechanism ADR-025 considers and rejects as a home for an SDK.

## Options considered

### Option 1 — Multi-package uv workspace (`farsight-core`, `farsight-engine-basilisk`, ...) — REJECTED
Separate distributions make the boundaries physical rather than linted: the auditor literally cannot import an adapter that is not installed, adapters version independently, and this is where a 10-engineer version of this codebase belongs. Rejected for two reasons. First, cost against team size: three devs (§17) during weeks 1-6, when the schema pack churns daily, would pay a cross-package release dance for every field added. Second and more decisive, it fragments code identity. ADR-001 and ADR-007 want one tool version and one commit in the manifest; N independently versioned distributions turn "what code produced this package" from a hash into a resolution problem, and the environment fingerprint grows a version-plus-hash tuple per component. Extras deliver the install-time property we actually need without that cost.

### Option 2 — Flat package, convention-only boundaries — REJECTED
Fastest to start, and there is a real argument that import-linter contracts authored in week 0 against a tree that does not yet exist will be wrong and will be fought. Rejected because boundary erosion is the modular monolith's characteristic death mode, and here the specific erosion has a name: someone in `evidence/` imports the SPICE geometry service to conveniently recompute a range during verification, all tests pass, and the failure surfaces months later on a customer's auditor's machine. Contracts that are slightly wrong get fixed in the commit that trips them; contracts that do not exist get discovered by customers.

### Option 3 — Plugin architecture with entry-point-discovered adapters — REJECTED
Third parties could ship adapters without forking, which is a plausible commercial channel. Rejected for the MVP because entry-point discovery makes the set of loaded code a function of the environment, which fights ADR-006's environment fingerprint: two machines with identical locks could load different adapter sets. Adapters are registered in an explicit in-repo table. Revisit when someone has actually written one — which §2 tripwire #2 says cannot even be tracked until one cross-engine comparison has shipped inside an evidence package.

### Option 4 — Single distribution with extras and import-linter contracts — CHOSEN
Gets the install-time guarantee from extras, the compile-time guarantee from linted contracts, and keeps one hash for the code that produced any package.

## Consequences

**Buys us:** an auditor install path that is one `pip install farsight` with no compiled engines; one `.importlinter` file that is the entire layering, so "may X import Y" is answered by grep rather than by argument; a codebase where a new dev learns the layering by having the build reject the wrong import; and honest engine-neutrality, because upstream code physically cannot reach past `engines.base`.

**Costs us:** contracts must be maintained as the tree evolves, and there will be a week where a legitimate refactor is blocked by a contract that needs editing first. Dependency inversion for the replayer is more indirection than a direct import would be, and a new reader will ask why. Every heavy interactive tool lives behind `analysis/`, so plotting during debugging means importing across a quarantine line that CI enforces on library code.

**Forecloses:** shipping an engine adapter on its own release cadence. A customer pinned to core 0.4 cannot receive a new Basilisk adapter without upgrading the whole distribution, and if two adapters ever need mutually incompatible third-party pins, we are forced into the workspace split under time pressure rather than by choice.

Second, and it is the foreclosure this record previously left unstated: **the zero-extras auditor gets `verify` and metric recomputation only.** `auditor_boundary` forbids `farsight.evidence` from importing both `farsight.engines` and `farsight.experiments.runner`, and the replayer is inverted onto an executor that only `farsight.cli` can construct — so in the very install this ADR exists to guarantee, `farsight evidence replay` has nothing to execute. Even Tier-A replay of the pure-Python link chain requires the `linkchain` engine package, and therefore a second install step. The two-hour audit path (§13, AT-9) is a *verification* path, not a re-execution path, for anyone who has not installed FarSight's own engine code, and AT-1's cross-machine replay is likewise not a zero-extras operation. Two responses are open and this record does not pick between them, because both belong to ADR-007's audit-path definition: move `linkchain` out of `engines/` so a base install can re-execute the flagship (the flagship uses no third-party engine, so this is achievable and is worth more than the boundary purity it costs), or label the replay step as requiring an extra and say so in the shipped package instructions. What is not open is leaving it unsaid.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| One distribution with extras, rather than a multi-package workspace | 0.90 | `uv lock` cannot produce a single resolution satisfying core plus all engine extras — the observable event that makes the workspace split forced rather than optional. Also: the team passes 6 engineers, or someone outside the team writes an adapter (this trigger is legitimately open-ended rather than dated, because the workspace split stays cheap after revenue in a way the evidence-identity decisions do not). |
| `auditor_boundary` as the load-bearing contract (evidence and hashing import no engines) | 0.95 | The `auditor-install` job has to be weakened rather than fixed in order to land a legitimate feature — that is, the rule is discovered to be blocking something we actually need rather than something we merely wanted. |
| `analysis/` quarantine as the sole home for pandas and matplotlib | 0.88 | A truth-loop package needs a tabular join that is genuinely awkward without a DataFrame, twice, in the week 5-6 campaign work. Two occurrences is a design signal; one is a Tuesday. |
| Explicit in-repo adapter table rather than entry-point discovery | 0.85 | >=3 of the 8 K5 discovery interviews (end wk 6) name "we would write our own adapter" as a condition of adoption, which would make third-party packaging a product requirement rather than a hypothetical channel. |
| The base install stays light enough that the auditor path is one command | 0.80 | The `auditor-install` job exceeds **180 s** on the Linux runner, which the job already measures and which replaces the earlier non-number "a few minutes". A cold install that slow means core has quietly grown heavy dependencies, and the auditor is the one who notices. |
| Replay by dependency inversion rather than by relaxing the boundary | 0.72 | The week-8 external cold auditor (AT-9, §17) reports that being unable to re-execute a run from the base install was a friction item, or ADR-007's audit path is amended to require an extra at step 3. This is the lowest row because the design is right and its consequence for the two-hour audit was, until now, undocumented. |

## Enforcement

- **CI job `boundaries`** (first green by **week 1**, from the first commit, on both the Windows and Linux runners): runs `lint-imports` against the configuration above, which is the whole `.importlinter` file including the seven contracts owned by ADR-002, ADR-008, ADR-009, ADR-012, ADR-018, ADR-022 and ADR-025. A contract that names a package which does not exist yet is vacuously green and stays in the file, because the day the package appears is the day the rule has to already be there.
- **CI job `auditor-install`** (first green by **week 4**, when the single-run evidence package v0 exists to verify against; a reduced leg that installs with no extras and imports `farsight.evidence` and `farsight.cli` is green from **week 1**). It creates a clean virtual environment, runs `pip install .` with no extras, and executes `farsight evidence verify` against the archived fixture packages with `-W error` and an import hook that fails the job if `bsk`, `Basilisk` or `spiceypy` is imported at any point. It additionally asserts that the **installed distribution set** equals the declared base list held in `tests/unit/test_dependency_allowlist.py` (defined in ADR-014) — checking imports alone would let an installed-but-unimported compiled engine sit in the auditor's `pip list` and falsify the sentence this job exists to defend. ADR-007 contributes the fixture corpus; the job is defined once, here. It also records its own wall-clock time, which is what the 180 s revisit trigger reads.
- **`tests/unit/test_importlinter_contract_inventory.py`** (first green by **week 1**): asserts that the set of contract names in `.importlinter` equals a literal list checked into the test, so a contract cannot be silently deleted to make a red build green. Adding or removing one requires editing the test in the same commit, which is where a second dev sees it.
- **PARTIALLY MECHANIZED:** import-linter sees static imports. It does not see a module loaded through `importlib`, a plugin resolved at runtime, or a dependency that is installed and never imported — and the third of those is exactly how the auditor-boundary rule would first break in practice. Two of the three residues are covered mechanically (the `auditor-install` distribution-set assertion, and the contract-inventory test above); what remains is dynamic import, and it is covered by review-checklist item **BOUNDARY-1** ("does this change reach another package through `importlib`, an entry point, or a string-named module?"), whose sign-off lands in the `review_signoffs` list on the frozen `EvidencePackage` (ADR-000) — the row asserts the item for the tool version that produced that package, which is the version an auditor is holding.

## References

- FARSIGHT_FOUNDATION_PLAN.md §6 (repository architecture and the boundary-rule list), §3 D1, §2 (product boundary and scope-creep tripwires), §5 (engine install shapes: Basilisk `bsk` wheels with Windows supported, GMAT not pip-installable, SpiceyPy MIT with bundled CSPICE, TudatPy conda-only), §13 (audit path), §16 (offline-first), §17 (three devs; scope-cut order), §18 AT-1 and AT-9, §21 K5, "Things we must get right" items 7 and 8.
- ADR-002 (process-isolated workers; owns `worker-is-private`), ADR-003 (two-level adapter contract and refusal), ADR-006 (environment fingerprint), ADR-007 (evidence package, the zero-engine verify path, and the audit-path definition this record's second Forecloses paragraph hands back to it), ADR-012 (offline-first; owns `no-network-in-truth-loop` and the `acquire/` HTTP exemption), ADR-014 (extras, lock, and the CI jobs named above), ADR-018 (owns `geometry_is_not_an_engine`), ADR-022 (owns `no_sampler_libraries`), ADR-025 (the LLM exclusion, split out of this record).
- **PLAN AMENDMENT REQUESTED: §6** — the extras list in §6 reads "basilisk, gmat, analysis, dev". A fifth extra, `spice`, is requested: `spiceypy` bundles a compiled CSPICE, and leaving it in the base install falsifies the zero-engine auditor claim that §6, §18 AT-9 and "Things we must get right" item 7 all rest on. ADR-014 carries the concrete dependency table.
- **PLAN AMENDMENT REQUESTED: §6** — the subpackage tree in §6 does not contain `acquire/`. It is requested as an addition: §16 item 1 requires that acquisition be "an explicit `farsight fetch` recording URL+hash" while the runner and verifier make zero network calls, and that separation needs a package boundary to be enforceable. `acquire/` is the only package permitted an HTTP import (ADR-012).
