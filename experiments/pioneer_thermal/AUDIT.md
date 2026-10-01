# Auditing the Pioneer evidence package

For an independent reviewer. The goal is that you can build the package, verify it yourself, and
form your own view of what it does and does not establish — without taking anything here on
trust, and without installing a simulation engine.

**Expect the reproduction to fail its own criteria.** That is the result, not a fault. Two of the
pre-registered gates are missed, the package records `not_reproduced`, and it verifies cleanly
while saying so. A workflow that could only package successes would be worth nothing.

## 1. Install

Python **3.12** (the project pins `>=3.12,<3.13`). Verified on 3.12.10.

```bash
git clone https://github.com/xuanhuyle/farsight
cd farsight
python -m venv .venv && .venv/Scripts/activate      # POSIX: source .venv/bin/activate
pip install .
```

**Base install only — do not add extras.** `spiceypy`, Basilisk, GMAT, pandas and matplotlib are
deliberately absent; verification must work without them, and a test enforces it by making those
names unimportable. Installing them proves less, not more.

## 2. Build

```bash
python experiments/pioneer_thermal/build_evidence_package.py --out ./pioneer_pkg
```

Prints the root hash and `verdict: not_reproduced`, and exits **0** — building a failed
reproduction is a success of the workflow. Pass `--built-at 2026-10-01T12:00:00+00:00` to make
two builds byte-identical; without it the honest build timestamp differs, so the root hash does.

The counterfactual is a separate package, never a correction to the baseline:

```bash
python experiments/pioneer_thermal/build_evidence_package.py --out ./pioneer_cf \
    --counterfactual w_rtgb_geometric
```

## 3. Verify

```bash
python experiments/pioneer_thermal/verify_evidence_package.py ./pioneer_pkg
```

Exit **0** on an intact package. Exit codes distinguish what failed: `2` integrity, `3` schema,
reference or cross-file inconsistency, `4` recomputation mismatch, `5` the package contradicts
its own numbers, `6` unreadable.

Four checks run, and the output says what each established. Only the first three can fail on a
scientific miss; check 4 reports the miss and fails only on contradiction.

## 4. The expected scientific outcome

| | |
|---|---|
| Scenarios 1–4 | reproduce to the printed precision: residuals +0.0021, +0.0041, +0.0015, −0.0019 |
| Scenario 5 (upper bound) | **misses**: rebuilt 6.9166 against a published 6.71, residual +0.2066 |
| Monte Carlo at t = 26 yr | **misses**: rebuilt ≈5.70 ± 1.19 against a published 5.8 ± 1.3 |
| Overall | `not_reproduced` — gate 1 fail, gate 2 fail |

Units are 10⁻¹⁰ m/s². The Monte Carlo figures depend on the iteration count; the default build
uses 10⁴ under seed 20260928.

## 5. What to inspect, in this order

1. **`PARTIAL_FORMAT.md`** (inside the package) — what of ADR-007 is implemented and what is not.
   Read this before concluding anything is missing.
2. **`report/summary.md`** — the generated report. Do not trust it on its own; it is checked
   against the record, and [REPORT_FIELD_INVENTORY.md](REPORT_FIELD_INVENTORY.md) traces every
   displayed value to the record that governs it.
3. **`PREREGISTRATION.md`** (in `experiment/`) — the criteria, fixed before the model existed.
   Its commit, `934505e`, predates the first result commit, `d8f8ba7`.
4. **`registers/assumptions.json`** — what the reproduction assumes and what breaks if each is
   wrong. This is the part a reader cannot derive from the numbers.
5. **`metrics/results.json`** and **`experiment/scenario_inputs.json`** — the numbers and the
   inputs that produced them, as decimal strings with units; no JSON floats anywhere.
6. **`code/reproduce_thermal_acceleration.py`** — the authoritative calculation, hashed into the
   package. The builder imports it rather than restating any formula.
7. **`hashes/file_hashes.json`** — reproduce the root hash yourself: it is
   `sha256(JCS(file_hashes.json content))`, which any `sha256sum` and JCS implementation can
   confirm.

In the repository rather than the package: [RESULT.md](RESULT.md) for the scientific write-up,
and [../../FINDINGS.md](../../FINDINGS.md) for how this experiment sits beside the other two.

## 6. What a verified package does and does not establish

**Does:** the files are the ones that were sealed; every document satisfies its schema; every
reference resolves inside the package and each claim result aggregates the results actually
recomputed; every quantity carries the unit it is read as; the accelerations and the Monte Carlo
were recomputed here and match; every residual and verdict was derived from those recomputed
numbers and agrees with what the package records.

**Does not:** authenticate anything. The root hash is **unsigned**, so anyone who can rewrite a
file can re-seal the manifest — verification establishes internal consistency and
reproducibility, not provenance. It does not show the physics is right, that the source paper is
wrong, or that any external reviewer has looked at this. The package ships no JSON Schemas, so
validation uses the installed FarSight schemas rather than copies travelling with the package.

## 7. If you want to try to break it

The regression suite is `tests/unit/test_pioneer_evidence_package.py`, and it is mostly attempts
to make a tampered package verify. Each one documents what was measured before it was closed. The
quickest honest test of the workflow is to edit a number in `metrics/results.json`, re-seal, and
watch which check objects — and then to do it properly, re-storing the addressed object and
re-rendering the report, and watch recomputation catch what the file manifest could not.

```bash
pip install ".[dev]"
FARSIGHT_REQUIRE_GIT=1 python -m pytest tests/unit -q
```
