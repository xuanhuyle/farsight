"""Stage 1 of the first project: reproduce Voyager 2's published link tables from their inputs.

Source: R. Ludwig and J. Taylor, "Voyager Telecommunications", DESCANSO Design and Performance
Summary Series, Article 4, JPL, March 2002. Tables 5-2 (S-band uplink carrier), 5-3 (X-band
downlink carrier) and 5-4 (X-band 160 bps telemetry), predicting Voyager 2 at DSS-43, the 70 m
Canberra antenna, on 1996-01-01 00:00.

TRANSCRIPTION. Every number below was read two independent ways, and the two agree digit for
digit: text extracted from JPL's PDF, with glyph coordinates used to fix which column each number
sits in, and the Internet Archive's OCR of the same article. A blank cell is None, never 0.0 --
the tables really do print no mean or variance for some rows, and silently treating that as zero
would decide one of the questions this script exists to ask.

THE RULE (plan section 6, fixed before this ran). Every published total must be matched to its
printed precision, 0.1 dB. A mismatch is reported with the input that causes it and is never tuned
away. The candidate conventions are all declared below, before any result exists, and are scored
side by side. None is chosen because it happens to work: a convention that reproduces one table
and not another is itself the finding.

    mean conventions      design sum; printed mean (blank -> design); printed mean (blank -> 0);
                          uniform; triangular; JPL per-row types from Cheung, IPN 42-183 (2010),
                          Table 2(b)
    variance conventions  printed (blank -> 0); uniform; triangular; JPL types with Gaussian
                          tolerances read as +/-3 sigma; the same read as +/-2 sigma

One caution is stated here rather than discovered in the output. The source does not say how a
Gaussian row's tolerances map to sigma, so the +/-2 and +/-3 sigma readings are both carried. If
one of them matches, that identifies a convention from the printed numbers -- an inference, not an
independent reproduction -- and the result memo must say so. Table 2(b) covers downlink
parameters only; Table 2(a) (uplink) was not read, so the JPL-type convention is not evaluated on
Table 5-2 at all rather than guessed.

Standard library only, deliberately not the FarSight pipeline: this is arithmetic on published
numbers, and a reproduction that ran through the system under test would prove less.

Exit status is the gate: 0 if at least one declared mean convention reproduces every published
dB total, 1 if none does. Exit 1 is a scientific result ("not reproduced"), not a crash.

Status: internally cross-checked transcription. The inputs are JPL's; nothing here is externally
expert-reviewed (ADR-030).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

C_KM_S = 299_792.458            # exact, SI
BOLTZMANN_J_K = 1.380_649e-23   # exact, SI 2019
AU_KM = 149_597_870.7           # IAU 2012

MEAN_HALF_STEP = 0.05           # totals printed to 0.1 dB
VAR_HALF_STEP = 0.005           # variances printed to 0.01 dB^2
EPS = 1e-9


@dataclass(frozen=True)
class Row:
    key: str
    name: str
    design: float | None
    fav: float | None = None
    adv: float | None = None
    mean: float | None = None      # as printed; None where the cell is blank
    var: float | None = None
    jpl: str | None = None         # IPN 42-183 Table 2(b) pdf type; None = not assignable


# ---------------------------------------------------------------------------------------------
# Transcription. dB-valued rows that enter each (1+2+...+9) sum, with their dB sub-rows expanded.
# ---------------------------------------------------------------------------------------------

UPLINK_SUMMED = [  # Table 5-2, DSS-43 -> Voyager 2, S-band
    Row("1", "RF Power, dBm", 72.55, 0.50, -0.50, 72.6, 0.04),
    Row("1a", "Transmit Circuit Loss, dB", 0.00, 0.00, 0.00, 0.0, 0.00),
    Row("2", "Antenna Gain (DSS-43), dBi", 62.10, 0.30, -0.70, 61.9, 0.08),
    Row("3", "Pointing Loss, dB", -0.03, -0.03, -0.03),
    Row("4", "Space Loss, dB", -296.18, None, None, -296.2, 0.00),
    Row("5", "Atmospheric Attenuation, dB", -0.04, 0.00, 0.00, 0.0, 0.00),
    Row("6", "Polarization Loss, dB", -0.12, 0.12, -0.18),
    Row("7", "Antenna Gain (spacecraft), dBi", 34.60, 0.39, -0.39, 34.5, 0.03),
    Row("8", "Pointing Error, dB", -0.10, 0.10, -0.10, -0.1, 0.00),
    Row("9", "Rec Circuit Loss, dB", 0.00, 0.00, 0.00, 0.0, 0.00),
]
UPLINK_N0 = Row("10", "Noise Spec Dens, dBm/Hz", -166.71, -0.10, 0.16, -166.7, 0.00)
UPLINK_BW = Row("11", "Carr Thr Noise BW, dB-Hz", 12.72, -0.24, 0.23, 12.7, 0.01)
UPLINK_14 = Row("14", "Ranging Suppression, dB", 0.00, 0.00, 0.00, 0.0, 0.00)
UPLINK_15 = Row("15", "Command Suppression, dB", 0.00, 0.00, 0.00, 0.0, 0.00)

DOWNLINK_SUMMED = [  # Table 5-3, Voyager 2 -> DSS-43, X-band
    Row("1a", "Transmitter Power, dBm", 40.90, 0.50, -0.50, 40.9, 0.04, "triangular"),
    Row("1b", "Transmit Circuit Loss, dB", 0.00, 0.00, 0.00, 0.0, 0.00, "uniform"),
    Row("2", "Antenna Circuit Loss, dB", 0.00, 0.30, 0.00, 0.0, 0.00, "uniform"),
    Row("3", "Antenna Gain (spacecraft HGA), dBi", 48.20, 0.26, -0.26, 48.2, 0.01, "triangular"),
    Row("4", "Pointing Error, dB", -0.10, 0.10, -0.10, -0.1, 0.00, "uniform"),
    Row("5", "Space Loss, dB", -308.19, None, None, -308.2, 0.00, "deterministic"),
    Row("6", "Atmospheric Attenuation, dB", -0.04, 0.00, 0.00, 0.0, 0.00, "deterministic"),
    Row("7", "Polarization Loss, dB", -0.08, 0.08, -0.11, None, None, "uniform"),
    Row("8", "Antenna Gain (DSS-43), dBi", 74.01, 0.60, -0.60, 73.7, 0.14, "triangular"),
    Row("9", "Pointing Loss, dB", -0.20, 0.20, -0.20, None, None, "uniform"),
]
DOWNLINK_N0 = Row("10", "Noise Spec Dens, dBm/Hz", -185.35, -0.97, 0.80, -185.4, 0.09, "gaussian")
DOWNLINK_BW = Row("11", "Carr Thr Noise BW, dB-Hz", 14.77, -0.46, 0.41, 14.8, 0.03,
                  "deterministic")
DOWNLINK_14 = Row("14", "Ranging Suppression, dB", -0.22, 0.05, 0.05, -0.2, 0.00, "triangular")
DOWNLINK_15 = Row("15", "Telemetry Suppression, dB", -6.02, 0.16, -0.17, -6.0, 0.00, "triangular")

TLM_19 = Row("19", "Data Bit Rate (160 bps), dB", 22.04, 0.00, 0.00, 22.0, 0.00, "deterministic")
TLM_20 = Row("20", "Data Pwr/Total Pwr, dB", -1.25, 0.05, -0.06, -1.2, 0.00, "triangular")
TLM_23 = Row("23", "System Losses, dB", -0.72, 0.06, -0.36, -0.8, 0.01, "triangular")
TLM_25 = Row("25", "Threshold, dB", 2.34, 0.00, 0.00, 2.3, 0.00, "deterministic")

ALL_ROWS = [*UPLINK_SUMMED, UPLINK_N0, UPLINK_BW, UPLINK_14, UPLINK_15,
            *DOWNLINK_SUMMED, DOWNLINK_N0, DOWNLINK_BW, DOWNLINK_14, DOWNLINK_15,
            TLM_19, TLM_20, TLM_23, TLM_25]


# ---------------------------------------------------------------------------------------------
# Distribution arithmetic. Tolerances bound the parameter at design+adv and design+fav.
# ---------------------------------------------------------------------------------------------

def shape_mean(row: Row, shape: str) -> float:
    d = row.design if row.design is not None else 0.0
    if row.fav is None or row.adv is None or shape == "deterministic":
        return d
    f, a = row.fav, row.adv
    if shape in {"uniform", "gaussian"}:
        return d + (f + a) / 2
    if shape == "triangular":            # mode at design: mean = (lower + upper + mode) / 3
        return d + (f + a) / 3
    raise ValueError(shape)


def shape_var(row: Row, shape: str, sigmas: float = 3.0) -> float:
    if row.fav is None or row.adv is None or shape == "deterministic":
        return 0.0
    f, a = row.fav, row.adv
    if shape == "uniform":
        return (f - a) ** 2 / 12
    if shape == "triangular":            # (a^2 + b^2 + c^2 - ab - ac - bc) / 18, shifted to c = 0
        return (f * f + a * a - f * a) / 18
    if shape == "gaussian":              # tolerance span read as +/- `sigmas`
        return ((f - a) / (2 * sigmas)) ** 2
    raise ValueError(shape)


MeanConvention = Callable[[Row], float]
VarConvention = Callable[[Row], float]

MEAN_CONVENTIONS: dict[str, MeanConvention] = {
    "design sum": lambda r: r.design if r.design is not None else 0.0,
    "printed mean, blank->design": lambda r: r.mean if r.mean is not None else (r.design or 0.0),
    "printed mean, blank->0": lambda r: r.mean if r.mean is not None else 0.0,
    "uniform": lambda r: shape_mean(r, "uniform"),
    "triangular": lambda r: shape_mean(r, "triangular"),
    "JPL types (IPN 42-183)": lambda r: shape_mean(r, r.jpl) if r.jpl else float("nan"),
}
VAR_CONVENTIONS: dict[str, VarConvention] = {
    "printed, blank->0": lambda r: r.var if r.var is not None else 0.0,
    "uniform": lambda r: shape_var(r, "uniform"),
    "triangular": lambda r: shape_var(r, "triangular"),
    "JPL types, Gaussian +/-3 sigma": lambda r: shape_var(r, r.jpl, 3.0) if r.jpl else float("nan"),
    "JPL types, Gaussian +/-2 sigma": lambda r: shape_var(r, r.jpl, 2.0) if r.jpl else float("nan"),
}


def total(rows: list[Row], per_row: Callable[[Row], float]) -> float:
    return sum(per_row(r) for r in rows)


def matches(value: float, printed: float, half_step: float) -> bool:
    return not math.isnan(value) and abs(value - printed) <= half_step + EPS


# ---------------------------------------------------------------------------------------------
# The published totals, each as (table, label, printed mean, printed variance, how to compute).
# ---------------------------------------------------------------------------------------------

Total = tuple[str, str, float, float | None, Callable[[Callable[[Row], float]], float]]


def published_totals() -> list[Total]:
    up_pt = lambda c: total(UPLINK_SUMMED, c)                                    # noqa: E731
    dn_pt = lambda c: total(DOWNLINK_SUMMED, c)                                  # noqa: E731
    dn_carr = lambda c: dn_pt(c) + c(DOWNLINK_14) + c(DOWNLINK_15)               # noqa: E731
    tlm_21 = lambda c: dn_pt(c) + c(DOWNLINK_14) + c(TLM_20)                     # noqa: E731
    tlm_22 = lambda c: tlm_21(c) - c(TLM_19) - c(DOWNLINK_N0)                    # noqa: E731
    return [
        ("5-2", "12 Rcvd Power Pt, dBm", -127.4, 0.16, up_pt),
        ("5-2", "13 Rcvd Pt/N0, dB-Hz", 39.2, 0.16, lambda c: up_pt(c) - c(UPLINK_N0)),
        ("5-2", "16 Carr Pwr/Tot Pwr, dB", 0.0, 0.00, lambda c: c(UPLINK_14) - c(UPLINK_15)),
        ("5-2", "17 Rcvd Carr Pwr, dBm", -127.4, 0.16,
         lambda c: up_pt(c) + c(UPLINK_14) - c(UPLINK_15)),
        ("5-2", "18 Carr SNR in 2BLO, dB", 26.5, 0.17,
         lambda c: up_pt(c) + c(UPLINK_14) - c(UPLINK_15) - c(UPLINK_N0) - c(UPLINK_BW)),
        ("5-3", " 1 RF Power to Antenna, dBm", 40.9, 0.04,
         lambda c: c(DOWNLINK_SUMMED[0]) + c(DOWNLINK_SUMMED[1])),
        ("5-3", "12 Rcvd Power Pt, dBm", -145.5, 0.19, dn_pt),
        ("5-3", "13 Rcvd Pt/N0, dB-Hz", 39.9, 0.28, lambda c: dn_pt(c) - c(DOWNLINK_N0)),
        ("5-3", "16 Carr Pwr/Tot Pwr, dB", -6.2, 0.00, lambda c: c(DOWNLINK_14) + c(DOWNLINK_15)),
        ("5-3", "17 Rcvd Carr Pwr, dBm", -151.7, 0.20, dn_carr),
        ("5-3", "18 Carr SNR in 2BLO, dB", 19.0, 0.31,
         lambda c: dn_carr(c) - c(DOWNLINK_N0) - c(DOWNLINK_BW)),
        ("5-4", "21 Data Pwr to Rcvr, dBm", -147.0, 0.19, tlm_21),
        ("5-4", "22 ST/N0 to Rcvr, dB", 16.4, 0.28, tlm_22),
        ("5-4", "24 (22+23), dB", 15.6, 0.29, lambda c: tlm_22(c) + c(TLM_23)),
        ("5-4", "26 Margin (24-25), dB", 13.3, 0.29,
         lambda c: tlm_22(c) + c(TLM_23) - c(TLM_25)),
    ]


def variance_of(label_fn: Callable[[Callable[[Row], float]], float], conv: VarConvention) -> float:
    """Variance of a total = sum of member variances. Signs do not matter for independent terms,
    so every row a total touches contributes its variance once, whatever its sign in the sum."""
    seen: list[Row] = []

    def collect(r: Row) -> float:
        seen.append(r)
        return 0.0

    label_fn(collect)
    return sum(conv(r) for r in dict.fromkeys(seen))


# ---------------------------------------------------------------------------------------------

def physics_checks() -> list[tuple[str, float, float, float]]:
    def space_loss(range_km: float, freq_mhz: float) -> float:
        wavelength_km = C_KM_S / (freq_mhz * 1e6)
        return -20 * math.log10(4 * math.pi * range_km / wavelength_km)

    def n0(temp_k: float) -> float:
        return 10 * math.log10(BOLTZMANN_J_K * temp_k) + 30

    rng = 7.273e9
    rng_step_db = 20 * math.log10(1 + 0.0005e9 / rng)       # 4 significant figures in "7.273+09"
    return [
        ("space loss, S-band 2113.31 MHz", space_loss(rng, 2113.31), -296.18, 0.005 + rng_step_db),
        ("space loss, X-band 8415.00 MHz", space_loss(rng, 8415.00), -308.19, 0.005 + rng_step_db),
        ("range in AU", rng / AU_KM, 48.62, 0.005 + 0.0005e9 / AU_KM),
        ("N0 from 1545.00 K", n0(1545.00), -166.71, 0.005),
        ("N0 from 21.12 K", n0(21.12), -185.35, 0.005),
        ("N0 fav tol from -34 K", 10 * math.log10(1511 / 1545), -0.10, 0.005),
        ("N0 adv tol from +59 K", 10 * math.log10(1604 / 1545), 0.16, 0.005),
        ("N0 fav tol from -4.24 K", 10 * math.log10((21.12 - 4.24) / 21.12), -0.97, 0.005),
        ("N0 adv tol from +4.24 K", 10 * math.log10((21.12 + 4.24) / 21.12), 0.80, 0.005),
        ("SNT = sum of its components", 13.20 + 2.88 + 2.68 + 2.36 + 0.00, 21.12, 0.005),
        ("10 log10(160 bps)", 10 * math.log10(160.0), 22.04, 0.005),
        ("data/total, sin^2(60 deg)",
         10 * math.log10(math.sin(math.radians(60)) ** 2), -1.25, 0.005),
        ("carrier suppression, cos^2(60 deg)",
         10 * math.log10(math.cos(math.radians(60)) ** 2), -6.02, 0.005),
    ]


def main() -> int:  # noqa: PLR0912, PLR0915 - one linear report, clearer unsplit
    print("=" * 100)
    print("Voyager 2 DCTs, DESCANSO Article 4 Tables 5-2 to 5-4 (DSS-43, 1996-01-01 00:00)")
    print("=" * 100)

    print("\n[1] Independent physics checks on the published inputs")
    for label, computed, printed, tol in physics_checks():
        ok = abs(computed - printed) <= tol + EPS
        print(f"  {'ok  ' if ok else 'MISS'} {label:38s} "
              f"computed {computed:11.4f}  printed {printed:9.2f}")

    print("\n[2] Per-row: which tolerance shape reproduces the printed mean and variance")
    for r in ALL_ROWS:
        if r.mean is None or r.var is None or r.fav is None or r.adv is None:
            continue
        if r.fav == 0 and r.adv == 0:
            continue
        cells = []
        shapes = (("uniform", 3.0), ("triangular", 3.0), ("gaussian", 2.0), ("gaussian", 3.0))
        for shape, sig in shapes:
            m, v = shape_mean(r, shape), shape_var(r, shape, sig)
            tag = shape if shape != "gaussian" else f"gauss+/-{sig:.0f}s"
            flag = ("M" if matches(m, r.mean, MEAN_HALF_STEP) else "-") + \
                   ("V" if matches(v, r.var, VAR_HALF_STEP) else "-")
            cells.append(f"{tag}:{flag}")
        print(f"  {r.key:>3} {r.name:36s} printed {r.mean:8.2f}/{r.var:4.2f}  "
              f"jpl={r.jpl or '?':13s} "
              + "  ".join(cells))
    blanks = [f"{r.key} {r.name}" for r in ALL_ROWS if r.design is not None and r.mean is None]
    print(f"  rows printed with NO mean/variance: {blanks}")

    totals = published_totals()
    print("\n[3] Published dB totals against every declared mean convention (M = within 0.05 dB)")
    header = "  " + f"{'table':5s} {'total':30s} {'printed':>8s}  " + "  ".join(
        f"{name[:18]:>18s}" for name in MEAN_CONVENTIONS)
    print(header)
    score = dict.fromkeys(MEAN_CONVENTIONS, 0)
    evaluated = dict.fromkeys(MEAN_CONVENTIONS, 0)
    for table, label, printed, _pvar, fn in totals:
        cells = []
        for name, conv in MEAN_CONVENTIONS.items():
            if name.startswith("JPL") and table == "5-2":
                cells.append(f"{'n/a (no Table 2a)':>18s}")
                continue
            value = fn(conv)
            ok = matches(value, printed, MEAN_HALF_STEP)
            evaluated[name] += 1
            score[name] += ok
            cells.append(f"{value:14.3f} {'M ' if ok else 'xx'} ")
        print(f"  {table:5s} {label:30s} {printed:8.1f}  " + "  ".join(cells))

    print("\n[4] Published variances against every declared variance convention (V = within 0.005)")
    for table, label, _printed, pvar, fn in totals:
        if pvar is None:
            continue
        cells = []
        for name, conv in VAR_CONVENTIONS.items():
            if name.startswith("JPL") and table == "5-2":
                cells.append(f"{name[:26]:>26s}=n/a")
                continue
            value = variance_of(fn, conv)
            flag = "V" if matches(value, pvar, VAR_HALF_STEP) else "x"
            cells.append(f"{name[:26]:>26s}={value:6.3f}{flag}")
        print(f"  {table:5s} {label:30s} printed {pvar:4.2f} | " + " ".join(cells))

    print("\n[5] The printed 2-sigma lines, against 2*sqrt(variance) of the row they sit under")
    for table, row_label, printed_2s in (("5-2", "18 Carr SNR in 2BLO, dB", 0.80),
                                         ("5-3", "18 Carr SNR in 2BLO, dB", 1.10),
                                         ("5-4", "26 Margin (24-25), dB", 1.10)):
        fn = next(f for t, lab, _m, _v, f in totals if t == table and lab.strip() == row_label)
        pvar = next(v for t, lab, _m, v, _f in totals if t == table and lab.strip() == row_label)
        from_printed = 2 * math.sqrt(pvar)
        cells = [f"from printed var {pvar:.2f} -> {from_printed:.3f}"]
        for name, conv in VAR_CONVENTIONS.items():
            if name.startswith("JPL") and table == "5-2":
                continue
            cells.append(f"{name[:22]} -> {2 * math.sqrt(variance_of(fn, conv)):.3f}")
        print(f"  {table} {row_label:26s} printed 2.0S = {printed_2s:.2f} | " + " | ".join(cells))

    print("\n[GATE] a single declared convention must reproduce every published dB total to 0.1 dB")
    passing = []
    for name in MEAN_CONVENTIONS:
        n = evaluated[name]
        whole = "all tables" if not name.startswith("JPL") else "Tables 5-3, 5-4 only"
        print(f"  {name:30s} {score[name]:2d} / {n:2d}   ({whole})")
        if n and score[name] == n and not name.startswith("JPL"):
            passing.append(name)
    if passing:
        print(f"\nGATE: REPRODUCED under {passing}")
        return 0
    print("\nGATE: NOT REPRODUCED by any single declared convention across all three tables. "
          "See [2]-[4] for the rows responsible.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
