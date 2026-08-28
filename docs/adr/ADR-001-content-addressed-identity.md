# ADR-001 — Content-addressed identity and the freeze protocol
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §4 (four planes, immutability invariant), §7 (canonical serialization, two-layer identity, versioning), §12, §16, §23 item 1, "Things we must get right" item 1; decisions D4 and D5
**Related ADRs:** ADR-000 (the escape-hatch tokens and the `review_signoffs` field this record's checklist items land in), ADR-004 (an `Unknown` belief is why we never need NaN to mean "we do not know"), ADR-005 (the seeding authority: the root seed's encoding is its decision, and derived seeds are hashed inputs, which is what makes run #4242 addressable), ADR-006 (a tier claim is always a claim about one named content hash), ADR-007 (a package identity is a closure over these hashes), ADR-011 (bytes-as-written is what the store must guarantee), ADR-012 (the signing seam signs a root hash produced here), ADR-013 (owns the `schemas_is_leaf` and `auditor_boundary` import contracts this record depends on), ADR-014 (`uv.lock` SHA-256 is one of the hashed environment inputs), ADR-016 (kernel-coverage attestation is a step of the freeze protocol decided here, and it is the one step that needs an engine extra), ADR-022 (sampler stream stability decides whether the pure-derivation claim holds outside a pinned environment)

## Context

Every commercial claim FarSight makes reduces to a hash comparison. Tamper evidence (AT-3) is "recompute and compare". Replay (AT-7) is "re-derive this RunSpec from `(experiment_hash, run_index)` and compare output hashes". Provenance is "this parameter came from that `Source`, and here is its hash". The forcing question is therefore narrow and unforgiving: **what exact byte sequence does SHA-256 run over for a FarSight object, and what guarantees that two honest implementations, on two machines, in two years, produce the same digest?**

The facts that constrain the answer are mostly about floating point and about time. JSON has no canonical float serialization that survives a Python round trip: `0.1` authored by a human, parsed to a binary64, and re-emitted is a value whose shortest round-trip representation depends on the emitter. RFC 8785 (JCS) does define number serialization precisely, by deferring to the ECMAScript `Number::toString` algorithm, but that only makes the *emission* deterministic; it does not recover the decimal the engineer actually wrote, and it puts the most fragile part of the specification on the hot path of every hash we compute. Timestamps are the other trap: if a creation time is inside the hashed document then nothing is ever reproducible by construction, because the second run of the same experiment produces a different identity for identical content.

What breaks if we get this wrong is not a bug, it is the company. Customers hold evidence packages; §16 states plainly that changing the evidence *identity scheme* after customers hold packages is near-impossible. A canonicalizer that drifts between versions silently invalidates every archived Tier-A golden and every published pre-registration hash (§17 weeks 7-8), and it does so in a way that looks exactly like a physics regression. K3, the hard gate at end of week 3, is a statement about hash stability. There is no version of FarSight in which this decision is revisited cheaply.

## Decision

**1. Identity is SHA-256 over RFC 8785 (JCS) canonical JSON.** A hashed object is serialized via Pydantic v2 `model_dump(mode="json")`, canonicalized under the JCS profile (UTF-8, keys sorted by UTF-16 code unit, no insignificant whitespace, no trailing newline), and hashed. The identifier is the lowercase 64-character hex digest. The 8-character prefix is a display and directory-naming convenience only and is never accepted as a lookup key.

**2. No JSON floating-point numbers appear in any hashed document, ever.** This is stricter than "physical quantities are strings" and deliberately so: it removes JCS number serialization from our trust surface entirely. Only JSON integers within the exact-integer range are permitted (indices, counts, exponents, array shapes). Every physical quantity is a decimal string plus a unit:

```json
{"magnitude": "0.22", "unit": "m"}
{"magnitude": "-1.5503e-9", "unit": "kg m2 / s"}
```

The magnitude grammar is exact and validated:

```
decimal := "-"? int frac? exp?
int     := "0" | [1-9] [0-9]*
frac    := "." [0-9]+
exp     := "e" ("+" | "-") [0-9]+
```

No leading `+`, no leading zeros, no bare `5.` or `.5`, lowercase `e`, mandatory exponent sign. Validators normalize *syntax* only and reject anything outside the grammar. They never normalize *value*: `"0.220"` and `"0.22"` are different strings and therefore different objects, because significant figures are an engineering claim (a 22.0 cm aperture and a 22 cm aperture are different statements about what somebody measured). Quantity equality for hashing is string equality.

**3. NaN and Infinity are forbidden by validator in every hashed document.** Ignorance is structural, never numeric: it is an `Unknown` belief carrying a bounding assumption or a sweep declaration (ADR-004). Non-finite values may exist in raw channel arrays produced by a diverged run, which is a storage matter handled in ADR-011, never in a spec.

**4. Timestamps and human identity live outside the hash.** Each persisted object file has exactly two top-level keys:

```json
{
  "object":     { "schema_version": 1, "kind": "ScenarioTemplate", "...": "..." },
  "provenance": { "created_at": "2026-08-26T14:03:11Z", "frozen_by": "operator:jh",
                  "authorization": "attended", "tool_version": "0.3.1",
                  "draft_id": "018f..." }
}
```

`content_hash = sha256(JCS(object))`. The provenance block is not part of identity but is not unprotected either: the whole file is hashed by path in the package file manifest (ADR-007), so altering provenance is detectable at package level while never changing what the object *is*. Consequence stated bluntly: the hash does not attest to who froze the object. That attestation comes from the audit log (ADR-012) and, later, from a signature.

**5. Two-layer identity plus a pure derivation.**

```python
spec_hash  = sha256(JCS(runspec.object))
output_hash = sha256(JCS({"channels": {name: channel_hash, ...},   # sorted by name
                          "metrics":  metrics_doc_hash}))
experiment_hash = sha256(JCS({"design": design_hash,
                              "planner_version": "1",
                              "root_seed": "31415926535897932384626433832795028841",  # 128-bit,
                                                                   # decimal string (ADR-005 owns
                                                                   # the encoding; a hex string
                                                                   # would also fail rule 2's
                                                                   # decimal grammar)
                              "generation_rules": {...}}))
# and therefore, with no lookup table anywhere:
plan_run(experiment_hash_inputs, run_index) -> RunSpec -> spec_hash
```

`output_hash` is **a one-level Merkle root over the run's channel hashes plus its metrics document** — a tree of depth one, deliberately, not a deep tree. The package root hash (ADR-007) has the same shape one level up: a one-level Merkle root over a flat file manifest. Depth buys partial-subtree proofs we have no use case for, and costs the auditor the ability to reproduce a root with a hash function and a sorted list.

Because the planner is pure (§11) and every drawn value is written into the RunSpec before dispatch, `(experiment_hash, run_index) -> spec_hash` is a derivation, not a database join. This is what makes "replay run #4242 standalone" (AT-7) a two-line operation on an auditor's laptop. The claim has one honest boundary: the derivation is pure with respect to *FarSight's* code, but the transformation from seeded bits to a drawn physical value passes through the sampler library, whose stream stability across versions is ADR-022's subject. ADR-022 settles it: FarSight implements every transformation from bits to a drawn value in its own source over Philox raw words, so the derivation is pure with respect to every library we depend on, and its bit-level reproducibility is Tier A in the reference container and Tier B across platforms, on the same footing as every other float in the system. The archived draws (ADR-005) remain what makes replay independent of re-derivation at all.

**6. Draft to frozen lifecycle.** Draft objects carry a mutable `draft_id` (UUID, never hashed) and may be edited freely; LLM-assisted authoring is permitted here. `farsight freeze <draft-ref>` performs, in order: completeness validation (every adapter binding present, no silent defaults, every `ParameterBelief` carrying pedigree and validity envelope, every `Unknown` carrying a bounding assumption or sweep declaration); kernel-coverage attestation, which for a design declaring a `KernelSet` requires the `spice` extra and is refused rather than skipped when it is absent (ADR-016 decision 4); reference resolution, which **fails** if any referenced object is draft, or is named by an alias rather than a hash; canonicalization and hashing; an immutable write (ADR-011); and an audit row recording the freezing human. `--yes` exists for CI but stamps `authorization: unattended`, and a package containing an unattended freeze of a design-plane object fails `evidence_grade` verification. Freezing is idempotent: refreezing identical content yields the identical hash and writes nothing.

**7. Names are mutable aliases, git-style.** `refs/<namespace>/<name>` maps to a content hash in the alias registry (ADR-011). Alias updates append audit rows and never mutate objects. A schema-level `Ref` type accepts only 64-hex digests, so an alias cannot syntactically appear inside a frozen document. A `Ref` is 64 lowercase hex with no algorithm prefix. Fields that are not `Ref`-typed but hold a digest — `kernel_set_hash`, `grid_hash`, `source_artifact_sha256`, `traceback_sha256`, and every entry of `hashes/file_hashes.json` — use the same bare 64-hex form. The `sha256:` prefix appears only in human-facing CLI output and in prose; no hashed document ever contains it. This is the mechanical form of the plan's immutability invariant: **nothing frozen may reference anything mutable or draft.**

## Options considered

### Option 1 — SHA-256 over JCS JSON, decimal-string quantities — CHOSEN
Human-readable objects an auditor can open in a text editor, JSON Schema exports usable without Python, an RFC to point at when asked "whose canonicalization", and no floating-point ambiguity because floats are excluded rather than specified.

### Option 2 — UUID identifiers plus a detached SHA-256 file manifest — REJECTED
Stated at its strongest, this is not "trust our server": it is what most artifact repositories do. Objects carry UUIDs in a local SQLite store (ADR-011 chooses SQLite anyway, so no server is implied), and integrity comes from a detached manifest of file digests shipped alongside. The auditor's hash check survives intact, tamper evidence survives intact, AT-3 still passes, and the canonicalizer, the JCS property suite and the decimal-string authoring friction all disappear — a genuinely large saving in week 1. Rejected for what it loses rather than for what it risks: identity stops being a function of content, so deduplication becomes a database concern rather than a free property, and — decisively — `(experiment_hash, run_index) -> spec_hash` stops being a derivation. Replaying run #4242 becomes a lookup in a table the auditor does not have, which turns AT-7 from arithmetic into a database restore. The manifest also proves that a file has not changed since *we* wrote the manifest; it does not let two parties who never met agree on what an object is.

### Option 3 — Deterministic CBOR or dag-cbor — REJECTED
The canonical form is defined by the encoding itself, so key ordering, Unicode escaping and number representation stop being our problem. This is the technically cleaner answer and §19 risk 4 already names it as the fallback if the JSON canonicalizer property suite proves fragile. Rejected for MVP because the package must be inspectable without our tooling: an auditor opening `runspec_4242.json` in Notepad is a real step in the ≤2 hour audit path, and shipping JSON Schema for third-party validation (§7) is only useful if the documents are JSON.

### Option 4 — Canonicalize, then use git as the object store — REJECTED
The naive form of this option ("git hashes incidental formatting, so identical specs get different identities") is defeated by our own design: we canonicalize *before* writing, so the bytes are canonical and `git hash-object` over them is a stable content address with the same semantics we are building by hand. Taken at its strongest, then, git offers identical identity semantics *plus* packfile deduplication, replication, a refs model we are borrowing wholesale, and **signed tags** — which would close the non-repudiation gap ADR-012 currently leaves open with a no-op signer. That is a serious offer and it is cheap to adopt. Rejected on two operational grounds instead. First, it puts a `git` binary and a working repository in the auditor's path, and the audit target is a zip file, a plain Python session, and two hours (§13, AT-9). Second, `.npy` channel storage at 10k runs becomes an LFS problem — §11's scale check puts one campaign in the tens of thousands of files — and an auditor who must install and configure git-lfs before checking a hash has been handed a worse product, not a better one.

### Option 5 — Allow JSON floats, rely on JCS number serialization — REJECTED
JCS does specify float emission exactly, implementations exist in several languages, and it would remove the authoring friction of decimal strings, which is a real cost we are choosing to pay. Rejected because the specified emission still cannot recover the decimal the engineer wrote, cross-language agreement on float emission is precisely the fragile seam, and it would let a parameter's stated precision be silently rewritten by a round trip.

## Consequences

**Buys us:** a single 64-hex string that names any object anywhere, deduplication for free, replay addressing without a lookup table, tamper evidence with no server in the trust path, and an identity scheme that outlives the company because it is an RFC plus a hash function.

**Costs us:** authoring friction — engineers must write `"0.22"` rather than `0.22`, and importing an existing parameter table requires an explicit conversion pass with a declared precision. Every schema change is an identity change. A frozen object with a typo cannot be corrected, only superseded by a new object plus a pointer record. The canonicalizer becomes a company-critical component that needs the full Hypothesis property suite in week 1 (§23 item 1), before anything it protects exists.

**Forecloses:** stable identity across schema versions. The same experiment re-serialized under schema v2 has a different hash than under v1, so "this is the same object, newer schema" is not expressible as one identifier, and any future cross-version deduplication or "show me all versions of this spec" feature has to be built on explicit supersession edges rather than on identity. It also forecloses in-place annotation of frozen objects forever: a reviewer's note about a frozen `MetricSpec` can never live on that object, only in a separate context-plane record that a naive reader will not see.

Two further foreclosures are stated bluntly because they are easy to leave buried in the body. **For the MVP's entire life, no FarSight artifact attests to who produced it.** The hash proves that content matches a digest; combined with ADR-012's no-op signer and its own admission that an operator with write access can rewrite the audit chain, a tampered package whose root hash has been recomputed is indistinguishable from a genuine one to any recipient who does not independently hold the original hash. "Content-addressed and independently re-executable" is the honest phrase (§12); "cryptographically traceable" is not available to us and must not be said. And because `"0.220"` and `"0.22"` are different objects, **deduplication and "have we run this already?" are syntactic, not semantic**: importing a customer parameter table with inconsistent trailing zeros silently produces duplicate campaigns at full compute cost, and nothing in the system will point this out.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| SHA-256 over RFC 8785 (JCS) canonical JSON as the identity function | 0.9 | The week-1 Hypothesis suite finds a JCS disagreement against an independent implementation that cannot be closed in two days — fires the §19 risk-4 fallback to deterministic CBOR with the rest of this record unchanged |
| No JSON floats in any hashed document; quantities are decimal string + unit | 0.85 | At least 2 of the 8 K5 interviews (wk 6) name decimal-string authoring as a reason they would not adopt, **or** the wk-2 import of the DSN 810-005 parameter tables costs more than one dev-day of precision-declaration work. The fix in either case is an authoring importer with declared precision, never a loosening of the hashed form |
| Significant figures are semantic: `"0.220"` != `"0.22"` | 0.8 | The wk-4 DSN benchmark or the wk-6 campaign produces two campaigns that differ only in trailing zeros, i.e. the syntactic-dedup cost has been paid for real |
| Timestamps and freezing identity live outside the hash | 0.9 | At least 3 of the 8 K5 interviews (wk 6) name "who produced this package, provably" as a precondition — this changes dedup semantics and must be decided before packages ship in wks 7-8, never patched in afterwards |
| `(experiment_hash, run_index) -> spec_hash` is a pure derivation | 0.75 | A cross-platform `--verify-derivation` difference exceeding one ULP in a drawn value, or any same-container mismatch, at week 5 — either means the derivation is not pure even with the library axis removed |
| Draft-to-frozen lifecycle with human freeze authorization | 0.85 | The wk-4 single-run package or the wk-6 campaign needs more than one `--yes` unattended freeze of a design-plane object, which means the attended-freeze rule is being routed around |
| `Ref` accepts only 64-hex digests, so aliases cannot appear in frozen documents | 0.8 | The wk-3 metric-registry freeze cannot express ADR-009's metric and referent references as digests — the `name@version` form used in that record's examples is, as written, syntactically impossible here, and one of the two must give |

## Enforcement

1. `test_canonical_hash` (unit tier, every commit, Windows and Linux; **first green by week 1**): Hypothesis property suite asserting hash invariance under dict key insertion order, nested reordering, and a process boundary; asserting rejection of NaN, +Inf, -Inf, `-0.0`, and any JSON float in a hashed model; asserting decimal-grammar round trips to 1 ULP where a float interpretation is taken (ADR-008).
2. `ci-hash-goldens` (every commit; **first green by week 1**): re-canonicalizes the archived fixture *objects* in `tests/golden/objects/` and fails if any recorded digest changes. This is the tripwire for silent canonicalizer drift and it fails loudly on a dependency bump. It is a distinct job from `ci-golden-regold-guard` (defined in ADR-006), which guards *numeric* goldens; this one never looks at a physical value.
3. `no_json_floats` validator on the hashed-model base class, plus a schema-export lint that fails the build if any exported JSON Schema for a hashed model declares a numeric type other than integer (**first green by week 1**).
4. `test_freeze_protocol` (**first green by week 2**, with the design-plane completeness clauses landing as the `design` schema pack does): freezing a draft that references a draft, an alias, a missing pedigree, or an `Unknown` without a bounding assumption must raise and name the offending field path; refreezing identical content must produce an identical hash and write nothing.
5. `Ref` field type rejects any string that is not 64 lowercase hex characters, so alias leakage into frozen documents is a validation error rather than a review finding (**first green by week 1**).
6. import-linter contracts `schemas_is_leaf` and `auditor_boundary` (defined in ADR-013; **first green by week 1**, in CI from the first commit per §6): `farsight.schemas` imports nothing internal at all — `farsight.hashing` included — and `farsight.hashing` imports only `farsight.schemas`; neither ever imports `farsight.engines`, so the canonicalizer is installable and testable with zero engine extras.
7. `farsight evidence verify` (defined in ADR-007; **first green by week 4**, with the single-run package v0) recomputes every object hash in a package and exits nonzero naming the first mismatching file.
8. `PARTIALLY MECHANIZED: PREC-1` — the magnitude grammar is validated mechanically, but no validator can check that the *stated precision is the honest one*. `"0.220"` and `"0.22"` are both well-formed; only a human knows whether the source measured three significant figures or two, and rule 2 makes that difference an identity difference. Residue: the correspondence between a magnitude's significant figures and its cited source. Substituted by review-checklist item **PREC-1** — *"every magnitude introduced or edited in this object was checked against its cited source, and its significant figures are the source's, not the author's typing"* — which lands in `review_signoffs` on the frozen `ExperimentDesign` (ADR-000) and is required before an `evidence_grade: evidence` package will verify. **First green by week 1** for the magnitude-grammar validator; week 4 for the `review_signoffs` gate inside `farsight evidence verify` (defined in ADR-007).
9. `PARTIALLY MECHANIZED: FREEZE-1` — `--yes` stamps `authorization: unattended` mechanically, and a package containing an unattended freeze of a design-plane object fails `evidence_grade` verification mechanically. What cannot be checked is that an `attended` stamp is true: the operator asserts it. Residue: the truth of the attended claim. Substituted by review-checklist item **FREEZE-1** — *"the human named in `frozen_by` was present at this freeze and reviewed the completeness report"* — landing in `review_signoffs` (ADR-000). **First green by week 2** for the stamp and the schema field; **week 4** for the `verify` gate.

## References

- RFC 8785, JSON Canonicalization Scheme (JCS): https://www.rfc-editor.org/rfc/rfc8785
- FARSIGHT_FOUNDATION_PLAN.md §4 (immutability invariant, freeze validates completeness and records the freezing human, LLM-assisted drafting permitted at draft stage), §7 (canonical serialization, decimal strings, NaN/Inf forbidden, two-layer identity, unhashed provenance block, migration on read), §12 (determinism rules, terminology note), §16 item 2 (identity scheme cannot change after customers hold packages), §19 risk 4 (canonicalization edge cases, CBOR fallback), §21 gate K3, §23 item 1, decisions D4 and D5.
- Acceptance tests served: AT-3 (tamper detection names the item), AT-6 (no point value for a flagged unknown), AT-7 (standalone re-execution of run #4242), AT-8 (metric version consistency).
- ADR-000, ADR-004, ADR-005, ADR-006, ADR-007, ADR-011, ADR-012, ADR-013, ADR-014, ADR-016, ADR-022.
- PLAN AMENDMENT REQUESTED: §4 — this record's checklist items `PREC-1` and `FREEZE-1` are discharged by rows in a `review_signoffs` field on the frozen `ExperimentDesign` and on `EvidencePackage`, which §4 and §13 do not currently carry. The amendment is stated once, in ADR-000's References, and is relied on here rather than restated as a second request.
