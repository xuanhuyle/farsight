# ADR-000 — ADR process and template
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §22, §3, §21
**Related ADRs:** ADR-013 (its Enforcement section is the pattern this template exists to force), ADR-014 (the CI jobs that Enforcement sections name are configured there), ADR-001 (deliberately not applied to ADR numbering — see Decision), ADR-006 (owns `ci-worker-order-invariance`, the worked example of the one-job-one-owning-record rule), ADR-025 (the record split out of ADR-013, and part of why the numbering runs past §22's twelve)

## Context

The question under test here is not "should we write decision records" — everyone says yes to that and then stops reading. It is narrower and it is an exchange: **do we accept a per-record authoring tax of roughly one hour, plus about a day of setup, in return for a stop-loss on each architectural bet?** If the answer is yes, the template must be shaped so that the stop-loss actually exists; if the machinery does not pay out, the tax is pure ceremony and this record is the first thing that should be cut.

Two facts about FarSight decide the shape of that machinery. First, §21 is a list of dated gates and standing kills — K1 at week 1, K2 at week 2, K3 as a hard gate at week 3, K5 at week 6, K6 and K7 at week 8. (Founder direction, `FARSIGHT_FOUNDER_FEEDBACK.md` §2: **K5 is a business-model gate, not a project kill gate.** If discovery finds no budgeted problem FarSight displaces, that marks the commercial-SaaS thesis unvalidated and sends the funding and distribution question elsewhere — research infrastructure, open-core, institutional partnership — rather than ending the project. The hard kills are scientific: replay, provenance, the aleatory/epistemic distinction proving usable, no hidden defaults, adapter cost, value beyond a notebook. This matters to *this* record because roughly a dozen ADRs key revisit triggers to the eight K5 interviews: those triggers are unaffected and stay exactly as written, because they were never kill decisions — they fire "revisit this sub-decision", and what an interview count adjudicates is a design bet, not the project's existence.) When K3 fails, or the adapter-cost kill fires, somebody has to know *which decision to reverse* and what it was holding up. A record without a stated confidence and without a trigger that can fire *before* the decision hardens is not a bet with a stop-loss; it is dogma with a date on it. Second, the entire product thesis is that rules are mechanically prevented rather than policed — the metric-version check, the golden-change check, the tolerance-inflation kill with an allowed count of zero. A decision set for *that* product whose own rules are enforced by memory would be internally inconsistent, and the inconsistency would be visible to exactly the audience we are trying to convince (§17 week 8, AT-9).

What breaks concretely if the exchange is bad in either direction: at one extreme an ADR names no mechanical check, the rule erodes in week 5 under schedule pressure, and nobody notices until the auditor's laptop cannot verify a package. At the other extreme, three devs spend two days of an eight-week build writing prose that no one consults, and the honest response is to stop.

## Decision

Record every architecturally significant decision as a numbered Markdown ADR in `docs/adr/`, using exactly this template:

```
# ADR-0NN — <Title>
**Status:** Proposed (awaiting founder review)
**Date:** YYYY-MM-DD
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §<n>[, decision D<n>]
**Related ADRs:** ADR-0XX (<one-clause reason>), ...

## Context            # forcing question, verified facts, what breaks concretely
## Decision           # imperative, implementable; a concrete sketch where the schema IS the decision
## Options considered # "### Option N — <name> — CHOSEN|REJECTED"; every rejected option steelmanned
## Consequences       # Buys us: / Costs us: / Forecloses:
## Confidence and revisit triggers   # a TABLE, one row per separable sub-decision
## Enforcement        # named mechanical check + "first green by week N"; escape-hatch tokens where honest
## References         # plan sections, ADR numbers, PLAN AMENDMENT REQUESTED lines
```

The H1 line and the five header lines form **one contiguous block with no blank lines anywhere inside it**. This is not cosmetics: `adr-lint` parses the header positionally, and two records in the first draft of this set drifted a blank line into the middle of the block.

Four things in that skeleton are non-standard, and each exists because of a specific failure this set already exhibited in draft.

**Confidence is a table, not a number.** One row per *separable* sub-decision, each with its own confidence in [0, 1] and its own revisit trigger:

```
| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| <the one thing this row is about> | 0.NN | <dated, countable, and able to fire before the decision hardens> |
```

A single number per record was tried and failed. Records here routinely decide four or five separable things — a three-way split *and* a restricted expression language *and* a one-layer graph — and a single 0.85 attached to all of them tells the six-month reader nothing about which one is load-bearing and shaky. The number is a bet: 0.9 means we would bet 9:1 that in six months this has not materially changed; 0.7 means we expect to revisit it and are proceeding anyway. **A set in which nothing sits below 0.75 has a decorative confidence column**, and authors are expected to say so when a row is genuinely shaky rather than round it up to the set average.

**Revisit triggers must be able to fire before the decision becomes irreversible.** FarSight has zero customers. A trigger reading "two independent customers request X", or "a paying customer requires Y", cannot fire inside the window where the decision is still cheap — and for anything touching evidence identity there is no later window at all, because §16 says the identity scheme cannot change once customers hold packages. Triggers are therefore keyed to the plan's dated gates and to countable artifacts that will exist: K1 (wk 1), K2 (wk 2), K3 (wk 3, hard gate), K5 (wk 6, the eight discovery interviews), K6 and K7 (wk 8), the week-8 external cold audit, and measurements taken during the build. The house pattern for a market-facing trigger is *"at least 3 of the 8 K5 interviews name X unprompted"* — dated, countable, and adjudicated by a transcript rather than by the author of the decision.

**Enforcement names a mechanical check and says when it first goes green.** A CI job, a test module, an import-linter contract, or a schema validator, identified by name so a reader can go find it, followed by **"first green by week N"**. Several checks in this set cannot exist before week 5 or 6 because they need a runner, a package builder or an archived campaign fixture; a check that quietly claims "every commit" while being unbuildable until week 6 is indistinguishable from an intention, and week 1 through week 5 is precisely the window in which rules erode.

Where mechanization is impossible or only partial, the item must open with one of exactly two literal tokens — **`NOT MECHANIZABLE:`** or **`PARTIALLY MECHANIZED:`** — followed by the id of the review-checklist item that substitutes, and, for the partial case, the honest residue the check does not cover. `adr-lint` greps for exactly those two tokens and reports a count per record; nothing else counts as the escape hatch. A check that is formally undecidable (proving a function is pure, detecting all network access, proving a universal negative about arbitrary source, parsing prose) is downgraded to `PARTIALLY MECHANIZED:` with the false-negative class named in one sentence, rather than stated flatly as a unit test.

**Review-checklist items are records, not norms.** A checklist item has an id in `[A-Z][A-Z0-9]*(-[A-Z0-9]+)+` — `EV-1`, `LOG-CONTENT`, `PHYS-1`, `SEED-1`, `CC-3` — and it is discharged by writing a row into a new required field:

```python
class ReviewSignoff(BaseModel):        # hashed; frozen with its parent
    checklist_item_id: str             # e.g. "EV-1"
    reviewer: str                      # operator identity, as recorded in the audit log (ADR-012)
    date: str                          # ISO-8601 UTC date
    statement: str                     # what the reviewer asserts, in one sentence

review_signoffs: list[ReviewSignoff]   # on frozen ExperimentDesign and on EvidencePackage
```

`farsight evidence verify` fails an `evidence_grade: evidence` package that is missing a signoff row for any checklist item applicable to it. We cannot mechanize whether `EV-1` was answered *honestly*; we can mechanize that a named human answered it, on a date, inside a hashed document. Any ADR that asserts a checklist item must give it an id and say that it lands in `review_signoffs`. Checklist ids never begin with `ADR`, so that an item id can never be misread as a record number. Ids are allocated per record rather than from one dense sequence across the set, so gaps carry no meaning and are not evidence of a missing item: `CC-3` with no `CC-1`, or `ENV-2` and `ENV-3` with no `ENV-1`, means only that the owning record numbered its own items and nothing else claimed the earlier ones. The single exception to the `review_signoffs` rule is `PROC-1` below, which gates a pull request rather than an artifact and therefore has nowhere in a package to land.

**Status values are exactly three.**
- `Proposed (awaiting founder review)` — written, not yet agreed. No implementation may depend on it, and **every section is freely editable**.
- `Accepted (MVP commitment; see Revisit triggers)` — committed for the 8-week MVP, binding on implementation, enforced in CI. Not immutable: the revisit triggers are the sanctioned route to changing it.
- `Superseded by ADR-NNN` — replaced. The content stays exactly as written.

**This set entered review as a whole, and was accepted as a whole on 2026-08-28.** Every record in `docs/adr/` — ADR-000 through ADR-029 — carries `Accepted 2026-08-28`; ADR-030 was accepted 2026-08-29 on founder direction. None of it has been founder-reviewed, so none of it is Accepted, and the set is reviewed and accepted in one act rather than record by record: the records cross-reference each other so densely that accepting a subset would leave accepted records citing proposals. A record abandoned before acceptance keeps its number and its `Proposed` status with a one-line note in Context; numbers are never reused.

**Supersession applies from acceptance, not before.** An *accepted* ADR's Context, Decision, Options, Consequences and Enforcement sections are never edited; permitted edits are a broken link, a typo, and appending `Superseded by ADR-NNN` to Status. Reversing an accepted decision means a new ADR carrying `Supersedes ADR-NNN` in its Related ADRs line, explaining what changed in the world. While a record is Proposed none of that applies — which is what makes the current review possible at all.

**Numbering and filenames.** Zero-padded three digits, monotonically allocated, never reused; filename `ADR-0NN-kebab-case-title.md`. §22 asked for twelve records; the set as it stands runs **ADR-000 through ADR-030** — thirty-one records — because the gap audit found ten forced decisions with no coverage (time and frames, kernel sets, topology, run composition, the reference container, channels, referents, distributions, run outcomes, the CLI surface), because ADR-013 was split with its LLM exclusion moving to ADR-025, and because the architecture evolution review commissioned four more (ADR-026 model identity, ADR-027 scenario enumerations, ADR-028 the observable vocabulary, ADR-029 derived bindings). A number is claimed by adding its row to `docs/adr/README.md` in the same commit that adds the file, which is also how collisions between parallel authors surface as merge conflicts rather than as duplicate numbers.

**One job, one name, one owning record.** A CI job, test module or import-linter contract is *defined* in exactly one ADR. Every other record naming it **in its Enforcement section** must append `(defined in ADR-0XX)`. The draft set shipped one job under two names — "pool-order-independence" in two records and `ci-worker-order-invariance` (defined in ADR-006) in two others, for the same `--workers 1` versus `--workers 8` test — which silently doubles the apparent enforcement surface and breaks the Enforcement section's job as an index into the build. The retired name is quoted here without backticks so that the uniqueness check does not trip on the example of its own defect.

**Relationship to the plan.** `FARSIGHT_FOUNDATION_PLAN.md` at the repository root is the authority; ADRs are subordinate elaborations and must not silently contradict it. Where a record needs to depart, it states the departure in its References as a literal line — `PLAN AMENDMENT REQUESTED: §N — <what and why>` — so the founder can approve or reject the departures as one batch. The plan file is never edited by an ADR author.

Note the deliberate inconsistency: ADRs are identified by a human-allocated sequence number, not by the content hash ADR-001 mandates for everything the product itself produces. Content addressing is for machine-verifiable artifacts that must never change identity; ADRs are prose for humans, and a number a person can say out loud in a standup is worth more here than tamper evidence.

## Options considered

### Option 1 — No ADRs; the plan plus code comments carry the decisions — REJECTED
The plan is approved, detailed, and already contains most of the positions; three devs sit inside one 8-week sprint and can simply ask each other. That is a real saving: thirty documents is more than a day of writing that produces no working code, and in a build with a hard gate at week 3 that day is expensive. Rejected because the plan records *conclusions* without alternatives or costs, and the reversal machinery in §21 needs both — when the adapter-cost kill fires, "why did we choose process isolation universally rather than only for GMAT" must be answerable from the repository and not from someone's memory of a week-0 conversation.

### Option 2 — Standard lightweight ADR template (Nygard / MADR: Context, Decision, Status, Consequences) — REJECTED
Widely recognized, minimal friction, familiar to any engineer we later hire, supported by off-the-shelf tooling, and — the strongest point in its favour — a template nobody has to be taught, which matters when the fourth dev arrives. Rejected on one specific deficiency: it has nowhere to put a calibrated confidence and nowhere to name the mechanical check, and those two omissions are exactly the failure modes this project cannot afford. Adding two sections to a familiar skeleton costs almost nothing in recognizability, and every remaining heading is MADR's.

### Option 3 — RFC-style long-form design documents — REJECTED
Steelmanned properly: IETF RFCs are immutable once published and carry explicit `Obsoletes` and `Updates` edges between documents. That is the strongest supersession discipline in software documentation, it is the model this record then borrows, and long documents hold more design detail, which is attractive for schema-heavy areas like the evidence package. Rejected on cost rather than on discipline: an RFC is a multi-week artifact with a review process attached, we have eight weeks, and the plan already plays the long-form role. We take the supersession model and leave the length.

### Option 4 — The FarSight template above — CHOSEN
The MADR skeleton, plus the sections that make a decision falsifiable, calibrated and mechanically defended. Roughly **1,500 to 3,000 words per record** — long enough to steelman the rejected options and name a real check, short enough that the whole set is one readable afternoon, which is what makes an index useful at all. The draft set's stated 700-1,300 band was falsified by every record in it and is corrected here rather than aspired to.

## Consequences

**Buys us:** a reversal protocol tied to the dated gates rather than to hindsight; a greppable inventory of every place we accepted human review, with a count per record; an auditable record — `review_signoffs` — where forty-two previously invisible norms now leave a row in a hashed document; an onboarding path for dev four and for the week-8 auditor; and an honest public record that the confidence on the commercial-facing decisions was never 1.0.

**Costs us:** roughly a day of setup and about an hour per subsequent record, spent in the weeks where the gates are tightest. Numeric confidences will be quoted back at us — a customer or auditor reading `docs/adr/` will find a 0.7 attached to a load-bearing sub-decision, and we have to be willing to defend that in a sales conversation rather than wish it away. `review_signoffs` also adds a required field to two frozen schemas, which is an identity change to every design-plane object (ADR-001), and it makes freezing an evidence-grade design impossible until a second human has actually signed.

**Forecloses:** the set becomes a **staleness liability it cannot detect in itself**. Twenty-six records, each naming CI jobs by name, and `adr-lint` can check that a job name is unique and that its record claims a week — it cannot check that the job still exists or still asserts what the record says it asserts. By week 6 the repository will contain confidently-worded records citing jobs that were renamed, merged or descoped, and the week-8 external auditor (AT-9) reads exactly these records. Second, and permanently: an accepted Decision is never edited, so a decision that was *right for the wrong reason* stays on the record with its wrong reason, and the superseding record has to argue against a strawman we wrote ourselves. Third, once a rule is Accepted and wired into CI, relaxing it costs a new numbered document and a visible supersession line — real friction on decisions that are genuinely cheap to reverse.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| The exchange itself: ~1 h per record buys a usable stop-loss | 0.75 | Cumulative ADR authoring passes 2.5 dev-days before K3 (end wk 3), or no record is cited in a design discussion between wk 1 and K3 |
| The seven-section skeleton (MADR + confidence + enforcement) | 0.85 | The week-8 external cold auditor (§17, AT-9) reports in writing that the ADR set did not help them complete the audit |
| Confidence as a per-sub-decision table rather than one number | 0.85 | Two consecutive new records ship a table whose rows all sit in [0.85, 0.90], which means the table is being filled in rather than used |
| Escape-hatch tokens + `adr-lint` grep as the visibility mechanism | 0.9 | `adr-lint` reports a per-record token count above 5 on any record, or a token appearing without a checklist-item id |
| `review_signoffs` as the home for checklist items | 0.7 | The first evidence-grade package (wk 4) needs more than 20 signoff rows to freeze, or two of them are discharged by the same reviewer on the same day without a stated basis — either means the checklist has become a form; or ADR-007's `verify` cannot express "applicable to this package" without a hand-maintained table |
| "First green by week N" as a required Enforcement field | 0.85 | Any single record's stated week slips 2 times before K5 (wk 6), which means the field is a wish rather than a schedule |
| Flat README index over 30 records | 0.7 | The set is at the 30-record threshold this row named as its own trigger, so the next record forces the grouping decision rather than deferring it again |
| Three status values, whole-set review | 0.9 | The founder review — due before implementation starts in wk 1 — returns verdicts on fewer than all 30 records, which makes partial acceptance real and needs a stated rule for accepted records that cite records still Proposed |

## Enforcement

1. **CI job `adr-lint`** (first green by week 1), running `tests/unit/test_adr_index.py` on every push. It parses every `docs/adr/ADR-*.md` and fails the build if any of the following does not hold:
   - the filename matches `ADR-\d{3}-[a-z0-9-]+\.md` and its number matches the H1;
   - the H1 line and the five header lines form one contiguous block with no blank line inside it, and the header keys are exactly `Status`, `Date`, `Deciders`, `Plan reference`, `Related ADRs` in that order;
   - the seven required section headings are present, spelled exactly, and in order;
   - the Status line matches one of the three permitted forms;
   - the Confidence section contains a Markdown table with at least one data row, every row's confidence cell parses as a float in [0, 1], and every row's trigger cell is non-empty and contains a digit or a gate id (`K1`-`K7`, `wk N`);
   - every `ADR-\d{3}` cross-reference resolves to a file that exists;
   - `docs/adr/README.md` contains exactly one table row per ADR file and exactly one file per row;
   - **CI job-name uniqueness across the set**: each backticked job, test-module or contract name has exactly one owning record, and every other record naming it carries `(defined in ADR-0XX)`;
   - every Enforcement item that names a mechanical check contains the literal string `first green by week` followed by a numeral, matched case-insensitively; an item consisting only of an escape-hatch token, its checklist id and its residue is exempt, because a human review has no green to date;
   - every `NOT MECHANIZABLE:` and `PARTIALLY MECHANIZED:` token is followed on the same line by a checklist-item id matching `[A-Z][A-Z0-9]*(-[A-Z0-9]+)+`. A token occurrence carrying no checklist id is a *mention* — a record naming the tokens rather than using one — and is skipped rather than failing the job; a token occurrence carrying an id is a *use* and is counted. The discriminator is the id, not the backticks: every genuine use in this set is written inside an inline code span, so skipping code spans would skip the whole mechanism. The per-record use counts are printed in the job log;
   - the checklist-id registry module `src/farsight/evidence/checklist_registry.py` (defined in ADR-007) contains exactly the set of ids declared across `docs/adr/`, with one owning record each;
   - every `PLAN AMENDMENT REQUESTED:` line appears in References and names a section number that exists in `FARSIGHT_FOUNDATION_PLAN.md`.
2. **`test_review_signoff_schema`** (unit tier, first green by week 2): asserts `review_signoffs` is a required field on the frozen `ExperimentDesign` and `EvidencePackage` models, that `checklist_item_id` is validated against the id grammar, and that the field is inside the hashed object rather than the provenance block (ADR-001 decision 4).
3. **`farsight evidence verify`** (defined in ADR-007, first green by week 4): exits nonzero, naming the item, when an `evidence_grade: evidence` package lacks a `review_signoffs` row for an applicable checklist item.
4. `PARTIALLY MECHANIZED: PROC-1` — whether an Enforcement section names a check that actually exists and actually fails. `adr-lint` can see that the name is unique, that a week is claimed, and (from week 2) that the name appears somewhere in `.github/workflows/` or `tests/`; it cannot see that the job asserts what the record says it asserts, and it cannot detect a record that contradicts the plan in prose. Residue: semantic agreement between a record and both its named job and the plan. Substituted by review-checklist item **PROC-1** — *"does the Enforcement section name a check that exists in this commit or a tracked issue to create it, and does the Decision contradict any plan section it cites?"* — which is discharged in the ADR pull request. PROC-1 is the one checklist item that does **not** land in `review_signoffs`: it gates a pull request, not an artifact, and there is no hashed document for it to live in. The mechanized half is **first green by week 1** for the uniqueness and week-claimed checks, and week 2 for the does-the-name-exist check, which needs `.github/workflows/` and `tests/` to have something in them to look at.

## References

- FARSIGHT_FOUNDATION_PLAN.md §3 (per-decision confidence table, D1-D14), §21 (kill criteria and dated gates K1-K7), §22 (the ADR list this process serves), §17 (week-8 external cold audit; the eight K5 discovery interviews), §4 and §13 (the frozen objects and the package layout that `review_signoffs` attaches to).
- ADR-013 (package boundaries; the canonical example of an ADR whose Enforcement is a CI-executed contract), ADR-014 (toolchain; where `adr-lint` and the other named jobs are configured), ADR-006 (owner of `ci-worker-order-invariance`), ADR-007 (owner of `farsight evidence verify`), ADR-025 (the LLM exclusion, split out of ADR-013).
- Prior art for the base skeleton: M. Nygard, "Documenting Architecture Decisions" (2011), and the MADR template at https://adr.github.io/madr/. Background reading only; neither URL was re-verified on 2026-08-26 and no claim in this ADR depends on their current contents.
- Refinement of plan §3, not a departure: §3 assigns one confidence per decision; this template requires one per *separable sub-decision*, which is strictly more information about the same decisions.
- PLAN AMENDMENT REQUESTED: §22 — the ADR list runs to ADR-030 (thirty-one records), not the twelve §22 enumerates. Ten records cover forced decisions the gap audit found uncovered (time and frames, kernel sets, system topology, run composition, the reference container, channels, referents, distributions and sampling, run outcomes, the CLI surface); ADR-000 is the process record; ADR-025 is the LLM exclusion split out of ADR-013 so that it can be superseded without touching the auditor-boundary import contract; and ADR-026 through ADR-029 are the records commissioned by `FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md` §19 (model identity and validity envelopes, declared scenario enumerations, the canonical observable vocabulary, derived bindings).
- PLAN AMENDMENT REQUESTED: §4 and §13 — a `review_signoffs: list[ReviewSignoff]` field on the frozen `ExperimentDesign` (§4, design plane) and on `EvidencePackage` (§13). The plan states several human sign-off gates in prose; without a field to record them they are norms that nothing can check, and two of them are described elsewhere in this set as binding gates on `evidence_grade`.
