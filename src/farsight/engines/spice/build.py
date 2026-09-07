"""The SPICE adapter's own build identity. ADR-026, ADR-019.

Lives here, and not in ``engines/environment.py``, because the ``geometry_is_not_an_engine``
contract makes ``spiceypy`` importable only under ``farsight.engines.spice``. That boundary is the
reason this file exists: the environment probe needs to know which CSPICE produced the numbers,
and the only module allowed to ask is this one.

ADR-026 calls the value an ``install_fingerprint`` and lets an adapter declare how it computes one
-- ``wheel_digest``, ``declared_file_set`` or ``container_digest``. This is the declared-file-set
form: the CSPICE shared objects inside the installed ``spiceypy`` package, by SHA-256.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["FINGERPRINT_METHOD", "install_fingerprint", "toolkit_version"]

FINGERPRINT_METHOD = "declared_file_set"


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def toolkit_version() -> str | None:
    """The CSPICE toolkit version, or None when the `spice` extra is absent.

    Calling it also FORCES the shared object to be mapped, which is the point: the adapter imports
    spiceypy lazily, so a probe that only inspected `sys.modules` would report an environment with
    no CSPICE in it and hash a predicate that omits the library the geometry depends on.
    """
    try:
        import spiceypy
    except ImportError:
        return None
    return str(spiceypy.tkvrsn("TOOLKIT"))


def install_fingerprint() -> list[str]:
    """SHA-256 of every CSPICE object in the installed package, sorted. Empty without the extra."""
    try:
        import spiceypy
    except ImportError:
        return []

    spiceypy.tkvrsn("TOOLKIT")   # map it before measuring it
    module_file = getattr(spiceypy, "__file__", None)
    if not module_file:
        return []

    digests = set()
    for candidate in Path(module_file).parent.rglob("*cspice*"):
        if candidate.is_file():
            digest = _sha256_file(candidate)
            if digest:
                digests.add(digest)
    return sorted(digests)
