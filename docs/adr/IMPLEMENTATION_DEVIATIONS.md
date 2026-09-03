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
