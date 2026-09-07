"""What the SPICE geometry provider can do — declared without importing SPICE.

ADR-003 requires an adapter's capabilities to be readable by the planner, and the planner runs on
the base install. If reading them pulled in the SDK, every capability query would require the
extra, and the zero-extras auditor path would be a fiction the moment anything asked what an
adapter supports.

So this module imports nothing from ``spiceypy``, and a test asserts that by replacing the module
with an import-raising sentinel before importing this one.

**A ``GeometryProvider`` is not an ``Engine``**, and ADR-003 says so deliberately: SPICE is a
deterministic lookup service over a kernel pool. It has no segment model, no interventions, and
no randomness, so three of five ``Engine`` methods would have to raise. The capability record
below says that positively rather than by omission.
"""

from __future__ import annotations

from typing import Final

__all__ = ["CAPABILITIES", "PROVIDER_ID", "REUSABLE_WORKER", "SEED_SCOPE", "SUPPORTS_STEPPING"]

PROVIDER_ID: Final = "spice"

# A geometry stage is evaluated in one shot over the run's sample grid (ADR-018). There are no
# segment boundaries to step to, so a ConditionSchedule predicate over a geometry channel is
# resolved before the engine stage begins rather than by stepping this provider.
SUPPORTS_STEPPING: Final = False

# ADR-002 grants worker recycling to SPICE **alone**, and the grant is defensible only because it
# is falsifiable: CSPICE keeps one global kernel pool per process, and the pool is cleared between
# runs, so a recycled worker must produce byte-identical results to a fresh one. That equality is
# the third leg of `ci-worker-order-invariance`. If it ever fails, this flag is what was wrong.
REUSABLE_WORKER: Final = True

# No randomness reaches this provider at all: geometry is a lookup, not a simulation. Declaring
# "none" rather than omitting the field is what lets the planner refuse to hand it a seed rather
# than silently passing one nothing consumes.
SEED_SCOPE: Final = "none"

CAPABILITIES: Final[dict[str, object]] = {
    "provider_id": PROVIDER_ID,
    "supports_stepping": SUPPORTS_STEPPING,
    "reusable_worker": REUSABLE_WORKER,
    "seed_scope": SEED_SCOPE,
    "is_engine": False,
}
