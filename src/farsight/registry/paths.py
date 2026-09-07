"""Where FarSight keeps its own state.

ADR-012 decision 4 fixes the split: "configuration, object registry, ledger and audit log live
under ``$FARSIGHT_HOME``; mission data lives only under operator-declared ``data_roots``, and a
path outside them is refused rather than copied." ADR-016 anchors the kernel cache at
``$FARSIGHT_HOME/kernels/<first2>/<sha256>``.

**The default location is a decision no record makes**, and it is taken here rather than left to
whichever module needs a path first. ``FARSIGHT_HOME`` in the environment wins; otherwise
``%LOCALAPPDATA%\\farsight`` on Windows and ``~/.local/share/farsight`` on POSIX, following each
platform's own convention for application state rather than inventing a third. Recorded as
DEV-14, because "workspace", "working store" and "output root" appear across four records and are
defined in none of them.

Nothing here creates directories. A path resolver that quietly makes a tree on import turns a
typo in an environment variable into a scattering of empty folders, and makes `--home` hard to
test. Creation belongs to the writer, which is :func:`farsight.registry.atomic.write_atomic`.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["HOME_ENV_VAR", "farsight_home", "kernel_cache_root", "objects_root"]

HOME_ENV_VAR = "FARSIGHT_HOME"


def farsight_home(override: str | Path | None = None) -> Path:
    """FarSight's state directory.

    ``override`` is the CLI's ``--home`` flag (ADR-024 makes it global on every command) and wins
    over the environment, so a single command can be pointed elsewhere without exporting anything.
    """
    if override is not None:
        return Path(override).expanduser()

    from_env = os.environ.get(HOME_ENV_VAR)
    if from_env:
        return Path(from_env).expanduser()

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "farsight"
        return Path.home() / "AppData" / "Local" / "farsight"
    return Path.home() / ".local" / "share" / "farsight"


def objects_root(home: str | Path | None = None) -> Path:
    """The object store root (ADR-011 decision 1). Documents live under ``objects/`` inside it."""
    return farsight_home(home)


def kernel_cache_root(home: str | Path | None = None) -> Path:
    """The kernel byte cache (ADR-016 decision 5), the fourth store.

    Separate from the object store on purpose: that store "is walked in full by ``verify``, by
    package build and by dedup", so putting multi-hundred-megabyte binaries in the walk would make
    all three proportional to kernel volume.
    """
    return farsight_home(home) / "kernels"
