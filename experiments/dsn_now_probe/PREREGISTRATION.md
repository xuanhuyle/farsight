# DSN Now feed probe — pre-registration

**Written 2026-09-10, before any logging run.** This file is committed before the first snapshot
of the run it governs, and that commit's hash is the pre-registration. Every threshold below was
fixed from published antenna gains and stated assumptions, not from logged data.

**Status:** internally cross-checked; not externally expert-reviewed (ADR-030). Allowances marked
**assumption** are not literature values.

## Question

Does the `power` attribute of `<downSignal>` in `https://eyes.nasa.gov/dsn/data/dsn.xml` respond to
receive-antenna aperture the way received signal power physically must?

- **Yes** → the field can serve as a *relative* answer key for Stage 2 of the first project.
- **No** → Stage 2 is not attempted against this feed, and the plan switches to candidate B.

## Known before this was written

From one snapshot on 2026-09-10 — not logged-run data:

- The feed states no unit, definition or calibration for `power`.
- Values seen were integers. Many sat on multiples of 10 (−110, −120, −140, −150, −160).
- Inactive signals carried −470 and −480, which look like sentinels.
- A second snapshot, run through the analyzer before this was committed: 5 eligible values, all
  integers and **all on multiples of 10**. Recorded here so it cannot later be presented as a
  discovery. It is not a verdict: one snapshot forms no pairing.
- `downlegRange` appears for some targets, rounded to three significant figures. `rtlt` read −1
  everywhere.

These observations shaped the test design. They are why a large, physically certain effect was
chosen rather than a subtle one.

## The test: 70 m versus 34 m for the same spacecraft and band

At fixed spacecraft EIRP and range, received power scales with receive-antenna gain. Published
X-band gains at the elevation of peak gain, referenced to the feedhorn aperture:

| Antenna | Source | Gain |
|---|---|---|
| 70 m DSS-14 | 810-005 Module 101 Rev E, Table 2, 8420 MHz | 74.55 (X-only) / 74.35 (S/X) dBi, ±0.1 |
| 70 m DSS-43 | same | 74.63 / 74.36 dBi, ±0.1 |
| 70 m DSS-63 | same | 74.66 / 74.19 dBi, ±0.1 |
| 34 m BWG | 810-005 Module 104 Rev L, Table 7, 8425 MHz | 68.32 (X-only) / 68.27 (S/X) dBi, +0.1 −0.2 |

The feed does not say which feed configuration is in use, so both are carried as intervals:

- 70 m: [74.09, 74.76] dBi
- 34 m BWG: [68.07, 68.42] dBi
- **Expected 70 m − 34 m difference: [5.67, 6.69] dB.** The 5 MHz frequency difference contributes
  0.005 dB and is ignored.

Allowances added to that interval:

| Allowance | Size | Basis |
|---|---|---|
| Feed rounding: each value appears to be an integer, ±0.5 each | ±1.0 dB | observed |
| Elevation-dependent gain of two antennas, both at ≥ 20° | ±1.0 dB | **assumption** — Appendix A of Modules 101 and 104 gives the coefficients, but the equations were not evaluated |
| Pointing and polarization loss differences | ±0.3 dB | **assumption** |

**Acceptance band for one pairing difference: [3.3, 9.0] dB** — the interval widened by the
allowances, rounded outward.

What the band discriminates:

| If `power` is… | A pairing difference is about… | Result |
|---|---|---|
| a received-power measurement | 6 dB | inside |
| a constant placeholder | 0 dB | outside |
| a category in 10 dB steps | 0 or 10 dB | outside |

**What passing does not show:** absolute calibration. A field offset from true received power by a
constant still passes. Stage 2 must carry that offset as an unknown, never assume it is zero.

## Data selection (fixed)

- **Eligible signal:** `downSignal` with `active="true"`, `signalType="data"`, `band="X"`, and a
  numeric `power`. Its dish has `isArray="false"`, `isMSPA="false"` and `elevationAngle` ≥ 20.
- **Antennas.** 70 m: DSS14, DSS43, DSS63. 34 m BWG: DSS25, DSS26, DSS34, DSS35, DSS36, DSS54,
  DSS55. Excluded because their X-band gain was not in the tables read: DSS24 (Module 104
  Table 6), the 34 m HEF dishes DSS15, DSS45 and DSS65 (Module 103), and DSS23, DSS53 and DSS56.
- **Counting.** An archived snapshot counts once per distinct feed `timestamp`, so a feed that did
  not update between two fetches is not double-counted.
- **Pairing.** Same spacecraft code, same UTC date, one eligible 70 m dish and one eligible 34 m
  BWG dish, each with at least 3 eligible snapshots that date.
  - Per dish, take the median of its eligible `power` values. The pairing difference is
    median(70 m) − median(34 m).
  - Where several dishes of one class qualify, use the one with the most eligible snapshots; on a
    tie, the lowest DSS number.

## Decision rule (fixed)

- **Window:** 7 days from the first archived snapshot, by fetch time.
- **PASS:** at least 3 pairings on at least 2 UTC dates, and at least 80% of pairing differences
  (rounded up to a whole pairing) inside [3.3, 9.0] dB.
- **FAIL:** at least 3 pairings on at least 2 UTC dates, and fewer than that inside the band.
- **INCONCLUSIVE:** fewer than 3 pairings, or pairings on fewer than 2 UTC dates. The window is
  extended once, to 14 days. If still inconclusive, the plan treats it as FAIL, because a feed that
  cannot produce the comparison in two weeks cannot serve as an answer key in practice.
- **Consequence:** PASS → Stage 2, with a constant power offset carried as an unknown.
  FAIL → candidate B.

## Reported, not gating

- Of eligible values: the fraction that are integers, and the fraction on multiples of 10.
- Sentinels (`power` ≤ −300), split by `active`.
- Spearman correlation of elevation against `power` within single-dish, single-date passes.
- Median arrayed minus single-dish power, where both occur for one spacecraft on one date.

## Changes after the first snapshot

Any edit to this file after the first archived snapshot of the governed run is a deviation. It is
recorded here with date and reason, and the decision under the original text is reported
alongside.

*(none)*
