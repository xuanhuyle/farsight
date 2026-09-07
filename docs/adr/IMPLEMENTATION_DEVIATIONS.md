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

## DEV-12 — `DataArtifact` carries no `fetched_at_utc`

**Record:** [ADR-012](ADR-012-offline-security-foundations.md) decision 1 sketches the record
`farsight fetch` writes as `{url, sha256, size_bytes, fetched_at_utc, modified: false,
license_note}`; [ADR-001](ADR-001-content-addressed-identity.md) decision 4 puts timestamps in the
unhashed `provenance` half
**Code:** `src/farsight/schemas/knowledge.py` — `DataArtifact`

**What differs.** Five of the six sketched fields are implemented. `fetched_at_utc` is not a field
on the hashed object; when the artifact is stored it belongs in the envelope's `provenance` half
beside `created_at`.

**Why.** The two records contradict each other and only one reading survives. If the fetch time
were inside the hashed half, **two fetches of identical bytes would produce two different
addresses** — destroying the deduplication that `Referent.artifact_refs` and the kernel cache both
rely on, and contradicting ADR-001's own reason for the split: "if a creation time is inside the
hashed document then nothing is ever reproducible by construction". ADR-016 applies the same rule
explicitly to `CoverageAttestation.produced_by` ("no timestamp (ADR-001 rule 4)"), so the corpus
is consistent everywhere except this one sketch.

`url` stays inside the hash, because ADR-016's KERN-2 check is that "the `DataArtifact` carries
the source URL" — a publisher not covered by the digest is a provenance claim nothing protects.

**Consequence if this is the wrong call.** "When did we fetch this" stops being part of the
artifact's identity, so two records of the same bytes fetched years apart are one object. That is
the intent; if a caller ever needs to distinguish them, the distinction belongs in the audit log
(ADR-012), which already records a `fetch` action with a timestamp and is the place the corpus
puts that question.

**Also unreconciled, and not resolved here.** `DataArtifact{url, sha256, size_bytes, modified,
license_note}` and ADR-016's `KernelRef{sha256, kernel_type, logical_name, size_bytes,
attribution, modifier, parent_sha256, license_note}` describe the same bytes with different
fields, and no record says how they relate. `KernelRef` lands with the kernel cache; whichever
record defines it should state the relationship rather than leave two overlapping descriptions.

**Closes by:** an ADR defining `DataArtifact`, which should state the field split explicitly and
reconcile it with `KernelRef`.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-13 — the object store is files, and the plan's §6 line says SQLite

**Record:** `FARSIGHT_FOUNDATION_PLAN.md` §6 — `registry/ # object store (SQLite:
objects/aliases/edges), kernel cache, audit log`; [ADR-011](ADR-011-storage-and-persistence.md)
decision 1 — "Object store (files). Frozen content-addressed documents at
`objects/<first2>/<hash>.json`", and decision 6 — "SQLite is used for three tables and nothing
else"
**Code:** `src/farsight/registry/objects.py`

**What differs.** The implementation follows ADR-011: objects are files, and SQLite holds exactly
`runs`, `aliases` and `audit_log`. There is **no `objects` table and no `edges` table**.

**Why.** ADR-011 is the later and more specific record, it gives its reasoning (an auditor should
find JSON they can read in a text editor rather than a storage engine standing between them and
the numbers), and ADR-017 independently forecloses edges as a stored relation — "never as an
`edges` or `links` field". The plan line is stale.

**What makes this worth recording rather than silently following.** ADR-000 makes the plan the
authority and ADRs subordinate elaborations that "must not silently contradict it", and requires a
departure to be declared as a `PLAN AMENDMENT REQUESTED` line. ADR-011 files amendment requests
for other §6 items and **not** for this one, so the contradiction is undeclared. That is the D3
shape: an accepted record and the plan disagree, the record is right, and nothing records it.

**Consequence if this is the wrong call.** If the plan's line was the intent, the store would need
an `objects` table and an `edges` table, and the second would reopen a relation ADR-017 closed
deliberately. Both would be visible immediately, because the file layout is what `verify` and
package build walk.

**Closes by:** a `PLAN AMENDMENT REQUESTED` line on ADR-011, or a plan edit by the founder.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-14 — `$FARSIGHT_HOME` has a default, because no record gives it one

**Record:** [ADR-012](ADR-012-offline-security-foundations.md) decision 4 — "configuration,
object registry, ledger and audit log live under `$FARSIGHT_HOME`";
[ADR-016](ADR-016-kernel-sets.md) decision 5 anchors the kernel cache at
`$FARSIGHT_HOME/kernels/<first2>/<sha256>`
**Code:** `src/farsight/registry/paths.py`

**What differs.** Nothing is contradicted; a value is chosen that four records depend on and none
supplies. `FARSIGHT_HOME` in the environment wins, then the CLI's `--home`, then a platform
default: `%LOCALAPPDATA%arsight` on Windows and `~/.local/share/farsight` on POSIX.

**Why.** Every record that mentions state uses one of "workspace", "working store", "output root"
or `$FARSIGHT_HOME`, and **none of the four is defined anywhere** — a grep across `docs/adr/` and
the plan returns no definition for any of them. Some module has to resolve a path before anything
can be stored, and leaving it to whichever module needs one first is how two modules end up
disagreeing about where the store is.

Platform conventions were followed rather than a third invented, so the location is where a user
would expect application state on their own operating system.

**What is deliberately not done.** Resolving a path creates no directory. A resolver that makes a
tree on import turns a typo in an environment variable into a scattering of empty folders and
makes `--home` hard to test; creation belongs to the writer, `write_atomic`.

**Consequence if this is the wrong call.** The default moves and existing caches are orphaned —
which matters more than usual here, because ADR-016 forbids garbage-collecting the kernel cache,
so an orphaned cache is disk that is never reclaimed. That argues for settling the default before
anything large is fetched, which is the current position.

**Closes by:** a record defining `$FARSIGHT_HOME`, the workspace and the output root, and the
relationship between them.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-15 — the CLI reaches the network through one named edge, not none

**Record:** [ADR-012](ADR-012-offline-security-foundations.md) Enforcement 2 — `socket`, `http`,
`urllib`, `ftplib`, `smtplib`, `requests` and `httpx` "are forbidden in every `farsight` package
except `farsight.acquire`, which is itself importable only from the CLI's `fetch` module"
**Code:** `.importlinter`, contract `no_network_in_truth_loop`

**What differs.** The contract lists `farsight.cli` as a guarded source module *and* names one
ignored edge, `farsight.cli.fetch -> farsight.acquire.fetch`.

**Why.** ADR-012's architecture is a chain, not a wall, and the two halves of its own sentence
pull against each other: `acquire` may import a networking library, and the CLI's fetch module is
its only importer — so the CLI *does* reach the network, transitively, by design. A `forbidden`
contract reports transitive chains, so listing `farsight.cli` without an exception fails on the
sanctioned path. This was not theoretical: it broke the moment the fetch verb was registered.

The two alternatives were both worse. Dropping `farsight.cli` from the source list would have
left every *other* CLI module free to open a socket directly. Dropping the stdlib modules from
the forbidden list would have left the contract naming only third-party HTTP clients, which is
where it started — and the sharp omission there was `urllib`, since the obvious way to write a
downloader uses it, so the contract forbade the imports nobody would reach for and permitted the
one they would.

**What this buys.** Verified by construction: `socket` added to `cli/main.py` and `urllib` added
to `cli/exit_codes.py` are both refused, while the one sanctioned edge passes.

**Consequence if this is the wrong call.** The ignored edge is a hole exactly one import wide. If
`farsight.acquire` ever grows a second importer the contract will say so, because the ignore names
one specific pair rather than a package.

**Closes by:** nothing needs to close it — this implements ADR-012 as written. It is recorded
because the exception is invisible in the record's prose and a later reader deleting the
`ignore_imports` line would break a green build for the wrong reason.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-16 — the first fetch of a NAIF kernel cannot verify anything

**Record:** [ADR-012](ADR-012-offline-security-foundations.md) decision 1 —
`farsight fetch kernel --url <url> --expect-sha256 <hex> --into <cache>`;
[ADR-016](ADR-016-kernel-sets.md) Enforcement 9 (KERN-2) — the `DataArtifact` carries the source
URL and `naif_unmodified` may be stamped only when the stored bytes match "the hash `fetch`
recorded at acquisition"
**Code:** `kernels/pinned_kernels.json`; `src/farsight/acquire/fetch.py`

**What differs.** Nothing in the code. The gap is in the record's premise: `--expect-sha256` is a
required precondition with no flag to skip it, and **no record says where the first digest comes
from.**

**Why.** The precondition is right and the premise behind it is missing: a digest that must come
from somewhere other than the download has to come from *somewhere*, and for this publisher it
does not exist. Implementing the check as written and pretending the first fetch satisfied it
would make every later verification inherit a claim nobody made.

**What that means here specifically.** Verified 2026-09-07: NAIF publishes no checksums for the
generic kernels. There is no `checksums.txt`, no `md5sums.txt`, no `SHA256SUMS`, and the LSK
directory's `aareadme.txt` carries no digest. So the first acquisition of `naif0012.tls` could not
check anything against an independent source — the digest
`678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b` was obtained by downloading the
file and hashing it.

That is **trust-on-first-use**, and it is a genuinely weaker property than the rest of this system
provides. Stated precisely: it establishes that everyone after us gets the same bytes we got. It
does **not** establish that the bytes we got are the bytes NAIF published. A compromise of the
transport or the origin at the moment of first fetch would be pinned, not caught, and every
subsequent verification would confirm the compromised bytes.

**What was done to narrow it, and what remains.** The file was fetched twice over independent
connections and the bytes compared, which catches transient corruption and nothing else. Transport
was HTTPS, which is not nothing but is not a publisher attestation. The digest is now pinned in
`kernels/pinned_kernels.json`, so every fetch after the first is a real check; the manifest states
the acquisition mode per row rather than letting a pin read as verified provenance, and a test
refuses a row that does not declare one.

**Two hazards found in the same pass, both fixed by the manifest's rules and tested.** NAIF ships
`naif0012.tls.pc` — the same kernel with CRLF line endings, 5,409 bytes against 5,257, and
therefore a **different content address for identical physics**. Fetching that variant on Windows
would give a design frozen there a different `kernel_set_hash` from one frozen on Linux, and
ADR-006's cross-platform golden would fail for a reason with nothing to do with physics. And
`latest_leapseconds.tls` is a symlink NAIF updates in place, so the same URL returns different
bytes over time — exactly what content addressing exists to prevent. Neither is pinnable.

**Consequence if this is left as it is.** Every kernel this project ships rests on a
trust-on-first-use root, and a package's provenance chain is only as strong as that root. That is
survivable and common — it is how most dependency pinning works — but it must never be described
as verified against the publisher, because it is not.

**Closes by:** a record stating the acquisition modes and what each one licenses a package to
claim; or a genuine second source for the digest — a PDS4 bundle checksum manifest, a published
paper, or an independent project's pin — at which point the row's `acquisition` changes and the
weaker mode is retired for that kernel.

**Status:** internally cross-checked; the absence of NAIF checksums was verified directly rather
than assumed. Not externally expert-reviewed.

---

## DEV-11 — the design-scope tag is not outside the run-index range, and does not need to be

**Record:** [ADR-005](ADR-005-seeding-and-replay.md) — "`SeedSequence(entropy=design_seed,
spawn_key=(0xD5, ...))`, where `0xD5` is the design-scope tag and is **deliberately outside the
run-index range**"; its Enforcement asks `test_seed_derivation` to assert "that no design-scoped
`spawn_key[0]` value is in the run-index range"
**Code:** `src/farsight/experiments/seeding.py` — `DESIGN_SCOPE_TAG`;
`tests/unit/test_seeding.py::test_design_scoped_keys_are_separated_by_entropy_not_by_tag_value`

**What differs.** The stated enforcement is not satisfiable and is not implemented as written.
`0xD5` is 213. ADR-004's own illustrative campaign is 24 outer points × 400 inner draws = 9,600
runs, so `run_index` 213 exists in the flagship's own sampling plan. There is no value that is
both a small constant and outside the run-index range, because the range grows with the campaign.

**Why.** The record's own decision is sound; only the justification offered for the constant is
wrong, and implementing the justification rather than the decision would produce a check that is
either vacuous or wrong.

**What the real separation is.** Design-scoped keys are rooted at
`design_seed`, which is a *different entropy value* from `root_seed` — ADR-005 says so in the same
paragraph. Two `SeedSequence` objects with different entropy produce unrelated streams regardless
of whether their `spawn_key` prefixes coincide, so the tag value carries no separation duty at
all. The record's own decision is sound; only the justification offered for the constant is wrong.

**What is implemented instead.** A test asserting the separation that is real: the same
`spawn_key` prefix under `design_seed` and under `root_seed` produces different words. Writing
the enforcement as stated would have meant either a test that passes vacuously (asserting 213 is
outside a range that is empty because no campaign exists yet) or one that fails the moment a
campaign exceeds 214 runs.

**Consequence if this reading is wrong.** If the intent was that design-scoped and run-scoped keys
share one entropy value — which the record's wording elsewhere contradicts — then the tag would
have to be moved outside the maximum campaign size, and the constant would need a bound the
record does not state. That would be a superseding decision, not a validator change.

**Closes by:** a superseding ADR-005 restating the separation as entropy-based and dropping the
range claim, or stating a maximum campaign size that makes the original claim true.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-10 — the units boundary is a package, not a `Quantity` method

**Record:** [ADR-008](ADR-008-units-and-numerics.md) — the decision block sketches
`Quantity.to_si()` as a method on the hashed wire form in `schemas/common.py`, "the one
conversion point"
**Code:** `src/farsight/units/__init__.py` — `to_si`, `from_si`, `encode_float`, `convert`

**What differs.** Placement only. The conversion point is a function in `farsight.units` rather
than a method on `Quantity`; the semantics — convert once, at the boundary, and let the numeric
core see raw SI float64 — are exactly the record's.

**Why.** `schemas` is a leaf package under the `schemas_is_leaf` contract, and `common.py`'s own
docstring already made this call before this work started: "the conversion boundary lives in
`farsight.units`, not here, because this package is a leaf and may not import a unit library."
ADR-008's own Enforcement 2 permits astropy in `farsight.schemas`, so the record does not forbid
the method — but a module-level astropy import in `common.py` would pull astropy into every
worker process spawn, and ADR-002's spawn-floor measurement (still unrun) is what should decide
that, not a docstring.

**What this closes that was open.** ADR-008 Enforcement 2 names the forbidden source set exactly:
`farsight.engines`, `farsight.metrics`, `farsight.uncertainty` and `farsight.hashing`, permitted
in `farsight.schemas`, `farsight.units` and `farsight.analysis` only. The shipped `.importlinter`
named only `farsight.metrics` and `farsight.engines.linkchain` — so `farsight.engines.spice` was
unguarded, which is precisely where ADR-015 decision 7's independence claim lives: the SPICE time
path and the astropy time path are cross-checked, never collapsed into one call. The contract now
matches the record, and it was verified to bite by feeding a synthetic `import astropy` into both
`hashing` and `engines`, neither of which it previously covered.

**A property the record does not state, found by testing and worth recording.** Conversion through
SI is **not bit-reversible**. `to_si` narrows to float64 because that is what the core computes
in, and no care in the other direction undoes that rounding: a Hypothesis property found
`5749259923628352.0 km` returning as `5749259923628351.0 km` within seconds. Because a magnitude
is hashed, a value authored in km, converted to SI and re-encoded in km can produce a different
`spec_hash`. The rule that follows — and it is now in the module docstring rather than folklore —
is that **values are encoded once, in the unit they were authored or drawn in**; ADR-022's
encoding rule applies to a machine-produced float already in its target unit, and `convert` is for
reading rather than for re-minting a hashed magnitude.

**Consequence if this is the wrong call.** If the spawn-floor measurement shows astropy's import
cost is not the dominant term, `Quantity.to_si()` could be added as a thin delegation to this
module without moving anything. The reverse — starting with the method and discovering the import
cost — would mean unwinding a module-level import from the bottom of the schema stack.

**Closes by:** a superseding ADR-008 stating the boundary as a package, or the spawn-floor
measurement showing the method form is affordable.

**Status:** internally cross-checked. Not externally expert-reviewed.

---

## DEV-9 — `Claim` promoted to an object, and the honest limit of what containment proves

**Record:** [ADR-007](ADR-007-evidence-package-format.md) decision 3 — "The claim statement is a
required, structured manifest field", singular, ten fields, no identity;
[ADR-009](ADR-009-metrics-and-acceptance-rules.md) line 109 — the falsifier "is the exact
restatement of this rule"; [ADR-006](ADR-006-reproducibility-tiers.md) — "Every claim carries
exactly one" tier
**Code:** `src/farsight/schemas/design.py` — `Claim`, `ClaimResult`, `falsifier_restates`,
`unregistered_claim_refs`

**What differs.** `claim_statement` becomes a content-addressed `Claim` belonging to the
**design**, plus a package-side `ClaimResult` carrying only what execution can know. This is
finding G3: the ten fields were ~70% of a Claim and 0% of an identity, so nothing could
reference, contradict or supersede one; a package supported exactly one; and the tie from a claim
to its supporting runs was directory co-membership rather than a reference.

**Why.** The deepest half is pre-registration. ADR-021 decision 7 already lets FarSight
pre-register what it will *measure against*; nothing let it pre-register what it will *claim*.
For a platform whose thesis is falsification that is backwards.

**The central correction, and the reason this entry exists.** The natural claim — "a claim frozen
into the design cannot be post-hoc, because it sits inside `experiment_hash`" — is **false**, and
an adversarial pass caught it before this shipped. ADR-005 line 28 derives every bit stream from
`SeedSequence(entropy=root_seed, spawn_key=(run_index, stream_id))`; `experiment_hash` is not an
input. So re-freezing a design with a new claim changes every `spec_hash` while leaving every
drawn value and every channel byte **identical**. Post-hoc insertion costs a re-*plan*, which is
a pure derivation, not a re-*run*. An author who ran first, looked, then wrote the claim and
re-froze produces a package that verifies.

So the module says what is true: containment is **tamper-evidence** — a claim absent from the
design is visibly unregistered, and adding one changes the identity of every run — and
pre-registration is *containment plus an externally published digest*, which is exactly what plan
§17 already does when it publishes hashed predictions before the paywalled data is purchased. A
mechanism that overstated this would be doing the thing the product exists to prevent, and a test
pins the docstring so a later reader cannot quietly strengthen the claim.

**What is enforced.** Every field on a `Claim` is knowable before a run executes — which is why
`verdict`, `partial` and `contains_epistemic_collapse` are absent, each being a fact about an
execution that has not happened. `ClaimResult` restates **nothing** from its claim, because
ADR-007 refuses two hash-verified copies of one datum by name: they "create a precedence
question", and any answer is worse than not having the second copy. `run_set` is frozen with the
claim rather than chosen with the package, since closing HARKing while letting an author pick
*which runs support the claim* after seeing them is the same problem wearing a different hat.
The falsifier correspondence is computed by **generation and containment**: the canonical
condition is generated from the criterion's parts (`metric_display`, the negated comparator, the
target magnitude) and the falsifier must contain it — which reproduces ADR-007's own worked
example, `i.e. dsoc.rate_ladder_step_delta < -1`, exactly.

**Rejected after critique.** Character floors on `sentence` and `falsifier`: a floor stands in for
sharpness and gets the sign wrong, since the bare condition is a better falsifier than sixty
characters of hedging. A `Finding` type and a sixth register: the lane distinction falls out of
`unregistered_claim_refs` without new machinery, and ADR-007 line 136 makes a sixth register an
explicit revisit trigger. A `withdrawn` revision reason: a claim cannot be withdrawn from a
frozen design, and offering the member would name an operation with no implementation. Coupling
claim-*optionality* to the exploratory lane: making an exploratory package the one place a result
needs no claim would make that lane the cheapest legal home for a real finding.

**Consequence if this is the wrong call.** `referent_refs` is required non-empty, following
ADR-007's rule that `verify` fails a package whose claim lacks a resolvable `referent_ref`. That
makes a purely internal claim — "the margin exceeds 3 dB", with no external observation to be
wrong against — **inexpressible**. That may be too strong; the record is explicit and the
implementation follows it, but this is the field most likely to need widening.

**Not built, and named rather than implied.** `ExperimentDesign` itself, so the containment this
module describes is asserted by a freeze validator that does not yet exist;
`AcceptanceCriterion`, so `falsifier_restates` takes the criterion's parts rather than resolving
its digest. And the link from a confirmatory design back to the exploratory work that prompted it
must **not** be a hashed back-link — ADR-007 line 126: "a hashed back-link would make a design's
identity depend on its own search history" — so it belongs in the unhashed provenance half of the
object file.

**Closes by:** the ADR-032 the self-audit review proposes, which should also carry the
`claims: []` plurality amendment to ADR-007 decision 3 and decide the `referent_refs` question
above.

**Status:** internally cross-checked; six binding records were read directly and three
independent designs were adversarially critiqued, which is what caught the containment overclaim.
Not externally expert-reviewed.

---

## DEV-8 — `Source` and `Assumption` defined, and what they deliberately do not claim

**Record:** [ADR-021](ADR-021-referent-semantics.md) (`Referent.source_refs  # Source objects, by
digest`), [ADR-007](ADR-007-evidence-package-format.md) (the assumption register carries every
`Assumption` "with pedigree and the objects that depend on it"), [ADR-004](ADR-004-uncertainty-belief-model.md)
(`Pedigree.sources`, `Unknown.bounding_assumption_ref`), [ADR-026](ADR-026-model-and-engine-build.md)
(`ModelVersion.source_refs` / `assumption_refs`)
**Code:** `src/farsight/schemas/knowledge.py`

**What differs.** Nothing is contradicted; two types that four accepted records reference and
none defines are now defined. This is finding G2, and the review calls it verbatim the hazard
ADR-026 was commissioned to close for `ModelVersionRef` — *the reference is live in a hashed
document and its referent is undefined*.

**Why.** Both take ADR-021's `Referent` shape — one content-addressed object, an authored `*_id`
label, a monotone `revision`, `supersedes` plus a typed `revision_reason` — rather than ADR-026's
two-object split. The split exists so a `ModelVersion` digest changing does not orphan its
history, and its price is a parent carrying nothing that can affect a number. For `Assumption`
that price buys nothing and costs something real: ADR-007 requires the register to carry each
assumption **with pedigree**, and a parent stable enough to be worth splitting out is a parent
with no pedigree on it.

**What is deliberately NOT claimed: that FarSight detects two citations are the same paper.**
ADR-001's own Consequences say deduplication is "syntactic, not semantic … and nothing in the
system will point this out", and normalizing a citation into a comparison key is normalizing
*value*, which the same record forbids validators from doing. So: identifiers are transcribed
**verbatim** (hygiene only — one line, stripped), sameness is **declared** by an authored
`supersedes` a human signs, and everything else is a named residue.

There is deliberately **no freeze-time collision refusal on identifiers.** One was designed and
then refuted by the flagship's own central source: DSN 810-005 is a numbered *series* whose
modules are separately issued under one designation, so a key on the designation alone merges
different documents and a refusal built on it rejects a legal document set.
`SourceIdentifier.part` distinguishes them, and `Source.collision_keys()` reports keys for a
validator one layer up to use — a signal, not a rule enforced where a false positive means a
week-3 author disables the check and takes the mechanism with it.

**Two closures worth naming.** A `Source` carries **no pedigree**: provenance has to terminate or
it regresses forever, and who read a paper and how well is a property of the *reading*, which
ADR-021 puts on `ReferentPoint.locator`. An `AssumptionBound` is **never a point**: if an
assumption could carry one value, discharging an `Unknown` through
`Unknown.bounding_assumption_ref` would hand it a concrete number — the silently-fitted default
ADR-001 rule 6 forbids and AT-6 tests for. One-sided bounds carry an *absent* edge rather than an
invented finite one, because "at most 0.5" with a fabricated lower edge of 0 is the same fitting
under a different name.

**Rejected as theater**, each proposed by a design and cut after critique: a constant
`external_review` field on every register row (a value that never varies reads as information and
is not); an `access` field that would be uniformly `full_text` because the honest value costs more
to write; confidence scores and trust percentages; a forbidden-claim regex inside the schema layer
(it is a lint, ADR-030 already has one, and the regex refused the honest negation); `scan_points`
on the assumption (mission-specific data in a mission-independent object); and a `pessimistic_edge`
no consumer reads.

**Deferred, and named rather than implied.** The assumption register's reverse index —
"the objects that depend on it" — cannot live on the `Assumption`, because ADR-001 forecloses
in-place annotation and a `used_by` field would re-hash the assumption and every belief citing it
whenever a dependent appeared. Its only legal home is a materialized row in
`registers/assumptions.json`, recomputed by `verify` and refused on disagreement — the
`draw_order` pattern. That register is ADR-007's document; `dependents_of()` is the pure forward
walk this module can honestly provide. Also deferred: the freeze validator that anchors
`Source.origin` against the package input closure, which needs ADR-021's `Referent` and ADR-007's
package to exist.

**A third instance of the same hazard, not fixed here.** `DataArtifact` is referenced by digest
from `ArtifactSource.artifact_ref` (`execution.py`), `Referent.artifact_refs` and now
`Source.artifact_refs`, appears in 26 places across the accepted records, and has no schema. The
review named `Source` and `Assumption`; this one is the same shape and is recorded so it is found
by reading rather than by an auditor failing. ADR-012 already sketches its fields.

**Closes by:** an ADR defining these two objects, most naturally alongside `DataArtifact` and
ADR-021's `Referent` when `knowledge.py` is completed.

**Status:** internally cross-checked; the constraint set was assembled by reading the six binding
records directly, and three independent designs were adversarially critiqued before this shape was
chosen. Not externally expert-reviewed.

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

## DEV-17 — the coverage check exists, but at run time, and the freeze validator does not

**Record:** [ADR-016](ADR-016-kernel-sets.md) — `kernel_coverage_completeness` is specified as a
**freeze** validator; [ADR-023](ADR-023-run-outcomes.md) Enforcement 6 — no `FreezeTimeError`
subclass may be raised or imported under `src/farsight/engines/`
**Code:** `src/farsight/engines/spice/time.py`; `src/farsight/schemas/errors.py`

**What differs.** The record places the coverage refusal at freeze. The code places it in the
worker: `check_epoch_covered` raises `EpochCoverageError`, which is an `UnhonorableSpec` and
therefore a `WorkerError`. The freeze-time half is a type with no raising site —
`KernelCoverageError` is defined in `schemas/errors.py` and nothing raises it, because the freeze
validator that would is not built.

**Why.** The two are not substitutes, and building the run-time half first was the smaller
mistake. A run-time refusal fires after the design was frozen and dispatched, so it catches the
epoch but not the design that permitted it — and by ADR-023 that is exactly what a worker-side
refusal means: evidence that a freeze-time completeness check has a hole. The freeze validator
needs the SPK and PCK coverage windows, which are stage-4 kernels that are not downloaded, so
writing it now would mean writing a validator that cannot be tested against a real coverage
window. What could be built honestly today is the leapsecond half, and it is built.

The typing was also wrong in the first draft and is worth recording as such: both
`UnhonorableSpec` and the coverage error were written as `FreezeTimeError` subclasses under
`engines/`, in direct violation of ADR-023 Enforcement 6, and the lint that should have caught it
had a blind spot — it only collected classes whose names end in `Error`, so `UnhonorableSpec`
was invisible and its subclass was reported as orphaned instead. Both are fixed, and
`test_no_freeze_time_error_under_engines` now checks the enforcement leg directly.

**Closes by:** ADR-016's `kernel_coverage_completeness` implemented as a freeze validator over
the full SPK/PCK/LSK window set, raising `KernelCoverageError`, once stage-4 kernels exist to
test it against. At that point `EpochCoverageError` becomes a defence-in-depth check that should
be unreachable in a frozen design rather than the only check.

**Status:** Open. The run-time half is enforced and mutation-checked; the freeze half is absent
and is not claimed anywhere in the code or docs to exist.

## DEV-18 — `GridRef` carries a digest, which ADR-020 requires and ADR-018 spells differently

**Record:** [ADR-018](ADR-018-run-composition.md) decision 1 — `class GridRef(BaseModel):
grid_id: str`, and rule 4, "the producing and consuming stages declare the same `grid.grid_id`";
[ADR-020](ADR-020-channel-model.md) decision 4 — `grid_hash` "is what ADR-018's `StageSpec.grid`
and ADR-015's `GeometryRequest.epochs` reference, both of which are `Ref`-shaped and therefore
admit only a digest"
**Code:** `src/farsight/schemas/execution.py`

**What differs.** `GridRef` holds `grid_hash: Ref` — a bare 64-hex content address — where ADR-018
writes `grid_id: str`, a segment-grammar name. The stage-compatibility check of ADR-018 rule 4
compares digests rather than ids. The field name `grid` and the type name `GridRef` are unchanged.

**Why.** The two accepted records disagree, and ADR-020 is the one that governs: ADR-018's own
comment on that line says "ADR-020 owns the grid descriptor itself", and ADR-020 then names
ADR-018's `StageSpec.grid` explicitly as one of the two fields that admit only a digest.

Following ADR-018's literal spelling would also make rule 4 unable to do its job. Two grids can
share a human-chosen id while describing different time bases, so comparing ids would pass two
stages sitting on genuinely different grids — which is precisely the "silent-killer class this
rule exists to close" that rule 4's own text names. A digest cannot be shared by two different
grids.

Changed rather than left as a deviation-in-code because nothing is frozen yet. After the first
package ships, altering this field invalidates every archived `spec_hash`, and ADR-020 records
that the identity scheme is effectively permanent once customers hold packages.

**Closes by:** ADR-031 or ADR-032 superseding ADR-018 decision 1's `GridRef` block, or an
amendment recording that ADR-020 decision 4 governs the reference shape.

**Status:** Open. The code follows ADR-020; ADR-018's code block still says otherwise and cannot
be edited.


## DEV-19 — `test_determinism_rules` ships with a two-entry allowlist the record does not provide for

**Record:** [ADR-006](ADR-006-reproducibility-tiers.md) Enforcement 5 — "AST-scans
`src/farsight/` outside `analysis/` and fails on `datetime.now`, `time.time`, `os.getpid`,
`socket.gethostname` and `os.listdir`"
**Code:** `tests/unit/test_no_false_validation.py`; `src/farsight/cli/geometry.py`;
`src/farsight/registry/atomic.py`

**What differs.** The lint is implemented as specified and then permits exactly two sites, each
with a written reason. ADR-006 states the ban with no exception mechanism.

**Why.** Two things the architecture requires cannot be written without a banned name, and both
were already in the tree before this lint existed.

`cli/geometry.py` calls `datetime.now` for ADR-012's `ts_utc`. The audit log records when things
happened; it cannot be written without reading a clock, and ADR-012 and ADR-006 both put it
outside every evidence hash precisely so that reading one is safe there.

`registry/atomic.py` calls `os.getpid` for a temp filename component, so two concurrent writers
do not collide on the same sibling path. The name is discarded by `os.replace` and reaches no
hashed artifact.

The alternative — dropping the two names from the banned list — would have been worse: it removes
the check everywhere to accommodate two places, and `datetime.now` reaching a hashed document is
exactly the failure the rule exists to catch. The allowlist is asserted to be *exactly* those two
entries in both directions, so a third use fails the test until somebody writes down why, and an
entry whose call has been removed fails it too.

**Closes by:** a superseding record either granting ADR-006 Enforcement 5 an allowlist with these
two entries, or naming a different mechanism for the audit timestamp and the temp-file suffix.

**Status:** Open. The lint is green and the allowlist is closed and documented.


## DEV-20 — the weeks 1-2 exit gate is met on a synthetic kernel, not on Psyche and not in a container

**Record:** FARSIGHT_FOUNDATION_PLAN.md §17 — the weeks 1-2 exit gate, *"`farsight geometry`
emits hash-stable Psyche pass geometry, bitwise-reproducible in container"*;
[ADR-019](ADR-019-reference-container.md) (the container that is not built);
[ADR-024](ADR-024-cli-surface.md) decision 1 (the verb)
**Code:** `tests/unit/test_geometry_gate.py`; `tests/fixtures/synthetic_spk.py`;
`src/farsight/cli/run_geometry.py`

**What differs.** Three words of the gate are not met, and the passing test says so in its own
module docstring rather than in this ledger alone:

* **Psyche** — no Psyche SPK has been downloaded; that needs founder approval and disk that is
  spent permanently, because the kernel cache is never garbage-collected by design. The gate runs
  against a FarSight-authored synthetic SPK of two fictional bodies moving on straight lines.
* **in container** — ADR-019's reference image is not built. What is shown is bitwise stability
  within one machine, across two runs and across two processes.
* **pass geometry** — there is no station, no visibility model and no pass. A two-kernel set
  (one LSK, one SPK) supports inertial body-to-body geometry and nothing body-fixed; ADR-015's
  `ITRF93` and a station topocentric frame both need kernels that are not present.

**Why.** The machinery can be built and tested honestly before the download is spent, and doing
it in that order is what let the gate find real defects — a reserved channel name that would have
been silently swallowed by the `nul` device, an audit write that crashed in a stripped
environment, and a grid reference that compared names instead of addresses. What the synthetic
kernel cannot do is say anything about real ephemerides: it exercises furnish order, content
addressing, coverage refusal, the light-time solver and every refusal on the path, and it is not
evidence about Psyche.

The one thing it does check beyond plumbing is that the numbers are right *for the trajectory it
declares*: the fictional bodies move on straight lines, so the geometric range has a closed form,
and CSPICE is compared against it rather than only against itself. Measured agreement is 0.0 km
at one epoch and 6e-8 km at another, the residual being float64 rounding in the Lagrange
interpolation.

**Closes by:** the Psyche SPK and station kernels acquired under founder approval, ADR-019's
reference image built, and `ci-geometry-crosscheck` green against an external golden — at which
point the synthetic fixture stays as a plumbing test and stops being the gate.

**Status:** Open. The gate is green on the terms stated above and on no others; no document in
this repository claims the Psyche or container legs are met.

## DEV-21 — `GeometryDesign` is a second document for a job `RunSpec` is already defined to do

**Record:** [ADR-018](ADR-018-run-composition.md) decision 1 — "A run with no engine stage is a
**geometry-only run**: the week-1 exit gate (`farsight geometry`, verb owned by ADR-024) ... are
both this shape"; [ADR-024](ADR-024-cli-surface.md) confidence table — `farsight geometry` as a
permanent top-level command is held at **0.60**, with the revisit trigger "ADR-018 lands run
composition in week 3 and geometry turns out to be expressible as a one-stage `RunSpec`"
**Code:** `src/farsight/schemas/probe.py`; `src/farsight/cli/run_geometry.py`

**What differs.** `GeometryDesign` is a hashed document carrying a kernel set, one grid and a list
of requests. ADR-018 says that shape is a `RunSpec` whose stage list contains no engine stage, and
names this exact command as an instance of it. So two document types now describe one job, and
only one of them is in an Accepted record.

**Why.** The immediate reason is that `RunSpec` cannot express it today: it has no sample grid
(`StageSpec.grid` is a reference to a descriptor no code produced until this stage), no
`GeometryRequest`, and `StageSpec.config_ref` is deliberately dangling because ADR-003 makes
provider config opaque. Building the gate on `RunSpec` would have meant inventing the missing half
of run composition first, and ADR-018's own composition validators are due week 3.

The honest part is that this is a scheduling reason, not an architectural one — which is exactly
what ADR-024 says about the verb itself.

**ADR-024's revisit trigger has already fired, and that is the point of this entry.** The trigger
is conditional on geometry turning out to be expressible as a one-stage `RunSpec`; ADR-018 is
Accepted and already says it is. So the condition is met in the record set today, not pending a
week-3 discovery. ADR-024 requires the question settled **before the first package ships in week
4**, after which the name — and by extension this document type — is permanent.

The decision is a founder decision and is not taken here. The two live options: declare
`GeometryDesign` a deliberate week-1-only document with a retirement date, or move geometry onto
`RunSpec` now while `spec_hash` has no archived instances and the change is free.

**Closes by:** a superseding record settling ADR-024's 0.60 row, either retiring `geometry` in
favour of a one-stage `run` or making the verb and this document permanent with reasons.

**Status:** Open, and **time-boxed**: free to change now, permanent after the first package ships.
