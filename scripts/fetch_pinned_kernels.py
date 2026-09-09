"""Put every kernel in `kernels/pinned_kernels.json` into the local cache. ADR-016.

    python scripts/fetch_pinned_kernels.py

Idempotent: a kernel already in the cache is not re-fetched, so this is cheap to run on every CI
job and only pays the 46 MiB on a cache miss. Exits non-zero if anything is still missing
afterwards, because the caller's next step is a test suite that must not quietly skip.

Fetching goes through `farsight fetch kernel`, not through `urllib` here. ADR-016 makes the cache
verify-on-insert and ADR-012 makes `farsight.acquire` the only package permitted an HTTP library
with `cli/fetch` its only importer -- a second downloader in `scripts/` would be a second way for
unverified bytes to reach the cache, which is the thing that arrangement exists to prevent.

**This is a NETWORK script.** It is not imported by anything in the truth loop and nothing in the
test suite calls it; CI invokes it as a step, and a developer runs it once. The kernels are
never garbage-collected by design (ADR-016 decision 5), so the disk it spends is spent for good.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = REPO / "kernels" / "pinned_kernels.json"


def _console_script() -> str | None:
    """`farsight`, preferring the one belonging to the interpreter running this script."""
    beside = pathlib.Path(sys.executable).parent
    for name in ("farsight", "farsight.exe"):
        candidate = beside / name
        if candidate.exists():
            return str(candidate)
    return shutil.which("farsight")


def main() -> int:
    sys.path.insert(0, str(REPO / "src"))
    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import kernel_cache_root

    # The installed console script, not `python -m farsight.cli.main` -- that module has no
    # `__main__` guard and exits 1 without running anything, which is precisely the kind of
    # silently-does-nothing invocation this repository spent two days removing.
    #
    # Looked for BESIDE THE RUNNING INTERPRETER before PATH. In a venv -- which is what CI has
    # after setup-python plus `pip install -e` -- the console script sits next to `python`, and
    # the venv is not necessarily on PATH for a script invoked by absolute path.
    farsight = _console_script()
    if farsight is None:
        print(
            "REFUSED: the `farsight` console script is not on PATH. Install the package "
            "(`pip install -e .`) -- this script deliberately does not download anything itself, "
            "because ADR-012 makes `farsight.acquire` the only permitted downloader and the cache "
            "verify-on-insert lives behind that command.",
            file=sys.stderr,
        )
        return 1

    pinned = json.loads(MANIFEST.read_text(encoding="utf-8"))["kernels"]
    root = kernel_cache_root()
    cache = KernelCache(root)
    print(f"cache root: {root}")

    fetched = 0
    for kernel in pinned:
        name, digest = kernel["logical_name"], kernel["sha256"]
        if cache.has(digest):
            print(f"  present  {name}")
            continue
        print(f"  FETCHING {name}  ({kernel['size_bytes'] / 1024 / 1024:.1f} MiB)")
        command = [
            farsight, "fetch", "kernel",
            "--url", kernel["url"],
            "--expect-sha256", digest,
            "--into", str(root),
        ]
        if kernel.get("license_note"):
            command += ["--license-note", kernel["license_note"]]
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            print(f"  FAILED   {name}: fetch exited {result.returncode}", file=sys.stderr)
        else:
            fetched += 1

    # Re-read the cache rather than trusting the loop's own bookkeeping: `has()` is the same
    # question the test fixtures ask, and it is the only answer that matters to them.
    missing = [k["logical_name"] for k in pinned if not cache.has(k["sha256"])]
    have = len(pinned) - len(missing)
    print(f"\n{have}/{len(pinned)} pinned kernels in cache ({fetched} newly fetched)")
    if missing:
        print(
            "REFUSED: still missing " + ", ".join(missing) + ".\n"
            "The suite's real-kernel legs SKIP when a kernel is absent, so a caller that ignores "
            "this exit code gets a green run that tested nothing -- set FARSIGHT_REQUIRE_KERNELS=1 "
            "to make those skips into failures.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
