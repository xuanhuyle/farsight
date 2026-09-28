"""A digest recorded in a memo must be the digest a reader will compute.

Every experiment memo vouches for its evidence files by SHA-256. That claim is only worth
something if it survives leaving this machine, and it nearly did not: MEASURED 2026-09-28, the
Pioneer run was committed with CRLF endings while git stored LF, so `RESULT.md` recorded a digest
no one else could reproduce. `.gitattributes` now pins those bytes, and this test checks the
arithmetic the memo asserts rather than trusting that the next memo remembers to.

The failure this guards against is silent in the worst way: the file is present, the memo is
present, the digest is a plausible 64 hex characters, and only someone who actually hashes the
file finds out.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO / "experiments"

# "- `evidence/run.txt` — ... sha256 `<64 hex>`", across however many lines the bullet wraps to.
CLAIM = re.compile(
    r"`(?P<path>[\w./-]+\.(?:txt|jsonl|json|csv))`(?P<between>[^`]*?)sha256\s+`(?P<digest>[0-9a-f]{64})`",
    re.DOTALL,
)
SIZE = re.compile(r"([\d,]+) bytes")


def _claims() -> list[tuple[Path, Path, str, str | None]]:
    """Every (memo, file, digest, byte count) a memo asserts."""
    found = []
    for memo in sorted(EXPERIMENTS.glob("*/*.md")):
        text = memo.read_text(encoding="utf-8")
        for match in CLAIM.finditer(text):
            size = SIZE.search(match.group("between"))
            found.append((
                memo,
                (memo.parent / match.group("path")).resolve(),
                match.group("digest"),
                size.group(1).replace(",", "") if size else None,
            ))
    return found


def test_the_scan_finds_the_claims_that_exist():
    """A regex that matches nothing would make every test below vacuous."""
    claims = _claims()
    assert len(claims) >= 2, f"expected at least two recorded digests, found {len(claims)}"
    memos = {memo.parent.name for memo, _, _, _ in claims}
    assert "pioneer_thermal" in memos and "dsn_now_probe" in memos


@pytest.mark.parametrize("memo, target, digest, size", _claims(),
                         ids=lambda value: getattr(value, "name", str(value)[:16]))
def test_a_recorded_digest_matches_the_file_it_names(memo, target, digest, size):
    rel = memo.relative_to(REPO)
    assert target.exists(), f"{rel} records a digest for {target}, which does not exist"
    data = target.read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, (
        f"{rel} records sha256 {digest[:16]}... for {target.name}, "
        f"but the file hashes to {hashlib.sha256(data).hexdigest()[:16]}..."
    )
    if size is not None:
        assert len(data) == int(size), (
            f"{rel} says {target.name} is {size} bytes; it is {len(data)}"
        )


@pytest.mark.parametrize("target", [target for _, target, _, _ in _claims()],
                         ids=lambda path: path.name)
def test_evidence_files_carry_no_carriage_returns(target):
    """The defect that started this: CRLF in the working copy, LF in the repository."""
    assert b"\r\n" not in target.read_bytes(), (
        f"{target.name} has CRLF line endings, so its digest depends on which machine "
        f"checked it out. `.gitattributes` should be pinning it with -text."
    )
