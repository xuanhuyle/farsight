"""Acquisition: the only place in FarSight that reaches the network.

ADR-012 decision 1: "The runner and the verifier make zero network calls, ever. There is no
offline mode and no online mode." Acquisition is a separate command on a separate code path, and
``farsight.acquire`` is the only package permitted to import an HTTP library — with the CLI's
``fetch`` subcommand as its only importer. The import-linter contract
``no_network_in_truth_loop`` is what makes that structural rather than a convention.

**The hash is declared before the bytes arrive, not derived from them.** Hashing whatever turned
up and recording that would make the record a description of what was received rather than a check
on it — the difference between provenance and a log line. The signature is a *precondition*: the
caller has to have got a digest from somewhere else for the fetch to mean anything, and
``fetch_kernel`` refuses when it is given none.

**Two digests, because publishers and we address files differently.** ``expect_sha256`` is
FarSight's own content address. ``expect_md5`` is what a publisher stated, and PDS4 bundles state
MD5 — including the Psyche SPICE bundle, whose ``checksum.tab`` covers every kernel in it. Either
may be given and both are checked when present, which is what lets a FIRST acquisition be verified
at all: before this, the first fetch of a file could only be trust-on-first-use, because our
address is not knowable until the bytes exist (DEV-16).

**What an MD5 from a publisher is worth, stated precisely.** It establishes that these bytes are
the bytes that publisher listed. It defends against transport corruption and against substitution
by anyone who cannot construct an MD5 collision. It is **not** collision-resistant and is not a
defence against a prepared second preimage, so it does not make the chain cryptographically
strong — it makes it *independently attested*, which trust-on-first-use never was. FarSight's own
address stays SHA-256; the MD5 is a cross-check against the publisher, never a substitute.

**The transport is injected**, which is why this module is fully testable offline. ``opener`` is a
callable taking a URL and returning bytes; the default reaches the network, and every test passes
a function that returns bytes from memory. The network is then the *only* untested line, rather
than a reason the whole path goes untested.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from farsight.registry.kernel_cache import KernelCache, sha256_bytes
from farsight.schemas.errors import FarSightError
from farsight.schemas.knowledge import DataArtifact

__all__ = ["MAX_FETCH_BYTES", "AcquisitionError", "Opener", "default_opener", "fetch_kernel"]

# A ceiling so a misdirected URL cannot fill the disk before anyone notices. Generous against the
# real cases -- a planetary ephemeris SPK is a few hundred MB -- and it exists because the cache
# is never garbage-collected, so bytes written here are written permanently.
MAX_FETCH_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB


class AcquisitionError(FarSightError, OSError):
    """Bytes did not match the declared digest, or the transport failed.

    Maps to CLI exit code 30, ``acquisition_failure`` (ADR-024).
    """


class Opener(Protocol):
    """Fetch a URL and return its bytes. The seam that keeps this module testable offline."""

    def __call__(self, url: str) -> bytes: ...


def default_opener(url: str) -> bytes:
    """The real transport. The one function in FarSight that opens a socket.

    ``urllib`` is imported inside the function rather than at module scope so that importing
    ``farsight.acquire`` -- which the CLI does to register its verb -- does not itself pull a
    networking stack into the process.
    """
    from urllib.parse import urlparse  # at point of use; see this function's docstring
    from urllib.request import urlopen

    scheme = urlparse(url).scheme
    if scheme not in {"https", "file"}:
        raise AcquisitionError(
            f"refusing to fetch {url!r}: scheme {scheme!r} is not https. Plaintext transport "
            f"would let the bytes be altered in flight, and although the digest check would "
            f"catch that, the honest fix is not to offer the channel."
        )
    # The URL scheme is checked above, which is what a scheme-audit rule would ask for.
    with urlopen(url) as response:
        return response.read(MAX_FETCH_BYTES + 1)


def fetch_kernel(
    url: str,
    expect_sha256: str | None,
    cache: KernelCache,
    *,
    license_note: str,
    modified: bool = False,
    expect_md5: str | None = None,
    opener: Callable[[str], bytes] | None = None,
) -> tuple[DataArtifact, Path]:
    """Fetch ``url``, verify it against ``expect_sha256``, cache it, and describe it.

    Returns the ``DataArtifact`` record and the path the bytes landed at. The record is *not*
    stored here: writing it to the object store is the caller's step, because the caller is what
    holds the ``Provenance`` (who fetched it, when) that the envelope's unhashed half carries.

    Note what is absent from the returned record: a timestamp. ADR-012's sketch lists
    ``fetched_at_utc``, and ADR-001 forbids it inside the hashed half — two fetches of identical
    bytes must produce one address, or the deduplication the cache exists for is gone. See DEV-12.
    """
    if expect_sha256 is None and expect_md5 is None:
        raise AcquisitionError(
            "fetch_kernel needs a digest declared before the bytes arrive: `expect_sha256` (our "
            "content address, known for anything fetched before) or `expect_md5` (what the "
            "publisher stated, e.g. a PDS4 bundle's checksum.tab). With neither, this would hash "
            "whatever turned up and call the result provenance"
        )

    transport = opener or default_opener

    try:
        data = transport(url)
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"transport failed for {url!r}: {exc}") from exc

    if len(data) > MAX_FETCH_BYTES:
        raise AcquisitionError(
            f"{url!r} returned more than the {MAX_FETCH_BYTES} byte ceiling. The cache is never "
            f"garbage-collected, so an unbounded fetch spends disk permanently."
        )

    # The publisher's digest is checked FIRST, because it is the only one that can be wrong in an
    # interesting way on a first acquisition: our own address is computed from these same bytes
    # and so cannot disagree with them, while the publisher's is an independent statement about
    # what should have arrived.
    if expect_md5 is not None:
        actual_md5 = hashlib.md5(data).hexdigest()
        if actual_md5 != expect_md5.lower():
            raise AcquisitionError(
                f"{url!r} returned bytes with MD5 {actual_md5}, not the {expect_md5} the "
                f"publisher listed. These are not the bytes that were published, so nothing "
                f"downstream of them would be about the file the manifest describes."
            )

    actual = sha256_bytes(data)
    if expect_sha256 is not None and actual != expect_sha256:
        raise AcquisitionError(
            f"{url!r} returned bytes hashing to {actual}, not the {expect_sha256} declared. "
            f"The digest is a precondition, not a description: it has to come from somewhere "
            f"other than the download for the fetch to mean anything."
        )

    path = cache.put(data, actual)
    artifact = DataArtifact(
        url=url,
        sha256=actual,
        size_bytes=len(data),
        modified=modified,
        license_note=license_note,
    )
    return artifact, path
