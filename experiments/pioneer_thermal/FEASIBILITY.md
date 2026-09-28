# Pioneer anomaly — can the published thermal analysis be rebuilt from what the papers state?

**Date:** 2026-09-28
**Status:** internally cross-checked; not externally expert-reviewed (ADR-030)

This is the question flagged as unverified when the Pioneer anomaly was chosen as the fallback
first project. The DSN Now feed probe failed its pre-registered test
([../dsn_now_probe/RESULT.md](../dsn_now_probe/RESULT.md)), so under that pre-registration the
fallback is now the project, and this is its first step.

## Answer: yes, for the point-source model — with three limits stated below

The target is **Francisco, Bertolami, Gil & Páramos, *Modelling the reflective thermal contribution
to the acceleration of the Pioneer spacecraft*, Physics Letters B 711 (2012) 337–346**
([arXiv:1103.5222](https://arxiv.org/abs/1103.5222)), with its method paper
([arXiv:0807.0041](https://arxiv.org/abs/0807.0041), Phys. Rev. D 78 103001, 2008).

Every input the model needs is printed in those two papers. Nothing requires spacecraft design
documentation, telemetry files, or a thermal finite-element solver.

## Inventory of inputs

| Input | Where | Value |
|---|---|---|
| Geometry | 2012 Fig. 1 | nine dimensions in mm, as selectable text: 2500, 600, 343, ⌀200, ⌀2768, 480, 190, 660, 120° |
| Point-source positions and normals | 2012 Table 2 | explicit, in metres, for front wall, six lateral-wall sources, both RTG ends, six back-wall sources |
| Spacecraft mass | 2012 §3 | 230 kg (259 kg at launch less 36 kg hydrazine) |
| Power, late mission (t = 26 yr, 1998) | 2012 §4.1 | total 2100 W; equipment 56 W; RTG thermal 2024 W; radio beam 20 W |
| Power, launch | 2012 §3, 2008 §V | RTG thermal 2580 W; ²³⁸Pu half-life 87.74 yr; electrical 120 W compartment + 20 W radio (2008 gives 160 W electrical at launch) |
| Per-scenario power split | 2012 Eqs. (18), (19), Table 3 | five scenarios, every surface's watts given |
| Reflection coefficients | 2012 Table 3, §4.2 | per scenario; Monte Carlo uses k_d,ant ~ U[0.6, 0.8], k_s,ant ~ U[0, 0.2], constrained k_d + k_s = 0.8 |
| Monte Carlo distributions | 2012 §4.2 | W_RTGb ~ Normal(143.86 W, σ = 25%); W_front ~ Normal(40 W, σ = 7.5 W); remaining surfaces conserve the 56 W |

**Published intermediate results, usable as checkpoints rather than only as a final answer** — this
is what makes the reproduction diagnosable when it disagrees:

- front wall force = (2/3)·W_front/c
- lateral-wall shadow on the dish: z-component −0.0738·(W_lat/c)
- specular antenna term: 0.0089·k_s,ant·(W_lat/c)
- 16.8–17.3% of side-wall power converts to sunward thrust along the spin axis

## The answer to check against

| Quantity | Published value |
|---|---|
| Scenario accelerations (Table 3), 10⁻¹⁰ m/s² | 2.27, 4.43, 5.71, 5.69, 6.71 |
| Monte Carlo at t = 26 yr | **(5.8 ± 1.3) × 10⁻¹⁰ m/s²**, 95% |
| Monte Carlo at t = 8 yr | (8.9 ± 2) × 10⁻¹⁰ m/s², 95% |
| Fraction of the anomaly explained | 44% to 96% |
| The anomaly itself | **(8.74 ± 1.33) × 10⁻¹⁰ m/s²** — Anderson et al., Phys. Rev. D 65 082004 (2002) |

Independently, Turyshev et al., Phys. Rev. Lett. 108 241101 (2012), report no statistically
significant difference between a finite-element thermal model driven by flight telemetry and the
navigation-derived acceleration.

## Three limits, stated rather than discovered later

1. **One input is given, not derived.** W_RTGb = 143.86 W appears in Eq. (18) without a formula. It
   is reconstructible from the stated geometry — one cylinder end over the RTG's total emitting
   area, times 2024 W, gives about 144.5 W, which is 0.4% from the published figure. Closing that
   0.4% is part of the reproduction, and the discrepancy may turn out to be a convention the paper
   does not print, exactly as happened with Voyager's design control tables.
2. **The time-series of electrical power exists only as figures** — 2012 Fig. 7, and Toth &
   Turyshev (arXiv:0901.4597) Fig. 1, whose caption says the values come from telemetry. The
   continuous curve cannot be rebuilt without digitising a plot or obtaining telemetry files. The
   three static epochs the paper analyses (t = 8, 26, and one more) are reproducible from stated
   numbers, so the reproduction targets those and does not attempt the curve.
3. **The finite-element analysis is out of reach and is not a target.** Turyshev et al. built theirs
   from spacecraft design documentation and flight telemetry with a thermal solver. It stands as an
   independent corroboration to compare conclusions against, never as something to rebuild here.

## Why this is worth doing, in one line each

- **The answer is known and published**, so the reproduction can be wrong — the property the DSN Now
  feed turned out not to have.
- **The dominant uncertainties are epistemic**: how power divides between surfaces, and how the dish
  reflects. The paper handles them by bounding scenarios and a parametric sweep, which is the same
  shape as FarSight's interval treatment and can be compared against it directly.
- **It is the case where missing knowledge was once mistaken for new physics**, which is this
  project's thesis stated as history rather than as argument.

## Proposed next step

Pre-register the reproduction before writing the model, in the same form used for the Voyager work
and the feed probe:

- **Gate 1:** the five scenario accelerations in Table 3, each to its printed precision
  (0.01 × 10⁻¹⁰ m/s²).
- **Gate 2:** the Monte Carlo result at t = 26 yr, (5.8 ± 1.3) × 10⁻¹⁰ m/s², to the printed 0.1.
- **Reported, not gating:** t = 8 yr; the fraction-of-anomaly range against the published 44–96%;
  and the same inputs carried as intervals rather than distributions, which is the comparison
  FarSight exists to make and the paper does not perform.
