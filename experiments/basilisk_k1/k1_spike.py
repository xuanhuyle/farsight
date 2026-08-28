"""K1 spike: is a seeded Basilisk run bitwise reproducible, and can we intervene mid-run?

Plan §21 K1: a seeded Basilisk scenario reruns bitwise-identically within 3 dev-days of the
spike starting. Failing that, Basilisk is descoped from the MVP demo.

This is information-gathering, timeboxed, and it deliberately answers the three questions the
ADRs already committed to in prose *before* anyone had run the engine:

  Q1 (ADR-002, ADR-006)  Two identical runs in one process -> bitwise-identical channel bytes?
                         Tier-A replay is the product's foundational claim; if the engine
                         cannot do it, the claim does not survive contact with the engine.
  Q2 (ADR-005)           Do per-module `RNGSeed` attributes actually control the draws, so that
                         two runs with different seeds differ and the same seed reproduces?
  Q3 (ADR-003, ADR-010)  Can we stop at a boundary, mutate a module attribute, and continue --
                         the `native` fault-lowering mode the whole fault model rests on?
                         And is a zero-magnitude mutation byte-transparent (AT-10), which is
                         what makes the paired-counterfactual causal claim arithmetic?

Run this with a Python that has `bsk` installed. It writes nothing and imports no FarSight
code, so it can be run standalone against any Basilisk version.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys

import numpy as np


def arr_hash(a: np.ndarray) -> str:
    """Canonical hash of a channel array, per ADR-011: header over the raw C-order payload.

    Deliberately mirrors the production rule rather than hashing whatever NumPy happens to
    produce, so that what the spike measures is what the platform will later claim.
    """
    header = f"{a.dtype.str}|{a.shape}".encode()
    return hashlib.sha256(header + b"\x00" + np.ascontiguousarray(a, dtype="<f8").tobytes()).hexdigest()


def build_sim(seed: int, noise_scale: float = 1.0):
    """A minimal seeded scenario: one spacecraft plus a noisy navigation sensor.

    `simpleNav` is used rather than a sun sensor because it needs only the spacecraft state
    wired in, and it carries exactly the two surfaces the questions are about: an `RNGSeed` and
    a noise covariance (`PMatrix`) that can be mutated live. Fidelity is beside the point --
    what is under test is the engine's determinism and intervention behaviour, not orbits.
    """
    from Basilisk.simulation import simpleNav, spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros

    sim = SimulationBaseClass.SimBaseClass()
    proc = sim.CreateNewProcess("dyn")
    proc.addTask(sim.CreateNewTask("dynTask", macros.sec2nano(1.0)))

    sc = spacecraft.Spacecraft()
    sc.ModelTag = "sc"
    sc.hub.mHub = 750.0
    sc.hub.r_CN_NInit = [[7000e3], [0.0], [0.0]]
    sc.hub.v_CN_NInit = [[0.0], [7.5e3], [0.0]]
    sim.AddModelToTask("dynTask", sc)

    nav = simpleNav.SimpleNav()
    nav.ModelTag = "nav"
    # Diagonal position/velocity noise. `noise_scale` is the mid-run mutation handle and is
    # the analogue of the plan's "sensor noise doubles" fault.
    pmat = [[0.0] * 18 for _ in range(18)]
    for i in range(6):
        pmat[i][i] = 10.0 * noise_scale
    nav.PMatrix = pmat
    # Bounds must sit outside 3 sigma, or Basilisk truncates the distribution and warns. At
    # sigma ~64 m, 500 m clears it. Left at 100 m the spike still passes every determinism
    # check -- truncated noise is just as deterministic -- but it would be exercising a
    # bound-limited regime rather than the Gauss-Markov one, which is not what we meant to test.
    nav.walkBounds = [[500.0]] * 18
    nav.RNGSeed = seed
    nav.scStateInMsg.subscribeTo(sc.scStateOutMsg)
    sim.AddModelToTask("dynTask", nav)

    rec_truth = sc.scStateOutMsg.recorder()
    rec_nav = nav.transOutMsg.recorder()
    sim.AddModelToTask("dynTask", rec_truth)
    sim.AddModelToTask("dynTask", rec_nav)

    return sim, sc, nav, rec_truth, rec_nav


def run_plain(seed: int, stop_s: float = 200.0) -> dict[str, str]:
    from Basilisk.utilities import macros

    sim, _sc, _nav, rec_truth, rec_nav = build_sim(seed)
    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(stop_s))
    sim.ExecuteSimulation()
    return {
        "truth": arr_hash(np.array(rec_truth.r_BN_N)),
        "nav": arr_hash(np.array(rec_nav.r_BN_N)),
    }


def run_segmented(seed: int, mutate_to: float | None, stop_s: float = 200.0) -> dict[str, str]:
    """Run in two segments, optionally mutating a module attribute at the boundary.

    This is ADR-003's `native` fault-lowering mode in miniature: stop at a boundary, reach into
    a live module, continue. `mutate_to=None` is the control -- same segmentation, no mutation --
    which is what isolates "did segmenting change the answer" from "did the mutation".
    """
    from Basilisk.utilities import macros

    sim, _sc, nav, rec_truth, rec_nav = build_sim(seed)
    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(stop_s / 2))
    sim.ExecuteSimulation()

    if mutate_to is not None:  # the intervention: reach into a live module and rebind
        pmat = [[0.0] * 18 for _ in range(18)]
        for i in range(6):
            pmat[i][i] = 10.0 * mutate_to
        nav.PMatrix = pmat

    sim.ConfigureStopTime(macros.sec2nano(stop_s))
    sim.ExecuteSimulation()
    return {
        "truth": arr_hash(np.array(rec_truth.r_BN_N)),
        "nav": arr_hash(np.array(rec_nav.r_BN_N)),
    }


def main() -> int:
    import Basilisk

    print("=" * 78)
    print("K1 SPIKE -- Basilisk determinism and mid-run intervention")
    print("=" * 78)
    print(f"  Basilisk : {getattr(Basilisk, '__version__', 'unknown')}")
    print(f"  Python   : {sys.version.split()[0]}")
    print(f"  Platform : {platform.platform()}")
    print(f"  NumPy    : {np.__version__}")

    results: dict[str, bool] = {}

    print("\n" + "-" * 78)
    print("Q0  Is the noise real? (guards against every later check passing vacuously)")
    print("-" * 78)
    rms = noise_rms(1234)
    print(f"  RMS(nav - truth) = {rms:.3f} m")
    results["q0_noise_is_real"] = rms > 1.0

    print("\n" + "-" * 78)
    print("Q1  Two identical seeded runs -> bitwise identical? (Tier-A prerequisite)")
    print("-" * 78)
    a, b = run_plain(1234), run_plain(1234)
    for ch in a:
        same = a[ch] == b[ch]
        print(f"  {ch:10s} {'IDENTICAL' if same else 'DIFFERS'}   {a[ch][:16]}")
        results[f"q1_{ch}"] = same

    print("\n" + "-" * 78)
    print("Q2  Does RNGSeed actually control the stochastic module?")
    print("-" * 78)
    c = run_plain(9999)
    differs = a["nav"] != c["nav"]
    print(f"  seed 1234 vs 9999 nav:   {'DIFFERS (seed bites)' if differs else 'IDENTICAL (seed inert!)'}")
    print(f"  seed 1234 vs 9999 truth: "
          f"{'differs' if a['truth'] != c['truth'] else 'identical (expected: dynamics carry no noise)'}")
    results["q2_seed_controls"] = differs

    print("\n" + "-" * 78)
    print("Q3a Segmenting a run without mutating -> same as one continuous run?")
    print("-" * 78)
    seg = run_segmented(1234, mutate_to=None)
    for ch in a:
        same = a[ch] == seg[ch]
        print(f"  {ch:10s} {'IDENTICAL' if same else 'DIFFERS'}")
        results[f"q3a_{ch}"] = same

    print("\n" + "-" * 78)
    print("Q3b Zero-magnitude mutation -> byte-transparent? (AT-10)")
    print("-" * 78)
    zero = run_segmented(1234, mutate_to=1.0)  # rebind the identical value
    for ch in a:
        same = seg[ch] == zero[ch]
        print(f"  {ch:10s} {'IDENTICAL' if same else 'DIFFERS'}")
        results[f"q3b_{ch}"] = same

    print("\n" + "-" * 78)
    print("Q3c Real mutation -> does it change the outcome at all?")
    print("-" * 78)
    mutated = run_segmented(1234, mutate_to=25.0)
    changed = mutated["nav"] != seg["nav"]
    print(f"  nav after 25x noise increase: {'CHANGED (intervention works)' if changed else 'UNCHANGED (inert!)'}")
    results["q3c_mutation_effective"] = changed

    print("\n" + "-" * 78)
    print("Q4  Determinism ACROSS processes (ADR-002's actual production condition)")
    print("-" * 78)
    child = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--emit"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": "99"},
        check=True,
    ).stdout.strip().splitlines()
    child_hashes = dict(line.split("=", 1) for line in child if "=" in line)
    for ch in a:
        same = a[ch] == child_hashes.get(ch)
        print(f"  {ch:10s} {'IDENTICAL' if same else 'DIFFERS'}  (fresh process, PYTHONHASHSEED=99)")
        results[f"q4_{ch}"] = same

    print("\n" + "=" * 78)
    print("K1 VERDICT")
    print("=" * 78)
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    ok = all(results.values())
    print(f"\n  K1: {'PASS -- Basilisk stays in the MVP' if ok else 'ATTENTION -- see failures above'}")
    return 0 if ok else 1


def noise_rms(seed: int, stop_s: float = 200.0) -> float:
    """RMS of (nav - truth). If this is ~0 the sensor is not noising and every other check
    below would pass for the wrong reason."""
    from Basilisk.utilities import macros

    sim, _sc, _nav, rec_truth, rec_nav = build_sim(seed)
    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(stop_s))
    sim.ExecuteSimulation()
    resid = np.array(rec_nav.r_BN_N) - np.array(rec_truth.r_BN_N)
    return float(np.sqrt((resid**2).mean()))


if __name__ == "__main__":
    if "--emit" in sys.argv:  # child mode for the cross-process check
        for k, v in run_plain(1234).items():
            print(f"{k}={v}")
        sys.exit(0)
    sys.exit(main())
