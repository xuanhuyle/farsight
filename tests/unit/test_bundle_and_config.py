"""The run bundle and the SPICE provider config. ADR-001, ADR-003, ADR-018, ADR-020.

These two types are what let ``farsight geometry`` execute a ``RunSpec`` rather than a parallel
document (DEV-21). The bundle turns a digest back into a document and refuses one that does not
match its address; the config is the one place that knows what ``config_dialect`` means, because
ADR-003 keeps provider config opaque to the core.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from farsight.hashing.canonical import content_hash
from farsight.registry.bundle import BundleError, RefBundle, object_half

DOC = {"kind": "uniform", "n_samples": 4}
REF = content_hash(DOC)


# ------------------------------------------------------------------------------------------
# RefBundle
# ------------------------------------------------------------------------------------------


def test_an_object_must_hash_to_the_address_filing_it():
    RefBundle({REF: DOC})
    with pytest.raises(BundleError, match="actually hashes to"):
        RefBundle({REF: {"kind": "uniform", "n_samples": 5}})


def test_a_key_must_be_a_content_address_and_not_a_name():
    """ADR-001 rule 7: a bare lowercase 64-hex digest, no algorithm prefix.

    A name where an address belongs is how two different documents come to share a key -- and a
    bundle keyed by names could not detect the substitution the hash check exists to catch,
    because there would be nothing to compare against.
    """
    for bad in ("grid", "sha256:" + REF, REF.upper(), REF[:-1], REF + "0", ""):
        with pytest.raises(BundleError, match="not a bare lowercase 64-hex"):
            RefBundle({bad: DOC})


def test_the_two_key_envelope_is_recognised_and_nothing_looser_is():
    """ADR-001 rule 4: a stored object is ``{object, provenance}`` and only ``object`` is hashed.

    Recognition requires EXACTLY those two keys. Treating any dict with an ``object`` field as an
    envelope would silently hash the wrong half of a document that merely happens to have a field
    called ``object`` -- and the resulting digest would be stable, self-consistent, and wrong.
    """
    envelope = {"object": DOC, "provenance": {"created_at": "2026-09-07T00:00:00Z"}}
    assert object_half(envelope) == DOC
    bundle = RefBundle({REF: envelope})
    assert bundle.resolve(REF) == DOC

    # A document that merely HAS an `object` field is not an envelope: it is its own object half.
    looks_like_one = {"object": DOC, "provenance": {}, "extra": 1}
    assert object_half(looks_like_one) == looks_like_one

    not_an_envelope = {"object": "a name", "unit": "km"}
    assert object_half(not_an_envelope) == not_an_envelope
    RefBundle({content_hash(not_an_envelope): not_an_envelope})


def test_an_unresolvable_reference_names_itself_and_what_it_was_for():
    """AT-3 requires a nonzero exit naming the exact item."""
    bundle = RefBundle({REF: DOC})
    with pytest.raises(BundleError, match="grid for stage 'geometry'"):
        bundle.resolve("b" * 64, what="grid for stage 'geometry'")
    assert bundle.refs() == [REF]
    assert REF in bundle and len(bundle) == 1


def test_a_bundle_must_be_a_mapping():
    with pytest.raises(BundleError, match="mapping"):
        RefBundle([DOC])


# ------------------------------------------------------------------------------------------
# SpiceGeometryConfig
# ------------------------------------------------------------------------------------------


def _quantity(emit: str = "range", unit: str = "km", quantity_class: str = "range") -> dict:
    return {
        "emit": emit,
        "unit": unit,
        "request": {
            "target": "9010002", "observer": "9010001", "frame": "J2000",
            "aberration": "CN", "quantity_class": quantity_class,
            "epochs": "a" * 64, "rationale": None,
        },
    }


def _config(quantities=None) -> dict:
    from farsight.engines.spice.config import SPICE_GEOMETRY_DIALECT

    return {
        "schema_version": 1,
        "dialect": SPICE_GEOMETRY_DIALECT,
        "kernel_set": {
            "schema_version": 1,
            "kernels": [
                {
                    "sha256": "a" * 64, "kernel_type": "lsk", "logical_name": "x.tls",
                    "size_bytes": 1, "attribution": "farsight_authored", "modifier": "FarSight",
                    "parent_sha256": None, "license_note": "test",
                }
            ],
            "frame_sources": {},
        },
        "quantities": quantities if quantities is not None else [_quantity()],
    }


def test_a_stage_cannot_emit_the_same_channel_twice():
    """Each channel is one file, so a duplicate is one request silently overwriting another's
    answer -- and the run would report success with one of the two results simply gone."""
    from farsight.engines.spice.config import SpiceGeometryConfig

    SpiceGeometryConfig.model_validate(_config([_quantity("range"), _quantity("light_time",
                                                                              "s",
                                                                              "light_time")]))
    with pytest.raises(ValidationError, match="appear more than once"):
        SpiceGeometryConfig.model_validate(_config([_quantity("range"), _quantity("range")]))


def test_an_emitted_name_is_one_segment_and_cannot_reach_another_stages_namespace():
    """ADR-018: the run-level channel name is ``stage_id + "." + emit``, so the qualifier is
    supplied by the stage. A dotted ``emit`` would let a stage write into another stage's
    namespace, which ADR-018's pairwise non-overlap rule exists to prevent -- and it would do so
    without colliding with anything the uniqueness check can see.
    """
    from farsight.engines.spice.config import SpiceGeometryConfig

    for bad in ("link.margin", "range.x", "Range", "nul", "", "_range"):
        with pytest.raises(ValidationError):
            SpiceGeometryConfig.model_validate(_config([_quantity(bad)]))


def test_a_config_that_computes_nothing_is_refused():
    from farsight.engines.spice.config import SpiceGeometryConfig

    with pytest.raises(ValidationError, match="computes nothing"):
        SpiceGeometryConfig.model_validate(_config([]))


def test_a_declared_unit_is_non_empty():
    from farsight.engines.spice.config import SpiceGeometryConfig

    for bad in ("", " km", "km "):
        with pytest.raises(ValidationError):
            SpiceGeometryConfig.model_validate(_config([_quantity(unit=bad)]))


def test_the_dialect_is_a_closed_literal():
    """ADR-003: `config_dialect` names the provider's own schema, so the version lives in the
    string. A change to this document's shape is a new dialect, not a silent reinterpretation of
    an archived config_ref."""
    from farsight.engines.spice.config import SpiceGeometryConfig

    bad = _config()
    bad["dialect"] = "spice_geometry_v2"
    with pytest.raises(ValidationError):
        SpiceGeometryConfig.model_validate(bad)


def test_qualified_names_are_built_from_the_stage_id():
    from farsight.engines.spice.config import SpiceGeometryConfig

    config = SpiceGeometryConfig.model_validate(
        _config([_quantity("range"), _quantity("light_time", "s", "light_time")])
    )
    assert config.qualified_names("geometry") == ["geometry.range", "geometry.light_time"]
    assert config.qualified_names("sky") == ["sky.range", "sky.light_time"]
    # The qualifier is itself checked against the channel-name grammar.
    with pytest.raises(ValueError, match="reserved device name"):
        config.qualified_names("nul")
