# ADR-008 — Units at boundaries, SI float64 core, numerical conventions
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §8, §7 (decimal-string quantities in hashed specs), §14 items 2-4; decision D6
**Related ADRs:** ADR-001 (hashed specs carry decimal strings plus a unit, so the unit must survive canonicalization intact), ADR-002 (owns `_THREAD_ENV`, the worker environment pins every reduction guarantee below assumes), ADR-003 (each adapter owns the conversion table for its engine-native surface), ADR-006 (the determinism rules these reduction conventions serve), ADR-009 (metrics are pure functions over raw SI arrays), ADR-011 (channel files are canonical little-endian float64 with unit metadata alongside), ADR-013 (import-linter keeps the unit library out of the inner packages), ADR-014 (the astropy version is pinned like everything else), ADR-019 (the reference container fixes the BLAS and libm the bitwise reduction claims rest on), ADR-020 (the channel name, unit, dtype and shape header this ADR's unit metadata travels in)

## Context

The forcing question is narrow: does a physical quantity in FarSight carry its unit at runtime, or only at the boundary, travelling as a bare float in between? Both answers are defensible, the industry does not agree with itself, and the schema pack lands in week 1 — so it is decided once, now.

Three verified facts constrain it. **Cost:** astropy `Quantity` and Pint each cost roughly 20-100x a raw float per *scalar* operation. The MVP target is 10,000 seeded runs completing overnight (§11, §21 throughput kill). A two-order-of-magnitude tax on a scalar inner loop does not fit that budget. That figure is real, and — as the options below now say out loud — it defeats only one of the two designs it was previously used to defeat.

**Interop, which matters as much:** every engine boundary takes raw floats in engine-native units anyway. Basilisk task rates are set through SWIG-exposed attributes in nanoseconds; GMAT script fields are text in the units the script language declares (`Sat.VX` in km/s); CSPICE takes and returns doubles in km, km/s and seconds past J2000. A quantity-carrying core would spend its life being stripped at the boundary and rebuilt on the way back, and stripping is exactly where unit bugs breed — a `.to_value()` with the wrong target unit is invisible at review and silent at runtime.

**Identity forbids floats regardless:** hashed specs represent quantities as decimal strings plus a unit (ADR-001), never JSON floats. The unit concept therefore already exists at the schema layer as stably canonicalizing metadata. The only open question is how far inward it travels.

What breaks is concrete. A missing conversion in the DSOC link chain is a silently-fitted zero or a factor-of-1000 error in a decibel term — precisely the defect class the product exists to prevent, found by a domain reviewer in front of a customer (§19 risk 2). A units library in the hot loop instead turns the overnight campaign into a multi-day campaign and fires the throughput kill for no physics reason.

## Decision

**Boundary-typed, raw-core.** Units are declarative metadata on schema fields, normalized to SI at construction; nothing in the numeric core sees a unit-carrying object.

Every schema field with a physical dimension declares its unit. On an unhashed model that declaration is an annotated, astropy-backed type; on a hashed model it is the `unit` field of a `Quantity` document. Validators accept an astropy `Quantity`, a `(value, unit)` pair, or the canonical document form, and normalize at construction. Construction is the only place conversion happens.

```python
# src/farsight/schemas/common.py
from typing import Annotated
from pydantic import BaseModel, ConfigDict

class Unit:                      # declarative metadata; symbol validated against astropy at import
    def __init__(self, symbol: str) -> None: ...

Metres        = Annotated[float, Unit("m")]        # UNHASHED models only; stored as SI float64
Watts         = Annotated[float, Unit("W")]
Radians       = Annotated[float, Unit("rad")]
Dimensionless = Annotated[float, Unit("dimensionless")]

class Quantity(BaseModel):                          # the hashed wire form (ADR-001)
    model_config = ConfigDict(extra="forbid", frozen=True)
    magnitude: str                                  # decimal string, never a JSON float
    unit: str                                       # astropy-parseable symbol
    def to_si(self) -> float: ...                   # the one conversion point
```

These `Annotated[float, Unit(...)]` aliases apply to **unhashed** models only — channel metadata, runtime configuration, and the in-memory forms handed to the numeric core. No field of any hashed model is float-typed: in every model that is canonicalized and hashed (ADR-001), a physical quantity is a `Quantity` document with a decimal-string `magnitude`, and only exact-range JSON integers may be numeric. `to_si()` is the single point where a hashed `Quantity` becomes the SI float64 the core sees; it runs after validation, never during serialization.

Inside `engines/`, `metrics/`, `uncertainty/` and every numeric kernel: **raw SI float64 and numpy only**, no unit library importable (ADR-013 assembles the contract this ADR owns).

**Per-adapter conversion tables.** Each adapter owns one explicit, tested table. Conversions are data, not scattered multiplications:

```python
# src/farsight/engines/basilisk/conversions.py
CONVERSIONS = (
    Conversion(field="task_rate", native_unit="ns",    si_unit="s",     factor=1e-9),
    Conversion(field="rw_Omega",  native_unit="rad/s", si_unit="rad/s", factor=1.0),
)
# src/farsight/engines/gmat/conversions.py
# UNVERIFIED - exact GMAT field names and epoch-format identifiers confirmed at implementation
# time against the installed R2025a tree; only the km/s unit convention is verified today.
CONVERSIONS = (
    Conversion(field="Sat.VX",    native_unit="km/s",  si_unit="m/s",   factor=1e3),
    Conversion(field="Sat.Epoch", native_unit="TAIModJulian", si_unit="s_past_j2000_tdb",
               factor=None, transform="tai_mjd_to_tdb_sec"),   # non-multiplicative: named function
)
```

Every row is round-trip tested against an independently written expected value. A field read or written without a table row is a contract-test failure, not a runtime surprise.

**Channel metadata carries units.** Each `.npy` channel ships a `(name, unit, dtype, shape)` header (ADR-011, ADR-020), so `analysis/` re-hydrates quantities for humans without the truth loop ever touching one.

**Debug-mode shadow computation.** A runner flag `--shadow-units` re-executes small N with a quantity-tracked shadow of the same computation and reports dimensional inconsistencies. Its limit is absolute: never in the production loop, never in an evidence package. It is a debugging instrument for the week a link-budget term looks wrong.

**Tolerance conventions.** Every comparison declares absolute *and* relative tolerance with a one-line rationale comment on the same or preceding line. Where a discretization parameter exists, a **convergence-order assertion** is preferred over a single-point tolerance: halve the step, assert error drops by about `2^p`. Order assertions are strictly stronger — they fail a wrong-but-close implementation that any point tolerance passes — and §14 already commits to one for fixed-step RK4 against `prop2b`.

**Reductions.** Every aggregation over runs iterates in sorted `run_index` order with compensated summation (`math.fsum`, or Neumaier where a streaming form is needed). Naive `sum()` and bare `numpy.sum` are banned in the truth loop: FarSight's own arithmetic must not be the weak link in a Tier-A claim (ADR-006).

**Environment pins, set by every worker before the numeric stack imports:** the canonical list is `_THREAD_ENV` in `farsight/engines/worker.py` (ADR-002) — `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS` and `VECLIB_MAXIMUM_THREADS` all at `1`, plus `TZ=UTC`, `LC_ALL=C`, `LANG=C`, `PYTHONHASHSEED=0`. Nothing FarSight compiles is built with `-ffast-math`, and CPU model plus ISA flags are recorded in the environment fingerprint. This ADR does not restate the list; ADR-002 owns it.

**Review sign-offs are records, not norms.** The one residue this record cannot mechanize (NUM-1 below) is recorded as a row in the `review_signoffs: list[{checklist_item_id, reviewer, date}]` field on the frozen `ExperimentDesign` and `EvidencePackage`. We cannot mechanize whether a tolerance rationale is true; we can mechanize that a named human asserted it, on a date, inside a hashed document.

## Options considered

### Option 1a — Per-scalar quantities everywhere, core included — REJECTED
Wrap every scalar in an astropy `Quantity` and let dimensional errors become impossible rather than merely tested-for. This is what a physicist writing a one-off analysis reaches for. Rejected on cost alone: 20-100x per scalar operation is fatal at 10k-run scale, would fire the throughput kill for no physics reason, and cannot be optimized out later without rewriting every kernel. Two sentences is all this version deserves, and it is listed separately so that the cost figure is not mistaken for an argument against the version below.

### Option 1b — Array-level `Quantity` in `metrics/` and `linkchain/` — REJECTED
This is the competent version and it was previously not considered. One unit-carrying wrapper around an entire numpy channel array: the unit check is O(1) per array operation regardless of array length, the arithmetic underneath is the same BLAS call, and the overhead is microseconds per operation rather than per element. This is how astropy is actually used in performance-sensitive code. **The 20-100x scalar figure is true and completely irrelevant to this option**, and it would be dishonest to reuse it here.

More damagingly for the chosen design: Option 1b *would* deliver the structural dimensional guarantee that this record's Forecloses section gives up. Dimensional correctness inside `metrics/` and `linkchain/` would be a property of the type, not of our test coverage, and the honest sentence in front of an auditor would be the strong one. This option has to be defeated on its own terms, not waved away on cost.

It is rejected on three grounds, each of which survives the steelman.

It does not survive the engine boundary. Basilisk takes SWIG-exposed doubles, GMAT takes text fields in script-native units, and CSPICE takes and returns raw doubles. Every engine call still strips to a raw float in an engine-native unit and rebuilds on return. The wrapper protects the middle and leaves the seams untouched, and the seams are where the conversion bugs actually live: each `.to_value(unit)` is a silent choice of target unit that no wrapper checks. We would pay for a guarantee at exactly the place we were already safe and keep the exposure at exactly the place we are not.

It makes reduction order and dtype implicit inside a wrapper, at the one place ADR-006 forbids implicitness. A `Quantity`-level reduction dispatches to numpy's pairwise summation in an order the wrapper chooses, and a unit conversion inserts a multiply whose placement relative to the accumulation is a library implementation detail. Tier A is a *bitwise* claim. A bitwise claim mediated by a wrapper we do not control is a claim about that library's version, not about our arithmetic, and it would move a golden-hash dependency from our code into a third-party release cycle.

And it does not preserve the compensated-summation discipline this ADR mandates. `math.fsum` takes an iterable of floats; there is no unit-preserving equivalent. Every compensated reduction would strip to floats and rebuild — precisely the pattern the wrapper was adopted to eliminate — so the wrapper would be absent from the arithmetic that most needs checking.

What we lose by rejecting it is stated in Forecloses as a chosen trade, not as an unavoidable limitation.

### Option 2 — Pint instead of astropy — REJECTED
Pint is the better general-purpose engineering units library: richer registry, better non-multiplicative handling, no astronomy baggage. If FarSight were a generic engineering tool it would win. Rejected because astropy is already a required dependency for reasons that do not go away — §14 mandates a SPICE-versus-astropy station-elevation cross-check as an independent implementation of the frame and time-system math, the highest-value analytical anchor in the suite. Pint would add a second registry for zero capability we need.

### Option 3 — Both libraries, each in its natural domain — REJECTED OUTRIGHT
No steelman survives. Two registries mean two parsers for `"km/s"`, two definitions of dimensionless, and a conversion layer between them that is itself a unit-bug factory whose discrepancies hide inside a library boundary nobody reads. Worse than having no unit library at all.

### Option 4 — Bare suffix conventions only (`range_m`, `power_w`) — REJECTED as the mechanism
Zero dependency, zero runtime cost, instantly readable, and what most flight-software codebases actually do. Rejected as the mechanism because nothing checks it: a suffix is a comment, and `range_km` assigned from a metres-valued expression compiles, runs, ships, and produces a plausible wrong answer. FarSight cannot sell dimensional rigour enforced by hope. The convention is nonetheless **adopted as house style inside the raw-float core**, where it is the only signal available and costs nothing.

### Option 5 — Boundary-typed, raw SI float64 core — CHOSEN
Machine-checkable where data enters and where it is hashed, free where it is expensive, every conversion concentrated into per-adapter tables testable against independently computed values, and reduction order and dtype explicit at every line that matters to a Tier-A claim.

## Consequences

**Buys us:** dimensional errors caught at construction and at every engine boundary by tests rather than review; a hot loop with no per-operation overhead, keeping the overnight 10k-run target reachable; one hashable quantity representation that canonicalizes without float ambiguity; conversion logic that is enumerable, reviewable and diffable per adapter; explicit reduction order and dtype at every point a Tier-A hash depends on them; and clean unit re-hydration for human-facing analysis without contaminating the truth loop.

**Costs us:** an unprotected middle. Once a value is a bare float in `engines/` or `metrics/`, only naming discipline and tests stand between us and a units bug — we have traded a construction-time guarantee for a test-time one, and the size of that middle grows with every metric we write. Every adapter carries a conversion table that must track upstream engine changes. And `--shadow-units` is a second numeric path that must be kept honest or deleted.

**Forecloses:** we give up the structural dimensional guarantee that Option 1b would have delivered inside `metrics/` and `linkchain/`. This is a trade we chose, not a limitation the problem imposed, and the honest sentence in front of an auditor is the full one: *we could have had dimensional correctness by construction in the pure-Python parts of the numeric core, and we declined it to keep reduction order and dtype explicit and to keep compensated summation available.* What we can claim is "checked at boundaries, tested inside", which is weaker, and in an assurance or certification context that difference is the whole conversation.

Retrofitting quantities into the core later means rewriting every kernel and every metric function, so the decision is effectively permanent even though the reasoning is a trade. We also foreclose accepting mixed-unit arrays anywhere, so any future engine with a natively quantity-typed Python surface gets an adapter-level unpacking layer rather than a direct binding.

## Confidence and revisit triggers

This record decides five separable things. The core boundary decision is safe; the rejection of array-level quantities is a genuine close call and is scored as one.

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Boundary-typed, raw SI float64 core rather than per-scalar quantities (Option 1a) | 0.90 | The week-4 profile of the first link-chain campaign shows the numeric core is not the bottleneck — for example subprocess spawn and import dominate, which ADR-002 flags as plausible — which removes the performance half of the argument entirely. |
| Rejecting array-level `Quantity` in `metrics/` and `linkchain/` (Option 1b) | 0.72 | Either of: a dimensional defect reaches an evidence package by the week-8 external audit despite the boundary tests, which is direct evidence the unprotected middle is too large; or the week-5 golden-hash work shows we are not in fact depending on reduction order in `metrics/` anywhere, which removes the second of the three defeating grounds. |
| astropy rather than Pint | 0.85 | The SPICE-versus-astropy elevation cross-check (§14 item 3) is replaced or dropped by the end of week 2, at which point astropy stops being a required dependency for an independent reason and the choice is re-made on its own merits. |
| Sorted-order compensated reductions in the truth loop | 0.92 | K3 (end wk 3) fails on a reduction-order difference, or passes only because a reduction was quietly exempted; either says the discipline is not doing what it claims. |
| `--shadow-units` earns its maintenance cost | 0.60 | It has found nothing by the week-7 DSOC hardening pass. The response is deletion, not neglect: a second numeric path that nobody trusts is worse than none. |

An additional trigger applies to the record as a whole: an engine lands whose Python surface is natively quantity-typed, which points the strip-and-rebuild argument the other way and reopens Option 1b for that adapter specifically.

## Enforcement

Each item states the week by which it can first be green.

1. `test_schema_units_complete` (unit tier, first green by week 1): walks every Pydantic model in `farsight.schemas` and fails on (a) any float-typed field on a **hashed** model — a physical quantity there must be a `Quantity` (ADR-001 Enforcement 3), and (b) any float-typed field on an unhashed model lacking either a `Unit(...)` annotation or an explicit `Dimensionless` marker. A physically meaningful field cannot merge without declaring its unit.
2. `import-linter` contract `no-units-lib-in-core` (owned by this ADR, shipped in the `.importlinter` file ADR-013 assembles; first green by week 1): forbids `astropy`, `astropy.units` and `pint` imports from `farsight.engines`, `farsight.metrics`, `farsight.uncertainty` and `farsight.hashing`. Permitted in `farsight.schemas`, `farsight.units` and `farsight.analysis` only.
3. `test_adapter_conversion_tables` (engine-contract tier, first green by week 4 for the link chain and week 6 for Basilisk): for each adapter, asserts every engine-native field the adapter touches appears in `CONVERSIONS`, and round-trips each row against a value computed independently in the test file rather than by importing the table. Includes the mixed-unit smoke test against a hand-computed SI reference required by §14 item 2.
4. `test_tolerance_rationale` (lint tier, first green by week 1): AST-scans the test suite and `comparison/` for calls passing `atol`, `rtol` or a `tolerance` field, failing when no `# tol:` rationale comment sits on the same or preceding line. This is the mechanical half of the tolerance-inflation kill. PARTIALLY MECHANIZED: the lint proves a rationale exists and nothing more; whether the stated reason is a real physical or numerical mechanism rather than a desired outcome cannot be linted. Review-checklist item **NUM-1**, recorded in `review_signoffs`.
5. `test_no_naive_reductions` (lint tier, first green by week 1): AST-scans `src/farsight/` outside `analysis/` and fails on builtin `sum(`, `numpy.sum` and `.sum(`; `math.fsum` and the sanctioned Neumaier helper are the only permitted forms. PARTIALLY MECHANIZED: deciding statically which axis of an array is the run axis is not possible, so the lint bans the call shapes outright and carries an explicit allowlist file for the cases where a non-run-axis reduction is correct. It produces false positives we accept, and each allowlist entry is a reviewed act with a one-line reason, covered by **NUM-1**.
6. **`test_worker_environment_pins`** (defined in ADR-002; first green by week 2): ADR-002 owns `_THREAD_ENV` and this test. It is named here because every reduction guarantee above assumes single-threaded BLAS; this record adds no second copy of the list and no second test.
7. Hypothesis suite `test_unit_roundtrip` (first green by week 1): quantity construction and `to_si()` round-trip to within 1 ULP; `Quantity` documents reject NaN, Infinity and unparseable unit symbols at validation.
8. `--shadow-units` is blocked structurally (first green by week 4, when the package builder exists): the builder refuses any run whose provenance block records `shadow_units: true`, exiting nonzero and naming the run.

## References

- FARSIGHT_FOUNDATION_PLAN.md §8 (boundary-typed raw-core decision, tolerance conventions, compensated reductions, environment pins), §7 (decimal-string quantities, NaN/Inf forbidden, canonical channel bytes), §6 (`units/` boundary converters, `analysis/` quarantine, import-linter boundary rules), §14 items 2-4 (dimensional tests, analytical anchors including the SPICE-vs-astropy elevation cross-check and the RK4 convergence-order assertion, unit round-trip property tests), §19 risk 2 (missing-term risk in the link budget), §21 (throughput kill, tolerance-inflation kill); decision D6.
- Verified fact pack (2026-08-26): astropy `Quantity` and Pint cost roughly 20-100x per *scalar* operation versus raw floats; Basilisk is driven through SWIG-exposed module attributes with task rates in nanoseconds; GMAT is driven through script fields in engine-native units and is not pip-installable; CSPICE takes and returns raw doubles; astropy is BSD-3 licensed. The per-array-operation cost of an array-level `Quantity` wrapper (Option 1b) is UNVERIFIED — it is not stated in the plan and no number is asserted here; the argument against Option 1b rests on the boundary, reduction-order and compensated-summation grounds, none of which depend on a measurement.
- PLAN AMENDMENT REQUESTED: §8 — the sentence "every schema field carries declarative unit metadata (astropy-backed `Annotated` types)" must be narrowed to unhashed models. Reason: §7 forbids JSON floats in hashed documents while §8 as written mandates float-typed annotated fields on every schema field, and both cannot hold on a hashed model. The narrowed form: on a hashed model the unit metadata is the `Quantity` document's `unit` field, and `Annotated[float, Unit(...)]` applies to unhashed models and the in-memory numeric core only.
- PLAN AMENDMENT REQUESTED: §4 and §13 — `ExperimentDesign` and `EvidencePackage` gain a `review_signoffs` list of `{checklist_item_id, reviewer, date}`. Reason: NUM-1 is otherwise a norm with no home, and the tolerance-inflation kill (§21, allowed count zero) needs the sign-off to be an auditable record rather than a habit.
- ADR-001, ADR-002, ADR-003, ADR-006, ADR-009, ADR-011, ADR-013, ADR-014, ADR-019, ADR-020.
