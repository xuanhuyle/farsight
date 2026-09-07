"""The independent time path, and the network door it closes on the way in. ADR-015 decision 7.

Two conversion implementations exist **by design**, and they are cross-checked rather than merged.
The authoritative path for anything entering a hashed document is SPICE, under the pinned LSK, in
``farsight/engines/spice/time.py``. This is the other one. Plan §14 item 3 asks for exactly this
independence, and ADR-015 records why it is not an optimization to collapse them: a systematic
frame or time-system error is invisible to a single implementation checked against itself.

**The network door.** astropy is a *base-install* dependency, and
``astropy.utils.iers.conf.auto_download`` defaults to ``True``, pointing at
``https://datacenter.iers.org/data/9/finals2000A.all``. Any astropy conversion that touches UT1
will try to fetch it. ADR-012's structural no-network claim would then be false on the Windows
leg, where no network-namespace check exists to catch it -- and it would be false in the
*auditor's* install, which is the one install that must run anywhere.

Importing this module sets ``auto_download = False`` and ``auto_max_age = None``. **UT1 is not
used anywhere in the MVP**: Earth orientation enters only through the binary PCK of ADR-015
decision 5, as a hash-pinned kernel rather than an ambient table that silently refreshes.

Measured 2026-09-07 on this machine: before the assignment ``auto_download`` was ``True`` and
``auto_max_age`` was ``30.0``. This is a real door, not a hypothetical one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from astropy.utils import iers

from farsight.schemas.errors import FarSightError

__all__ = [
    "IERS_SETTINGS",
    "J2000_TT_ISO",
    "TimeIndependenceError",
    "network_is_closed",
    "utc_to_tdb_seconds",
]

# Executed at import, before any astropy Time object can exist in this process. Assigning rather
# than using a context manager is deliberate: a context manager would close the door only for the
# code inside it, and the claim ADR-012 makes is about the process.
iers.conf.auto_download = False
iers.conf.auto_max_age = None

IERS_SETTINGS: Final = {"auto_download": False, "auto_max_age": None}

# The TT instant that defines J2000, as an ISO string. Definitional, not measured.
J2000_TT_ISO: Final = "2000-01-01T12:00:00.000"


class TimeIndependenceError(FarSightError, ValueError):
    """The independent path cannot answer, or its answer is not comparable."""


def network_is_closed() -> bool:
    """True when astropy's IERS auto-download is off in this process.

    A function rather than a constant so a test can assert the *live* configuration, which is what
    a later import or a stray assignment would change.
    """
    return iers.conf.auto_download is False and iers.conf.auto_max_age is None


def utc_to_tdb_seconds(utc_iso: str) -> Decimal:
    """UTC ISO string to TDB seconds past J2000, via astropy. **Not the authoritative path.**

    This exists to disagree with SPICE when one of the two is wrong. Nothing in a hashed document
    may come from here: ADR-015 decision 7 makes SPICE authoritative for anything that enters a
    hash, and a value from this function reaching a frozen design would defeat the entire point of
    having two implementations.

    Returns a ``Decimal`` because the comparison against SPICE is at the tens-of-microseconds
    level and a float subtraction of two large epoch values would lose exactly the digits the
    cross-check is about.
    """
    if not network_is_closed():  # pragma: no cover - defended at import; asserted by a test
        raise TimeIndependenceError(
            "astropy's IERS auto-download is enabled, so this conversion may reach the network. "
            "That would make ADR-012's structural no-network claim false in the auditor's install"
        )

    from astropy.time import Time

    try:
        t = Time(utc_iso, scale="utc", format="isot")
        tdb = t.tdb
        j2000 = Time(J2000_TT_ISO, scale="tt", format="isot").tdb
    except Exception as exc:  # astropy raises a wide range for a malformed literal
        raise TimeIndependenceError(
            f"astropy could not parse {utc_iso!r} as a UTC ISO instant: {exc}"
        ) from exc

    # `(t - j2000).sec` is a float64 difference of two nearby quantities, which is well
    # conditioned here precisely because astropy keeps the two-part julian date internally.
    # `float()` before `repr()`: NumPy 2 renders a scalar as `np.float64(...)`, which Decimal
    # cannot parse. The float is the shortest round-trip representation, so no digits are lost.
    return Decimal(repr(float((tdb - j2000).sec)))
