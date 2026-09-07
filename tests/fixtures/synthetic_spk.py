"""A FarSight-authored synthetic SPK, generated offline. Test fixture, not shipped code.

**Why this exists.** The weeks 1-2 exit gate needs a geometry command that produces hash-stable
output. Doing that against a real ephemeris needs a NAIF SPK -- a large download requiring founder
approval that has not happened. Two fictional bodies on an analytically exact trajectory give the
command a real CSPICE answer, with a closed-form truth to check it against, and no network.

**What it proves and what it cannot.** It exercises the plumbing: furnish order, content
addressing, coverage refusal, the light-time solver, units, and every refusal on the path. It
proves nothing whatsoever about real ephemerides. A green result here is not evidence about
Psyche, and ``ci-geometry-crosscheck`` against an external golden remains the check that would
catch a wrong-but-stable kernel choice.

**Measured properties this fixture depends on** (spiceypy 6.0.3 / CSPICE_N0067 / Python 3.12,
2026-09-07):

* The SPK writer is **byte-deterministic**. Twenty writes from separate processes, into different
  directories, with wall-clock gaps between them, produced one digest. No creation date, no
  toolkit version and no author string appears that the caller did not put there -- the complete
  inventory of printable runs is the DAF ID word, ``ifname``, the binary-format marker, the FTP
  validation string, the comment text and the segment ids.
* ``ifname`` and every ``segid`` are therefore **inside the digest**, so they are pinned constants
  here rather than incidental strings.
* The bytes carry a **little-endian marker** at offset 88 (``LTL-IEEE``). This is a statement
  about **content addressing**, not about reproducibility tiers: the same declared inputs
  regenerate to the same content address on any little-endian host, which is what keeps a
  kernel's cache address stable across the dev machine and the pinned container, and what makes
  ADR-016 Enforcement 1's ``test_kernel_sequence_identity`` meaningful on both platforms.

  It is emphatically **not** a cross-OS bitwise claim. ADR-006 forecloses one: "We can never
  claim bitwise reproducibility across operating systems, so a Windows-only customer is
  permanently a Tier-B customer and must be told so." Tier A is defined by container digest and
  CPU ISA feature set, and that record keeps separate golden trees per platform for this reason.

  On a big-endian host CSPICE would write byte-swapped doubles, read them back happily, and
  surface the difference only as a cache hash mismatch far from its cause.
* States are built from **exactly-representable constants** (powers of two). The writer stores
  IEEE-754 doubles verbatim, so the digest is exactly as reproducible as the arithmetic that
  produced the array; a value computed through a NumPy expression could move in its last bit
  across a NumPy or BLAS version and silently change the kernel's address.
* Both bodies are centred on the **Solar System Barycentre (id 0)**. Measured on a two-body SPK
  centred on 9010003 with no chain back to 0: ``NONE`` still succeeds, while ``LT``, ``LT+S`` and
  ``CN+S`` all fail with ``SPICE(SPKINSUFFDATA)``. So it is not only the stellar-aberration
  members -- every light-time solution needs the chain, because solving for light time needs the
  observer's state in a common frame. Centring on 0 is what keeps a two-kernel set
  self-sufficient.
* Body ids **9010001** and **9010002** sit in a range CSPICE N0067's built-in table leaves empty.

**The cache keeps its single writer.** ADR-016 decision 5 permits exactly one writer to the kernel
cache. This module returns *bytes*; insertion goes through ``KernelCache.put`` with the expected
digest, exactly as a fetched kernel does. A generator that wrote into the cache root directly
would be the second writer that rule forbids.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import numpy as np

# Inside the digest, so they are constants rather than incidental strings.
IFNAME = "FARSIGHT SYNTHETIC PAIR"
SEGID_A = "FARSIGHT BODY A LINEAR"
SEGID_B = "FARSIGHT BODY B LINEAR"
COMMENT = "AUTHORED BY FARSIGHT. THIS IS NOT A NAIF PRODUCT. Fictional bodies; not physical."

BODY_A = 9010001
BODY_B = 9010002
CENTRE = 0            # Solar System Barycentre -- see the docstring on stellar aberration
FRAME = "J2000"

# Powers of two, so every state is exact in float64 and the digest cannot move under a NumPy
# version change. The window spans 2017-01 to 2034-01 in TDB seconds past J2000, which covers
# every epoch these tests use.
FIRST_ET = float(2**29)      # 536870912.0
LAST_ET = float(2**30)       # 1073741824.0

_SPAN = LAST_ET - FIRST_ET

# Body A: on +x, drifting +x. Body B: on -x and +y, drifting -y. Linear in both cases, so a
# degree-1 Lagrange segment reproduces the motion exactly and the truth is closed form.
_A0 = (float(2**27), 0.0, 0.0)
_AV = (float(2**-10), 0.0, 0.0)
_B0 = (-float(2**27), float(2**26), 0.0)
_BV = (0.0, -float(2**-10), 0.0)


def _states(p0, v) -> np.ndarray:
    """Two nodes at the window's ends, positions advanced exactly by ``v * span``."""
    return np.array(
        [
            [p0[0], p0[1], p0[2], v[0], v[1], v[2]],
            [p0[0] + v[0] * _SPAN, p0[1] + v[1] * _SPAN, p0[2] + v[2] * _SPAN, v[0], v[1], v[2]],
        ],
        dtype=np.float64,
    )


def analytic_position(body: int, et: float) -> tuple[float, float, float]:
    """The closed-form truth the SPK is supposed to reproduce. Independent of SPICE."""
    p0, v = (_A0, _AV) if body == BODY_A else (_B0, _BV)
    dt = et - FIRST_ET
    return (p0[0] + v[0] * dt, p0[1] + v[1] * dt, p0[2] + v[2] * dt)


def analytic_range(et: float) -> float:
    """``|B - A|`` in km, geometric, from the closed form rather than from a kernel."""
    ax, ay, az = analytic_position(BODY_A, et)
    bx, by, bz = analytic_position(BODY_B, et)
    return float(np.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2))


def synthetic_spk_bytes() -> bytes:
    """Generate the SPK and return its bytes. Deterministic: same bytes on every call.

    Written to a fresh temporary path because ``spkopn`` refuses to open a file that already
    exists -- which is ADR-016's kernel immutability rule enforced by the toolkit rather than by
    discipline, and it forces the write-then-address ordering the content-addressed cache needs
    anyway.
    """
    import spiceypy

    directory = Path(tempfile.mkdtemp(prefix="farsight_spk_"))
    path = directory / "synthetic.bsp"

    handle = spiceypy.spkopn(str(path), IFNAME, len(COMMENT) + 64)
    try:
        epochs = np.array([FIRST_ET, LAST_ET], dtype=np.float64)
        spiceypy.spkw09(handle, BODY_A, CENTRE, FRAME, FIRST_ET, LAST_ET, SEGID_A,
                        1, 2, _states(_A0, _AV), epochs)
        spiceypy.spkw09(handle, BODY_B, CENTRE, FRAME, FIRST_ET, LAST_ET, SEGID_B,
                        1, 2, _states(_B0, _BV), epochs)
        spiceypy.dafac(handle, [COMMENT])
    finally:
        spiceypy.spkcls(handle)

    data = path.read_bytes()
    path.unlink()
    directory.rmdir()
    return data


def synthetic_spk_sha256() -> str:
    return hashlib.sha256(synthetic_spk_bytes()).hexdigest()
