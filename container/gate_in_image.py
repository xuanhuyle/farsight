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
    from farsight.engines.environment import TIER_A_ISA_BASELINE, _dispatch_selected

    return {
        "declared_baseline": TIER_A_ISA_BASELINE,
        "numpy_rejected_the_pin": rejected,
        "numpy_says": probe.stderr.strip()[-500:] if rejected else "",
        "requested": os.environ.get("NPY_DISABLE_CPU_FEATURES", ""),
        # What NumPy SELECTED, which is the only thing that proves the pin did anything: a name
        # NumPy does not recognise is accepted in silence and changes nothing.
        "selected": _dispatch_selected(),
        "targets": json.loads(probe.stdout) if probe.stdout.strip() else {},
    }


# `current` reads as "X86_V3" or "baseline(X86_V2)". Anything above the declared x86-64-v3
# baseline means AVX-512 kernels are reachable and the pin did not hold.
PERMITTED_SELECTIONS = ("baseline", "X86_V2", "X86_V3")


def check_isa_pin(pin: dict[str, object]) -> None:
    """Refuse a Tier-A gate run whose ISA pin did not take effect.

    Recording it and carrying on was the tempting shape, and it is the shape that let a dead pin
    sit in the record unnoticed. A pin nothing checks is a comment. ADR-019 decision 3 says
    dispatch "is pinned to a declared baseline"; when it is not, this run is not the environment
    the predicate describes and must not be reported as one.
    """
    if pin["numpy_rejected_the_pin"]:
        raise SystemExit(
            "ISA pin REJECTED by numpy, so dispatch is not pinned.\n"
            f"  requested:  {pin['requested']}\n"
            f"  numpy said: {' '.join(str(pin['numpy_says']).split())}"
        )
    if not pin["selected"]:
        raise SystemExit(
            "the ISA pin could not be measured at all -- no dispatch selection was reported, so "
            "whether it took effect is unknown, which is not the same as fine"
        )
    above = [s for s in pin["selected"] if not s.startswith(PERMITTED_SELECTIONS)]
    if above:
        raise SystemExit(
            "ISA pin took NO EFFECT: NumPy selected kernels above the declared "
            f"{pin['declared_baseline']} baseline -- {', '.join(above)}.\n"
            f"  requested: {pin['requested']}\n"
            f"  dispatch targets in this build: {pin['targets']}\n"
            "  A name NumPy does not recognise is accepted in silence and changes nothing, so "
            "this is also what a typo in NPY_DISABLE_CPU_FEATURES looks like."
        )


def main() -> int:
    # Imported here rather than at module scope so the file is importable for inspection off
    # Linux, where `mapped_libraries()` refuses by design.
    sys.path[:0] = ["tests", "tests/unit"]
    from test_geometry_gate import _bundle_dict, _populate_cache

    from farsight.cli.run_geometry import run_geometry
    from farsight.engines.environment import numeric_environment

    # FIRST, before a single number is computed. A refusal that arrives after the channels are
    # written is a report about evidence already produced, not a gate on producing it.
    pin = isa_pin_measurement()
    check_isa_pin(pin)

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
        "isa_pin": pin,
        "x86_level": sorted(f for f in isa if f.startswith("X86_V")),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2, sort_keys=True))

    print("bitwise reproducible in container:")
    print("   spec_hash", record["spec_hash"])
    for line in record["channels"]:
        print("  ", line)
    # The AVX-512 COUNT belongs on this line, not only in the file. Two runners printed an
    # identical "x86 level: X86_V2, X86_V3" while differing by 16 AVX-512 entries, and that line
    # was read as "same machine". A summary that hides the field the predicate actually refuses
    # on is worse than no summary.
    print("   x86 level:", ", ".join(record["x86_level"]) or "(none reported)",
          "| avx512:", len(record["avx512"]), "features")
    print("   isa pin  : HELD --", ", ".join(pin["selected"]),
          "at or below the declared", pin["declared_baseline"], "baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
