# ADR-024 — CLI surface, exit-code contract, and output modes
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §6 (the `cli/` package and its verb list), §13 (the audit path and the two-hour target), §16 (CLI only, no web UI; append-only audit log for every CLI mutation), §17 (weeks 1-2 exit gate: `farsight geometry`), §18 (AT-3, AT-9); decision D1
**Related ADRs:** ADR-000 (the escape-hatch tokens this record's Enforcement uses), ADR-001 (`freeze` and the alias registry), ADR-002 (`--workers`), ADR-004 (authorizing an `EpistemicCollapse` is a human act and therefore a command), ADR-005 (`--verify-derivation`), ADR-006 (`--tier` and what a tier refusal means), ADR-007 (the package format, the four-step audit path, and the generated report that prints these command names), ADR-008 (`--shadow-units`), ADR-009 (three-valued verdicts, and why a `fail` verdict is not a process failure), ADR-012 (owns the `audit_log` action enumeration this surface must cover exactly, `fetch kernel`, and `--require-signature`), ADR-018 (run composition, which is what `geometry` would become if it were expressible as a one-stage run), ADR-019 (the environment refusal this contract gives a code to), ADR-023 (owns the run-outcome taxonomy behind the work-remains code)

## Context

The CLI is the entire user interface - §16 rules out a web UI in the MVP and on the roadmap - and the audit path is a **product claim**: AT-9 says a competent outsider, given only the package, the CLI and the README, reaches a defensible verdict in under two hours, and §21's audit-usability kill fires when two consecutive auditors fail that. So the command surface is not ergonomics. It is the interface across which the central claim is tested.

It currently has no owner, and the scatter shows. Plan §6 lists eight flat verbs: `plan`, `run`, `resume`, `replay`, `verify`, `show`, `diff`, `fetch`. Since then the set has added `freeze --yes` (ADR-001), an `evidence` subcommand group carrying `show`, `verify`, `replay` and `diff` (ADR-007), `fetch kernel --expect-sha256` and `verify --audit` (ADR-012), `diff --rules` (ADR-009), and the flags `--workers`, `--verify-derivation`, `--shadow-units` and `--require-signature`. Two of those directly contradict each other: ADR-007 nests `verify` and `diff` under `evidence`, while ADR-009 and ADR-012 explicitly fold their checks into plan §6's *flat* `diff` and `verify` verbs. Both records defer the reconciliation to this one by name.

And **the weeks 1-2 exit gate is `farsight geometry`** - a command that appears in no ADR at all and is absent from §6's list. The gate that decides whether the geometry service works is stated in terms of a command nobody has defined.

Exit codes are worse, because they are what a machine reads. The set currently asserts, in four places: nonzero naming the item on any discrepancy (ADR-007, AT-3); exits zero for an `indeterminate` verdict and nonzero *only* on integrity failures (ADR-009); a nonzero exit when a `worker_env_hash` disagrees with its tier claim (ADR-002); and `--require-signature` changing the exit code (ADR-012). Nobody has defined the code space. An auditor scripting a check needs to distinguish **tamper** from **schema-invalid** from **missing register** - those three demand different responses, and "nonzero" collapses them into one.

What breaks concretely, and it is permanent: `report/summary.md` is generated from package JSON and contains the audit instructions, and §13 puts the audit path inside the package. **Command names and exit codes are printed into shipped evidence packages.** Renaming `farsight evidence verify` after packages ship makes the instructions in those packages wrong forever, and a package whose own instructions do not work is worse than no instructions - it is the first thing an auditor tries and the first impression they form.

## Decision

**1. Two levels, and the rule that decides which.** A command is `farsight <group> <verb> [target]` when its target is a durable object class FarSight produced or holds, and `farsight <verb> [target]` only for the actions whose target is unambiguously the experiment at hand or an external byte stream. A bare verb that could act on three different object classes is not a shorthand; it is an ambiguity an auditor pays for. That is what settles the ADR-007 / ADR-009 / ADR-012 conflict: `verify` alone cannot say whether it means an evidence package, the local audit-log chain, or a seed derivation, so it is not a top-level verb.

The complete surface. Every row cites the record that forced it, the `audit_log.action` value it writes (ADR-012 owns that enumeration), and whether it is in plan §6's list.

| Command | Acts on | Forced by | `audit_log.action` | In §6 |
|---|---|---|---|---|
| `farsight plan <design-ref>` | a frozen `ExperimentDesign` | ADR-005 | `plan` | yes |
| `farsight run <experiment-hash>` | the planned run set | ADR-002 | `run` | yes |
| `farsight resume <experiment-hash>` | the ledger | ADR-011 | `resume` | yes |
| `farsight freeze <draft-path>` | a draft design object | ADR-001 | `freeze` | no |
| `farsight fetch kernel\|artifact` | external bytes | ADR-012 | `fetch` | yes |
| `farsight geometry` | the `GeometryProvider` | plan §17 gate | `run` | no |
| `farsight evidence build <experiment-hash>` | a package | ADR-007 | `package` | no |
| `farsight evidence show <pkg>` | a package | ADR-007 | none | verb yes |
| `farsight evidence verify <pkg>` | a package | ADR-007 | `verify` | verb yes |
| `farsight evidence replay <pkg>` | a package | ADR-006 | `replay` | verb yes |
| `farsight evidence diff <pkg-a> <pkg-b>` | two packages | ADR-007 | none | verb yes |
| `farsight rules show <ref>` | the rule registry | ADR-009 | none | no |
| `farsight rules diff <ref-a> <ref-b>` | two registry refs | ADR-009 | none | no |
| `farsight alias set <name> <hash>` | the alias registry | ADR-001 | `alias_set` | no |
| `farsight alias list` | the alias registry | ADR-001 | none | no |
| `farsight collapse authorize <belief-ref>` | an `EpistemicCollapse` | ADR-004 | `collapse_authorize` | no |
| `farsight store verify` | `$FARSIGHT_HOME` | ADR-012 | none | no |

Seventeen commands, and none of them is discretionary: each one either appears in plan §6 or is forced by a record in this set, and the last three exist because **ADR-012's `audit_log.action` enumeration is closed and contains `alias_set` and `collapse_authorize`** - values no command in the set produced. An action nothing can write is either a dead enum member or a missing command; it was the latter.

`farsight store verify` replaces ADR-012's `farsight verify --audit`; `farsight rules diff` replaces ADR-009's `farsight diff --rules`. Both records state that this one owns the grammar, so those spellings are superseded rather than contradicted. `store verify` deliberately writes **no** audit row: appending to the chain you are verifying moves the head between the check and the report.

`farsight geometry` keeps the plan's literal spelling because it is the wording of the weeks 1-2 exit gate, and because it exists for a real reason - in weeks 1-2 there is no planner, no ledger and no package builder, and the geometry service must still be exercisable and hash-stable. It is a leaf command, not a group: `farsight geometry --design PATH --out DIR`. It shares the `run` audit action because ADR-012's enumeration is closed and `run` is the only admissible member; its `detail_json` carries the design path, which is what disambiguates a week-1 geometry probe from a campaign when an auditor reads the chain.

Flags, each inherited from the record that decided it: `--workers N` (ADR-002) on `run`, `resume` and `evidence replay`; `--yes` (ADR-001) on `freeze`; `--url --expect-sha256 --into` (ADR-012) on `fetch`; `--require-signature` (ADR-012) and `--exit-on-verdict` on `evidence verify`; `--runs SPEC --tier A|B` (ADR-006, ADR-007) and `--verify-derivation` (ADR-005) on `evidence replay`; `--shadow-units` (ADR-008) on `run` and `geometry` only. Global on every command: `--json`, `--quiet`, `--home PATH`, `--no-color`, `--version`.

A run executed with `--shadow-units` writes a ledger flag; `evidence build` refuses to include such a run, because ADR-008 says the shadow path is never in an evidence package.

**2. The exit-code contract.** One registry, in `src/farsight/cli/exit_codes.py`, and it is the single source for the code, the symbol and the one-line meaning:

```
 0  ok                        the operation completed and every check it performed passed
 1  internal_error            unhandled exception; never returned deliberately
 2  usage_error               reserved: this is Typer/Click's own code and is not reassigned
10  integrity_failure         a recorded hash did not match recomputed bytes (the AT-3 tamper class)
11  schema_failure            a document failed validation against the schema shipped in the package
12  completeness_failure      a required element is absent: a register file, a review_signoff row,
                              a claim falsifier, an unresolvable referent_ref, an unresolved input hash
13  recomputation_mismatch    a metric or verdict recomputed from raw channels differs from the
                              recorded value while every hash matched (a version-skew finding)
14  environment_refusal       the tier predicate is not satisfiable here (ADR-019), or a required
                              engine extra is not installed
15  signature_policy_failure  --require-signature was given and the signature is absent or invalid
20  precondition_refusal      the artifact could not be produced because a precondition was refused:
                              an unhonorable RunSpec, a refused fault lowering, an unbounded Unknown,
                              a missing pedigree, a shadow-units run offered to evidence build
21  work_remains              run/resume: not every planned run reached a terminal status; or --strict
                              was given and at least one run is not `ok`
22  verdict_fail              --exit-on-verdict and at least one acceptance verdict is `fail`
23  verdict_indeterminate     --exit-on-verdict, no `fail`, at least one `indeterminate`
30  acquisition_failure       fetch: bytes did not match --expect-sha256, or transport failed
```

Three rules make it scriptable.

*Resolution.* When several conditions hold, the process returns **the numerically smallest applicable code above 2**. That makes tamper (10) dominate everything, which is the ordering an auditor wants, and it is deterministic: the same package on the same install always yields the same code. Nothing is hidden by it, because `--json` reports every finding regardless of which code was returned.

*A verdict is a result, not a failure.* `pass`, `fail` and `indeterminate` all exit **0** by default, which preserves ADR-009's rule exactly. `--exit-on-verdict` is the opt-in for a CI system that wants the verdict in the exit status, and it is opt-in precisely because a `fail` verdict is a scientific outcome and a nonzero exit reads as a broken tool.

*The registry is append-only.* A number's meaning is never reassigned and a symbol is never removed. New conditions get new numbers. This is what lets a package shipped today print "exit code 10 means a hash did not match" and still be true in three years.

**3. There is a `--json` contract, and it is the same on every command.** With `--json`, **stdout carries exactly one JSON object and nothing else**; all human-readable text, progress and warnings go to stderr.

```json
{"schema_version": "cli_result/1",
 "command": "evidence verify",
 "exit_code": 10,
 "status": "error",
 "findings": [{"code": 10, "symbol": "integrity_failure",
               "message_id": "channel_hash_mismatch",
               "item": "runs/channels/4242/link.margin.npy",
               "expected": "sha256:...", "observed": "sha256:..."}],
 "summary": {}}
```

`message_id` is drawn from a closed enumeration, exactly as ADR-012's log events are, and for the same reason: with free text no validator can bound what reaches the output. `item` is a POSIX-relative path inside the package or a content hash, and nothing else. A digest printed by the CLI carries the `sha256:` prefix; a digest inside a hashed document never does (ADR-001 decision 7), and `--json` output is a report rather than package content, which is why the two spellings can differ without either being wrong. The LOG-CONTENT vocabulary of paths, hashes and enumerated labels applies to CLI output as strictly as it applies to logs, because a customer's parameter magnitude is as exportable when printed as when logged. Paths are POSIX-relative even on Windows, so that an auditor's script written against a package produced on Linux works unchanged.

**4. Stdout is never part of a hashed artifact, and no artifact is ever produced by redirecting it.** Every package file is written by the atomic-rename writer with explicit `\n` line endings (ADR-011). Three reasons, and the third is decisive on our own platform: human output carries wall-clock progress, which ADR-006 forbids in any hashed value; rendering is locale- and terminal-dependent; and **a redirected stdout on Windows undergoes CRLF translation**, so `farsight ... > file.json` produces different bytes on the development platform than in the container, silently, for a file whose whole purpose is a byte-for-byte hash. `--json` output is a machine-readable *report*, never package content.

**5. The verb surface is a compatibility surface with the same status as the evidence format.** Verb names, group names and exit codes are append-only from the first shipped package. A verb is never renamed; if a better name is found, the new name is added and the old one is retained permanently as an alias that prints a deprecation line **to stderr** (never to stdout, never inside `--json`). `report/summary.md`'s renderer draws every command name and every exit code from `cli/verbs.py` and `cli/exit_codes.py` rather than from literal strings, so the instructions inside a package cannot drift from the code that has to honour them.

## Options considered

### Option 1 — Plan §6's eight flat verbs, unchanged — REJECTED
Steelmanned: it is the plan, which is the authority; it is the shortest surface to learn and to type; `git` and `docker` both started flat and it served them; and every additional level is a thing an auditor has to guess under time pressure. Rejected because the surface has genuinely grown past what a flat namespace can disambiguate. `verify` now has three distinct targets (a package, the local audit-log chain, a seed derivation), `diff` has two (packages, rule registries), and `show` has several. A flat verb whose meaning depends on the shape of its argument is exactly the interface that fails the AT-9 two-hour test, because the auditor's mistake is silent - they verify the wrong object and believe they verified the right one.

### Option 2 — Full noun-verb for everything, including `plan`, `run` and `resume` — REJECTED
Steelmanned properly, this is the more principled position and it is what `kubectl` and the AWS CLI converge on at scale: one rule, no exceptions, no memorizing which verbs are special, and a surface that stays regular as it grows past twenty commands. Rejected because `farsight campaign run` renames three of plan §6's eight verbs for no gain in clarity - there is exactly one object those three verbs can act on - and each rename is a permanent plan amendment plus a permanent alias under decision 5. Regularity is worth something; it is not worth three irreversible renames of the plan's own words in week 1.

### Option 3 — Two exit codes: 0 and 1, with detail in `--json` only — REJECTED
Steelmanned: it is what most Unix tools do, it never runs out of numbers, it cannot drift out of sync with the JSON, and it forces consumers to read structured output rather than script against integers - which is better engineering. Rejected on the specific audience: AT-9's auditor is scripting a check on a machine they control against a package they distrust, and §21's tamper requirement is that a flipped byte fails **loudly and by name**. "Nonzero, go read the JSON" is a strictly weaker signal than "10, that is tamper" in the one situation the product exists for, and the deciding case is a shell pipeline in someone else's CI where the JSON is not being parsed at all.

### Option 4 — Rich exit codes with a distinct number per failing check — REJECTED
Steelmanned: maximum information in the status byte, no JSON parsing needed at all, and it is what some verification tools do. Rejected because the space is bounded at 125 usable values on POSIX, because it would make every new check a permanent numbering decision under the append-only rule, and because it puts a taxonomy that will change into the one part of the interface that can never change. Classes are stable; individual checks are not.

### Option 5 — A nonzero exit for a `fail` verdict — REJECTED
Steelmanned, and this is the option most users would expect: CI wants "did my acceptance criteria pass" in the exit status, that is how every test runner behaves, and requiring a flag to get it will surprise people. Rejected because it contradicts ADR-009 at the type level - a three-valued verdict is a *result*, and `indeterminate` in particular is the flagship's common case - and because a tool that exits nonzero on an honest scientific outcome trains its users to ignore nonzero exits, which destroys the tamper signal that Option 3 was rejected to protect. `--exit-on-verdict` gives the behaviour to whoever wants it without making it the default meaning of failure.

### Option 6 — Two levels by object class, an append-only code registry with classes, a uniform `--json` object, and stdout excluded from every hash — CHOSEN
It disambiguates exactly where ambiguity had appeared, keeps plan §6's three unambiguous verbs unchanged, gives the auditor the three distinctions they actually need, and makes the shipped instructions structurally incapable of drifting from the code.

## Consequences

**Buys us:** an auditor can script tamper-versus-schema-versus-missing-register without parsing anything. A closed, checkable surface: every command maps to exactly one audit action, and every value of ADR-012's closed enumeration is produced by at least one command, so a missing command shows up as a failing test rather than as a dead enum member. Instructions inside a shipped package that cannot go stale, because the renderer reads the same registries the parser does. And a single place - `cli/verbs.py` - where adding a command forces a decision about its audit action, its exit codes and its `--json` shape at the same time.

**Costs us:** seventeen commands to document, test and keep, against a plan that named eight. Append-only means the surface only grows: `cli_surface.json` is a golden that has to be re-issued with an `EXPECTED-CHANGE` note for every addition. Every command must maintain a typed result model for `--json`, which is real work per command and the first thing that will be skipped under schedule pressure. And the smallest-applicable-code rule means a package with both a tampered channel and an invalid schema reports 10, so an operator who reads only the exit code fixes one problem and re-runs into the next - the `findings` list has both, and they have to look.

**Forecloses:** **we can never rename a verb.** A better name discovered in week 6 ships as a second name that we carry forever, and the ADR set is full of week-1 naming judgements made by three people with no users. That is the single largest permanent cost in this record and it is the direct consequence of putting command names inside shipped evidence. It also forecloses any interactive mode - a REPL, a TUI, a wizard - as a *first-class* surface: every command is a pure function of its arguments plus `$FARSIGHT_HOME`, there is no session state, and anything interactive would be a separate front end over the same commands rather than an evolution of these. And it forecloses the exit status as a complete summary: because a `fail` verdict exits 0 by default, a green build does **not** mean the claim passed, and anyone who scripts naively on the exit code will believe otherwise. We chose that, ADR-009 requires it, and it will mislead somebody.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Two levels, groups for object classes and bare verbs for the three unambiguous ones | 0.80 | `ci-cli-contract` needs more than two `EXPECTED-CHANGE` renames before K5 (end wk 6), or the week-8 cold auditor (AT-9) invokes the wrong object's verb at least once during the audit. Either says the rule is not carrying the disambiguation it was adopted for. |
| The exit-code classes and the smallest-applicable-code resolution rule | 0.85 | Any condition arising in weeks 3-6 needs a code and cannot be placed in an existing class without reassigning a number - which the append-only rule forbids, so it would force a class boundary to move before the first package ships in week 4. |
| Verb names and exit codes are an append-only compatibility surface | 0.90 | A rename is judged necessary before the first evidence package ships (wk 4). It is nearly free then and impossible afterwards, which is why this is the one trigger that must be checked on a date rather than on an event. |
| A uniform `--json` object on stdout, human text on stderr, closed `message_id` vocabulary | 0.82 | Two or more commands ship in weeks 3-6 whose useful output cannot be expressed without a free-text field, which would mean the closed vocabulary is being worked around rather than used. |
| **`farsight geometry` as a permanent top-level command** | **0.60** | ADR-018 lands run composition in week 3 and geometry turns out to be expressible as a one-stage `RunSpec`, at which point `geometry` is a second permanent entry point into the geometry provider that duplicates `run`. It exists because weeks 1-2 have no planner and the plan's own gate names it; that is a scheduling reason, not an architectural one, and this must be settled before the first package ships in week 4 because after that the name is permanent. |
| **`run`/`resume` exit 0 when runs failed, 21 only when work remains** | **0.70** | Any run set in the weeks 5-6 campaign reaches `evidence build` with silently failed runs because a script keyed on the exit code alone treated the campaign as clean. The fix is to make `--strict` the default and add an opt-out, which is a behaviour change to a shipped verb and therefore has to happen before week 4. |
| Stdout is never part of a hashed artifact | 0.95 | A workflow in weeks 3-6 genuinely needs a hashed artifact on stdout - for example piping a canonical document into an external signer - which would force an explicit `--emit-canonical` mode writing bytes with no translation, rather than a general relaxation. |

## Enforcement

1. **CI job `ci-cli-contract`** (**first green by week 2**; every commit). It walks the Typer application and snapshots the full tree - group, command, every option name, every default, every declared audit action and every declared exit code - into `tests/golden/cli_surface.json`, which is text and therefore lives in git under ADR-014's rules. The job fails on any difference without a matching `EXPECTED-CHANGE` note, and fails unconditionally on any **removal or rename**, which is the append-only rule in mechanical form. It additionally AST-scans the `report/summary.md` renderer and fails if a command name or exit code appears there as a string literal rather than as a reference into `cli/verbs.py` or `cli/exit_codes.py`.
2. **`tests/unit/test_exit_code_registry.py`** (**first green by week 2**): the registry must be append-only against a frozen table checked into the test; no number may be reused, no symbol removed, and codes 0, 1 and 2 must keep their reserved meanings. It also exercises the resolution rule over a matrix of simultaneously-holding conditions and asserts the smallest applicable code above 2 is returned every time.
3. **`tests/unit/test_cli_audit_action_coverage.py`** (**first green by week 2**): every command declares either exactly one `audit_log.action` value or `audit: none`; the union of declared values equals ADR-012's enumeration exactly, with no orphan enum member and no undeclared command. This is the check that turned two missing commands into two rows in the table above, and it is bidirectional on purpose.
4. **`tests/unit/test_json_contract.py`** (**first green by week 2**): under `--json`, stdout must parse as exactly one object validating against `cli_result/1` with no leading or trailing bytes; human text must appear on stderr; every `message_id` must be in the closed enumeration; and every `findings[].item` must be a POSIX-relative path or a `sha256:` hash, which is the LOG-CONTENT vocabulary (ADR-012) applied to output.
5. **`test_tamper_matrix`** (defined in ADR-007; **first green by week 4**): this record strengthens the assertion it makes. It is not enough that `verify` exits nonzero and prints the offending path; it must exit exactly `10` for a flipped byte, exactly `11` for a document that fails its shipped schema, and exactly `12` for a deleted register file. AT-3's "nonzero naming the item" becomes "the tamper code, naming the item".
6. **PARTIALLY MECHANIZED: `tests/unit/test_stdout_never_hashed.py` (CLI-1)** (**first green by week 1**). Mechanical half: an AST lint fails on any call to `print` or any write to `sys.stdout` from a module under `src/farsight/` outside `cli/`, and fails if any function in `farsight.evidence` that writes package content does so through anything but the atomic-rename writer (ADR-011). Residue: nothing we can run decides whether an *operator* pipes our stdout into a hash, and no lint sees a write performed through a file object our own code was handed. Review checklist item **CLI-1** - "no shipped instruction, example or README snippet directs a reader to hash, redirect or archive FarSight's standard output as an artifact" - carries it, and a CLI-1 row naming a reviewer and a date is recorded per release and copied into the `review_signoffs` list of every package built by that release (ADR-000, ADR-007).
7. **NOT MECHANIZABLE: CLI-2** - whether the audit path is *followable* by a stranger inside two hours. No parser decides that, and the four commands can each be individually correct while the sequence is unusable. Review checklist item **CLI-2** - "a person who has not used FarSight before was handed only a package, the CLI and the README, and reached a verdict without asking us a question" - substitutes; AT-9 in week 8 is the external backstop, and §21's audit-usability kill is what fires when it fails twice.

## References

- FARSIGHT_FOUNDATION_PLAN.md §6 (the `cli/` package described as "typer: plan/run/resume/replay/verify/show/diff/fetch"), §13 (the audit path: `evidence verify` then `show` then `replay` then an independent recomputation and a referent check; nonzero exit naming the item; the two-hour target; `report/summary.md` generated from the JSON), §16 (CLI only, no web UI; `farsight fetch` records URL and hash; append-only audit log for every CLI mutation from v0), §17 (weeks 1-2 exit gate: `farsight geometry` emits hash-stable Psyche pass geometry, bitwise-reproducible in container; weeks 5-6 `replay` and `diff`), §18 AT-3 (tamper: nonzero exit naming the exact item) and AT-9 (external engineer, package plus CLI plus README, two hours), §21 (audit-usability kill).
- ADR-012 owns the `audit_log.action` enumeration (`freeze`, `plan`, `run`, `resume`, `fetch`, `package`, `verify`, `replay`, `alias_set`, `collapse_authorize`) that decision 1's table must cover exactly; this record does not redefine it and does not maintain a rival list.
- Superseded CLI spellings, both by explicit deferral rather than by contradiction: ADR-012's `farsight verify --audit` becomes `farsight store verify`, and ADR-009's `farsight diff --rules` becomes `farsight rules diff`. Both records state that ADR-024 owns the verb and flag grammar.
- UNVERIFIED - confirm at implementation time: Typer's and Click's exact reserved exit codes and whether the version pinned by `uv.lock` uses 2 for usage errors as assumed here; the mechanism by which a Typer group emits a single JSON object on stdout while sending its own error rendering to stderr.
- **PLAN AMENDMENT REQUESTED: §6** - the CLI verb list becomes the seventeen commands of decision 1's table. Beyond §6's eight verbs this adds `freeze` (ADR-001), `geometry` (already named as the weeks 1-2 exit gate in §17 but absent from §6), the `evidence` group with `build` (the `package` audit action has no other producer), and the `rules`, `alias`, `collapse` and `store` groups - the last three forced because ADR-012's closed audit-action enumeration contains `alias_set` and `collapse_authorize`, and because the audit-log chain needs a verifier that is not the package verifier. The `fetch` verb is unchanged and remains the only importer of `farsight.acquire`, the sole package permitted an HTTP import (ADR-012, ADR-013, which carry the `acquire/` amendment for §6's source tree).
- **PLAN AMENDMENT REQUESTED: §6** - the following flags are added to §6's verbs: `--workers` (ADR-002), `--yes` (ADR-001), `--url`, `--expect-sha256`, `--into` (ADR-012), `--require-signature` (ADR-012), `--runs`, `--tier` (ADR-006, ADR-007), `--verify-derivation` (ADR-005), `--shadow-units` (ADR-008), plus `--strict` and `--exit-on-verdict` decided here, and the global `--json`, `--quiet`, `--home`, `--no-color` and `--version`.
- **PLAN AMENDMENT REQUESTED: §13** - the audit path in the package is spelled `farsight evidence show` then `farsight evidence verify` then `farsight evidence replay --runs ... --tier A|B`, and §13's statement that a discrepancy produces a "nonzero exit naming the item" is refined to the exit-code registry of decision 2, so that tamper, schema invalidity and a missing register are distinguishable by a script rather than only by a human reading the message. §13's prose is what `report/summary.md` renders into every shipped package, so the spelling and the codes must be settled before the first package ships in week 4.
- ADR-000, ADR-001, ADR-002, ADR-004, ADR-005, ADR-006, ADR-007, ADR-008, ADR-009, ADR-011, ADR-012, ADR-013, ADR-014, ADR-018, ADR-019, ADR-023.
