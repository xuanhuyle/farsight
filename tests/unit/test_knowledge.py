"""Source and Assumption: the two referents that were live and undefined (finding G2).

The tests that matter most are the ones asserting what these types CANNOT say. An assumption
that could carry a point value would hand a discharged `Unknown` a concrete number, which is the
silently-fitted default the product exists to prevent; and a design that claimed to detect
duplicate citations would be claiming a capability ADR-001's own Consequences section denies.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from farsight.hashing.canonical import canonicalize, content_hash
from farsight.schemas.belief import Pedigree, Unknown
from farsight.schemas.common import Quantity, VersionedDocument
from farsight.schemas.knowledge import (
    EXTERNAL_PUBLICATION_ORIGINS,
    Assumption,
    AssumptionBound,
    Source,
    SourceIdentifier,
    dependents_of,
)

HEX = "a" * 64
HEX_B = "b" * 64


def ped(level: str = "speculative", on: dt.date = dt.date(2026, 9, 3)) -> Pedigree:
    return Pedigree(
        level=level, sources=[] if level == "speculative" else [HEX],
        assessor="operator:jh", assessed_on=on,
    )


def ident(scheme="standard_designation", value="810-005", part="104") -> SourceIdentifier:
    return SourceIdentifier(scheme=scheme, value=value, part=part)


def source(**over) -> Source:
    base = dict(
        source_id="dsn_810_005",
        title="DSN Telecommunications Link Design Handbook, Module 104",
        origin="standard_or_handbook",
        issued="2024-09",
        identifiers=[ident()],
        artifact_refs=[HEX],
    )
    return Source(**{**base, **over})


def assumption(**over) -> Assumption:
    base = dict(
        assumption_id="rx_train_bound",
        statement="The Palomar receive optical train throughput is at least 0.30 end to end.",
        consequence_if_false="Every DSOC link margin computed from it is optimistic.",
        bound=AssumptionBound(lower=Quantity(magnitude="0.30", unit="1"), upper=None),
        pedigree=ped(),
        source_refs=[HEX],
        review_by=None,
    )
    return Assumption(**{**base, **over})


# --------------------------------------------------------------------------------------
# The referents exist at all (G2)
# --------------------------------------------------------------------------------------


def test_both_types_are_content_addressed_documents():
    """SourceRef and AssumptionRef were live inside hashed documents with undefined referents --
    verbatim the hazard ADR-026 was commissioned to close for ModelVersionRef."""
    for obj in (source(), assumption()):
        assert isinstance(obj, VersionedDocument)
        assert obj.model_dump()["schema_version"] == 1
        assert content_hash(obj.model_dump(mode="json"))


def test_a_source_carries_no_pedigree_so_provenance_terminates():
    """A belief cites a source; the source cites nothing. Provenance has to stop somewhere or it
    regresses forever, and who read it and how well is a property of the READING, which ADR-021
    puts on ReferentPoint.locator."""
    assert "pedigree" not in Source.model_fields
    with pytest.raises(ValidationError):
        source(pedigree=ped())


# --------------------------------------------------------------------------------------
# Duplicate detection: what is claimed, and what is admitted
# --------------------------------------------------------------------------------------


def test_identifiers_are_transcribed_verbatim_not_normalized():
    """A validator that lowercased a DOI would be normalizing VALUE, which ADR-001 forbids -- and
    a grammar strict enough to force one spelling just moves the normalization into the author's
    head, off the record, destroying the equality the comparison rests on."""
    a = SourceIdentifier(scheme="doi", value="10.1117/12.3001234", part=None)
    b = SourceIdentifier(scheme="doi", value="10.1117/12.3001234", part=None)
    c = SourceIdentifier(scheme="doi", value="DOI:10.1117/12.3001234", part=None)
    assert a.key() == b.key()
    assert a.key() != c.key()  # not silently reconciled; a human decides these are one work


def test_a_numbered_series_does_not_collide_with_itself():
    """The case that refuted a freeze-time collision refusal. DSN 810-005 is the flagship's
    central source and is a SERIES: its modules are separately issued under one designation, so a
    key on the designation alone merges different documents -- and a refusal built on it rejects
    a legal document set."""
    module_104 = source(identifiers=[ident(part="104")])
    module_105 = source(identifiers=[ident(part="105")])
    assert module_104.collision_keys() != module_105.collision_keys()
    assert module_104.collision_keys() == source(identifiers=[ident(part="104")]).collision_keys()


def test_collision_keys_are_reported_not_refused():
    """Two sources sharing an identifier construct fine. Whether they are the same work is a
    judgement for a human one layer up; refusing it here is where a week-3 author disables the
    check and takes the whole mechanism with it."""
    one = source(source_id="a_paper")
    two = source(source_id="another_paper")
    assert one.collision_keys() == two.collision_keys()  # shared key, both legal


def test_sameness_is_declared_by_a_human_never_inferred():
    """The only sanctioned way to say two digests are about one work: an authored forward
    pointer with a typed reason, which is a judgement someone signs."""
    revised = source(revision=2, supersedes=HEX_B, revision_reason="same_work_relinked")
    assert revised.supersedes == HEX_B
    with pytest.raises(ValidationError, match="travel together"):
        source(revision=2, supersedes=HEX_B)
    with pytest.raises(ValidationError, match="travel together"):
        source(revision_reason="same_work_relinked")


def test_revision_cannot_be_decoration():
    """Unchecked, `revision: 7` on a first draft reads as a version history that does not
    exist."""
    with pytest.raises(ValidationError, match="disagree"):
        source(revision=7)
    with pytest.raises(ValidationError, match="disagree"):
        source(revision=1, supersedes=HEX_B, revision_reason="transcription_corrected")


def test_identifiers_are_sorted_and_unique():
    with pytest.raises(ValidationError, match="repeats an identifier"):
        source(identifiers=[ident(), ident()])
    with pytest.raises(ValidationError, match="sorted"):
        source(identifiers=[ident(part="105"), ident(part="104")])


def test_identifier_hygiene_is_the_only_normalization():
    SourceIdentifier(scheme="doi", value="10.1117/12.3001234", part=None)
    for bad in (" 10.1117/12 ", "10.1117\n12", "  "):
        with pytest.raises(ValidationError):
            SourceIdentifier(scheme="doi", value=bad, part=None)


# --------------------------------------------------------------------------------------
# Referent laundering (ADR-021): which sources may back a referent
# --------------------------------------------------------------------------------------


def test_our_own_work_is_not_an_external_publication():
    """ADR-021 forbids anything FarSight produces from being bound as a Referent. The rule is
    about where a number ORIGINATED, not who wrote the code -- so our execution of an independent
    library is internal, even though the library is not ours."""
    for internal in ("internal_hand_calc", "internal_analysis", "second_library_output"):
        assert not source(origin=internal).is_external_publication()
        assert internal not in EXTERNAL_PUBLICATION_ORIGINS
    for external in ("published_literature", "standard_or_handbook",
                     "agency_technical_report", "public_dataset", "private_communication"):
        assert source(origin=external).is_external_publication()


def test_a_source_can_point_at_the_bytes_without_absorbing_them():
    """ADR-021 keeps Source and DataArtifact apart -- a Referent carries both lists. Without the
    pointer, `origin` would be the author's unfalsifiable word about where a number came from."""
    assert source().artifact_refs == [HEX]
    assert source(artifact_refs=[]).artifact_refs == []  # a positive assertion: no bytes held
    with pytest.raises(ValidationError, match="same artifact twice"):
        source(artifact_refs=[HEX, HEX])
    with pytest.raises(ValidationError, match="sorted"):
        source(artifact_refs=[HEX_B, HEX])


# --------------------------------------------------------------------------------------
# The assumption bound: never a point (AT-6)
# --------------------------------------------------------------------------------------


def test_an_assumption_bound_may_not_be_a_point():
    """The closure that makes Unknown.bounding_assumption_ref safe. If an assumption could carry
    one value, discharging an Unknown would hand it a concrete number -- the silently-fitted
    default ADR-001 rule 6 forbids and AT-6 tests for."""
    with pytest.raises(ValidationError, match="point value wearing an interval"):
        AssumptionBound(lower=Quantity(magnitude="0.45", unit="1"),
                        upper=Quantity(magnitude="0.45", unit="1"))


def test_a_one_sided_bound_leaves_the_other_edge_absent():
    """"At most 0.5" with a fabricated lower edge of 0 puts a number in the record no source
    stated -- the same fitting under a different name."""
    upper_only = AssumptionBound(lower=None, upper=Quantity(magnitude="0.5", unit="1"))
    assert upper_only.is_one_sided() and upper_only.lower is None
    with pytest.raises(ValidationError, match="asserts nothing"):
        AssumptionBound(lower=None, upper=None)


def test_bound_edges_are_ordered_and_share_a_unit():
    with pytest.raises(ValidationError, match="different units"):
        AssumptionBound(lower=Quantity(magnitude="1", unit="m"),
                        upper=Quantity(magnitude="2", unit="km"))
    with pytest.raises(ValidationError, match="exceeds"):
        AssumptionBound(lower=Quantity(magnitude="2", unit="m"),
                        upper=Quantity(magnitude="1", unit="m"))


def test_an_unquantified_assumption_is_legal_but_cannot_discharge_an_unknown():
    """"Failures are conditionally independent given the declared factors" is a real assumption
    with no bracket. It belongs in the register; it may not stand in for a missing number."""
    qualitative = assumption(bound=None)
    assert not qualitative.bounds_an_unknown()
    assert assumption().bounds_an_unknown()


# --------------------------------------------------------------------------------------
# What the register reads
# --------------------------------------------------------------------------------------


def test_an_assumption_states_what_it_costs_to_be_wrong():
    with pytest.raises(ValidationError, match="sentence a reviewer can check"):
        assumption(statement="throughput ok")
    with pytest.raises(ValidationError, match="what breaks"):
        assumption(consequence_if_false="bad")


def test_pedigree_is_mandatory_so_a_speculative_assumption_is_visible():
    """The same type every belief carries, so an assumption resting on speculation is exactly as
    visible as a speculative number -- and it is why this type is not split into a thin identity
    plus a version, since ADR-007 requires the register to carry it WITH pedigree."""
    assert assumption().pedigree.level == "speculative"
    assert "pedigree" in Assumption.model_fields
    with pytest.raises(ValidationError):
        Assumption(
            assumption_id="x", statement="y" * 45, consequence_if_false="z" * 25,
            bound=None, source_refs=[], review_by=None,
        )


def test_review_by_must_postdate_the_assessment():
    assumption(review_by=dt.date(2027, 1, 1))
    with pytest.raises(ValidationError, match="never valid"):
        assumption(review_by=dt.date(2026, 9, 3))


def test_review_by_is_required_and_explicitly_nullable():
    """DEV-4's defect, not repeated: `= None` would make "considered, this bound does not go
    stale" and "nobody thought about it" the same document."""
    with pytest.raises(ValidationError):
        Assumption(
            assumption_id="x", statement="y" * 45, consequence_if_false="z" * 25,
            bound=None, pedigree=ped(), source_refs=[],
        )


# --------------------------------------------------------------------------------------
# The reverse index, computed forward
# --------------------------------------------------------------------------------------


def test_dependents_are_computed_by_walking_forward():
    """ADR-007 requires the register to carry "the objects that depend on it", and every edge in
    FarSight is a forward pointer -- a back-pointer would change the hash of its target and
    re-version every belief citing it."""
    unknown = Unknown(
        what_is_missing="No published receive-train throughput exists anywhere.",
        bounding_assumption_ref=HEX_B, pedigree=ped(),
    )
    docs = [("digest_unknown", unknown), ("digest_source", source())]
    assert dependents_of(HEX_B, docs) == {"digest_unknown"}
    assert dependents_of("c" * 64, docs) == frozenset()


def test_dependents_finds_a_nested_citation():
    """An assumption_refs list can sit inside a larger document rather than at its top level."""
    nested = {"models": [{"binding": {"assumption_refs": [HEX_B]}}]}
    assert dependents_of(HEX_B, [("deep", nested)]) == {"deep"}


def test_revision_history_is_not_dependency():
    """`supersedes` is excluded from the dependency edges. Putting history in the one column the
    reverse index exists for would report a withdrawn assumption as still load-bearing."""
    superseding = {"supersedes": HEX_B, "revision_reason": "withdrawn"}
    assert dependents_of(HEX_B, [("later", superseding)]) == frozenset()


def test_knowledge_objects_canonicalize_without_a_float():
    out = canonicalize(assumption().model_dump(mode="json"))
    assert "0.30" in out
    assert content_hash(source().model_dump(mode="json"))
