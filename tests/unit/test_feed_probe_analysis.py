"""The DSN Now feed probe decides a branch of the first-project plan, so its analysis is held to its
pre-registration here rather than trusted.

`experiments/dsn_now_probe/analyze_feed_probe.py` applies `PREREGISTRATION.md`. These tests build
small synthetic archives in the exact layout `scripts/log_dsn_now.py` writes and check each outcome
the pre-registration names -- and, separately, that the thresholds in the script still equal the
thresholds in the document. A gate whose code and whose written rule could drift apart silently
would be a pre-registration in name only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / "experiments" / "dsn_now_probe"


def _analyzer():
    spec = importlib.util.spec_from_file_location("analyze_feed_probe",
                                                  PROBE / "analyze_feed_probe.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def _snapshot(ts_ms: int, dishes: list[tuple]) -> bytes:
    """dishes: (dss, elevation, [(spacecraft, band, power, active, signalType)], is_array)."""
    parts = ['<dsn><station name="cdscc" friendlyName="Canberra" timeUTC="0" timeZoneOffset="0"/>']
    for dss, elevation, signals, is_array in dishes:
        parts.append(f'<dish name="{dss}" azimuthAngle="0" elevationAngle="{elevation}" '
                     f'windSpeed="" isMSPA="false" isArray="{str(is_array).lower()}" '
                     f'isDDOR="false" activity="test">')
        for spacecraft, band, power, active, signal_type in signals:
            parts.append(f'<downSignal active="{active}" signalType="{signal_type}" '
                         f'dataRate="160" frequency="0" band="{band}" power="{power}" '
                         f'spacecraft="{spacecraft}" spacecraftID="-32"/>')
        parts.append("</dish>")
    parts.append(f"<timestamp>{ts_ms}</timestamp></dsn>")
    return "".join(parts).encode("utf-8")


def _write_archive(root: Path, snapshots: list[bytes]) -> Path:
    lines = []
    for body in snapshots:
        digest = hashlib.sha256(body).hexdigest()
        path = root / "snapshots" / digest[:2] / f"{digest}.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        ts = int(re.search(rb"<timestamp>(\d+)</timestamp>", body).group(1))
        when = dt.datetime.fromtimestamp(ts / 1000, dt.UTC).isoformat(timespec="seconds")
        lines.append(json.dumps({"attempted_at_utc": when, "sha256": digest,
                                 "bytes": len(body), "feed_timestamp_ms": ts}))
    # Binary, LF-terminated -- exactly what scripts/log_dsn_now.py writes. Text mode would write
    # CRLF on Windows and make byte comparisons disagree for a reason unrelated to the data.
    (root / "index.jsonl").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return root


def _day(date: str, power_70m: float, power_34m: float, *, spacecraft: str = "VGR2",
         count: int = 3, elevation: float = 40, band: str = "X", big: str = "DSS43",
         small: str = "DSS34", active: str = "true", is_array: bool = False) -> list[bytes]:
    base = int(dt.datetime.fromisoformat(f"{date}T12:00:00+00:00").timestamp() * 1000)
    return [
        _snapshot(base + i * 300_000, [
            (big, elevation, [(spacecraft, band, power_70m, active, "data")], is_array),
            (small, elevation, [(spacecraft, band, power_34m, active, "data")], is_array),
        ])
        for i in range(count)
    ]


def _verdict(tmp_path: Path, snapshots: list[bytes], *extra: str) -> int:
    archive = _write_archive(tmp_path, snapshots)
    return _analyzer().main(["--archive", str(archive), *extra])


DATES = ("2026-09-11", "2026-09-12", "2026-09-13")


def test_a_real_aperture_difference_passes(tmp_path):
    snaps = [s for d in DATES for s in _day(d, -154, -160)]      # 6 dB: what 70 m vs 34 m gives
    assert _verdict(tmp_path, snaps) == 0


def test_a_constant_placeholder_fails(tmp_path):
    snaps = [s for d in DATES for s in _day(d, -150, -150)]
    assert _verdict(tmp_path, snaps) == 1


def test_a_value_quantized_to_ten_db_steps_fails(tmp_path):
    snaps = [s for d in DATES for s in _day(d, -150, -160)]
    assert _verdict(tmp_path, snaps) == 1


def test_the_band_edges_are_inclusive(tmp_path):
    analyzer = _analyzer()
    pairs = [{"date": d, "in_band": analyzer.BAND_DB[0] <= diff <= analyzer.BAND_DB[1]}
             for d, diff in zip(DATES, (3.3, 9.0, 9.1), strict=True)]
    assert [p["in_band"] for p in pairs] == [True, True, False]
    # 2 of 3 inside is below the 80% requirement, rounded up to a whole pairing.
    assert analyzer.decide(pairs)[0] == analyzer.FAIL


def test_too_few_pairings_is_inconclusive_not_a_pass(tmp_path):
    snaps = [s for d in DATES[:2] for s in _day(d, -154, -160)]
    assert _verdict(tmp_path, snaps) == 3


def test_three_pairings_on_a_single_date_are_inconclusive(tmp_path):
    snaps = [s for sc in ("VGR1", "VGR2", "NHPC")
             for s in _day(DATES[0], -154, -160, spacecraft=sc)]
    assert _verdict(tmp_path, snaps) == 3


@pytest.mark.parametrize(("change", "value"), [
    ("elevation", 19),          # below the 20 degree floor
    ("band", "S"),              # X-band only
    ("active", "false"),        # inactive signals carry sentinels
    ("is_array", True),         # arrays are excluded
    ("small", "DSS24"),         # its X-band gain was not in the tables read
    ("big", "DSS15"),           # a 34 m HEF is not a 70 m antenna
])
def test_ineligible_signals_never_form_a_pairing(tmp_path, change, value):
    snaps = [s for d in DATES for s in _day(d, -154, -160, **{change: value})]
    assert _verdict(tmp_path, snaps) == 3


def test_a_feed_that_did_not_update_is_counted_once(tmp_path):
    snaps = []
    for d in DATES:
        one = _day(d, -154, -160, count=1)[0]
        snaps += [one, one, one]         # three fetches, one feed timestamp
    assert _verdict(tmp_path, snaps) == 3


def test_a_tampered_snapshot_is_refused(tmp_path):
    archive = _write_archive(tmp_path, [s for d in DATES for s in _day(d, -154, -160)])
    victim = next((archive / "snapshots").rglob("*.xml"))
    victim.write_bytes(victim.read_bytes().replace(b"-154", b"-150"))
    analyzer = _analyzer()
    with pytest.raises(analyzer.ArchiveError, match="does not hash to its own name"):
        analyzer.main(["--archive", str(archive)])


def test_the_window_is_seven_days_unless_the_single_extension_is_used(tmp_path):
    late = ("2026-09-19", "2026-09-20", "2026-09-21")       # beyond 7 days, within 14
    snaps = _day(DATES[0], -154, -160) + [s for d in late for s in _day(d, -154, -160)]
    archive = _write_archive(tmp_path, snaps)
    analyzer = _analyzer()
    assert analyzer.main(["--archive", str(archive)]) == 3
    assert analyzer.main(["--archive", str(archive), "--extended"]) == 0


def test_the_script_still_says_what_the_preregistration_says():
    """Drift between the written rule and the code that applies it is the failure to prevent."""
    analyzer = _analyzer()
    text = (PROBE / "PREREGISTRATION.md").read_text(encoding="utf-8")

    assert f"[{analyzer.BAND_DB[0]}, {analyzer.BAND_DB[1]}] dB**" in text
    assert analyzer.MIN_ELEVATION_DEG == 20.0 and "`elevationAngle` ≥ 20" in text
    assert analyzer.MIN_SNAPSHOTS_PER_DISH_DATE == 3 and "at least 3 eligible snapshots" in text
    assert analyzer.MIN_PAIRINGS == 3 and analyzer.MIN_DATES == 2
    assert "at least 3 pairings on at least 2 UTC dates" in text
    assert analyzer.PASS_FRACTION == 0.80 and "at least 80%" in text
    assert analyzer.WINDOW_DAYS == 7 and "7 days from the first archived snapshot" in text
    assert analyzer.EXTENDED_WINDOW_DAYS == 14 and "to 14 days" in text

    def listed(label: str) -> set[str]:
        # Whitespace-tolerant: the document wraps its antenna lists across lines.
        match = re.search(rf"{label}: ((?:DSS\d+(?:,\s*)?)+)", text)
        assert match, f"PREREGISTRATION.md no longer lists the {label} antennas"
        return set(re.split(r",\s*", match.group(1).strip().rstrip(",")))

    assert listed("70 m") == analyzer.ANTENNAS_70M
    assert listed("34 m BWG") == analyzer.ANTENNAS_34M_BWG


def test_the_probe_workflow_cannot_pass_silently_or_run_forever():
    import yaml

    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "dsn-now-probe.yml")
                              .read_text(encoding="utf-8"))
    steps = workflow["jobs"]["log"]["steps"]
    runs = "\n".join(s.get("run") or "" for s in steps)

    assert "STOP=" in runs and "exit 1" in runs, (
        "no hard stop: a scheduled logger would keep polling NASA after its question is answered")
    assert "the archive is not empty" in [s.get("name") for s in steps], (
        "nothing checks that a job archived anything, so an empty run would go green")
    upload = next(s for s in steps if "upload-artifact" in (s.get("uses") or ""))
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload.get("if") == "always()"
    assert workflow["concurrency"]["cancel-in-progress"] is False

    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "log_dsn_now" not in ci, (
        "CI must stay a function of the commit, with no scheduled network")


# ---------------------------------------------------------------------------------------------
# merge_archives.py -- the logger uploads one archive per job; the analysis reads one directory.
# ---------------------------------------------------------------------------------------------

def _merger():
    spec = importlib.util.spec_from_file_location("merge_archives", PROBE / "merge_archives.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_merging_job_archives_decides_exactly_as_one_archive_would(tmp_path):
    """Plumbing must not move the verdict: split evidence across two jobs, merge, compare."""
    days = [_day(d, -154, -160) for d in DATES]
    whole = _write_archive(tmp_path / "whole", [s for day in days for s in day])
    job1 = _write_archive(tmp_path / "job1", days[0] + days[1])
    job2 = _write_archive(tmp_path / "job2", days[2])
    merged = tmp_path / "merged"

    assert _merger().main(["--into", str(merged), str(job2), str(job1)]) == 0
    analyzer = _analyzer()
    assert analyzer.main(["--archive", str(merged)]) == 0
    assert analyzer.main(["--archive", str(whole)]) == 0
    assert (merged / "index.jsonl").read_bytes() == (whole / "index.jsonl").read_bytes()


def test_a_merge_refuses_a_tampered_snapshot_and_writes_nothing(tmp_path):
    job = _write_archive(tmp_path / "job", _day(DATES[0], -154, -160))
    victim = next((job / "snapshots").rglob("*.xml"))
    victim.write_bytes(victim.read_bytes().replace(b"-154", b"-150"))
    assert _merger().main(["--into", str(tmp_path / "out"), str(job)]) == 1
    assert not (tmp_path / "out").exists()


def test_a_merge_refuses_the_same_archive_twice(tmp_path):
    job = _write_archive(tmp_path / "job", _day(DATES[0], -154, -160))
    assert _merger().main(["--into", str(tmp_path / "out"), str(job), str(job)]) == 1


def test_a_merge_refuses_an_existing_destination(tmp_path):
    job = _write_archive(tmp_path / "job", _day(DATES[0], -154, -160))
    (tmp_path / "out").mkdir()
    assert _merger().main(["--into", str(tmp_path / "out"), str(job)]) == 1


def test_a_merge_refuses_an_index_line_whose_snapshot_is_missing(tmp_path):
    job = _write_archive(tmp_path / "job", _day(DATES[0], -154, -160))
    next((job / "snapshots").rglob("*.xml")).unlink()
    assert _merger().main(["--into", str(tmp_path / "out"), str(job)]) == 1


def test_failed_attempts_survive_a_merge(tmp_path):
    """A failed fetch has no snapshot but is still evidence: it is what makes a gap visible."""
    job = _write_archive(tmp_path / "job", _day(DATES[0], -154, -160))
    failure = json.dumps({"attempted_at_utc": "2026-09-11T00:00:00+00:00",
                          "error": "URLError: unreachable", "url": "https://example.invalid"})
    with (job / "index.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(failure + "\n")
    out = tmp_path / "out"
    assert _merger().main(["--into", str(out), str(job)]) == 0
    assert failure in (out / "index.jsonl").read_text(encoding="utf-8").splitlines()
