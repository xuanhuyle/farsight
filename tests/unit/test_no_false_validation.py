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
    r"instead of|do not|don't|cannot|refuse|ban|Forbidden|`|\"|“|‘|'",
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
    entries = re.split(r"^## ", text, flags=re.M)[1:]
    assert entries, "the deviations ledger must contain at least one entry"

    required = ["**Record:**", "**Code:**", "**What differs.**", "**Why.**",
                "**Closes by:**", "**Status:**"]
    for entry in entries:
        title = entry.splitlines()[0].strip()
        for field in required:
            assert field in entry, f"deviation entry {title!r} is missing {field}"

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
    entries = re.split(r"^## ", text, flags=re.M)[1:]
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

    The other two legs -- that no ``FreezeTimeError`` is raised under ``engines/``, and that the
    worker returns a ``RunOutcome`` for every injected error -- need the worker, and are not
    silently skipped: they are named here so the gap is visible when this test passes.
    """
    import ast

    src = REPO / "src" / "farsight"
    known = {"FarSightError"}
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
            base_names |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
            looks_like_exception = (
                node.name.endswith("Error")
                or bool(base_names & {"Exception", "BaseException", "ValueError", "RuntimeError"})
            )
            if not looks_like_exception:
                continue
            if node.name == "FarSightError":
                continue
            if not (base_names & known):
                offenders.append(
                    f"{path.relative_to(REPO).as_posix()}:{node.lineno}: {node.name}"
                    f"({', '.join(sorted(base_names)) or 'object'})"
                )
            else:
                known.add(node.name)
    assert not offenders, (
        "exceptions outside the FarSightError hierarchy (ADR-023 decision 8); each is a site "
        "the worker's exception-to-failure_class mapping cannot classify:\n  "
        + "\n  ".join(offenders)
    )
