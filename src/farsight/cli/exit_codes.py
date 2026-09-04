"""The exit-code contract: one registry, append-only, printed into shipped packages.

ADR-024 decision 2. This module is the single source for the code, the symbol and the one-line
meaning, and it exists because "nonzero" is not scriptable. An auditor needs to distinguish
**tamper** from **schema-invalid** from **missing register**; those three demand different
responses, and collapsing them into one number makes the audit path guesswork.

**Append-only, and the reason is unusual.** ``report/summary.md`` is generated from package JSON
and contains the audit instructions, so **command names and exit codes are printed into shipped
evidence packages** (ADR-024). A number's meaning is therefore never reassigned and a symbol is
never removed: a package shipped today says "exit code 10 means a hash did not match", and that
sentence has to still be true in three years. New conditions get new numbers.

**A verdict is a result, not a failure.** ``pass``, ``fail`` and ``indeterminate`` all exit ``0``
by default, preserving ADR-009's rule exactly. ``--exit-on-verdict`` is the opt-in for a CI system
that wants the verdict in the exit status, and it is opt-in precisely because a ``fail`` verdict
is a scientific outcome and a nonzero exit reads as a broken tool.
"""

from __future__ import annotations

from typing import Final, Iterable, NamedTuple

__all__ = [
    "ExitCode",
    "REGISTRY",
    "resolve",
    "meaning",
    "OK",
    "INTERNAL_ERROR",
    "USAGE_ERROR",
    "INTEGRITY_FAILURE",
    "SCHEMA_FAILURE",
    "COMPLETENESS_FAILURE",
    "RECOMPUTATION_MISMATCH",
    "ENVIRONMENT_REFUSAL",
    "SIGNATURE_POLICY_FAILURE",
    "PRECONDITION_REFUSAL",
    "WORK_REMAINS",
    "VERDICT_FAIL",
    "VERDICT_INDETERMINATE",
    "ACQUISITION_FAILURE",
]


class ExitCode(NamedTuple):
    code: int
    symbol: str
    meaning: str


OK: Final = 0
INTERNAL_ERROR: Final = 1
USAGE_ERROR: Final = 2
INTEGRITY_FAILURE: Final = 10
SCHEMA_FAILURE: Final = 11
COMPLETENESS_FAILURE: Final = 12
RECOMPUTATION_MISMATCH: Final = 13
ENVIRONMENT_REFUSAL: Final = 14
SIGNATURE_POLICY_FAILURE: Final = 15
PRECONDITION_REFUSAL: Final = 20
WORK_REMAINS: Final = 21
VERDICT_FAIL: Final = 22
VERDICT_INDETERMINATE: Final = 23
ACQUISITION_FAILURE: Final = 30

# Transcribed from ADR-024 decision 2. The meanings are the record's own wording, because this
# text is what an auditor reads out of a package.
REGISTRY: Final[tuple[ExitCode, ...]] = (
    ExitCode(OK, "ok", "the operation completed and every check it performed passed"),
    ExitCode(INTERNAL_ERROR, "internal_error", "unhandled exception; never returned deliberately"),
    ExitCode(USAGE_ERROR, "usage_error",
             "reserved: this is Typer/Click's own code and is not reassigned"),
    ExitCode(INTEGRITY_FAILURE, "integrity_failure",
             "a recorded hash did not match recomputed bytes (the AT-3 tamper class)"),
    ExitCode(SCHEMA_FAILURE, "schema_failure",
             "a document failed validation against the schema shipped in the package"),
    ExitCode(COMPLETENESS_FAILURE, "completeness_failure",
             "a required element is absent: a register file, a review_signoff row, a claim "
             "falsifier, an unresolvable referent_ref, an unresolved input hash"),
    ExitCode(RECOMPUTATION_MISMATCH, "recomputation_mismatch",
             "a metric or verdict recomputed from raw channels differs from the recorded value "
             "while every hash matched (a version-skew finding)"),
    ExitCode(ENVIRONMENT_REFUSAL, "environment_refusal",
             "the tier predicate is not satisfiable here (ADR-019), or a required engine extra "
             "is not installed"),
    ExitCode(SIGNATURE_POLICY_FAILURE, "signature_policy_failure",
             "--require-signature was given and the signature is absent or invalid"),
    ExitCode(PRECONDITION_REFUSAL, "precondition_refusal",
             "the artifact could not be produced because a precondition was refused: an "
             "unhonorable RunSpec, a refused fault lowering, an unbounded Unknown, a missing "
             "pedigree, a shadow-units run offered to evidence build"),
    ExitCode(WORK_REMAINS, "work_remains",
             "run/resume: not every planned run reached a terminal status; or --strict was given "
             "and at least one run is not `ok`"),
    ExitCode(VERDICT_FAIL, "verdict_fail",
             "--exit-on-verdict and at least one acceptance verdict is `fail`"),
    ExitCode(VERDICT_INDETERMINATE, "verdict_indeterminate",
             "--exit-on-verdict, no `fail`, at least one `indeterminate`"),
    ExitCode(ACQUISITION_FAILURE, "acquisition_failure",
             "fetch: bytes did not match --expect-sha256, or transport failed"),
)

_BY_CODE: Final[dict[int, ExitCode]] = {e.code: e for e in REGISTRY}


def meaning(code: int) -> str:
    """The registry's one-line meaning for ``code``, or a refusal naming the unknown code."""
    entry = _BY_CODE.get(code)
    if entry is None:
        raise KeyError(
            f"exit code {code} is not in the registry. The registry is append-only and is the "
            f"single source (ADR-024 decision 2); a code with no entry cannot be printed into a "
            f"package whose instructions must still be true in three years."
        )
    return entry.meaning


def resolve(codes: Iterable[int]) -> int:
    """The code to return when several conditions hold at once.

    ADR-024: **the numerically smallest applicable code above 2**. That makes tamper (10) dominate
    everything, which is the ordering an auditor wants, and it is deterministic -- the same
    package on the same install always yields the same code.

    Nothing is hidden by this. ``--json`` reports every finding regardless of which code the
    process returned; the single number exists so a shell script can branch, not so a human can
    stop reading.
    """
    applicable = sorted({c for c in codes if c > USAGE_ERROR})
    return applicable[0] if applicable else OK
