"""The kernel byte cache: the fourth store, keyed only by content.

ADR-016 decision 5. Kernels live at ``<cache>/<first2>/<sha256>`` **with no extension and no
logical name in the path**, so nothing can resolve a kernel by anything but its content. A file
called ``naif0012.tls`` in a cache would invite exactly the ambient-kernel-directory habit the
record rejects; a bare digest cannot be reached by guessing a name.

**Read-only to everything except one writer.** Only ``farsight.acquire``, via ``farsight fetch``,
writes here. An AST lint (``test_registry_lint``) fails on any write to the cache root from
anywhere else, because a second writer means bytes could enter the cache without having been
verified against a declared hash.

**Verified on insert and on furnish, memoized per process.** Re-hashing a multi-hundred-megabyte
SPK on every furnish is the one place this rule gets expensive, so a verified ``(path, sha256)``
pair is remembered for the life of the process — which is what lets ADR-002's single
``reusable_worker`` grant re-furnish per run while re-hashing once per process.

**The residue is named rather than hidden**, in ADR-016's own words: another process could modify
a cache file mid-campaign, and nothing catches that until the next process starts. Memoizing is
what makes the check affordable, and forgetting between processes is what keeps it honest.

**Nothing is ever evicted.** No garbage collection, no ``prune``, not in the MVP: a cache that can
delete a kernel a shipped package references is a way to make a package unverifiable by accident.
The cost — a store that only grows, dominated by files we did not write — is accepted knowingly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from farsight.registry.atomic import write_atomic
from farsight.schemas.common import is_ref
from farsight.schemas.errors import FarSightError

__all__ = [
    "KernelCacheError",
    "KernelCache",
    "sha256_bytes",
    "sha256_file",
    "READ_CHUNK_BYTES",
]

# Files here are large, so hashing streams rather than loading. 1 MiB is a compromise between
# syscall count and peak memory; it is not tuned, and `bench_kernel_verify` (ADR-016 Enforcement
# 7) is the measurement that would justify changing it.
READ_CHUNK_BYTES = 1024 * 1024


class KernelCacheError(FarSightError, ValueError):
    """Bytes in the cache do not match the address they are filed under, or a path is malformed."""


def sha256_bytes(data: bytes) -> str:
    """The bare lowercase 64-hex digest of ``data`` (ADR-001 rule 7: no algorithm prefix)."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Stream a file and return its digest, without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:  # noqa: FS001 - read-only; the write lint targets writes
        while chunk := handle.read(READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


class KernelCache:
    """A content-addressed store of raw bytes, rooted at a directory.

    Distinct from :class:`farsight.registry.objects.ObjectStore` and deliberately so: this one
    holds opaque bytes with no envelope and no JSON, and is not walked by ``verify``.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        # (path, sha256) pairs verified in THIS process. Never persisted: a memo that survived
        # the process would be a claim about bytes nobody has read since.
        self._verified: set[tuple[str, str]] = set()

    def path_for(self, sha256: str) -> Path:
        """Where the bytes with digest ``sha256`` live. No extension, by decision."""
        if not is_ref(sha256):
            raise KernelCacheError(
                f"{sha256!r} is not a bare 64-hex digest (ADR-001 rule 7). The cache is keyed "
                f"only by content, so there is no name to fall back to."
            )
        return self.root / sha256[:2] / sha256

    def has(self, sha256: str) -> bool:
        return self.path_for(sha256).exists()

    def put(self, data: bytes, expect_sha256: str) -> Path:
        """Insert ``data``, verifying it hashes to ``expect_sha256`` first.

        Verified **on insert**, so bytes that do not match what the caller declared never reach
        the cache at all. Inserting bytes already present is a no-op — the content is the address,
        so there is nothing a second copy could say that the first does not.
        """
        actual = sha256_bytes(data)
        if actual != expect_sha256:
            raise KernelCacheError(
                f"bytes hash to {actual}, not to the {expect_sha256} the caller declared. "
                f"Nothing enters the cache unverified: an unchecked insert would put a file "
                f"under an address that does not describe it, and every later read would "
                f"inherit the lie."
            )
        destination = self.path_for(expect_sha256)
        if destination.exists():
            return destination
        write_atomic(destination, data)
        return destination

    def get_path(self, sha256: str, *, verify: bool = True) -> Path:
        """The path to cached bytes, re-verified once per process unless already checked.

        ``verify=False`` exists for callers that have just written the file and hold the digest
        from that write; it is not an escape hatch for skipping the check on a read.
        """
        destination = self.path_for(sha256)
        if not destination.exists():
            raise KernelCacheError(f"no cached bytes for {sha256} (looked in {destination})")

        if not verify:
            return destination

        key = (str(destination), sha256)
        if key in self._verified:
            return destination

        actual = sha256_file(destination)
        if actual != sha256:
            raise KernelCacheError(
                f"cache file {destination} hashes to {actual}, not to the {sha256} its own path "
                f"claims. The path IS the assertion, so this file was replaced or corrupted "
                f"after it was stored."
            )
        self._verified.add(key)
        return destination

    def verified_count(self) -> int:
        """How many (path, digest) pairs this process has checked. For the memo's own tests."""
        return len(self._verified)
