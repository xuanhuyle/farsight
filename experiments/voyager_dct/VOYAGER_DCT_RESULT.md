# Stage 1, part A — Voyager 2's 1996 link tables, reproduced from their own inputs

**Date:** 2026-09-10
**Script:** [`reproduce_voyager2_dct_1996.py`](reproduce_voyager2_dct_1996.py), standard library
only, deliberately not the FarSight pipeline
**Status:** internally cross-checked; not externally expert-reviewed (ADR-030)

**Source:** R. Ludwig and J. Taylor, *Voyager Telecommunications*, DESCANSO Design and Performance
Summary Series, Article 4, JPL, March 2002. Tables 5-2 (S-band uplink carrier), 5-3 (X-band
downlink carrier) and 5-4 (X-band 160 bps telemetry) predict Voyager 2 at DSS-43, the 70 m
Canberra antenna, on 1996-01-01 00:00.

## Verdict

**NOT REPRODUCED** under the rule fixed before the run: *a single declared convention must
reproduce every published dB total to its printed precision, 0.1 dB.* No declared convention does.

This is a result about the published tables' internal arithmetic. It is not evidence that JPL's
predictions were wrong, and every discrepancy found is 0.4 dB or smaller.

## How it was tested

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

## Scorecard

| Mean convention | dB totals reproduced |
|---|---|
| design-value sum | **9 of 15** |
| printed mean, blank → design | 7 of 15 |
| printed mean, blank → 0 | 6 of 15 |
| triangular | 6 of 15 |
| uniform | 5 of 15 |
| JPL types (downlink tables only) | 2 of 10 |

## Findings

### 1. The article's tables use different conventions

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

### 2. Rows no declared shape explains

| Row | Printed | Why it does not reproduce |
|---|---|---|
| 5-3 row 8, DSS-43 X-band gain | 74.01, ±0.60 → mean 73.7, var 0.14 | symmetric tolerance, yet the mean is 0.31 dB below design; uniform variance would be 0.12 |
| 5-2 row 7, spacecraft S-band gain | 34.60, ±0.39 → mean 34.5 | symmetric tolerance, yet the mean is 0.1 dB below design; the variance does fit triangular |
| 5-3 row 2, antenna circuit loss | 0.00, fav +0.30, adv 0.00 → mean 0.0 | uniform gives +0.15 and triangular +0.10; the printed mean ignores the tolerance |
| 5-4 row 20, data/total power | −1.25, +0.05 −0.06 → mean −1.2 | sits on the rounding boundary; not treated as substantive |
| 5-2 rows 3 and 6; 5-3 rows 7 and 9 (pointing and polarization losses) | no mean or variance printed | the tables still sum over them |

### 3. Variances follow the same split

- In Tables 5-3 and 5-4, summing the printed variances reproduces every total except row 17
  (0.190 against 0.20).
- In Table 5-2 it gives 0.150 against a printed 0.16. Adding a uniform variance for the blank
  polarization-loss row closes that gap. Also chosen after seeing the output — not scored.

### 4. One JPL convention can be identified from the numbers

Downlink noise spectral density (5-3 row 10) reproduces its printed variance, 0.09, only when the
Gaussian tolerances are read as ±3σ; ±2σ gives 0.20. **That identifies a convention from the
printed value, which is an inference, not an independent reproduction.**

### 5. The 1996 tables do not follow JPL's 2010 distribution assignments

- The JPL-types convention reproduces 2 of 10 downlink totals.
- Example: Table 2(b) lists the carrier-loop noise bandwidth as deterministic. The 1996 table
  gives it tolerances, and a triangular shape reproduces its printed mean and variance.
- A convention documented in 2010 cannot be assumed to govern a 1996 design control table.

### 6. Physics checks on the inputs: 11 of 13 at printed precision

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
  - *Range remains possible.* A range of at least 7.2746e9 km would reproduce both the S-band and
    X-band rows; the printed range is 7.273e9 km.
  - *Not decided here.* Part B computes the 1996-01-01 range independently from SPICE.
- **Noise adverse tolerance** from +4.24 K: computed 0.7946 dB, printed 0.80 — on the rounding
  boundary.

## What this licenses

- **Can be said:** Voyager 2's published 1996 design control tables do not reproduce from their own
  printed rows under any single stated convention. The article mixes conventions between its uplink
  and downlink tables. All residuals are 0.4 dB or less.
- **Cannot be said:**
  - that JPL's predictions were inaccurate — no measurement is involved
  - that the source rows contain errors — an unprinted internal convention, or unrounded
    intermediate values, could explain each discrepancy, and the article is not detailed enough to
    tell
- **Consequence for Stage 2:** the 1996 inputs are usable at about the 0.3 dB level, far inside any
  realistic link uncertainty budget. The choice of aggregation convention is not silent — it enters
  Stage 2 as a stated, separately reported unknown.

## Still to do in Stage 1

- **Part B:** reproduce Table 5-5's pass profile — DSS-43 elevation from 11.66° to 84.40° and back,
  1996 day 029 17:45 to day 030 08:00 — through the FarSight geometry pipeline. Also compute the
  range, to settle the 0.007 dB space-loss question.
