"""Writing a channel, and hashing it so that the hash is over the numbers. ADR-011, ADR-020.

**The channel hash is not the file's hash.** ADR-011 decision 2 makes a channel's identity
``JCS(header) || 0x00 || payload`` rather than the ``.npy`` container's bytes, and that decoupling
buys a specific thing: nothing depends on NumPy's header byte layout being stable across
versions, which nobody has verified and which the Tier-A goldens must not rest on. The ``.npy``
file is *also* hashed by path in ``file_hashes.json`` for file-level tamper evidence, and those
two hashes answer different questions.

**The grid is in the header, and that is the whole of ADR-011's stated hole.** Without it, a
channel computed on a 60-second grid and one computed on a 10-second grid hash identically when
their values happen to match -- so a run re-executed against a different time base would
hash-verify clean. One field closes it, because the grid descriptor is small, exact, and already
hashed as part of the design.

**Non-finite samples are counted, not tolerated.** ADR-023 makes any non-finite sample a
divergence and ADR-020 decision 2 bans NaN as an absence marker, so the manifest records the count
and the first index rather than leaving a reader to discover them. Absence is a lifecycle code
(ADR-020), never a NaN.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.lib import format as np_format

from farsight.hashing.canonical import canonical_bytes, hash_object
from farsight.registry.atomic import write_atomic
from farsight.schemas.channels import validate_channel_name
from farsight.schemas.errors import FarSightError

__all__ = [
    "CHANNEL_DTYPE",
    "ChannelWriteError",
    "channel_hash",
    "channel_header",
    "grid_hash",
    "read_channel",
    "write_channel",
    "write_channels_manifest",
]

# ADR-020 decision 2. Little-endian float64, C-order, axis 0 is the sample axis. The endianness is
# explicit rather than native so that a big-endian machine produces the same bytes, which is what
# makes the hash a statement about the numbers rather than about the machine.
CHANNEL_DTYPE = "<f8"


class ChannelWriteError(FarSightError, ValueError):
    """A channel cannot be written as declared."""


def grid_hash(grid: Any) -> str:
    """``sha256(JCS(sample_grid))`` -- the grid's identity. ADR-020 decision 4.

    Bare 64-hex with no algorithm prefix, the one spelling ADR-001 decision 7 admits inside a
    hashed document.
    """
    return hash_object(grid)


def channel_header(name: str, unit: str, shape: tuple[int, ...], grid_digest: str) -> dict:
    """The hashed header. ADR-011 decision 2, with ADR-020 decision 6's added field.

    Exactly five keys. A sixth would change every published channel hash, so the field list is a
    compatibility surface and not a convenience.
    """
    return {
        "name": name,
        "unit": unit,
        "dtype": CHANNEL_DTYPE,
        "shape": list(shape),
        "grid_hash": grid_digest,
    }


def channel_hash(header: dict, array: np.ndarray) -> str:
    """``sha256(JCS(header) || 0x00 || array.tobytes(order="C"))``.

    The separator byte is not decoration: without it, a header ending in a digit and a payload
    beginning with one would be indistinguishable from a different split of the same bytes.
    """
    if array.dtype != np.dtype(CHANNEL_DTYPE):
        raise ChannelWriteError(
            f"channel array is {array.dtype!r}, not {CHANNEL_DTYPE!r}. The hash is over these "
            f"bytes, so a dtype difference is a different channel, and normalizing silently here "
            f"would hide it"
        )
    digest = hashlib.sha256()
    digest.update(canonical_bytes(header))
    digest.update(b"\x00")
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _as_channel_array(values: Any, *, name: str) -> np.ndarray:
    """Coerce to ``<f8`` C-order, refusing anything whose coercion would be a decision.

    ADR-020 decision 2 is explicit that there are no integer, boolean or string channels, so an
    integer array is not quietly promoted: above 2**53 that promotion is lossy, and a caller who
    meant a categorical channel wants a ``code_map``, not a cast.
    """
    array = np.asarray(values)
    if array.dtype.kind != "f":
        raise ChannelWriteError(
            f"channel {name!r} was handed a {array.dtype!r} array. Every channel is float64 "
            f"(ADR-020 decision 2): there are no integer, boolean or string channels, and a "
            f"categorical channel is a float64 channel with a code_map. Promoting an integer "
            f"array here would be lossy above 2**53 and silent below it"
        )
    # `astype` with an explicit byte order is a representation change and never a value change:
    # it is what makes a big-endian machine emit the same bytes as this one.
    return np.ascontiguousarray(array.astype(CHANNEL_DTYPE, copy=False))


def write_channel(
    directory: str | Path,
    name: str,
    unit: str,
    values: Any,
    grid_digest: str,
    *,
    expect_samples: int | None = None,
) -> dict:
    """Write ``channels/<name>.npy`` and return its manifest row.

    The name reaches the filename verbatim -- no escaping, no hashing, no case folding (ADR-020
    decision 7) -- which is safe only because ADR-017's grammar already excluded the characters
    and the reserved device names that would make it unsafe.
    """
    validate_channel_name(name)
    array = _as_channel_array(values, name=name)

    if array.ndim not in (1, 2):
        raise ChannelWriteError(
            f"channel {name!r} has {array.ndim} dimensions; a channel is (n,) or (n, components) "
            f"with axis 0 the sample axis (ADR-020 decision 2)"
        )
    if expect_samples is not None and array.shape[0] != expect_samples:
        raise ChannelWriteError(
            f"channel {name!r} has {array.shape[0]} samples but the run's grid has "
            f"{expect_samples}. Every channel of a run shares one grid (ADR-020 decision 4), and "
            f"nothing here interpolates the difference away"
        )

    header = channel_header(name, unit, array.shape, grid_digest)
    digest = channel_hash(header, array)

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    # Serialized in memory and written through `write_atomic`, so the file is complete or absent
    # and never half-written -- and so the bytes hashed are the bytes written (ADR-001).
    #
    # `numpy.lib.format.write_array` rather than `np.save`: it is the documented entry point for
    # writing an .npy stream to a file object, and it keeps ADR-011 Enforcement 10's lint honest.
    # That lint looks for `.save()` call sites, and `np.save` into a BytesIO is not a file write
    # -- so using it here would have needed an exemption for a call the rule does not actually
    # mean to catch. Removing the call is better than widening the rule.
    buffer = io.BytesIO()
    np_format.write_array(buffer, array, allow_pickle=False)
    write_atomic(directory / f"{name}.npy", buffer.getvalue())

    nonfinite = ~np.isfinite(array)
    nonfinite_count = int(nonfinite.sum())
    first_nonfinite = int(np.argmax(nonfinite.any(axis=tuple(range(1, array.ndim)))
                                    if array.ndim > 1 else nonfinite)) if nonfinite_count else None

    return {
        "name": name,
        "unit": unit,
        "dtype": CHANNEL_DTYPE,
        "shape": list(array.shape),
        "grid_hash": grid_digest,
        "channel_hash": digest,
        # ADR-020 decision 8: a run that stops early truncates every channel to one index k and
        # the manifest records `samples_written: k`, while the grid descriptor stays unchanged --
        # the grid is a declared input, not a report of what happened. Equal to shape[0] here
        # because `expect_samples` refuses a short channel outright, but the key exists so a
        # reader never has to infer it, and so the manifest model is not closed at eight fields.
        "samples_written": int(array.shape[0]),
        "nonfinite_count": nonfinite_count,
        "first_nonfinite_index": first_nonfinite,
    }


def read_channel(directory: str | Path, name: str) -> np.ndarray:
    """Read a channel back. ``allow_pickle=False``, always.

    ADR-011 Enforcement 1 requires that every read passes ``allow_pickle=False``: a pickled
    ``.npy`` executes code on load, which would make reading an evidence package an execution of
    whatever produced it.
    """
    return np.load(Path(directory) / f"{name}.npy", allow_pickle=False)


def write_channels_manifest(directory: str | Path, rows: list[dict]) -> Path:
    """Write ``channels_manifest.json``, sorted by channel name.

    Sorted because the manifest is package content whose bytes are hashed, and dict insertion
    order is a property of the producing code rather than of the run.
    """
    ordered = sorted(rows, key=lambda r: r["name"])
    payload = json.dumps(ordered, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return write_atomic(Path(directory) / "channels_manifest.json", payload.encode("utf-8"))
