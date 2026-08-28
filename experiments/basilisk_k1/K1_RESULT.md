# K1 gate result — Basilisk determinism and mid-run intervention

**Date:** 2026-08-28 · **Verdict: PASS.** Basilisk stays in the MVP.
**Reproduce:** `pip install bsk && python k1_spike.py` (exit 0 = pass)

| | |
|---|---|
| Basilisk | 2.11.1, wheel `bsk-2.11.1-cp39-abi3-win_amd64` (66 MB) |
| Python | 3.12.10 · NumPy 2.4.6 |
| Platform | Windows 11 (10.0.22621) |
| Elapsed | well inside the 2-day timebox |

## What was asked, and what came back

The gate (plan §21 K1) is whether a seeded Basilisk scenario reruns bitwise-identically. The
spike answers that plus the adjacent questions several ADRs had already committed to in prose
*before* anyone ran the engine — which is the point of running it now rather than in week 5.

| | Question | ADR at risk | Result |
|---|---|---|---|
| Q0 | Is the noise real at all? | — | **63.8 m RMS** — not vacuous |
| Q1 | Two identical seeded runs → bitwise identical? | ADR-002, ADR-006 | identical |
| Q2 | Does per-module `RNGSeed` actually control the draws? | ADR-005 | seeds 1234 vs 9999 differ |
| Q3a | Does *segmenting* a run change its result? | ADR-003 | identical to continuous |
| Q3b | Is a zero-magnitude mutation byte-transparent? | ADR-010, AT-10 | identical |
| Q3c | Does a real mutation actually bite? | ADR-003 | changed |
| Q4 | Deterministic **across processes**? | ADR-002 | identical |

Q0 and Q4 exist because the first version of this spike was capable of passing for the wrong
reasons. Q0 guards the case where the sensor emits no noise, under which every determinism
check below it passes trivially. Q4 guards the more serious one: Q1 compares two runs in a
single process, whereas ADR-002 mandates a *fresh process per run*, so the same-process result
is not the production condition. The child process runs under a different `PYTHONHASHSEED` and
produces the same hashes.

Hashes are computed with ADR-011's rule — a header over the raw C-order `<f8` payload — rather
than over whatever NumPy happens to emit, so what the spike measured is what the platform will
later claim.

## What this buys, decision by decision

**Tier-A replay survives contact with the engine.** ADR-006's Tier A is bitwise equality in a
pinned environment, and it was written before we knew whether Basilisk could deliver it. It
can, on this platform, across processes.

**The seed discipline works as designed.** ADR-005 has FarSight own all sampling and hand
Basilisk per-module `RNGSeed` integers, having noted that Basilisk exposes no global seed. The
attribute exists, it bites, and different seeds produce different draws — so the seed-map design
is implementable rather than aspirational.

**`native` fault lowering is real, and it is byte-transparent.** ADR-003's four lowering modes
put mid-run attribute mutation first, and ADR-010's paired-counterfactual causal claim depends
entirely on a zero-magnitude fault being byte-transparent (AT-10). Q3a and Q3b are the two
halves of that: segmenting a run does not perturb it, and rebinding an attribute to its existing
value changes nothing. Both hold. That means "the metric moved because of activation X" can be
arithmetic rather than inference, which is the strongest causal claim the product makes.

## What it does not establish

- **Windows only.** Every result is from one platform. ADR-006's Tier B — agreement across
  platforms within stated tolerances — is untested, and the Linux leg is where it would fail.
  Worth a CI job once the Basilisk adapter exists.
- **One trivial scenario.** Two-body dynamics with one noisy sensor over 200 s. Nothing here
  exercises variable-step integrators, reaction wheels, or the dynamics/FSW process split, which
  is where reproducibility usually gets harder rather than easier.
- **`simpleNav`, not the module we will actually use.** It was chosen because it needs only the
  spacecraft state wired in. The first attempt used `coarseSunSensor`, which refused to
  initialize without its sun and state input messages — an early, cheap reminder that Basilisk
  module wiring is a real cost the adapter will have to carry.
- **Nothing about the adapter.** This is the engine behaving, not FarSight driving it. ADR-002's
  cost row (spawn plus scientific-stack import per run, self-flagged UNVERIFIED and scored 0.60)
  is still unmeasured, and the `spawn-floor-spike` remains outstanding.

## One incidental finding worth keeping

The first working version emitted `BSK_WARNING: GaussMarkov bounds set tighter than 3σ -
distribution will be truncated` on every step. `walkBounds` at 100 m against a ~64 m sigma was
clipping the distribution. Every determinism check still passed — truncated noise is exactly as
deterministic as untruncated noise — so the gate verdict never depended on it. But the spike
would have been exercising a bound-limited regime while claiming to exercise a Gauss-Markov one,
and the warning is the only thing that said so. Bounds are now 500 m.

The general lesson for the adapter: **Basilisk reports this class of problem on stderr and
continues.** A worker that discards engine stderr would silently lose it. ADR-012 owns the
logging mechanism and the worker-to-parent payload; engine diagnostics should be captured there
rather than dropped, and this is the concrete case that argues for it.

## Recommendation

Keep Basilisk in the MVP at the scope ADR-004/§17 already set: a minimal adapter in weeks 5–6,
covering a two-body scenario against SPICE `prop2b`, one mid-run fault injection, and the
per-module seed map. The gate that mattered is passed, and the two mechanisms the fault model
depends on — segment-boundary mutation and zero-magnitude transparency — are demonstrated rather
than assumed.

Next spike, unchanged in priority: GMAT R2025a subprocess round-trip, which ADR-014 still marks
UNVERIFIED on its entry-point filename, and the `spawn-floor-spike` measurement that ADR-002's
lowest-confidence row is waiting on.
