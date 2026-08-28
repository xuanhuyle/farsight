# ADR-006 — Reproducibility tiers A/B/C and determinism rules
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §12, §14 items 5-8, §19 risk 5, §21 (gate K3 and the standing reproducibility kill); decision D13
**Related ADRs:** ADR-000 (the `NOT MECHANIZABLE:` / `PARTIALLY MECHANIZED:` tokens this record's Enforcement uses), ADR-001 (a tier claim is always a claim about one named content hash), ADR-002 (process isolation is what lets us pin threads=1 per run), ADR-003 (engine facts are stated once there, not restated here), ADR-005 (seed derivation is what makes a single run independently re-executable), ADR-007 (tier claims are stamped per run set in the package manifest, and review sign-offs land there), ADR-008 (compensated summation and worker environment pins are the numerical half of these rules), ADR-011 (byte-stable `.npy` channels are what "bitwise" is measured over), ADR-014 (the pinned toolchain and `uv.lock` hash), ADR-019 (the reference container is what the Tier-A environment predicate actually resolves to), ADR-020 (the sample grid a Tier-B comparison epoch indexes into)

## Context

FarSight's commercial claim compresses to one sentence: here is an evidence package, re-execute it yourself and check. The forcing question is what "the same result" means when the auditor's machine is not ours. The answer determines the manifest schema, the CI matrix, and what `farsight evidence replay` is permitted to assert, so it must be settled before the schema pack lands in week 1.

The verified facts are unkind. Bitwise reproducibility is achievable, but only single-threaded, in the same container, on the same CPU ISA feature set. It is broken by threaded BLAS reduction order, FMA contraction, `-ffast-math`, libm differences across operating systems, and runtime CPU dispatch, where an AVX2 kernel and an AVX-512 kernel are simply different programs. We develop on Windows and ship evidence from a pinned Linux container, so we cross at least one of those lines daily (§19 risk 5). The engines contribute their own limits, stated once in plan §5 and once in ADR-003 and not restated here; the operative consequence for this record is that replay-from-RunSpec is the only checkpoint model available to us.

What breaks runs in both directions. Overclaim — stamp "bitwise" on a result that is really tolerance-bounded — and nightly CI goes red the first time the runner fleet changes silicon, at which point nobody can separate "FarSight has a bug" from "different CPU", and gate K3 becomes unpassable for undiagnosable reasons. Underclaim — quote tolerances everywhere, never assert an exact hash — and AT-3 dies: tamper evidence *is* exact-hash comparison, and a tolerance test cannot distinguish a flipped byte from platform drift. Two fatal failure modes with opposite fixes is why tiers exist.

A fourth thing breaks quietly and is the reason this record also owns golden provenance. Plan §14 item 5 states a hard rule — a golden number may never originate from our own code — and states it as a rule, not as an artifact. A rule with no artifact is a rule nobody can audit, and the first person to try is the week-8 external engineer.

## Decision

Three named tiers. Every claim carries exactly one, stamped per run set, and the tier bounds what the verifier may assert.

**Tier A — replay identity.** Same container image digest (or a byte-identical pinned environment), same CPU ISA feature set, `threads=1`, same engine builds. Asserts **bitwise-equal output hashes**, machine-checked by `farsight evidence replay --tier A`. Claimed for SPICE geometry, the link chain, metric recomputation, and single Basilisk runs. The pinned Linux container is the canonical Tier-A platform; what that container is, and how it is pinned, is ADR-019's decision, not this one.

**Tier B — portability envelope.** Across OS, CPU vendor and compiler. Asserts per-metric stated tolerances **at defined comparison epochs**, never at the end of a chaotic horizon. Each tolerance is absolute plus relative with a one-line rationale (ADR-008). Verified by the cross-platform matrix and the weekly second-machine replay.

**Tier C — cross-engine agreement.** Matched-configuration declaration plus physically motivated per-channel tolerances. Never bitwise. Every element that could not be matched is enumerated in the package as an unmatched item with expected divergence direction and magnitude.

Tier claims are data, not prose. Every quantity in them is a `Quantity` document with a decimal-string magnitude, because `manifest.json` is package content covered by the root hash and no hashed document may contain a JSON float (ADR-001):

```json
{"tier_claims": [
  {"run_set": "dsoc_link_epistemic_grid", "tier": "A",
   "environment_fingerprint_hash": "<64-hex digest>",
   "asserts": "bitwise_equal_output_hash"},
  {"run_set": "dsn_rf_anchor", "tier": "B",
   "comparison_epochs": ["2024-04-08T00:00:00Z"],
   "tolerances": [{"channel": "link.pt_over_n0",
                   "atol": {"magnitude": "0.05", "unit": "dB"},
                   "rtol": {"magnitude": "0", "unit": "1"},
                   "rationale": "platform float drift budget, not the physical link tolerance"}]}]}
```

The epoch strings shown here are the human-readable spelling; the canonical epoch representation inside a hashed document is ADR-015's decision, and this record consumes it rather than defining it.

The environment fingerprint (§13) is the Tier-A predicate: container digest, OS and kernel, CPU model and ISA flags, Python version, `uv.lock` hash, engine build ids, and the thread-environment variables actually observed inside the worker. `replay --tier A` exits nonzero naming the mismatched field when the fingerprint is incompatible; it never silently downgrades to B.

**Determinism rules, binding on all FarSight code.** No hashed value may depend on run completion order, wall clock, `dict` or `os.listdir` iteration order, PID, or hostname. All aggregation over runs iterates in sorted `run_index` order with compensated summation. Workers are single-threaded, with thread limits set before the numeric stack imports. Timestamps live only in the unhashed provenance block, which is also why worker logs are not package content (ADR-012).

**The single most important regression test:** a 100-run experiment at `--workers 1` and at `--workers 8` must produce **identical evidence root hashes**. This record owns that job and names it `ci-worker-order-invariance`; ADR-002, ADR-005, ADR-009 and ADR-011 all cite it and none of them redefines it. It catches nearly every violation above as one red build.

**Golden-hash policy.** Per-platform golden trees from day one (`tests/golden/linux_container/`, `tests/golden/windows/`), with container hashes normative. A Windows-only mismatch is a Tier-B finding; a container mismatch is a Tier-A defect and blocks merge.

**Golden provenance attestation.** Plan §14 item 5's hard rule — a golden number may never originate from our own code — becomes a required artifact rather than a norm. Every file under `tests/golden/` carries a sibling sidecar:

```json
{"schema_version": "golden_attestation/1",
 "golden_path": "tests/golden/linux_container/dsn_rf_anchor/link.pt_over_n0.npy",
 "source": "horizons_response",
 "source_artifact_sha256": "<64-hex digest>",
 "obtained_by": "<human identity>",
 "obtained_on": "<date>",
 "note": "one sentence saying which field of the cited artifact the value was read from"}
```

`source` is one of exactly four values: `horizons_response`, `cited_paper`, `hand_calc_notebook`, `second_library`. There is deliberately no `farsight_output` member, so the rule is enforced by the absence of a way to express its violation. `source_artifact_sha256` must resolve to a hash-pinned `DataArtifact` in the repo's fixture manifest — the artifact itself, not a number copied out of it, because per plan §14 item 5 the number must not live in prose either.

**Re-golding discipline.** Any golden change requires an `EXPECTED-CHANGE` note giving the physical or numerical reason, reviewed by a second developer, and a re-issued attestation. CI fails on silent golden changes. This is the tolerance-inflation kill (§21) in mechanical form: allowed count of undocumented loosenings is zero.

**Richardson-style discrimination for Tier C.** Run both engines at step `tau` and `tau/100`. If the delta shrinks, it is integration error. If it does not, it is model mismatch that must map to a declared unmatched item, or it is a defect and the comparison does not ship.

**Terminology.** We say "content-addressed, independently re-executable", not "cryptographically traceable", until a signing identity exists (ADR-012). Hashes prove self-consistency and integrity against a hash someone independently holds; they say nothing about who produced the package or when.

## Options considered

### Option 1 — One tier: bitwise or it does not count — REJECTED
Maximally strong, trivially explained, ungameable by a salesperson. Rejected because it is false where we need it most: Tier-C cross-engine agreement can never be bitwise even in principle, and neither can replay on an auditor's laptop given libm and CPU-dispatch variation. A rule physics cannot satisfy gets quietly ignored, which is worse than honest gradations.

### Option 2 — Tolerance-bounded everywhere, no bitwise claim — REJECTED
Removes the brittle dependency on container digests and ISA flags and would make CI far more stable across runner churn. Rejected because it destroys tamper evidence: AT-3 requires a flipped byte to fail loudly and by name, and a tolerance comparison cannot see one. It would also let genuine regressions hide inside a tolerance band.

### Option 3 — Two tiers, merging portability and cross-engine — REJECTED
Simpler manifest; tempting because both non-bitwise tiers reduce to "a number with a tolerance". Rejected because the provenance of the tolerance differs in kind. A Tier-B tolerance is a floating-point argument and should shrink as engineering improves; a Tier-C tolerance is a physics argument and legitimately does not. Merging them lets model mismatch be excused as rounding, which is the dishonesty we claim to prevent.

### Option 4 — Hermetic build (Nix or equivalent) as the whole answer — REJECTED for MVP
The strongest form of this is not "use Nix for the container": it is a fully hermetic, content-addressed build of the entire numeric stack, which would make the Tier-A predicate a single derivation hash instead of a five-field fingerprint and would remove container drift, base-image CVE churn and the ISA argument in one move. This is plausibly what a mature FarSight looks like, and it is a better answer than ours on the merits. Rejected for eight weeks on schedule and platform grounds: GMAT installs as an application tree rather than a package, Basilisk ships prebuilt wheels we do not want to rebuild, and we develop on Windows where hermetic tooling is weakest. The adoption cost lands in weeks 1-2, which are fully committed to the schema and hashing core. The cost of rejecting it is that Tier A stays defined by a fingerprint we must maintain by hand.

### Option 5 — Three tiers, stamped per claim — CHOSEN
Matches the physics of each claim, keeps exact-hash tamper evidence where it is achievable, and forces "which tier is this, really?" to be answered at freeze time rather than in front of an auditor.

## Consequences

**Buys us:** an auditor-legible answer to "what should I expect when I re-run this"; exact tamper evidence where physically available; a diagnosis path when replay fails, since tier mismatch is reported as a named fingerprint field rather than a generic error; mechanical honesty tripwires around tolerances and goldens; and, via the attestation sidecar, the first artifact in the set that makes plan §14 item 5 checkable by someone who does not trust us.

**Costs us:** three tiers to explain in every sales and audit conversation and to maintain in schema, CLI and CI; a cross-platform matrix plus duplicated per-platform golden trees from week 1; a second file to author and re-author beside every golden; and real friction on every legitimate numerical improvement, which now requires a documented re-golding.

**Forecloses:** multi-threaded execution inside a run for the whole MVP, threaded BLAS included — a genuine throughput loss on linear-algebra-heavy work, and the door to GPU acceleration closes without a formal tier revision. We can never claim bitwise reproducibility across operating systems, so a Windows-only customer is permanently a Tier-B customer and must be told so. Because Tier A is defined by container digest, any base-image security update invalidates existing Tier-A goldens and forces a re-golding cycle on someone else's schedule. And the attestation rule forecloses ever pinning a golden for a quantity no external source publishes: if no Horizons response, paper, hand-calc or second library covers a channel, that channel simply has no golden, and its regression protection drops to a Tier-B tolerance we chose ourselves.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Three tiers rather than one or two, stamped per run set | 0.90 | `ci-worker-order-invariance` or `ci-tier-a-bitwise` is red on three or more separate days before K3 (end wk 3) for causes traced outside FarSight code, meaning the tier boundary is drawn in the wrong place. |
| Tier-A predicate is container digest plus CPU ISA feature set | 0.70 | K3 (end wk 3) cannot be passed twice in a row without pinning the CI fleet to one silicon generation, or the week-1/2 CI matrix shows two ISA generations among the runners we actually have. Either fires a re-definition of Tier A against a normalized numeric environment (ADR-019) rather than raw silicon. |
| Determinism rules: sorted `run_index` order, compensated summation, threads=1 | 0.92 | The 10k-run overnight target fails after one optimization pass at the week-6 gate (§21 throughput kill), which forces deliberate re-examination of threads=1 rather than a quiet exception. |
| Golden-hash policy, including the four-source attestation | 0.80 | Any golden required in weeks 1-4 has no admissible source among the four — that is, the only way to pin the channel is to run our own code — which means the enumeration needs a fifth member or that channel loses its golden. |
| Richardson discrimination as the Tier-C method | 0.75 | K4 (post-MVP, when GMAT lands): the two-body-plus-J2 arc cannot be classified as integration error or model mismatch by the shrink/no-shrink test within the ≤1 dev-week matching budget, which means the method does not survive contact with a real second engine. |

Failure to achieve Tier-A bitwise replay for the pure-Python link chain within two calendar weeks of first attempt is not a revisit trigger for any row above. It fires the standing reproducibility kill (§21).

## Enforcement

1. `ci-worker-order-invariance` (defined here; owned by this ADR): runs the 100-run reference experiment at `--workers 1` and `--workers 8` and fails unless evidence root hashes are byte-identical. **First green by week 5** — it needs the pool, the ledger and the package builder, none of which exist before the week 5-6 campaign machinery. It does not run "on every commit" until then, and saying otherwise would be a claim about a job that cannot execute.
2. `ci-tier-a-bitwise` (pinned container): rebuilds the reference package twice, once after a container restart, and fails on any channel or root hash difference. Gate K3 in mechanical form. **First green by week 3**, which is what K3 dates it to; every commit thereafter.
3. `ci-crossplatform-matrix` (nightly, Windows + Linux): recomputes Tier-B metrics at declared epochs and fails on any excursion; a metric compared with no declared tolerance is itself a failure. **First green by week 4**, when the DSN anchor supplies the first metrics with published tolerances.
4. `ci-golden-regold-guard` (every commit): fails when any file under `tests/golden/` differs from its merge base without a matching `EXPECTED-CHANGE` entry naming the file and giving a rationale, or without a re-issued attestation sidecar. Second-developer review is enforced by CODEOWNERS on `tests/golden/`. **First green by week 2**, when the first goldens land.
5. `test_determinism_rules` (unit tier, every commit; **first green by week 1**): AST-scans `src/farsight/` outside `analysis/` and fails on `datetime.now`, `time.time`, `os.getpid`, `socket.gethostname` and `os.listdir`, plus a runtime assertion that each worker observes single-threaded limits.
   PARTIALLY MECHANIZED: the unsorted-iteration half. Deciding whether a `dict` or `set` iteration is reachable from a hashed value is interprocedural taint analysis over dynamically dispatched Python; it is not decidable in general and it is certainly not a unit-tier test. The check therefore does not attempt reachability. It bans unsorted `dict`/`set` iteration everywhere in `src/farsight/` outside `analysis/`, with an explicit per-site allowlist where each entry carries a one-line reason. The residue runs in both directions: false positives on iterations that could never reach a hash, which we absorb by allowlisting, and false negatives on order-dependence arriving through a library we do not scan. Review checklist item **DET-1** — "every allowlisted unsorted iteration is argued not to reach a hashed value" — carries the residue. A DET-1 row naming a reviewer and a date is recorded per release and copied into the `review_signoffs` list of every package built by that release (ADR-007).
6. Schema validation in `evidence/verifier` (**first green by week 4**, with the first `verify`): a claim with `tier: A` and no complete `environment_fingerprint_hash`, or `tier: B`/`C` without both comparison epochs and per-channel tolerances carrying rationale strings, fails verification with a nonzero exit naming the claim. A tolerance expressed as a JSON float rather than a `Quantity` fails the same validator (ADR-001).
7. PARTIALLY MECHANIZED: Richardson discrimination. The two-step-size run pair and the shrink/no-shrink classification are automated in `comparison/` — **first green by week 6 for the schema and classifier**; the cross-engine execution is post-MVP with GMAT, per plan §14 item 7, and no CI job asserts it before then. The judgment "this non-shrinking residual maps to declared unmatched item X" is irreducibly human. Review checklist item **CC-3** — "every non-shrinking cross-engine residual is mapped to a named unmatched configuration item or filed as a defect" — substitutes. What is mechanized is the *presence* of the sign-off: a CC-3 row naming reviewer and date must appear in the `review_signoffs` list of any `EvidencePackage` carrying a Tier-C comparison, and `verify` fails an `evidence_grade` package whose Tier-C comparison has no CC-3 row (ADR-007).
8. PARTIALLY MECHANIZED: `ci-golden-attestation` (every commit; **first green by week 2**). Mechanical half: every file under `tests/golden/` must have a sibling `<name>.attest.json` that validates against the attestation schema, whose `source` is one of the four admissible values, and whose `source_artifact_sha256` resolves to a hash-pinned `DataArtifact` in the repo's fixture manifest. A golden without an attestation fails the build; so does an attestation naming a source the manifest does not contain. Residue: no check can confirm that the cited artifact actually contains the number, only that a citation exists and resolves. Review checklist item **GOLD-1** — "the attested source was independently opened and the golden value read from it" — substitutes. GOLD-1's auditable record is the attestation's own `obtained_by` and `obtained_on` fields, which are the `review_signoffs` shape applied to a repository artifact; where a golden is cited by a shipped package, the same row is copied into that package's `review_signoffs`.

## References

- FARSIGHT_FOUNDATION_PLAN.md §12 (tier definitions, determinism rules, terminology note), §13 (`environment/fingerprint.json`, per-run-set tier claims), §14 item 5 (a golden number may never originate from our own code; admissible sources), items 6-8 (regression pinning and re-golding, cross-engine methodology and Richardson discrimination, deterministic replay tests), §19 risk 5 (Windows-dev / Linux-container skew), §21 gate K3 plus the reproducibility and tolerance-inflation kills, acceptance tests AT-1, AT-2, AT-3, AT-4, AT-7, AT-12.
- Verified fact pack (2026-08-26): bitwise reproducibility achievable single-threaded, same container, same CPU ISA; broken by threaded BLAS reduction order, FMA contraction, `-ffast-math`, libm differences across OS, and runtime CPU dispatch (AVX2 vs AVX-512). Engine facts are not restated here; see plan §5 and ADR-003 References.
- Cross-tool comparison precedent: GMAT's V&V program, which plan §1 names as the source of the cross-tool comparison methodology FarSight productizes. UNVERIFIED — the specific benchmark tools and any document identifier are not stated in the plan; confirm before citing either externally.
- **PLAN AMENDMENT REQUESTED: §14 item 5** — the golden-provenance rule gains a required artifact. Every file under `tests/golden/` must carry a `<name>.attest.json` sidecar naming one of four admissible sources and the SHA-256 of the source artifact, lint-checked for presence and resolution by `ci-golden-attestation`. The plan states the rule and names no artifact, so nothing in the set currently enforces or records it; this is the smallest change that makes the rule auditable by a stranger.
- ADR-000, ADR-001, ADR-002, ADR-003, ADR-005, ADR-007, ADR-008, ADR-011, ADR-012, ADR-014, ADR-015, ADR-019, ADR-020.
