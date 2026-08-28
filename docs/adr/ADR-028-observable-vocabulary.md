# ADR-028 — Canonical observable vocabulary
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-28
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §2 (product boundary; no universal spacecraft ontology), §14 (matched-configuration declaration), decision D3
**Related ADRs:** ADR-020 (channel names and units; its Option 3 rejected a closed namespace and this record must not reverse that), ADR-017 (`ChannelDecl` carries the new field), ADR-003 (matched configuration; the ontology tripwire), ADR-006 (Tier C comparison, where conformance is consumed), ADR-009 (the definition-hashing pattern reused here), ADR-021 (comparison against referents), ADR-026 (models declare what they compute; observables declare what a channel means)

## Context

The founder feedback revises one architectural principle. The plan's rule against a universal spacecraft ontology stands, but is narrowed:

> No universal spacecraft ontology. Maintain only the minimum canonical vocabulary required for evidence and cross-engine comparison.

The corpus predates that revision, and there is a real tension to resolve rather than paper over. ADR-020 gives channels a name grammar and a unit, and its Option 3 **rejected** a closed FarSight-owned namespace list (`geometry.`, `link.`, `power.`) as "a physics ontology with a smaller word count" — correctly, since reserving namespaces forces every customer to name their nodes from our list, and ADR-017's whole design is that names belong to the author and FarSight never dispatches on them. Its Forecloses pays the cost knowingly: "Two customers computing the same link margin will hold two metric definitions with two identities, and FarSight will not ship the vocabulary that would have unified them."

But cross-engine comparison needs *some* shared semantics, and nothing in the corpus carries them. `link.margin` after which losses, referenced to what, in which frame, at which point in the chain — two engines can each emit a channel by that name, both with unit `dB`, computing different quantities, and the comparison machinery would happily difference them. ADR-003's matched-configuration declaration is the closest existing home, but it is per-comparison prose enumerating *unmatched* items, not a reusable definition a second adapter can conform to.

The resolution has to satisfy three constraints at once: the founder's directive, ADR-020's rejection of reserved namespaces, and the standing rule that FarSight owns no physics. It turns out they are compatible, because the founder asked for a *vocabulary*, and ADR-020 rejected a *naming scheme*. Those are different objects.

## Decision

**1. The vocabulary is data, not schema, and not a namespace.** A canonical observable is a content-addressed knowledge-plane object describing what a quantity means. It reserves no name, constrains no topology, and is never required.

```python
# src/farsight/schemas/knowledge.py

class ObservableDef(BaseModel):        # frozen, extra="forbid"
    schema_version: int
    observable_id: str                 # segment grammar; "link_margin", "state_of_charge"
    version: str                       # semver; identity is still the digest
    unit_dimension: str                # an astropy-parseable dimension, not a fixed symbol:
                                       # "dB" and "1" are both admissible for a ratio-like
                                       # observable, and the check is dimensional
    conventions: list[str]             # each one sentence, each independently checkable by a human:
                                       # reference point, frame, timescale, sign, what is included
    definition: str                    # what this quantity IS, in prose, length-validated
    supersedes: ContentHash | None = None
    revision_reason: str | None = None
```

**There are no numeric fields.** No default value, no admissible range, no nominal, no per-observable attribute schema, no component taxonomy. That is the line between a vocabulary and an ontology, and it is enforced mechanically below rather than promised. An `ObservableDef` says "link margin means the ratio of received power to the power required at the declared reference point, positive when the link closes, including implementation loss and excluding atmospheric loss" — and stops.

**2. Conformance is an optional declaration on a channel.** `ChannelDecl` gains `conforms_to: str | None = None`, a bare 64-hex digest (ADR-001 rule 7), defaulting to absent (ADR-017, ADR-020). A channel that declares it is claiming *this channel computes that quantity under those conventions*. Engine-native channels stay engine-native and undeclared; a single-spacecraft experiment never fills the field in; nothing anywhere requires it.

Names are untouched. A customer's channel is still `ground.palomar.link.margin` or `downlink.hdr_margin` or whatever they call it — **the vocabulary does not reserve, suggest or constrain a single name.** This is what makes it compatible with ADR-020 Option 3 rather than a reversal of it: that rejection was of a naming scheme, and this record ships none.

**3. Conformance is consumed in the comparison layer, and it informs rather than refuses.** When a `ComparisonSpec` (ADR-006, ADR-021) pairs two channels produced by different engines:

- if both declare `conforms_to` and the digests match, the comparison records that the two sides claim the same quantity under the same conventions;
- if they differ, or one is absent, **the comparison is not refused** — it proceeds and the mismatch is enumerated in the declared-unmatched-items list that ADR-003's matched-configuration declaration already requires.

Refusing would be wrong here. Comparing two engines' differently-defined quantities is sometimes exactly the experiment, and the corpus's honesty rule is that unmatched items are *declared*, not that comparison is forbidden. What must never happen is an undeclared mismatch, and that is what this closes.

The mechanical check is dimensional: a channel declaring conformance whose `unit` is dimensionally incompatible with the `ObservableDef.unit_dimension` fails at freeze. Whether the producer actually computes the defined quantity is not decidable by us, and is the sign-off residue below.

**4. The registry is small, capped, and populated late.** The distribution ships a seed set of roughly fifteen entries, drawn from the founder's list: epoch, reference frame, position, velocity, attitude, angular rate, power, state of charge, link margin, link availability, data backlog, node operational state, and a small number of mission-metric observables. **A sixteenth entry is a decision, not a feature** — the same ceiling ADR-010 puts on its thirteen predicate node kinds and ADR-017 on its two node kinds.

Contents are **deferred to Stage 3**, when GMAT lands and the first genuine cross-engine comparison exists to write them against. Authoring definitions before there is a second implementation to disagree with is how vocabularies acquire entries nobody needs. What lands now is the object, the field and the principle — because the field sits inside a hashed document and is free today.

**5. What this does not do, stated as decisions.** It defines no physical model and no relationship between observables (no "power = voltage × current"): observables are independent definitions, and arithmetic between them is a metric, which is ADR-009's. It does not make FarSight compute anything. No code path branches on `observable_id` except digest equality in comparison validation and display — ADR-017 rule 7's dispatch ban extends to it verbatim. And it is not a channel type system: a channel's dtype, shape, grid and components remain entirely ADR-020's.

## Options considered

### Option 1 — Reserved channel namespaces (`link.`, `power.`, `geometry.`) — REJECTED
The reading of the founder's directive a hurried implementer would take, and the one this record most needs to foreclose. It fails at the first rung of the generality ladder: a lunar spacecraft's author is forced to name nodes from our list, ADR-017's "the customer names their own nodes" rule dies, and every TOPO-1 review becomes an adjudication of our taxonomy. It also reverses a decision ADR-020 made on its merits. The founder asked for a vocabulary for comparison; a namespace is a vocabulary for *naming*, which is a different and much more invasive thing.

### Option 2 — Nothing; keep per-comparison prose in the matched-configuration declaration — REJECTED
The status quo, and it has a genuine argument: the unmatched-items list already exists, it is per-comparison where the semantics actually matter, and prose is what a reviewer reads anyway. Rejected because it does not accumulate. Every cross-engine comparison re-derives the same statements about what link margin means, nothing is reusable across studies or customers, and a mismatch that nobody thought to enumerate is silently absent from a list of declared exceptions — which is exactly the failure mode the declaration exists to prevent.

### Option 3 — A typed observable schema with per-observable attribute models (a `LinkMargin` type with reference-point and loss-inclusion fields) — REJECTED
Would make conventions machine-checkable instead of prose, which is a real gain. It is also the ontology arriving in the shape of a type system: per-observable attribute schemas require FarSight to own a model of each quantity's structure, the set is unbounded, and each addition is a physics decision made by us on behalf of every customer. Prose conventions plus a dimensional check keep the mechanical half where mechanization is honest.

### Option 4 — Mandatory conformance for every channel — REJECTED
Would guarantee coverage. It would also force every engine-native diagnostic channel into a vocabulary that has no entry for it, produce a long tail of junk definitions authored to satisfy a validator, and burden the single-spacecraft case with a step that buys it nothing since it has no second engine to compare against. Optional-and-absent is the honest default.

### Option 5 — Definitions as data, optional per-channel conformance, consumed in comparison — CHOSEN
Satisfies the founder's directive, preserves ADR-020's rejection intact, costs a single optional field now, and defers every judgement about contents to the point where a second implementation exists to make them against.

## Consequences

**Buys us:** a place for cross-engine semantics that accumulates instead of being re-derived per comparison, without reserving a single name. An undeclared semantic mismatch between two engines becomes a declared one, which is the difference between an honest comparison and a plausible wrong number. The founder's revised principle acquires a mechanism rather than remaining a sentence. And the field lands while `ChannelDecl` is still `Proposed` — the single cheapest moment it will ever be available.

**Costs us:** a fourth knowledge-plane object class, in a corpus that already asks a lot before the first run. A registry we must maintain, version and defend against growth, forever, with a ceiling that will be argued about. Definitions are prose, so two people can conform the same channel to the same observable and still mean different things — the dimensional check is thin protection. And there is a real risk this record is answering a question the MVP does not yet have: no cross-engine comparison exists until GMAT arrives, so the first genuine consumer is post-MVP, which is why contents are deferred and only the seam lands now.

**Forecloses:** machine-checkable convention agreement, permanently in this design — a reviewer, not a validator, decides whether two channels really compute the same thing, and a wrong conformance claim is indistinguishable from a right one to any code we will write. It also forecloses portable metric libraries in the strong sense: two customers conforming to the same observable still hold two metric definitions with two identities, because a metric is a computation and this record defines only what the inputs mean. ADR-020's Forecloses on that point is narrowed, not lifted.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Vocabulary as data, never as namespaces | 0.9 | None expected; a proposal to reserve names should be answered with ADR-020 Option 3 and this row |
| Optional `conforms_to` on `ChannelDecl` | 0.85 | The field is still unused by the end of Stage 3, meaning the seam was speculative and the honest move is to remove it before it is load-bearing |
| No numeric fields on `ObservableDef` | 0.85 | The first request for one — most likely a nominal or an admissible range, phrased as a convenience — which is the moment the object starts becoming an ontology |
| Mismatch informs rather than refuses | 0.75 | A wk-5+ cross-engine comparison ships with an unnoticed mismatch that a refusal would have caught, twice; or the unmatched-items list grows so long that entries stop being read |
| ~15-entry ceiling | 0.7 | The first two genuine cross-engine comparisons need an observable outside the seed set, which is likely and is the trigger to decide whether the ceiling or the set is wrong |
| Contents deferred to Stage 3 | 0.8 | A pre-Stage-3 need appears — most plausibly the DSN-to-DSOC comparison wanting one shared definition of received signal power |
| Dimensional check as the only mechanical half | 0.7 | A conformance claim passes the dimensional check while being obviously wrong to a reviewer, and it happens often enough to be a pattern rather than an anecdote |

## Enforcement

1. **`test_observable_def_field_set`** (unit tier, **first green by week 2**): pins the field set against a literal list and asserts **no field is typed `Quantity`, `IntervalQ`, `float` or `int`**. This is the mechanical form of "the vocabulary carries no numbers", and it is the check that keeps this record from becoming the thing it was written to avoid.
2. **`no-observable-dispatch`** (lint tier, leg of ADR-017's dispatch lint, **first green by week 2**): no code under `src/farsight/` compares an `observable_id` to a string literal or uses one as a dict key outside display formatting and comparison validation. FarSight must not learn what link margin is.
3. **Freeze validator `conformance_dimension`** (**first green by week 3**): a `ChannelDecl` declaring `conforms_to` resolves to an `ObservableDef` present in the object store, and its `unit` is dimensionally compatible with that definition's `unit_dimension` under astropy; failure names the channel, the claimed observable and both units.
4. **`test_observable_registry_ceiling`** (**first green by week 3**): the shipped registry contains at most fifteen entries, and the test carries the literal list. A sixteenth requires editing this test, which is where the decision becomes visible.
5. **Comparison validation `conformance_declared`** (**first green when the first cross-engine `ComparisonSpec` exists**): a comparison pairing two channels whose `conforms_to` digests differ, or where one is absent, emits an unmatched-item row into the matched-configuration declaration (ADR-003). A comparison is never refused on conformance grounds; a *missing* unmatched-item row for a known mismatch fails.
6. **NOT MECHANIZABLE: OBS-1** — whether a channel that claims conformance actually computes the defined quantity. The dimensional check compares units; nothing compares meanings, and a channel computing margin before implementation loss conforms exactly as well as one computing it after. Review-checklist item **OBS-1** — *"does this channel compute the quantity this observable defines, under every one of its stated conventions?"* — is a second-developer sign-off recorded in `review_signoffs` on the frozen `ExperimentDesign`, and it is the reason conformance is a claim rather than a proof.

## References

- FARSIGHT_FOUNDER_FEEDBACK.md §10 (the revised principle: no universal spacecraft ontology, only the minimum canonical vocabulary required for evidence and cross-engine comparison; the candidate list this record's seed set is drawn from; "engine-native models remain engine-native").
- FARSIGHT_FOUNDATION_PLAN.md §2 (product boundary; the universal-ontology refusal and hot spot 1), §14 (matched-configuration declaration enumerating what could not be aligned), §17 (GMAT and cross-engine work as post-MVP), decision D3.
- `FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §7 C3 and §14, which identified the tension between the founder's directive and ADR-020 Option 3, and resolved it as vocabulary-versus-naming-scheme.
- ADR-020 (Option 3's rejection of reserved namespaces, which this record preserves rather than reverses; its Forecloses on unshared metric definitions, narrowed here), ADR-017 (`ChannelDecl` and the dispatch ban extended to `observable_id`), ADR-003 (matched configuration; `no-physics-in-shared-schema`), ADR-006 (Tier C, where conformance is consumed), ADR-009 (declarative-definition hashing, the pattern this object follows), ADR-021 (referent comparison; the other place semantics matter), ADR-026 (a model declares what it computes; an observable declares what a channel means — deliberately separate).
- PLAN AMENDMENT REQUESTED: §2 — the ontology rule is restated as the founder's revised form: no universal spacecraft ontology, and a minimum canonical observable vocabulary maintained solely for evidence and cross-engine comparison. Reason: §2 as written forbids the vocabulary the founder has now directed; the two are compatible only once "vocabulary" and "naming scheme" are distinguished, which is this record's decision 1.
- PLAN AMENDMENT REQUESTED: §7 — `ChannelDecl` gains optional `conforms_to`, and `ObservableDef` joins the knowledge plane. Requested jointly with ADR-017's `component_labels` amendment, since both land on the same schema in the same pass.
- UNVERIFIED — confirm at implementation time: that astropy's dimensional comparison behaves as required for decibel-referenced units, which is the exact case the first link-margin observable will exercise, and which ADR-020 already flags as unverified for unit parsing generally.
