"""The Tier-A predicate: what the numbers were computed on, measured rather than declared.

ADR-019 decision 2. The predicate is ``numeric_environment_hash``, **not** the container image
digest, and that record gives the reason plainly: a container cannot reliably read its own image
digest from inside, so whatever the runtime injects is a value the operator asserted. "A predicate
we cannot measure is a predicate we cannot enforce." Everything here is therefore read out of the
running process.

**Measured after the numeric stack has imported, and that includes the engine.** ADR-019 says
"from inside the running worker, after the numeric stack has imported". The SPICE adapter imports
``spiceypy`` lazily -- at the point of use, so the module tree stays importable without the
``spice`` extra -- which means a probe run before the first geometry call would not have CSPICE
mapped, and the predicate would silently omit the one shared object the geometry gate depends on.
:func:`numeric_environment` therefore forces the engine import when asked for one, rather than
measuring whatever happens to be loaded.

**Windows produces no Tier-A predicate, by construction.** ADR-006 forecloses the claim: "We can
never claim bitwise reproducibility across operating systems, so a Windows-only customer is
permanently a Tier-B customer and must be told so." ``mapped_libraries`` has no meaning there --
there is no ``/proc/self/maps``, and the loaded DLL set is a different thing from a glibc mapping
-- so this module refuses instead of inventing a weaker document that would look like the real
one. Refusing is the point: a Tier-A fingerprint that silently means less on one platform is worse
than none.

**A residue this document does not close, stated because ADR-019's own reasoning misses it.**
That record argues ISA normalization entirely in terms of OpenBLAS and NumPy's runtime dispatcher.
SPICE geometry is CSPICE arithmetic over libm and goes through neither. Pinning
``OPENBLAS_CORETYPE`` and ``NPY_DISABLE_CPU_FEATURES`` therefore does not constrain the code path
the weeks 1-2 gate is about. What this module can do, and does, is put the actual ``libm``/``libc``
and CSPICE shared objects into ``mapped_libraries`` by SHA-256, so that two environments differing
in them produce different predicates even though NumPy reports identical features. What it cannot
do is make one machine's libm behave like another's; ``GLIBC_TUNABLES`` is the candidate lever and
it must be set before the process starts, which is the parent's job (see :data:`ISA_ENV`).
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any

from farsight.schemas.errors import FarSightError

__all__ = [
    "ISA_ENV",
    "ISA_RESIDUE",
    "THREAD_ENV",
    "TIER_A_ISA_BASELINE",
    "EnvironmentUnavailable",
    "mapped_libraries",
    "numeric_environment",
    "numeric_environment_hash",
    "parse_maps",
]

# ADR-019 decision 3. The psABI level: AVX2 + FMA + BMI2.
TIER_A_ISA_BASELINE = "x86-64-v3"

# ADR-019 owns these; ADR-002 owns the thread pins. BOTH must be set in the PARENT before the
# worker process starts. Assigning them inside a running interpreter is a no-op for anything that
# reads them at load time -- the same shape as `PYTHONHASHSEED`, which CPython reads only at
# startup, so setting it in `os.environ` and reading it back yields a green test and no effect.
ISA_ENV: dict[str, str] = {
    "OPENBLAS_CORETYPE": "Haswell",              # the x86-64-v3 coretype OpenBLAS names
    "NPY_DISABLE_CPU_FEATURES": "AVX512F AVX512CD AVX512_SKX AVX512_CLX AVX512_CNL AVX512_ICL",
}

THREAD_ENV: dict[str, str] = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}

ISA_RESIDUE = (
    "PARTIALLY MECHANIZED: ISA_ENV constrains OpenBLAS kernel selection and NumPy's runtime SIMD "
    "dispatcher. It does NOT constrain glibc's libm, which resolves sin/cos/atan2/exp/pow to "
    "FMA/AVX2/AVX-512 variants through IFUNC at load time. SPICE geometry is CSPICE arithmetic "
    "over libm and goes through neither OpenBLAS nor NumPy's dispatcher, so the weeks 1-2 gate's "
    "own code path is not covered by these pins. `mapped_libraries` records the libm actually in "
    "use, which makes a DIFFERENT libm visible as a different predicate; it does not make two "
    "different CPUs compute the same libm result. Closing that needs GLIBC_TUNABLES set before "
    "process start, measured on two physically different CPU generations."
)


class EnvironmentUnavailable(FarSightError, RuntimeError):
    """A Tier-A numeric environment cannot be measured here."""


def _sha256_file(path: str | Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


_MAPS_LINE = re.compile(r"^\S+\s+\S+\s+\S+\s+\S+\s+(\d+)\s+(/.*)$")


def parse_maps(maps_text: str) -> list[str]:
    """The shared-object paths in a ``/proc/self/maps`` dump, unique and sorted.

    Split out from :func:`mapped_libraries` as a PURE function so the parsing and the ordering can
    be tested anywhere. They could otherwise only be exercised on Linux, which is not where this
    is developed -- a mutation removing the sort survived precisely because the assertion guarding
    it was inside a platform branch that never ran on the author's machine.

    Sorted because the list goes into a hashed document: loader order is a property of the run,
    not of the environment, and an unsorted list would make one environment hash differently
    between two runs of the same program.
    """
    paths: set[str] = set()
    for line in maps_text.splitlines():
        # `splitlines()` has already removed the terminator, so nothing to strip.
        match = _MAPS_LINE.match(line)
        if not match:
            continue
        inode, path = match.group(1), match.group(2)
        # inode 0 is an anonymous mapping: no file behind it, so nothing to hash.
        if inode == "0":
            continue
        if ".so" in path or path.endswith(".dylib"):
            paths.add(path)
    return sorted(paths)


def mapped_libraries() -> list[dict[str, Any]]:
    """Every shared object this process has mapped, by SHA-256 of the file on disk.

    ADR-019: this "is what makes 'glibc and libm provenance' a fact rather than a version string:
    two builds of the same glibc version produce different SHA-256 values and therefore a
    different predicate".
    """
    if not sys.platform.startswith("linux"):
        raise EnvironmentUnavailable(
            f"mapped_libraries needs /proc/self/maps and this is {sys.platform!r}. ADR-006 makes "
            f"a non-Linux host permanently Tier B, so there is no weaker document to fall back "
            f"to: a Tier-A fingerprint that means less on one platform is worse than none"
        )

    with open("/proc/self/maps", encoding="utf-8") as handle:
        paths = parse_maps(handle.read())

    entries: list[dict[str, Any]] = []
    for path in paths:
        digest = _sha256_file(path)
        if digest is None:
            continue
        entries.append({
            "soname": os.path.basename(path),
            "path": path,
            "sha256": digest,
            "size_bytes": int(os.path.getsize(path)),
        })
    return entries


def _isa_features() -> list[str]:
    """The features NumPy's dispatcher reports as enabled.

    NumPy's view, and labelled as such: it is what NumPy was told, and NumPy is not what computes
    the geometry. See :data:`ISA_RESIDUE`.
    """
    try:
        import numpy as np

        features = getattr(np.core._multiarray_umath, "__cpu_features__", {})
        return sorted(name for name, enabled in features.items() if enabled)
    except Exception:  # noqa: BLE001 - a NumPy without the private attribute is not a failure here
        return []


def _blas() -> dict[str, Any]:
    try:
        import numpy as np

        config = getattr(np, "__config__", None)
        info = config.show(mode="dicts") if config and hasattr(config, "show") else {}
        build = (info or {}).get("Build Dependencies", {}).get("blas", {})
        library_path = build.get("lib directory") or build.get("name") or "unknown"
        return {
            "name": str(build.get("name", "unknown")),
            "library_path": str(library_path),
            "version": str(build.get("version", "unknown")),
            "coretype": os.environ.get("OPENBLAS_CORETYPE", ""),
        }
    except Exception:  # noqa: BLE001
        return {"name": "unknown", "library_path": "unknown", "version": "unknown",
                "coretype": os.environ.get("OPENBLAS_CORETYPE", "")}


def _engine_build_ids(*, with_spice: bool) -> list[str]:
    """ADR-026's `install_fingerprint` for each engine present.

    Asked of the ADAPTER rather than computed here, because `geometry_is_not_an_engine` makes
    `spiceypy` importable only under `farsight.engines.spice` -- and that boundary is right: this
    module should not know what a CSPICE shared object is called. A second engine adds a line
    here and a `build.py` beside its own adapter.

    Forcing the import is the point (see the module docstring): the SPICE adapter loads spiceypy
    lazily, so a probe measuring only what was already imported would omit CSPICE from a predicate
    whose whole job is to say what the numbers were computed on.
    """
    if not with_spice:
        return []
    from farsight.engines.spice.build import install_fingerprint

    return install_fingerprint()


def numeric_environment(*, with_spice: bool = True, uv_lock: Path | None = None) -> dict[str, Any]:
    """The ADR-019 document, measured in this process.

    ``with_spice`` forces the engine import first, so CSPICE is mapped before ``mapped_libraries``
    reads the map. Passing ``False`` measures an environment that genuinely has no engine in it.
    """
    engine_ids = _engine_build_ids(with_spice=with_spice)
    libraries = mapped_libraries()   # after the engine import, deliberately

    interpreter_digest = _sha256_file(sys.executable) or ""
    lock = uv_lock if uv_lock is not None else Path(__file__).resolve().parents[3] / "uv.lock"
    lock_digest = _sha256_file(lock) if lock.exists() else ""

    return {
        "schema_version": "numeric_environment/1",
        "isa_baseline": TIER_A_ISA_BASELINE,
        "isa_enabled_features": _isa_features(),
        "interpreter": {
            "version": platform.python_version(),
            "binary_sha256": interpreter_digest,
        },
        "uv_lock_sha256": lock_digest,
        "mapped_libraries": libraries,
        "blas": _blas(),
        "thread_env": {key: os.environ.get(key, "") for key in sorted(THREAD_ENV)},
        "isa_env": {key: os.environ.get(key, "") for key in sorted(ISA_ENV)},
        "engine_build_ids": engine_ids,
    }


def numeric_environment_hash(document: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """``sha256(JCS(numeric_environment))``. ADR-019 decision 2.

    Bare 64 lowercase hex, no ``sha256:`` prefix -- this is a hashed document and ADR-001
    decision 7 admits the prefix only in human-facing output.
    """
    from farsight.hashing.canonical import content_hash

    return content_hash(document if document is not None else numeric_environment(**kwargs))
