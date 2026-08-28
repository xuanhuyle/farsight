# ADR-026 — Model, ModelVersion, EngineBuild, and the validity envelope
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-28
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §4 (knowledge plane), §7 (validity envelope and the violation register), §14 (V&V), decision D4
**Related ADRs:** ADR-001 (identity and the freeze protocol this object obeys), ADR-004 (`EpistemicSet.members` already references this object type), ADR-003 (engine binding and capability flags), ADR-014 (`EngineBuild` is relied on there for the GMAT install), ADR-018 (a stage names the model it runs), ADR-021 (the same reference-form problem, solved there for `Referent`), ADR-023 (what a run does when it leaves an envelope)

## Context

`ModelVersionRef` already appears inside a hashed schema. ADR-004's `EpistemicSet.members: list[Quantity] | list[ModelVersionRef]` is how model-family uncertainty is enumerated — "the aggregate attrition law is clustered or it is independent-given-factors, and we do not know which" — and it is the mechanism the flagship DSOC campaign uses to enumerate atmospheric model families. ADR-014's prose records a user-installed GMAT tree "as an `EngineBuild` with install path, reported version string, and a content hash over a declared file set". Plan §4 lists `Model` and `ModelVersion` in the knowledge plane, with a validity envelope, an engine binding and a verification status.

**None of these three objects has a schema.** The reference is live in a hashed document and its referent is undefined. This is the identical hazard ADR-021 was written to close for `Referent`: a reference form that is not decided before the first freeze becomes permanent at the first shipment, because ADR-001 §16 makes the identity scheme effectively unchangeable once packages exist outside this building. Week 3 freezes designs; those designs contain `EpistemicSet[ModelVersionRef]`.

The gap is load-bearing beyond the reference form, and the architecture evolution review is what made that visible. Three separate questions the review examined — how a population of a million probes is represented, how hardware generations that differ in detectors and coding are expressed, how an aggregate law and an explicit-agent simulation compose into one evidence chain — all resolve to *the same answer*: they are different models, distinguished by their validity envelopes. That answer is only as good as the object carrying the envelope, and the object does not exist. The corpus's central principle is that physics belongs to models; the thing that principle points at has no definition.

There is a second, quieter reason to write this now. `ValidityEnvelope` exists in ADR-004 as a field on a `Belief` — the conditions under which a *parameter's* stated uncertainty applies. Plan §7 additionally promises envelopes on models, and that a run leaving one "sets validity flags and lands in the violation register". ADR-023 defines the register and the flag; nothing defines what is being left.

## Decision

**1. Three objects, all knowledge-plane, all content-addressed under ADR-001.** They are frozen, `extra="forbid"`, quantities are decimal-string `Quantity` documents, references are bare 64-hex digests (ADR-001 rule 7).

```python
# src/farsight/schemas/knowledge.py

class Model(BaseModel):
    """The stable identity of a modelled thing. Versions hang off it."""
    schema_version: int
    model_id: str                  # segment grammar (ADR-017 rule 3); a name, never dispatched on
    description: str
    domain_note: str               # one sentence: what physical question this model answers

class ModelVersion(BaseModel):
    schema_version: int
    model_ref: ContentHash         # the Model this is a version of
    version: str                   # semver; ordering is for humans, identity is the digest
    description: str
    validity: ValidityEnvelope     # decision 2 -- the reason this object exists
    binding: ModelBinding          # decision 3 -- how it is executed
    verification: VerificationStatus   # decision 4 -- what has been checked
    assumption_refs: list[ContentHash] = []   # Assumption objects (plan §4)
    source_refs: list[ContentHash] = []       # Source objects; a model with no provenance says so
    supersedes: ContentHash | None = None
    revision_reason: str | None = None        # required when supersedes is set

class EngineBuild(BaseModel):
    schema_version: int
    engine_id: str                 # "linkchain", "basilisk", "gmat", "spice"
    reported_version: str          # what the engine says about itself
    install_fingerprint: str       # 64-hex over a declared file set, or a wheel digest,
                                   # or a container digest -- the adapter declares which
    fingerprint_method: Literal["wheel_digest", "declared_file_set", "container_digest"]
    capabilities: EngineCapabilities   # ADR-003, captured as built, not as documented
```

`Model` is deliberately thin. It exists so that two versions of the same thing are recognizably the same thing, and so that a `ModelVersion` digest changing does not orphan its history. Everything that can affect a number lives on the version.

**2. `ValidityEnvelope` is promoted from ADR-004 to a shared type, and gains a subject.** The type is the one ADR-004 already defines for beliefs; this record does not redefine its fields, it widens where it may attach and states what it means on a model:

```python
class ValidityEnvelope(BaseModel):        # shared; ADR-004 uses it on Belief, this record on ModelVersion
    conditions: list[str]                 # prose, each one sentence, each independently checkable by a human
    ranges: dict[str, IntervalQ] = {}     # parameter path or declared observable -> admissible interval
    time_span: TimeSpanQ | None = None
    not_validated_for: list[str] = []     # explicit anti-claims; plan §10's model-validity example
```

On a `ModelVersion`, the envelope answers one question: **under what conditions is this model's output entitled to be believed?** For an aggregate population law that is "n >= 100 members, failures conditionally independent given declared factors, attrition below 30 % per decade"; for a link model it is the wavelength and range band plan §10 uses as its worked example; for a two-body propagator it is the regime where the neglected terms stay negligible.

`ranges` keys are parameter paths or declared observable names, so the check is mechanical wherever the quantity is one FarSight already holds. `conditions` and `not_validated_for` are prose and are not checkable by us — they are what a reviewer reads, and they are the honest home for "this was fitted to ground-test data and has never seen flight".

**3. Envelope excursions are recorded, never blocking, and never silent.** A run whose bound parameters or emitted channels leave a `ModelVersion.validity.ranges` interval is **still `ok`** (ADR-023 says this for validity flags generally, and this record is the case it was written for). What happens is: the run carries a validity flag naming the model, the parameter or observable, the admissible interval and the observed value; the flag lands in `registers/validity_violations.json`; and the package's claim statement inherits nothing automatically, because whether an excursion invalidates a conclusion is a judgement, not a rule.

Extrapolation is legitimate and constant in this domain. The product's position is not that it must not happen — it is that it must never happen *invisibly*. Refusing here would be the wrong kind of refusal: it would push teams to widen envelopes until they stop firing, which converts an honest record into a formality. The mechanical half is the check and the register row; the judgement is review-checklist item **MODEL-1**.

**4. Binding and verification status.**

```python
class ModelBinding(BaseModel):
    kind: Literal["farsight_native", "engine_native", "analytic"]
    engine_id: str | None = None      # required unless kind == "analytic"
    config_dialect: str | None = None # the dialect a StageSpec.config_ref must speak (ADR-018)
    implementation_ref: ContentHash | None = None   # for farsight_native: source digest of the module

class VerificationStatus(BaseModel):
    level: Literal["unverified", "self_consistent", "analytic_anchor",
                   "cross_model", "referent_compared"]
    evidence_refs: list[ContentHash] = []   # evidence package root hashes supporting the level
    statement: str                          # one sentence naming what was checked and against what
```

`level` is ordered by strength and is a *claim about work that was done*, so it may only be raised in a commit that adds an `evidence_refs` entry supporting it — the same discipline as re-golding (ADR-006). `analytic_anchor` means the model reproduces a closed-form result (plan §14's two-body-versus-`prop2b`, the hand-computed link budget); `cross_model` means it agreed with an independent implementation within declared tolerances (Tier C, ADR-006); `referent_compared` means it was scored against observed data (ADR-021). `unverified` is the honest default and appears in evidence packages unedited.

**5. The reference form, settled.** `ModelVersionRef` is a bare 64-hex digest of a `ModelVersion`, exactly like every other reference inside a frozen document. `refs/model/<model_id>` is a mutable alias for authoring and never appears inside a frozen object (ADR-001 rule 7). `EpistemicSet.members: list[ModelVersionRef]` therefore enumerates digests, and the display spelling `model_id@version` is resolved from the referenced object for reports — the same resolve-for-display rule ADR-021 decision 3 and ADR-009 use for referents and metrics. This is the whole of what week 3 needs from this record.

**6. What a package carries.** An evidence package ships, for every `ModelVersion` referenced by its design: the object itself under `objects/`, its envelope, its verification status, and its `EngineBuild` where the binding names one. `farsight evidence show` prints the model inventory with verification levels, because "what models produced this, and what has anyone checked about them" is the first question an external reviewer asks and it should not require a graph traversal to answer.

## Options considered

### Option 1 — Leave the objects undefined until an implementer needs them — REJECTED
The status quo, and it has one real argument: nothing in the eight-week MVP strictly requires a rich model registry, since the link chain is one FarSight-native model and Basilisk arrives as an engine rather than as a model catalogue. If the reference form were the only issue, a single sentence in ADR-004 fixing `ModelVersionRef` as a digest would discharge it at a tenth of the cost.

Rejected because the reference is already inside a hashed schema and week 3 freezes designs that use it, so "undefined" is not a neutral state — it is a permanent decision made by whoever writes the first line of code, under schedule pressure, without a record. And the second half is worse than the reference form: three separate architectural questions rest on the validity envelope, and an envelope with no object to live on becomes a comment in a YAML file.

### Option 2 — Fold model identity into `EngineBuild` — REJECTED
Tempting because for Basilisk the model *is* the engine configuration, so one object could carry both. It fails on the two cases that matter most: a FarSight-native model (the link chain) has no engine of its own, and one engine hosts many models with different envelopes and different verification histories — the whole point of enumerating model families in an `EpistemicSet` is that they share an engine and differ in physics. Merging them would make "which model" and "which build" the same question, and they have different lifetimes: an engine upgrade must not silently re-identify a model whose physics did not change.

### Option 3 — A rich model registry with typed physical interfaces (inputs, outputs, coupling ports) — REJECTED
This is what a model-based-systems-engineering tool would do, and it would enable static checking that two models are composable. It is also the universal-ontology graveyard reached by a different road: typed physical ports require FarSight to own a vocabulary of physical quantities and their meanings, which §2 tripwire 1 and ADR-003's denylist exist to prevent. The composition check we actually need is narrower and already exists — a stage's `config_ref` must satisfy its adapter's declared `config_dialect`, and channel bindings must resolve — so the ports would buy checking we have while costing the ontology we refused.

### Option 4 — Validity envelopes as free prose on the model, with no `ranges` — REJECTED
Simpler, and honest about the fact that most envelope conditions are not machine-checkable. Rejected because the checkable subset is exactly the subset that fires silently: a parameter swept by an outer scan into a region where the model was never validated is a mechanical comparison against an interval, it happens in the middle of a ten-thousand-run campaign where no human is looking, and prose cannot catch it. Keeping `ranges` mechanical and `conditions` prose puts each half where it belongs, and `not_validated_for` gives the anti-claim a home that plan §10 explicitly asks for.

### Option 5 — Three content-addressed objects, mechanical `ranges`, non-blocking excursions — CHOSEN
It closes the dangling reference before the first freeze, gives the corpus's central principle an object, and adds nothing that a single-spacecraft experiment must fill in: one `ModelVersion` with an `unverified` status and an empty envelope is a legal, honest starting point, and the fields grow as the work does.

## Consequences

**Buys us:** a defined referent for a reference form already in use, before it becomes permanent. An object for the validity envelope, which is what makes an aggregate population law, a generation's detector model and a fast surrogate honest rather than merely convenient — each states where it may be believed, and excursions are recorded rather than assumed away. A verification level that appears in every evidence package, so "what has anyone actually checked about this model" is answerable by a stranger in one command. And an inventory that makes the model-family enumeration in an `EpistemicSet` legible: a reader sees three digests resolve to three named models with three envelopes, rather than three opaque hashes.

**Costs us:** a third knowledge-plane object class to author, review and keep provenance for, in a corpus that already asks a lot of an author before the first run. Every model now carries a status field that will read `unverified` for most of the MVP, which is honest and will still look bad in a screenshot. `ValidityEnvelope` becomes a shared type with two attachment points, so a change to it touches both ADR-004's beliefs and this record's models. And `ranges` invites a false sense of coverage: a model can have a beautifully specified interval on one parameter and be badly wrong for a reason no interval expresses.

**Forecloses:** typed model composition, permanently in the MVP — FarSight will never be able to tell you that two models are dimensionally compatible before you run them, and a mismatch surfaces as an engine error or a wrong number rather than as a freeze-time refusal. It also forecloses automatic invalidation: because an envelope excursion never blocks, a package can ship a conclusion drawn entirely from extrapolated model output, correctly flagged and entirely wrong, and nothing but a human reading the violation register will stop it. That is a deliberate trade — the alternative pushes envelopes toward uselessness — but it is the failure mode this record buys.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Three separate objects (`Model`, `ModelVersion`, `EngineBuild`) | 0.85 | Authoring the DSN and DSOC model sets in wk 3-4 produces a `Model` object that never has a second version, in every case, and the indirection is pure ceremony |
| `ModelVersionRef` is a bare digest, display spelling resolved | 0.9 | None expected; this follows ADR-001 rule 7 with no exception, and ADR-021 settled the identical question |
| `ValidityEnvelope` shared between beliefs and models | 0.8 | The wk-3 link-model envelope needs a field the belief form must not have, or vice versa — at which point they are two types wearing one name |
| Mechanical `ranges` + prose `conditions` split | 0.75 | Fewer than half the envelope conditions authored by end of wk 4 are expressible as `ranges`, making the mechanical half decorative; or a `ranges` check fires so often in the wk-5 campaign that the register is noise |
| Excursions flag but never block | 0.7 | The first campaign where a majority of runs carry a validity flag: either the envelope is wrong or the study is out of scope, and a non-blocking flag is not enough to force that question. This is the shakiest row: the failure mode is a flag everyone learns to ignore |
| `VerificationStatus.level` raised only with evidence | 0.8 | A model is legitimately verified by something that is not an evidence package (a published paper, a supplier test report), and `evidence_refs` cannot hold it — likely by wk 7 with the DSOC hardware parameters |
| No typed physical interfaces | 0.9 | Two independently authored models are composed in one run and produce a silent unit or frame mismatch that a port type would have caught, twice |

## Enforcement

1. **`test_model_schema_field_set`** (unit tier, **first green by week 1**): pins the field names of `Model`, `ModelVersion`, `EngineBuild`, `ModelBinding` and `VerificationStatus` against literal lists, and asserts `VerificationStatus.level` has exactly the five members. Growing any of them is an edit a second developer sees, the same discipline as ADR-017 item 5.
2. **Freeze validator `model_refs_resolve`** (**first green by week 2**): every `ModelVersionRef` in a design — including every member of every `EpistemicSet` — is a bare 64-hex digest resolving to a `ModelVersion` in the object store; an alias spelling, an unresolvable digest or a digest resolving to a different object kind fails the freeze naming the path. This is the check that makes week 3 safe.
3. **Freeze validator `model_binding_consistent`** (**first green by week 3**): a `ModelVersion` whose `binding.kind` is `engine_native` names an `engine_id` and a `config_dialect`; every `StageSpec` (ADR-018) naming that model carries a `config_ref` whose dialect matches; a `farsight_native` binding carries an `implementation_ref`. A model that cannot be executed by the stage that names it is refused at freeze rather than at run 8,300.
4. **`test_validity_range_check`** (**first green by week 3**): given a `ModelVersion` with `ranges` and a run's bound parameters and emitted channels, the excursion check produces a validity flag with the model digest, the key, the interval and the observed value, and the run's status is unchanged. A property test asserts the check is total over the declared keys and silent on undeclared ones.
5. **`test_verification_level_evidence`** (CI, **first green by week 4**): a commit that raises a `ModelVersion.verification.level` without adding an `evidence_refs` entry fails, and the diff names the model. Lowering a level requires no evidence, because retracting a claim is always allowed.
6. **`farsight evidence show` model inventory** (**first green by week 4**): the command prints every referenced `ModelVersion` with its version, verification level and envelope summary, and `verify` fails if a referenced model object is absent from the package (ADR-007's closure rule applied to this object class).
7. **NOT MECHANIZABLE: MODEL-1** — whether a validity envelope is honest, and whether an excursion invalidates the conclusion drawn over it. A range check compares numbers to an interval somebody wrote; nothing tests whether that interval reflects what was actually validated, and nothing can decide whether extrapolating a membrane-degradation law two decades beyond its evidence is defensible in this study. Review-checklist item **MODEL-1** — *"is this envelope what was actually validated, and does this package's claim survive the excursions in its register?"* — is a second-developer sign-off recorded in `review_signoffs` on the frozen `ExperimentDesign` and repeated per evidence-grade package.

## References

- FARSIGHT_FOUNDATION_PLAN.md §4 (knowledge plane: `Model`, `ModelVersion` with validity envelope, engine binding and verification status; `EngineBuild`), §7 (provenance metadata mandatory at freeze; runs exiting an envelope set validity flags and land in the violation register), §10 (the `simple_optical_link_v1` worked example with `validated_for` and `not_validated_for`), §14 (analytic anchors, cross-engine comparison, golden provenance), §2 (no universal spacecraft ontology; scope-creep hot spot 1).
- `FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §7 C1 (this record's commissioning), §12 (population as a model with an envelope), §19 (ADR-026 in the amendment batch). The review's finding was that populations, generations and fidelity levels all resolve to model identity plus envelope, and that the object carrying both was the one thing the corpus had not written down.
- ADR-001 (identity, freeze protocol, rule 7 on reference form), ADR-003 (`EngineCapabilities`, `no-physics-in-shared-schema`), ADR-004 (`EpistemicSet.members`, `ValidityEnvelope` as first defined, `Belief` pedigree), ADR-006 (tiers; the re-golding discipline this record's verification levels borrow), ADR-009 (metric identity resolved for display), ADR-014 (`EngineBuild` for the GMAT install), ADR-017 (segment grammar for `model_id`), ADR-018 (`StageSpec.config_ref` and `config_dialect`), ADR-021 (the same reference-form problem, solved for `Referent`), ADR-023 (validity flags do not change a run's outcome).
- PLAN AMENDMENT REQUESTED: §4 — the knowledge plane's `Model`, `ModelVersion` and `EngineBuild` are specified as the schemas above, and `ValidityEnvelope` becomes a shared type attaching to both a `Belief` (ADR-004) and a `ModelVersion`. Reason: §4 names all three objects and §7 promises model-level envelopes, but no record defines them, while `ModelVersionRef` is already live inside a hashed schema — so the reference form and the envelope's home would otherwise be settled by the first implementer rather than by a record.
- PLAN AMENDMENT REQUESTED: §13 — an evidence package carries the `ModelVersion` and `EngineBuild` objects its design references, and `evidence show` prints the model inventory with verification levels. Reason: §13's manifest lists engine versions but not the models they ran, and "what has anyone checked about this model" is the first question an external reviewer asks.
- UNVERIFIED — confirm at implementation time: whether Basilisk exposes a stable, hashable identifier for the module set a given scenario instantiates, or whether an `EngineBuild.install_fingerprint` over the installed wheel is the only honest granularity available for it.
