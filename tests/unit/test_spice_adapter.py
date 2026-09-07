"""The SPICE adapter: furnish order, the override canary, and epoch coverage (ADR-016, ADR-015).

Two tests here carry the stage.

`test_furnish_order_changes_the_answer` is ADR-016's `ci-kernel-override-canary`, and its
load-bearing assertion is that reordering changes **the computed value** -- not that it changes
the hash. Two orderings always hash differently, because JCS preserves array order; asserting
that would prove something about the serializer and nothing about SPICE. If the ordered-sequence
identity in ADR-016 decision 2 is not earned, this is the test that finds out.

`test_an_uncovered_epoch_is_refused` is the fix for the 16-second silent error found when
spiceypy was installed: SPICE extrapolates rather than refusing, so the refusal has to be ours.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

spiceypy = pytest.importorskip(
    "spiceypy", reason="the `spice` extra is not installed -- the auditor's install, and fine"
)

from farsight.engines.spice import time as spice_time
from farsight.engines.spice.kernels import (
    UnhonorableSpec,
    clear_pool,
    furnish_in_order,
    furnished_pool,
    loaded_count,
)
from farsight.registry.kernel_cache import KernelCache
from farsight.schemas.kernels import KernelRef, KernelSet

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "farsight"
FIXTURES = REPO / "tests" / "fixtures"

BASE_LSK = FIXTURES / "farsight_authored.tls"
OVERRIDE_LSK = FIXTURES / "override_later.tls"

DSOC_EPOCH_UTC = "2024-06-24T00:00:00"


def _ref(path: Path, kernel_type: str = "lsk") -> KernelRef:
    data = path.read_bytes()
    return KernelRef(
        sha256=hashlib.sha256(data).hexdigest(),
        kernel_type=kernel_type,
        logical_name=path.name,
        size_bytes=len(data),
        attribution="farsight_authored",
        modifier=None,
        parent_sha256=None,
        license_note="Authored by FarSight as a test fixture.",
    )


@pytest.fixture
def cache(tmp_path):
    """A cache holding both fixture kernels, addressed by content like any other."""
    c = KernelCache(tmp_path)
    for path in (BASE_LSK, OVERRIDE_LSK):
        data = path.read_bytes()
        c.put(data, hashlib.sha256(data).hexdigest())
    return c


@pytest.fixture(autouse=True)
def _clean_pool():
    """CSPICE keeps one pool per process, so a leak makes one test another's silent input."""
    clear_pool()
    yield
    clear_pool()


# --------------------------------------------------------------------------------------
# ADR-016's override canary: the order changes the ANSWER
# --------------------------------------------------------------------------------------


def test_furnish_order_changes_the_answer(cache):
    """ADR-016 Enforcement 2. The assertion that matters is the computed value, not the hash.

    Two orderings of one multiset always hash differently -- JCS preserves array order, so that
    is a property of the serializer. What earns ADR-016 decision 2's "reordering is an identity
    change" is that the pool resolves the LAST writer, so the order determines what a run reads.
    """
    base, override = _ref(BASE_LSK), _ref(OVERRIDE_LSK)

    with furnished_pool([base, override], cache):
        override_wins = spice_time.delta_et_utc(
            spice_time.utc_to_et(DSOC_EPOCH_UTC, check_coverage=False)
        )

    with furnished_pool([override, base], cache):
        base_wins = spice_time.delta_et_utc(
            spice_time.utc_to_et(DSOC_EPOCH_UTC, check_coverage=False)
        )

    assert override_wins != base_wins, (
        "the furnish order did not change the computed value, so ADR-016's ordered-sequence "
        "identity is unearned and this canary tests nothing"
    )
    # The fixtures differ by exactly 4 leap seconds, so the answers must too.
    assert abs(override_wins - base_wins) == pytest.approx(4.0, abs=1e-6)
    assert base_wins == pytest.approx(69.184303, abs=1e-5)


def test_reordering_changes_the_kernel_set_hash():
    """True, and deliberately asserted separately from the canary above -- because on its own it
    would look like the same guarantee while proving only that JCS preserves array order.

    Note this cannot reuse the two LSK fixtures: a KernelSet holds exactly one leapsecond kernel,
    so the two-LSK pair the furnish canary uses is not a legal set. That rule caught this test
    when it was first written.
    """
    from farsight.hashing.canonical import hash_object

    lsk = _ref(BASE_LSK)
    pck = KernelRef(
        sha256="d" * 64, kernel_type="pck", logical_name="synthetic.bpc", size_bytes=1024,
        attribution="farsight_authored", modifier=None, parent_sha256=None,
        license_note="Authored by FarSight as a test fixture.",
    )
    forward = KernelSet(kernels=(lsk, pck))
    backward = KernelSet(kernels=(pck, lsk))
    assert hash_object(forward) != hash_object(backward)


def test_a_kernel_set_holds_exactly_one_leapsecond_kernel():
    """ADR-016 decision 6: 'the pinned LSK' in ADR-015 only denotes something if there is one.
    Zero means no time conversion is defined; two means the later silently overrides the earlier
    -- which the furnish canary above shows is a four-second difference in the answer."""
    with pytest.raises(Exception, match="exactly one leapsecond kernel"):
        KernelSet(kernels=(_ref(BASE_LSK), _ref(OVERRIDE_LSK)))


# --------------------------------------------------------------------------------------
# Furnishing
# --------------------------------------------------------------------------------------


def test_the_pool_gains_exactly_what_was_furnished(cache):
    with furnished_pool([_ref(BASE_LSK)], cache):
        assert loaded_count() == 1
    assert loaded_count() == 0, "the pool must be cleared on the way out"


def test_the_pool_is_cleared_even_when_the_block_raises(cache):
    """A pool left furnished by a failing run becomes the next run's silent input."""
    with pytest.raises(RuntimeError), furnished_pool([_ref(BASE_LSK)], cache):
        raise RuntimeError("something failed mid-run")
    assert loaded_count() == 0


def test_a_kernel_missing_from_the_cache_is_refused(cache, tmp_path):
    """Verified before SPICE sees it. A missing kernel must fail here rather than as a missing
    frame later."""
    from farsight.registry.kernel_cache import KernelCacheError

    absent = _ref(BASE_LSK).model_copy(update={"sha256": "c" * 64})
    with pytest.raises(KernelCacheError, match="no cached bytes"):
        furnish_in_order([absent], cache)


def test_a_silently_skipped_furnish_is_caught(cache, monkeypatch):
    """CSPICE declines to load a file it cannot parse and carries on. Without the count, that
    shows up later as a missing frame or a wrong value, far from its cause."""

    real = spiceypy.furnsh
    monkeypatch.setattr(spiceypy, "furnsh", lambda _p: None)  # load nothing, raise nothing
    try:
        with pytest.raises(UnhonorableSpec, match="pool gained"):
            furnish_in_order([_ref(BASE_LSK)], cache)
    finally:
        monkeypatch.setattr(spiceypy, "furnsh", real)


# --------------------------------------------------------------------------------------
# Coverage: the refusal SPICE does not perform
# --------------------------------------------------------------------------------------


def test_an_uncovered_epoch_is_refused(cache):
    """The 16-second finding, closed. SPICE extrapolates from the earliest table entry and
    returns a plausible number; this refusal is ours because there is no other."""
    with furnished_pool([_ref(BASE_LSK)], cache):
        spice_time.utc_to_et(DSOC_EPOCH_UTC)  # inside coverage: fine

        with pytest.raises(spice_time.EpochCoverageError, match="before the furnished"):
            spice_time.utc_to_et("1980-01-01T00:00:00")


def test_the_refusal_names_the_measured_cost(cache):
    """The message has to say why, or the next reader relaxes the check to get their run to
    start."""
    with (furnished_pool([_ref(BASE_LSK)], cache),
          pytest.raises(spice_time.EpochCoverageError) as caught):
        spice_time.utc_to_et("1980-01-01T00:00:00")
    message = str(caught.value)
    assert "extrapolates" in message and "16 seconds" in message


def test_the_coverage_boundary_comes_from_the_furnished_table(cache):
    """Read from the pool rather than the file, so it reflects any override by a later kernel."""
    with furnished_pool([_ref(BASE_LSK)], cache):
        table = spice_time.leapsecond_table()
        assert [offset for offset, _ in table] == [36.0, 37.0]
        assert spice_time.coverage_start_et() == min(t for _, t in table)


def test_a_hand_computed_conversion_still_holds(cache):
    """69.184 s from the definitional 32.184 offset and the published 37 leap seconds -- neither
    read out of the kernel."""
    with furnished_pool([_ref(BASE_LSK)], cache):
        et = spice_time.utc_to_et(DSOC_EPOCH_UTC)
        expected = 37 + spice_time.DEFINITIONAL_TT_MINUS_TAI
        assert abs(spice_time.delta_et_utc(et) - expected) < 0.002
        assert spice_time.et_to_utc(et) == DSOC_EPOCH_UTC + ".000"


# --------------------------------------------------------------------------------------
# ADR-016 Enforcement 5: no metakernel at runtime
# --------------------------------------------------------------------------------------


def test_furnsh_is_called_from_exactly_one_place():
    """ADR-016: one file at a time, never a metakernel. Asserted as EXACTLY one call site rather
    than at most one -- 'at most' passes when nothing calls it at all."""
    sites: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC.parent.parent).as_posix().replace("src/farsight/", "")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "furnsh"
            ):
                sites.append(f"{rel}:{node.lineno}")
    assert len(sites) == 1, f"furnsh call sites: {sites}"
    assert sites[0].startswith("engines/spice/kernels.py")


def test_no_metakernel_syntax_appears_anywhere():
    """A metakernel names kernels by path, reintroducing the ambient directory the
    content-addressed cache exists to remove."""
    forbidden = ("KERNELS_TO_LOAD", "PATH_VALUES", "PATH_SYMBOLS")
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC.parent.parent).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # String LITERALS only, via the AST. The first version of this lint scanned raw text and
        # flagged its own docstring for the word ".tm" -- a lint that reads prose finds the
        # documentation of the rule and calls it a violation.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node is getattr(tree, "docstring_node", None):
                continue
            value = node.value
            if len(value) > 200:      # a docstring, not a path literal
                continue
            for token in forbidden:
                if token in value:
                    offenders.append(f"{rel}:{node.lineno}: {token}")
            if value.endswith(".tm"):
                offenders.append(f"{rel}:{node.lineno}: a .tm metakernel literal")
    assert not offenders, f"metakernel syntax in the source: {offenders}"


def test_kernel_type_cannot_express_a_metakernel():
    """Closure by inexpressibility: `mk` is absent from the enum, so the input cannot say it."""
    with pytest.raises(ValidationError):
        _ref(BASE_LSK).model_copy(update={"kernel_type": "mk"})


# --------------------------------------------------------------------------------------
# ADR-003: capabilities are readable without the SDK
# --------------------------------------------------------------------------------------


def test_capabilities_import_without_spiceypy(monkeypatch):
    """The planner runs on the base install. If reading an adapter's capabilities required the
    extra, the zero-extras path would break the moment anything asked what an adapter supports."""
    import importlib
    import sys

    class Refuses:
        def __getattr__(self, name):
            raise AssertionError("capabilities must not touch spiceypy")

    monkeypatch.setitem(sys.modules, "spiceypy", Refuses())
    module = importlib.reload(importlib.import_module("farsight.engines.spice.capabilities"))
    assert module.PROVIDER_ID == "spice"
    assert module.CAPABILITIES["is_engine"] is False
    assert module.REUSABLE_WORKER is True
    assert module.SUPPORTS_STEPPING is False


def test_the_capabilities_module_imports_nothing_from_spiceypy():
    """The reload test above proves it at runtime; this proves it in the source, so a future
    module-level import is caught even if the reload happens to succeed."""
    source = (SRC / "engines" / "spice" / "capabilities.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all("spiceypy" not in a.name for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert "spiceypy" not in (node.module or "")


# The whole module is gated by `pytest.importorskip` at the top; no per-test mark needed.
def test_an_unfurnished_pool_refuses_by_name_rather_than_by_spice_lookup_failure():
    """The empty-table guard, reachable at last.

    It was written to say "no leapsecond table is furnished", but `dtpool` raised `NotFoundError`
    before the guard could run, so the sentence was never the one a caller saw. A mutation test
    caught it the only way it could be caught: deleting the guard changed no test outcome, because
    no test -- and no user -- could reach it.
    """
    from farsight.engines.spice.kernels import clear_pool
    from farsight.engines.spice.time import EpochCoverageError, coverage_start_et, leapsecond_table

    clear_pool()
    assert leapsecond_table() == [], "an unfurnished pool has no leapsecond table"
    with pytest.raises(EpochCoverageError) as exc:
        coverage_start_et()
    assert "no leapsecond table is furnished" in str(exc.value)
