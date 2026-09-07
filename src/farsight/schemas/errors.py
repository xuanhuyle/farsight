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
    "KernelCoverageError",
    "MissingEngineExtra",
    "SpecCompositionError",
    "UnhonorableSpec",
    "WorkerError",
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


class KernelCoverageError(FreezeTimeError):
    """An epoch falls outside what the declared kernels cover (ADR-016).

    Freeze-time because ADR-016 specifies ``kernel_coverage_completeness`` as a freeze validator,
    and the reason is measurable: SPICE does not refuse an epoch before its leapsecond table --
    it extrapolates and returns a plausible number, wrong by 16 seconds for a 1980 epoch against
    a table starting in 2015. At run time there is nothing left to catch, because the wrong
    answer is indistinguishable from the right one.
    """


class WorkerError(FarSightError):
    """Raised inside the worker process.

    The distinction from a freeze-time error is not cosmetic, and ADR-023 draws a consequence
    from it: a failure that *should* have been caught at freeze but surfaced inside a worker is
    itself a report that the freeze-time completeness check has a hole. So a worker error is
    recorded as a run outcome AND read as evidence about the validator that let the spec through.
    """


class UnhonorableSpec(WorkerError):
    """A provider cannot honour the spec it was handed (ADR-003 ``initialize``).

    A ``WorkerError`` rather than a ``FreezeTimeError``, which ADR-023 fixes and which matters
    mechanically: its Enforcement item 6 forbids any ``FreezeTimeError`` subclass from being
    raised or imported under ``src/farsight/engines/``. An engine runs inside a worker, and
    nothing but bytes crosses the pool boundary, so a freeze-time exception raised there is a
    category error that could never reach the parent as itself.
    """


class MissingEngineExtra(WorkerError):
    """A provider needs an optional install that is not present.

    Distinct from :class:`UnhonorableSpec` because ADR-024's exit-code registry distinguishes
    them: "a required engine extra is not installed" is `environment_refusal` (14), while an
    unhonorable spec is `precondition_refusal` (20). Collapsing the two would tell an operator
    whose install is incomplete that their design is wrong -- and the two have completely
    different fixes.
    """
