"""The independent time path and the network door it closes. ADR-015 decision 7, ADR-012.

ADR-015 keeps two conversion implementations on purpose and cross-checks them rather than merging
them, because a systematic frame or time-system error is invisible to a single implementation
checked against itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from farsight.units.time import (
    J2000_TT_ISO,
    TimeIndependenceError,
    network_is_closed,
    utc_to_tdb_seconds,
)

from ._guards import skip_or_fail_on_missing_kernels

REPO = Path(__file__).resolve().parents[2]


def test_importing_the_time_module_closes_astropys_iers_download():
    """ADR-015 decision 7, and the reason it is not optional.

    astropy is a BASE-install dependency and `iers.conf.auto_download` defaults to True, pointing
    at datacenter.iers.org. Any conversion touching UT1 would try to fetch it -- which would make
    ADR-012's structural no-network claim false in the auditor's install, the one install that has
    to run anywhere. Measured before the assignment on this machine: auto_download True,
    auto_max_age 30.0.
    """
    from astropy.utils import iers

    assert network_is_closed()
    assert iers.conf.auto_download is False
    assert iers.conf.auto_max_age is None


def test_the_door_is_closed_at_import_and_not_by_the_caller():
    """A fresh interpreter that imports nothing but this module must already be closed.

    Asserted in a subprocess because the in-process check cannot distinguish "closed at import"
    from "closed by some earlier test", and the property ADR-012 needs is about the process.
    """
    script = f"""
import sys
sys.path.insert(0, {str(REPO / "src")!r})
import farsight.units.time  # noqa: F401
from astropy.utils import iers
print(iers.conf.auto_download, iers.conf.auto_max_age)
"""
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          check=False)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False None"


def test_the_two_implementations_agree_to_far_better_than_a_time_system_error():
    """Plan §14 item 3's independence, executed rather than asserted.

    The assertion is deliberately not "these agree to N digits is correct physics". It is that
    the two differ by far less than any TIME-SYSTEM error could produce. A missed leap second is
    1 s, a TT/TAI confusion is 32.184 s, a TAI/UTC confusion is tens of seconds. The two
    implementations differ only in how they truncate the TDB-TT periodic term, whose amplitude is
    about 1.7 ms -- so a millisecond bound passes with four orders of magnitude of margin against
    the class of error this check exists to catch.

    Measured 2026-09-07 under the pinned naif0012.tls: the largest disagreement over the epochs
    below was 1.2e-4 s.
    """
    pytest.importorskip("spiceypy")
    from farsight.engines.spice.kernels import furnished_pool
    from farsight.engines.spice.time import utc_to_et
    from farsight.registry.kernel_cache import KernelCache
    from farsight.registry.paths import kernel_cache_root
    from farsight.schemas.kernels import KernelRef

    pinned = json.loads((REPO / "kernels" / "pinned_kernels.json").read_text(encoding="utf-8"))
    entry = pinned["kernels"][0]
    cache = KernelCache(kernel_cache_root())
    if not cache.has(entry["sha256"]):
        skip_or_fail_on_missing_kernels(
            "the pinned LSK is not in the local cache; run `farsight fetch kernel`"
        )

    ref = KernelRef(
        sha256=entry["sha256"], kernel_type="lsk", logical_name=entry["logical_name"],
        size_bytes=entry["size_bytes"], attribution="third_party_unmodified",
        modifier=None, parent_sha256=None,
        license_note=entry.get("license_note", "NAIF public domain"),
    )

    worst = Decimal(0)
    with furnished_pool([ref], cache):
        for utc in ("2000-01-01T12:00:00", "2024-04-08T00:00:00",
                    "2016-12-31T23:59:59", "2020-06-15T06:30:00"):
            spice = Decimal(repr(utc_to_et(utc)))
            astropy = utc_to_tdb_seconds(utc)
            worst = max(worst, abs(spice - astropy))

    assert worst < Decimal("0.001"), (
        f"SPICE and astropy differ by {worst} s. Below a millisecond this is two truncations of "
        f"the TDB-TT periodic term; at or above it, suspect a time-system error -- a leap second "
        f"is 1 s and TT-TAI is 32.184 s"
    )
    assert worst > 0, (
        "the two implementations agree exactly, which would mean they are not independent"
    )


def test_the_independent_path_refuses_a_literal_it_cannot_parse():
    for bad in ("not-a-time", "2024-13-45T99:99:99", ""):
        with pytest.raises(TimeIndependenceError):
            utc_to_tdb_seconds(bad)


def test_j2000_is_the_definitional_tt_instant():
    """A hand-checkable anchor: at J2000, TT - UTC is 32.184 plus the 32 leap seconds in force,
    so 2000-01-01T12:00:00 UTC is 64.184 s past J2000 on the TDB timeline."""
    assert J2000_TT_ISO.startswith("2000-01-01T12:00:00")
    value = utc_to_tdb_seconds("2000-01-01T12:00:00")
    assert abs(value - Decimal("64.184")) < Decimal("0.002")
