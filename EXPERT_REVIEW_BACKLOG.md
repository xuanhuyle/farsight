# Expert Review Backlog

Mandated by [ADR-030](docs/adr/ADR-030-deep-review-substitution.md). No reliable external
domain-expert access exists in the current phase; every topic below would materially benefit
from eventual human review, and this ledger is what prevents that gap from becoming forgotten
technical debt. Entries close only on an actual external review — never on more of our own
research. Confidence levels are evidence-referenced per ADR-030 decision 3.

Status vocabulary used throughout: `research-reviewed`, `internally cross-checked`,
`literature-supported`, `independently reconstructed`, `not externally expert-reviewed`.

---

## 1. DSOC link-budget parameter table (K2 envelope bounds)

**Topic:** The six-term epistemic envelope for predicting DSOC received signal
(atmosphere, receiver optical train, flight-terminal transmit efficiency, pointing, detector,
transmit operating point).

**Expertise eventually required:** Deep-space optical communications; free-space laser-comm
link engineering; JPL DSOC project insight or access to unpublished operational records.

**Current state:** Research-reviewed and independently reconstructed
(`experiments/dsoc_k2/K2_DEEP_REVIEW.md`, 2026-08-29): every bound moved from unaided
engineering judgement onto cited primary sources; three silently-fitted terms found and
corrected (half-power transmitter operating point, receive-aperture obscuration, epoch range);
missing-term audit run against the ESA OGS LLCD and JPL DOT budgets. Not externally
expert-reviewed.

**Current confidence:** Detector HIGH; pointing MEDIUM; flight-terminal EIRP MEDIUM-LOW;
atmosphere and receiver train LOW (the two dominant terms rest on model transfer and design
allocations, with the key quantities unpublished in free sources).

**Critical questions (verbatim hand-over from the Deep Review):**
1. Was the 1.8 nm GLROA bandpass filter installed for the 2024-06-24 pass (and generally for
   >2 AU passes), and what is its measured peak transmission?
2. What is the measured aperture-to-cryostat-window throughput of the Hale + GLROA receive
   chain at 1550 nm, and what fraction of in-band light is picked off to acquisition/tracking?
3. What convention does "sub-microradian downlink pointing control" use (per-axis 1σ, radial
   RMS, or bias + 3σ total mispoint), and what was the flight bias-vs-jitter split?
4. What are the as-built transmit truncation ratio, full-path wavefront error, and end-to-end
   transmit throughput of the FLT — and is the "4 W" referenced at fiber output or radiated?
5. Was the flight laser at half power on 2024-06-24 — half of 4.0 W or of 4.5 W — and when
   exactly was the restriction lifted?
6. Do DSOC operations gate passes on atmospheric thresholds, and was the 2024-06-24 pass flown
   in daylight, twilight, or darkness? (Geometry: elongation ~53°, evening object, culmination
   in daylight.)
7. Is the Hale prime-focus cage obscuration in coudé configuration correctly ~12.5% areal plus
   vanes, and should it be a deterministic level factor?
8. How large is field-stop/zoom clipping plus dome/mirror-seeing coupling loss under
   worse-than-nominal seeing, and which envelope term should own it?
9. Is 0.75 or 0.76 the right operational detector ceiling given spot-spread operation across
   the 64-pixel SNSPD array?
10. Does JPL's internal DSOC link budget contain any line item outside the thirteen-item
    checklist validated against the ESA OGS LLCD and DOT budgets?

**Consequence if wrong:** The K2 gate verdict (DSOC demoted to secondary) rests on these
bounds; a materially wrong bound in either direction changes the flagship-benchmark decision
and the honesty of any published envelope.

**Priority:** HIGH (partially purchasable: the SPIE 13355 batch likely answers 1, 2, 4, 5, 6.)

---

## 2. Optical link-budget completeness (missing-term risk)

**Topic:** Whether the FarSight link-chain model's term structure is complete — an omitted
term is a silently fitted zero/one, the exact failure the product exists to prevent.

**Expertise eventually required:** Optical-communications link engineering.

**Current state:** Internally cross-checked against two independent flight-program budgets
(ESA OGS LLCD; JPL DOT): thirteen candidate terms dispositioned, two silently-fitted terms
found by that audit and corrected. The check is only as complete as the budgets compared
against. Not externally expert-reviewed.

**Current confidence:** MEDIUM — two independent budget cross-checks is real evidence, but a
term absent from both comparison budgets would pass silently.

**Unresolved:** Question 10 above; seeing-coupling ownership (question 8).

**Consequence if wrong:** A missing term biases every DSOC prediction and the eventual
scoring against the referent; found late, it is a published-package retraction.

**Priority:** HIGH.

---

## 3. Cross-engine matched-configuration tolerances (Stage 3)

**Topic:** What "matched configuration" and "acceptable divergence" mean for Basilisk-vs-GMAT
trajectory comparison — gravity model degree/order, ephemeris versions, EOP handling,
integrator tolerances, and the physically-motivated Tier-C tolerance per channel.

**Expertise eventually required:** Astrodynamics; orbit-determination and propagation V&V
practice.

**Current state:** Methodology committed (ADR-006: matched-config declaration, comparison at
epochs, Richardson-style discrimination); the plan's own risk register (§19 risk 1) ranks
mismatch diagnosis as the likeliest three-week sink for a team without domain depth. No
comparison yet exists. Not externally expert-reviewed.

**Current confidence:** MEDIUM for the methodology (literature-supported precedent: GMAT's own
V&V program); LOW for our ability to diagnose km-level divergences unaided.

**Unresolved:** Expected agreement magnitudes for matched point-mass + J2 configs at our
tolerances; which divergence sources are legitimate vs defects.

**Consequence if wrong:** Cross-engine validation — a core moat claim — either ships with
dishonest tolerances or burns weeks 5+ schedule; K4's gate fires on it.

**Priority:** HIGH (dormant until GMAT work begins; activates at Stage 3).

---

## 4. Basilisk minimal-adapter scenario realism

**Topic:** Whether the weeks 5–6 minimal Basilisk scenario (two-body vs `prop2b`, one mid-run
fault, per-module seed map) exercises the engine in a way a GNC engineer would consider
representative rather than degenerate.

**Expertise eventually required:** Spacecraft GNC simulation; Basilisk practitioner.

**Current state:** K1 spike research-reviewed (determinism, seeding, intervention all
demonstrated on a trivial scenario); the spike's own writeup lists its non-representativeness
(no variable-step integrators, no reaction wheels, no dynamics/FSW split). Not externally
expert-reviewed.

**Current confidence:** HIGH for what was measured; LOW for generalization beyond it.

**Consequence if wrong:** The engine-independence demo claim rests on an adapter validated
against a toy; a realistic scenario could surface wiring or determinism issues the spike
missed.

**Priority:** MEDIUM.

---

## 5. Evidence-package audit usability (AT-9 substitute)

**Topic:** Whether a competent outside aerospace engineer can audit a FarSight evidence
package in ≤2 hours and would say it increases their trust — AT-9, now a deferred gate.

**Expertise eventually required:** Aerospace V&V / mission assurance; an engineer NOT on this
project.

**Current state:** Interim substitute per ADR-030: internal cold audit by a non-author at week
7–8, recorded as internal. The genuinely external judgement — does this artifact increase a
stranger's trust — cannot be self-administered even in principle.

**Current confidence:** SPECULATIVE for the external-trust claim (no evidence type we can
generate bears on it).

**Consequence if wrong:** The audit-usability kill criterion (plan §21) cannot honestly fire
or clear; the product's core commercial claim is untested until access exists.

**Priority:** MEDIUM (becomes CRITICAL at first external demo or design-partner conversation).

---

## 6. Time-system and frame conventions

**Topic:** TDB epoch handling, frame realizations (J2000/ICRF, ITRF93 vs IAU_EARTH for
stations), aberration-correction choices, and leap-second handling in the geometry service —
the domain's "most common silent killers" (plan §14).

**Expertise eventually required:** Astrodynamics / SPICE practitioner.

**Current state:** Conventions decided and recorded (ADR-015, ADR-016) with mechanical
cross-checks specified (SPICE-vs-Astropy elevation, Horizons range goldens, AT-11); the
cross-implementation checks are the strongest available non-expert defense. Not externally
expert-reviewed.

**Current confidence:** MEDIUM — independent-implementation agreement catches most error
classes here, but a convention wrong in both implementations passes.

**Consequence if wrong:** Plausible wrong geometry underneath every experiment; the failure
mode explicitly named in the plan as surviving CI.

**Priority:** MEDIUM.

---

## 7. Metasurface sail as a 1550 nm communications aperture (Stage 7)

**Topic:** Whether a photonic-membrane "dandelion" probe's sail can serve as its
high-gain optical aperture under the interstellar reference architecture's assumptions.

**Expertise eventually required:** Nanophotonics / optical antenna / metasurface engineering.

**Current state:** Literature-supported concept; not demonstrated for FarSight conditions;
listed in the reference architecture's own §17 as an assumption that must remain visible.
Nothing in the current phase depends on it.

**Current confidence:** LOW–SPECULATIVE.

**Critical questions:** achievable optical efficiency; wavefront stability after acceleration;
thermal distortion; radiation and dust degradation; beam-steering precision.

**Consequence if wrong:** Potentially invalidates the photonic-dandelion communications
architecture — the reference stress case, not the product.

**Priority:** CRITICAL at Stage 7; dormant now. Entered so the horizon item is on the ledger
from day one.
