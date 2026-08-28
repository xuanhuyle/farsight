# ADR-029 — Derived bindings and the arithmetic expression AST
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-28
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §4 (design plane; `Assumption`), §7 (identity is syntactic; no silent defaults), §9 (beliefs), decision D5
**Related ADRs:** ADR-001 (identity is syntactic, which is why duplication is undetectable without this), ADR-004 (`Belief`, `Deterministic`, pedigree levels), ADR-008 (SI float64 core; the boundary where units are checked), ADR-010 (`PredicateAST`, whose construction style this borrows and whose grammar it must not extend), ADR-017 (`ParameterDecl`, `ParameterBinding`, the materialization pattern), ADR-022 (the shortest-round-trip decimal rule for machine-produced magnitudes)

## Context

Some design inputs are not independent. The reference architecture states the case plainly — `launch interval = relay spacing / cruise speed`, and "derived values such as relay spacing and launch cadence must be computed, not duplicated manually" — and its optimization variable list carries a hard constraint of the same shape, `N_total = N_swarms × N_probes_per_swarm`. The general problem is older and much more common than interstellar corridors: any design with a geometric or budget relationship among its inputs has quantities that are consequences rather than choices.

The corpus distinguishes three of the four categories it needs. An input assumption is an `Assumption` plus a bound `Belief`. A simulation output is a channel. A derived *output* is a metric — versioned, pure, with its reduction recorded. **A derived *input* has no representation at all.** `ParameterDecl` is declared-never-valued, `ParameterBinding` binds exactly one belief, and no expression over parameters is representable anywhere in the design plane.

What makes this worse than a missing convenience is ADR-001. Identity is syntactic: `"0.220"` and `"0.22"` are different objects, and nothing in the system compares two independently authored numbers for consistency. So a design carrying `relay_spacing`, `cruise_speed` and `launch_interval` as three separate bound beliefs can be internally contradictory — the third disagreeing with the first two — and **every check we have will pass**. The freeze validator confirms each is bound exactly once; the hash is stable; the campaign runs; the evidence package verifies. This is precisely the class of silent inconsistency the product exists to prevent, sitting inside the product's own design document.

The MVP escapes because the DSOC and DSN engines compute their derived quantities internally, where they belong. The gap bites when a derived quantity shapes the *design* — another parameter's admissible range, a scenario's structure, an enumeration's cadence.

## Decision

**1. A `DerivedBinding` sits alongside `ParameterBinding` in the `UncertaintySpec`, and overspecification is refused.**

```python
# src/farsight/schemas/design.py

class DerivedBinding(BaseModel):           # frozen, extra="forbid"
    path: str                              # resolves to a ParameterDecl, exactly like a binding
    expression: ArithExpr                  # decision 2
    note: str                              # one sentence: why this is derived rather than chosen
```

`UncertaintySpec` gains `derived: list[DerivedBinding] = []`, byte-wise sorted by path. A path carrying **both** a `ParameterBinding` and a `DerivedBinding` fails the freeze, naming the path. This is the whole point: the failure mode being closed is a design that states a quantity twice and disagrees with itself, so the answer is not to reconcile the two values but to refuse the document. Refusal over silent approximation, applied to our own inputs.

**2. The expression grammar is closed, small, and a sibling of the predicate AST — not an extension of it.**

```python
ArithExpr = Annotated[
    Union[ParamLeaf, ConstLeaf, Add, Sub, Mul, Div, Neg],
    Field(discriminator="kind"),
]

class ParamLeaf(BaseModel):    kind: Literal["param"];  path: str        # a topology path
class ConstLeaf(BaseModel):    kind: Literal["const"];  value: Quantity  # decimal string + unit
class Add(BaseModel):          kind: Literal["add"];    lhs: ArithExpr; rhs: ArithExpr
class Sub(BaseModel):          kind: Literal["sub"];    lhs: ArithExpr; rhs: ArithExpr
class Mul(BaseModel):          kind: Literal["mul"];    lhs: ArithExpr; rhs: ArithExpr
class Div(BaseModel):          kind: Literal["div"];    lhs: ArithExpr; rhs: ArithExpr
class Neg(BaseModel):          kind: Literal["neg"];    operand: ArithExpr
```

Seven node kinds, two of them leaves. No functions, no powers, no transcendentals, no conditionals, no unit conversions beyond what the dimensional check performs. **An eighth kind is a decision, not a feature** — the ceiling discipline ADR-010 puts on its predicate grammar and ADR-017 on its node kinds. The moment this grammar grows a `sqrt`, it has started to become a modelling language, and modelling belongs in engines.

It is a *separate* AST from ADR-010's `PredicateAST`, deliberately. That record says twice that its grammar has no arithmetic and that a fourteenth node kind would be a decision; fusing the two would put arithmetic into the fault-trigger surface, which it closed on purpose. The two ASTs do different jobs at different times: predicates are booleans over channels at run time, derivations are quantities over parameters at freeze time.

**3. Evaluated once, at freeze, over deterministic inputs only.** Every `ParamLeaf` must resolve to a path already bound to a `Deterministic` belief. An input that is `Aleatory`, `EpistemicInterval`, `EpistemicSet` or `Unknown` fails the freeze naming the path and the kind — a deliberate MVP restriction, not an oversight, because evaluating a derivation over an uncertain input means deciding what the derived quantity's uncertainty is, and that is inference we are not going to perform silently.

Evaluation runs in SI float64 through `to_si()` (ADR-008), the result's dimension is checked against the target `ParameterDecl.unit` at the schema boundary, and the value is encoded by ADR-022's shortest-round-trip decimal rule — the same path every machine-produced aleatory draw already takes into a hashed document, so no new encoding question arises.

**4. The result is materialized into the frozen design.** The freeze writes an ordinary `Deterministic` belief at that path, carrying `pedigree.level: "derived_analysis"` (an existing member of ADR-004's `PedigreeLevel`) and the hashed expression as its derivation record. A freeze validator recomputes every derivation and refuses any disagreement. This is the same pattern as `draw_order` (ADR-017) and grouped expansion (ADR-027), for the same reason: **the hashed document contains what actually happened, and the rule that produced it, and the two are checked against each other.** A reader of a frozen design sees a number and its derivation, not a formula to evaluate.

Cycles are refused: the derivation graph must be a DAG, checked at freeze, failure naming the cycle.

**5. Growth path, named and not built.** Per-outer-point evaluation — a derivation whose inputs include an epistemic coordinate, re-evaluated at each point of the outer scan — is the natural extension and would ride the `at(point)` resolution step ADR-004 already performs. It is not built, and the restriction in decision 3 is what defers it honestly rather than by omission. The reference architecture's own case wants it eventually (cruise speed is a four-member scan, and launch interval derives from it), which is exactly why the restriction is written as a stated boundary with a trigger rather than as silence.

## Options considered

### Option 1 — Nothing; author derived quantities by hand — REJECTED
The status quo. Its real argument is that the MVP does not need this: DSN and DSOC compute their derived quantities inside the engines, and no eight-week deliverable authors an inconsistent design. Rejected because the failure it permits is invisible and permanent — ADR-001's syntactic identity means no check we have will ever notice, the resulting evidence package verifies cleanly, and the inconsistency lives in the record forever. A product whose thesis is that assumptions must be visible should not ship a design format in which two inputs can quietly contradict each other.

### Option 2 — A declared consistency assertion instead of a derivation — REJECTED
Keep both values, add an assertion that they agree within a tolerance, check it at freeze. Genuinely tempting: it is less invasive, it preserves the author's ability to state a number they care about directly, and it catches the contradiction. Rejected because it needs *the same expression AST* to state the constraint — so it costs identical schema — while permitting the duplication it checks, and it introduces a tolerance where none is warranted (how far apart may `launch_interval` and `spacing/speed` be before it is a bug?). Same price, weaker guarantee. It remains the fallback if the founder prefers to keep authored values visible.

### Option 3 — Extend ADR-010's `PredicateAST` with arithmetic — REJECTED
One grammar, one compiler, one test suite. Rejected on ADR-010's own text: "there is deliberately no arithmetic" and "a fourteenth kind is a decision to revisit, not an incremental feature". Predicates evaluate over channels during a run and gate fault triggers; derivations evaluate over parameters at freeze and produce quantities. Fusing them widens the fault-trigger surface to admit arithmetic, which that record closed deliberately, and couples two compilers whose failure modes should stay separate.

### Option 4 — A symbolic algebra dependency (sympy or similar) — REJECTED
Would give unit-aware simplification, solving, and inversion nearly free, and would let an author write the relationship once and derive any variable from the others. It is also a new non-stdlib dependency inside the truth loop, against ADR-022's whole posture of owning the numerics that determine hashed values; its version becomes part of the reproducibility surface; and unit-aware symbolic algebra is a mathematics-shaped ontology project of exactly the kind §2 warns about. Seven node kinds and a dimensional check cover the cases that matter.

### Option 5 — Closed arithmetic AST, freeze-time evaluation, materialized result, overspecification refused — CHOSEN
Makes derived inputs first-class and internally consistent, at the cost of one small grammar; keeps the hashed document explicit; and the restriction to deterministic inputs keeps the hard question (uncertainty propagation through derivations) visibly deferred rather than accidentally answered.

## Consequences

**Buys us:** a design document that cannot silently contradict itself on a derived quantity, which ADR-001's syntactic identity otherwise permits and no other check would catch. A recorded derivation next to every derived number, so a reader sees *why* a value is what it is rather than an unexplained constant with `derived_analysis` pedigree and no derivation. And the reference architecture's discipline — derived values computed, never duplicated — becomes structural rather than a convention someone has to remember at 2 a.m.

**Costs us:** a second expression AST in a corpus that already argues about grammars, with its own compiler, its own property suite and its own ceiling to defend. Freeze grows a new failure mode that will confuse people the first time — a design that was fine yesterday is refused today because someone bound a value that is now derived. And the deterministic-input restriction means the case the reference architecture actually wants (derive from a scanned cruise speed) is not yet expressible, so an author with an epistemic input still hand-authors, which is the situation this record set out to fix.

**Forecloses:** derived quantities with uncertainty, in the MVP — anything downstream of an uncertain input remains hand-authored, with all the duplication risk that entails, until decision 5's extension lands. It also forecloses inversion: the AST evaluates in one direction only, so an author who knows the launch interval and wants the implied spacing writes the second expression themselves, and nothing checks that the two are mutually consistent. And it permanently forecloses expressive derivations: no `sqrt`, no logarithm, no piecewise — so a link-budget-shaped relationship among design inputs cannot be a derivation and must be a model, which is the right answer but will not always feel like it.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| A derived-input concept is needed at all before corridor-class studies | 0.9 | Nothing; the alternative is a design format that permits silent self-contradiction |
| Materialized derivation rather than a consistency assertion (Option 2) | 0.7 | Authors in wk 5+ report that losing the ability to state a derived value directly hurts review legibility more than the duplication risk costs — the fallback is Option 2 and it is fully specified |
| Seven-node closed grammar | 0.75 | The second real derivation needs an operator outside the set, which is the moment to decide between raising the ceiling once and declaring the quantity a model output |
| Separate AST from `PredicateAST` | 0.85 | Both grammars grow toward each other over two revisions, at which point one hosted expression language deserves a fresh look — including the CEL/Starlark option ADR-010 rejected |
| Deterministic inputs only | 0.65 | The first study wanting a derivation over an epistemic coordinate, which the reference architecture's own scenario matrix guarantees. This is the shakiest row and the most likely early amendment |
| Overspecification refused rather than reconciled | 0.85 | A legitimate case appears for stating both a derived value and its derivation — most plausibly a customer quoting a contractual number alongside its computation, which is arguably Option 2's use case rather than a defect here |
| Implementation deferred to post-MVP | 0.8 | A wk-5/6 campaign needs a derived design input, which would pull the implementation into the same budget as ADR-010's predicate compiler and ADR-027's expander — the schedule risk this deferral exists to avoid |

## Enforcement

1. **`test_arith_ast_grammar`** (unit tier, **first green by week 2** as schema, evaluation later): a Hypothesis suite asserting the union has exactly seven members, that every node is a frozen Pydantic model discriminated on `kind`, that an unknown `kind` is rejected, and that the field set is pinned against a literal list. An eighth kind requires editing this test.
2. **Freeze validator `derived_no_overspecification`** (**first green by week 3**): a path bound both by a `ParameterBinding` and a `DerivedBinding` fails, naming the path and both objects. This is the check the record exists for.
3. **Freeze validator `derived_inputs_deterministic`** (**first green by week 3**): every `ParamLeaf` resolves to a path bound to a `Deterministic` belief; an aleatory, epistemic or unknown input fails naming the path and the belief kind, with a message pointing at decision 5 so the refusal reads as a boundary rather than a bug.
4. **Freeze validator `derived_dag`** (**first green by week 3**): the derivation graph is acyclic; a cycle fails naming its members.
5. **Freeze validator `derived_materialized`** (**first green by week 3**): recomputes every derivation from the frozen inputs and asserts byte equality with the materialized `Deterministic` value, including its decimal encoding under ADR-022's rule. A design whose stored value disagrees with its own expression cannot freeze.
6. **`test_derived_dimensions`** (**first green by week 3**): the expression's result dimension is checked against the target `ParameterDecl.unit` through astropy at the schema boundary (ADR-008), including the mixed-unit cases (`km / (km/s)` yielding seconds); a dimensional mismatch fails naming both sides.
7. **`test_derived_pedigree`** (**first green by week 3**): every materialized derived value carries `pedigree.level: "derived_analysis"` and a resolvable derivation record; a derived value indistinguishable from a hand-authored constant fails.
8. **PARTIALLY MECHANIZED: DERIV-1** (**first green by week 3**) — whether a quantity *should* be derived. Items 2 through 7 check that a stated derivation is consistent, dimensionally sound and materialized; nothing detects the design that hand-authors three mutually inconsistent numbers and declares no derivation at all, which is the original failure this record addresses and which no validator can see. Review-checklist item **DERIV-1** — *"is every quantity in this design that is a consequence of others declared as a derivation?"* — is a second-developer sign-off recorded in `review_signoffs` on the frozen `ExperimentDesign`.

## References

- FARSIGHT_INTERSTELLAR_REFERENCE_ARCHITECTURE_v0.1.md §4 ("Treat this as derived, not independent"), §13 (`N_total_probes = N_swarms × N_probes_per_swarm`), §18 ("Derived values such as relay spacing and launch cadence must be computed, not duplicated manually").
- FARSIGHT_FOUNDATION_PLAN.md §4 (design plane; `Assumption`), §7 (canonical serialization; syntactic identity, which is what makes duplication undetectable), §9 (pedigree levels including `derived_analysis`), §2 (no symbolic-algebra-shaped scope creep).
- `FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §4 stressor 6, §7/§8.5 (this record's commissioning; schema now, implementation post-MVP), §19.
- ADR-001 (syntactic identity; the freeze protocol), ADR-004 (`Deterministic`, `PedigreeLevel.derived_analysis`, `at(point)` resolution for the deferred extension), ADR-008 (`to_si()`, the astropy boundary check), ADR-010 (`PredicateAST` construction style and ceiling discipline; the explicit reason this is a sibling rather than an extension), ADR-017 (`ParameterDecl`, `ParameterBinding`, and the materialization pattern), ADR-022 (shortest-round-trip decimal encoding for machine-produced magnitudes), ADR-027 (the other freeze-time materialization landing in the same pass).
- PLAN AMENDMENT REQUESTED: §4 — `UncertaintySpec` gains `derived: list[DerivedBinding]`, and a path bound both directly and by derivation is refused at freeze. Reason: §4 distinguishes assumptions, outputs and metrics but has no representation for a design *input* that is a consequence of other inputs, and §7's syntactic identity means two independently authored values that contradict each other pass every check the corpus has.
- UNVERIFIED — confirm at implementation time: that astropy's dimensional arithmetic yields the expected result dimension for the compound cases these expressions will actually produce (a distance divided by a velocity, a count multiplied by a count), and that its behaviour on dimensionless intermediate results is stable across the pinned version range.
