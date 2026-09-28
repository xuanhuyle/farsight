"""Rebuild the published point-source thermal acceleration of the Pioneer probes.

Source: F. Francisco, O. Bertolami, P. J. S. Gil, J. Paramos, "Modelling the
reflective thermal contribution to the acceleration of the Pioneer spacecraft",
Physics Letters B 711 (2012) 337-346, arXiv:1103.5222.

Every coefficient and every input below is printed in that paper. Nothing here is
fitted, tuned, or carried over from a previous run. The targets this is judged
against were fixed in PREREGISTRATION.md before this file existed.

What this reproduces is the paper's arithmetic and its Monte Carlo. The paper has
already reduced its Lambertian-source and Phong-reflection integrals to the
numeric coefficients used here; re-deriving those by integration is a different
exercise and is not attempted.

Exit codes: 0 both gates pass, 1 a gate fails, 2 the script's own consistency
checks fail.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import numpy as np

# Speed of light, exact by SI definition. The paper writes only "c".
C_LIGHT = 299792458.0
# 2012 Eq. (15): 259 kg at launch less part of 36 kg of hydrazine.
M_PIO = 230.0

# 2012 Eq. (16). The prose of section 3.4 gives the Pu-238 half-life as 87.74
# years while this equation uses 87.72. The equation governs, because it is what
# the paper computes with; the difference is reported, not silently resolved.
RTG_HALF_LIFE_EQ16_YR = 87.72
RTG_HALF_LIFE_PROSE_YR = 87.74
RTG_POWER_AT_LAUNCH_W = 2580.0
EQUIP_HALF_LIFE_YR = 24.0          # 2012 Eq. (17)
EQUIP_POWER_AT_LAUNCH_W = 120.0    # 2012 Eq. (17)
RADIO_BEAM_W = 20.0                # 2012 sections 3.4 and 4.1

# Late-mission epoch, t = 26 yr (Pioneer 10, 1998), 2012 section 4.1.
W_TOTAL_T26 = 2100.0
W_EQUIP_T26 = 56.0
W_RTG_T26 = 2024.0

# The measured anomaly, for the reported fraction only. Anderson et al.,
# Phys. Rev. D 65 082004 (2002). An input here, never an output.
A_PIONEER = 8.74e-10
A_PIONEER_UNCERTAINTY = 1.33e-10


def axial_force_terms(
    w_rtgb: float,
    w_front: float,
    w_lat: float,
    w_back: float,
    kd_ant: float,
    ks_ant: float,
    ks_lat: float,
) -> dict[str, float]:
    """The five z-axis force contributions of 2012 Eqs. (10)-(14), in newtons.

    Positive is sunward. Radial components cancel over a spin revolution, which
    is why only the axis appears.
    """
    return {
        # Eq. (11): lateral compartment walls, shadow on the dish plus reflection.
        "F11": (w_lat / C_LIGHT) * (0.0738 + 0.0537 * kd_ant + 0.0089 * ks_ant),
        # Eq. (12): RTG base facing the spacecraft, reflected by the dish.
        "F21": (w_rtgb / C_LIGHT) * (0.0283 + 0.0478 * kd_ant + 0.0502 * ks_ant),
        # Eq. (13): the same emission reflected by the compartment's own walls.
        "F22": (w_rtgb / C_LIGHT) * (-0.0016 + 0.0013 * ks_lat),
        # Eq. (14): back wall. -2/3 is its own emission, +0.5872 the dish shadow.
        "F3": (w_back / C_LIGHT)
        * (-2.0 / 3.0 + 0.5872 + 0.5040 * kd_ant + 0.3479 * ks_ant),
        # Eq. (10): front wall and louvers, radiating straight into space.
        "F4": (2.0 / 3.0) * (w_front / C_LIGHT),
    }


def thermal_acceleration(**inputs: float) -> float:
    """2012 Eq. (15): the five contributions over the spacecraft mass, m/s^2."""
    return sum(axial_force_terms(**inputs).values()) / M_PIO


@dataclass(frozen=True)
class Scenario:
    """One row of 2012 Table 3, transcribed with its published result."""

    number: int
    label: str
    w_rtgb: float
    w_front: float
    w_lat: float
    w_back: float
    kd_ant: float
    ks_ant: float
    ks_lat: float
    published_a_th: float  # in 1e-10 m/s^2, as printed

    def inputs(self) -> dict[str, float]:
        return {
            "w_rtgb": self.w_rtgb,
            "w_front": self.w_front,
            "w_lat": self.w_lat,
            "w_back": self.w_back,
            "kd_ant": self.kd_ant,
            "ks_ant": self.ks_ant,
            "ks_lat": self.ks_lat,
        }


# 2012 Table 3, with the scenario descriptions of sections 4.1.1 to 4.1.5.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario(1, "lower bound, uniform temperature",
             143.86, 17.5, 21.0, 17.5, 0.0, 0.0, 0.0, 2.27),
    Scenario(2, "higher emission from the louvers",
             143.86, 40.0, 8.73, 7.27, 0.0, 0.0, 0.0, 4.43),
    Scenario(3, "diffusive reflection in the antenna",
             143.86, 40.0, 8.73, 7.27, 0.8, 0.0, 0.0, 5.71),
    Scenario(4, "diffusive and specular reflection",
             143.86, 40.0, 8.73, 7.27, 0.6, 0.2, 0.4, 5.69),
    Scenario(5, "upper bound",
             158.24, 56.0, 0.0, 0.0, 0.8, 0.0, 0.4, 6.71),
)

GATE1_TOLERANCE = 0.005   # in 1e-10 m/s^2, PREREGISTRATION.md
GATE2_TOLERANCE = 0.05    # in 1e-10 m/s^2, PREREGISTRATION.md
GATE2_CENTRAL = 5.8       # 2012 Eq. (20)
GATE2_HALF_WIDTH = 1.3    # 2012 Eq. (20)

# Scenario 4 is the Monte Carlo reference (2012 section 4.2). Its split of the
# non-louvre equipment power is reused when W_front is sampled.
_S4 = SCENARIOS[3]
NON_LOUVRE_W_T26 = W_EQUIP_T26 - _S4.w_front
LATERAL_SHARE = _S4.w_lat / NON_LOUVRE_W_T26


def _check_the_transcription() -> list[str]:
    """Refuse to run on a table that does not add up.

    A silent typo in the transcription would look exactly like a failed
    reproduction, so the table is checked against its own stated relations
    before any result is computed.
    """
    problems = []
    if len(SCENARIOS) != 5:
        # Stop here: the checks below index into the table by position, and a
        # crash would be a worse answer than the problem it was asked about.
        return [f"expected 5 scenarios, have {len(SCENARIOS)}"]
    if abs(W_EQUIP_T26 + W_RTG_T26 + RADIO_BEAM_W - W_TOTAL_T26) > 1e-9:
        problems.append("t=26 power budget does not sum to the stated total")
    for scenario in SCENARIOS[1:4]:
        total = scenario.w_front + scenario.w_lat + scenario.w_back
        if abs(total - W_EQUIP_T26) > 5e-3:
            problems.append(
                f"scenario {scenario.number} surface powers sum to {total}, "
                f"not {W_EQUIP_T26}"
            )
    if abs(SCENARIOS[4].w_rtgb / SCENARIOS[0].w_rtgb - 1.1) > 1e-3:
        problems.append("scenario 5 W_RTGb is not the stated 10% above the rest")
    if not 0.0 < LATERAL_SHARE < 1.0:
        problems.append(f"lateral share out of range: {LATERAL_SHARE}")
    return problems


def gate_1() -> tuple[bool, list[tuple[Scenario, float, float]]]:
    """The five scenario accelerations of 2012 Table 3."""
    rows = []
    for scenario in SCENARIOS:
        computed = thermal_acceleration(**scenario.inputs()) / 1e-10
        rows.append((scenario, computed, computed - scenario.published_a_th))
    passed = all(abs(residual) <= GATE1_TOLERANCE for _, _, residual in rows)
    return passed, rows


def sample_accelerations(
    rng: np.random.Generator,
    iterations: int,
    w_rtgb_mean: float,
    w_equip: float,
    w_front_mean: float,
    w_front_sigma: float,
) -> np.ndarray:
    """The Monte Carlo of 2012 section 4.2, at one epoch.

    W_RTGb normal at 25% of its mean; W_front normal; the rest of the equipment
    power conserved and split in Scenario 4's proportion; k_d,ant uniform on
    [0.6, 0.8] with k_s,ant = 0.8 - k_d,ant, the constraint the paper imposes.
    """
    if iterations < 1:
        raise ValueError(f"iterations must be positive, got {iterations}")
    w_rtgb = rng.normal(w_rtgb_mean, 0.25 * w_rtgb_mean, iterations)
    w_front = rng.normal(w_front_mean, w_front_sigma, iterations)
    remainder = w_equip - w_front
    kd_ant = rng.uniform(0.6, 0.8, iterations)
    samples = np.array(
        [
            sum(
                axial_force_terms(
                    w_rtgb=w_rtgb[i],
                    w_front=w_front[i],
                    w_lat=remainder[i] * LATERAL_SHARE,
                    w_back=remainder[i] * (1.0 - LATERAL_SHARE),
                    kd_ant=kd_ant[i],
                    ks_ant=0.8 - kd_ant[i],
                    ks_lat=_S4.ks_lat,
                ).values()
            )
            / M_PIO
            for i in range(iterations)
        ]
    )
    if samples.size != iterations:
        raise RuntimeError(f"asked for {iterations} samples, got {samples.size}")
    return samples


def summarise(samples: np.ndarray) -> dict[str, float]:
    """Both readings of "95%", because the paper does not say which it used."""
    scaled = samples / 1e-10
    lo, hi = np.percentile(scaled, [2.5, 97.5])
    return {
        "mean": float(scaled.mean()),
        "median": float(np.median(scaled)),
        "sigma": float(scaled.std(ddof=1)),
        "half_width_1p96_sigma": float(1.96 * scaled.std(ddof=1)),
        "half_width_percentile": float((hi - lo) / 2.0),
        "p2p5": float(lo),
        "p97p5": float(hi),
    }


def rtg_thermal_power(t_years: float, half_life: float) -> float:
    """2012 Eq. (16), total RTG thermal power at t years after launch."""
    return RTG_POWER_AT_LAUNCH_W * math.exp(-t_years * math.log(2.0) / half_life)


def equipment_power(t_years: float) -> float:
    """2012 Eq. (17), compartment electrical power at t years after launch."""
    return EQUIP_POWER_AT_LAUNCH_W * math.exp(
        -t_years * math.log(2.0) / EQUIP_HALF_LIFE_YR
    )


# RTG cylinder. Fig. 1 gives a diameter of 200 mm; Table 2 puts its two
# Lambertian sources at x = 2.5 m and x = 3.1 m, which fixes the length at 600 mm.
RTG_DIAMETER_M = 0.200
RTG_LENGTH_M = 0.600


def rtgb_from_geometry(w_rtg: float) -> tuple[float, float]:
    """Rebuild W_RTGb, the one input the paper gives without a formula.

    Each RTG radiates from two bases and a side; only the base facing the
    spacecraft illuminates anything. Splitting the RTG thermal power by area
    gives the inward-facing share. Returns the power and the area fraction.
    """
    base = math.pi * (RTG_DIAMETER_M / 2.0) ** 2
    side = math.pi * RTG_DIAMETER_M * RTG_LENGTH_M
    fraction = base / (2.0 * base + side)
    # Both RTGs: each contributes its own base out of its own total area, so the
    # halving of the power and the doubling of the count cancel.
    return w_rtg * fraction, fraction


def interval_bounds() -> tuple[float, float]:
    """The same unknowns carried as intervals and combined at the worst corner.

    Reported, not gating. Each input enters linearly, so the extremes lie at the
    corners. The ranges are the paper's own: W_RTGb at plus or minus two standard
    deviations, W_front likewise, k_d,ant across [0.6, 0.8] under the constraint.
    """
    w_rtgb_range = (143.86 * 0.5, 143.86 * 1.5)          # mean +/- 2 * 25%
    w_front_range = (40.0 - 2 * 7.5, 40.0 + 2 * 7.5)     # mean +/- 2 * 7.5 W
    kd_range = (0.6, 0.8)
    values = []
    for w_rtgb in w_rtgb_range:
        for w_front in w_front_range:
            for kd_ant in kd_range:
                remainder = W_EQUIP_T26 - w_front
                values.append(
                    thermal_acceleration(
                        w_rtgb=w_rtgb,
                        w_front=w_front,
                        w_lat=remainder * LATERAL_SHARE,
                        w_back=remainder * (1.0 - LATERAL_SHARE),
                        kd_ant=kd_ant,
                        ks_ant=0.8 - kd_ant,
                        ks_lat=_S4.ks_lat,
                    )
                    / 1e-10
                )
    return min(values), max(values)


def what_would_close(scenario: Scenario) -> dict[str, float]:
    """For a scenario that misses, what each single input would have to be.

    This is a sensitivity report, not a fit: none of these values is adopted,
    and the reproduction keeps the inputs the paper prints. Its purpose is to
    say whether some plausible stated quantity accounts for the gap, or whether
    nothing does. Each input enters the force linearly, so each is solved
    directly rather than searched.
    """
    target_force = scenario.published_a_th * 1e-10 * M_PIO
    terms = axial_force_terms(**scenario.inputs())
    computed_force = sum(terms.values())
    shortfall = computed_force - target_force

    inputs = scenario.inputs()
    rtgb_per_watt = (terms["F21"] + terms["F22"]) / inputs["w_rtgb"]
    return {
        # Mass: the one input that scales the whole sum.
        "m_Pio (kg)": (
            computed_force / (scenario.published_a_th * 1e-10), M_PIO
        ),
        # W_RTGb: carries F21 and F22, both linear in it.
        "W_RTGb (W)": (
            inputs["w_rtgb"] - shortfall / rtgb_per_watt, inputs["w_rtgb"]
        ),
        # W_front: carries F4 alone.
        "W_front (W)": (
            inputs["w_front"] - shortfall / ((2.0 / 3.0) / C_LIGHT),
            inputs["w_front"],
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild arXiv:1103.5222.")
    parser.add_argument("--seed", type=int, default=20260928,
                        help="fixed so the run repeats; recorded in the result")
    parser.add_argument("--iterations", type=int, default=10_000,
                        help="10^4, the published number")
    parser.add_argument("--alternatives", action="store_true",
                        help="also print the other readings of the paper that "
                             "were tried, none of which is adopted")
    args = parser.parse_args()

    problems = _check_the_transcription()
    if problems:
        for problem in problems:
            print(f"TRANSCRIPTION ERROR: {problem}")
        return 2

    print("Pioneer thermal acceleration, rebuilt from arXiv:1103.5222")
    print(f"seed {args.seed}, {args.iterations} Monte Carlo iterations")
    print()

    print("GATE 1 - the five scenarios of Table 3 (1e-10 m/s^2)")
    header = (f"{'#':>2} {'scenario':<36} {'published':>10} {'rebuilt':>9} "
              f"{'residual':>9}  verdict")
    print(header)
    gate1_passed, rows = gate_1()
    for scenario, computed, residual in rows:
        verdict = "match" if abs(residual) <= GATE1_TOLERANCE else "MISS"
        print(f"{scenario.number:>2} {scenario.label:<36} "
              f"{scenario.published_a_th:>10.2f} {computed:>9.4f} "
              f"{residual:>+9.4f}  {verdict}")
    print(f"Gate 1: {'PASS' if gate1_passed else 'FAIL'} "
          f"(tolerance +/-{GATE1_TOLERANCE})")
    for scenario, _, residual in rows:
        if abs(residual) <= GATE1_TOLERANCE:
            continue
        print(f"  scenario {scenario.number} misses. For its published "
              f"{scenario.published_a_th} a single input would have to be:")
        for name, (required, printed) in what_would_close(scenario).items():
            print(f"    {name:<14} {required:>9.2f}   "
                  f"(the paper prints {printed:.2f})")
        print("  None of these is adopted; the paper's own values are kept.")
    print()

    rng = np.random.default_rng(args.seed)
    samples = sample_accelerations(
        rng,
        args.iterations,
        w_rtgb_mean=_S4.w_rtgb,
        w_equip=W_EQUIP_T26,
        w_front_mean=_S4.w_front,
        w_front_sigma=7.5,
    )
    stats = summarise(samples)
    central_residual = stats["mean"] - GATE2_CENTRAL
    hw_sigma_residual = stats["half_width_1p96_sigma"] - GATE2_HALF_WIDTH
    hw_pct_residual = stats["half_width_percentile"] - GATE2_HALF_WIDTH
    gate2_passed = (
        abs(central_residual) <= GATE2_TOLERANCE
        and min(abs(hw_sigma_residual), abs(hw_pct_residual)) <= GATE2_TOLERANCE
    )

    print("GATE 2 - the Monte Carlo at t = 26 yr (1e-10 m/s^2)")
    print(f"  published            {GATE2_CENTRAL} +/- {GATE2_HALF_WIDTH}")
    print(f"  rebuilt mean         {stats['mean']:.4f}  "
          f"residual {central_residual:+.4f}")
    print(f"  rebuilt median       {stats['median']:.4f}")
    print(f"  standard deviation   {stats['sigma']:.4f}")
    print(f"  half-width 1.96 s    {stats['half_width_1p96_sigma']:.4f}  "
          f"residual {hw_sigma_residual:+.4f}")
    print(f"  half-width 2.5-97.5  {stats['half_width_percentile']:.4f}  "
          f"residual {hw_pct_residual:+.4f}")
    print(f"  95% interval         [{stats['p2p5']:.3f}, {stats['p97p5']:.3f}]")
    print(f"Gate 2: {'PASS' if gate2_passed else 'FAIL'} "
          f"(tolerance +/-{GATE2_TOLERANCE})")
    print()

    report_not_gating(stats, seed=args.seed, iterations=args.iterations)

    if args.alternatives:
        print()
        print_alternative_readings(seed=args.seed, iterations=args.iterations)

    if gate1_passed and gate2_passed:
        print()
        print("REPRODUCED: both gates pass.")
        return 0
    print()
    print("NOT REPRODUCED: at least one gate missed. The residuals above name "
          "which, and no input was adjusted to close them.")
    return 1


def print_alternative_readings(seed: int, iterations: int) -> None:
    """Readings of the paper other than the plain one, tried and reported.

    Both gates miss, so the obvious question is whether some other defensible
    reading of the text closes them. These are the ones tried. None is adopted:
    the reproduction stands on the values the paper prints, and this list exists
    so the reader can see what was searched rather than take it on trust.
    """
    print("ALTERNATIVE READINGS (none adopted)")
    scenario_5 = SCENARIOS[4].inputs()
    variants = {
        "as printed": scenario_5,
        "no 10% RTG bump, W_RTGb = 143.86": {**scenario_5, "w_rtgb": 143.86},
        "k_s,lat = 0": {**scenario_5, "ks_lat": 0.0},
        "k_d,ant = 0.6, Scenario 4's value": {**scenario_5, "kd_ant": 0.6},
        "k_d,ant = 0.6 with k_s,ant = 0.2": {
            **scenario_5, "kd_ant": 0.6, "ks_ant": 0.2},
    }
    print(f"  Scenario 5, published {SCENARIOS[4].published_a_th}:")
    for label, inputs in variants.items():
        value = thermal_acceleration(**inputs) / 1e-10
        print(f"    {label:<36} {value:7.4f}  "
              f"{value - SCENARIOS[4].published_a_th:+.4f}")

    print(f"  Monte Carlo at t = 26, published {GATE2_CENTRAL} "
          f"+/- {GATE2_HALF_WIDTH}:")
    for label, kwargs in {
        "as read": {"w_rtgb_mean": _S4.w_rtgb, "w_front_mean": _S4.w_front},
        "Scenario 5's RTG mean, 158.24": {
            "w_rtgb_mean": 158.24, "w_front_mean": _S4.w_front},
        "Scenario 5's louvre power, W_front = 56": {
            "w_rtgb_mean": _S4.w_rtgb, "w_front_mean": 56.0},
    }.items():
        stats = summarise(
            sample_accelerations(
                np.random.default_rng(seed), iterations,
                w_equip=W_EQUIP_T26, w_front_sigma=7.5, **kwargs,
            )
        )
        print(f"    {label:<36} {stats['mean']:7.4f} "
              f"+/- {stats['half_width_1p96_sigma']:.4f}")


def report_not_gating(stats: dict[str, float], seed: int, iterations: int) -> None:
    """Everything PREREGISTRATION.md lists as reported rather than gating.

    None of this can turn a failed gate into a passed one; it is here because a
    reproduction that only prints its verdict says nothing about where it sits.
    """
    print("REPORTED, NOT GATING")
    low, high = interval_bounds()
    print(f"  same unknowns as intervals, worst corner: "
          f"[{low:.3f}, {high:.3f}], half-width {(high - low) / 2:.3f}")
    print(f"  Monte Carlo 95% for comparison:           "
          f"[{stats['p2p5']:.3f}, {stats['p97p5']:.3f}], "
          f"half-width {stats['half_width_percentile']:.3f}")

    # Two readings of "fraction of the anomaly". Against the central measured
    # value, the model interval alone sets the range. The published 44% to 96%
    # is only recovered by swinging the measured anomaly's own uncertainty the
    # other way at each end, which the paper does not say it does.
    print("  fraction of the anomaly:")
    print(f"    against the central {A_PIONEER / 1e-10:.2f}e-10: "
          f"{(stats['p2p5'] * 1e-10) / A_PIONEER * 100:.0f}% to "
          f"{(stats['p97p5'] * 1e-10) / A_PIONEER * 100:.0f}%")
    print(f"    with its +/-{A_PIONEER_UNCERTAINTY / 1e-10:.2f} swung against "
          f"each end: "
          f"{(stats['p2p5'] * 1e-10) / (A_PIONEER + A_PIONEER_UNCERTAINTY) * 100:.0f}% to "
          f"{(stats['p97p5'] * 1e-10) / (A_PIONEER - A_PIONEER_UNCERTAINTY) * 100:.0f}%"
          f"   (published: 44% to 96%)")

    rebuilt_rtgb, fraction = rtgb_from_geometry(W_RTG_T26)
    print(f"  W_RTGb from the stated geometry: {rebuilt_rtgb:.2f} W against the "
          f"published {_S4.w_rtgb} W ({100 * (rebuilt_rtgb / _S4.w_rtgb - 1):+.2f}%)")
    print(f"    the inward-facing base is {fraction:.6f} of an RTG's area, "
          f"which is 1/{1 / fraction:.4f}")
    print(f"    the published 143.86 W implies W_RTG = {_S4.w_rtgb / fraction:.1f} W, "
          f"against the stated {W_RTG_T26} W")

    print("  power model, Eq. (16) and Eq. (17):")
    for t_years in (0.0, 8.0, 17.0, 26.0):
        w_tot = rtg_thermal_power(t_years, RTG_HALF_LIFE_EQ16_YR)
        w_prose = rtg_thermal_power(t_years, RTG_HALF_LIFE_PROSE_YR)
        w_eq = equipment_power(t_years)
        print(f"    t={t_years:>4.0f} yr  W_tot {w_tot:>7.1f} W  "
              f"(87.74 yr gives {w_prose:>7.1f} W, "
              f"{100 * (w_prose / w_tot - 1):+.3f}%)  "
              f"W_equip {w_eq:>5.1f} W  "
              f"RTG {w_tot - w_eq - RADIO_BEAM_W:>7.1f} W")
    print(f"    stated at t=26: W_tot {W_TOTAL_T26} W, W_equip {W_EQUIP_T26} W, "
          f"W_RTG {W_RTG_T26} W")

    for t_years in (8.0, 17.0):
        w_tot = rtg_thermal_power(t_years, RTG_HALF_LIFE_EQ16_YR)
        w_equip = equipment_power(t_years)
        w_rtg = w_tot - w_equip - RADIO_BEAM_W
        # Assumption, stated because the paper does not print these splits:
        # W_RTGb scales with RTG thermal power, and the louvre share and the
        # spread on W_front scale with equipment power, both taken from t = 26.
        early = sample_accelerations(
            np.random.default_rng(seed),
            iterations,
            w_rtgb_mean=_S4.w_rtgb * w_rtg / W_RTG_T26,
            w_equip=w_equip,
            w_front_mean=_S4.w_front * w_equip / W_EQUIP_T26,
            w_front_sigma=7.5 * w_equip / W_EQUIP_T26,
        )
        early_stats = summarise(early)
        print(f"  t = {t_years:.0f} yr (inputs scaled, not published): "
              f"{early_stats['mean']:.2f} +/- "
              f"{early_stats['half_width_percentile']:.2f}")
    print("    published: 8.9 +/- 2 at t=8, 7.1 +/- 1.6 at t=17")


if __name__ == "__main__":
    raise SystemExit(main())
