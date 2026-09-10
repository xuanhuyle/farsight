# DSN Now feed probe — interim looks

Every look at logged data before the decision date is recorded here: when, what was read, what was
seen. **No interim look changes a threshold, selection rule or decision rule in
[PREREGISTRATION.md](PREREGISTRATION.md).** If a look ever tempts such a change, that temptation is
recorded here, and the change itself would still be a deviation under that document's own rule.

**Status:** internally cross-checked; not externally expert-reviewed (ADR-030).

---

## 2026-09-10 — after the first logging job

**Read:** the archive from GitHub Actions run 34468587614, fetched 10:56 to 16:21 UTC — 66 attempts,
none failed, 66 distinct feed timestamps.

**Analyzer:** INCONCLUSIVE, 0 pairings. No spacecraft appeared on both an eligible 70 m dish and an
eligible 34 m BWG dish on the same date, so the pre-registered comparison had no opportunity to run.
Voyager 1 and 2 did not appear in this job.

**Reported, not gating:**

- **Resolution.** 342 eligible values: 100% integers, **98% on multiples of 10**.
- **Held constant while elevation changed.**

  | Spacecraft | Dish | Samples | Values | Distinct elevations |
  |---|---|---|---|---|
  | EMM | DSS26 | 46 | all −120 | 45 |
  | Juno | DSS25 | 57 | 56 × −130, 1 × −140 | 55 |
  | STEREO-A | DSS24 | 50 | all −120 | 48 |

- **Different links, identical values.** MRO, EMM and TGO at Mars, and STEREO-A near 1 AU, all read
  −120.
- **Order still broadly follows distance.** Mars orbiters −120 (Mars Odyssey −130), Juno −130,
  New Horizons on the 70 m DSS43 −150 to −170.
- **The only values off multiples of 10.** KPLO, a lunar orbiter, on DSS23: −93 to −95. So finer
  steps exist for at least one signal.
- **Sentinels.** 164 of 310 inactive signals read ≤ −300; no active signal did.
- **Elevation against power.** Median Spearman −0.12, over the 4 passes with any variation at all.

**Reading, offered as an interpretation of one job and not as a verdict:** for most deep-space
signals the field behaves like a coarse, roughly distance-ordered category rather than a dB-accurate
received power. If that holds, the pre-registered test cannot pass. A 10 dB step makes a pairing
difference of 0 or 10 dB, and both lie outside [3.3, 9.0].

**Changed:** nothing. Logging continues, and the decision is taken on the pre-registered date, by
the pre-registered rule.
