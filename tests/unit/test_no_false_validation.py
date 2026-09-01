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
