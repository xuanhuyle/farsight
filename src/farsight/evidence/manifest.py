"""The file manifest and root hash of an evidence package (ADR-007 decision 2).

This module is the reusable half of packaging: it knows how to seal a directory and how to
detect that a sealed directory has changed. It knows nothing about what is in the directory,
which is why it can serve an experiment it has never heard of.

**The root hash is a one-level Merkle root over a flat file manifest.** ``file_hashes.json``
maps every relative POSIX path in the package to the SHA-256 of that file's bytes, and
``root_hash = sha256(JCS(file_hashes.json content))``. ADR-007 keeps the tree one level deep on
purpose: an auditor can reproduce this with ``sha256sum`` and any JCS implementation, which a
deep tree cannot claim.

**Why ``hashes/`` is excluded from its own manifest.** A manifest that listed
``hashes/file_hashes.json`` would have to contain that file's digest, which depends on the
manifest -- there is no fixed point. So the two files under ``hashes/`` are the seal, not part
of what is sealed, and everything else in the package is covered. The consequence is stated
rather than hidden: an attacker who rewrites a file *and* re-seals produces a package that is
internally consistent with a different root hash, which is why the root hash has to be
transported or signed separately (ADR-012's signing seam attaches here).

This module never imports ``farsight.engines`` -- the ``auditor_boundary`` import contract
enforces it -- because verification has to run on an auditor's laptop with zero engine extras.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from farsight.hashing.canonical import content_hash
from farsight.registry.atomic import write_atomic

__all__ = [
    "FILE_HASHES_PATH",
    "HASHES_DIR",
    "ROOT_HASH_PATH",
    "IntegrityProblem",
    "check_integrity",
    "file_digests",
    "read_file_hashes",
    "root_hash_of",
    "seal",
]

HASHES_DIR = "hashes"
FILE_HASHES_PATH = "hashes/file_hashes.json"
ROOT_HASH_PATH = "hashes/root_hash.txt"


@dataclass(frozen=True)
class IntegrityProblem:
    """One thing wrong with a sealed package, named precisely enough to act on.

    ``kind`` is one of ``missing``, ``unlisted``, ``modified`` or ``root``. ``path`` is the
    package-relative POSIX path, or ``hashes/root_hash.txt`` for a root mismatch.
    """

    kind: str
    path: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.path} -- {self.detail}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_digests(root: str | Path) -> dict[str, str]:
    """Every file under ``root`` except the seal itself, as {relative POSIX path: sha256}.

    Sorted, so the mapping's canonical form is stable regardless of filesystem walk order.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(f"{HASHES_DIR}/"):
            continue
        digests[relative] = _sha256_file(path)
    if not digests:
        raise ValueError(
            f"{root} contains no files to seal. An empty manifest would hash to a stable value "
            f"and claim to attest to a package, which is worse than refusing."
        )
    return dict(sorted(digests.items()))


def root_hash_of(digests: dict[str, str]) -> str:
    """``sha256(JCS(file_hashes))`` -- ADR-007 decision 2, reproducible with any JCS tool."""
    return content_hash(digests)


def seal(root: str | Path) -> str:
    """Write ``hashes/file_hashes.json`` and ``hashes/root_hash.txt``. Returns the root hash.

    Sealing twice over unchanged content produces the identical root hash and identical bytes,
    which is what makes a package diffable at all.
    """
    root = Path(root)
    digests = file_digests(root)
    root_hash = root_hash_of(digests)
    # Indented JSON for a human reading the package, sorted for a stable diff. The bytes of this
    # file are NOT what the root hash is over -- that is the canonical form of its content, so a
    # reformat cannot change the package's identity.
    write_atomic(
        root / FILE_HASHES_PATH,
        (json.dumps(digests, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    write_atomic(root / ROOT_HASH_PATH, (root_hash + "\n").encode("utf-8"))
    return root_hash


def read_file_hashes(root: str | Path) -> dict[str, str]:
    """The recorded manifest, or a raised error naming what is missing."""
    path = Path(root) / FILE_HASHES_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing, so this directory is not a sealed package. Run the builder, or "
            f"check that you are pointing at the package root rather than a parent."
        )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} does not contain a JSON object of path -> digest")
    return loaded


def check_integrity(root: str | Path) -> list[IntegrityProblem]:
    """Every file the manifest claims, checked against what is on disk. Empty list means intact.

    Reports all four failure kinds rather than the first one found, because an auditor wants the
    shape of the damage, not its alphabetically first instance.
    """
    root = Path(root)
    recorded = read_file_hashes(root)
    actual = file_digests(root)
    problems: list[IntegrityProblem] = []

    for path, digest in recorded.items():
        if path not in actual:
            problems.append(
                IntegrityProblem("missing", path, "listed in the manifest, not on disk")
            )
        elif actual[path] != digest:
            problems.append(
                IntegrityProblem(
                    "modified", path,
                    f"manifest says {digest[:16]}..., file hashes to {actual[path][:16]}...",
                )
            )
    for path in actual:
        if path not in recorded:
            problems.append(
                IntegrityProblem("unlisted", path, "present on disk, absent from the manifest")
            )

    root_hash_file = root / ROOT_HASH_PATH
    if not root_hash_file.exists():
        problems.append(IntegrityProblem("root", ROOT_HASH_PATH, "the sealed root hash is missing"))
    else:
        recorded_root = root_hash_file.read_text(encoding="utf-8").strip()
        expected = root_hash_of(recorded)
        if recorded_root != expected:
            problems.append(
                IntegrityProblem(
                    "root", ROOT_HASH_PATH,
                    f"file says {recorded_root[:16]}..., the manifest hashes to {expected[:16]}...",
                )
            )
    return problems
