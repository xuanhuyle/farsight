# Pioneer thermal reproduction — pre-registration

**Written 2026-09-28, before any model code exists.** Committed before the first run; that commit's
hash is the pre-registration. Every target below is a number already printed in the source papers.

**Status:** internally cross-checked; not externally expert-reviewed (ADR-030).

## Question

Can the published point-source thermal-recoil analysis of the Pioneer spacecraft be rebuilt from the
inputs its own papers state?

**Target paper.** F. Francisco, O. Bertolami, P. J. S. Gil, J. Páramos, *Modelling the reflective
thermal contribution to the acceleration of the Pioneer spacecraft*, Physics Letters B 711 (2012)
337–346, [arXiv:1103.5222](https://arxiv.org/abs/1103.5222). Method paper: Phys. Rev. D 78 103001
(2008), [arXiv:0807.0041](https://arxiv.org/abs/0807.0041). Feasibility inventory:
[FEASIBILITY.md](FEASIBILITY.md).

## What is being reproduced, and at what depth

The paper reduces its Lambertian-source and Phong-reflection integrals to **closed-form force
expressions with numeric coefficients** (Eqs. 10–15):

    F11 = (W_lat  / c) ( 0.0738 + 0.0537 k_d,ant + 0.0089 k_s,ant)
    F21 = (W_RTGb / c) ( 0.0283 + 0.0478 k_d,ant + 0.0502 k_s,ant)
    F22 = (W_RTGb / c) (-0.0016 + 0.0013 k_s,lat)
    F3  = (W_back / c) (-2/3 + 0.5872 + 0.5040 k_d,ant + 0.3479 k_s,ant)
    F4  = (2/3) (W_front / c)
    a_th = (F11 + F21 + F22 + F3 + F4) / m_Pio

**So the gates below test the paper's arithmetic and its Monte Carlo — not its geometry.** The
coefficients are inputs here, taken as printed. Re-deriving them by integrating over the stated
geometry is a different and much larger exercise; it is **out of scope for the gates**, and if any
part of it is attempted it is reported separately and labelled.

This is the same depth as the Voyager design-control-table work
([../voyager_dct/VOYAGER_DCT_RESULT.md](../voyager_dct/VOYAGER_DCT_RESULT.md)), which is worth
saying plainly: that exercise looked shallow and found two undocumented conventions in one article.

## Inputs, fixed here so that tuning them later is visible

Taken from the papers, and nothing else. Not fitted, not adjusted.

| Input | Value |
|---|---|
| Spacecraft mass | 230 kg |
| RTG thermal power, t = 26 yr | 2024 W |
| Equipment power, t = 26 yr | 56 W (total 2100 W, radio beam 20 W) |
| Force coefficients | Eqs. (10)–(14), as printed above |
| Scenario power splits | 2012 Eqs. (18), (19) and Table 3 |
| Monte Carlo: RTG base power | Normal(143.86 W, σ = 25% of the mean) |
| Monte Carlo: front-wall power | Normal(40 W, σ = 7.5 W); other compartment surfaces conserve 56 W |
| Monte Carlo: antenna reflection | k_d,ant ~ Uniform[0.6, 0.8], k_s,ant ~ Uniform[0, 0.2], constrained k_d + k_s = 0.8 |
| Iterations | 10⁴, as published |

**W_RTGb = 143.86 W is used as published** for the gates. The paper gives it without a formula. The
separate attempt to reconstruct it from the stated geometry is reported, never substituted.

**An inconsistency inside the source, recorded before it can be discovered later.** The prose gives
the ²³⁸Pu half-life as 87.74 years; Eq. (16) uses 87.72. **Eq. (16) governs**, because it is the
equation the paper computes with. The difference is about 0.005% at t = 26 years, and is reported.

**Randomness.** One fixed seed, recorded in the result, so the run repeats. Monte Carlo sampling
error at 10⁴ draws is near 0.01 × 10⁻¹⁰ m/s², far inside every tolerance below.

## Gates

**Gate 1 — the five scenarios.** Each of the five accelerations in 2012 Table 3 reproduced to its
printed precision, ±0.005 × 10⁻¹⁰ m/s²:

| Scenario | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| a_th (10⁻¹⁰ m/s²) | 2.27 | 4.43 | 5.71 | 5.69 | 6.71 |

**Gate 2 — the Monte Carlo at t = 26 years.** Central value 5.8 and 95% half-width 1.3, each to the
printed precision, ±0.05 × 10⁻¹⁰ m/s².

**Both gates must pass for the reproduction to count as reproduced.** A miss is reported together
with the input or step responsible, and is never closed by adjusting an input.

## Reported, not gating

- **t = 8 years:** published (8.9 ± 2) × 10⁻¹⁰ m/s². Reported because its input powers are stated
  less completely than the t = 26 case.
- **Fraction of the anomaly**, against the published 44–96%, using
  a_Pio = (8.74 ± 1.33) × 10⁻¹⁰ m/s² (Anderson et al., Phys. Rev. D 65 082004, 2002).
- **W_RTGb reconstructed from the stated geometry**, against the published 143.86 W.
- **The power model**, Eqs. (16) and (17), against the stated launch and late-mission figures.
- **The same unknowns carried as intervals**, combined worst-corner rather than sampled: the
  paper's own ranges for the reflection coefficients, and the scenario bounds for the power split.
  This is the comparison FarSight exists to make and the paper does not perform. It is reported
  beside the Monte Carlo result, never in place of it.

## What a result here can and cannot say

- **Can:** whether this published analysis is rebuildable from its own printed inputs and
  coefficients, and where it is not.
- **Cannot:** whether the paper's geometry integrals are right — they are inputs here, not outputs.
- **Cannot:** whether the thermal explanation of the Pioneer anomaly is correct. That rests on work
  not reproduced here, including the finite-element analysis of Turyshev et al. (Phys. Rev. Lett.
  108 241101, 2012), which needs design documentation and flight telemetry.
- **Cannot:** anything about the anomaly's measured value, which is an input here, taken from
  Anderson et al. (2002).

## Changes after the first run

Any edit to this file after the first recorded run is a deviation, recorded here with date and
reason, with the decision under the original text reported alongside.

*(none)*
