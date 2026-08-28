"""K2 gate: the DSOC epistemic envelope, hand-computed.

This is deliberately NOT the FarSight pipeline. It is the gate that decides whether it is
worth pointing that pipeline at DSOC at all, so it must not depend on the thing it is
evaluating. Plain arithmetic, every input on the page, no imports beyond the standard library.

    Plan §21 K2:  envelope > 12 dB at 2.6 AU using all free published constraints
                  -> DSOC is demoted to secondary and the DSN RF benchmark becomes flagship.
    Plan §18 AT-5: envelope width <= 6 dB, else the acceptance test is vacuous -- a band that
                  wide is consistent with almost any model and cannot falsify one.

The quantity computed is the *width* of the honest prediction band for received signal, and
hence for supportable data rate. Range does not contribute to the width: geometry is known to
much better than a dB from published ephemerides (and will come from SPICE). The width is set
entirely by the terms nobody has published, and the whole point of the exercise is to refuse to
fit them.

Epistemic terms combine by interval arithmetic -- worst corner against worst corner -- because
they are not random variables and there is no distribution over them to convolve. Treating them
as independent Gaussians and adding in quadrature would produce a narrower, more flattering
band that means nothing, and is precisely the laundering ADR-004 exists to prevent.

Provenance of the bounds below: the *values* are engineering judgement over published component
classes, not measurements. Their pedigree level is `expert_judgment`, and the paid optical-comms
review (plan §19 risk 2) is what turns them into something better. That is stated here rather
than discovered later, because a gate decision resting on invented numbers would be exactly the
failure this project exists to prevent.
"""

from __future__ import annotations

import math

H_PLANCK = 6.62607015e-34  # J s, exact by SI definition
C_LIGHT = 2.99792458e8  # m/s, exact by SI definition
AU_M = 1.495978707e11  # m, IAU 2012 definition

# ----------------------------------------------------------------------------------------
# Published, and therefore not part of the envelope width
# ----------------------------------------------------------------------------------------
# Sources: JPL DSOC press kit; Biswas et al., ICSOS 2017; open-access SNSPD paper
# (arXiv:2409.02356). Each of these needs a hash-pinned DataArtifact when this becomes a real
# FarSight referent (plan §14 item 5); here they are transcribed with the citation named.
LAMBDA_M = 1550e-9  # flight downlink wavelength
P_TX_W = 4.0  # flight laser average power
D_TX_M = 0.22  # flight transceiver aperture
D_RX_M = 5.1  # Hale telescope, Palomar

# Achieved-rate points, from NASA/JPL releases. These are *operationally selected* rates, not
# channel capacity -- the distinction that makes the claim one-sided (ADR-021).
EPOCHS = [
    # (label, range_AU, achieved_Mbps, note)
    ("2023-12-11", 0.21, 267.0, "hardware-capped: cannot falsify (saturated, ADR-021)"),
    ("2024-04-08", 1.51, 25.0, "two-sided-capable"),
    ("2024-06-24", 2.58, 8.3, "two-sided-capable; this is the K2 decision epoch"),
]

# ----------------------------------------------------------------------------------------
# The unknowns. Each is an interval, and NONE is fitted to an achieved rate.
# ----------------------------------------------------------------------------------------
# name -> (lower, upper, basis)
UNKNOWNS: dict[str, tuple[float, float, str]] = {
    "atmosphere": (
        0.55,
        0.93,
        "1550 nm sits in a good window; a clear night at Palomar at moderate airmass is "
        "~0.90, thin cirrus is far worse. Per-pass conditions are not published for any pass.",
    ),
    "glr_optical_train": (
        0.25,
        0.60,
        "Hale coude path (5-8 reflective surfaces), ~1.8 nm bandpass filter, and coupling into "
        "the SNSPD. No end-to-end throughput figure is published in any free source.",
    ),
    "flt_eirp": (
        0.42,
        0.81,
        "Strehl and transmit-path optical throughput of the flight terminal. Aperture and "
        "average power are published; what fraction actually leaves as a diffraction-limited "
        "beam is not.",
    ),
    "pointing": (
        0.85,
        0.996,
        "Flight performance published only as 'sub-microradian'; lab jitter 0.16 urad/axis. "
        "Loss computed from those two against the 22 cm beamwidth.",
    ),
    "detector": (
        0.65,
        0.75,
        "SNSPD system detection efficiency ~70% is open-access (arXiv:2409.02356); the "
        "residual interval covers operating-point and blocking-loss variation.",
    ),
}


def db(ratio: float) -> float:
    return 10.0 * math.log10(ratio)


def width_db(lo: float, hi: float) -> float:
    return db(hi / lo)


def photon_energy() -> float:
    return H_PLANCK * C_LIGHT / LAMBDA_M


def geometric_photon_rate(range_au: float) -> float:
    """Photons per second collected by the receive aperture, before any efficiency term.

    Diffraction-limited transmit gain into a receive area at range R. Everything here is
    published or defined, so it contributes to the *level* of the prediction and nothing to
    its width.
    """
    r_m = range_au * AU_M
    g_tx = (math.pi * D_TX_M / LAMBDA_M) ** 2
    a_rx = math.pi * (D_RX_M / 2.0) ** 2
    p_rx_w = P_TX_W * g_tx * a_rx / (4.0 * math.pi * r_m**2)
    return p_rx_w / photon_energy()


def envelope(range_au: float, exclude: set[str] = frozenset()) -> tuple[float, float, float]:
    """(low, high, width_db) of the received photon rate, in photons/s.

    `exclude` drops a term from the epistemic set -- used to ask what a given measurement
    would buy, which is the decomposition that matters more than the width itself.
    """
    base = geometric_photon_rate(range_au)
    lo = hi = base
    for name, (a, b, _) in UNKNOWNS.items():
        if name in exclude:
            mid = math.sqrt(a * b)  # pinned at its geometric centre; contributes no width
            lo *= mid
            hi *= mid
        else:
            lo *= a
            hi *= b
    return lo, hi, db(hi / lo)


def main() -> None:
    print("=" * 78)
    print("K2 GATE -- DSOC epistemic envelope, hand-computed")
    print("=" * 78)
    print(f"\nPhoton energy at {LAMBDA_M * 1e9:.0f} nm: {photon_energy():.4e} J")
    print(f"Transmit gain from {D_TX_M} m aperture: {db((math.pi * D_TX_M / LAMBDA_M) ** 2):.1f} dB")
    print(f"Receive area of {D_RX_M} m aperture: {math.pi * (D_RX_M / 2) ** 2:.2f} m^2")

    print("\n" + "-" * 78)
    print("UNKNOWN TERMS (none fitted; interval arithmetic, worst corner to worst corner)")
    print("-" * 78)
    total = 0.0
    for name, (a, b, _basis) in UNKNOWNS.items():
        w = width_db(a, b)
        total += w
        print(f"  {name:20s} [{a:.3f}, {b:.3f}]   {w:5.2f} dB")
    print(f"  {'TOTAL WIDTH':20s} {'':21s}{total:5.2f} dB")

    print("\n" + "-" * 78)
    print("ENVELOPE AT EACH EPOCH")
    print("-" * 78)
    for label, au, achieved, note in EPOCHS:
        lo, hi, w = envelope(au)
        # Supportable rate scales with received photon rate at fixed photon efficiency.
        # 1.0 bit/photon is a deliberately round, conservative stand-in for a high-order PPM
        # operating point; it shifts the level, never the width.
        print(f"\n  {label}  ({au} AU)   achieved {achieved} Mbps")
        print(f"    collected photon rate: {lo / 1e6:9.2f} .. {hi / 1e6:9.2f} Mphotons/s")
        print(f"    implied rate @1 b/ph : {lo / 1e6:9.2f} .. {hi / 1e6:9.2f} Mbps")
        print(f"    envelope width       : {w:.2f} dB  ({10 ** (w / 10):.1f}x, "
              f"~{w / db(2):.1f} rate-ladder steps at 2x per step)")
        print(f"    note: {note}")

    print("\n" + "-" * 78)
    print("WHAT WOULD NARROW IT (the artifact that matters)")
    print("-" * 78)
    k2_au = EPOCHS[-1][1]
    _, _, full = envelope(k2_au)
    for name in UNKNOWNS:
        _, _, w = envelope(k2_au, exclude={name})
        print(f"  pin {name:20s} -> {w:5.2f} dB   (buys {full - w:4.2f} dB)")
    _, _, both = envelope(k2_au, exclude={"glr_optical_train", "atmosphere"})
    print(f"  pin train + atmosphere     -> {both:5.2f} dB   (buys {full - both:4.2f} dB)")

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    print(f"  Envelope at {k2_au} AU: {full:.2f} dB")
    print(f"  K2 threshold (>12 dB demotes DSOC): {'PASS' if full <= 12 else 'FAIL'}")
    print(f"  AT-5 threshold (<=6 dB or vacuous): {'PASS' if full <= 6 else 'FAIL'}")


if __name__ == "__main__":
    main()
