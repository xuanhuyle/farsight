# K2 gate result — DSOC epistemic envelope

**Date:** 2026-08-28 · **Computed by:** [`k2_envelope.py`](k2_envelope.py) (stdlib only, deliberately
not the FarSight pipeline) · **Status:** gate **UNDECIDED** on free data; two cheap actions decide it

## The gate

| Threshold | Source | Value | Result |
|---|---|---|---|
| Envelope > 12 dB at 2.6 AU ⇒ demote DSOC | plan §21 K2 | **10.25 dB** | does not demote |
| Envelope ≤ 6 dB, else AT-5 is vacuous | plan §18 AT-5 | **10.25 dB** | **fails** |

The answer landed between the two thresholds, which is the least convenient place it could have
landed and the reason this memo exists rather than a one-line pass.

## What the number is

The width of the honest prediction band for received signal at Psyche's published range on
2024-06-24 (2.58 AU), using only free published parameters and **fitting nothing**. Geometry
contributes no width — range is known to far better than a dB — so the entire 10.25 dB comes
from terms nobody has published:

| Unknown | Interval | Width | Why it is unknown |
|---|---|---|---|
| Ground receiver optical train | [0.25, 0.60] | **3.80 dB** | Hale coudé path, ~1.8 nm filter, SNSPD coupling. No end-to-end figure in any free source. |
| Flight terminal EIRP | [0.42, 0.81] | **2.85 dB** | Aperture and average power are published; Strehl and transmit throughput are not. |
| Atmosphere (per pass) | [0.55, 0.93] | **2.28 dB** | 1550 nm is a good window, but per-pass conditions are unpublished for every pass. |
| Pointing | [0.85, 0.996] | 0.69 dB | Flight published only as "sub-microradian"; lab 0.16 µrad/axis. |
| Detector | [0.65, 0.75] | 0.62 dB | ~70% system DE is open-access; residual covers operating point. |

Terms combine by interval arithmetic — worst corner against worst corner. They are not random
variables, there is no distribution over them to convolve, and adding them in quadrature would
produce a narrower, more flattering band that means nothing. That is the laundering ADR-004
exists to prevent, and refusing it here is the whole point of the exercise.

**Consistency check, not validation:** the achieved 8.3 Mbps falls inside the implied
2.16–22.86 Mbps band. The model brackets reality. That is the weakest possible form of
agreement and is exactly why a 10 dB band cannot carry a claim.

## Why the gate is undecided

The bounds above are **my engineering judgement over published component classes, not
measurements** — pedigree `expert_judgment`. The verdict is sensitive to them in both
directions:

- Take the coudé train's lower bound to 0.15 instead of 0.25 — a view a real optical-comms
  engineer might well hold — and the total reaches **12.46 dB: DSOC demotes.**
- Tighten every term to the far end of plausible expert opinion, with no new data at all, and
  the total falls to **5.37 dB: AT-5 passes.**

So the gate currently turns on the judgement of someone (me) who is not qualified to bound the
two dominant terms. Reporting "10.25 dB, K2 passes" would be false precision of exactly the kind
this project exists to refuse.

One further caveat that pushes the same way: 10.25 dB is the envelope on **received signal**.
Converting to *supportable data rate* additionally requires the per-pass PPM order and code
rate, which are only partly published, so the rate envelope is **wider than this**. Treat 10.25
dB as a floor.

## What decides it, cheaply

The decomposition is the useful artifact, and it names its own remedy:

| Action | Buys | Resulting width |
|---|---|---|
| Pin the ground receiver train | 3.80 dB | 6.44 dB |
| Pin the atmosphere per pass | 2.28 dB | 7.96 dB |
| **Both** | **6.08 dB** | **4.16 dB — AT-5 passes** |

Two purchases, in the order they pay:

1. **The optical-comms expert review** (~$1–2k, already budgeted in plan §19 risk 2, called the
   highest-ROI spend in the plan). Two hours against this parameter table. It replaces my
   judgement on the two dominant terms with someone's who has built one, and it is also the
   review most likely to find a term I omitted entirely — an omitted term is a silently fitted
   zero, which is worse than a wide bound.
2. **SPIE 13355 papers** (~$300), particularly Alerstam et al. on the ground laser receivers'
   first year, which plausibly contains the train throughput, and the per-pass tables.

**Pre-registration protocol (plan §17):** this envelope is published *before* those purchases,
with its content hash, and is then scored against what they reveal. That sequencing is what
makes the eventual comparison circularity-proof, and it means this memo must not be revised
after the papers arrive — a superseding memo cites it instead.

## Recommendation

**Do not demote DSOC, and do not declare K2 passed.** Hold it open for the two actions above,
which fit inside week 2 and cost ~$1.5–2.3k against a decision that reshapes the flagship.

Two things follow regardless of how it resolves:

- **The DSN RF anchor matters more, not less.** It is ±1 dB with zero unknown parameters, and it
  is now the only benchmark that can validate the pipeline in a setting where any discrepancy is
  unambiguously a bug rather than an unknown. It should stay first in weeks 3–4.
- **AT-5's ≤6 dB threshold cannot be met on free data.** Either it is met by purchasing the two
  measurements, or the acceptance test needs re-deriving against what is actually knowable. It
  should not be quietly relaxed to whatever the envelope turns out to be — that is the
  tolerance-inflation failure the plan gives an allowed count of zero.

The honest framing for an external reader, and it is a genuinely good one: *the width itself is
the result.* A benchmark that says "this is 10 dB wide, 3.8 dB of it is one unpublished mirror
train, and here is the paper that would halve it" is a more useful artifact than a confident
prediction that quietly fitted the same term.
