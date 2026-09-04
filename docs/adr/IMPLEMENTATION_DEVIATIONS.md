# Implementation deviations from accepted ADRs

[ADR-000](ADR-000-adr-process-and-template.md) forbids editing an accepted record's Decision:
reversing one means a new ADR carrying `Supersedes ADR-NNN`. That rule is right, and it leaves
a gap this file fills. Between the moment code departs from a record and the moment a
superseding record is written, the departure exists only in whichever developer's head noticed
it — and ADR-000's own Consequences section names that outcome: *"the set becomes a staleness
liability it cannot detect in itself."*

`FARSIGHT_SELF_AUDIT_ARCHITECTURE_REVIEW.md` finding D3 is the proof it had already happened:
an accepted record and the accepted implementation disagreed, the **code** was the correct one,
and nothing anywhere recorded that.

This is a ledger, not an authority. Nothing here amends an ADR. Each entry is a debt that
closes by writing the superseding record, and an entry that has sat here for a phase is a
signal that the record set is drifting faster than it is being maintained.

**This file is not a licence to deviate.** The default remains: implement what the record says.
An entry here needs a reason of the form *the record cannot be implemented as written*, not
*the record was inconvenient*.

Every entry carries: the record, the code, what differs, why, and how it closes.

Status vocabulary is ADR-030's. Nothing in this file has been externally reviewed.

---

## DEV-1 — `EpistemicCollapse.collapse_id` cannot be a content hash

**Record:** [ADR-004](ADR-004-uncertainty-belief-model.md) line 149 — `collapse_id: ContentHash`
**Code:** `src/farsight/schemas/belief.py` — `EpistemicCollapse.collapse_id: str`

**What differs.** The record types the field as a content hash. The implementation makes it a
short authored name in the ADR-017 segment grammar.

**Why.** A document that contains its own content hash is circular: the hash is computed over
the bytes, and the field is part of the bytes. The only ways to write it are to hash a document
with the field blanked — a second, undocumented canonical form, which is exactly the class of
hazard [ADR-001](ADR-001-content-addressed-identity.md) exists to remove — or to let the field
hold something that is not the document's address, which makes the name a lie.

Under ADR-001 the content address **is** the identity, and no field is needed to carry it. What
a register entry and a review comment actually need is a short handle that a human can say out
loud, which is what `claim_id` and `metric_id` are elsewhere in the corpus. The field keeps its
name so the superseding record changes a type and not an identifier.

**Consequence if this is the wrong call.** Two collapses could share a `collapse_id` across
experiments, since nothing enforces global uniqueness of a human-chosen name. Within one
experiment the freeze validator can check uniqueness; across experiments, the content address
is the identity and the name is a label. If cross-experiment citation by name is ever needed,
that is a uniqueness rule in a new record, not a return to a self-referential field.

**Closes by:** a superseding ADR restating the field as an authored segment name, most naturally
folded into the ADR-032 claim-identity record the self-audit review proposes.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-2 — `HumanIdentity` is named by ADR-004 and defined by no record

**Record:** [ADR-004](ADR-004-uncertainty-belief-model.md) line 153 — `authorizer: HumanIdentity`,
"the same identity the freeze protocol records"
**Code:** `src/farsight/schemas/belief.py` — `EpistemicCollapse.authorizer: str`

**What differs.** The record names a type. No record in the set defines it, and the freeze
protocol it points at does not exist yet.

**Why.** Inventing the type here would put an identity model in the bottom of the schema stack
on the authority of one field, and the freeze protocol and `review_signoffs` (ADR-004 line 164)
both need the same type. Whoever writes that protocol should choose its shape once.

**What is enforced meanwhile.** Non-empty after stripping, and the reserved
`MACHINE_AUTHORIZER_PREFIX` (`auto:`) marking an authorizer that is a rule rather than a person.
That prefix is not a deviation — it implements ADR-004 line 160, which permits an exploratory
auto-collapse to the midpoint while the same record requires a collapse to be signed by a human.
Without a way to say "this one was a machine, in the exploratory lane" those two sentences
contradict each other, and a contradiction nothing checks resolves in whichever direction nobody
is watching. The validator confines a machine-authored collapse to the exploratory lane.

**Consequence if this is the wrong call.** `authorizer` is a free string until the identity type
lands, so a typo produces a collapse attributed to nobody in particular and no signature binds
the authorizer to the document. The taint machinery does not depend on this field — it reads
`scope` — so the exposure is attribution, not correctness.

**Closes by:** the freeze-protocol record defining `HumanIdentity`; this field then changes type
without changing name.

**Status:** not externally expert-reviewed.

---

## DEV-3 — `CollapseScope` matches parameter paths exactly, never by subtree

**Record:** [ADR-004](ADR-004-uncertainty-belief-model.md) line 155 — `scope: CollapseScope`,
"experiment_hash + explicit parameter paths"; line 160 — `verify` recomputes taint "by
intersecting each collapse's `scope` with the parameter paths a result actually depends on"
**Code:** `src/farsight/schemas/belief.py` — `CollapseScope.covers`

**What differs.** Not a departure from anything the record states — an addition to what it
leaves open. The record says "intersecting" without saying whether a scope path covers its
subtree. The implementation matches exactly, and additionally requires the path list to be
byte-wise sorted and duplicate-free.

**Why.** Subtree semantics would be more convenient to author and would silently extend an
existing signed judgement over parameters added under that node later — authorization by
accident, on the one record in the system whose entire purpose is that a human took
responsibility for a specific conversion. The sorting requirement is ADR-017 decision 5's
reasoning applied here: two scopes covering the same parameters should be the same document and
hash alike, or the register acquires duplicates that differ only in authoring order.

**Consequence if this is the wrong call.** Authoring cost. A collapse covering a whole subsystem
lists every path rather than one prefix, and a parameter added later needs the collapse
re-signed. That is the intended cost. If it proves unworkable in practice, the fix is a declared
subtree form that expands to explicit paths at freeze — the same materialize-at-freeze pattern
`draw_order` and `GroupedBinding` already use — never a prefix match evaluated at verify time.

**Closes by:** a superseding record stating the matching rule, or confirming this one.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-7 — `StageSpec.models`: the Model-to-Run edge two records assumed and neither defined

**Record:** [ADR-026](ADR-026-model-and-engine-build.md) Enforcement 3 (`model_binding_consistent`
is written against "every `StageSpec` (ADR-018) naming that model") and its Related-ADRs line
("ADR-018 — a stage names the model it runs"); [ADR-018](ADR-018-run-composition.md) sketches
`StageSpec` with eight fields, none naming a `ModelVersion`
**Code:** `src/farsight/schemas/execution.py` — `StageModel`, `StageSpec.models`, `model_versions`

**What differs.** `StageSpec` gains a ninth field, `models: list[StageModel]`, required with no
default. This is finding D1: two accepted records contradict, and the contradiction is not a
wording difference — ADR-026's freeze validator quantifies over a field that does not exist, so
it could never have been written. "Which model produced this number" had no answer.

**Why.** The edge is the only thing that answers "which model produced this number", and ADR-026
Enforcement 3 already depends on it existing. Adding the field is what makes an accepted
validator writable rather than aspirational; leaving it out keeps two accepted records in
contradiction with each other.

**Why a list of objects rather than a `model_ref` digest.** Plural because ADR-026's own wording
is "every `StageSpec` naming that model" and one stage legitimately runs several — the DSOC link
chain has an atmospheric model and a detector model, versioned independently. Objects rather than
bare digests because of a case the review's one-line sketch does not reach: a model *family* is
enumerated as `EpistemicSet.members: list[ModelVersionRef]` (ADR-004), so **which model runs can
itself be an epistemic coordinate** that the outer scan varies. That choice cannot lower through
`ValueSource`, whose `value` is a `Quantity` and cannot hold a digest. So this is the lowering
site for it, and a bare digest here would re-open G1 for a different value type — a bound
parameter reaching a run with nothing saying which parameter it was.

`StageModel.path` is therefore required and **explicitly nullable**, which is not the same as
optional. `None` is an authored statement — *this stage runs this model because the design says
so, not because a parameter selected it* — and the author must write it. A `= None` default would
make "fixed by the design" and "nobody filled this in" the same document, which is the
hidden-default shape ADR-001 rule 6 forbids. The same reasoning makes `models` itself default-free:
an empty list is the assertion *this stage runs no separately identified model version*, true of a
SPICE geometry stage whose ephemerides are data (ADR-016 `KernelRef`) rather than a modelled
thing. That is ADR-007's register rule applied one level down — an empty register is an
assertion, a missing register is a verification failure.

**What is enforced, and what is not.** Enforced here: model lists sorted and duplicate-free so two
stages running the same models hash alike; selection paths in the ADR-017 grammar; model-selection
paths included in `parameter_paths` and `paths_reaching_stage`, so a verdict's dependence on
*which physics ran* is answerable; and ADR-017 decision 4's "bound exactly once by exactly one
route" extended across both lowering sites, so a path cannot be a value in one stage and a model
selection in another. **Not** enforced: `model_binding_consistent` itself — matching a
`ModelVersion`'s `binding.engine_id` and `binding.config_dialect` against the stage's
`provider_id` and `config_dialect` — because that requires resolving the digest and
`schemas/knowledge.py` does not exist. This schema supplies the edge the validator quantifies
over; the validator is listed by `RunSpec.unenforced_rules()` until it can run.

**An entry is a selection, not an execution.** Uniqueness is on the `(model_version_ref, path)`
pair rather than the digest alone, because two paths naming one model version is ordinary: a
grouped binding over three relay hops (ADR-027) selects a propagation model per hop, and two hops
choosing the same version is a coincidence, not a contradiction. Deduplicating on the digest
refused that legal document in the first version of this field. `model_versions()` collapses the
set for callers asking which models ran.

Three converse rules are enforced, all of them **run-scoped**, matching the value-lowering site:
one path may not select two different model versions anywhere in the run (a per-stage check would
let the geometry stage run Kolmogorov while the link stage runs von Karman under the same
coordinate, a run asserting that one choice took two values at once); one path may not be both a
value and a model selection (ADR-017 decision 4); and one model version may not appear both fixed
by the design and selected by a parameter within a stage, since those are different claims about
*why* it ran and a reader cannot be given both.

**Consequence if this is the wrong call.** `spec_hash` moves again, for the same reason and with
the same answer as DEV-6: nothing is frozen, and ADR-018's Option 3 already argues that this
class of change is nearly free now and invalidates the Tier-A golden corpus later.

**Closes by:** the superseding ADR-018 record, which the self-audit review already scopes as
carrying `StageSpec.model_ref` and `ValueSource.path` together.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-6 — `ValueSource` carries the path and origin ADR-018 sketched it without

**Record:** [ADR-018](ADR-018-run-composition.md) — `ValueSource` is sketched with two fields,
`kind` and `value: Quantity`
**Code:** `src/farsight/schemas/execution.py` — `ValueSource`, `parameter_paths`

**What differs.** Two required fields are added: `path` (the topology path the value was bound
at) and `origin` (a closed seven-member enum naming the route it arrived by). `StageSpec` and the
six composition rules are otherwise as the record writes them, and `StageInput` still has exactly
three members, so ADR-018 Enforcement item 2 is untouched.

**Why.** This is finding G1 of the self-audit review. As sketched, a lowered value carried the
number and nothing else, so every deterministic and every derived parameter had no
reconstructible edge into any run. The only available join was matching decimal strings, and
ADR-001 makes `"0.220" != "0.22"` precisely so that a value is never a key. Two accepted
requirements depended on the missing edge: ADR-004's rule that `verify` **recompute** collapse
taint by intersecting a scope with the paths a result depends on, and AT-6's rule that a RunSpec
assigning a point value to a flagged `Unknown` be rejected *by schema*. Neither was implementable.

`origin` rather than `path` alone, for two reasons a path cannot cover. A per-group sampling
scope draws `len(members)` values **from one binding at one path** (ADR-027), so several values
legitimately share a path and `group_member` is what tells them apart. And an `Unknown` carrying
a *declared sweep* legitimately produces point values, so AT-6 cannot be enforced by refusing all
values at an unknown's path — the enum has a member for a declared sweep point and none for
anything else, which makes the illegitimate case unsayable rather than validated.

**Consequence if this is the wrong call.** `spec_hash` changes, and `RunSpec` is the most-hashed
document in the system. That cost is why this lands now: nothing is frozen yet, and ADR-018's own
Option 3 makes the same argument for the same reason — "the change is nearly free now and
invalidates the Tier-A golden corpus later". The authoring burden is nil, since a planner emits
these, not a human.

**An unchecked cross-record dependency this creates.** Closing transitively from a derived value
to its contributing parameters requires the evidence package to carry the complete frozen
`UncertaintySpec`, including every materialized `Deterministic.derivation` — not only the runs.
ADR-007 does not state that in those terms. If a package ever ships runs without it,
`parameter_paths` stays correct while the transitive question becomes silently unanswerable for
an external auditor, which is G1 again one level up. No test can catch this until the package
builder exists; it is recorded here so it is found by reading rather than by an auditor failing.

**Two routes this does NOT attribute, named so the claim is not read wider than it is.** A
`DataArtifact` cited by `ArtifactSource` may contain physical quantities with no topology paths,
and a provider's `config_ref` document may contain them too -- the second structurally, since
ADR-003 makes that document opaque per dialect and commits FarSight to never reading it
physically. No change to `execution.py` can close the second without contradicting an accepted
record. What bounds both is ADR-017 decision 5's binding completeness, which turns "a quantity
lives in an opaque blob" into "a declared parameter is missing from the design"; it needs a
`SystemTopology` and is listed by `RunSpec.unenforced_rules()`.

**Closes by:** the superseding record the self-audit review proposes for ADR-018 (`ValueSource.path`
and `StageSpec.model_ref`), which should also state the ADR-007 dependency above.

**Status:** internally cross-checked; the constraint set behind it was assembled by reading the
ten binding records directly. Not externally expert-reviewed.

---

## DEV-5 — the arithmetic AST lives in `schemas/expr.py`, not `schemas/design.py`

**Record:** [ADR-029](ADR-029-derived-bindings.md) decision 2 — the `ArithExpr` sketch is
annotated `# src/farsight/schemas/design.py`
**Code:** `src/farsight/schemas/expr.py`

**What differs.** Module placement only. The grammar is exactly the seven node kinds ADR-029
fixes, with no eighth.

**Why.** The placement as sketched is an import cycle. `design.py` imports `belief.py`, because
an `UncertaintySpec` holds `Belief` objects; and `belief.py` needs the expression type, because
ADR-029 decision 4 materializes a derived value as a `Deterministic` **carrying the hashed
expression as its derivation record**. Putting the AST in `design.py` therefore requires
`belief.py` to import `design.py` and `design.py` to import `belief.py`. A leaf module both can
import is the smallest resolution; the alternative — moving `Derivation` off the belief — would
undo the very edge ADR-029 decision 4 exists to create.

**Related, and not a deviation:** `Deterministic.derivation` is new, and it implements ADR-029
decision 4 rather than departing from it. The record states the materialized belief carries the
expression; no record gave it a field, which is the same shape as finding D2 (a stated
capability with nothing to hold it).

**What is enforced.** `inputs` is materialized alongside the expression and checked against it
on every construction, so the shortcut a lineage query reads cannot disagree with the authority
it summarizes. A `Derivation` on a belief whose pedigree is not `derived_analysis` is refused.
Node-count and depth ceilings turn an over-large expression into a refusal rather than a
`RecursionError` inside the canonicalizer.

**What is deliberately NOT enforced here, and where it belongs.** That every `ParamLeaf` resolves
to a path bound to a `Deterministic` (ADR-029 decision 3); that the derivation graph is a DAG
(decision 4); and that the expression is dimensionally coherent. The first two need the whole
design, which a single belief cannot see. The third needs a unit library, which the
`no_units_lib_in_core` contract forbids `schemas` from importing and which ADR-029 puts at
freeze in SI float64. Claiming any of them here would be worse than omitting them, because a
caller would believe an expression had been checked when it had not.

**Consequence if this is the wrong call.** A third module in `schemas/`. If the freeze validator
later wants the AST and the design types in one file, moving it is a rename with no semantic
change, because nothing about the grammar depends on where it lives.

**Closes by:** a superseding record naming the module, or ADR-029 being reissued with the
placement corrected.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-4 — `ValidityEnvelope.conditions` is optional in code, required by ADR-004

**Record:** [ADR-004](ADR-004-uncertainty-belief-model.md) — `conditions` "required and non-empty"
**Code:** `src/farsight/schemas/common.py` — `ValidityEnvelope.conditions` defaults to empty

**What differs.** The record requires at least one condition on every envelope. The
implementation permits none.

**Why.** This is finding D3 of the self-audit review, and it is the direction of drift worth
noticing: **the code is right and the record is stale.** A mandatory prose field on every belief
produces filled-in ceremony — "nominal conditions apply" on four hundred parameters — which is
worse than an empty list, because it is indistinguishable from a considered statement.

**What is still wrong.** An empty `conditions` list currently means both "considered, and there
are no constraints" and "never considered". The self-audit review's coverage-declaration
recommendation resolves that by requiring either an assessment or an explicit *not assessed*,
generalizing the sentence ADR-007 already applies to registers: an empty register is an
assertion, a missing register is a verification failure. That change touches the registers too
and is deliberately **not** made piecemeal here.

**Closes by:** the coverage-declaration record (ADR-031 in the self-audit review's numbering),
which supersedes this clause of ADR-004 and states what an empty envelope asserts.

**Status:** internally cross-checked. Not externally expert-reviewed.
