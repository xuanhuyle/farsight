# Stage 1 — Voyager 2's 1996 DSS-43 link predictions, reproduced from what JPL printed

**Date:** 2026-09-10
**Status:** internally cross-checked; not externally expert-reviewed (ADR-030)

**Source:** R. Ludwig and J. Taylor, *Voyager Telecommunications*, DESCANSO Design and Performance
Summary Series, Article 4, JPL, March 2002:

- Tables 5-2 (S-band uplink carrier), 5-3 (X-band downlink carrier) and 5-4 (X-band 160 bps
  telemetry) predict Voyager 2 at DSS-43, the 70 m Canberra antenna, on 1996-01-01 00:00.
- Table 5-5 lists the predicted pass across 1996 days 029–030.

| Part | What | Verdict |
|---|---|---|
| A | the three link tables' arithmetic, from their printed rows | **not reproduced** — residuals ≤ 0.4 dB |
| B | the pass geometry, through the FarSight pipeline | **not reproduced** — residuals ≤ 0.023° |

Neither result is evidence that JPL's predictions or FarSight's geometry are wrong. Both show that
this published analysis cannot be rebuilt to its printed precision from what it prints. What
remains in each case is a convention the article never states.

---

## Part A — the link tables' arithmetic

**Script:** [`reproduce_voyager2_dct_1996.py`](reproduce_voyager2_dct_1996.py), standard library
only, deliberately not the FarSight pipeline.

### Verdict

**NOT REPRODUCED** under the rule fixed before the run: *a single declared convention must
reproduce every published dB total to its printed precision, 0.1 dB.* No declared convention does.

This is a result about the published tables' internal arithmetic, not about the accuracy of JPL's
predictions. Every discrepancy is 0.4 dB or smaller.

### How it was tested

- **Transcription, two independent ways, digit-for-digit agreement.**
  - Text extracted from JPL's PDF, with glyph coordinates used to fix which column each number
    sits in.
  - The Internet Archive's OCR of the same article.
  - A blank cell is carried as blank, never as zero.
- **Conventions declared before any result existed.**
  - Mean conventions: design-value sum; printed mean (blank → design); printed mean (blank → 0);
    uniform; triangular; JPL's per-row distribution types from Cheung, IPN 42-183 (2010),
    Table 2(b).
  - Variance conventions: printed; uniform; triangular; the JPL types with Gaussian tolerances read
    as ±3σ, and again as ±2σ.
- **A limit on the JPL-types convention.** Table 2(b) covers downlink parameters only. Table 2(a),
  for the uplink, was not read, so that convention is not evaluated on Table 5-2 at all, rather
  than guessed.

### Scorecard

| Mean convention | dB totals reproduced |
|---|---|
| design-value sum | **9 of 15** |
| printed mean, blank → design | 7 of 15 |
| printed mean, blank → 0 | 6 of 15 |
| triangular | 6 of 15 |
| uniform | 5 of 15 |
| JPL types (downlink tables only) | 2 of 10 |

### Findings

#### 1. The article's tables use different conventions

| Table | Convention that reproduces it | Totals matched | Worst residual |
|---|---|---|---|
| 5-2, uplink | sum of **printed means** | 5 of 5 | — |
| 5-3, downlink carrier | sum of **design values** | 5 of 6 | row 18: −0.16 dB |
| 5-4, telemetry | sum of **design values** | 3 of 4 | row 22: −0.06 dB |

Received power in Table 5-3 is exactly the design-value sum, −145.50 dBm. Summing the printed means
instead gives −145.78.

**Mixing a different convention per table matches 13 of 15 totals, with residuals up to 0.16 dB.
This per-table mix was chosen after seeing the output, so it is reported as an observation, not
scored as a pass.**

#### 2. Rows no declared shape explains

| Row | Printed | Why it does not reproduce |
|---|---|---|
| 5-3 row 8, DSS-43 X-band gain | 74.01, ±0.60 → mean 73.7, var 0.14 | symmetric tolerance, yet the mean is 0.31 dB below design; uniform variance would be 0.12 |
| 5-2 row 7, spacecraft S-band gain | 34.60, ±0.39 → mean 34.5 | symmetric tolerance, yet the mean is 0.1 dB below design; the variance does fit triangular |
| 5-3 row 2, antenna circuit loss | 0.00, fav +0.30, adv 0.00 → mean 0.0 | uniform gives +0.15 and triangular +0.10; the printed mean ignores the tolerance |
| 5-4 row 20, data/total power | −1.25, +0.05 −0.06 → mean −1.2 | sits on the rounding boundary; not treated as substantive |
| 5-2 rows 3 and 6; 5-3 rows 7 and 9 (pointing and polarization losses) | no mean or variance printed | the tables still sum over them |

#### 3. Variances follow the same split

- In Tables 5-3 and 5-4, summing the printed variances reproduces every total except row 17
  (0.190 against 0.20).
- In Table 5-2 it gives 0.150 against a printed 0.16. Adding a uniform variance for the blank
  polarization-loss row closes that gap. Also chosen after seeing the output — not scored.

#### 4. One JPL convention can be identified from the numbers

Downlink noise spectral density (5-3 row 10) reproduces its printed variance, 0.09, only when the
Gaussian tolerances are read as ±3σ; ±2σ gives 0.20. **That identifies a convention from the
printed value, which is an inference, not an independent reproduction.**

#### 5. The 1996 tables do not follow JPL's 2010 distribution assignments

- The JPL-types convention reproduces 2 of 10 downlink totals.
- Example: Table 2(b) lists the carrier-loop noise bandwidth as deterministic. The 1996 table
  gives it tolerances, and a triangular shape reproduces its printed mean and variance.
- A convention documented in 2010 cannot be assumed to govern a 1996 design control table.

#### 6. Physics checks on the inputs: 11 of 13 at printed precision

Checked:
- space loss from range and frequency
- range in AU
- noise spectral density from system temperature, including the tolerances
- system temperature as the sum of its components
- bit rate in dB
- data and carrier suppression at a 60° modulation index

Two misses:

- **X-band space loss:** computed −308.183 dB, printed −308.19 — **0.007 dB**.
  - *Frequency ruled out.* The article's own frequency table (page 24) gives Voyager 2's two-way
    X-band downlink as 8415.000 MHz, channel 14, which is what Table 5-3 prints.
  - *Light-time-corrected range ruled out in part B*, below. A range definition the article does
    not state remains untested.
- **Noise adverse tolerance** from +4.24 K: computed 0.7946 dB, printed 0.80 — on the rounding
  boundary.

---

## Part B — the pass geometry, through the FarSight pipeline

**Script:** [`reproduce_table_5_5_geometry.py`](reproduce_table_5_5_geometry.py). Unlike part A,
this runs the system under test — a RunSpec bundle through `run_geometry`, with channels read back
from disk — on the pinned Voyager 1996 kernels. All four are trust-on-first-use (DEV-16).

**Criteria fixed in the script's docstring before it first ran:**

- **Gate 1:** every Table 5-5 row printed at 45° or higher matches within 0.02°. Refraction is
  under 0.017° there and the table prints to 0.01°, so this holds whichever way JPL treated
  refraction.
- **Gate 2:** at 1996-01-01 00:00 UTC, elevation matches 58.01° within 0.02°, and range matches
  7.273e9 km within ±0.0005e9 km.
- **Time convention:** Table 5-5's times are read as UTC at DSS-43, with converged light time at
  that observer epoch.

**Transcription:** 37 of the 58 elevations agree digit for digit between JPL's PDF and the Internet
Archive's OCR. The OCR omits the continuation block, day 030 00:45 to 05:45, so those 21 rows have a
single source.

### Verdict

**NOT REPRODUCED.**

| Gate | Result |
|---|---|
| 1 — rows at ≥ 45° within 0.02° | **FAIL** — 26 of 31. The five misses are 0.020–0.023°. |
| 2 — 1996-01-01 elevation and range | PASS — elevation +0.016°, range +4.3×10⁵ km |

Three runs of the script produced bitwise-identical channel hashes.

### Reported, not gating

- **Close everywhere.** All 58 rows agree within 0.023°, with a mean difference of +0.001°.
- **Geometric, not apparent.** At the lowest rows, near 11°, the residuals are +0.016° rising and
  −0.014° setting. Refraction there would be about −0.08° if the table included it, so the residuals
  indicate geometric elevations.
- **Structured, not noise.** The residuals average +0.017° across the 29 rising rows and −0.015°
  across the 29 setting rows. A sign flip at the top of the pass is the signature of a time offset,
  not of an elevation bias or a station-position error.
- **The single-source rows** behave exactly like the two-source rows around them. There is no sign
  of a transcription error.
- **Space loss.** SPICE's light-time-corrected range, 7.27343e9 km, reproduces the printed S-band
  row (−296.182 → −296.18) but not the X-band row (−308.184 against −308.19). With frequency already
  ruled out in part A, this range is ruled out too. The 0.007 dB stays unexplained. A different
  range definition in the 1996 software is the remaining untested candidate.

### Post-hoc diagnostic — run after the verdict, and changes nothing

The script's `[POST-HOC]` section, printed after the verdict, fits a single least-squares time
shift of **+5.59 s**. It reduces the residuals from max 0.0227° / rms 0.0163°
to **max 0.0059° / rms 0.0028°** -- about the table's own printing precision, 0.005°. These are the
script's full-precision figures; a quick fit on the rounded printout had given +5.62 s and 0.0057°.

- **What it suggests:** the printed elevations describe instants about 5.6 s away from their times
  as read here (UTC at the station).
- **What it does not establish:** the cause. Untested candidates: a time-tagging convention in
  JPL's 1996 prediction software; Earth-orientation or station-coordinate differences between 1996
  and today's kernels; differences between the 1996 predicted trajectory and today's reconstruction.
  A trajectory offset large enough to mimic 5.6 s of Earth rotation would be about 3 million km at
  48.6 AU, which makes that candidate unlikely — not excluded.
- **Why it is not a pass:** the shift was fitted to the same residuals it removes. Accepting it
  would tune the answer to the question.

---

## What Stage 1 licenses

- **Can be said:** Voyager 2's published 1996 predictions cannot be reproduced to their printed
  precision from what the article prints. The link tables mix aggregation conventions. The pass
  table carries an apparent ~5.6 s time offset. Link residuals are ≤ 0.4 dB and geometry residuals
  ≤ 0.023°.
- **Cannot be said:**
  - that JPL's predictions were inaccurate — no measurement is involved in Stage 1
  - that the source contains errors — an unstated convention could explain every item
  - that FarSight's geometry is correct in any absolute sense — it agrees with a 1996 prediction
    to 0.023°, and the remaining difference has a pattern whose cause is unknown
- **For Stage 2:** both residual conventions enter as stated unknowns rather than silent choices —
  about 0.3 dB of aggregation ambiguity, and about 6 s of time-tag ambiguity. The time-tag ambiguity
  is negligible for received power: over 6 s the elevation changes by about 0.017°, which moves
  antenna gain by far less than 0.01 dB.
