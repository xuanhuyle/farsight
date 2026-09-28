"""The Pioneer reproduction is judged against a pre-registration, so the two must not drift.

`experiments/pioneer_thermal/reproduce_thermal_acceleration.py` rebuilds arXiv:1103.5222 and
decides PASS or FAIL against targets fixed in `PREREGISTRATION.md` before the script existed. Two
kinds of failure would be invisible without these tests: the gate numbers in the code quietly
diverging from the numbers in the document, and the model silently computing nothing -- an empty
sample array, a table that never got transcribed -- while still printing a verdict.

The rebuilt values are pinned to four decimals. That is not a tolerance on the physics; it locks
the recorded result, so that a later edit which changes any scenario has to say so out loud.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
PIONEER = REPO / "experiments" / "pioneer_thermal"
PREREGISTRATION = PIONEER / "PREREGISTRATION.md"


def _model():
    spec = importlib.util.spec_from_file_location(
        "reproduce_thermal_acceleration", PIONEER / "reproduce_thermal_acceleration.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def _preregistration_text() -> str:
    text = PREREGISTRATION.read_text(encoding="utf-8")
    assert len(text) > 2000, f"pre-registration is implausibly short: {len(text)} bytes"
    return text


# The values the script must reproduce, and what it actually produces. Recorded 2026-09-28 from
# the first run, under seed 20260928.
REBUILT = {1: 2.2721, 2: 4.4341, 3: 5.7115, 4: 5.6881, 5: 6.9166}


def test_the_published_targets_match_the_preregistration():
    """The five Table 3 values in the code are the five in the document."""
    model = _model()
    row = re.search(
        r"\| a_th \(10.*?\) \|(.+?)\|\s*$", _preregistration_text(), re.MULTILINE
    )
    assert row, "the pre-registration's Gate 1 table row was not found"
    documented = [float(cell) for cell in row.group(1).split("|") if cell.strip()]
    assert documented == [s.published_a_th for s in model.SCENARIOS]
    assert len(documented) == 5


def test_the_gate_tolerances_match_the_preregistration():
    """A tolerance loosened in code but not in the document would pass a failing result."""
    model = _model()
    text = _preregistration_text()
    assert "±0.005" in text and model.GATE1_TOLERANCE == 0.005
    assert "±0.05" in text and model.GATE2_TOLERANCE == 0.05
    assert "5.8" in text and model.GATE2_CENTRAL == 5.8
    assert "1.3" in text and model.GATE2_HALF_WIDTH == 1.3


def test_every_scenario_reproduces_the_value_on_record():
    """Four match the paper; the fifth misses by 0.21 and that miss is the finding."""
    model = _model()
    passed, rows = model.gate_1()
    assert not passed, "Gate 1 passing would contradict the recorded result -- re-read RESULT.md"
    for scenario, computed, residual in rows:
        assert computed == pytest.approx(REBUILT[scenario.number], abs=5e-5)
        matched = abs(residual) <= model.GATE1_TOLERANCE
        assert matched is (scenario.number != 5)


def test_the_transcription_check_refuses_a_table_that_does_not_add_up():
    """A typo in the transcription would look exactly like a failed reproduction."""
    model = _model()
    assert model._check_the_transcription() == []

    broken = model.SCENARIOS[1]
    mistyped = model.Scenario(
        broken.number, broken.label, broken.w_rtgb, broken.w_front + 5.0,
        broken.w_lat, broken.w_back, broken.kd_ant, broken.ks_ant,
        broken.ks_lat, broken.published_a_th,
    )
    model.SCENARIOS = (*model.SCENARIOS[:1], mistyped, *model.SCENARIOS[2:])
    problems = model._check_the_transcription()
    assert any("surface powers sum to" in problem for problem in problems)


def test_the_transcription_check_refuses_a_missing_table():
    model = _model()
    model.SCENARIOS = ()
    assert any("expected 5 scenarios" in problem for problem in model._check_the_transcription())


def test_the_monte_carlo_repeats_under_its_seed():
    """A result whose number moves between runs cannot be checked by a reader."""
    model = _model()
    kwargs = {"iterations": 500, "w_rtgb_mean": 143.86, "w_equip": 56.0,
              "w_front_mean": 40.0, "w_front_sigma": 7.5}
    first = model.sample_accelerations(np.random.default_rng(20260928), **kwargs)
    again = model.sample_accelerations(np.random.default_rng(20260928), **kwargs)
    other = model.sample_accelerations(np.random.default_rng(1), **kwargs)
    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)
    assert first.size == 500


def test_a_zero_iteration_run_is_refused_rather_than_silently_empty():
    """Zero samples would summarise to nan and print a verdict anyway."""
    model = _model()
    with pytest.raises(ValueError):
        model.sample_accelerations(np.random.default_rng(0), 0, 143.86, 56.0, 40.0, 7.5)


def test_the_force_terms_carry_the_signs_the_paper_states():
    """Eq. (14)'s own-emission term is sunward-negative; Eq. (10)'s is positive."""
    model = _model()
    zero = model.axial_force_terms(w_rtgb=0.0, w_front=0.0, w_lat=0.0, w_back=0.0,
                                   kd_ant=0.0, ks_ant=0.0, ks_lat=0.0)
    assert all(value == 0.0 for value in zero.values())

    unreflected = model.axial_force_terms(w_rtgb=100.0, w_front=100.0, w_lat=100.0,
                                          w_back=100.0, kd_ant=0.0, ks_ant=0.0, ks_lat=0.0)
    assert unreflected["F4"] > 0            # front wall, straight into space
    assert unreflected["F3"] < 0            # back wall, emission beats the dish shadow
    assert unreflected["F22"] < 0           # RTG base on the compartment walls
    assert unreflected["F11"] > 0           # the dish shadow is itself sunward


def test_the_sensitivity_report_returns_the_printed_values_when_nothing_is_missing():
    """With no shortfall, every 'would have to be' equals what the paper prints -- otherwise the
    report would invent a discrepancy wherever it was pointed."""
    model = _model()
    scenario = model.SCENARIOS[0]
    exact = model.Scenario(
        scenario.number, scenario.label, scenario.w_rtgb, scenario.w_front,
        scenario.w_lat, scenario.w_back, scenario.kd_ant, scenario.ks_ant,
        scenario.ks_lat, model.thermal_acceleration(**scenario.inputs()) / 1e-10,
    )
    for _, (required, printed) in model.what_would_close(exact).items():
        assert required == pytest.approx(printed, rel=1e-9)


def test_the_interval_bounds_enclose_the_monte_carlo():
    """Worst-corner interval arithmetic must not produce a narrower range than sampling."""
    model = _model()
    low, high = model.interval_bounds()
    samples = model.sample_accelerations(
        np.random.default_rng(20260928), 2000, 143.86, 56.0, 40.0, 7.5
    )
    stats = model.summarise(samples)
    assert low < stats["p2p5"]
    assert high > stats["p97p5"]


def test_the_rtg_base_share_is_one_fourteenth_of_its_area():
    """The paper gives W_RTGb without a formula. For a cylinder of diameter 200 mm and length
    600 mm the inward-facing base is exactly 1/14 of the emitting area, which is what makes the
    reconstruction checkable rather than a coincidence of rounding."""
    model = _model()
    power, fraction = model.rtgb_from_geometry(model.W_RTG_T26)
    assert fraction == pytest.approx(1 / 14, rel=1e-12)
    assert power == pytest.approx(144.571, abs=0.005)
