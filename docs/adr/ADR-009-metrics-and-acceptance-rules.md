# ADR-009 — Metric and acceptance-rule separation, versioning, and deterministic failure signatures
**Status:** Accepted 2026-08-28 (MVP commitment; see Revisit triggers)
**Date:** 2026-08-26
**Deciders:** FarSight founding engineering
**Plan reference:** FARSIGHT_FOUNDATION_PLAN.md §13 (Metrics and rules), §4 (Design and Execution planes), §18 AT-3/AT-8, §21 tolerance-inflation kill; decision D13 (the tier vocabulary a criterion names)
**Related ADRs:** ADR-000 (the escape-hatch tokens this record's Enforcement uses), ADR-001 (canonical JSON hashing is what gives a metric definition an identity at all), ADR-004 (the epistemic band is what forces a three-valued verdict), ADR-006 (a criterion must name the reproducibility tier it is claimed at, and `ci-worker-order-invariance` is defined there), ADR-007 (the metric registry, acceptance results and failure groups are package content, and TOLERANCE-CHANGE sign-offs land in `review_signoffs`), ADR-008 (metrics run on raw SI float64 with ordered compensated reductions), ADR-010 (faults active at first violation are a signature component), ADR-013 (the `metrics` package may not import `engines` or `analysis`), ADR-020 (the sample grid a "first violation" index refers to), ADR-021 (what a referent reference is, and how a referent's stated uncertainty enters a comparison), ADR-023 (which run outcomes participate in the aggregate a criterion is evaluated over), ADR-024 (the CLI verb a rule diff is spelled with)

## Context

The forcing question is where a threshold lives. If the number that separates acceptable from unacceptable sits inside the function computing link margin, two things follow that we cannot live with. Changing that number changes the metric's identity, so every historical `MetricValue` becomes uncomparable with new ones although the arithmetic never moved — and §4 already rejects the candidate hierarchy for exactly this reason, calling an undetectable "metric changed mid-campaign" fatal for evidence. Worse, §21's tolerance-inflation kill allows exactly zero undocumented threshold loosenings, and a tripwire that depends on a reviewer noticing a constant buried in a numpy expression is not a tripwire.

The second question is what a verdict may say. The flagship claim is "achieved rate at or below the predicted supportable envelope, within one rate-ladder step", and §19 item 3 states DSOC's dominant uncertainties are almost all epistemic. A band that straddles a threshold is the normal case here. If the verdict domain is boolean, the only route to an answer is picking a point out of the p-box — the laundering of ignorance into probability that ADR-004 makes structurally impossible everywhere else. The honesty feature would die at the last mile.

The third is how failures are grouped. A 10k-run fault campaign yields hundreds of failures, and whatever groups them ships in `metrics/failure_groups.json` inside a package an outsider must re-derive in under two hours (AT-9). Anything the auditor cannot recompute exactly becomes the weakest link in the artifact.

## Decision

**A metric is a versioned pure function with no thresholds.** Its context contains only what a pure function needs, so the rule is enforced first by there being nothing else to call:

```python
@dataclass(frozen=True)
class MetricContext:
    channels: Mapping[str, np.ndarray]        # raw SI float64, C-order, read-only views
    channel_meta: Mapping[str, ChannelMeta]   # (name, unit, dtype, shape)
    run_facts: Mapping[str, str]              # hashed declared facts: outer grid index,
                                              # fault activation ids, validity flags
    constants: Mapping[str, float]            # ONLY source of numeric literals; comes from
                                              # the hashed definition, never from source text

class Metric(Protocol):
    def compute(self, ctx: MetricContext) -> MetricValue: ...
```

`MetricContext` is an in-memory, unhashed object, which is why `constants` is typed `float` here. In the hashed definition below each constant is a decimal string with a unit, per ADR-001's rule that no hashed document contains a JSON float; the conversion happens once, at load, in the same place `Quantity.to_si()` runs (ADR-008). The sample grid that indexes `channels` — how index *i* maps to an epoch, and whether all channels share one grid — is ADR-020's decision; "first violation" below is an index into it.

No filesystem, no engine handle, no RNG, no clock, no threshold. `MetricValue` carries `value`, `unit`, `defined: bool` and `undefined_reason`; NaN and Inf are forbidden by §7, so an empty domain yields `defined: false`, never a silent NaN.

**Identity is dual.** A criterion references a metric by the metric definition's digest. The `metric_id@version` spelling survives only as display resolved from the referenced object, exactly as ADR-021 resolves a referent's `referent_id@revision`. Identity is the SHA-256 (JCS profile, ADR-001) of the declarative definition *excluding* its `implementation` block. That block is recorded provenance, and it is checked, but it is not the identity:

```json
{
  "schema_version": "metric_spec/1",
  "metric_id": "link.margin_min_db",
  "version": "2.1.0",
  "title": "Minimum optical link margin over an in-view window",
  "inputs": [
    {"channel": "link.margin", "unit": "dB", "dtype": "float64"},
    {"channel": "geometry.in_view", "unit": "1", "dtype": "float64"}
  ],
  "domain": {"predicate": "geometry.in_view > constants.in_view_gate", "min_samples": 2},
  "reduction": {"op": "min", "over": "domain"},
  "output": {"name": "margin_min", "unit": "dB"},
  "constants": [
    {"name": "in_view_gate", "value": "0.5", "unit": "1",
     "rationale": "in_view is a 0/1 indicator channel; 0.5 decodes it, it is not a limit"}
  ],
  "undefined_when": ["no sample satisfies the domain predicate"],
  "thresholds": null,
  "implementation": {
    "callable": "farsight.metrics.link:margin_min_db",
    "package_version": "0.4.2",
    "source_sha256": "<raw file bytes>",
    "impl_ast_sha256": "<normalized AST over the entrypoint's internal closure>"
  }
}
```

The referent-comparison shape the DSOC claim needs still returns a number, never a judgement:

```json
{
  "metric_id": "dsoc.rate_ladder_step_delta",
  "version": "1.0.0",
  "title": "Signed ladder-step distance from achieved rate to supportable rate",
  "inputs": [
    {"channel": "link.supportable_rate", "unit": "bit/s"},
    {"referent": "dsoc.achieved_points@v3", "field": "achieved_rate_bps", "unit": "bit/s"}
  ],
  "reduction": {"op": "ladder_index(supportable) - ladder_index(achieved)",
                "ladder": "ccsds_142_0_b_1_scppm"},
  "output": {"name": "step_delta", "unit": "step"},
  "constants": [], "thresholds": null
}
```

The `name@version` spellings above — `dsoc.achieved_points@v3` for a referent, `dsoc.rate_ladder_step_delta@1.0.0` for a metric — are the human-readable form and never the in-document one, because ADR-001 rule 7 admits only bare 64-hex digests inside a frozen document. ADR-021 settles the referent half, binding a metric's referent input to a digest through `ComparisonSpec`. This record settles the metric half, below: a criterion carries `metric_ref`, the digest of the metric definition, and `metric_display` is resolved from the referenced object for reading and is never a lookup key. Nothing now blocks the week-3 metric-registry freeze.

**An acceptance criterion is a separate versioned object, and thresholds live only here:**

```json
{
  "schema_version": "acceptance_criterion/1",
  "criterion_id": "dsoc.achieved_within_envelope",
  "version": "1.2.0",
  "metric_ref": "<64-hex digest of the metric definition>",
  "metric_display": "dsoc.rate_ladder_step_delta@1.0.0",   // derived from the resolved object; never a lookup key
  "comparator": ">=",
  "target": {"kind": "literal", "magnitude": "-1", "unit": "step"},
  "tolerance": {"absolute": {"magnitude": "0", "unit": "step"}, "relative": "0"},
  "reproducibility_tier": "B",
  "epistemic_policy": "band_straddle_is_indeterminate",
  "rationale": "One-sided envelope claim within one ladder step of the lower edge. No margin added; operational margin is unpublished and is an unknowns-register entry.",
  "supersedes": "<64-hex digest of 1.1.0>",
  "change_reason": "Tier raised A -> B after second-machine replay; threshold unchanged.",
  "authorized_by": "<freezing human identity>"
}
```

This criterion is deliberately **one-sided**: it tests `step_delta >= -1` and nothing tests an upper edge, because the claim is "achieved does not exceed the predicted envelope by more than one ladder step" and there is no physical claim about a lower edge to falsify. ADR-007's `claim_statement.falsifier` is the exact restatement of this rule and says so; a falsifier naming a condition no rule computes would be unfalsifiable in the literal sense.

`target.kind` may also be `metric_ref`, carrying a second metric definition's digest in the same form as the criterion's own, so "achieved at or below supportable" joins two metrics rather than smuggling a comparison into either.

**Verdicts are three-valued**, evaluated over the epistemic band from ADR-004's outer scan (the inner aleatory summary statistic is named by the criterion and reduced per ADR-008, over the run set ADR-023 says participates):

```
criterion holds at every point of the band -> pass
criterion holds at no point of the band    -> fail
otherwise                                  -> INDETERMINATE
metric undefined for the run set           -> INDETERMINATE (reason: metric_undefined)
```

`indeterminate` is a result, not an error: it is written to `acceptance_results.json`, it is its own report column, and the CLI exits zero for it. `verify` exits nonzero only on integrity failures (ADR-007). A verdict inherits `contains_epistemic_collapse` from any tainted input.

**Failure grouping is exact signature match.** The signature is a canonical document; the group id is its hash:

```json
{"violated_rule_ids": ["dsoc.achieved_within_envelope@1.2.0"],
 "active_faults": ["fm.pointing_degradation@1.0.0:act_03"],
 "epistemic_bin": "outer_grid_index=(2,0,5)"}
```

Lists are lexicographically sorted. "First violation" means the lowest *sample index* at which any violated rule leaves its acceptance region, ties broken by sorted rule id — never a wall clock. Nothing is clustered, ranked by similarity, or summarized.

## Options considered

### Option 1 — One object: the metric computes and asserts — REJECTED
The unit-test model every engineer already knows: one version, one number, no join at evaluation time, no dangling references. Genuinely simpler to build and to author. Rejected because a threshold edit churns the metric hash and orphans historical values; because §21's zero-allowed tolerance inflation would have no object to diff; and because the same margin computation is legitimately judged against different limits by different customers, which under this option forks the arithmetic.

### Option 2 — Split, metric identity = SHA-256 of the Python source text — REJECTED
Maximally honest about what actually ran, trivial to compute, impossible to fake. Rejected as brittle and opaque: a reformat, a docstring fix or a local rename invalidates identity, so either historical references break or nobody dares touch a metric file — and an auditor holding a package gets a hash over source they may not read, when what they need to check is inputs, domain, reduction and unit.

### Option 3 — Split, identity = declarative definition only — REJECTED
Readable, refactor-stable, exactly what an auditor wants to inspect. Rejected because the implementation drifts underneath a frozen definition undetected: the definition says "min over the in-view window", the code quietly starts skipping the first sample, and the recorded hash never moves. AT-8 requires a mutated implementation without a version bump to fail CI; this option gives that check nothing to compare.

### Option 4 — Dual identity: declarative hash is identity, implementation hashes are provenance — CHOSEN
The definition is the auditable, refactor-stable identity. The implementation is pinned twice: `source_sha256` over raw bytes for the package record, and `impl_ast_sha256` over the normalized AST of the entrypoint plus the FarSight-internal functions reachable from it, which is what CI compares. Formatting moves freely; behavior does not. The soundness limit of "reachable" is stated in Enforcement rather than assumed away.

### Option 5 — Boolean verdicts, straddle raised as an error — REJECTED
Consumers want a boolean, three-valued logic complicates every aggregate, and "the tool refused to answer" demos badly. Rejected because on the flagship benchmark the straddle is the common case, so the operator's only route to a verdict becomes asserting a value for something unknown.

### Option 6 — Clustering or model-assisted failure triage — REJECTED
Genuinely better at finding structure: exact matching will produce a long tail of singletons on a high-cardinality campaign, and clustering would surface the "these 300 failures are one problem" narrative a mission-assurance engineer actually wants. Rejected because it would be the first thing in the package an auditor could not reproduce, and because cluster results shift with library versions and initialization. LLM-assisted variants are separately foreclosed by ADR-025.

## Consequences

**Buys us:** A threshold change becomes a hash-visible, second-reviewed diff on a small rule object, so `farsight diff --rules` can enumerate every loosening between two versions and the §21 tripwire becomes mechanical. Metric values survive threshold history. `verify` recomputes both metrics and verdicts from raw `.npy` channels with zero engines installed, and the AT-9 auditor works from a readable definition rather than our source.

**Costs us:** Two registries, two version lines, and a join validated at freeze. Every numeric literal in a metric implementation must be declared in the definition with a rationale — real authoring friction, and the only reason the no-threshold rule is checkable at all. Three-valued verdicts propagate into every aggregate, table and exit-code decision.

**Forecloses:** Metrics can never carry a data-dependent threshold, so a rule like "margin must exceed the pass median" must become a second metric plus a `metric_ref` criterion; natural rules become two objects and read worse. Metrics cannot short-circuit on breach, so pathological campaigns pay full compute. Metrics cannot read auxiliary files, so any lookup table enters as a hashed `DataArtifact` channel or as declared constants, which will be clumsy for table-driven work. We ship a failure view that on a wide fault campaign will look like an unhelpfully long list; we will not smooth it, and some prospects will read that as immaturity. And because the package carries the metric *definition* plus two hashes of the implementation rather than the implementation itself, an auditor recomputing on a different `farsight` version is performing a self-consistency check against their installed code, not against the code that produced the package; `impl_ast_sha256` is the only evidence they have that the two were the same, and it is a hash they cannot recompute without our source (ADR-007).

## Confidence and revisit triggers

| Sub-decision | Confidence | Revisit trigger |
|---|---|---|
| Thresholds live only in criterion objects, never in metrics | 0.92 | An acceptance rule authored in weeks 3-6 cannot be expressed as comparator plus target plus tolerance, or ≥3 of the 8 K5 interviews (end wk 6) describe a rule of that shape they use today. Then the criterion grows a restricted predicate AST reusing ADR-010's, never embedded Python. |
| Dual identity: declarative hash is identity, implementation hashes are provenance | 0.80 | `metric-registry-consistency` (AT-8) produces a false negative found by hand in weeks 3-6 — a behaviour change that moved no hash — which means the reachable-set approximation is too weak to carry AT-8. |
| Three-valued verdicts, `indeterminate` as a first-class result | 0.85 | The week-8 external auditor (AT-9) reads `indeterminate` as a tool failure rather than a result. That is a §9 margin-first presentation fix, not a type-system change, but it is the signal that the presentation layer is not carrying the type system. |
| Exact-signature failure grouping | 0.75 | More than a quarter of failing runs in the week-6 campaign land in singleton groups, which indicts the `epistemic_bin` granularity rather than the grouping rule. |
| Metric purity is enforceable by construction plus a lint | 0.70 | Any metric merged in weeks 3-6 reads module-level or class-level state and passes `test_metric_purity` — that is, the denylist misses a real impurity, which is the failure mode the check cannot exclude by construction. One instance forces either a stricter execution sandbox for metric evaluation or an explicit downgrade of the purity claim in external materials. |

## Enforcement

- **import-linter contract `metrics-purity`** (**first green by week 1**): `farsight.metrics` may not import `farsight.engines`, `farsight.analysis`, `farsight.evidence`, nor `os`, `pathlib`, `time`, `datetime`, `random`, `numpy.random`, `socket`, `urllib`, `requests`. This half is sound: it is a statement about imports, and imports are decidable.
- **PARTIALLY MECHANIZED: `tests/unit/test_metric_purity.py`** (**first green by week 2**). AST scan of every registered metric module. It fails on a numeric literal not declared in that metric's `constants` block (0, 1 and axis arguments excepted by an explicit allowlist), on a `bool` or verdict-typed return annotation, on any banned call name, and — folding in what was previously only a revisit trigger — on any `constants` entry appearing as an operand of a comparison, which is how a threshold would be smuggled in under a physical-sounding name. What it cannot do is prove purity. Purity is a semantic property and undecidable in general; an AST denylist catches imports and obvious I/O, and it does not catch a metric that reads a module-level global, mutates a captured default argument, or depends on a class attribute set elsewhere. The honest residue is exactly that class. Review checklist item **METRIC-PURE-1** — "the metric reads nothing but its `MetricContext` and writes nothing" — carries it, and a METRIC-PURE-1 row lands in `review_signoffs` (ADR-007) for the release that introduces or changes a metric implementation. `MetricContext` being a frozen dataclass with no handles is what makes the residue small; it is not what makes it empty.
- **PARTIALLY MECHANIZED: CI job `metric-registry-consistency`** (this is AT-8; **first green by week 4**, when a metric registry with more than one version exists). It recomputes `impl_ast_sha256` and fails when it differs while `version` is unchanged, naming the metric. Two limits, both stated rather than assumed. First, coverage: it covers FarSight-internal reachable code only, so a behaviour change originating in NumPy is caught by the ADR-006 environment fingerprint, not here. Second, soundness: static call-graph reachability in Python is approximate, and a behaviour change routed through `getattr`, a registry lookup or a dynamically bound attribute is invisible to the analyzer. We convert the unsound check into a sound one by constraining its input rather than by improving the analysis: **metric implementations may not use dynamic dispatch**, and a lint in `test_metric_purity` fails on `getattr`, `eval`, `exec`, `importlib` and attribute assignment to a module or class inside a metric module. Within that constraint the reachable set is exact; outside it, the check is void, which is why the constraint is enforced and not merely requested.
- **`tests/unit/test_criterion_thresholds.py`** (**first green by week 2**): every `target` and `tolerance` must be a decimal string with a unit (ADR-001), every criterion's `metric_ref` must resolve to a registered metric definition, and its `metric_display` must equal that resolved object's `metric_id@version`; freeze fails otherwise.
- **`tests/unit/test_failure_signature_determinism.py`** (**first green by week 5**, since it needs the pool): the same campaign at `--workers 1` and `--workers 8`, and with shuffled completion order, must yield identical group ids. It is the sibling of `ci-worker-order-invariance` (defined in ADR-006) and shares its schedule for the same reason — neither can run before the runner exists.
- **`farsight evidence verify`** (defined in ADR-007) recomputes metrics from raw channels and re-evaluates all criteria; any discrepancy exits nonzero naming the item (AT-3). **First green by week 4.**
- **NOT MECHANIZABLE:** no check can decide whether a `change_reason` for a loosened threshold is physics or rationalization. Parsing prose for a justification is not a check; it is a wish. Review checklist item **TOLERANCE-CHANGE** — "the stated physical or numerical reason for this threshold or tolerance movement was independently accepted by a second developer, who did not see the failing result first" — substitutes. CI enforces the mechanical half only: that `change_reason` is non-empty, that `version` and `supersedes` both moved, and that CODEOWNERS review landed on any diff touching `target` or `tolerance`. A TOLERANCE-CHANGE row naming the reviewer and date lands in the `review_signoffs` list of every `ExperimentDesign` that freezes the changed criterion and of every package built from it (ADR-007), so the §21 tolerance-inflation count is a query over rows rather than a memory.

## References

- FARSIGHT_FOUNDATION_PLAN.md §4 (verdict domain pass | fail | indeterminate; `MetricValue`, `AggregateResult`, `Verdict` taint), §7 (canonical serialization; NaN/Inf forbidden), §8 (ordered compensated reductions), §12 (worker-count invariance), §13 (metrics and rules; `metric_registry.json`, `acceptance_results.json`, `failure_groups.json`), §14 items 6-7, §18 AT-3/AT-8/AT-9, §21 tolerance-inflation kill, §22.
- CCSDS 142.0-B-1 (SCPPM) supplies the rate ladder used by `dsoc.rate_ladder_step_delta`; the ladder table enters as a hashed `DataArtifact`, never as metric source and never as a number in this record (plan §14 item 5).
- CLI note: the rule diff is spelled `farsight diff --rules`, folded into plan §6's existing `diff` verb rather than introduced as a new `farsight rules` command. No plan amendment is needed; ADR-024 owns the CLI surface and the flag grammar.
- Closed cross-reference: the `name@version` referent and metric references shown in the examples above are the human-readable spelling. Their canonical form inside a frozen, content-addressed document is bare 64-hex per ADR-001 rule 7 — bound to a slot by `ComparisonSpec` for a referent (ADR-021), and carried as `metric_ref` with a derived `metric_display` for a metric (this record). Nothing blocks the week-3 metric-registry freeze.
- ADR-000, ADR-001, ADR-004, ADR-006, ADR-007, ADR-008, ADR-010, ADR-013, ADR-020, ADR-021, ADR-023, ADR-024, ADR-025.
