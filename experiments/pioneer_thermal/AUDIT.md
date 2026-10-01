# Auditing the Pioneer evidence package

For an independent reviewer. The goal is that you can build the package, verify it yourself, and
form your own view of what it does and does not establish — without taking anything here on
trust, and without installing a simulation engine.

**Expect the reproduction to fail its own criteria.** That is the result, not a fault. Two of the
pre-registered gates are missed, the package records `not_reproduced`, and it verifies cleanly
while saying so. A workflow that could only package successes would be worth nothing.

---

## 0. The implementation under audit is pinned

```
454e37b6fce309a4d85312def09cefef51f63dec
```

Every command below checks that commit out explicitly, by design. Two reasons:

1. **The default branch is the wrong place.** A plain `git clone` lands on `main`, where the
   evidence-package builder does not exist yet — this work lives on the
   `evidence-workflow-pioneer` branch, under review in PR #1. Following clone-and-go would leave
   you looking for files that are not there.
2. **An audit should assess a fixed implementation.** The branch will keep moving; your findings
   should attach to something that cannot.

**This document is not the thing being audited.** It is maintained on the branch and its own
commit is necessarily *newer* than the pinned implementation — a documentation change cannot
predate the code it documents. The documentation commit SHA is recorded in PR #1. If the two
disagree about anything, the pinned commit is the implementation; this file is a description of
it, and a disagreement is a defect in the description worth reporting.

---

## 1. Windows PowerShell

Copy-ready. Nothing is activated, so an execution-policy restriction on `Activate.ps1` cannot
get in the way — the virtual environment's interpreter is invoked by path throughout.

```powershell
git clone https://github.com/xuanhuyle/farsight
cd farsight
git checkout --detach 454e37b6fce309a4d85312def09cefef51f63dec

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .

.\.venv\Scripts\python.exe experiments\pioneer_thermal\build_evidence_package.py --out .\pioneer_pkg
.\.venv\Scripts\python.exe experiments\pioneer_thermal\build_evidence_package.py --out .\pioneer_cf --counterfactual w_rtgb_geometric

.\.venv\Scripts\python.exe experiments\pioneer_thermal\verify_evidence_package.py .\pioneer_pkg
Write-Host "baseline exit code: $LASTEXITCODE"
.\.venv\Scripts\python.exe experiments\pioneer_thermal\verify_evidence_package.py .\pioneer_cf
Write-Host "counterfactual exit code: $LASTEXITCODE"
```

If `py -3.12` is not available, substitute the full path to a Python 3.12 interpreter.

## 2. POSIX shells (bash, zsh)

```bash
git clone https://github.com/xuanhuyle/farsight
cd farsight
git checkout --detach 454e37b6fce309a4d85312def09cefef51f63dec

python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install .

./.venv/bin/python experiments/pioneer_thermal/build_evidence_package.py --out ./pioneer_pkg
./.venv/bin/python experiments/pioneer_thermal/build_evidence_package.py --out ./pioneer_cf --counterfactual w_rtgb_geometric

./.venv/bin/python experiments/pioneer_thermal/verify_evidence_package.py ./pioneer_pkg
echo "baseline exit code: $?"
./.venv/bin/python experiments/pioneer_thermal/verify_evidence_package.py ./pioneer_cf
echo "counterfactual exit code: $?"
```

**Which of these was rehearsed.** The PowerShell block above was executed end to end on Windows
while preparing this document — fresh clone, pinned checkout, fresh virtual environment, base
install, both builds, both verifications. The POSIX block was **not** run on a POSIX host; it is
the same sequence written for the standard `.venv/bin/python` layout. If it misbehaves, that is
worth reporting as a documentation defect — it is exactly the sort of thing this handoff is
meant to find.

## 3. Python version, and why no extras

The project pins **Python 3.12** (`requires-python = ">=3.12,<3.13"`).

`pip install .` installs the base package only. **Do not add extras.** `spiceypy`, Basilisk,
GMAT, pandas and matplotlib are deliberately absent: verification must work without any
simulation engine, and that property is the commercially decisive one in this design. Installing
them would prove less, not more. A test enforces it by making those names unimportable and
verifying anyway.

---

## 4. The expected outcome

**Verification exits `0` for both packages, while the scientific verdict stays
`not_reproduced`.** Those two facts are not in tension, and holding them apart is the whole
point: the first is about the package's internal consistency, the second is about the physics.

| | |
|---|---|
| Scenarios 1–4 | reproduce to printed precision: residuals +0.0021, +0.0041, +0.0015, −0.0019 |
| Scenario 5 (upper bound) | **misses** — rebuilt 6.9166 against a published 6.71, residual +0.2066 |
| Monte Carlo at t = 26 yr | **misses** — rebuilt ≈5.70 ± 1.19 against a published 5.8 ± 1.3 |
| Overall | `not_reproduced` — gate 1 fail, gate 2 fail |

Units are 10⁻¹⁰ m/s². Monte Carlo figures depend on the iteration count; the default build uses
10⁴ iterations under seed 20260928.

Verification exit codes, if something does fail: `2` integrity, `3` schema, reference or
cross-file inconsistency, `4` recomputation mismatch, `5` the package contradicts its own
numbers, `6` unreadable.

The build prints a root hash that differs between runs, because the build timestamp is recorded
honestly. Pass `--built-at 2026-10-01T12:00:00+00:00` to both builds if you want byte-identical
rebuilds.

---

## 5. What to inspect, in this order

1. **`PARTIAL_FORMAT.md`** (inside the package) — what of ADR-007 is implemented and what is
   not. Read this before concluding that something is missing.
2. **`report/summary.md`** — the generated report. Do not trust it on its own;
   [REPORT_FIELD_INVENTORY.md](REPORT_FIELD_INVENTORY.md) traces every displayed value back to
   the record that governs it, and says how the verifier establishes they agree.
3. **`experiment/PREREGISTRATION.md`** — the criteria, fixed before the model existed. Its
   commit `934505e` predates the first result commit `d8f8ba7`; `git log` will confirm that
   independently of anything asserted here.
4. **`registers/assumptions.json`** — what the reproduction assumes and what breaks if each
   assumption is wrong. This is the part a reader cannot derive from the numbers.
5. **`metrics/results.json`** and **`experiment/scenario_inputs.json`** — the numbers and the
   inputs that produced them, as decimal strings with units. No JSON floats anywhere.
6. **`code/reproduce_thermal_acceleration.py`** — the authoritative calculation, hashed into the
   package. The builder imports it rather than restating any formula.
7. **`hashes/file_hashes.json`** — reproduce the root hash yourself:
   `root_hash = sha256(JCS(file_hashes.json content))`, which any `sha256sum` plus a JCS
   implementation can confirm.

In the repository rather than the package: [RESULT.md](RESULT.md) for the scientific write-up,
and [../../FINDINGS.md](../../FINDINGS.md) for how this experiment sits beside the other two.

---

## 6. Three different questions, deliberately kept apart

A reader who collapses these will over-read the result in one direction or the other.

| Question | Answered by | Not answered by |
|---|---|---|
| Is the package internally consistent and reproducible? | the verifier's four checks | CI being green |
| Is the physical model valid? | **nothing here** — it needs a domain reviewer | recomputation succeeding |
| Is this workflow useful to someone assessing research? | your judgement, section 7 | either of the above |

**Neither green CI nor successful recomputation establishes that the physical model is valid.**
Recomputation shows that the recorded results follow from the recorded inputs and code. It is
also not authentication: the root hash is unsigned, so anyone able to rewrite a file can re-seal
the manifest.

---

## 7. Reviewer worksheet

Please record your answers in whatever form suits you — a comment on PR #1 is fine. Rough notes
are more useful than polished ones, and a blunt "I could not follow this" is the most useful
answer of all.

**A. Did the documented process work, unassisted?**
- Which platform and shell did you use? Python version?
- Did any step fail, require a workaround, or need knowledge not in this document?
- Where did you have to guess what was meant?

**B. Can you trace each gate's verdict to its criteria, inputs and assumptions?**
- Gate 1 (the five scenarios): from the printed verdict back to the tolerance, the published
  targets, the inputs and the assumptions that govern them — ☐ yes ☐ partly ☐ no
- Gate 2 (the Monte Carlo): the same, including the seed and sampling settings —
  ☐ yes ☐ partly ☐ no
- Where did the trail break, or require reading the source rather than the package?

**C. How do you explain the two discrepancies?**

Please separate what is demonstrated from what is conjecture.

- Scenario 5: rebuilt 6.9166 against a published 6.71.
- The Monte Carlo centre: rebuilt ≈5.70 against a published 5.8.
- Demonstrated by this package: …
- Your hypotheses, and your confidence in each: …
- Anything in the package you think is simply wrong: …

**D. What additional evidence would distinguish the competing explanations?**
- What would you want to see that is not here?
- Is any of it obtainable without the original authors?

**E. Is this package easier to assess than the paper alone?**
- Did it save you effort, cost you effort, or neither?
- What essential information is missing?
- What would you drop as noise?

---

## 8. The next decision

The point of this review is to decide **whether this evidence workflow is useful enough to apply
to a more substantial mission problem, and which of its limitations would matter there.** It is
not to choose that next problem — no candidate is being proposed here, and none should be
implemented on the strength of this one bounded demonstration.

Known limitations to weigh, each stated at greater length in the package's `PARTIAL_FORMAT.md`:

- **No signing.** Verification establishes internal consistency and reproducibility, never
  provenance.
- **No bundled JSON Schemas**, so validation runs against the installed FarSight schemas rather
  than copies travelling with the package. This is the largest gap against ADR-007.
- **No `replay`**, no run channels, no metric registry; the claim tier is recorded as `C`
  because nothing here runs in the reference container.
- `Source.artifact_refs` is empty — the sources are publications, not bytes, so there is no
  input closure to check them against.
- The field inventory and the unit table are **bounded to this experiment**. They are not a
  general mechanism, and a different experiment would need its own.

---

## 9. If you want to try to break it

Optional, and genuinely welcome. The regression suite is mostly attempts to make a tampered
package verify; each test records what was measured before it was closed.

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install ".[dev]"
$env:FARSIGHT_REQUIRE_GIT = "1"
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

POSIX:

```bash
./.venv/bin/python -m pip install ".[dev]"
FARSIGHT_REQUIRE_GIT=1 ./.venv/bin/python -m pytest tests/unit -q
```

The quickest honest probe is to edit a number in `metrics/results.json`, re-seal, and see which
check objects — then to do it properly, re-storing the addressed object and re-rendering the
report, and watch recomputation catch what the file manifest could not.
