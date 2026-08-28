# ADR-027 — Declared scenario enumerations, group addressing, and factor-coupled parameters
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-28
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §4 (`ScenarioTemplate`), §9 (shared latent variables as the mechanism for epistemic and common-cause dependence), §10 (fault model), §11 (draw order), decision D7, D8
**Related ADRs:** ADR-004 (`sampling_scope` lives there; the hyperparameter form extends its `Distribution`), ADR-005 (draw order and the identity chain this record must not disturb), ADR-010 (fault targets, couplings, trigger anchors), ADR-017 (the path grammar, the no-wildcards rule, and the freeze-time expansion its confidence table names as the fallback), ADR-022 (draw order within a run; correlation groups), ADR-001 (everything here is materialized into a frozen document)

## Context

Three defects in the Proposed corpus share one cause, and the architecture evolution review found all three independently before noticing they were the same problem.

**First, `sampling_scope` has a dangling referent.** ADR-004 declares `Aleatory.sampling_scope: Literal["per_run", "per_pass", "per_experiment"]` and ADR-022 says `per_pass` "draws one per declared pass in the scenario, in pass order". **No record defines how a scenario declares a pass.** `ScenarioTemplate` carries `epoch_start`, `topology_ref`, `active_subtrees`, `sample_grid` and `emitted_channels`, and nothing else. So the member is unimplementable as written, and week 1-2 is when `belief.py` gets built. It is also the one place a mission-shape noun has leaked into the bottom of the schema stack: "pass" is comms-mission vocabulary sitting in the type every belief-bearing document contains.

**Second, faults and beliefs over N sibling components are N authored objects.** ADR-017 is right to forbid wildcards — a pattern's expansion would depend on a document the `RunSpec` does not contain, making the number of aleatory draws a function of the topology and destroying the property that a run's draws are a pure function of its frozen spec. But its own confidence table names both the cost and the fix: the fallback "is not wildcards; it is a plan-time expansion recorded verbatim into the frozen design, and **it must be decided before the first fault campaign is hashed**." The first fault campaign is weeks 5-6 of the MVP. A common-cause factor over a hundred sibling components is a hundred hand-authored `Coupling` objects today, which is past the transcription-error threshold at the 100-satellite rung of the generality ladder and absurd at the corridor rung.

**Third, ADR-004 promises a mechanism it has no schema for.** Its Decision states that "epistemic and common-cause dependence uses shared latent variables that appear as outer coordinates, the same mechanism ADR-010 uses for `CommonCauseFactor`", and its sampling plan carries `outer.latent_factors`. But the only coupling schema in the corpus reaches **fault activations only** (`Coupling.modulates: hazard_rate | magnitude | duration`), and `Distribution.params` admits `Quantity | EpistemicInterval | EpistemicSet` and nothing else. There is no way for a latent factor to reach an ordinary parameter. The flagship survives because DSOC's weather factor couples into fault activations, but two ordinary parameters sharing one epistemic coordinate — a dust density affecting several link terms, a seasonal regime affecting two sites — cannot be authored at all.

The common cause: **the corpus has no way to name a recurring structure in a scenario and address it.** Passes, hops, deployment waves, wake windows, sibling components and shared latent conditions are all "a named set of things this scenario contains", and every one of the three defects is a consequence of there being no such concept.

## Decision

**1. A `ScenarioTemplate` may declare named enumerations, and they are run-protocol data.**

```python
# src/farsight/schemas/design.py

class EnumerationMember(BaseModel):        # frozen, extra="forbid"
    name: str                              # segment grammar (ADR-017 rule 3); unique in its group
    epoch: Epoch | None = None             # ADR-015; for time-shaped groups (passes, waves)
    window: TimeWindow | None = None       # for members that span an interval
    nodes: list[str] = []                  # topology paths this member denotes, if any

class ScenarioEnumeration(BaseModel):
    name: str                              # segment grammar; unique in the scenario
    description: str
    members: list[EnumerationMember]       # non-empty; byte-wise sorted by member name
```

`ScenarioTemplate` gains `enumerations: list[ScenarioEnumeration] = []`, byte-wise sorted by group name. The members carry **names, epochs, windows and topology paths — and nothing else.** No masses, no rates, no physical quantities of any kind: an enumeration says *what recurring things this scenario has and when they happen*, which is the same category of information as the sample grid. That is what keeps it clear of the plan's §2 ontology tripwire, and the enforcement below makes it mechanical rather than a promise.

A pass list is one such group. So is a set of relay hops, a set of deployment waves, a set of wake windows, and a set of representative units. FarSight never dispatches on a group's name (ADR-017 rule 7 applies unchanged); it only counts members, orders them and resolves their epochs.

**2. `sampling_scope` gains a group form and loses the mission noun.**

```python
SamplingScope = Literal["per_run", "per_experiment"] | PerGroup

class PerGroup(BaseModel):
    per_group: str                         # names a ScenarioEnumeration in this scenario
```

`per_pass` is retired. A parameter that previously wanted it declares `{"per_group": "passes"}` against a scenario declaring a `passes` enumeration, and the draw count is `len(members)`, taken in member order. This gives the old member its missing referent, removes comms vocabulary from `belief.py`, and generalizes to per-hop, per-wave and per-window draws without a further schema change. `per_run` and `per_experiment` are unchanged, and a scenario that declares no enumerations can only use those two — which is every single-spacecraft experiment.

**3. Group addressing for faults and beliefs, expanded at freeze and recorded verbatim.**

An author may write one grouped object; the freeze writes out the individual ones. Nothing pattern-shaped ever survives into a hashed document.

```python
class GroupTarget(BaseModel):              # design plane, authoring form
    over: str                              # a ScenarioEnumeration name, or a subtree path
    kind: Literal["enumeration", "subtree"]
    # for "subtree": the members are the nodes N where is_under(N, over) and N has the
    # named ParameterDecl / is a legal fault target -- resolved with ADR-017's own predicates,
    # which are the only selectors permitted. There is no pattern language.
```

`FaultCampaign` gains `group_activations: list[GroupedActivation] = []` and `UncertaintySpec` gains `group_bindings: list[GroupedBinding] = []`. At freeze, each is expanded into ordinary `FaultActivation` / `ParameterBinding` objects that are **materialized into the frozen design in full**, exactly as `draw_order` is (ADR-017 decision 5) — the third use of that pattern. A freeze validator recomputes the expansion and refuses any disagreement. Consequently the frozen record is fully enumerated, the draw count and `draw_order` are unchanged in kind, `RunSpec` pinning is untouched, and ADR-005's addressing does not move. The authoring form is convenience; the hashed record is explicit.

Two supporting fields. `FaultActivation` gains `group_id: str | None = None`, set by the expander to the grouped object's name, so that ADR-009's failure signature can say "these thousand activations are one batch defect" instead of producing a distinct singleton group for every run. `Coupling` may name a `GroupTarget` in place of a single `activation_ref`, expanding the same way.

**4. Trigger anchors may name an enumeration member.** ADR-010's `AfterElapsed.of: Literal["scenario_start", "mode_entry"]` gains a third form, `{"member": "<group>.<member>"}`, resolving to that member's `epoch`. This is what makes "degradation begins ten years after *this wave's* launch" expressible without hand-computing absolute epochs outside the record; `Duration.anchor: Ref | None` (ADR-015) already anticipated non-default anchors and now has something to point at. A member used as an anchor must carry an `epoch`.

**5. A latent factor may modulate an ordinary parameter.** `Distribution.params` and `ParameterBinding.belief` admit one further form, using ADR-010's exact vocabulary rather than a second one:

```python
class FactorCoupled(BaseModel):            # a hyperparameter or a bound value
    factor: ContentHash                    # a CommonCauseFactor (ADR-010)
    law: Literal["multiplicative", "additive", "replace"]
    coefficient: Belief                    # per-target, which is how a spatial profile is expressed
    base: Belief                           # what the factor modulates
```

Resolution rides machinery that exists: an epistemic factor is an outer coordinate, `Aleatory.at(point)` already substitutes outer coordinates into unresolved hyperparameters, and `RunSpec` construction already refuses anything left unresolved. No new propagation semantics, no new evaluation order. What it buys is the ability to say that two parameters share one epistemic condition — and, with a per-target `coefficient`, that a shared condition affects different targets by different amounts, which is a discretized spatial profile without any field or mesh type entering a schema.

**6. `Coupling`'s target becomes a discriminated union, and one layer stays a validator rather than a schema wall.**

```python
CouplingTarget = Annotated[
    Union[ActivationTarget, FactorTarget, GroupTarget], Field(discriminator="kind")
]
```

The MVP freeze validator refuses a `FactorTarget` — factor-to-factor coupling remains out, exactly as ADR-010 decided, and its 0.60-confidence row and week-5 trigger continue to govern when that is revisited. The change here is only that lifting the restriction later becomes a validator relaxation instead of a schema change that would re-identify every fault catalogue in existence. Multi-layer evaluation semantics — topological ordering of factors, draw sequencing against stream 0 — are **not designed here** and remain the superseding record ADR-010 anticipates.

## Options considered

### Option 1 — Wildcards and patterns in hashed documents — REJECTED
The obvious answer, and ADR-017 already rejected it for a reason that survives every re-examination: a pattern's expansion depends on the topology, which the `RunSpec` does not contain, so the number of aleatory draws in a run would become a function of a document outside the run's own spec. That breaks the property the whole identity chain rests on. Worse, adding wildcards *later* would change draw counts and invalidate every fault-bearing campaign hashed before it — so this is not merely wrong, it is the one option that gets more expensive the longer it is left available as a temptation.

### Option 2 — Plan-time expansion, resolved when runs are generated — REJECTED
Expand at plan time rather than at freeze, keeping the design document compact. Rejected for the same reason as Option 1 in weaker form: the frozen design would then not contain what actually ran, so two planners — or one planner and a later topology edit — could produce different run sets from the same `experiment_hash`. Freeze-time expansion has none of that exposure, at the cost of larger frozen documents, which is a cost paid in bytes rather than in trust.

### Option 3 — Extend `ScenarioTemplate` with typed mission structures (`passes`, `waves`, `hops` as distinct fields) — REJECTED
More legible than a generic enumeration, and it would let validators know that a pass has a station and a wave has a launch vehicle. That is precisely the objection: each typed structure is a small ontology, the set of them is unbounded, and the first customer whose mission has a structure we did not anticipate is back to hand-authoring. One generic, name-carrying enumeration serves all of them and knows nothing about any.

### Option 4 — Solve only the `per_pass` referent, defer groups and factor coupling — REJECTED
The minimal fix: define a pass list, leave the rest. Tempting because it is a fifth of the work. Rejected because the three defects share one concept, and solving them separately means three schema changes to `belief.py`, `design.py` and `faults.py` instead of one — each a `schema_version` bump if it lands after the first freeze. The enumeration that gives `per_pass` its referent is the same object that gives group targets and trigger anchors theirs; discovering that twice is worse than deciding it once.

### Option 5 — Declared enumerations, freeze-time expansion, factor-coupled parameters — CHOSEN
One concept discharges all three defects, adds nothing a single-spacecraft experiment must declare, and keeps every hashed document fully explicit.

## Consequences

**Buys us:** `sampling_scope` becomes implementable and stops carrying a mission noun. A hundred-member common-cause campaign becomes one authored object with a materialized expansion a reviewer can read. Failure signatures survive at population scale, because `group_id` keeps a thousand co-firing activations legible as one cause instead of fragmenting every run into its own singleton group. Per-entity mission ages become expressible without epoch arithmetic done by hand outside the record. And ADR-004's promise about shared latent variables becomes true of parameters, not just of faults — which closes the gap where a team would otherwise hand-encode correlation into occurrence beliefs, the invisible-dependence rot the latent-factor design exists to prevent.

**Costs us:** a new design-plane object class, and three schemas gain members (`SamplingScope`, `Distribution.params`, `CouplingTarget`) — each a `Proposed`-stage text edit now and an identity change later, which is the entire argument for doing it in this pass. Frozen designs get larger, sometimes much larger: a thousand-member expansion is a thousand objects in the document, and that is deliberate. Authors gain a second way to say things, and a design mixing grouped and individual authoring for the same targets is harder to read than either alone. The expander is real work in weeks 5-6, in a budget that already contains ADR-010's predicate compiler.

**Forecloses:** compact frozen designs, permanently — we have chosen explicit enumeration over any form of compression in the hashed record, so a corridor-scale campaign's design document is large and there is no plan to shrink it. It also forecloses dynamic membership: an enumeration's members are fixed at freeze, so a scenario in which the set of live relays is itself a simulation outcome cannot be expressed as an enumeration, only as engine state — which is correct, and worth stating so that nobody tries.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Named enumerations on `ScenarioTemplate` as one generic concept | 0.8 | Two of the first three enumerations authored need a member field this schema lacks, meaning the generic form is not carrying its weight |
| `per_pass` retired in favour of `{"per_group": ...}` | 0.85 | The wk-3/4 DSOC campaign cannot express its pass-scoped draws in this form, or an author finds the indirection worse than the old literal |
| Freeze-time expansion, materialized verbatim | 0.8 | The first grouped campaign produces a frozen design large enough to affect freeze or verify wall time (watch it against `bench_package_scale`, ADR-011) |
| `group_id` on activations | 0.75 | Failure-signature grouping at wk 5-6 still fragments, meaning the signature needs more than the group name |
| Trigger anchors naming enumeration members | 0.8 | No campaign through wk 8 uses it, in which case it is speculative and should be cut rather than carried |
| Factor-coupled parameters (`FactorCoupled`) | 0.7 | The first use reveals that `law` plus a scalar `coefficient` cannot express a real coupling — the likely failure is a coupling that is neither multiplicative nor additive but a table, which would mean borrowing ADR-010's table form too |
| `Coupling` target as a union with one-layer enforced by validator | 0.8 | None expected before ADR-010's own wk-5 trigger fires; this record only changes where the restriction lives |
| Enumerations stay free of physical quantities | 0.7 | The first request for a member field carrying a number — and it will come, phrased as "the pass needs its elevation" — which is the moment this object starts becoming an ontology and the answer is that elevation is a channel |

## Enforcement

1. **`test_enumeration_schema`** (unit tier, **first green by week 2**): pins the field sets of `ScenarioEnumeration` and `EnumerationMember` against literal lists; asserts member names are unique within a group, groups unique within a scenario, both in segment grammar, and both byte-wise sorted in the frozen form.
2. **`no-quantities-in-enumerations`** (lint tier, **first green by week 2**): asserts no field of `EnumerationMember` or `ScenarioEnumeration` is typed `Quantity`, `IntervalQ`, `float` or `int`, and that the field set contains no name on ADR-003's physical-quantity denylist. This is what keeps decision 1's promise mechanical rather than aspirational; it is a leg of `no-physics-in-shared-schema` (defined in ADR-003) and reported under that job.
3. **Freeze validator `enumeration_refs_resolve`** (**first green by week 3**): every `{"per_group": ...}` scope, every `GroupTarget` with `kind: "enumeration"`, and every `{"member": ...}` trigger anchor names a group that exists in this scenario; an anchor names a member carrying an `epoch`. Failure names the group and the referring object.
4. **Freeze validator `group_expansion_materialized`** (**first green by week 5**): recomputes every grouped object's expansion from the frozen topology and enumerations and asserts byte equality with the materialized list; a design whose expansion disagrees fails to freeze. A property test asserts that expanding, then re-authoring the expansion individually, yields the identical `experiment_hash` — which is the statement that the authoring form is convenience and nothing more.
5. **`test_group_draw_order_stable`** (**first green by week 5**): a grouped binding and its hand-authored expansion produce identical `draw_order` and identical drawn values for a fixed root seed. This is the direct check that this record did not disturb ADR-005's identity chain.
6. **`test_factor_coupled_resolution`** (**first green by week 5**): a `FactorCoupled` hyperparameter resolves at an outer point exactly as an equivalent hand-substituted belief does; an unresolved factor at `RunSpec` construction is refused naming the parameter path.
7. **Freeze validator `coupling_one_layer`** (**first green by week 5**): a `Coupling` whose target is a `FactorTarget` is refused with a message naming ADR-010's revisit trigger, so the refusal reads as a decision rather than as a bug.
8. **PARTIALLY MECHANIZED: ENUM-1** (**first green by week 3**) — whether an enumeration describes scenario structure or has started describing the spacecraft. Item 2 catches quantities by type and by denylisted name; it cannot catch a member named `hop_0042_high_gain_pass` carrying meaning in its name, and it cannot decide whether a group of "representative units" is scenario structure or a fleet model in disguise. Review-checklist item **ENUM-1** — *"does every member of this enumeration carry only names, epochs, windows and node paths, and would this scenario still make sense if the group were renamed?"* — is recorded in `review_signoffs` on the frozen `ExperimentDesign`.

## References

- FARSIGHT_FOUNDATION_PLAN.md §4 (`ScenarioTemplate`; the design plane), §9 (shared latent variables for epistemic and common-cause dependence — the promise decision 5 makes good), §10 (fault activation triggers; common cause via shared latent factors), §11 (draw order; all randomness pre-planned), §2 (ontology tripwire, hot spot 1).
- `FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §5 findings 1, 2, 6 and 10, §7 C2, §15. The review found the three defects independently and identified the single concept underneath them.
- ADR-004 (`sampling_scope`, `Distribution.params`, `at(point)` resolution, `outer.latent_factors`), ADR-005 (draw order, the identity chain, and the reason expansion must be at freeze), ADR-010 (`Coupling`, `FaultActivation`, `AfterElapsed`, the one-layer decision and its trigger, the `law`/`coefficient` vocabulary reused here), ADR-015 (`Epoch`, `Duration.anchor`), ADR-017 (path grammar, `is_under`, the no-wildcards decision and the confidence-table fallback this record implements), ADR-022 (draw order within a run; `per_pass` as previously specified), ADR-009 (failure signatures, which `group_id` serves).
- PLAN AMENDMENT REQUESTED: §4 — `ScenarioTemplate` gains `enumerations`; `FaultCampaign` gains `group_activations`; `UncertaintySpec` gains `group_bindings`; `FaultActivation` gains `group_id`. Reason: §4 gives a scenario an epoch span and a topology reference, which cannot express the recurring structures (passes, waves, hops, sibling sets) that §9's sampling scopes, §10's trigger anchors and §10's common-cause couplings all need to address.
- PLAN AMENDMENT REQUESTED: §9 — `sampling_scope`'s `per_pass` member is replaced by a `{"per_group": "<name>"}` form. Reason: §9 and ADR-022 specify a per-pass draw against a "declared pass" that no record declares, and "pass" is mission vocabulary in the schema every belief-bearing document contains.
- PLAN AMENDMENT REQUESTED: §9 — a belief or distribution hyperparameter may be `FactorCoupled`, letting a shared latent factor modulate an ordinary parameter. Reason: §9 states that epistemic and common-cause dependence use shared latent variables, but the only coupling schema in the corpus reaches fault activations, so the stated mechanism is unavailable for parameters — including for two parameters sharing one epistemic coordinate, which is the simplest case of all.
