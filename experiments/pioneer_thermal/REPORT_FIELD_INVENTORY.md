# What `report/summary.md` shows, and where each value comes from

The report is generated from the package JSON and the verifier re-renders it, so prose cannot
drift from the record. That alone turned out not to be enough: **regenerating Markdown from
unchecked JSON reproduces whatever the JSON says**, including values nothing had compared
against the record verification actually uses.

MEASURED 2026-10-01: a package displaying seed `123`, one iteration and a tolerance of `999`
verified, because those display copies were never checked; a forged duplicate scenario row made
the report print scenario 5 twice, once passing and once failing, because the lookups kept the
last occurrence; and an acceleration recorded in `km/s2` printed as `0.0023` under a
`10⁻¹⁰ m/s²` heading.

This inventory is the list that closed those. Every scientific or execution value the report
displays appears here with the record that is authoritative for it and how the verifier
establishes they agree.

## Scenario rows

| Displayed | Source | How it is established | Duplicate representation |
|---|---|---|---|
| scenario number | `metrics/results.json` `gate_1.scenarios[].scenario` | `_one_row_per_scenario` requires exactly one row per expected scenario **before** any lookup is built; duplicates, missing and unexpected numbers are each named | also in `experiment/scenario_inputs.json`, validated the same way |
| acceleration | same row, `computed` | recomputed from validated inputs with the packaged code; compared relatively at 1e-12 with no absolute floor | — |
| its unit | same row, `computed.unit` | validated against `m / s2`; a compatible unit is converted explicitly, **and the renderer converts before formatting** so the printed number matches the heading | — |
| residual | same row, `residual_1e10` | **derived** from the recomputed acceleration and the published target in the content-addressed referent object, then compared with the stored copy | the referent object holds the target |
| within tolerance | same row, `within_tolerance` | **derived** from the derived residual and the criterion tolerance | — |

## Verdicts

| Displayed | Source | How it is established |
|---|---|---|
| gate 1 verdict | `metrics/results.json` `gate_1.verdict` | derived from the derived per-scenario flags |
| gate 2 verdict | `gate_2.verdict` | derived from the recomputed Monte Carlo against the criteria |
| overall verdict | `manifest.json` `overall_verdict` | derived from both gates; also cross-checked against each `ClaimResult`, which must aggregate the results object actually recomputed |

## Targets, tolerances and execution settings

These are the duplicated display copies. Each is compared with its authoritative record, **field
by field**, so one disagreement cannot mask another.

| Displayed copy | Authoritative record |
|---|---|
| `manifest.json` `execution.seed` | `experiment/execution_settings.json` `seed` |
| `manifest.json` `execution.iterations` | `experiment/execution_settings.json` `iterations` |
| `metrics/results.json` `gate_1.tolerance_1e10` | `experiment/acceptance_criteria.json` `gate_1.tolerance_1e10` |
| `metrics/results.json` `gate_2.target_central_1e10` | `experiment/acceptance_criteria.json` `gate_2.target_central_1e10` |
| `metrics/results.json` `gate_2.target_half_width_1e10` | `experiment/acceptance_criteria.json` `gate_2.target_half_width_1e10` |
| `metrics/results.json` `gate_2.tolerance_1e10` | `experiment/acceptance_criteria.json` `gate_2.tolerance_1e10` |

The list lives in `verify_evidence_package.py` as `DUPLICATED_DISPLAY_VALUES`, and a test walks
every pair against a real package so an entry that addresses nothing fails rather than passing
vacuously.

The Monte Carlo's **rebuilt** central value and half-widths are not in this table: they are not
duplicates of anything, they are recomputed here from the recorded seed and settings and
compared with what the package records.

## Provenance and assumptions

| Displayed | Source | How it is established |
|---|---|---|
| commit, dirty flag | `manifest.json` `code` | recorded at build time; absent git metadata prints `GIT METADATA UNAVAILABLE` rather than reading as clean |
| assumptions | `registers/assumptions.json` | must equal the addressed `Assumption` objects the manifest references |
| package format, variant | `manifest.json` | descriptive; not a scientific value |

## What this does not cover

The inventory is bounded to the fields this report displays. It is not a general mechanism for
arbitrary packages, and a new displayed field needs a new row here plus an entry in
`DUPLICATED_DISPLAY_VALUES` if it duplicates a record. Nothing here addresses authenticity: the
root hash is unsigned, so a coherent rewrite of code, inputs, claims and report together remains
outside what verification can detect.
