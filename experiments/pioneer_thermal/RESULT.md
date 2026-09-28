# Pioneer thermal reproduction — result

**Decided 2026-09-28** under [PREREGISTRATION.md](PREREGISTRATION.md), committed in `934505e`
before `reproduce_thermal_acceleration.py` existed and unchanged since.

**Status:** internally cross-checked; not externally expert-reviewed (ADR-030).

## Verdict: NOT REPRODUCED

Both gates missed. The misses are narrow and localised, and neither was closed by adjusting an
input.

| | Gate | Result |
|---|---|---|
| 1 | five scenario accelerations, ±0.005 | **FAIL** — four match, Scenario 5 misses by +0.207 |
| 2 | Monte Carlo at t = 26 yr, ±0.05 | **FAIL** — centre low by 0.096, half-width low by 0.113 |

Saying what that does *not* mean, since the headline invites the wrong reading: nothing here
suggests the paper's physics is wrong. Four of five scenarios come out to four significant figures
from the paper's own equations, and the two epochs it documents least completely come out too. What
failed is the reproduction's own pre-registered standard, which was "every printed number, to its
printed precision".

## Gate 1 — the five scenarios of Table 3

Units of 10⁻¹⁰ m/s². Computed from Eqs. (10)–(15) with the Table 3 row as printed.

| # | Scenario | Published | Rebuilt | Residual | |
|---|---|---|---|---|---|
| 1 | lower bound, uniform temperature | 2.27 | 2.2721 | +0.0021 | match |
| 2 | higher emission from the louvers | 4.43 | 4.4341 | +0.0041 | match |
| 3 | diffusive reflection in the antenna | 5.71 | 5.7115 | +0.0015 | match |
| 4 | diffusive and specular reflection | 5.69 | 5.6881 | −0.0019 | match |
| 5 | **upper bound** | **6.71** | **6.9166** | **+0.2066** | **MISS** |

Scenarios 1–4 agree to better than half a unit in the last printed digit. Scenario 5 is 3.1% high.

**No stated input accounts for it.** For the published 6.71, a single input would have to be:

| | Would have to be | The paper prints |
|---|---|---|
| m_Pio | 237.08 kg | 230 kg |
| W_RTGb | 136.47 W | 158.24 W |
| W_front | 53.86 W | 56 W |

None is a quantity that appears anywhere in either paper, and none is adopted.

**Other readings tried** (`--alternatives`, all in `evidence/run_seed20260928.txt`):

| Reading of Scenario 5 | Result | vs 6.71 |
|---|---|---|
| as printed | 6.9166 | +0.2066 |
| without the 10% RTG bump, W_RTGb = 143.86 | 6.7801 | +0.0701 |
| k_s,lat = 0 | 6.9047 | +0.1947 |
| **k_d,ant = 0.6, Scenario 4's value** | **6.6972** | **−0.0128** |
| k_d,ant = 0.6 with k_s,ant = 0.2 | 6.9276 | +0.2176 |

The closest is k_d,ant = 0.6, which lands 0.013 away — still outside the gate, and **contradicted by
the paper's own text**, which says of Scenario 5: "Maintaining k_d,ant = 0.8 as in Scenario 3".
Table 3 prints 0.8 in that row as well. So it is a hypothesis about how the number was produced, not
a resolution, and it is recorded as such.

## Gate 2 — the Monte Carlo at t = 26 years

10⁴ iterations, seed 20260928, Scenario 4 means, W_RTGb normal at 25%, W_front normal at 7.5 W with
the rest of the 56 W conserved, k_d,ant uniform on [0.6, 0.8] under k_d + k_s = 0.8.

| | Published | Rebuilt | Residual |
|---|---|---|---|
| central value | 5.8 | 5.7044 | −0.0956 |
| 95% half-width, 1.96σ | 1.3 | 1.1875 | −0.1125 |
| 95% half-width, 2.5–97.5 percentile | 1.3 | 1.1876 | −0.1124 |

The pre-registration named "95% half-width" without fixing which estimator. Both were computed and
they agree to 0.0001, so the ambiguity does not touch the verdict.

**The centre sits where the model says it should, and the published value does not.** The paper
takes Scenario 4 as the Monte Carlo's reference, and Scenario 4 is 5.69. Sampling around it moves
the mean to 5.70. The published 5.8 is *above* its own reference scenario, which sampling symmetric
distributions around that scenario cannot produce. Supporting this from the paper's own numbers: its
fitted time evolution, Eq. (23), gives 5.73 at t = 26 — 0.03 from the rebuild and 0.07 from its own
stated static value.

Setting W_RTGb's mean to Scenario 5's 158.24 W instead of the stated 143.86 W gives 5.841 ± 1.225,
close to the published pair. Section 4.2 states 143.86, so this is not adopted either; it is
recorded because it is the only tried reading that lands near 5.8.

## Three things the rebuild found

**1. W_RTGb — the one input given without a formula — is exactly one fourteenth of the RTG thermal
power.** For the stated cylinder (diameter 200 mm from Fig. 1; length 600 mm, fixed by the two
source positions at x = 2.5 m and x = 3.1 m in Table 2), the inward-facing base is
0.0714286 = 1/14 of an RTG's emitting area. That gives **144.57 W** against the published 143.86 W,
0.49% apart. Inverting it, the published 143.86 W implies **W_RTG = 2014 W**, where section 4.1
states 2024 W. The reconstruction is exact in form; the 10 W is unexplained.

**2. "44% to 96% of the anomaly" needs the anomaly's own uncertainty swung in.** The model interval
alone, against the central (8.74 ± 1.33) × 10⁻¹⁰ m/s², gives 51% to 79%. Dividing the low end by
10.07 and the high end by 7.41 — the anomaly's bounds pushed the opposite way at each end — gives
**45% to 93%**, against the published 44% to 96%. The paper does not say it does this. It is the
same shape of undocumented convention found in the Voyager design control tables
([../voyager_dct/VOYAGER_DCT_RESULT.md](../voyager_dct/VOYAGER_DCT_RESULT.md)).

**3. The paper carries two plutonium half-lives, and it does not matter.** Section 3.4's prose says
87.74 years; Eq. (16) uses 87.72. Eq. (16) governs here, as pre-registered. The two differ by 0.005%
at t = 26 years — far below every tolerance in this exercise. Recorded because it was noticed, not
because it signifies anything.

## Reported, not gating

- **The power model reproduces the stated epoch to 0.04%.** Eqs. (16) and (17) at t = 26 give
  W_tot 2100.9 W, W_equip 56.6 W, W_RTG 2024.2 W, against the stated 2100, 56 and 2024 W.
- **The two other epochs reproduce**, using inputs scaled from t = 26 because the paper does not
  print their splits: **8.94 ± 1.84** at t = 8 against a published 8.9 ± 2, and **7.15 ± 1.47** at
  t = 17 against 7.1 ± 1.6. This is weaker evidence than it looks — the scaling rule is mine, not
  the paper's — but it is the rule stated in the script, and it was not tuned to hit these numbers.
- **The same unknowns carried as intervals** rather than distributions, combined at the worst
  corner: **[3.967, 7.409]**, half-width 1.721, against the Monte Carlo's [4.499, 6.874], half-width
  1.188. **The interval treatment is 45% wider.** This is FarSight's comparison and the paper does
  not perform it; see below for what it does and does not license.

## What the interval number means, and what it does not

The distributions here are not measured. Section 4.2 assigns a 25% spread to W_RTGb "to account for
unanticipated anisotropies" — a stated judgement, not a sampled population — and W_front's normal is
chosen so that 2σ lands below a physical ceiling. Where a distribution's shape is a judgement,
interval arithmetic reports the judgement's range instead of converting it into a probability. The
45% widening is the price of not making that conversion.

What it does **not** show is that the paper's number is too narrow in any absolute sense. Both
ranges are conditional on the same unexamined assumption: that the point-source model with these
coefficients is the right model. Nothing in this exercise tests that.

## What this licenses

- **Can be said:** four of the five published scenario accelerations, and the published power model,
  rebuild from the papers' own printed inputs and coefficients. The fifth, the upper bound, does not:
  its own row gives 6.92, not the printed 6.71. The published t = 26 Monte Carlo centre, 5.8, is
  above the scenario it is centred on, and the rebuild gives 5.70.
- **Can be said:** W_RTGb, the only input given without a formula, is recoverable as W_RTG/14 from
  the stated geometry, to 0.49%.
- **Cannot be said:** that the paper's geometry integrals are right or wrong. Its coefficients are
  inputs here, exactly as the pre-registration stated before the run.
- **Cannot be said:** anything about whether thermal recoil explains the Pioneer anomaly. That rests
  on work not reproduced here, including Turyshev et al., Phys. Rev. Lett. 108 241101 (2012), built
  from design documentation and flight telemetry.
- **Cannot be said:** that these two discrepancies are errors in the published paper. They are
  discrepancies between the paper's printed numbers and a rebuild from its printed inputs. A
  transcription slip into a table, a value changed between runs, and a mistake in this rebuild all
  produce the same evidence. What rules the third out is that the same code reproduces the other
  four scenarios, the power model, and both other epochs — which is an argument, not a proof.

**Not established:** why Scenario 5 and the Monte Carlo centre differ. Two readings land close
(k_d,ant = 0.6 for the scenario, W_RTGb = 158.24 W for the Monte Carlo), and each is contradicted by
the text that states the other value. No reading tried reproduces both.

## How to repeat this

```
python experiments/pioneer_thermal/reproduce_thermal_acceleration.py --alternatives
```

Exit code 1 is the verdict: 0 would mean both gates passed. The seed is 20260928 and is printed in
the output; the run is deterministic under it. Ten tests in
[../../tests/unit/test_pioneer_thermal.py](../../tests/unit/test_pioneer_thermal.py) hold the gate
numbers in the code to the numbers in the pre-registration, pin every rebuilt value, and check that
the model refuses to report a verdict on a table that does not add up or a run that sampled nothing.

## Evidence kept

- `evidence/run_seed20260928.txt` — the run above, verbatim, 3,338 bytes,
  sha256 `cffa8a0ea1ea3460ba17aeb8fca3286b8351f9e7d4ffa97d1c49161a436a5bf7`.
- Inputs are in the papers, both open access: [arXiv:1103.5222](https://arxiv.org/abs/1103.5222)
  and [arXiv:0807.0041](https://arxiv.org/abs/0807.0041). Nothing was downloaded into this
  repository, and no input is held anywhere but in the script, where each is commented with the
  equation or table it came from.

## Deviations from the pre-registration

None. One clarification, recorded rather than silently resolved: the pre-registration wrote "95%
half-width" without naming an estimator, so both the 1.96σ and the 2.5–97.5 percentile readings are
computed and reported. They agree to 0.0001, so the verdict does not depend on the choice.
