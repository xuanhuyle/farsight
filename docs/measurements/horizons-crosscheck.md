# `ci-geometry-crosscheck` — FarSight's SPICE pipeline vs JPL Horizons

**Measured:** 2026-09-07 · **Status:** measurement, not a review sign-off · **NOT externally
expert-reviewed** · **Tolerance set by the founder 2026-09-07**

Plan §14 item 3 asks for two independent implementations compared rather than merged, because a
systematic frame or time-system error is invisible to a single implementation checked against
itself. This is that comparison for geometry.

## What was compared

| | |
|---|---|
| Ours | `farsight geometry` → SPICE, the nine kernels pinned in `kernels/pinned_kernels.json` |
| Theirs | JPL Horizons API, response archived at `tests/fixtures/horizons/psyche_palomar_2024-01-15.txt` |
| Golden SHA-256 | `026ab8c0e61d03762e4b4cb6adc239e508e21a5d2641e0c5c985a4f9fbbd73c0` |
| Target | `-255` (`PSYC`), the Psyche **spacecraft** |
| Observer | `PSYC_DSOC_PALOMAR`, its position taken from the SPK and handed to Horizons as `SITE_COORD` |
| Epochs | 2024-01-15 00:00 → 2024-01-16 00:00 UTC, 3-hour step, 9 samples |
| Conventions | range compared under `CN`; elevation under `CN+S`; `APPARENT=AIRLESS`, no refraction on either side |

The comparison runs **offline** against the archived response, whose digest is asserted before any
number is read from it. ADR-012 forbids the truth loop a network call, and ADR-015 requires the
Horizons response to be a hash-pinned artifact whose settings are read from the artifact rather
than restated in prose — so the test asserts the settings block too.

## Result

| quantity | worst disagreement | AT-11 states | margin |
|---|---|---|---|
| **Range** | **0.69 m** over 61.5 million km | 10 km | **14,400×** inside |
| **Elevation** | **0.134 arcsec** (3.7e-5 deg) | 0.01 deg | **269×** inside |

Relative agreement on range is ~1.1 × 10⁻¹¹.

## The residual is explained, not merely small

The range difference is not noise: it tracks elevation, peaking at 0.69 m when Psyche is 81.7°
overhead and falling to 0.11 m near the horizon. That is the signature of a station **height**
difference projected on the line of sight.

Cause, measured: the site was handed to Horizons as geodetic lon/lat/alt, derived using
`pck00010.tpc`'s Earth radii (a = 6378.1366 km). Horizons rebuilt a Cartesian position from those
numbers with its own model (a = 6378.137 km, stated in the archived header). The 0.4 m difference
in equatorial radius displaces the station by **0.414 m**, radial component 0.310 m — which
accounts for the observed spread.

So the agreement on *where the spacecraft is* is better than the 0.69 m headline. The residual is
an artefact of how the site was specified.

## What this establishes, and what it does not

Horizons states its own source in the archived header: `{source: psyche_merged}` — **JPL's merged
Psyche trajectory, the same solution family the SPK carries.**

**This is an independent implementation, not an independent measurement.** The distinction is the
whole point of writing it down.

**It does check**, and was verified to fail on, each of the following — every one exercised as a
mutation against the live test:

| deliberate error | caught |
|---|---|
| aberration `CN` → `NONE` on a range | yes |
| aberration `CN+S` → `CN` on a direction | yes |
| target: spacecraft → the asteroid (16) Psyche | yes |
| observer: Palomar → OCTL | yes |
| frame: topocentric → inertial `J2000` | yes |
| time: UTC interpreted as TDB | yes |
| the archived golden edited after the fact | yes |

**It cannot check** whether JPL's trajectory is right. If the reconstructed SPK were wrong, both
sides would be wrong identically and this test would still pass. "Validated against an independent
source" would overstate it. The claim it supports is: *agrees with an independent implementation
of the same solution, to sub-metre, under matched conventions.*

A check that would be independent of the solution needs a different kind of referent — a radiometric
tracking residual, or a published DSOC link-budget figure — and none is in hand. That belongs in
`EXPERT_REVIEW_BACKLOG.md`, not here.

## The acceptance tolerance — DECIDED

**Set by the founder on 2026-09-07: 10 m on range, 1 arcsec on elevation.**

ADR-030 makes an acceptance tolerance a decision somebody owns rather than a number inferred from
a measurement, and this is that decision. It is now what the check asserts, not a regression bound.

| | measured | tolerance | margin | absolute headroom |
|---|---|---|---|---|
| range | 0.69 m | **10 m** | 14.5× | 9.31 m |
| elevation | 0.134 arcsec | **1 arcsec** | 7.5× | 0.866 arcsec |

The boundary was verified rather than assumed: an injected 9 m range error passes and 11 m fails;
an injected elevation error totalling 0.934 arcsec passes and 1.004 arcsec fails.

**Three things this tolerance means, worth stating before anyone reads it as slack.**

*The known artefact is not eating the budget.* The 0.414 m station displacement from the Earth-
radius model difference is about 4% of the range tolerance.

*The conventions the check exists to catch are still caught, with room to spare.* A defaulted
aberration correction moves the range by 735 km — 73,500 tolerances. Dropping stellar aberration
from a direction moves elevation by 18.4 arcsec — 18 tolerances. Neither is close to the line.

*It is deliberately tighter than a re-solved trajectory.* JPL re-releases reconstructed SPKs — the
Psyche archive already carries a `_v2` — and a new solution can move a range by kilometres. At 10 m
this check therefore **fails when the pinned kernel changes**, which is the intended behaviour: a
re-solved trajectory is a finding to be looked at, not a golden to be quietly refreshed.

**What it does not become.** This is the tolerance for *this* check — our implementation against
Horizons under matched conventions. It is not a statement about absolute knowledge of where Psyche
is, because both sides inherit JPL's solution (see the section above). AT-11's separate figures of
10 km and 0.01 deg are unchanged by this decision; nothing here amends an accepted record.

Reproduce the query with `python scripts/fetch_horizons_golden.py`; run the comparison with
`pytest tests/unit/test_horizons_crosscheck.py`.
