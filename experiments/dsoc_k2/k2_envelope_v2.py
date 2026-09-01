"""K2 envelope, revision 2 — bounds re-anchored by the Deep Review (K2_DEEP_REVIEW.md).

Supersedes `k2_envelope.py` for the gate verdict; the original stays untouched as the
pre-registered v1 artifact. Three structural changes, all found by the Deep Review:

  * a sixth epistemic term, `tx_operating_point` [0.50, 0.56] — the flight laser ran at half
    power throughout the first year of operations, which includes the K2 epoch (Wollman et
    al., Opt. Express 32:48185, open access; corroborated by JPL's Oct 2024 release). The v1
    model silently assumed the full 4 W.
  * receive obscuration as a deterministic level factor 0.87 — the Hale prime-focus cage
    (~12.5% areal + vanes) sits in the beam; v1 used the bare geometric area. A level term,
    not a width term: its +/-0.02 uncertainty is negligible against the epistemic widths.
  * epoch range corrected to the Horizons ephemeris value (2.67 AU on 2024-06-24), replacing
    the rounded press figure 2.58 AU.

Status of every bound: research-reviewed, internally cross-checked, independently
reconstructed; NOT externally expert-reviewed (ADR-030). Per-edge sources, taxonomy labels
and confidence live in K2_DEEP_REVIEW.md; this file is the arithmetic only. Interval terms
still combine worst-corner to worst-corner: they are not random variables, and quadrature
would manufacture a narrower band that means nothing.

Standard library only, deliberately not the FarSight pipeline.
"""

from __future__ import annotations

import math

H_PLANCK = 6.62607015e-34  # J s, exact by SI definition
C_LIGHT = 2.99792458e8  # m/s, exact by SI definition
AU_M = 1.495978707e11  # m, IAU 2012 definition

LAMBDA_M = 1550e-9
P_TX_W = 4.0  # published average power; the first-year operating point is a separate term
D_TX_M = 0.22
D_RX_M = 5.1

# Deterministic level factor (Deep Review §2): Hale prime-focus cage + vanes. Booked at the
# geometric level, not as epistemic width.
RX_OBSCURATION = 0.87

# The K2 decision epoch, range per JPL Horizons (obs 675 -> target -255, 2024-06-24).
EPOCHS = [
    ("2023-12-11", 0.21, 267.0, "hardware-capped: cannot falsify (saturated)"),
    ("2024-04-08", 1.51, 25.0, "two-sided-capable; op-point term also applies"),
    ("2024-06-24", 2.67, 8.3, "K2 decision epoch (range: Horizons, was 2.58 in v1)"),
]

# name -> (lower, upper, one-line basis; full sourcing in K2_DEEP_REVIEW.md)
UNKNOWNS: dict[str, tuple[float, float, str]] = {
    "atmosphere": (
        0.45,
        0.95,
        "Clear-sky models vs measured extinction statistics (DESCANSO Ch.3, AVM Table 3-4); "
        "site/wavelength transfer is extrapolation. Confidence LOW.",
    ),
    "glr_optical_train": (
        0.25,
        0.65,
        "3-mirror coude arm + unpublished GLROA; anchored by DOT allocation 0.25-0.30 and "
        "ESA OGS 0.44-0.48; filter-presence bimodality widens the top. Confidence LOW. "
        "Obscuration now OUTSIDE this term (deterministic level factor).",
    ),
    "flt_eirp": (
        0.32,
        0.72,
        "Upper capped by Klein-Degnan truncation ceiling with real optics; lower brackets "
        "DOT's de-pointed transmitter allocation. Confidence MEDIUM-LOW.",
    ),
    "pointing": (
        0.83,
        0.997,
        "Lab 0.16 urad/axis to ~1 urad-class at planetary Earth flux; loss model validated "
        "against DESCANSO Fig. 5-23. Confidence MEDIUM.",
    ),
    "detector": (
        0.66,
        0.75,
        "Measured operational array SDE 69-72% nominal-seeing x blocking at predicted rate; "
        "0.76 peak is not an operational ceiling. Confidence HIGH.",
    ),
    "tx_operating_point": (
        0.50,
        0.56,
        "Flight laser at half power for the whole first year (flight-demonstrated ops "
        "statement); half of 4.0 W vs half of 4.5 W capability. Confidence HIGH/MEDIUM.",
    ),
}


def db(ratio: float) -> float:
    return 10.0 * math.log10(ratio)


def photon_energy() -> float:
    return H_PLANCK * C_LIGHT / LAMBDA_M


def geometric_photon_rate(range_au: float) -> float:
    """Photons/s collected by the obscured receive aperture before any efficiency term."""
    r_m = range_au * AU_M
    g_tx = (math.pi * D_TX_M / LAMBDA_M) ** 2
    a_rx = math.pi * (D_RX_M / 2.0) ** 2 * RX_OBSCURATION
    p_rx_w = P_TX_W * g_tx * a_rx / (4.0 * math.pi * r_m**2)
    return p_rx_w / photon_energy()


def envelope(range_au: float, pinned: set[str] = frozenset()) -> tuple[float, float, float]:
    """(low, high, width_db). `pinned` terms sit at their geometric centre: zero width."""
    lo = hi = geometric_photon_rate(range_au)
    for name, (a, b, _) in UNKNOWNS.items():
        if name in pinned:
            mid = math.sqrt(a * b)
            lo *= mid
            hi *= mid
        else:
            lo *= a
            hi *= b
    return lo, hi, db(hi / lo)


def main() -> None:
    print("=" * 78)
    print("K2 ENVELOPE v2 -- Deep-Review bounds (research-reviewed; not expert-reviewed)")
    print("=" * 78)
    print(f"Receive obscuration (deterministic level): {RX_OBSCURATION}  ({db(RX_OBSCURATION):+.2f} dB vs v1)")

    print("\n" + "-" * 78)
    print("TERMS (interval arithmetic, worst corner to worst corner)")
    print("-" * 78)
    total = 0.0
    for name, (a, b, _basis) in UNKNOWNS.items():
        w = db(b / a)
        total += w
        print(f"  {name:20s} [{a:.3f}, {b:.3f}]   {w:5.2f} dB")
    print(f"  {'TOTAL WIDTH':20s} {'':21s}{total:5.2f} dB")

    print("\n" + "-" * 78)
    print("ENVELOPE AT EACH EPOCH")
    print("-" * 78)
    for label, au, achieved, note in EPOCHS:
        lo, hi, w = envelope(au)
        print(f"\n  {label}  ({au} AU)   achieved {achieved} Mbps  [observation only; not used]")
        print(f"    collected photon rate: {lo / 1e6:9.2f} .. {hi / 1e6:9.2f} Mphotons/s")
        print(f"    envelope width       : {w:.2f} dB  ({hi / lo:.1f}x)")
        print(f"    note: {note}")

    print("\n" + "-" * 78)
    print("PIN-DECOMPOSITION AT THE K2 EPOCH (what a purchase buys)")
    print("-" * 78)
    au = EPOCHS[-1][1]
    _, _, full = envelope(au)
    for pins in (
        {"glr_optical_train"},
        {"glr_optical_train", "atmosphere"},
        {"glr_optical_train", "atmosphere", "tx_operating_point"},
    ):
        _, _, w = envelope(au, pinned=pins)
        print(f"  pin {' + '.join(sorted(pins)):55s} -> {w:5.2f} dB")

    print("\n" + "=" * 78)
    print("VERDICT INPUT")
    print("=" * 78)
    print(f"  Envelope at {au} AU: {full:.2f} dB")
    print(f"  K2 demote threshold  (>12 dB): {'TRIGGERED' if full > 12 else 'not triggered'}")
    print(f"  AT-5 usability threshold (<=6 dB): {'met' if full <= 6 else 'NOT MET on free data'}")


if __name__ == "__main__":
    main()
