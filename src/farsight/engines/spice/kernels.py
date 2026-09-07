"""Furnishing: the one and only place FarSight calls ``spiceypy.furnsh``.

ADR-016 decision 2. The worker furnishes exactly the declared sequence, in exactly the declared
order, **one file at a time, never a metakernel** — and then proves it did.

Three rules, each closing a specific failure:

**One file at a time.** A metakernel names kernels by path, which reintroduces the ambient
directory the content-addressed cache exists to remove, and makes the furnished set depend on the
filesystem rather than on the frozen document. ``kernel_type`` has no ``mk`` member so the input
cannot express one, and an AST lint refuses a ``.tm`` literal anywhere in the source.

**Verified before furnishing.** Bytes are re-hashed against the address they are filed under
(memoized per process, ADR-016 decision 5), so a cache file replaced after it was stored is caught
before SPICE reads it rather than after a number comes out wrong.

**Counted after furnishing.** ``ktotal("ALL")`` must equal the sequence length. CSPICE will
decline to load a file it cannot parse and carry on; without the count, a silently-skipped
furnish shows up later as a missing frame or a wrong value, at a point far from its cause.

**The pool is global, and that is why it is cleared explicitly.** CSPICE keeps one kernel pool per
process — the fact behind ADR-002's single worker-recycling grant to SPICE. Leaving it furnished
between runs is how one run's kernels become another's silent input.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from farsight.registry.kernel_cache import KernelCache
from farsight.schemas.errors import MissingEngineExtra, UnhonorableSpec
from farsight.schemas.kernels import KernelRef

# `UnhonorableSpec` is a `WorkerError`, not a `FreezeTimeError`, and the distinction is enforced:
# ADR-023 Enforcement 6 forbids any FreezeTimeError subclass from being raised or imported under
# `src/farsight/engines/`. An engine runs inside a worker and nothing but bytes crosses the pool
# boundary, so a freeze-time exception raised here could never reach the parent as itself. What
# it means is still "this spec should not have reached me" -- ADR-023 reads a worker-side refusal
# as a report that the freeze-time completeness check has a hole.
__all__ = ["UnhonorableSpec", "MissingEngineExtra", "furnish_in_order", "clear_pool", "furnished_pool", "loaded_count"]


def _spiceypy():
    """Import SPICE at the point of use.

    Inside the function so that importing this module does not require the ``spice`` extra —
    which matters because the import-linter contract permits ``spiceypy`` only here, and because
    a planner that merely inspects this module should not need a compiled CSPICE.
    """
    try:
        import spiceypy  # noqa: PLC0415 - deliberate; see docstring
    except ImportError as exc:  # pragma: no cover - exercised by the auditor install, not by CI
        raise MissingEngineExtra(
            "the `spice` extra is not installed, so no kernel can be furnished. This is the "
            "auditor's install (ADR-007): `verify` runs without it, and only `replay` of a run "
            "with a geometry stage needs it."
        ) from exc
    return spiceypy


def loaded_count() -> int:
    """How many kernels the process pool currently holds."""
    return int(_spiceypy().ktotal("ALL"))


def clear_pool() -> None:
    """Empty the process-global kernel pool."""
    _spiceypy().kclear()


def furnish_in_order(sequence: Sequence[KernelRef], cache: KernelCache) -> list[Path]:
    """Furnish the declared sequence in the declared order. Returns the paths furnished.

    The order **is** the decision (ADR-016 decision 2): a later kernel overrides an earlier one,
    so two orderings of the same files are two different physical configurations, and the
    ``KernelSet`` hash differs between them precisely so that difference is visible.
    """
    spiceypy = _spiceypy()
    before = int(spiceypy.ktotal("ALL"))
    furnished: list[Path] = []

    for ref in sequence:
        # Verified against its own address before SPICE sees it. The cache memoizes per process,
        # so a large SPK is re-hashed once per process rather than once per furnish.
        path = cache.get_path(ref.sha256)
        spiceypy.furnsh(str(path))
        furnished.append(path)

    loaded = int(spiceypy.ktotal("ALL")) - before
    if loaded != len(sequence):
        raise UnhonorableSpec(
            f"furnished {len(sequence)} kernels but the pool gained {loaded}. CSPICE declines to "
            f"load a file it cannot parse and continues, so a silently-skipped furnish would "
            f"surface later as a missing frame or a wrong value, far from its cause. "
            f"Sequence: {[r.logical_name for r in sequence]}"
        )
    return furnished


@contextmanager
def furnished_pool(sequence: Sequence[KernelRef], cache: KernelCache) -> Iterator[list[Path]]:
    """Furnish for the duration of the block, and clear the pool afterwards, always.

    The pool is process-global, so an exception that skipped the clear would leave the next
    caller's results depending on which test or run happened to fail before it.
    """
    paths = furnish_in_order(sequence, cache)
    try:
        yield paths
    finally:
        clear_pool()
