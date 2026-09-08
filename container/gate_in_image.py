"""The weeks 1-2 exit gate, run inside the reference image.

This is a FILE, and not a heredoc piped into `python -`, on purpose. It *was* a heredoc, and it
never ran: `podman run` without `-i` leaves the container's stdin closed, so `python -` read an
empty program, printed nothing, and exited 0. Five consecutive green CI runs reported the
weeks 1-2 gate -- "bitwise-reproducible in container" -- while executing no assertion at all.
The tell was in the logs the whole time and looked like success: a step with no output.

A script the image already contains cannot fail that way, because there is no stdin to forget.
The step that invokes it also checks that the output file appeared, so a future silent no-op
fails rather than passes; that check, not this docstring, is what keeps the claim honest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path("/out/gate.json")

# Frozen so the two runs differ in nothing an auditor cannot see. The gate is a question about
# the ENVIRONMENT, so every input that is not the environment is held still.
TS_UTC = "2026-09-07T12:00:00+00:00"


def isa_pin_measurement() -> dict[str, object]:
    """Does `NPY_DISABLE_CPU_FEATURES` disable anything in THIS image?

    ADR-019 decision 3 records the variable names as UNVERIFIED, and the way NumPy reports a
    rejected name is the reason that matters: it warns through `ImportWarning`, which Python
    hides by default. A pin naming features NumPy will not accept therefore looks exactly like a
    pin that works -- silent, in both cases.

    Measured in a FRESH interpreter, because the variable is read once while NumPy imports;
    asking the already-imported module cannot answer it. `numpy_rejected_the_pin` is worded as
    what was observed and not as a verdict: the absence of a rejection warning is not by itself
    proof that a kernel was disabled, and this does not attempt to claim otherwise.
    """
    code = (
        "import numpy as np;"
        "m = np._core._multiarray_umath;"
        "import json, sys;"
        "json.dump({'numpy': np.__version__, 'baseline': m.__cpu_baseline__,"
        " 'dispatch': m.__cpu_dispatch__}, sys.stdout)"
    )
    probe = subprocess.run(
        [sys.executable, "-W", "always::ImportWarning", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    rejected = "NPY_DISABLE_CPU_FEATURES" in probe.stderr
    return {
        "numpy_rejected_the_pin": rejected,
        "numpy_says": probe.stderr.strip()[-500:] if rejected else "",
        "requested": os.environ.get("NPY_DISABLE_CPU_FEATURES", ""),
        "targets": json.loads(probe.stdout) if probe.stdout.strip() else {},
    }


def main() -> int:
    # Imported here rather than at module scope so the file is importable for inspection off
    # Linux, where `mapped_libraries()` refuses by design.
    sys.path[:0] = ["tests", "tests/unit"]
    from test_geometry_gate import _bundle_dict, _populate_cache

    from farsight.cli.run_geometry import run_geometry
    from farsight.engines.environment import numeric_environment

    home = Path(tempfile.mkdtemp())
    lsk, spk, lsk_size, spk_size = _populate_cache(home)
    design = Path(tempfile.mkdtemp()) / "run.json"
    design.write_text(json.dumps(_bundle_dict(lsk, spk, lsk_size, spk_size), indent=2))

    runs = [
        run_geometry(
            design_path=design,
            out_dir=Path(tempfile.mkdtemp()),
            home=home,
            ts_utc=TS_UTC,
        )
        for _ in range(2)
    ]
    first, second = runs

    if first["channels"] != second["channels"]:
        raise SystemExit("NOT bitwise reproducible in the container: channel hashes differ")
    if first["spec_hash"] != second["spec_hash"]:
        raise SystemExit("NOT bitwise reproducible in the container: spec_hash differs")

    isa = numeric_environment().get("isa_enabled_features") or []
    record = {
        # Recorded BESIDE the numbers, because "did the geometry move?" is only answerable next
        # to "did the silicon?" -- DEV-23. GitHub does not guarantee a runner CPU generation, and
        # one changed under this project mid-week.
        "avx512": sorted(f for f in isa if "AVX512" in f),
        "channels": first["channels"],
        "spec_hash": first["spec_hash"],
        "isa_pin": isa_pin_measurement(),
        "x86_level": sorted(f for f in isa if f.startswith("X86_V")),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2, sort_keys=True))

    print("bitwise reproducible in container:")
    print("   spec_hash", record["spec_hash"])
    for line in record["channels"]:
        print("  ", line)
    print("   x86 level:", ", ".join(record["x86_level"]) or "(none reported)")
    pin = record["isa_pin"]
    print("   isa pin  :", "REJECTED by numpy" if pin["numpy_rejected_the_pin"]
          else "no rejection warning")
    if pin["numpy_says"]:
        print("  ", " ".join(pin["numpy_says"].split()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
