"""No false validation claims (ADR-030 decision 4, enforcement 1-2).

A repo whose thesis is scientific honesty cannot describe its own research as expert
validation. This lint scans every Markdown document for the forbidden claim phrases and fails
on any occurrence that is not a quotation, negation, or definition of the rule itself.

PARTIALLY MECHANIZED: a grep recognizes phrases, not claims -- a forbidden claim in novel
wording passes cleanly, and review-checklist item REVIEW-1 carries that residue. The negation
heuristic errs permissive on lines that mention a phrase while forbidding it; the allowlist
below exists for the few structural cases, each with its reason.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._guards import python_sources

REPO = Path(__file__).resolve().parents[2]

FORBIDDEN = [
    "expert validated",
    "expert-validated",
    "validated by experts",
    "independently validated",
    "flight qualified",
    "flight-qualified",
    "verified by aerospace experts",
    "certified by",
]

# A line mentioning a forbidden phrase is a MENTION (not a claim) when it also carries one of
# these markers: negations, rule statements, or quoting punctuation around the phrase.
NEGATION = re.compile(
    r"never|not |no |forbidden|prohibit|must not|may not|unless|avoid|rather than|"
    # The curly quotes are deliberate: this scans Markdown, where they are what appears.
    r"instead of|do not|don't|cannot|refuse|ban|Forbidden|`|\"|“|‘|'",  # noqa: RUF001
)

# path (relative, posix) -> reason. Keep this SHORT; growth is ADR-030's revisit trigger.
ALLOWLIST: dict[str, str] = {}

SCAN_DIRS = ["docs", "experiments"]
SCAN_ROOT_FILES = ["README.md", "EXPERT_REVIEW_BACKLOG.md", "FARSIGHT_FOUNDATION_PLAN.md",
                   "FARSIGHT_ARCHITECTURE_EVOLUTION_REVIEW.md"]


def _markdown_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        files.extend((REPO / d).rglob("*.md"))
    for f in SCAN_ROOT_FILES:
        p = REPO / f
        if p.exists():
            files.append(p)
    return files


def test_no_false_validation_claims():
    violations: list[str] = []
    for path in _markdown_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOWLIST:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            for phrase in FORBIDDEN:
                if phrase in low and not NEGATION.search(line):
                    violations.append(f"{rel}:{lineno}: {line.strip()[:100]!r} [{phrase}]")
    assert not violations, (
        "Forbidden validation claims found (ADR-030 decision 4). Research is described as "
        "research -- 'research-reviewed', 'not externally expert-reviewed' -- never as expert "
        "validation:\n  " + "\n  ".join(violations)
    )


def test_implementation_deviations_ledger_is_structured_and_points_at_real_files():
    """ADR-000 forbids editing an accepted record, so a departure between code and ADR has
    nowhere to live until a superseding record is written. The ledger is that place, and it is
    only worth having if its entries stay true: an entry naming a file that no longer exists is
    the same staleness liability ADR-000's Consequences section warns about, one level down.
    """
    p = REPO / "docs" / "adr" / "IMPLEMENTATION_DEVIATIONS.md"
    assert p.exists(), "docs/adr/IMPLEMENTATION_DEVIATIONS.md is where ADR/code drift is recorded"
    text = p.read_text(encoding="utf-8")
    entries = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    assert entries, "the deviations ledger must contain at least one entry"

    required = ["**Record:**", "**Code:**", "**What differs.**", "**Why.**",
                "**Closes by:**", "**Status:**"]
    for entry in entries:
        title = entry.splitlines()[0].strip()
        # The message lists the WHOLE set, not just the first omission. `**Why.**` has been left
        # out of four separate entries in this repository, each time by composing the headings
        # from memory instead of copying an existing entry; a message that names one missing
        # heading invites fixing that one and rediscovering the next on the following run.
        missing = [f for f in required if f not in entry]
        assert not missing, (
            f"deviation entry {title!r} is missing {missing}.\n"
            f"Every entry carries all of: {required}.\n"
            f"Copy an existing entry as a template rather than writing the headings out."
        )

        # Every source file an entry blames must exist, or the entry describes a world that
        # has moved on.
        for line in entry.splitlines():
            if line.startswith("**Code:**"):
                for ref in re.findall(r"`([^`]+)`", line):
                    if "/" in ref:
                        assert (REPO / ref).exists(), (
                            f"deviation entry {title!r} names {ref!r}, which does not exist"
                        )
        # Same for the record it cites, which is a link relative to docs/adr/.
        for target in re.findall(r"\]\((ADR-[^)]+\.md)\)", entry):
            assert (REPO / "docs" / "adr" / target).exists(), (
                f"deviation entry {title!r} links {target!r}, which does not exist"
            )


def test_expert_review_backlog_exists_and_is_structured():
    p = REPO / "EXPERT_REVIEW_BACKLOG.md"
    assert p.exists(), "EXPERT_REVIEW_BACKLOG.md is mandatory (ADR-030 decision 6)"
    text = p.read_text(encoding="utf-8")
    # Every entry is an H2 section carrying the required fields.
    entries = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    assert entries, "the backlog must contain at least one entry"
    required = ["**Topic:**", "**Expertise eventually required:**", "**Current state:**",
                "**Current confidence:**", "**Consequence if wrong:**", "**Priority:**"]
    for entry in entries:
        title = entry.splitlines()[0]
        for field in required:
            assert field in entry, f"backlog entry {title!r} is missing {field}"


def test_deep_review_artifacts_carry_the_status_line():
    # ADR-030 enforcement 3 (mechanical half): every Deep Review artifact says what it is not.
    reviews = list((REPO / "experiments").rglob("*DEEP_REVIEW*.md"))
    assert reviews, "expected at least one Deep Review artifact"
    for r in reviews:
        text = r.read_text(encoding="utf-8")
        assert "NOT externally expert-reviewed" in text, (
            f"{r.name} must carry the ADR-030 status line, including its negative half"
        )


def test_exception_hierarchy_closed():
    """ADR-023 Enforcement item 6, the leg that is checkable today.

    Every exception class defined under ``src/farsight/`` subclasses ``FarSightError``. The
    reason is not tidiness: the worker boundary needs a closed mapping from exception type to
    ``failure_class`` (ADR-023 decision 8), and a closed mapping over the standard library's
    open set is not writable. An exception outside the hierarchy is a site nobody classified.

    The remaining leg -- that the worker returns a ``RunOutcome`` for every injected error --
    needs the worker, and is not silently skipped: it is named here so the gap stays visible
    while this test passes. The ``engines/`` half is checked by the test below.
    """
    import ast

    src = REPO / "src" / "farsight"

    # Collected first, then resolved. The first version of this walked files in sorted order and
    # grew the known set as it went, so a subclass defined in a file sorting BEFORE the one
    # defining its base was reported as an offender -- `engines/spice` before `schemas/errors`.
    # A lint whose verdict depends on filename order is worse than no lint: it fails for the
    # wrong reason and teaches the reader to distrust it.
    # EVERY class is collected, not only the ones that look like exceptions, because
    # membership in the hierarchy has to be resolved through classes the *reporting* rule
    # ignores. `UnhonorableSpec` is exactly that: ADR-023 names it without an `Error` suffix
    # and derives it from `WorkerError`, so the earlier version of this collector never saw
    # it -- and then reported its subclass `EpochCoverageError` as orphaned, when the real
    # defect was the lint's own blind spot. Detection and reporting are now separate: the
    # graph is complete, and only the exception-shaped nodes can be offenders.
    classes: dict[str, tuple[str, int, set[str]]] = {}
    for path in python_sources(src):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
            base_names |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
            classes[node.name] = (path.relative_to(REPO).as_posix(), node.lineno, base_names)

    BUILTIN_EXC = {"Exception", "BaseException", "ValueError", "RuntimeError", "OSError",
                   "TypeError", "KeyError", "LookupError"}
    found = {
        name: entry
        for name, entry in classes.items()
        if name.endswith("Error") or bool(entry[2] & BUILTIN_EXC)
    }

    known = {"FarSightError"}
    changed = True
    while changed:
        changed = False
        for name, (_path, _line, bases) in classes.items():
            if name not in known and (bases & known):
                known.add(name)
                changed = True

    offenders = [
        f"{path}:{line}: {name}({', '.join(sorted(bases)) or 'object'})"
        for name, (path, line, bases) in sorted(found.items())
        if name != "FarSightError" and name not in known
    ]
    assert not offenders, (
        "exceptions outside the FarSightError hierarchy (ADR-023 decision 8); each is a site "
        "the worker's exception-to-failure_class mapping cannot classify:\n  "
        + "\n  ".join(offenders)
    )


def test_no_freeze_time_error_under_engines():  # noqa: PLR0912 - one rule, one place
    """ADR-023 Enforcement item 6, second leg.

    No ``FreezeTimeError`` subclass may be raised or imported anywhere under
    ``src/farsight/engines/``. The reason is mechanical rather than stylistic: an engine runs
    inside a worker process, and ADR-002 lets nothing but bytes cross that boundary -- so an
    exception raised there never reaches the parent as itself, only as whatever the worker
    protocol encodes. A freeze-time exception raised inside a worker is therefore a claim that
    cannot be honoured by the place it is made.

    It is also a claim in the wrong tense. Freeze-time means "this design should never have been
    built". Reaching a worker at all means it *was* built and dispatched, so the honest report is
    ADR-023's: a worker-side refusal that a freeze validator should have caught is evidence about
    the validator, and the type system should say worker, not freeze.

    This got past review once already. Both `UnhonorableSpec` and the coverage error were
    written as `FreezeTimeError` subclasses under `engines/spice/`, and nothing objected.
    """
    import ast

    src = REPO / "src" / "farsight"
    errors_mod = src / "schemas" / "errors.py"

    # The freeze-time branch, resolved transitively from the module that defines it.
    freeze: set[str] = {"FreezeTimeError"}
    tree = ast.parse(errors_mod.read_text(encoding="utf-8"))
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name not in freeze:
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                if bases & freeze:
                    freeze.add(node.name)
                    changed = True
    assert len(freeze) > 1, (
        "no FreezeTimeError subclasses were found, so this test would pass vacuously"
    )

    violations: list[str] = []
    for path in python_sources(src / "engines", minimum=10):
        rel = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in freeze:
                        violations.append(f"{rel}:{node.lineno}: imports {alias.name}")
            elif isinstance(node, ast.Raise) and node.exc is not None:
                call = node.exc
                target = call.func if isinstance(call, ast.Call) else call
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name in freeze:
                    violations.append(f"{rel}:{node.lineno}: raises {name}")
            elif isinstance(node, ast.ClassDef):
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                if bases & freeze:
                    violations.append(
                        f"{rel}:{node.lineno}: {node.name} subclasses a freeze-time error"
                    )
    assert not violations, (
        "freeze-time exceptions under engines/ (ADR-023 Enforcement 6). An engine runs inside a "
        "worker; use a WorkerError subclass such as UnhonorableSpec, and put the freeze-time "
        "refusal in the parent-side validator that should have caught it:\n  "
        + "\n  ".join(violations)
    )


def test_determinism_rules():
    """ADR-006 Enforcement 5, specified as first green by week 1 and not implemented until now.

    AST-scans ``src/farsight/`` outside ``analysis/`` and fails on ``datetime.now``,
    ``time.time``, ``os.getpid``, ``socket.gethostname`` and ``os.listdir``. The ban exists for
    one reason: each of these returns a value that differs between two otherwise identical runs,
    and any of them reaching a hashed artifact destroys bitwise reproducibility.

    **Two sites are allowed, and the allowlist is closed.** The rule as ADR-006 words it is
    broader than the architecture it serves -- two things the design requires cannot be written
    without a banned name -- so each exception is enumerated with the reason its value cannot
    reach a hashed artifact. The list is asserted to be exactly these two, so a third use fails
    this test until somebody edits the list and writes down why. That is the whole mechanism:
    the exception is cheap, and it is not silent.

    The runtime half of ADR-006's item 5 -- that each worker observes single-threaded limits --
    needs the worker, which does not exist, and is named here so the gap is visible.
    """
    import ast

    src = REPO / "src" / "farsight"
    banned = {"now": "datetime.now", "time": "time.time", "getpid": "os.getpid",
              "gethostname": "socket.gethostname", "listdir": "os.listdir"}

    # path -> (banned attribute, why the value cannot reach a hashed artifact)
    ALLOWED = {
        "cli/geometry.py": (
            "now",
            ("ADR-012's `ts_utc` for the audit row. The audit log is explicitly NOT package "
            "content (ADR-006, ADR-012): timestamps live only in the unhashed provenance half, "
            "and a log of when things happened cannot be written without reading a clock."),
        ),
        "registry/atomic.py": (
            "getpid",
            ("A temp filename component, so two concurrent writers do not collide on the same "
            "sibling path. The file is renamed over the destination and the name is discarded; "
            "no hashed artifact ever contains it."),
        ),
    }

    found: dict[str, list[str]] = {}
    for path in python_sources(src):
        rel = path.relative_to(src).as_posix()
        if rel.startswith("analysis/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in banned:
                found.setdefault(rel, []).append(f"{banned[node.attr]} (line {node.lineno})")

    offenders = [
        f"{rel}: {', '.join(uses)}"
        for rel, uses in sorted(found.items())
        if rel not in ALLOWED
    ]
    assert not offenders, (
        "non-deterministic calls under src/farsight/ (ADR-006 Enforcement 5). Each returns a "
        "value that differs between two otherwise identical runs; if it can reach a hashed "
        "artifact it destroys bitwise reproducibility. Add an ALLOWLIST entry with the reason "
        "its value cannot, or remove the call:\n  " + "\n  ".join(offenders)
    )

    # The allowlist is closed in the other direction too: an entry whose call has been removed is
    # a licence nobody is using, and it would silently re-permit the name if it came back.
    stale = sorted(set(ALLOWED) - set(found))
    assert not stale, (
        f"allowlist entries with no matching call: {stale}. Remove them, or the exception "
        f"outlives the reason for it"
    )


def test_the_lint_rule_set_is_pinned_rather_than_inherited():
    """A lint whose meaning depends on which machine runs it is not a contract.

    Measured 2026-09-07: with no `select`, ruff 0.16.5 enables 415 rules of its own choosing and
    reports 150 findings in this tree. A different ruff version would enable a different set, so
    CI would start failing on the tool's release schedule rather than on a change to this code --
    which is the shape ADR-006 already warns about for container base images, where "any
    base-image security update invalidates existing Tier-A goldens and forces a re-golding cycle
    on someone else's schedule".

    Two things therefore have to stay pinned, and this test fails if either is dropped: the rule
    set, and the version of the tool that interprets it.
    """
    import re
    import tomllib

    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))

    lint = config.get("tool", {}).get("ruff", {}).get("lint", {})
    assert lint.get("select"), (
        "[tool.ruff.lint].select is empty or missing, so the enforced rule set is whatever this "
        "ruff version happens to default to"
    )
    assert isinstance(lint.get("ignore"), list), (
        "every deliberate exclusion belongs in `ignore` with a reason beside it, not in a "
        "narrowed `select` where the disagreement is invisible"
    )

    dev = config["project"]["optional-dependencies"]["dev"]
    pins = [d for d in dev if d.replace(" ", "").startswith("ruff==")]
    assert pins, (
        f"ruff is unpinned in the `dev` extra ({dev}). An unpinned linter in CI is a build that "
        f"breaks when someone else ships a release"
    )
    assert re.fullmatch(r"ruff==\d+\.\d+\.\d+", pins[0].replace(" ", "")), (
        f"expected an exact ruff pin, got {pins[0]!r}"
    )


def test_ci_runs_the_real_ephemeris_legs_rather_than_skipping_them():
    """A job that reports the Horizons cross-check green must have actually run it.

    Until 2026-09-09 the `spice` job reported `484 passed, 8 skipped` on every run, and those
    eight were the Psyche and Horizons legs -- the kernels were not in CI, so the strongest
    external claim this project makes had never once been checked there. It was protected against
    regression on one developer's machine.

    Three things have to hold together, and each is useless alone: the cache must be restored, a
    miss must be fetched, and the suite must be told the kernels are REQUIRED. Without the third,
    a failed fetch returns the suite to skipping and the job goes green having tested nothing --
    which is the shape DEV-26 catalogued and this is the fourth instance of.
    """
    import yaml

    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"))
    steps = workflow["jobs"]["spice"]["steps"]

    assert any("actions/cache" in (s.get("uses") or "") for s in steps), (
        "the spice job does not restore a kernel cache, so every run would pay 46 MiB or skip"
    )
    assert any("fetch_pinned_kernels" in (s.get("run") or "") for s in steps), (
        "nothing populates the kernel cache on a miss, so a cold cache means skipped legs"
    )

    strict = [s for s in steps if (s.get("env") or {}).get("FARSIGHT_REQUIRE_KERNELS") == "1"]
    assert strict, (
        "no step sets FARSIGHT_REQUIRE_KERNELS=1, so the real-ephemeris legs SKIP when the cache "
        "is empty and the job reports success having exercised none of them"
    )
    assert any("pytest" in (s.get("run") or "") for s in strict), (
        "FARSIGHT_REQUIRE_KERNELS is set on a step that does not run pytest, so it constrains "
        "nothing -- the variable is only read by the test fixtures"
    )


def test_the_kernel_requirement_is_honoured_rather_than_merely_declared():
    """`FARSIGHT_REQUIRE_KERNELS=1` must turn a missing kernel into a failure, not a skip.

    Asserted against the helper directly, because the CI-shape test above can only see that the
    variable is set. A variable nothing reads would satisfy that test and change nothing.
    """
    import os

    import pytest

    from ._guards import REQUIRE_KERNELS_ENV, skip_or_fail_on_missing_kernels

    previous = os.environ.get(REQUIRE_KERNELS_ENV)
    os.environ[REQUIRE_KERNELS_ENV] = "1"
    try:
        with pytest.raises(AssertionError, match="FAILURE rather than a skip"):
            skip_or_fail_on_missing_kernels("pretend the cache is empty")
    finally:
        if previous is None:
            os.environ.pop(REQUIRE_KERNELS_ENV, None)
        else:
            os.environ[REQUIRE_KERNELS_ENV] = previous
