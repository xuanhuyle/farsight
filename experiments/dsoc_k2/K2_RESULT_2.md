# K2 gate result, revision 2 — verdict on Deep-Review bounds

**Date:** 2026-08-29 · **Supersedes** [`K2_RESULT.md`](K2_RESULT.md) (2026-08-28), which is
pre-registered and remains untouched; this memo cites it and is itself committed **before**
any data purchase, keeping the pre-registration chain intact.
**Status:** `research-reviewed; internally cross-checked; independently reconstructed; NOT
externally expert-reviewed` (ADR-030).
**Computed by:** [`k2_envelope_v2.py`](k2_envelope_v2.py) · full sourcing in
[`K2_DEEP_REVIEW.md`](K2_DEEP_REVIEW.md).

## Verdict

| Threshold | Source | v1 (judgment bounds) | v2 (Deep-Review bounds) | Result |
|---|---|---|---|---|
| Envelope > 12 dB ⇒ demote DSOC | plan §21 K2 | 10.25 dB — not triggered | **12.76 dB — TRIGGERED** | **DSOC demotes to secondary; DSN 810-005 becomes flagship** |
| Envelope ≤ 6 dB, else AT-5 vacuous | plan §18 AT-5 | fails | fails by 6.8 dB | unchanged: unreachable on free data |

The original memo held the gate open because its bounds were one person's unaided judgment.
The Deep Review replaced every bound with source-anchored intervals — and the envelope
**widened**, from 10.25 to 12.76 dB, crossing the demote threshold the founder pre-committed
before any number existed. Applying the pre-set rule rather than relitigating it is this
project's own tolerance-inflation discipline (allowed loosening count: zero), so:

**DSOC is demoted to secondary benchmark. The DSN 810-005 RF benchmark is the flagship for
weeks 3–4.**

Two honesty notes on the verdict itself. First, the crossing is not deep: the most charitable
defensible reading (operating point pinned at its center, filter established as installed) is
11.92 dB — under the line — but both charitable assumptions require data we do not hold, and
ADR-030's rule is that missing evidence widens. Second, the width is a floor: converting the
received-signal envelope to a *supportable-rate* envelope adds the per-pass PPM order and code
rate, only partly published.

## Why it widened: the three findings that matter more than the verdict

1. **The flight laser ran at half power for the entire first year of operations — including
   the K2 epoch.** Stated plainly in JPL's own open-access detector paper; corroborated by
   JPL's October 2024 release. The v1 model assumed the full 4 W: a silently fitted
   factor-of-two, found not by an expert but by reading the primary literature the way an
   expert would. New term `tx_operating_point` [0.50, 0.56].
2. **The receive aperture is obstructed.** The Hale telescope's prime-focus cage blocks
   ~12.5% of the 5.1 m aperture; v1 used the bare geometric area. Now a deterministic level
   factor 0.87 — ESA's own LLCD ground-station budget books exactly this row, which is how the
   omission was caught.
3. **The epoch range was a rounded press figure.** Horizons gives 2.663–2.677 AU for
   2024-06-24, not 2.58: a −0.30 dB level error that SPICE-based referent definition would
   have caught later anyway, fixed now.

Together: the band's *center* drops ~3.7 dB and its width grows 2.5 dB. Any future scoring
against the referent must use the v2 structure.

## Demotion is reversible, by one named purchase

The pin-decomposition names the price of reversal:

| Purchase pins | Envelope becomes | Crosses |
|---|---|---|
| receiver train | 8.61 dB | back under demote threshold |
| + atmosphere per pass | 5.37 dB | **under the AT-5 usability threshold** |
| + operating point | **4.87 dB** | comfortably usable |

All three are plausibly answered by the **~$300 SPIE 13355 batch** (Alerstam 133550N — ground
receivers, first year; Wright 133550L — laser transmitters operational performance; Andrews
133550M — flight terminal), which now attacks four unknowns at once. That purchase is the
founder's decision. If made: score the *v2* pre-registered envelope against what the papers
reveal, publish the comparison either way, and re-run this gate on the pinned bounds. If the
papers pin what they plausibly pin, DSOC returns as a strong secondary or co-flagship with a
~5 dB honest envelope — which is a *better* demo than the v1 plan, because the narrowing
itself is then a documented, purchased, non-circular event.

## Consequences for the plan

- **Weeks 3–4 structure unchanged; labels swap.** The geometry pipeline is shared. DSN
  810-005 + DESCANSO becomes the flagship comparison (±1 dB class, zero unknown parameters —
  every discrepancy is a bug, which is what a pipeline shakedown needs). The DSOC link chain
  is still built: it is the only benchmark that exercises the epistemic machinery
  (`Unknown`, sweeps, the collapse lane), and that machinery is the product.
- **AT-5 is re-scoped to the flagship it now describes**: the decided pass/fail lives on the
  DSN benchmark; the DSOC acceptance test becomes envelope-integrity (counterfactual
  falsifiability, unknowns ledger completeness) rather than a width threshold it cannot meet
  on free data — unless the purchase is made, in which case the 6 dB test returns.
- **The kill-criteria chain is intact**: plan §21's standing rule ("if the DSN benchmark also
  cannot produce a decided pass/fail, the falsification thesis is dead") is now load-bearing,
  exactly as the original K2 memo anticipated when it called DSN "the only benchmark that can
  validate the pipeline in a setting where any discrepancy is unambiguously a bug."
- **The ten expert questions** are on the ledger (`EXPERT_REVIEW_BACKLOG.md` entry 1) and the
  eventual human review of this parameter table remains a deferred gate; nothing in this memo
  is externally validated, and the demo language must say so (ADR-030 lint enforces it).
