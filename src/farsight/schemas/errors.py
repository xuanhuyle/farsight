"""The FarSight exception hierarchy, freeze-time branch.

ADR-023 decision 8: one hierarchy, three branches, and nothing crosses the pool boundary.

```
FarSightError            base; never raised directly
├── FreezeTimeError      raised in the parent; no run is ever planned
├── WorkerError          raised inside the worker process
└── VerificationError    raised by verify / replay in the audit path
```

**Partial on purpose.** Only the base and the freeze-time branch are here, because only they
have a raising site in the code that exists. ``WorkerError`` and ``VerificationError`` land with
the worker and the verifier, whose records own their subclasses. Declaring the empty branches
now would create three classes nothing raises and nothing catches, and ADR-023's own Option 6
rejects exactly that -- "a base class no one catches is ceremony".

**Why these live under ``schemas``.** They are raised by schema validators, and the
``schemas_is_leaf`` import contract forbids ``schemas`` from importing anything else inside
FarSight. A hierarchy in a central ``farsight.errors`` would therefore be unreachable from the
place that raises it. Putting it in the leaf keeps the contract intact and matches what the
package already is: the one vocabulary everything else depends on. The error names are part of
that vocabulary.

**Not a ``ValueError``.** ADR-023 Option 6 considered and rejected standard-library exceptions,
noting that "Pydantic raises ``ValidationError`` regardless so a custom base does not achieve
uniformity anyway". There is a concrete consequence here worth stating, because it is easy to
get backwards: Pydantic wraps ``ValueError`` and ``AssertionError`` raised inside a validator
into a ``ValidationError``, and lets every other exception propagate unchanged. So a
composition failure raised as a ``ValueError`` would reach the caller as a ``ValidationError``
and the record's requirement that it raise ``SpecCompositionError`` would be quietly false.
Subclassing ``Exception`` is what makes ADR-018's sentence literally true.
"""

from __future__ import annotations

__all__ = [
    "FarSightError",
    "FreezeTimeError",
    "SpecCompositionError",
]


class FarSightError(Exception):
    """Base for every exception FarSight defines. Never raised directly.

    Its purpose is the one lint ADR-023 says is worth having: an exception defined under
    ``src/farsight/`` that does not subclass this is a site nobody classified. The worker
    boundary needs a closed mapping from exception type to ``failure_class``, and a closed
    mapping over the standard library's open set is not writable.
    """


class FreezeTimeError(FarSightError):
    """A refusal in the parent process, before any run is planned.

    The distinction from a worker error is not cosmetic. A freeze-time refusal means no run was
    ever dispatched, so there is nothing in the ledger and nothing partial to clean up. ADR-023
    goes further: a failure that *should* have been caught at freeze but surfaced inside a
    worker is itself a report that the freeze-time completeness check has a hole.
    """


class SpecCompositionError(FreezeTimeError):
    """A run whose stages do not compose (ADR-018): stage, binding, grid or capability.

    Every one of ADR-018's six composition rules raises this, naming the stage id.
    """
