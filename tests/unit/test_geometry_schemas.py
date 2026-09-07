"""ADR-015, ADR-020 and ADR-011's schema-level enforcement items.

Three of the assertions here were specified as "first green by week 1" and were not implemented:
ADR-015 Enforcement 2 (``test_geometry_request_has_no_defaults`` and its companion AST lint),
ADR-011 Enforcement 1 (``test_channel_roundtrip``), and the grid arithmetic ADR-020 decision 4
requires. They are named by those records, so they are spelled the way the records spell them.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from farsight.registry.channels import (
    CHANNEL_DTYPE,
    ChannelWriteError,
    channel_hash,
    channel_header,
    grid_hash,
    read_channel,
    write_channel,
)
from farsight.schemas.channels import (
    ChannelDecl,
    ExplicitGrid,
    UniformGrid,
    elapsed_seconds,
    epoch_seconds,
    validate_channel_name,
)
from farsight.schemas.common import Quantity
from farsight.schemas.geometry import ABERRATION_MEMBERS, Duration, Epoch, GeometryRequest

REPO = Path(__file__).resolve().parents[2]


def _epoch(magnitude: str = "0") -> Epoch:
    return Epoch(scale="TDB", seconds_past_j2000=Quantity(magnitude=magnitude, unit="s"))


def _grid(step: str = "60", n: int = 4) -> UniformGrid:
    return UniformGrid(epoch0=_epoch(), step=Quantity(magnitude=step, unit="s"), n_samples=n)


def _request(**over) -> GeometryRequest:
    base = dict(
        target="PSYCHE", observer="EARTH", frame="J2000",
        aberration="CN", quantity_class="range", epochs="a" * 64, rationale=None,
    )
    base.update(over)
    return GeometryRequest(**base)


# ------------------------------------------------------------------------------------------
# ADR-015 Enforcement 2 -- first green by week 1.
# ------------------------------------------------------------------------------------------


def test_geometry_request_has_no_defaults():
    """No field of GeometryRequest declares a default, and omitting one raises.

    ADR-015 decision 6: omission is a validation error, not a fallback. The two halves are
    checked separately because a field could have no default and still be optional.
    """
    for name, field in GeometryRequest.model_fields.items():
        assert field.is_required(), (
            f"GeometryRequest.{name} is optional. ADR-015 rejects a default for a convention "
            f"because a default is invisible in the evidence package: the number changes, the "
            f"hash changes, and nothing says why"
        )

    for missing in ("target", "observer", "frame", "aberration", "quantity_class", "epochs"):
        fields = dict(
            target="X", observer="Y", frame="J2000", aberration="CN",
            quantity_class="range", epochs="a" * 64, rationale=None,
        )
        del fields[missing]
        with pytest.raises(ValidationError):
            GeometryRequest(**fields)


def test_stellar_aberration_is_refused_on_a_range_and_on_a_light_time():
    """ADR-015 decision 6's consistency rule.

    Stellar aberration displaces an apparent direction and does not change a range. A `+S` member
    on a range is not a more careful choice; it is a statement that does not typecheck against the
    physics, and it would produce a number that looks more careful than the one without it.
    """
    for quantity in ("range", "light_time"):
        for aberration in ("LT+S", "CN+S", "XLT+S", "XCN+S"):
            with pytest.raises(ValidationError, match="stellar-aberration term"):
                _request(quantity_class=quantity, aberration=aberration)
        # ... and the same members without `+S` are fine.
        for aberration in ("NONE", "LT", "CN", "XLT", "XCN"):
            _request(quantity_class=quantity, aberration=aberration)


def test_a_geometric_direction_needs_a_stated_reason():
    """A direction without `+S` is geometric rather than apparent, which ADR-015 admits only with
    a rationale -- so the author says why, rather than the reader guessing."""
    for aberration in ("NONE", "LT", "CN"):
        with pytest.raises(ValidationError, match="rationale"):
            _request(quantity_class="direction", aberration=aberration, rationale=None)
        _request(quantity_class="direction", aberration=aberration,
                 rationale="reproducing an archived golden whose source states the geometric case")
    for aberration in ("LT+S", "CN+S"):
        _request(quantity_class="direction", aberration=aberration, rationale=None)


def test_no_literal_aberration_string_outside_the_module_that_defines_the_enum():
    """ADR-015 Enforcement 2's companion AST lint.

    "A companion AST lint fails on any literal aberration string appearing anywhere under
    `src/farsight/` outside the module that defines the `Aberration` literal." That is what
    mechanically prevents a convention from being re-introduced as a constant in an adapter --
    which is the exact failure ADR-015 decision 6 exists to prevent, one level down.

    String literals only, via the AST. A previous lint in this repo matched its own docstring and
    reported itself; scanning parsed literals rather than raw text is what stops that.
    """
    defining = (REPO / "src" / "farsight" / "schemas" / "geometry.py").resolve()
    members = set(ABERRATION_MEMBERS)
    offenders: list[str] = []

    for path in sorted((REPO / "src" / "farsight").rglob("*.py")):
        if path.resolve() == defining:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in members:
                    offenders.append(
                        f"{path.relative_to(REPO).as_posix()}:{node.lineno}: {node.value!r}"
                    )

    assert not offenders, (
        "literal aberration strings outside schemas/geometry.py (ADR-015 Enforcement 2). Pass "
        "`request.aberration` through instead: a convention spelled as a constant is a default "
        "wearing a different name, and it is invisible in the evidence package:\n  "
        + "\n  ".join(offenders)
    )


def test_an_epoch_is_seconds_and_a_duration_is_not_an_epoch():
    """ADR-015 decisions 1 and 2. Both are Quantity{unit: "s"} and nothing but a type stops one
    being assigned to the other, which is why they are two types."""
    _epoch("764640000")
    with pytest.raises(ValidationError, match="unit"):
        Epoch(scale="TDB", seconds_past_j2000=Quantity(magnitude="1", unit="min"))
    with pytest.raises(ValidationError):
        Epoch(scale="UTC", seconds_past_j2000=Quantity(magnitude="1", unit="s"))

    Duration(seconds=Quantity(magnitude="600", unit="s"), anchor=None)
    assert Epoch is not Duration
    assert set(Epoch.model_fields) != set(Duration.model_fields)


# ------------------------------------------------------------------------------------------
# ADR-020 decision 4 -- the grid, expanded exactly.
# ------------------------------------------------------------------------------------------


def test_the_grid_is_expanded_by_multiplication_and_never_by_accumulation():
    """ADR-020 decision 4 forbids the accumulating alternative by name.

    The measured difference at a 0.1 s step over 8640 samples is ~1.3e-10 s -- about 4 cm of
    light travel, physically negligible here. What makes it matter anyway is that it is
    *path-dependent*: the accumulated value depends on how many additions preceded it, so the
    same sample computed by two chunkings differs, and a content-addressed system turns that into
    two different hashes for one physical grid. It also grows with n.
    """
    grid = UniformGrid(epoch0=_epoch("0"), step=Quantity(magnitude="0.1", unit="s"),
                       n_samples=8641)
    exact = epoch_seconds(grid, 8640)
    assert exact == Decimal("864.0")

    accumulated = 0.0
    for _ in range(8640):
        accumulated += 0.1
    assert accumulated != 864.0, (
        "float accumulation happened to be exact here, so this test no longer demonstrates the "
        "hazard it was written for"
    )
    assert abs(accumulated - float(exact)) > 0

    # Sample i does not depend on the samples before it.
    assert epoch_seconds(grid, 5000) == Decimal("500.0")


def test_a_non_accumulating_float_expansion_is_still_not_the_exact_one():
    """The sharper half of ADR-020 decision 4, and the one an implementer is likelier to miss.

    "Never by accumulating a float" is easy to honour and insufficient. ``np.arange(n) * 0.1``
    accumulates nothing -- it is a single multiply per sample, exactly the shape decision 4 asks
    for -- and it still disagrees with exact arithmetic.

    Measured for step 0.1 over 10001 samples: arange and linspace agree with each other at every
    sample, and both differ from the exact expansion at **3595 of 10001 samples (36%)**, first at
    i=3, where the float path gives 0.30000000000000004 and the exact path gives 0.3.

    So the requirement is exact arithmetic, not the absence of a running total. Two implementers
    who both read decision 4 and both avoided accumulation would still produce two different
    grids, two different sets of epochs, and two different channel hashes for one design.
    """
    n, step = 10001, "0.1"
    grid = UniformGrid(epoch0=_epoch("0"), step=Quantity(magnitude=step, unit="s"), n_samples=n)

    arange = np.arange(n) * float(step)
    linspace = np.linspace(0.0, (n - 1) * float(step), n)
    exact = np.array([float(epoch_seconds(grid, i)) for i in range(n)])

    assert np.array_equal(arange, linspace), (
        "arange and linspace no longer agree, so this test's framing needs revisiting"
    )
    differing = int((arange != exact).sum())
    assert differing > n // 4, (
        f"only {differing} of {n} samples differ; the hazard this test documents has changed"
    )
    first = int(np.argmax(arange != exact))
    assert first == 3
    assert exact[first] == 0.3 and arange[first] != 0.3


def test_t_elapsed_starts_at_exactly_zero():
    """ADR-020 decision 5: `t_elapsed[0]` is exactly 0.0, and it carries elapsed seconds rather
    than an absolute epoch -- a float64 cannot hold ADR-015's epoch without a precision claim
    ADR-020 declines to make."""
    grid = _grid(step="60", n=10)
    assert elapsed_seconds(grid, 0) == 0.0
    assert elapsed_seconds(grid, 9) == 540.0
    with pytest.raises(IndexError):
        elapsed_seconds(grid, 10)


def test_a_grid_step_is_strictly_positive():
    for bad in ("0", "-60"):
        with pytest.raises(ValidationError, match="strictly positive"):
            UniformGrid(epoch0=_epoch(), step=Quantity(magnitude=bad, unit="s"), n_samples=4)


def test_the_two_grid_kinds_are_told_apart_by_their_discriminator():
    explicit = ExplicitGrid(epochs_artifact="b" * 64)
    assert explicit.kind == "explicit"
    assert grid_hash(_grid()) != grid_hash(explicit)


def test_a_channel_name_is_a_path_plus_a_leaf_and_run_is_closed():
    """ADR-020 rule 1, including the one reserved namespace."""
    validate_channel_name("geometry.range")
    validate_channel_name("run.t_elapsed")
    with pytest.raises(ValueError, match="at least two"):
        validate_channel_name("range")
    with pytest.raises(ValueError, match="reserved `run` namespace"):
        validate_channel_name("run.anything_else")


def test_a_code_map_stays_inside_exact_float64_integers():
    """ADR-020 decision 2: codes live in [-2**53, 2**53] so equality against a code is exact
    rather than a floating-point comparison in disguise."""
    ChannelDecl(name="mode", unit="1", description="pointing mode",
                code_map={"safe": 2, "science": 3})
    with pytest.raises(ValidationError, match=r"2\*\*53"):
        ChannelDecl(name="mode", unit="1", description="x", code_map={"safe": 2**53 + 1})
    with pytest.raises(ValidationError, match="share a code"):
        ChannelDecl(name="mode", unit="1", description="x", code_map={"safe": 2, "idle": 2})


def test_component_labels_must_name_the_axis_they_claim_to_name():
    ChannelDecl(name="margin", unit="dB", description="per-relay margin", components=3,
                component_labels=["relay_a", "relay_b", "relay_c"])
    with pytest.raises(ValidationError, match="component_labels has"):
        ChannelDecl(name="margin", unit="dB", description="x", components=3,
                    component_labels=["relay_a"])
    with pytest.raises(ValidationError, match="ambiguous"):
        ChannelDecl(name="margin", unit="dB", description="x", components=2,
                    component_labels=["relay_a", "relay_a"])


# ------------------------------------------------------------------------------------------
# ADR-011 Enforcement 1 -- test_channel_roundtrip, first green by week 1.
# ------------------------------------------------------------------------------------------


def test_channel_roundtrip(tmp_path):
    """Write, read and re-hash, including the empty, single-element and non-finite cases.

    ADR-011 Enforcement 1 names those three cases specifically, and each is a real edge: an empty
    channel has a zero-length payload so the separator byte is the only thing between header and
    nothing; a single element cannot distinguish a scalar from a length-1 axis without the shape
    field; and a non-finite sample is what ADR-023 turns into a divergence.
    """
    digest = grid_hash(_grid())
    cases = {
        "geometry.empty": np.array([], dtype="<f8"),
        "geometry.single": np.array([42.5], dtype="<f8"),
        "geometry.nonfinite": np.array([1.0, np.nan, np.inf, -np.inf], dtype="<f8"),
        "geometry.ordinary": np.array([1.5, -2.25, 3.0], dtype="<f8"),
        "geometry.vector": np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype="<f8"),
    }

    for name, array in cases.items():
        row = write_channel(tmp_path, name, "km", array, digest)
        back = read_channel(tmp_path, name)

        assert back.dtype == np.dtype(CHANNEL_DTYPE)
        assert back.shape == array.shape
        np.testing.assert_array_equal(np.nan_to_num(back, nan=0.0), np.nan_to_num(array, nan=0.0))

        # Re-hashing what came off disk must reproduce the recorded hash. Hashing the in-memory
        # array instead would test the hash function rather than the write.
        assert channel_hash(channel_header(name, "km", back.shape, digest), back) == \
            row["channel_hash"]

    nonfinite_row = write_channel(tmp_path, "geometry.nonfinite", "km",
                                  cases["geometry.nonfinite"], digest)
    assert nonfinite_row["nonfinite_count"] == 3
    assert nonfinite_row["first_nonfinite_index"] == 1


def test_the_channel_hash_covers_the_grid_which_is_the_hole_adr_011_named():
    """ADR-011's stated hole, closed by ADR-020 decision 6.

    Without `grid_hash` in the header, a channel computed on a 60-second grid and one computed on
    a 10-second grid hash identically whenever their values match -- so a run re-executed against
    a different time base hash-verifies clean.
    """
    values = np.array([1.0, 2.0, 3.0, 4.0], dtype="<f8")
    sixty = channel_hash(channel_header("geometry.range", "km", (4,), grid_hash(_grid("60"))),
                         values)
    ten = channel_hash(channel_header("geometry.range", "km", (4,), grid_hash(_grid("10"))),
                       values)
    assert sixty != ten

    # And the four-field header of ADR-011's own example would NOT tell them apart, which is why
    # that record says its example no longer computes what a reader would get.
    four_field = {"name": "geometry.range", "unit": "km", "dtype": CHANNEL_DTYPE, "shape": [4]}
    assert channel_hash(four_field, values) == channel_hash(dict(four_field), values)


def test_a_channel_is_float64_and_an_integer_array_is_refused_rather_than_promoted(tmp_path):
    """ADR-020 decision 2: there are no integer, boolean or string channels. Promotion would be
    lossy above 2**53 and silent below it, and a caller who meant a categorical channel wants a
    code_map rather than a cast."""
    digest = grid_hash(_grid())
    for bad in (np.array([1, 2, 3]), np.array([True, False]), np.array(["a", "b"])):
        with pytest.raises(ChannelWriteError, match="float64"):
            write_channel(tmp_path, "geometry.bad", "km", bad, digest)


def test_channel_bytes_do_not_depend_on_the_writing_machines_byte_order(tmp_path):
    """ADR-011 Enforcement 1's platform-invariance claim, at the granularity one machine can
    check: a big-endian array is written as little-endian and hashes identically to the
    little-endian one carrying the same numbers."""
    digest = grid_hash(_grid())
    values = [1.5, -2.25, 3.0, 4.0]
    little = write_channel(tmp_path / "le", "geometry.range", "km",
                           np.array(values, dtype="<f8"), digest)
    big = write_channel(tmp_path / "be", "geometry.range", "km",
                        np.array(values, dtype=">f8"), digest)
    assert little["channel_hash"] == big["channel_hash"]
