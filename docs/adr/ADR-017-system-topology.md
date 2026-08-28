# ADR-017 — SystemTopology: node model, path grammar, and parameter binding
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §4 (knowledge plane; `SystemTopology` as the naming authority), §2 (scope-creep hot spot 1 and its tripwire), §11 (aleatory draws in sorted topology-path order), §6 (`schemas/knowledge.py` as a week 1-2 deliverable)
**Related ADRs:** ADR-000 (the escape-hatch tokens and the `review_signoffs` field this record's checklist items land in), ADR-005 (draws every aleatory value in sorted topology-path order, so this grammar fixes the draw order), ADR-010 (targets faults at topology paths and needs the `environment` rule to be writable), ADR-004 (a `ParameterDecl` is what a `Belief` binds to, and the vertex tie-break is a sorted path), ADR-020 (channel names are topology paths plus a leaf, so this grammar is also the filename grammar), ADR-001 (a topology is a frozen, content-addressed object referenced only by digest), ADR-003 (owns `no-physics-in-shared-schema`, the ontology tripwire this record is the most likely place to trip), ADR-018 (which stages of a run see which subtree), ADR-009 (metric definitions name channels, which are paths in this namespace)

## Context

Plan §4 calls `SystemTopology` "the naming authority" and §6 puts it in `schemas/knowledge.py` as a week 1-2 deliverable. Nothing in the set defines it, and four records already depend on it. ADR-010 targets faults at `path: "ground.palomar.receiver.optical_train"` and rejects any path resolving under an `environment` subtree with a validator named `FaultTargetsEnvironment` — a validator that cannot be written without a node model. ADR-004 requires every `ParameterDecl` to carry a binding and breaks vertex-selection ties by "sorted topology path". ADR-020 needs to know whether a channel name is related to a topology path. And ADR-005 draws **every aleatory value by iterating parameters in sorted topology-path order**, which is the sharp one: the grammar determines the sort, the sort determines the draw order, the draw order determines every drawn value, and every drawn value is written into a RunSpec and hashed. A grammar change is not a refactor; it is a different number in every campaign.

The forcing question is therefore narrow: **what exactly is a path, what exactly does it name, and what stops this tree from becoming a spacecraft ontology?**

That last clause is not decoration. Plan §2 lists a universal spacecraft ontology as scope-creep hot spot 1, with an explicit review tripwire — "any shared schema model containing physical quantities (mass, thrust, force model) rather than run-protocol fields (times, seeds, hashes, channels) is rejected in review" — and the plan's "Things we must get right" item 8 states the failure mode plainly: the moment a shared schema grows a `mass` field, we are building the thing that killed every predecessor. A typed node tree spanning flight and ground, authored by customers, referenced by faults and metrics, is precisely where that field arrives. ADR-003's mechanical guard against it, `no-physics-in-shared-schema`, is a field-name denylist and is already declared partial.

What breaks concretely if this is wrong: week 3-4's "belief tagging of every parameter" is unimplementable without it; `FaultTargetsEnvironment` cannot be written; and a rename after the first campaign re-hashes the knowledge plane, re-hashes every design that cites it, and moves every drawn value in any re-plan.

## Decision

**1. A `SystemTopology` is a frozen, content-addressed, mission-independent knowledge-plane document, and an experiment references exactly one.** It is referenced by 64-hex digest (ADR-001 rule 7), never by alias, from `ScenarioTemplate.topology_ref`. A `Mission` workspace (context plane) may hold an alias pointing at one, and that is the whole of the mission relationship. There is no import, include, or subtree-composition mechanism: a topology is authored as one document. Exactly one topology per experiment is mandatory, because a total order over paths is what ADR-005's draw order rests on and two namespaces have no canonical interleaving.

**2. The node model. A node is a name with children; it holds no values.**

```python
# src/farsight/schemas/knowledge.py -- all models: ConfigDict(extra="forbid", frozen=True)

NodeKind = Literal["physical", "logical"]   # exactly two members; see rule 7

class ParameterDecl(BaseModel):
    name: str                      # segment grammar (rule 3)
    unit: str                      # astropy-parseable symbol (ADR-008); "1" for dimensionless
    admissible_range: IntervalQ | None = None   # two Quantity documents; a freeze-time
                                                # rejection bound, never an input to arithmetic
    description: str               # one sentence; it is what lands in the unknown register

class ChannelDecl(BaseModel):      # ADR-020 owns everything about its content
    name: str                      # local segment; the full channel path is <node path>.<name>
    unit: str
    components: int = 1            # trailing axis width; axis 0 is always the sample axis
    component_labels: list[str] | None = None   # optional; len == components when present,
                                                # each label in segment grammar (rule 3).
                                                # The trailing axis is the sanctioned home for
                                                # per-entity state (rule 8); without labels it
                                                # is anonymous and column 42 means nothing to
                                                # an auditor. Never parsed, only displayed and
                                                # joined against records.
    code_map: dict[str, int] | None = None      # categorical channels (ADR-020)
    description: str
    conforms_to: str | None = None # optional 64-hex digest of an ObservableDef (ADR-028).
                                   # Engine-native channels stay engine-native and undeclared.

class TopologyNode(BaseModel):
    name: str                      # segment grammar
    kind: NodeKind
    description: str
    children: list[TopologyNode] = []
    parameters: list[ParameterDecl] = []
    channels: list[ChannelDecl] = []

class SystemTopology(BaseModel):
    schema_version: int
    name: str                      # a label, hashed like everything else
    description: str
    nodes: list[TopologyNode]      # the root's children; paths never include a root segment
```

Those six fields on `TopologyNode` are the whole node model, and the field set is asserted by a test against a literal list, so adding a seventh is a visible act rather than a Tuesday. (`ChannelDecl` gained `component_labels` and `conforms_to` in the same review pass; both are optional, both default to absent, and neither is a field on the node.)

`kind` is the only type information in the tree and it describes **FarSight's own protocol, never the thing**. A `physical` node denotes something whose behaviour can deviate from design intent and is therefore a legal fault target; a `logical` node is a namespace or an input grouping and is not. There is no `spacecraft` kind, no `transmitter` kind, and no attribute schema per kind. The flight/ground split that plan §4 requires is expressed by *names* the author chooses — `flight`, `ground.palomar`, `ground.table_mountain` — and DSOC's two ground stations are ordinary `physical` nodes, which is exactly the case that broke the Vehicle/Environment candidate §4 rejected.

**Reserved names, both at the root only.** `environment` is a reserved root child: if present it must be `logical`, its entire subtree must be `logical`, and it is where environmental inputs live. `run` is forbidden as a topology node name because ADR-020 reserves it as the namespace for run-protocol channels that belong to no node.

**3. The path grammar.** One grammar for node paths, parameter paths and channel paths.

```
path      := segment ( "." segment )*
segment   := [a-z] [a-z0-9]* ( "_" [a-z0-9]+ )*
```

Binding rules, all validator-enforced:

- **Lowercase ASCII only.** No uppercase, no Unicode, no hyphen, no leading or trailing underscore, no doubled underscore. Case is excluded for three reasons that each stand alone: byte order equals code-point order equals sort order; case folding has locale-dependent edge cases; and paths become filenames (ADR-020), where two names differing only in case collide on Windows and not on Linux, presenting as a Tier-B physics divergence.
- **No leading separator and no root segment.** A path is relative to the topology root. Making the topology's own name part of every path would mean renaming the topology re-hashes every fault, metric and register entry that cites it.
- **Depth is capped at 6 node segments, plus at most one leaf** (a parameter or channel local name), so a path has at most 7 segments. **Total path length is capped at 64 characters** and a segment at 32. The 64 is a filename budget, not an aesthetic: `evidence_pkg_<root8>/runs/channels/<i>/<name>.npy` is about 110 characters at the cap, leaving roughly 150 of the legacy 260-character Windows path limit for the auditor's own extraction directory.
- **No indices and no wildcards, anywhere, in any document.** A numeric suffix is permitted as *characters in a name* (`string_02`) and carries no meaning: FarSight never parses an index out of a name and never expands a pattern. A fault or belief covering N sibling components is N authored objects. This is a real cost and it is in Forecloses; the reason it is not negotiable is that a wildcard's expansion depends on the topology it is applied to, so the number of aleatory draws in a run would become a function of a document the RunSpec does not contain.
- **No Windows reserved device name** may appear as any segment: `con`, `prn`, `aux`, `nul`, `com1`-`com9`, `lpt1`-`lpt9`. The check is on every segment, not only the first, so that a future flattening of the channel directory cannot reintroduce the hazard.
- **Within a node, child names, parameter names and channel local names are pairwise disjoint.** This is what makes `resolve(topology, path)` a total function returning at most one object, with no separator ceremony distinguishing a parameter from a node.

One consumer of the grammar sits outside this record and is named here so the coupling is visible: ADR-018 gives every run stage a `stage_id` and qualifies that stage's channel names with it. ADR-020 states the rule that a `stage_id` must be a node path in this grammar, which is what makes a channel name a topology path and keeps a single namespace over parameters, channels and fault targets.

**Sort order is byte-wise over the full path string**, not segment by segment. Under the grammar the string is ASCII, so `sorted(paths)` in Python is byte-wise, and `LC_ALL=C` is already pinned in every worker (ADR-008, ADR-002). One consequence is worth stating because a reader will otherwise assume the opposite: `.` (0x2E) sorts before digits and before `_` (0x5F), so `link` precedes `link.margin` precedes `link_x`. That ordering is arbitrary but it is *fixed*, which is the only property that matters.

**4. Parameters attach to exactly one node, and are declared, never valued.** A `ParameterDecl` says what a name means, what unit it is in, and what range is admissible. It never holds a number that enters arithmetic. Values arrive in the design plane as `Belief`s (ADR-004), bound by path:

```python
class ParameterBinding(BaseModel):
    path: str            # must resolve to a ParameterDecl under an active subtree
    belief: Belief       # ADR-004; carries pedigree and validity envelope

class UncertaintySpec(BaseModel):
    bindings: list[ParameterBinding]   # validator: byte-wise sorted by path, no duplicates
```

A parameter that belongs to no physical thing — an operations margin policy, a scenario-level convention — attaches to a `logical` node the author creates (`operations`). That is the point of the tree being a namespace: nothing forces a parameter to pretend to be a property of a component.

Two further binding forms exist and are specified elsewhere, both expanding or evaluating at freeze into exactly the objects above: a `GroupedBinding` covering the members of a declared enumeration or a subtree (ADR-027), and a `DerivedBinding` whose value is computed from other bound parameters rather than authored (ADR-029). Both materialize into ordinary `ParameterBinding` objects in the frozen design, so the completeness rule in decision 5, the sort order, and everything downstream of it are unchanged by either. A path may be bound exactly once by exactly one of the three routes; two routes claiming one path is a freeze failure naming the path.

**5. Binding completeness, active subtrees, and the materialized draw order.** A frozen `ScenarioTemplate` declares `active_subtrees: list[str]` (non-empty, each resolving to a node). At freeze, **every `ParameterDecl` under an active subtree must be bound exactly once**, or the freeze fails naming the path; a binding for a path outside the active subtrees also fails; and every fault target, channel reference and metric input must resolve inside an active subtree. This is how a large reusable topology can serve a small scenario without reintroducing silent defaults (ADR-001 rule 6, AT-6).

The frozen `ExperimentDesign` then carries the draw order as data:

```jsonc
"draw_order": ["flight.laser.pointing_jitter_sigma",
               "ground.palomar.receiver.optical_train_throughput"]   // sorted, aleatory only
```

`draw_order` is the byte-wise sorted list of the paths whose bound `Belief` is `Aleatory`, materialized into the hashed design. ADR-005's planner iterates *this list*, not a fresh sort. A freeze validator recomputes the sort and refuses any disagreement, so the redundancy cannot rot. The reason for materializing it is exactly the failure the gap audit named: if the order were re-derived at plan time, a change to the grammar, to normalization, or to the sort would silently move every drawn value in every campaign. Materialized, the same change moves `draw_order`, which moves `experiment_hash`, which is loud.

**6. ADR-010's validator, in full.** This is what the node model exists to make writable:

```python
def is_under(path: str, subtree: str) -> bool:
    return path == subtree or path.startswith(subtree + ".")

def validate_fault_target(topo: SystemTopology, target: TopologyTarget) -> None:
    obj = resolve(topo, target.path)                       # raises UnknownTopologyPath
    owner = owning_node(topo, target.path)
    if owner.kind == "logical":                            # environment is logical by rule 2
        raise FaultTargetsEnvironment(target.path)         # ADR-010 owns the exception name
    expected = {"parameter": ParameterDecl, "output": ChannelDecl, "function": TopologyNode}
    if not isinstance(obj, expected[target.aspect]):
        raise FaultTargetKindMismatch(target.path, target.aspect)   # ADR-023 owns the hierarchy
```

The `kind` predicate is deliberately more general than the `environment` prefix test ADR-010 describes: it also refuses a fault targeting `operations.margin_policy`, which is an input convention rather than a system behaviour. The environment case keeps ADR-010's exception name because that is the case that record names.

**7. What keeps this a namespace rather than a physics model — four mechanical rules.**

- **The node schema has no value-bearing field.** The only numbers reachable from a `TopologyNode` are `ParameterDecl.admissible_range`, which is read by exactly one caller — the freeze-time binding validator — and by nothing else, ever. `test_topology_node_field_set` pins the field list and the two-member `NodeKind` enum against a literal, so growing either is an edit a second developer sees.
- **FarSight never dispatches on a customer-supplied name.** The only operations on a topology are `resolve`, `owning_node`, `iter_parameters`, `iter_channels` and `is_under`. No code branches on a node name, a parameter name or a channel name. This is what makes the ontology question moot: a customer node called `mass_properties` is a string we sort and print, and ADR-003's `no-physics-in-shared-schema` denylist keeps its own scope, which is *Python field names in `farsight.schemas`*, not customer data.
- **The distribution ships no topology.** No default, no template, no example topology exists in `src/farsight/`. The DSOC and DSN topologies live under `experiments/` as experiment data. The day we ship a starter topology containing `spacecraft.transmitter` is the day we have shipped an ontology and started maintaining it.
- **`NodeKind` has two members and a third is a decision, not a feature.** The same ceiling ADR-010 puts on its thirteen-node predicate grammar.

**8. What the tree deliberately does not carry — four reserved positions.** These were settled during the architecture evolution review (`FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §11, §12) against a system-of-systems stress case of a thousand relay swarms launched over decades. Each is written here so that a future proposal has text to argue against rather than an accident to exploit.

- **Relationship edges are never fields on a node.** If FarSight ever needs typed relationships between nodes, they enter as a *separate* content-addressed document referencing nodes by path — never as an `edges` or `links` field on `TopologyNode`, never affecting path sort order or `draw_order`, hashed design-plane if anything numeric flows through them and context-plane if annotation-only. This matters more than it looks: adding a seventh, edge-bearing field to the node would re-hash every topology, every design citing one, and — through the sorted-path draw order — move every drawn value in every campaign. Note also that two of the four relationships a systems engineer would reach for already have homes and must not acquire second ones: `shares_common_cause` **is** `CommonCauseFactor` plus `Coupling` (ADR-010), and generation membership is a subtree name plus a `ModelVersion` (ADR-026). Connectivity — `communicates_with`, `depends_on` — is deliberately foreclosed as FarSight data by Option 3; a relay corridor's live topology is time-varying physical state, which is a model output (channels), because a static edge list in a frozen document could not represent it anyway.
- **A node may denote an ensemble, and FarSight cannot know the difference.** A node named `corridor.relay_population` with parameters (`n_probes_per_swarm`, `attrition_shape`) and a `components`-wide channel is well-formed, and nothing in this schema distinguishes it from a node denoting one transceiver — by rule 7, nothing may. Aggregate population dynamics are engine physics behind `StageSpec.config_ref` (ADR-018), the population's model family is an `EpistemicSet[ModelVersionRef]` (ADR-004, ADR-026), and its applicability bound is that `ModelVersion`'s validity envelope. **There is no `Population` entity and no `population` `NodeKind`**, now or later: `kind`'s only consumer is fault-target legality, and an ensemble node is legitimately targetable, so `physical` is already correct. The moment FarSight core defines what a population *is* beyond "a node whose model happens to be aggregate", it owns population dynamics for every customer forever.
- **Entity-granularity nodes are an anti-pattern.** The honest altitude is the granularity at which the experiment *names* things — targets faults, binds beliefs, reads channels. Swarms, hops, generations and representative units are nodes; the individuals inside a population are engine-internal, and their per-entity state is the `components` axis of one channel, not one node or one file each. A topology with a node per probe is not forbidden by a validator — it dies of the path budget, the binding-completeness rule and `bench_package_scale` — but it is the wrong shape, and week-3 authors should not establish it as practice.
- **Fleet structure never becomes a schema object.** No `Population`, `Generation`, `Swarm`, `Cohort` or `Network` type enters `farsight.schemas`; a generation is a subtree name plus a `ModelVersion` plus, where its existence is uncertain, a `CommonCauseFactor` with `nature: "epistemic_existence"`. This is rule 7's ceiling applied to fleet vocabulary, and it is the specific proposal a reviewer will bring back every quarter.

**Review sign-offs are records, not norms.** The two residues below (TOPO-1, TOPO-2) are rows in the `review_signoffs` field on the frozen `ExperimentDesign` and `EvidencePackage` (ADR-000).

## Options considered

### Option 1 — No topology: parameters and channels are free-form dotted strings — REJECTED
This is what most Monte Carlo harnesses actually do. Dakota addresses variables by descriptor strings; Basilisk's own MonteCarlo Controller disperses engine-native attribute paths; nothing validates them and nothing needs to. It has zero schema, zero authoring burden, and — the genuinely strong point — it cannot grow into an ontology, because there is nothing there to grow. Rejected on three specific things it cannot do. `FaultTargetsEnvironment` has nothing to test against, so ADR-010's boundary rule reduces to a naming convention. AT-6's "no point value for a flagged unknown, and no default for it in the codebase" needs a closed set of declared parameters to quantify over. And sorting an unconstrained string set is stable only until someone writes `Link.Margin` or a trailing space, at which point the draw order moves and no validator noticed.

### Option 2 — A typed component ontology: `Spacecraft`, `Transmitter`, `GroundStation`, each with typed physical attributes — REJECTED
The strongest version is not a toy. Systems-engineering interchange models of exactly this shape exist and are used; a typed component library would make cross-mission reuse real rather than aspirational, would let a customer's existing parts list import, and — the serious argument — it is the only design from which a **matched configuration could be generated automatically**, and §19 ranks matched configuration as the number-one three-week sink in the whole plan. It is also a commercial asset in its own right: a validated component library is a thing people pay for. Rejected because a typed attribute is a physical quantity in a shared schema, which is the literal text of §2's tripwire 1, and because the plan's product boundary already refuses a universal spacecraft ontology by name and calls it the documented graveyard of this category. The narrower defeater: an ontology must be right about a domain that already spans an optical flight terminal and two observatory-class ground stations in the flagship alone, and being wrong about it is not a bug we could fix — it is a schema every frozen customer object depends on. §14.7's declared-unmatched-items list is the plan's non-ontological answer to the matched-configuration problem, and it is the one we are keeping.

### Option 3 — A directed graph rather than a tree, with links as edges — REJECTED
Honest systems are graphs. A communications link genuinely joins a flight terminal to a ground station; a power bus joins one source to many loads; a systems engineer asked to draw the topology draws a graph, not a tree, and would find our tree a distortion. Rejected because a graph gives a node more than one path, and this namespace's entire job is that a node has exactly one. With N paths per node the sort order depends on traversal, the draw order depends on the sort, and drawn values would depend on how the graph was walked — the precise dependency plan §12 outlaws and ADR-005 is built to eliminate. A link is therefore modelled as a node whose parameters name its endpoints as opaque strings, which is honest for a namespace and is not a connectivity claim FarSight can act on. What that costs is stated in Forecloses.

### Option 4 — Opaque surrogate ids as paths, with names as display metadata — REJECTED
This is stronger than it first looks and it attacks the chosen design at its weakest joint. If a parameter's identity is a generated id rather than its name, then renaming a node is free, a typo fix does not re-hash a campaign, and — decisively — the sort order that fixes the draw order no longer encodes anything a human might reasonably want to change. Every objection this record makes about renames evaporates. Rejected because the audit path is the product: §13 targets a competent outsider finishing in two hours, ADR-001 chose JSON specifically so an auditor can open a document in a text editor, and `runs/seeds_4242.json` containing `["a3f2c1...", "0.16", "urad"]` teaches that reader nothing. There is also a second answer to the rename objection, and it is not a consolation prize: a renamed parameter *is* a different declaration, and a campaign that ran against the old name should not silently claim to be the same campaign.

### Option 5 — Derive the draw order at plan time by sorting, rather than materializing it — REJECTED
No redundancy, no second source of truth, and ADR-005's own Consequences already complains about having two sources of truth for every seed. If the sort is a pure function of the frozen design, materializing its output is storing a derived value, which is normally a smell. Rejected because the input to that pure function includes the *grammar*, the normalization rules and the comparison, and those live in code rather than in the frozen document. A silent change to any of them moves every drawn value while every hash still verifies. Materializing converts that class of change from invisible to loud, and the freeze-time equality check keeps the two from drifting.

### Option 6 — Tree of untyped named nodes, one grammar, materialized draw order — CHOSEN
Accepts authoring friction and a rename cost in exchange for a total order that is hashed rather than inferred, a fault-target predicate that is two lines, and a shared schema that contains no physics.

## Consequences

**Buys us:** one canonical path per parameter and per channel, so ADR-005's draw order, ADR-004's vertex tie-break, ADR-009's metric inputs, ADR-020's filenames and ADR-010's fault targets all sort the same way; a `FaultTargetsEnvironment` validator that is implementable in week 5 rather than aspirational; a knowledge-plane object that is genuinely reusable across missions because it holds no scenario values; and a mechanical answer to §2's tripwire 1 that a reviewer can check in a field list rather than argue about.

**Costs us:** authoring friction on day one, since every parameter needs a node, a unit and a sentence before it can be bound. A large reusable topology plus `active_subtrees` is one more concept in the freeze path. The distribution ships no starter topology, so every customer's first hour is spent naming things, and a competitor shipping a component library will demo better. And the disjointness rule means a node cannot have a parameter with the same name as a child, which will surprise someone authoring `receiver.gain` alongside a `receiver.gain` subassembly.

**Forecloses:** a rename is a re-identification. Fixing a typo in a node name after a campaign has run changes the topology hash, every design that cites it, and — because the draw order is a sorted list of paths — the drawn values of any re-plan. **A typo fix is a new campaign**, and there is no migration that preserves the old identity, by construction (ADR-001).

It forecloses set-valued targeting permanently. There is no expression meaning "all transceivers" or "every string in the array", so a fault campaign over twelve identical components is twelve authored activations, and adding the feature later would change the number of aleatory draws per run and therefore invalidate every fault-bearing campaign hashed before it.

It forecloses connectivity as data. Because the topology is a tree and links are nodes, FarSight can never answer "what is downstream of this node", cannot compute a fault-propagation path, and cannot generate a matched configuration from structure. Any such question is a customer's own analysis over names we hand back to them.

And it forecloses partial reuse. With no import mechanism, two missions sharing a ground segment hold two copies, and correcting one does not correct the other; the only shared artifact is a whole topology referenced by digest.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| The four mechanical rules keep this a namespace rather than an ontology | 0.60 | Any of: a topology authored in wks 3-4 needs a node field that is not a name, a unit or a description; `test_topology_node_field_set` is edited for any reason before K3 (end wk 3); or the wk-8 external auditor (AT-9) reads the topology as a spacecraft model. This is the lowest row in the record because it is the plan's number-one scope-creep hot spot and because a denylist plus a field-set test is a thin defence against a customer's parts list arriving as a pull request. |
| Dot separator, lowercase ASCII segments, byte-wise sort | 0.85 | The wk-2 DSN parameter-table import or the wk-3 DSOC table needs a character the grammar forbids more than twice, which would mean the grammar is being routed around by transliteration and the transliteration is now an unrecorded mapping. |
| No indices and no wildcards, in any document | 0.70 | The wk-5/6 fault campaign or the DSOC parameter table needs 4 or more sibling nodes differing only by a numeric suffix, which is the point at which authoring N activations by hand stops being discipline and starts being a transcription-error source. The fallback is not wildcards; it is a plan-time expansion recorded verbatim into the frozen design, and it must be decided before the first fault campaign is hashed. |
| `draw_order` materialized into the frozen design rather than re-derived | 0.80 | The freeze-time equality check fires on a legitimate change more than once before K5 (wk 6), meaning the two representations are drifting for real reasons and the redundancy is costing more than the silent-change class it prevents. |
| `ParameterDecl` and `ChannelDecl` nested inside `SystemTopology` rather than free-standing knowledge-plane objects (a §4 departure) | 0.75 | Two topologies authored before K5 (wk 6) need to share a parameter declaration verbatim — same name, unit, range and description — which would mean declarations want their own identity and the nesting is forcing duplication. |
| Exactly one topology per experiment, no composition or import | 0.80 | The wk-5/6 cross-engine or multi-station campaign cannot express its system in one document without copying a subtree, or the DSN and DSOC topologies share more than half their nodes, at which point copy-paste is the design rather than an edge case. |
| `kind` as the only type information in the tree, two members, carrying the fault-target predicate | 0.75 | A third kind is proposed before K5 (wk 6), or the wk-5 fault work finds a node that must be fault-targetable and is not a system component. Either says the two-member enum is a compression of something with more structure, and the honest response is a superseding record rather than a quiet third member. |

## Enforcement

1. **`test_topology_path_grammar`** (unit tier, every commit, Windows and Linux; **first green by week 1**): a Hypothesis suite over generated paths asserting that the grammar accepts exactly the language above and rejects uppercase, non-ASCII, hyphens, leading or trailing underscores, doubled underscores, leading separators, empty segments, indices in brackets, `*` and `?`, any Windows reserved device name in any segment, paths over 64 characters, segments over 32 characters, and node depth over 6. It also asserts the disjointness rule and that `resolve` is total and single-valued over a generated topology.
2. **`test_topology_sort_order`** (**first green by week 1**): asserts that Python `sorted()` over grammar-conforming paths equals byte-wise ordering of their UTF-8 encodings, on Windows and Linux, under `LC_ALL=C` and under a deliberately hostile locale; and that the order is invariant to the insertion order of the nodes that produced the paths.
3. **Freeze validator `topology_bindings_complete`** (**first green by week 2**, with the `design` schema pack): every `ParameterDecl` under an active subtree is bound exactly once; an unbound declaration, a duplicate binding, a binding outside the active subtrees, and a fault, channel or metric reference that resolves outside them each fail the freeze naming the path. This is the topology half of ADR-001's no-silent-defaults rule.
4. **`test_draw_order_frozen`** (**first green by week 2**): a design whose `draw_order` is not exactly the byte-wise sorted list of aleatory-bound parameter paths fails to freeze; and a property test asserts that permuting the authored binding list leaves `draw_order`, and therefore `experiment_hash`, unchanged. The complementary direction — that ADR-005's planner consumes this list rather than re-sorting — is covered by `ci-worker-order-invariance` (defined in ADR-006) from week 5.
5. **`test_topology_node_field_set`** (**first green by week 1**): asserts the field names of `TopologyNode`, `ParameterDecl` and `ChannelDecl` against literal lists checked into the test, and that `NodeKind` has exactly the two members `physical` and `logical`. Adding a field or a kind requires editing this test in the same commit, which is where a second developer sees it. It further asserts that `admissible_range` is read by exactly one module, the binding validator.
6. **`no-topology-in-library`** (lint tier, **first green by week 1**): no `SystemTopology` or `TopologyNode` is constructed anywhere under `src/farsight/` outside `schemas/knowledge.py`, and no `.json` or `.yaml` topology document ships inside the built distribution. This is the mechanical form of "we ship no ontology"; the fixture topologies live under `tests/` and `experiments/`, which are not packaged.
7. **PARTIALLY MECHANIZED: TOPO-2** (**first green by week 2**) — FarSight must never dispatch on a customer-supplied name. The mechanical half is an AST lint that fails on any string literal matching the path grammar with two or more segments appearing as an operand of `==`, `!=` or `in`, or as a dict-key lookup, anywhere under `src/farsight/` outside `schemas/knowledge.py`. Residue: a name that reaches a comparison through a variable, a configuration file or an f-string is invisible to it, and "this function does not depend on what the node is called" is not decidable. Review-checklist item **TOPO-2** — *"does this change give a customer-supplied topology name a meaning inside FarSight code?"* — carries it, and a TOPO-2 row is recorded per release and copied into the `review_signoffs` list of every package built by that release.
8. **NOT MECHANIZABLE: TOPO-1** — whether a topology document declares names or models a spacecraft. A field-set test constrains our schema; nothing constrains what a customer puts in it, and a node named `mass_properties` with a parameter `mass` in kilograms is well-formed and may be entirely appropriate. Review-checklist item **TOPO-1** — *"does this topology declare the names this experiment needs, and is every parameter on it one this experiment actually binds?"* — is a second-developer sign-off recorded in `review_signoffs` on the frozen `ExperimentDesign`. It is the instance-level companion to ADR-003's schema-level **PHYS-1** and does not restate it.
9. **Validator `FaultTargetsEnvironment`** (defined in ADR-010; **first green by week 5**, when `faults/` exists): this record supplies `resolve`, `owning_node`, `is_under` and the `kind` predicate the validator is written against. It does not redefine the check or its exception.
10. **Ontology tripwire `no-physics-in-shared-schema`** (defined in ADR-003; **first green by week 1**): the denylist covers Python field names in `farsight.schemas`. This record adds no rival check and relies on item 5 for the field set and item 7 for the dispatch rule. Its denylist additionally covers the fleet-structure field names rule 8 forbids — `population`, `count`, `attrition`, `survival`, `generation`, `swarm` — as *schema field names*, never as customer node names.
11. **`test_component_labels`** (unit tier, **first green by week 2**): when `ChannelDecl.component_labels` is present its length equals `components`, every label conforms to the segment grammar, and labels within one declaration are unique. Absent labels are legal and mean the axis is anonymous. The complementary rule — that a label is never parsed for meaning, only displayed and joined — falls under item 7's dispatch lint.

## References

- FARSIGHT_FOUNDATION_PLAN.md §4 (the four planes; `SystemTopology` as the naming authority, a typed node tree spanning flight and ground, replacing Vehicle/Environment which break on DSOC where two ground stations are half the system; `ParameterDecl` in the knowledge plane; the immutability invariant), §2 (product boundary; universal spacecraft ontology refused; scope-creep hot spot 1 and its review tripwire), §6 (`schemas/knowledge.py`; `schemas` imports nothing internal), §11 (aleatory values drawn in sorted topology-path order), §12 (no hashed value may depend on iteration order), §17 weeks 1-2 and 3-4 (schema pack; belief tagging of every parameter), §18 AT-6, "Things we must get right" item 8.
- Open cross-reference, not a departure: ADR-005's `runs/seeds_4242.json` example writes a parameter path as `/spacecraft/laser/pointing_jitter_sigma` — slash-separated with a leading slash. That spelling is inadmissible under this grammar, which is dot-separated with no leading separator, matching ADR-010's `TopologyTarget.path` and ADR-004's `decl: tx.pointing_jitter_sigma`. Both records are `Proposed`; the example is the thing that must move, and it is named here so the correction is not discovered by an implementer in week 1.
- ADR-000, ADR-001, ADR-003, ADR-004, ADR-005, ADR-009, ADR-010, ADR-018, ADR-020.
- UNVERIFIED — confirm at implementation time: that the Windows reserved-device-name list above is complete for the filesystems we support, and that no supported filesystem imposes a component limit below 64 characters.
- PLAN AMENDMENT REQUESTED: §4 — `ParameterDecl` becomes a component of `SystemTopology` (a field on `TopologyNode`) rather than a free-standing knowledge-plane entity, and `TopologyNode` additionally carries `ChannelDecl`s. Reason: a declaration that floats free of the tree has no path, and a path is the only thing ADR-005's draw order, ADR-010's fault targets and ADR-020's channel names can be keyed on; making the tree the sole home for declarations is what makes "the naming authority" a checkable property rather than a description.
- PLAN AMENDMENT REQUESTED: §4 — the frozen `ScenarioTemplate` gains `active_subtrees` and the frozen `ExperimentDesign` gains a materialized `draw_order`. Reason: §11 specifies the draw order in prose as "sorted topology-path order", which places the order in code rather than in the hashed record; materializing it makes a grammar or sort change visible as a hash change instead of as a silent movement of every drawn value, and `active_subtrees` is what lets a reusable topology serve one scenario without reintroducing the silent defaults §4's freeze rule forbids.
- The `review_signoffs` amendment that TOPO-1 and TOPO-2 depend on is stated once, in ADR-000's References, and is relied on here rather than restated.
- PLAN AMENDMENT REQUESTED: §4 — `ChannelDecl` gains two optional fields: `component_labels` (naming the entities behind the trailing axis) and `conforms_to` (ADR-028's observable digest). Reason: the `components` axis is the sanctioned home for per-entity state, and an unlabelled axis leaves an auditor holding `corridor.hop_link_margin.npy` unable to say which hop column 42 is, or to join it to a fault record naming that hop. Both default to absent, so the single-spacecraft case never sees them. Adding them now, while `SystemTopology` is `Proposed` and no bytes exist, is free; adding them once topologies are hashed re-identifies every topology and everything citing one.
- Rule 8 records decisions taken in `FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §11 (tree kept, relationship edges reserved to a separate document) and §12 (population is a model, not an entity), against the interstellar reference architecture as a stress case. The review's own reasoning — that a corridor's live connectivity is time-varying state no frozen document could hold — is the argument of record for Option 3's rejection standing.
