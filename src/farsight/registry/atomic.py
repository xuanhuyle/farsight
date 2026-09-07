"""Atomic file writes: the only sanctioned way anything under ``src/farsight/`` writes a file.

ADR-011 decision 4, reproduced as the implementation rather than paraphrased:

    create ``<final>.tmp.<pid>.<counter>`` in the same directory, write, ``flush()``,
    ``os.fsync(fileno())``, close, ``os.replace(tmp, final)``, then ``fsync`` the directory
    file descriptor on POSIX.

Same directory matters: ``os.replace`` is only atomic within a filesystem, so a temp file in
``/tmp`` and a destination on another volume would silently become a copy with a window in the
middle. ``os.replace`` rather than ``os.rename`` matters on Windows, where ``rename`` refuses to
overwrite an existing file and ``replace`` does not -- ADR-011's Enforcement item 3 names that
distinction explicitly.

**The Windows asymmetry is stated rather than papered over.** There is no directory fsync on
Windows, so after a power loss the rename may not have reached stable storage even though the
file contents did. ADR-011 does not try to close that gap; it makes the *ledger the arbiter*
instead: a file that exists on disk with no committed ``ok`` row is garbage, and ``resume``
re-executes that run. Recovery never has to guess whether a file is complete, which is a stronger
position than a durability claim this platform cannot honour.

**Bytes in, bytes out.** Every function here takes ``bytes``. Text mode is not offered, because
on Windows it would translate ``\\n`` into ``\\r\\n`` and change the very bytes that were about to
be hashed -- the failure would appear as a cross-platform hash mismatch far from its cause.
"""

from __future__ import annotations

import itertools
import os
from pathlib import Path

from farsight.schemas.errors import FarSightError

__all__ = ["AtomicWriteError", "write_atomic"]

_counter = itertools.count()


class AtomicWriteError(FarSightError, OSError):
    """A write could not be completed atomically.

    ``OSError`` as well as ``FarSightError`` so that callers already handling filesystem failures
    catch it naturally, and ADR-023's rule that every exception under ``src/farsight/`` sits in
    the hierarchy still holds.
    """


def write_atomic(path: str | Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` atomically. Returns the path written.

    After this returns, ``path`` holds either the complete new bytes or -- if the process died
    partway -- its previous content, never a truncated mixture. A reader never observes a
    half-written file.

    The temp file is removed on failure, so a crashed write leaves no debris beside the
    destination for a later directory walk to trip over.
    """
    final = Path(path)
    if not isinstance(data, (bytes, bytearray)):
        raise AtomicWriteError(
            f"write_atomic takes bytes, not {type(data).__name__}. Text mode is not offered "
            f"because on Windows it would translate '\\n' into '\\r\\n' and change the bytes "
            f"about to be hashed."
        )

    final.parent.mkdir(parents=True, exist_ok=True)
    # Same directory as the destination: os.replace is atomic only within one filesystem.
    tmp = final.with_name(f"{final.name}.tmp.{os.getpid()}.{next(_counter)}")

    try:
        with open(tmp, "wb") as handle:  # noqa: FS001 - this module is the sanctioned writer
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, final)
    except BaseException:
        # BaseException, not Exception: a KeyboardInterrupt mid-write should still not leave a
        # temp file behind, and the raise re-propagates it unchanged.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    _fsync_directory(final.parent)
    return final


def _fsync_directory(directory: Path) -> None:
    """Flush the directory entry on POSIX. A no-op on Windows, deliberately.

    Windows has no directory file descriptor to sync. ADR-011 states the asymmetry rather than
    pretending to close it, and puts recovery on the ledger instead: a file with no committed row
    is garbage regardless of whether its rename was durable.
    """
    if os.name != "posix":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
