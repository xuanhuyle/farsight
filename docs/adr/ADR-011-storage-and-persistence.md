# ADR-011 — Storage: files, `.npy` channels, and a SQLite ledger only
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §7 (bulk run output, canonical array bytes, versioning and migration), §11 (ledger, resume, cancellation), §13 (package layout), §16 items 1 and 4, §12 (determinism rules); decision D10
**Related ADRs:** ADR-000 (the escape-hatch tokens this record's Enforcement uses), ADR-001 (hashes are over bytes-as-written, which is a guarantee this layer must make true), ADR-002 (workers write files and never touch the database), ADR-005 (seed archives are per-run files), ADR-006 ("bitwise" is measured over these channel bytes, and `ci-worker-order-invariance` is defined there), ADR-007 (the package layout this store feeds, including the per-run `channels_manifest.json`), ADR-012 (the hash-chained `audit_log` table is defined there and shares this SQLite file), ADR-013 (`analysis` is quarantined, which is what keeps pandas and matplotlib out of the truth loop; pyarrow is kept out by ADR-014's allowlist), ADR-014 (the base install's dependency set is what verification is allowed to need, and the allowlist test lives there), ADR-020 (channel names become file names, so the name grammar is a storage constraint), ADR-023 (the run-outcome taxonomy the ledger `status` column enumerates)

## Context

The forcing question is narrow: **what is on disk, such that hashing a stored channel is hashing the numbers rather than hashing some library's opinion about how to lay them out?** Everything downstream depends on the answer. Tier-A bitwise claims (ADR-006) are claims about these bytes. Tamper evidence (AT-3) requires that one flipped byte be attributable to one named file. Resume after `kill -9` at 50% of a 10k-run campaign must produce channel and metric hashes identical to an uninterrupted campaign (AT-4), which is a statement about crash semantics, not about storage format.

The constraints are concrete. Verification must run on a base install with zero engine extras (ADR-007), so any format requiring a heavyweight reader is disqualified from holding the record. Workers are separate OS processes on Windows and Linux (ADR-002), so multi-writer coordination is a real problem and not a footnote. Reductions must be order-independent (§12), so the storage layer must not make results depend on which worker finished first. And customers hold packages whose hashes were computed once and must verify forever (§16), so a storage format change is not a migration, it is an invalidation.

What breaks if we get this wrong is subtle and late. A container format whose bytes depend on writer version means a dependency bump silently re-golds every Tier-A hash, which looks exactly like a physics regression and burns days to diagnose. A crash model that leaves half-written files indistinguishable from good ones means resume produces a package that verifies and is wrong. Both failures surface in front of an auditor, not in CI.

## Decision

**1. Three stores, with strictly separated roles.**

- **Object store (files).** Frozen content-addressed documents at `objects/<first2>/<hash>.json`, each file being the two-key `{"object": ..., "provenance": ...}` envelope of ADR-001.
- **Channel store (files).** One `.npy` per (run, channel) at `runs/<shard>/<run_index>/channels/<name>.npy` in the working store, flattened to §13's `runs/channels/<i>/<name>.npy` at package build time.
- **Ledger (SQLite, WAL).** One file per workspace, `registry.sqlite`, holding **only** the run ledger, the alias registry, and the append-only audit log. No evidence content ever lives here.

A fourth store — the content-addressed kernel cache — is ADR-016's, not this record's; it is named here only so that "three stores" is not read as an exhaustive claim about the workspace.

**2. Channel files are maximally boring, and the channel hash does not depend on the container.** Only NPY format 1.0, dtype `<f8` (little-endian IEEE-754 float64), C-order, `fortran_order: false`, no object arrays, `allow_pickle=False` on every read, enforced. The identity of a channel is the payload plus a FarSight-defined header document, never the file's own bytes:

```python
header = {"name": "link.pt_over_n0", "unit": "dB", "dtype": "<f8", "shape": [8640],
          "grid_hash": "<64-hex digest of the frozen sample_grid>"}   # ADR-020 decision 6
channel_hash = sha256(JCS(header).encode("utf-8") + b"\x00" + array.tobytes(order="C"))
```

The `.npy` file is *also* hashed by path in `hashes/file_hashes.json` for file-level tamper evidence, but nothing depends on NumPy's header byte layout being stable across versions, which we have not verified and are not going to bet the Tier-A goldens on. `channels_manifest.json` per run records name, unit, dtype, shape, `grid_hash`, `channel_hash`, `nonfinite_count`, and `first_nonfinite_index`, and ships in the package (ADR-007). The header carries `grid_hash`, the digest of the frozen `sample_grid` descriptor (ADR-020 decision 6), so a channel recomputed on a different time base is a hash difference rather than a silent pass.

**3. Non-finite samples are stored, flagged, and demoted.** NaN and Infinity are forbidden in hashed *specs* (ADR-001); a diverged run's channels are a physical fact and are stored as produced. Any channel with `nonfinite_count > 0` marks its run `diverged` and is excluded from Tier-A bitwise claims and from Tier-B cross-platform comparison, because NaN payload bits are engine and platform dependent. That exclusion is recorded in the manifest rather than assumed by the reader.

**4. Atomic writes, with an explicit crash model.** Every file write is: create `<final>.tmp.<pid>.<counter>` in the same directory, write, `flush()`, `os.fsync(fileno())`, close, `os.replace(tmp, final)`, then `fsync` the directory file descriptor on POSIX. Windows offers no directory fsync, so the asymmetry is stated rather than papered over, and the crash model does not depend on closing it: **the ledger is the arbiter.** A channel file that exists on disk but has no committed `ok` row is garbage, and `resume` re-executes that run. Recovery therefore never has to guess whether a file is complete.

**5. Workers never write to SQLite.** Each worker writes its channel `.npy` files, the per-run `channels_manifest.json`, and one `status_<i>.json` result record — the file plan §13 and ADR-007 name — atomically, then returns a small record over the pool boundary. The parent process folds completed results into the JSONL manifest and the SQLite ledger **in sorted `run_index` order**, not in completion order. This buys three things at once: no multi-process SQLite write contention on Windows or on network filesystems, a crash model with a single writer, and worker-count invariance for free, which is exactly what `ci-worker-order-invariance` (defined in ADR-006) measures.

**6. SQLite is used for three tables and nothing else.** `journal_mode=WAL`, `synchronous=FULL`, stdlib `sqlite3` with hand-written SQL. No ORM, no SQLAlchemy.

```sql
CREATE TABLE runs (            -- the ledger (§11)
  experiment_hash TEXT NOT NULL, run_index INTEGER NOT NULL,
  spec_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN
    ('pending','running','ok','failed','diverged','crashed')),
  output_hash TEXT, wall_time_s REAL, worker_env_hash TEXT,
  PRIMARY KEY (experiment_hash, run_index));
CREATE TABLE aliases (         -- git-style mutable refs (ADR-001)
  namespace TEXT NOT NULL, name TEXT NOT NULL,
  target_hash TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (namespace, name));
CREATE TABLE audit_log (       -- hash-chained, append-only; columns are ADR-012's, reproduced not redefined
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, object_hash TEXT, detail_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL);
```

The `status` values are enumerated here because the column needs a `CHECK`; what each value *means*, which of them `resume` re-executes, and which participate in an aggregate are ADR-023's decisions, not this record's. `wall_time_s` is deliberately the only float in the schema and is never an input to any hash. The append-only JSONL manifest (the gmat-sweep pattern) is written alongside and is what ships in the evidence package; SQLite is a local index that can be rebuilt from the JSONL and the object store. Losing `registry.sqlite` costs an index rebuild, never evidence.

**7. Schema versioning is migration-on-read, and packages are never migrated in place.** Every persisted document embeds `schema_version`; migrations are pure `v_n -> v_{n+1}` functions in `schemas/versioning.py`, composed in sequence, applied on read only, and the migrated object is never written back over the original. Evidence packages are **never** rewritten, because the hash is over bytes-as-written and a customer holding the old root hash is holding an attestation about those exact bytes; rewriting them destroys the only thing the package was for. Correcting a published analysis means publishing a **new** package that references the old package's root hash as superseded. Old-version readers are kept alive and contract-tested against archived fixture packages.

**8. No PostgreSQL, and no PostgreSQL roadmap line.** The absence of the roadmap line is part of the decision: a stated intention to move to a server database causes people to write server-database-shaped code today. The ledger module exposes a narrow protocol so a different backend is possible later, but none is planned, scaffolded, or promised.

## Options considered

### Option 1 — Files plus one `.npy` per channel plus a SQLite ledger — CHOSEN
Byte-stable, readable in one line of NumPy, hashable with `sha256sum`, and it keeps the entire trust surface inside the standard library plus NumPy. The storage format is so dull that it cannot become an explanation for a hash difference.

### Option 2 — Parquet for channels — REJECTED
Genuine merit and the obvious answer at scale: columnar compression on 10k runs of float64 channels, predicate pushdown, and immediate readability from pandas, polars and duckdb, which is exactly where customer analysts live. The objection that would normally head this rejection — that Parquet bytes are not stable across writer versions, codecs and row-group boundaries — **does not survive decision 2 of this record**. Because a channel's identity is `JCS(header) || payload` and never the container's own bytes, a Parquet-stored column would hash identically to an `.npy`-stored one, and writer drift would move only the per-path entries in `file_hashes.json`. Stating that plainly costs us the loudest argument and leaves two that are sufficient. First, pyarrow is a large compiled dependency and it would land in the no-extras base install that `farsight evidence verify` must run in (ADR-007, ADR-013) — the auditor's install is the scarcest resource in this architecture, and a columnar engine is an expensive tenant in it. Second, it would be a second on-disk format to hold stable, to teach, and to keep a reader alive for forever: `.npy` stays the record so that "open the array in a plain Python session" remains one line rather than a dependency question, and so that exactly one format's reader must survive every schema version. Reconsidered at scale phase strictly as a derived analysis view generated inside the quarantined `analysis/` package (ADR-013), never as the hashed record.

### Option 3 — HDF5, one file per run or per campaign — REJECTED
The aerospace and scientific default, self-describing, hierarchical, chunked, and it would collapse the inode problem to one file. Rejected because h5py plus libhdf5 is a heavy compiled dependency in the verifier's path — the same defeater as Parquet, and here it is joined by a concurrency one: HDF5's concurrent-access story is poor precisely where our workers are concurrent. As with Parquet, the byte-layout argument is weaker than it looks under decision 2 and is not what the rejection rests on.

### Option 4 — One `.npz` per run — REJECTED
Fewer files by an order of magnitude, and one artifact to move per run. Rejected because extracting one channel requires zip machinery rather than a read, and because AT-3 requires a flipped byte to name one item — naming a member inside an archive means trusting our unpacker to do the naming. Reproducible zip is achievable, so the byte argument alone would not carry this.

### Option 5 — SQLite as the primary store, with channels as BLOBs — REJECTED
One transactional file, real crash semantics for free, no atomic-rename dance, and a single hash for the whole workspace. Genuinely tempting for the crash model alone. Rejected because it puts a storage engine between an auditor and the numbers, because a corrupted page fails the whole store rather than naming one item, and because it inverts the §13 package layout, which is a directory an auditor walks.

### Option 6 — PostgreSQL now, files as an export — REJECTED
Multi-user concurrency, cross-campaign queries, row-level security, mature backup tooling, and a natural path to a hosted product. Rejected because evidence packages are files (ADR-007), the MVP is a single-operator CLI with RBAC explicitly deferred (§16), and putting a server in the trust path contradicts the auditor-laptop requirement that is the commercial differentiator.

## Consequences

**Buys us:** hashing that means what it says; a channel readable by anyone with NumPy for as long as NumPy exists; crash recovery with a single arbiter and no ambiguity; worker-count invariance as a structural property rather than a discipline; and a base install small enough that verification is a plausible ask of a stranger.

**Costs us:** disk, uncompressed, at eight bytes per sample per channel, with no compression anywhere in the record. A file count that grows as runs times channels, mitigated by sharding run directories in the working store but not eliminated — and at the flagship's own sampling plan this is thousands of runs times a dozen channels, which is a number we have not yet measured on NTFS. A parent process that is the single ledger writer and therefore a serialization point and a single point of failure mid-campaign. Hand-written SQL with no ORM ergonomics. And the atomic-write discipline must be obeyed by every write path in the codebase, forever, including the ones written in a hurry at week 7.

One thing this design does *not* cost us, contrary to how it is easy to write: because the channel hash is decoupled from the container (decision 2), a later move to a columnar container would preserve every published channel hash and invalidate only the per-path entries in `file_hashes.json`. The format is durable, not metaphysically permanent, and overstating the lock-in would be a false cost.

**Forecloses:** cross-run querying over channel contents. There is no index over the numbers, so "find every run where margin dipped below 3 dB" is a full scan of the whole campaign's channel bytes, and it stays a scan until someone builds a derived view — at 10k runs that is a scan measured in gigabytes, every time, for every such question. It forecloses compression of the hashed record entirely and permanently: package size scales linearly with samples times channels times runs, forever, and self-contained closure adds the embedded inputs on top. It forecloses multi-machine campaign execution for the MVP, because the single-writer parent is a single-machine design; a distributed backend is a genuine rewrite of the runner and ledger seam, not a configuration flag.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Three stores with strictly separated roles | 0.90 | The kernel cache (ADR-016) or a fifth store needs transactional coupling to the ledger, which would mean the separation is not where the seams actually are. |
| `.npy` as the hashed channel record, with a container-independent channel hash | 0.85 | NumPy announces a change to `.npy` format 1.0 semantics for `<f8` arrays; or `test_channel_roundtrip` shows a platform-dependent `channel_hash`, which would mean the header document is under-specified. |
| `.npy` at flagship scale: file count, package size, `verify` wall-time | 0.70 | Week-4 measurement task (Enforcement 9): build a package for a scaled-down 960-run campaign, record bytes, file count, build wall-time and `verify` wall-time, extrapolate x10 and write the numbers into this record. It fires if the extrapolated self-contained flagship package exceeds 25 GB, or `verify` on the reference laptop exceeds 20 minutes against AT-9's two-hour total. Either forces a split between a small verifiable core and an addressable channel store, and it is likely to fire in week 7 on the flagship rather than at some later "scale phase". |
| Parquet rejected on install-surface and second-format grounds | 0.70 | The base install acquires a compiled columnar dependency for an unrelated reason, at which point the first surviving ground evaporates and the choice is re-made on the second alone; or analysis load times over a campaign dominate the working day, which argues for a derived Parquet view in `analysis/` and still not for changing the record. |
| Workers never write SQLite; the parent commits in `run_index` order | 0.88 | `ci-worker-order-invariance` (ADR-006) is red for a cause inside the ledger path, which would mean sorted-order commit is not sufficient for invariance. |
| SQLite WAL for the ledger | 0.80 | WAL corruption is observed on any CI, dev or reference machine; or ≥2 of the 8 K5 interviews (end wk 6) describe a network or virtualized filesystem as their normal working store. The fallback — JSONL-only with a rebuilt in-memory index — is already permitted by this design, so this trigger changes a default, not an architecture. |
| No PostgreSQL and, deliberately, no roadmap line | 0.85 | ≥3 of the 8 K5 interviews (end wk 6) describe running one campaign across more than one machine today, which is a deliberate re-examination of the single-writer parent and of ADR-002 together, not a database decision taken alone. |

## Enforcement

1. `test_channel_roundtrip` (unit tier, every commit, Windows and Linux; **first green by week 1**): write, read and re-hash arrays including empty, single-element, and non-finite-containing cases; assert `channel_hash` is invariant to the writing platform and to the NumPy patch version, and assert every read passes `allow_pickle=False`.
2. `ci-base-install-dependency-lint` (every commit, a leg of `env-guard`, ADR-014; **first green by week 1**): resolves the no-extras install from `uv.lock` and fails if `pyarrow`, `h5py`, `pandas`, `polars`, `sqlalchemy`, `spiceypy` or any engine distribution appears in it. A companion runtime test imports `farsight.evidence` and asserts none of those names appear in `sys.modules`. The allowlist itself is ADR-014's (`tests/unit/test_dependency_allowlist.py`); this job is the base-install leg of it and does not maintain a rival list.
3. `test_atomic_write` (**first green by week 1**): monkeypatches the write path to raise between write and rename and asserts the destination is either absent or the previous complete content, never partial; asserts `os.replace` is used rather than `os.rename` for overwrite semantics on Windows.
4. `test_crash_resume` (AT-4; **first green by week 5**, since it needs the runner and the ledger; nightly at scale and small-N every commit thereafter): kills workers mid-campaign, runs `resume`, and asserts channel hashes and the evidence root hash equal an uninterrupted run's.
5. `ci-worker-order-invariance` (defined in ADR-006; **first green by week 5**): the same 100-run experiment at `--workers 1` and `--workers 8` must produce identical evidence root hashes, which is the direct test of the "parent commits in `run_index` order" rule. This record does not redefine the job.
6. **`test_package_reader_compat`** (defined in ADR-007; **first green by week 4** in its one-version form, nightly): every archived fixture package from every prior schema version verifies using its embedded schemas and archived reader path; a package that requires in-place migration to verify is a failing test, not a migration task. In its one-version form it is nearly vacuous; it becomes load-bearing only when a second `schema_version` ships, which is not planned inside the MVP. This record supplies the migration-on-read policy the job tests and does not redefine the job.
7. **`test_audit_chain`** (defined in ADR-012; **first green by week 2**): recompute `row_hash` over every `audit_log` row and assert the `prev_hash` chain is unbroken; a gap or a rewritten row fails. ADR-012 owns the column definitions and the chaining rule; this ADR only guarantees the file they live in.
8. import-linter contract `analysis_quarantine` (defined in ADR-013; **first green by week 1**): nothing in the truth loop imports `farsight.analysis`, which is where pandas and matplotlib are permitted to live.
9. `bench_package_scale` (**due week 4**, a measurement task rather than a pass/fail gate): builds a package for a 960-run scaled campaign and records bytes, file count, build wall-time and `verify` wall-time; the numbers and their x10 extrapolation are written back into this record's Confidence table. A measurement with no scheduled date is an intention, so it has one.
10. PARTIALLY MECHANIZED: the atomic-write discipline (**lint first green by week 2**). `test_atomic_write` proves the shared helper is correct; it cannot prove that every write path in the codebase goes through the helper, because a direct `open(..., "w")` in a module written in week 7 is ordinary Python and a grep-based ban produces false positives on every legitimate temp write. The mechanical half is a lint that fails on `open(..., "w"|"wb")`, `Path.write_text`, `Path.write_bytes` and `np.save` anywhere in `src/farsight/` outside the single module defining the atomic-write helper (it lives under `registry/`, per plan §6's tree) and outside `analysis/`, with an explicit allowlist. Residue: a write performed by a library we call on our behalf, and an allowlisted site whose reason is wrong. Review checklist item **STORE-1** — "this write either goes through the atomic helper or provably cannot leave a partial file a reader could mistake for complete" — carries it, and a STORE-1 row is recorded per release and copied into the `review_signoffs` list of every package built by that release (ADR-007).

## References

- FARSIGHT_FOUNDATION_PLAN.md §7 (bulk run output as one canonical little-endian float64 `.npy` per channel, temp plus fsync plus atomic rename, "hashing the file is hashing the numbers", Parquet reconsidered at scale phase only, pyarrow dropped from the MVP trust surface, versioning and on-read migration, evidence packages never migrated in place), §11 (ledger schema, JSONL manifest, idempotent resume, partial results first-class, `ProcessPoolExecutor` with spawn), §12 (determinism rules, worker-count invariance test), §13 (package layout), §16 items 1 and 4 (offline-first, append-only hash-chained audit log, data and config separation), decision D10.
- Engine and platform facts relied on here (CSPICE global kernel pool requiring one instance per process; GMAT subprocess-per-run with file-based collection; bitwise reproducibility single-threaded on a fixed ISA) are stated once in plan §5 and §12 and restated once in ADR-003 References; they are not repeated in this record.
- Prior art adopted: gmat-sweep (license not stated in the plan; UNVERIFIED here), whose SHA-256 script manifests, resumable JSONL and subprocess isolation are the pattern generalized here platform-wide.
- **PLAN AMENDMENT REQUESTED: §6** — extras become `spice`, `basilisk`, `gmat`, `analysis`, `dev`. Enforcement item 2 denies `spiceypy` in the no-extras base install, which presupposes that it is an optional extra named `spice` rather than a core dependency; §6 lists extras as `basilisk, gmat, analysis, dev`. ADR-014 owns the dependency table.
- **PLAN AMENDMENT REQUESTED: §13** — the per-run `channels_manifest.json` written by decision 5 is package content that §13's layout does not list. The same amendment is requested in ADR-007, which owns the layout; it is named here because this record is where the file is produced.
- ADR-000, ADR-001, ADR-002, ADR-003, ADR-005, ADR-006, ADR-007, ADR-012, ADR-013, ADR-014, ADR-016, ADR-020, ADR-023.
