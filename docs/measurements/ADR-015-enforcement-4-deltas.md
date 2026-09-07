# ADR-015 Enforcement 4 — the three convention deltas, measured

**Measured:** 2026-09-07 · **Status:** measurement, not a review sign-off · **NOT externally
expert-reviewed**

ADR-015 marks three figures **UNVERIFIED — confirm at implementation time** and its Enforcement
item 4 makes measuring them a week-1 task "rather than a sentence in this record". This file is
that measurement. It is written here rather than into ADR-015 because that record is Accepted and
uneditable, and because ADR-015 itself says such figures belong "in a hash-pinned artifact or a
measured CI log, not in ADR prose".

## Configuration

| | |
|---|---|
| Observer | `PSYC_DSOC_PALOMAR` (−255195), DSOC downlink receiver |
| Target | `-255` (`PSYC`), the Psyche **spacecraft** |
| Topocentric frame | `PSYC_DSOC_PALOMAR_TOPO`, from `psyche_fk_v10.tf` |
| Kernels | the nine pinned in `kernels/pinned_kernels.json`, all publisher-checksum verified |
| Epochs | eight samples, 2023-12-20 to 2024-03-01, including a full day at 3-hour spacing |
| Range at these epochs | 61.5–62.6 million km (≈0.41 AU) |
| Toolkit | spiceypy 6.0.3 / CSPICE N0067, Python 3.12, Windows 11 |

Reproduce with `scripts/measure_adr015_deltas.py` (kernels must be in the local cache).

## 1. Inertial frame realization — `ITRF93` vs `IAU_EARTH`

**ADR-015 said:** *"The two frames differ by an amount that is large compared with AT-11's 0.01
degree elevation tolerance."*

**Measured: 0.28–0.29 arcsec of sky separation, stable across all eight epochs.**
Worst |Δelevation| = 0.27 arcsec = **0.000074 deg**. AT-11's tolerance is 0.01 deg = 36 arcsec.

**The record's expectation does not hold for this configuration.** The difference is ~125× SMALLER
than the tolerance, not larger.

Why, so the result is checkable rather than merely reported: the two frames differ by polar motion
and UT1 (≈0.3 arcsec of Earth-fixed rotation), plus a station position difference of metres. For a
*direction* to a target at 0.41 AU the position difference is negligible, so what survives is the
frame rotation — and 0.3 arcsec is what polar motion is.

**What this does NOT license.** It is one observer, one target distance, one month. The frame
choice would matter far more for a near-Earth target, where the station position difference is not
negligible against the range, and for any quantity that is a *position in an Earth-fixed frame*
rather than a direction to something far away. ADR-015's requirement that the frame be declared
per request stands on its own reasoning; this measurement narrows one figure, it does not retire
the rule.

## 2. Aberration correction — `NONE` vs `CN` on a range

**ADR-015 said:** *"the resulting difference in range is orders of magnitude larger than AT-11's
10 km tolerance."*

**Measured at 2024-01-15T04:00:00 UTC: 735.248 km.**

| correction | range (km) |
|---|---|
| `NONE` (geometric) | 61,715,616.463 |
| `CN` (converged Newtonian, reception) | 61,714,881.214 |

**Confirmed, and by a wide margin: 73× the 10 km tolerance.** This is the single strongest
justification in the set for ADR-015 decision 6 — a defaulted aberration correction would move a
range by seventy tolerances while every hash, every schema check and every unit check stayed
green. It is exactly the silent-wrong-number class, and it is why the field is mandatory, hashed,
and has no default anywhere in the code path.

## 3. Stellar aberration — `CN` vs `CN+S` on a direction

**Measured at 2024-01-15T04:00:00 UTC: 18.38 arcsec = 0.0051 deg.**

| correction | elevation (deg) |
|---|---|
| `CN` | 58.294814 |
| `CN+S` | 58.289709 |

About **half** AT-11's 0.01 deg tolerance — smaller than the tolerance but the same order of
magnitude, so it is not negligible and cannot be waved away. This is the measured basis for
ADR-015's consistency rule: a `direction` request without a `+S` member is a *geometric* direction,
materially different from an apparent one, and the schema requires a stated reason for choosing it.

It also confirms the other half of the rule. Stellar aberration displaces a direction and does not
change a range — which is why a `+S` member on a `range` or `light_time` request is refused at
construction rather than quietly accepted.

## A fourth finding, not asked for by Enforcement 4

`ADR-015` decision 5 also marks UNVERIFIED: *"Whether the NAIF PDS4 station kernel set ships an FK
defining a topocentric frame for each of the DSOC ground stations."*

**It does.** `psyche_fk_v10.tf` defines `PSYC_DSOC_PALOMAR_TOPO`, `PSYC_DSOC_OCTL_TOPO`,
`PSYC_DSOC_HELMOS_TOPO` and `PSYC_DSOC_KRYONERI_TOPO`. So the contingency ADR-015 describes —
"If it does not, FarSight authors a text FK, which is a new kernel attributed to FarSight" — is
**not needed**, and no FarSight-authored FK should be written. One less kernel we would have had
to attribute, maintain and defend.

## A naming hazard found while doing this

`PSYCHE` resolves through SPICE's built-in body table to **2000016 — the asteroid (16) Psyche**.
The **spacecraft** is `-255` / `PSYC`. A `GeometryRequest` written with the obvious spelling
`target="PSYCHE"` computes geometry to a body about 0.4 AU from the one intended, and every hash,
schema and unit check passes. The station body names are `PSYC_DSOC_PALOMAR` and `PSYC_DSOC_OCTL`,
not `PALOMAR` / `OCTL`.

This is not a defect in any record — it is a property of the SPICE name space — but it is the
kind of thing that is only ever found by running it, and it belongs in the review checklist beside
TIME-1.
