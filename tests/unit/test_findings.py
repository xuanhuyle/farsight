"""`FINDINGS.md` summarises evidence it does not hold, so it is checked against that evidence.

A summary document drifts in a way nothing else in this repository does: the memos stay correct
while the summary quietly goes stale, and a reader who trusts the summary is reading a number that
no longer appears anywhere. Worse, the drift is invisible -- a wrong figure in a table looks exactly
like a right one.

So every number in the "Findings at a glance" table must appear verbatim in the memo cited in the
same row, and every path the document links to must exist. This checks the table, not the prose:
the prose is held to the memos by review, the table by this test. What that buys is that the
headline figures -- the ones anyone will quote -- cannot silently diverge from their source.

Deliberately NOT checked: the commit hashes in the ordering table. Verifying them needs full git
history, and CI checks out shallow, so the test would fail on a correct repository for a reason
that has nothing to do with the document.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FINDINGS = REPO / "FINDINGS.md"

# A row of the glance table: | finding | number | [label](path) |
ROW = re.compile(
    r"^\|\s*(?P<finding>[^|]+?)\s*\|\s*(?P<number>[^|]+?)\s*"
    r"\|\s*\[[^\]]+\]\((?P<path>[^)]+)\)\s*\|$"
)
LINK = re.compile(r"\[[^\]]+\]\((?P<path>[^)#]+)\)")

# A floor, well under the true count, so a scan that silently finds nothing is loud. An exact count
# would need editing whenever a finding is added, which is the kind of maintenance that gets a
# check deleted instead of updated.
MINIMUM_ROWS = 15


def _text() -> str:
    text = FINDINGS.read_text(encoding="utf-8")
    assert len(text) > 3000, f"FINDINGS.md is implausibly short: {len(text)} bytes"
    return text


def _glance_rows() -> list[tuple[str, str, str]]:
    """Every (finding, number, cited path) in the glance table."""
    section = _text().split("## Findings at a glance", 1)
    assert len(section) == 2, "FINDINGS.md has no 'Findings at a glance' section"
    rows = []
    for line in section[1].splitlines():
        if line.startswith("## "):
            break
        match = ROW.match(line.strip())
        if match:
            rows.append((match["finding"], match["number"], match["path"]))
    return rows


def test_the_scan_finds_the_rows_that_exist():
    """A regex that matched nothing would make every assertion below vacuous and green."""
    rows = _glance_rows()
    assert len(rows) >= MINIMUM_ROWS, (
        f"parsed only {len(rows)} rows from the glance table, expected at least {MINIMUM_ROWS} -- "
        f"either findings were deleted or the table's shape changed and this regex no longer fits"
    )
    cited = {path for _, _, path in rows}
    assert len(cited) >= 3, (
        f"the table cites {len(cited)} memos; all three experiments should appear"
    )


@pytest.mark.parametrize("finding, number, path", _glance_rows(),
                         ids=lambda value: str(value)[:40])
def test_a_quoted_number_appears_in_the_memo_it_cites(finding, number, path):
    memo = (REPO / path).resolve()
    assert memo.exists(), f"FINDINGS.md cites {path}, which does not exist"
    assert number in memo.read_text(encoding="utf-8"), (
        f'FINDINGS.md says "{number}" for "{finding}", citing {path}, '
        f"but that string does not appear in it"
    )


def test_every_link_in_the_document_resolves():
    """Repository-relative links only; external URLs are not this test's business."""
    checked = 0
    for match in LINK.finditer(_text()):
        path = match["path"]
        if path.startswith(("http://", "https://", "mailto:")):
            continue
        assert (REPO / path).exists(), f"FINDINGS.md links to {path}, which does not exist"
        checked += 1
    assert checked >= MINIMUM_ROWS, f"only {checked} internal links checked; the scan found too few"


def test_the_document_makes_no_claim_of_external_review():
    """The forbidden vocabulary, enforced rather than remembered.

    These phrases are barred unless genuinely true, and none of them is true of this work. A
    summary written for other people is exactly where one would slip in.
    """
    # Wrapped lines are joined first: the disclaimer that uses these words runs across a line
    # break, and splitting on newlines would separate a phrase from the "not" that governs it.
    flat = " ".join(_text().lower().split())
    sentences = re.split(r"(?<=[.!?]) ", flat)
    assert len(sentences) > 30, (
        f"sentence split produced {len(sentences)} pieces; it is not working"
    )

    for phrase in ("expert validated", "expert-validated", "independently validated",
                   "certified", "flight qualified", "flight-qualified",
                   "verified by aerospace experts", "peer reviewed", "peer-reviewed"):
        for sentence in sentences:
            if phrase not in sentence:
                continue
            # Saying "this is not certified" is required; saying "this is certified" is barred.
            assert any(mark in sentence for mark in ("not ", "never ", "no claim", "without ")), (
                f'FINDINGS.md uses "{phrase}" in a sentence that does not deny it: '
                f'"{sentence[:140]}"'
            )
    assert "not externally expert-reviewed" in flat, (
        "FINDINGS.md must carry the ADR-030 status line stating the absence of expert review"
    )
