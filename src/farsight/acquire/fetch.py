"""Acquisition: the only place in FarSight that reaches the network.

ADR-012 decision 1: "The runner and the verifier make zero network calls, ever. There is no
offline mode and no online mode." Acquisition is a separate command on a separate code path, and
``farsight.acquire`` is the only package permitted to import an HTTP library — with the CLI's
``fetch`` subcommand as its only importer. The import-linter contract
``no_network_in_truth_loop`` is what makes that structural rather than a convention.

**The hash is declared before the bytes arrive, not derived from them.** ``fetch_kernel`` takes
``expect_sha256`` and refuses anything else. Hashing whatever turned up and recording that would
make the record a description of what was received rather than a check on it — which is the
difference between provenance and a log line. This is why the signature is a *precondition*: the
caller has to have got the digest from somewhere else (a publisher's manifest, a paper, a prior
package) for the fetch to mean anything.

**The transport is injected**, which is why this module is fully testable offline. ``opener`` is a
callable taking a URL and returning bytes; the default reaches the network, and every test passes
a function that returns bytes from memory. The network is then the *only* untested line, rather
than a reason the whole path goes untested.
"""

from __future__ import annotations

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
    expect_sha256: str,
    cache: KernelCache,
    *,
    license_note: str,
    modified: bool = False,
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

    actual = sha256_bytes(data)
    if actual != expect_sha256:
        raise AcquisitionError(
            f"{url!r} returned bytes hashing to {actual}, not the {expect_sha256} declared. "
            f"The digest is a precondition, not a description: it has to come from somewhere "
            f"other than the download for the fetch to mean anything."
        )

    path = cache.put(data, expect_sha256)
    artifact = DataArtifact(
        url=url,
        sha256=expect_sha256,
        size_bytes=len(data),
        modified=modified,
        license_note=license_note,
    )
    return artifact, path
