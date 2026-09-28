# DSN Now feed probe — result

**Decided 2026-09-28** under [PREREGISTRATION.md](PREREGISTRATION.md), committed 2026-09-10 before
the first snapshot and unchanged since.

**Status:** internally cross-checked; not externally expert-reviewed (ADR-030).

## Verdict: FAIL

**0 of 8 pairings** fell inside the pre-registered band of [3.3, 9.0] dB.

Decided on the **7-day window** (2026-09-10T10:56Z → 2026-09-17T10:56Z). The single permitted
extension to 14 days was **not used and not needed**: 8 pairings across 4 UTC dates clears the
"3 pairings on 2 dates" threshold, so the result is conclusive rather than inconclusive.

| Date | Spacecraft | 70 m | 34 m BWG | Difference |
|---|---|---|---|---|
| 2026-09-11 | EURC | DSS43 −140 (23) | DSS36 −150 (72) | **+10.0 dB** |
| 2026-09-11 | JNO | DSS43 −130 (23) | DSS34 −140 (25) | **+10.0 dB** |
| 2026-09-12 | JNO | DSS43 −130 (33) | DSS25 −130 (106) | **+0.0 dB** |
| 2026-09-16 | JNO | DSS43 −130 (45) | DSS25 −130 (52) | **+0.0 dB** |
| 2026-09-12 | NHPC | DSS43 −150 (123) | DSS26 −160 (62) | **+10.0 dB** |
| 2026-09-15 | PSYC | DSS43 −110 (8) | DSS36 −120 (24) | **+10.0 dB** |
| 2026-09-16 | PSYC | DSS43 −120 (18) | DSS34 −120 (21) | **+0.0 dB** |
| 2026-09-12 | VGR2 | DSS43 −160 (26) | DSS34 −170 (102) | **+10.0 dB** |

Every difference is exactly 0 or 10 dB. The 5.67–6.69 dB an aperture difference must produce never
appears, in any pairing, for any spacecraft.

**This outcome was named in advance.** [INTERIM_LOOKS.md](INTERIM_LOOKS.md), written 2026-09-10
after the first job, recorded that 98% of eligible values sat on multiples of 10 and stated: *"If
that holds, the pre-registered test cannot pass. A 10 dB step makes a pairing difference of 0 or
10 dB, and both lie outside [3.3, 9.0]."* It held. The verdict still comes from running the rule on
the full window, not from that expectation.

## Why the field cannot serve as an answer key

`power` is quantised to 10 dB across the whole deep-space range. Every distinct eligible value at or
below −100 dBm in the 7-day window is a multiple of 10:

    -290  -280  -210  -170  -160  -150  -140  -130  -120  -110  -100

The only finer values are **stronger** than −100 dBm — −98, −95, −94, −93, −91, −89, −88 — which
come from near-Earth and lunar spacecraft. So the feed does carry sub-decibel resolution, but only
where a deep-space link budget has no use for it.

Supporting observations, all reported-not-gating under the pre-registration:

- 6,652 eligible values: **100% integers, 97% on multiples of 10**.
- Values hold still while the antenna moves: median Spearman correlation of elevation against power
  **−0.13** over the 98 passes that showed any variation at all.
- Sentinels: 3,765 of 7,503 inactive signals read ≤ −300; 1 active signal did.
- The ordering still follows distance — Mars −120, Jupiter −130, Voyager 2 −160/−170 — so the field
  is not meaningless. It is a coarse category, not a measurement.

## Data quality

| | |
|---|---|
| Attempts logged | 4,290 |
| Snapshots archived | 4,285 |
| Failed fetches | 5, all `Connection reset by peer` (2026-09-11, 2026-09-16) |
| Distinct feed updates in the 7-day window | 1,777 |
| Gaps over 15 minutes | 34, largest 234 minutes, 48.2 hours in total |
| Collection span | 2026-09-10T10:56Z → 2026-09-27T03:28Z |

The gaps are mostly the deliberate ~30-minute spacing between 5.5-hour jobs, plus scheduled runs
GitHub delayed. They are visible because failed attempts are logged rather than skipped; none falls
in a place that could manufacture or destroy a pairing, since a pairing needs only 3 eligible
snapshots per dish per date and the qualifying dishes had 8 to 123.

## What this licenses

- **Can be said:** NASA's public DSN Now feed reports `power` in 10 dB steps for deep-space links.
  It cannot answer a question posed at the 1 dB level, so it cannot serve as the answer key for
  Stage 2 of the first project.
- **Cannot be said:** that the field is wrong, arbitrary, or badly made. It tracks distance in the
  right direction and is evidently fit for the display it was built for. What was tested is whether
  it could carry a decibel-level comparison. It cannot.
- **Not established:** what the quantisation actually is — a display rounding, a stored category, or
  a coarse detector reading. Nothing here distinguishes those.

## Consequence

Per the pre-registration: **FAIL → candidate B.** Stage 2 is not attempted against this feed. The
first project becomes the Pioneer anomaly thermal-recoil reproduction, where the answer is published
and the inputs are free.

Stage 1 stands as completed work either way: see
[VOYAGER_DCT_RESULT.md](../voyager_dct/VOYAGER_DCT_RESULT.md).

## Logging stopped

`.github/workflows/dsn-now-probe.yml` is deleted in the same commit as this memo, and its guard test
with it. Logging ran 2026-09-10 to 2026-09-27: 70 scheduled runs, 65 of which archived data. The
last 5 failed deliberately — the workflow carried a hard stop of 2026-09-26 that exits nonzero past
that date, so a logger left running after its question was answered would nag rather than quietly
keep polling NASA. It did exactly that, and this memo is the answer it was nagging for.

## Evidence kept

- `evidence/merged_index.jsonl` — every attempt, archived or failed, with each snapshot's sha256.
  4,290 lines, 1,184,877 bytes,
  sha256 `09da923b075a3e48c10a7a93d8c1aba9f7bbe15f5fbaef6b285c8d895e840b76`.
- `evidence/verdict_7day.txt` — the analyzer's output, verbatim.
- The 4,285 raw snapshots stay in GitHub Actions artifacts and **expire from 2026-12-09**. They are
  not committed: 5.3 MB of XML whose content is already fixed by the digests in the index. A reader
  who has an archived snapshot can check it against the index; a reader who does not cannot
  re-collect it, because the feed is live. That trade is recorded here rather than assumed.
