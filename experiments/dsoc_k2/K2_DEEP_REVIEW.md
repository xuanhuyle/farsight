# K2 Deep Review — the DSOC envelope parameter table

**Status:** `research-reviewed; internally cross-checked; independently reconstructed; NOT externally expert-reviewed`
**Date:** 2026-08-29 · **Protocol:** ADR-030 (this is its first executed instance)
**Reviews:** the five epistemic bounds of [`k2_envelope.py`](k2_envelope.py) / [`K2_RESULT.md`](K2_RESULT.md), whose pedigree was `expert_judgment` (mine), pending an optical-comms expert who is not available this phase.
**Method:** four parallel research passes over primary sources only (~225 fetches): receiver train; flight terminal; atmosphere/pointing/detector; then an adversarial pass performing the missing-term hunt, bound challenges, and independent reconstruction.

**Pre-registration audit (ADR-021 boundary): CLEAN.** Sources were used to constrain hardware,
environment and operations configuration only. Achieved data rates and received-signal
measurements — the referent this envelope will later be scored against — were encountered in
several sources and deliberately not used to set or tune any bound. The three near-boundary
usages are all legitimate: the half-power *configuration* statement (like knowing the PPM
order), blocking loss evaluated at the model's *own predicted* count rate, and Horizons
*geometry*.

---

## 1. The claim under review

That the honest epistemic envelope for DSOC received signal at the 2024-06-24 epoch is
10.25 dB wide, built from five interval-bounded unknowns — and, implicitly, that those five
terms are the *complete* set (an omitted term is a silently fitted 1.0).

## 2. Headline findings

**The implicit completeness claim was false.** Three terms were silently fitted:

| Omitted/wrong term | Finding | Effect | Evidence class |
|---|---|---|---|
| `tx_operating_point` | "During the first year of operations, the flight laser was limited to half of its maximum power and lower PPM orders as a risk reduction measure" — Wollman et al., [Opt. Express 32(27):48185](https://opg.optica.org/oe/fulltext.cfm?uri=oe-32-27-48185) / [arXiv:2409.02356](https://arxiv.org/abs/2409.02356); corroborated by [JPL release, Oct 2024](https://www.jpl.nasa.gov/news/nasas-laser-comms-demo-makes-deep-space-record-completes-first-phase/). The K2 epoch falls inside the window. The model assumed the full 4 W. New interval **[0.50, 0.56]** (half of 4.0 W vs half of the LTA's 4.5 W capability, [SPIE 11993 abstract](https://doi.org/10.1117/12.2613448)) | −2.8 dB level, +0.49 dB width | flight-demonstrated (ops statement) |
| Receive obscuration | Hale prime-focus cage ~1.8 m in the 5.08 m beam ≈ 12.5% areal + 1–2% vanes → factor **0.87 ± 0.02**; the model used bare π(D/2)². Precedent: ESA's OGS LLCD budget books effective area explicitly ([ICSOS 2012 PDF](https://icsos2012.nict.go.jp/pdf/1569600363.pdf)) | −0.6 dB level | engineering-estimate from published hardware dimension |
| Epoch range | Model used the rounded press figure 2.58 AU; [JPL Horizons](https://ssd.jpl.nasa.gov/api/horizons.api) (obs 675 → target −255) gives **2.663–2.677 AU** on 2024-06-24 | −0.30 dB level | experimentally-established ephemeris |

**Every judgment bound moved onto sources, and the envelope widened — from 10.25 to
12.76 dB** — which is what ADR-030's widen-never-narrow rule predicts when unaided judgment
meets evidence.

## 3. Per-term results

| Term | Was | Now | Width | Evidence basis of the edges | Confidence |
|---|---|---|---|---|---|
| atmosphere | [0.55, 0.93] | **[0.45, 0.95]** | 3.25 dB | Upper: MODTRAN-class clear-sky at altitude ([DESCANSO Ch. 3](https://descanso.jpl.nasa.gov/monograph/series7/Descanso%207_chap03.pdf), Figs 3-16/17) + [Giggenbach & Shrestha 2022](https://elib.dlr.de/144522/1/Giggenbach-2021-Atmospheric_absorption_and_scattering_impact_on_optical_satellite-ground_links-Wiley-JnlSatCommNW.pdf). Lower: JPL AVM measured extinction statistics (DESCANSO Table 3-4: the benign model prediction is achieved only 15–45% of uptime; thin cirrus is spectrally gray) scaled by airmass. Site/wavelength transfer is extrapolation | **LOW** — zero Palomar/1550 nm measurements in any free source; the weakest term |
| glr_optical_train | [0.25, 0.60] | **[0.25, 0.65]** | 4.15 dB | 3-reflection coudé arm at the epoch's declination ([Bowen, Trans. IAU](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/AD2F5FDEE93E81A1945E49567B4C18DB/S0251107X00032806a.pdf/5_the_200inch_hale_telescope.pdf); dec +13.1° from Horizons); fresh-Al R≈0.974 at 1550 nm (Rakić/McPeak optical constants) vs field-aged >0.95 ([arXiv:1512.00002](https://arxiv.org/pdf/1512.00002)); GLROA architecture qualitative only (Wollman; [SPIE 124130R abstract](https://doi.org/10.1117/12.2649577)); anchored below by JPL's own DOT receiver allocation 0.25–0.30 ([IPN 42-183A](https://ipnpr.jpl.nasa.gov/progress_report/42-183/183A.pdf) Table 8) and bracketed by ESA's minimal 2-mirror receiver at 0.44–0.48. Upper raised to 0.65 because the 1.8 nm filter's presence per pass is unpublished (bimodality must widen, not pick a mode) | **LOW** — the GLROA end-to-end number is the single dominant unpublished quantity |
| flt_eirp | [0.42, 0.81] | **[0.32, 0.72]** | 3.52 dB | Upper: Klein–Degnan truncation ceiling ≈0.81 of ideal uniform gain means the old 0.81 edge was the *vacuum ceiling*; with real coatings/WFE ≤~0.72. STOP-predicted OTA WFE <122 nm ([SPIE 11272 abstract](https://doi.org/10.1117/12.2546678)) → Strehl 0.78 by Maréchal, independently reconstructed and cross-checked against DOT's 0.2-wave assumption. Lower: DOT's own transmitter allocation de-pointed ([IPN 42-183](https://discovery.larc.nasa.gov/pdf_files/29_DOT_SE_Overview.pdf), [42-185](https://tmo.jpl.nasa.gov/progress_report/42-185/185D.pdf)) 0.36–0.40, widened for unpublished as-built path. Transmit obscuration verified **zero** (off-axis Gregorian, "22 cm unobscured") | **MEDIUM-LOW** |
| pointing | [0.85, 0.996] | **[0.83, 0.997]** | 0.80 dB | Lab 0.16 µrad/axis ([ICSOS 2017 deck](https://pdfs.semanticscholar.org/404a/ac311a05d58d6a1050c8c3a5fa453cbe82f7.pdf), p.15 — which also shows ~1 µrad-class tracking at Mars-like Earth flux, supporting the pessimistic edge); flight "sub-microradian" qualitative ([SPIE 133550M abstract](https://doi.org/10.1117/12.3045842) — convention undefined); loss model independently reconstructed and validated against [DESCANSO Ch. 5](https://descanso.jpl.nasa.gov/monograph/series7/Descanso%207_chap05.pdf) Fig. 5-23 (reproduces −2.0 dB at 0.42 λ/D exactly). Original lower edge 0.85 was slightly optimistic against its own worst corner (0.834 recomputed) | **MEDIUM** |
| detector | [0.65, 0.75] | **[0.66, 0.75]** | 0.56 dB | Wollman et al. read in full: peak SDE 76% (TE), operational array efficiency 69–72% under nominal seeing (includes inter-pixel gaps — so 0.76 is not an operational ceiling), blocking ≤~3% at the model's own predicted K2-epoch count rate. Boundary decision recorded: seeing-coupling and polarization conversion are booked once, in the train | **HIGH** — the one term resting on an open-access measurement campaign of the actual hardware |
| tx_operating_point | — (fitted 1.0) | **[0.50, 0.56]** | 0.49 dB | See §2 | **HIGH** (existence) / MEDIUM (exact factor: "half of 4 W vs 4.5 W" unresolved) |

**Total: 12.76 dB** (independently reconstructed as an interval product: 0.62–11.8 Mphotons/s
at the corrected range; ratio 18.9× = 12.76 dB). The prior consistency observation still holds
— the achieved 8.3 Mbps sits inside the shifted band — noted as observation only.

## 4. Missing-term audit (13 candidates dispositioned)

Checked against two independent flight-program budgets — the ESA OGS LLCD downlink budget
(found this pass; the strongest free comparison artifact) and JPL's DOT budget. Beyond the
three §2 findings: coding/implementation loss and sky background are *rate-domain* terms,
correctly outside a received-signal envelope (background is additive, per the ESA budget's own
row structure); the GLR acquisition/tracking pickoff is a real budget row (ESA: −0.45 dB)
whose DSOC value is unpublished — held inside the train width and pinning its lower edge;
filter Doppler detuning is negligible (LOS rate ≈ 24 km/s → 0.12 nm inside a 1.8 nm FWHM);
transmit obscuration is verified zero; scintillation is aperture-averaged; Hale tracking is
negligible against the 27–50 µrad FOV; the detector boundary (cryostat window) is clean with
no gap. One loss mode remains *unbounded by any source*: field-stop/seeing-disc clipping under
poor seeing — it argues permanently against raising the train's lower edge.

## 5. Disagreements between sources (reported, never averaged)

1. Old flt_eirp upper 0.81 vs truncation-ceiling physics ≤0.72 — contradiction; corrected.
2. DOT receiver allocation 0.25–0.30 vs bottom-up component product 0.33–0.68 — kept as the
   two train edges; ESA's 0.44–0.48 for a simpler receiver sits between.
3. Clear-sky models (T₀ 0.93–0.96) vs measured extinction statistics (benign value achieved
   15–45% of uptime) — kept as the two atmosphere edges.
4. "4 W" (press kit) vs "up to 4.5 W" LTA capability — carried as the op-point spread.
5. Fresh-Al optical constants vs field-aged measurements — consistent under aging; both kept.
6. Pointing lower edge 0.72–0.91 depending on beam-width convention and the undefined
   "sub-microradian" convention — widest defensible convention kept.
7. Detector ceiling: 76% peak vs 69–72% operational — resolved to 0.75 with reasoning; a
   human expert may overrule (backlog Q9).
8. Range 2.58 AU (press, rounded) vs 2.663–2.677 AU (Horizons) — ephemeris wins.
9. "5–8 reflective surfaces" (old basis) vs Bowen's 3-reflection coudé arm + 1–3 unpublished
   folds — basis corrected to "4–6".
10. Obscuration inside the train interval vs as a separate deterministic factor —
    width-identical; the separate factor adopted in v2 as the cleaner structure.

## 6. Verdict input

Against the pre-committed thresholds (plan §21 K2, §18 AT-5):
- **12.76 dB > 12 dB — the demote condition is triggered on research-supported bounds.** The
  most charitable defensible reading (op-point pinned at center, filter established as
  installed) is 11.92 dB — resolvable only by data we do not hold.
- **AT-5 (≤6 dB) fails by 6.8 dB on free data** — confirming the original memo's assessment.
- Pin-decomposition (what a purchase buys): pin train → 8.61 dB; + atmosphere → 5.37 dB
  (AT-5 passes); + op-point → **4.87 dB**. All three are plausibly answered by the ~$300
  SPIE 13355 batch (Alerstam 133550N, Wright 133550L, Andrews 133550M), which now attacks
  four terms at once.

## 7. Residue for an eventual human expert

The ten hand-over questions are recorded verbatim in
[`EXPERT_REVIEW_BACKLOG.md`](../../EXPERT_REVIEW_BACKLOG.md) entry 1 (priority HIGH), per
ADR-030 enforcement 3. Highest-leverage: filter presence per pass, GLROA end-to-end
throughput, the "sub-microradian" convention, the exact half-power semantics.

## 8. Dead ends (reported as required)

SPIE Digital Library full texts (10096, 11272, 12413, 12877, 13355 series) — bot-gated or
paywalled; abstracts used and labelled. IEEE Xplore (ICSOS 2017 formal record; JSTQE 2026
system paper, doc 11220176) — blocked. MIT DSpace LLCD PDFs — HTTP 405. Klein & Degnan 1974's
exact 0.8145 truncation factor — UNVERIFIED from any free primary (cited via DESCANSO/DOT
usage; the *ceiling's existence* is independently supported by DOT's own allocations).
Optica supplemental for the SNSPD paper — redirect-gated. Hale-specific mirror-reflectivity
logs — exist at Caltech Optical Observatories, unpublished. Palomar altitude — corroborated
only by secondary sources.

**What would have been two hours of an expert's time consumed a four-agent research campaign
over ~225 source fetches, and still leaves the ten questions above open. That ratio is the
recorded cost of the no-expert constraint, and this artifact does not claim to have closed
the gap — it claims to have mapped it.**