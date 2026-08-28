# ADR-025 — No LLM SDK: the exclusion as a structural absence
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §3 decision D14, §6 (boundary rules: no LLM SDK anywhere), §4 (LLM-assisted authoring permitted at draft stage; freeze authorization is always a human act), §2 (FarSight refuses to invent customer inputs), §13 (failure signatures are exact-match tuples)
**Related ADRs:** ADR-013 (assembles the `.importlinter` file this contract ships in, and owns the `analysis/` quarantine that Option 2 would have reused), ADR-004 (the Belief type system is the thing an LLM must never shortcut), ADR-001 (freeze authorization is a human act, which this decision is what keeps meaningful), ADR-014 (the lock file is the artifact the claim is checkable against, and its `env-guard` job runs the scan), ADR-009 (failure signatures are exact-match tuples; an LLM may propose a view, never the record), ADR-012 (no phone-home code path exists structurally — an SDK would be one), ADR-000 (status values and the escape-hatch tokens used below)

## Context

FarSight's entire pitch is that unknowns are never silently filled in. §2 says a parameter without provenance enters as `unknown`, never as a default; §9 makes that a type-system property with no `.to_distribution()` on an epistemic belief; §14 item 5 says a golden number may never originate from our own code. A generative model is, precisely and by design, a machine for fluently filling in unknowns. Asked "what is the likely GLR optical-train throughput?", a competent model returns a confident number with a plausible justification, and a confident number is the exact artifact this product exists to refuse.

The forcing question is not "would we misuse one". It is **what form of assurance we can offer a person who does not trust us**, because that person — a mission-assurance engineer deciding whether to accept an artifact, and the procurement reviewer behind them — is the audience the whole product is aimed at (§18 AT-9). Two forms are available:

- A **policy**: "we do not use an LLM to generate parameters." True, and unfalsifiable from outside. It is a statement about our intentions, checked by trusting us, in a product whose whole argument is that you should not have to.
- A **structural absence**: "no LLM SDK is installed anywhere in this product; here is the lock file." Checkable in one command by a stranger, which is the same property the evidence package has, offered to the same audience.

What makes this a decision rather than a posture is that the useful middle option is genuinely available and genuinely cheap, and it would be dishonest to pretend otherwise. ADR-013 already quarantines `analysis/` behind a CI-enforced import-linter contract; plan §4 already permits LLM-assisted authoring at draft stage, with freeze authorization always a human act. An SDK confined to `analysis/` would sit outside the truth loop by exactly the mechanism that keeps pandas outside it, and it would buy real things: help authoring tagged-union YAML, which §19 ranks as risk 6 with "schema-validated templates" as its only mitigation; and a proposed thematic *view* over already-computed failure signatures for an engineer looking at hundreds of singleton groups, which ADR-009's own revisit trigger anticipates. Refusing that has a price. This record's job is to name the price rather than to pretend the option was weak.

What breaks if we get it wrong runs in both directions. Take the SDK and the sales sentence acquires a qualifier — "no LLM, except in the analysis extra" — and in an assurance conversation the qualifier is the part the reviewer remembers and repeats. Refuse it and we lose a real aid and will re-litigate this every quarter, which is why the never-list below has to be written now, while nobody in the room wants anything from it.

An earlier draft of this set carried the exclusion inside ADR-013 alongside package boundaries. That was wrong twice over: it gave the exclusion four "options considered" that were all about packaging, so the exclusion itself had none; and it meant that acting on an LLM revisit trigger would require superseding the `auditor_boundary` contract in the same motion. It is its own number now, which also makes it independently citable in a procurement conversation — which is, honestly, most of its job.

## Decision

**No LLM SDK is a dependency of this repository, in any extra, including `dev`.** Nothing in the MVP uses an LLM. This is recorded as a *structural absence*, not a feature: there is no code path to disable, no configuration flag, no API key to leave unset, and no endpoint constant anywhere in the tree. If a customer asks what stops FarSight from hallucinating a parameter, the answer is a lock-file diff, not an assurance.

This record owns the contract; it ships in the `.importlinter` file ADR-013 assembles and runs in ADR-013's `boundaries` job.

```ini
[importlinter:contract:no_llm_sdk]
name = no LLM SDK is a dependency of this repository
type = forbidden
source_modules = farsight
forbidden_modules =
    anthropic
    openai
    langchain
    langchain_core
    llama_index
    transformers
    litellm
    ollama
    cohere
    mistralai
    google.generativeai
```

The list is names; the *rule* is "no generative inference inside this distribution or its lock". The list is a mechanical approximation of the rule and grows by edit, which is stated here rather than left implicit because the gap between the two is where this decision is weakest (see Enforcement).

**What an LLM may never do, at any future date, without an ADR that supersedes this one.** It may not: invent a constant; generate an authoritative distribution, interval or correlation; modify any simulation input; compute any authoritative result; decide `pass`, `fail` or `indeterminate`; fabricate missing data; or convert epistemic uncertainty into probabilistic precision. The last one is the specific hazard and the reason the list exists — the failure mode is not a model that refuses, it is a model that obliges. Every item on this list is something a fluent model does well and does invisibly, and every item is something ADR-004's type system exists to make structurally impossible for FarSight's own code. A dependency that could do them by another route would make that type system decorative.

**Where one may legitimately sit later.** Strictly downstream of frozen, content-addressed results: in `analysis/`, or in a separate tool outside this distribution, doing work a human then checks. Explaining what a deterministic result means. Clustering already-computed failure signatures into candidate themes for human review — and note the narrowness: §13 fixes the failure signature as an exact-match tuple and keeps it that way, so an LLM may propose a grouping *view* over signatures, never the grouping of record. Summarizing a campaign. Helping a user navigate the assumption and unknown registers. Assisting *authoring* at draft stage, which §4 already permits with freeze authorization always a human act — and which, under this decision, happens in the user's own editor, outside FarSight's process and outside its dependency tree.

**The claim we are allowed to make**, stated exactly, because an overclaim here is worse than no claim: *"No LLM SDK is a dependency of FarSight, in any extra. Here is the lock file."* Not "FarSight does not hallucinate" — that is a claim about behaviour, unfalsifiable in the same way the policy option is, and we should not trade a checkable sentence for a grander one.

## Options considered

### Option 1 — No SDK anywhere, in any extra, including `dev` — CHOSEN
The claim is answerable `no` from a lock file with no qualifier, by a stranger, in one command.

### Option 2 — SDK permitted only inside the `analysis/` extra, quarantined by the same contract that quarantines pandas — REJECTED
This is the strong option and it deserves the space.

It is **materially useful**. Authoring ergonomics of tagged-union YAML is a ranked risk in the plan's own list (§19 item 6) whose entire mitigation is "schema-validated templates"; a drafting assistant that turns an engineer's parameter table into a validated `UncertaintySpec` skeleton attacks that risk directly and would save real hours in weeks 3-4, when every parameter in the flagship gets belief-tagged by hand. The failure-triage case is equally real: ADR-009's own revisit trigger contemplates more than a quarter of failing runs landing in singleton groups in the week-6 campaign, and a human reading four hundred singleton tuples is a worse instrument than a human reading twenty proposed themes over those same tuples.

It is **already permitted in principle**. §4 states that LLM-assisted authoring is permitted at draft stage and that freeze authorization is always a human act. The plan has already decided that a model may touch a draft; Option 2 only changes *where the model runs*.

It **costs nothing structurally**. `analysis/` is outside the truth loop by construction: ADR-013's `analysis_quarantine` contract forbids every truth-loop package from importing it, and CI enforces that from the first commit. The mechanism that keeps a DataFrame's implicit column ordering out of a hashed value is exactly the mechanism that would keep a completion out of one. This is not a new trust surface; it is an existing, tested, CI-enforced one with one more package inside it. And a customer who never installs `farsight[analysis]` never installs the SDK at all.

Rejected anyway, on one ground that we believe defeats all of the above: **"is an LLM installed?" must be answerable `no` from a lock file with no qualifier.** "Yes, but only in the analysis extra, which is outside the truth loop, which is enforced by an import-linter contract" is a true, correct, three-clause answer. In the room where it matters — a mission-assurance reviewer deciding whether to accept an artifact, with a procurement officer downstream — a three-clause answer is a caveat, and the caveat is what gets repeated. The exclusion's commercial value is not that it prevents a specific harm the quarantine would also prevent; it is that it is unqualified, and an unqualified claim is a different object from a qualified one.

Two secondary reasons, weaker than the first but real. An extra is one `pip install farsight[analysis]` from every developer machine, and once the SDK is resolvable in the environment, the distance between "propose a view" and "write the record" is one convenience function added under week-6 schedule pressure — the same erosion argument ADR-013 uses to reject convention-only boundaries, applied to ourselves. And an SDK brings an API key, an endpoint and a network call into a repository whose §16 posture is that no phone-home code path *exists* — absent, not defaulted-off — which is a second unqualified claim we would have to start qualifying.

### Option 3 — SDK in `dev` only, for test-data generation — REJECTED
Also stronger than it looks. Dev dependencies never ship in the wheel, so the shipped-product claim survives intact. The use is legitimate and bounded: generating adversarial YAML and parameter tables to feed the Hypothesis property suite, and authoring fixture scenarios, neither of which could ever become a golden — §14 item 5 already forbids a golden originating from our own code, and an LLM is further from admissible than our own code is, so there is no path from this use to a contaminated number.

Rejected on the same axis as Option 2, one level down. The `dev` extra is resolved into `uv.lock`, and the check that backs this decision scans the lock rather than the imports (below), so accepting Option 3 degrades the claim from "not in the repository" to "not in the shipped wheel" — a distinction that is real to an engineer and invisible to a procurement reviewer reading a dependency report. Two further reasons make the trade a bad one even ignoring the claim: test data an LLM produced is test data nobody can regenerate deterministically, which collides with the property suite's own reproducibility discipline and with §12's rule that no hashed value depends on anything unrepeatable; and the actual need is already met by Hypothesis, which is in `dev` already and is built for exactly this — generating adversarial inputs from a declared strategy, reproducibly, with a shrinking counterexample at the end.

## Consequences

**Buys us:** a one-command answer to the only question a sceptical reviewer will ask about generative AI in this product, with no qualifier attached; no API key, endpoint or outbound call added to a codebase whose §16 posture is that no phone-home path exists; a never-list written while it is free, rather than negotiated later while somebody wants something; and an independently citable record, which is most of what this decision is for.

**Costs us:** a genuinely useful drafting aid, lost. Belief-tagging every parameter in the flagship (weeks 3-4) stays hand work; tagged-union YAML authoring keeps templates as its only mitigation against a risk the plan itself ranks; and failure triage over hundreds of singleton signature groups in week 6 stays a human reading tuples. Adversarial test-corpus generation falls back entirely on Hypothesis and our own imagination, so a class of authoring bug will go uncaught longer than it needed to. And — stated plainly because it is the honest forecast — **this decision will be re-litigated.** The first customer who asks for natural-language experiment authoring, and every quarter in between, will reopen it. The cost includes that recurring argument, and the mitigation is that the never-list above is what any superseding ADR must restate and defend rather than quietly drop.

**Forecloses:** in-product LLM features of every kind, including ones a customer may genuinely want and pay for — natural-language experiment authoring, a conversational walkthrough of an evidence package for a non-specialist reviewer, automated first-pass triage of a failed campaign. A competitor will ship those and demo well. We are choosing an unqualified sentence over a feature set, deliberately, and if the discovery track says the sentence is worth less than the features, that is information and the answer is a superseding ADR, not an exception.

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| No LLM SDK in the shipped distribution or any runtime extra | 0.92 | >=3 of the 8 K5 discovery interviews (end wk 6) name an in-product LLM capability as a condition of adoption, *and* none of them names the exclusion as a reason to trust the artifact. Both halves are required: the trigger is a net commercial signal, not a feature request. |
| No LLM SDK in `dev` either | 0.70 | The week-2 parameter-table work or the week-3/4 belief-tagging of the flagship spends more than two dev-days on hand-authoring that a drafting assistant would plausibly have absorbed, measured against the engineer-hours ledger §17 already requires; or the Hypothesis property suite is found to need hand-built adversarial corpora that Hypothesis strategies cannot express. This is the shakiest row: it trades real leverage for a distinction between "not in the product" and "not in the repository" that may turn out to be one nobody outside this team actually draws. |
| That the exclusion is worth stating as a product claim at all | 0.75 | The K5 interview notes contain zero unprompted mentions of AI provenance, hallucination or model use across all eight interviews — which would mean we spent a foreclosure on an anxiety our buyers do not have. Conversely, the week-8 external cold auditor (AT-9, §17) citing the absence as something that increased their trust is the confirming observation. |
| The never-list is the right list | 0.85 | Any superseding proposal argues that an item on the list is too broad — that is the moment to find out whether the list was drafted honestly or defensively — or a legitimate downstream use is blocked by an item that was aimed at something else. |

## Enforcement

- **import-linter contract `no_llm_sdk`** (owned by this record; ships in the `.importlinter` file ADR-013 assembles and runs in CI job **`boundaries`**, defined in ADR-013). First green by **week 1**, from the first commit. It catches an import of a named SDK anywhere under `farsight`.
- **`tests/unit/test_no_llm_dependency.py`** (owned by this record; runs as a leg of CI job **`env-guard`**, defined in ADR-014). First green by **week 1**. It scans `pyproject.toml` and every extra resolved into `uv.lock` — `dev` and `analysis` included — for the forbidden distribution names and fails on a match. This test, not the linter, is the actual guarantee: import-linter sees imports, and a declared-but-unimported dependency is exactly how this rule would first be broken.
- **PARTIALLY MECHANIZED:** a name denylist cannot recognize an SDK published under a name not on the list, a client vendored into the tree with no new dependency, or a raw HTTPS POST to a model endpoint written with the standard library. Two of those three residues are already covered mechanically and are named here so the coverage is legible rather than assumed: the import-linter contract `no-network-in-truth-loop` and the socket-disabled CI leg `test-no-sockets` (both defined in ADR-012) make any runtime call to any endpoint fail in CI; and `tests/unit/test_dependency_allowlist.py` (defined in ADR-014) fails on *any* top-level distribution absent from its literal allowlist, which catches the unknown-name case at the lock level without needing to know the name. What remains uncovered is a vendored client checked into the tree that adds no dependency and makes no call during the test suite. That residue is review-checklist item **LLM-1** — "does this change introduce a dependency, an endpoint, or vendored code that performs generative inference?" — whose sign-off lands in the `review_signoffs` list on the frozen `EvidencePackage` (ADR-000), asserting the item for the tool version that produced that package, so an unanswered item is an auditable absence rather than a norm somebody was supposed to remember.

## References

- FARSIGHT_FOUNDATION_PLAN.md §2 (FarSight refuses to invent customer inputs; a parameter without provenance enters as `unknown`), §3 D14 (LLM boundary enforced structurally; import-linter CI rule; "an architectural absence, not a feature"), §4 (LLM-assisted authoring permitted at draft stage; freeze authorization is always a human act), §6 (boundary rules: no LLM SDK anywhere), §9 (no epistemic-to-probability path except an authorized collapse), §13 (failure signature is an exact-match tuple; clustering is out of MVP scope because an auditor could not reproduce it), §14 item 5 (a golden number may never originate from our own code), §16 (no telemetry, structurally: absent, not defaulted-off), §17 (engineer-hours ledger; week-8 external cold audit), §18 AT-9, §19 item 6 (authoring ergonomics of tagged-union YAML), §21 K5.
- ADR-001, ADR-004, ADR-009, ADR-012, ADR-013, ADR-014, ADR-000.
- This record is beyond §22's list of twelve ADRs, as ADR-000 already notes for the set as a whole. **No plan amendment is requested:** D14's substance is unchanged and nothing here departs from §6 or §4 — only the decision's home has moved out of ADR-013, which carried it in an earlier draft with no options considered.
