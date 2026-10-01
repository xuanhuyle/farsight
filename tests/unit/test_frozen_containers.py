"""A frozen document's nested containers refuse mutation, and the store refuses to address an
object that does not satisfy its own schema.

MEASURED 2026-09-30, against commit bc4cdbd. ``frozen=True`` stops attribute assignment and the
overridden ``model_copy`` stops an unvalidated update, but neither reached one level down:

    p = Pedigree(level="measured_flight", sources=[digest], assessor="hle", ...)
    p.sources.clear()          # worked
    hash_object(p)             # returned a 64-hex address for a document whose own validator
                               # rejects it -- `model_validate` on the same payload raises

Appending ``"not-a-digest"`` to that list worked too, putting a value that is not a ``Ref``
inside a document whose schema says every entry is one. Both are the defect ``model_copy``
already had, one level down: **a content address is the address of a validated document**
(ADR-001), and here the mutation happened after the validator ran.

Two layers are tested, because neither alone is enough:

* the containers refuse mutation, which closes the demonstrated failure at its root;
* the object store revalidates before addressing, which closes ``model_construct`` and
  ``object.__setattr__`` -- routes no container can defend against.

``hash_object`` itself stays permissive and is tested to stay that way. It is a byte operation
over whatever it is handed, which is exactly what ``verify`` needs when re-addressing raw JSON
read back from disk; it is not the place that makes an evidence-grade claim.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from pydantic import ValidationError

from farsight.hashing.canonical import hash_object
from farsight.registry.objects import ObjectStore, ObjectStoreError, object_address
from farsight.schemas.belief import Deterministic, Pedigree
from farsight.schemas.common import (
    FrozenDict,
    FrozenList,
    IntervalQ,
    Provenance,
    Quantity,
    ValidityEnvelope,
    freeze_containers,
)

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64

# The address this exact document had before the containers were frozen, measured on the commit
# under review. Pinned because the fix must not move a single existing content address: a
# `FrozenList` serialises to the same JSON array a `list` does, and this is what says so.
PEDIGREE_ADDRESS_BEFORE_THE_FIX = (
    "e109bc86e2b2f17e9bee29678bc2f08e5da33d897dd9be921e2b3642125495d3"
)


def _pedigree() -> Pedigree:
    return Pedigree(
        level="measured_flight",
        sources=[DIGEST],
        assessor="h. le",
        assessed_on=_dt.date(2026, 9, 30),
    )


def _provenance() -> Provenance:
    return Provenance(
        created_at=_dt.datetime(2026, 9, 30, tzinfo=_dt.UTC),
        frozen_by="pytest",
        authorization="unattended",
        tool_version="test",
    )


def _envelope() -> ValidityEnvelope:
    return ValidityEnvelope(
        conditions=["elevation above 20 degrees"],
        ranges={"elevation": IntervalQ(
            lower=Quantity(magnitude="20", unit="deg"),
            upper=Quantity(magnitude="90", unit="deg"),
        )},
    )


# --------------------------------------------------------------------------------------------
# The demonstrated failure


def test_the_demonstrated_failure_is_closed():
    """The exact sequence the review reproduced, start to finish."""
    pedigree = _pedigree()
    with pytest.raises(TypeError, match="frozen document"):
        pedigree.sources.clear()
    assert pedigree.sources == [DIGEST], "the list must be unchanged after a refused mutation"
    # And the object still addresses, because nothing about it changed.
    assert len(hash_object(pedigree)) == 64


def test_the_same_payload_is_still_rejected_by_validation():
    """The asymmetry that made the original report a defect rather than a preference."""
    with pytest.raises(ValidationError):
        Pedigree.model_validate(
            {"level": "measured_flight", "sources": [],
             "assessor": "h. le", "assessed_on": "2026-09-30"}
        )


def test_an_invalid_entry_cannot_be_appended():
    """The other half of the same hole: inserting a value that is not a Ref."""
    pedigree = _pedigree()
    with pytest.raises(TypeError, match="frozen document"):
        pedigree.sources.append("not-a-digest")
    assert pedigree.sources == [DIGEST]


# --------------------------------------------------------------------------------------------
# The class of mutation, not the one call


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda s: s.clear(), id="clear"),
    pytest.param(lambda s: s.append(OTHER_DIGEST), id="append"),
    pytest.param(lambda s: s.extend([OTHER_DIGEST]), id="extend"),
    pytest.param(lambda s: s.insert(0, OTHER_DIGEST), id="insert"),
    pytest.param(lambda s: s.remove(DIGEST), id="remove"),
    pytest.param(lambda s: s.pop(), id="pop"),
    pytest.param(lambda s: s.sort(), id="sort"),
    pytest.param(lambda s: s.reverse(), id="reverse"),
    pytest.param(lambda s: s.__setitem__(0, OTHER_DIGEST), id="setitem"),
    pytest.param(lambda s: s.__delitem__(0), id="delitem"),
    pytest.param(lambda s: s.__iadd__([OTHER_DIGEST]), id="iadd"),
    pytest.param(lambda s: s.__imul__(2), id="imul"),
])
def test_every_list_mutator_is_refused(mutate):
    pedigree = _pedigree()
    with pytest.raises(TypeError, match="frozen document"):
        mutate(pedigree.sources)
    assert pedigree.sources == [DIGEST]


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda d: d.clear(), id="clear"),
    pytest.param(lambda d: d.update({"x": None}), id="update"),
    pytest.param(lambda d: d.setdefault("x", None), id="setdefault"),
    pytest.param(lambda d: d.pop("elevation"), id="pop"),
    pytest.param(lambda d: d.popitem(), id="popitem"),
    pytest.param(lambda d: d.__setitem__("x", None), id="setitem"),
    pytest.param(lambda d: d.__delitem__("elevation"), id="delitem"),
    pytest.param(lambda d: d.__ior__({"x": None}), id="ior"),
])
def test_every_dict_mutator_is_refused(mutate):
    envelope = _envelope()
    with pytest.raises(TypeError, match="frozen document"):
        mutate(envelope.ranges)
    assert set(envelope.ranges) == {"elevation"}


def test_a_list_inside_a_model_reached_through_another_field_is_frozen_too():
    """Every list field, not the one the report happened to name."""
    envelope = _envelope()
    for field in (envelope.conditions, envelope.not_validated_for):
        assert isinstance(field, FrozenList)
        with pytest.raises(TypeError, match="frozen document"):
            field.append("added later")


def test_containers_nested_inside_containers_are_frozen():
    """A list of lists, or a dict of lists, is frozen all the way down."""
    frozen = freeze_containers({"outer": [["inner"], {"deeper": ["leaf"]}]})
    assert isinstance(frozen, FrozenDict)
    assert isinstance(frozen["outer"], FrozenList)
    assert isinstance(frozen["outer"][0], FrozenList)
    assert isinstance(frozen["outer"][1], FrozenDict)
    assert isinstance(frozen["outer"][1]["deeper"], FrozenList)
    with pytest.raises(TypeError, match="frozen document"):
        frozen["outer"][1]["deeper"].append("x")


def test_models_built_by_validate_and_copy_are_frozen_as_well():
    """Every construction route, since one unfrozen route would be the whole hole again."""
    validated = Pedigree.model_validate(
        {"level": "measured_flight", "sources": [DIGEST],
         "assessor": "h. le", "assessed_on": "2026-09-30"}
    )
    copied = _pedigree().model_copy(update={"assessor": "someone else"})
    deep = _pedigree().model_copy(deep=True)
    for pedigree in (validated, copied, deep):
        assert isinstance(pedigree.sources, FrozenList)
        with pytest.raises(TypeError, match="frozen document"):
            pedigree.sources.clear()


# --------------------------------------------------------------------------------------------
# Reading is untouched, and no address moves


def test_reading_a_frozen_container_behaves_exactly_like_the_builtin():
    pedigree = _pedigree()
    assert pedigree.sources == [DIGEST]          # equal to a plain list
    assert list(pedigree.sources) == [DIGEST]
    assert pedigree.sources[0] == DIGEST
    assert len(pedigree.sources) == 1
    assert DIGEST in pedigree.sources
    seen = []
    for source in pedigree.sources:                       # the iteration protocol still works
        seen.append(source)
    assert seen == [DIGEST]
    # Non-mutating concatenation is still allowed: it returns a new object and leaves this one
    # alone. Spelled with the dunder so that a tidier rewrite cannot quietly drop the case.
    assert pedigree.sources.__add__([OTHER_DIGEST]) == [DIGEST, OTHER_DIGEST]
    assert pedigree.sources == [DIGEST]


def test_no_existing_content_address_moves():
    """The compatibility claim, pinned rather than asserted in prose."""
    assert hash_object(_pedigree()) == PEDIGREE_ADDRESS_BEFORE_THE_FIX


def test_the_json_document_still_contains_plain_arrays_and_objects():
    """What gets hashed must be ordinary JSON, whatever the in-memory types are."""
    dumped = _pedigree().model_dump(mode="json")
    assert dumped["sources"] == [DIGEST]
    assert type(dumped["sources"]) is list or isinstance(dumped["sources"], list)
    envelope = _envelope().model_dump(mode="json")
    assert set(envelope["ranges"]) == {"elevation"}


# --------------------------------------------------------------------------------------------
# The store boundary: the routes no container can close


def _invalid_by_construct() -> Pedigree:
    """`model_construct` skips every validator by design -- this is not an exotic route."""
    return Pedigree.model_construct(
        level="measured_flight", sources=[], assessor="", assessed_on=_dt.date(2026, 9, 30)
    )


def test_hash_object_stays_permissive_and_is_not_the_guard():
    """Documented behaviour, tested so that a later 'fix' here is a deliberate decision.

    A general-purpose hash that validated would break re-addressing raw JSON read back from
    disk, which is exactly what verification does.
    """
    assert len(hash_object(_invalid_by_construct())) == 64
    assert len(hash_object({"anything": "at all"})) == 64


def test_the_store_refuses_to_address_an_object_that_fails_its_own_schema():
    with pytest.raises(ObjectStoreError, match="validated document"):
        object_address(_invalid_by_construct())


def test_the_store_refuses_to_store_it(tmp_path):
    store = ObjectStore(tmp_path)
    provenance = _provenance()
    with pytest.raises(ObjectStoreError, match="validated document"):
        store.put(_invalid_by_construct(), provenance)
    assert store.refs() == [], "nothing may be written when the object is refused"


def test_a_valid_object_still_stores_and_reads_back(tmp_path):
    """The guard must not cost the ordinary path."""
    store = ObjectStore(tmp_path)
    provenance = _provenance()
    ref = store.put(_pedigree(), provenance)
    assert ref == PEDIGREE_ADDRESS_BEFORE_THE_FIX
    assert store.get(ref)["sources"] == [DIGEST]


def test_a_plain_mapping_is_still_storable(tmp_path):
    """There is no schema to re-run on raw JSON, and the store does not invent one."""
    store = ObjectStore(tmp_path)
    provenance = _provenance()
    ref = store.put({"plain": "document"}, provenance)
    assert store.get(ref) == {"plain": "document"}


def test_a_frozen_container_survives_pickling_and_copying_still_frozen():
    """ADR-002 runs engines in separate processes, so a model crosses that boundary pickled.

    MEASURED while writing this: the refusal broke `model_copy(deep=True)`, because both
    `copy.deepcopy` and pickle rebuild a list subclass by appending to an empty one. A freeze
    that cannot be copied would have failed the first time a model reached a worker.
    """
    import copy
    import pickle

    original = _pedigree()
    for restored in (pickle.loads(pickle.dumps(original)),
                     copy.deepcopy(original),
                     copy.copy(original)):
        assert restored.sources == [DIGEST]
        assert isinstance(restored.sources, FrozenList)
        with pytest.raises(TypeError, match="frozen document"):
            restored.sources.clear()
        assert hash_object(restored) == PEDIGREE_ADDRESS_BEFORE_THE_FIX


# --------------------------------------------------------------------------------------------
# Nested documents: the guard has to reach all the way down
#
# MEASURED 2026-09-30. The store validated `dict(obj.__dict__)`, which hands Pydantic the
# already-constructed nested model instances. Pydantic accepts an instance of the right class
# without re-running its field validators, so this passed:
#
#     bad = Pedigree.model_construct(level="measured_flight", sources=["not-a-digest"], ...)
#     document_of(Deterministic(value=Quantity(...), pedigree=bad, ...))   # accepted
#
# while validating the serialized payload rejects it. Nested documents are the normal shape in
# this schema stack, so a guard that stops at the outer model guards almost nothing.


def _valid_envelope() -> ValidityEnvelope:
    return ValidityEnvelope(conditions=["late mission"], ranges={})


def _deterministic_with(pedigree: Pedigree) -> Deterministic:
    return Deterministic(
        kind="deterministic",
        value=Quantity(magnitude="143.86", unit="W"),
        pedigree=pedigree,
        validity=_valid_envelope(),
        derivation=None,
    )


def test_a_nested_invalid_reference_is_refused_at_the_store():
    """The reviewer's exact case, through the real persistence path."""
    bad = Pedigree.model_construct(
        level="measured_flight", sources=["not-a-digest"],
        assessor="h. le", assessed_on=_dt.date(2026, 9, 30),
    )
    belief = _deterministic_with(bad)
    with pytest.raises(ObjectStoreError, match="validated document"):
        object_address(belief)


def test_a_nested_invalid_reference_is_refused_by_put(tmp_path):
    bad = Pedigree.model_construct(
        level="measured_flight", sources=["not-a-digest"],
        assessor="h. le", assessed_on=_dt.date(2026, 9, 30),
    )
    store = ObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError, match="validated document"):
        store.put(_deterministic_with(bad), _provenance())
    assert store.refs() == [], "nothing may be written when the object is refused"


@pytest.mark.parametrize("field, value, why", [
    pytest.param("sources", ["not-a-digest"], "a source that is not a content address",
                 id="invalid-ref"),
    pytest.param("sources", [], "no source at all under a level that claims provenance",
                 id="empty-sources"),
    pytest.param("assessor", "   ", "a blank assessor", id="blank-assessor"),
    pytest.param("level", "not_a_level", "a level outside the closed vocabulary", id="bad-level"),
])
def test_representative_nested_invalid_fields_are_refused(field, value, why, tmp_path):
    """Not just the reported reference: every kind of nested violation must be caught."""
    fields = {
        "level": "measured_flight", "sources": [DIGEST],
        "assessor": "h. le", "assessed_on": _dt.date(2026, 9, 30),
    }
    fields[field] = value
    # The parent is constructed unvalidated too. Pydantic re-runs a nested model's *model-level*
    # validators when the parent is built, but not its field-level constraints -- which is the
    # precise shape of the defect. Building both unvalidated puts every case on the same footing
    # and makes the store the only thing standing between an invalid document and an address.
    belief = Deterministic.model_construct(
        kind="deterministic",
        value=Quantity(magnitude="143.86", unit="W"),
        pedigree=Pedigree.model_construct(**fields),
        validity=_valid_envelope(),
        derivation=None,
    )
    store = ObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError, match="validated document"):
        store.put(belief, _provenance())
    assert store.refs() == []


def test_a_valid_nested_document_still_stores_and_reads_back(tmp_path):
    """The guard must not cost the ordinary nested path, which is most of this schema stack."""
    store = ObjectStore(tmp_path)
    belief = _deterministic_with(_pedigree())
    ref = store.put(belief, _provenance())
    read_back = store.get(ref)
    assert read_back["pedigree"]["sources"] == [DIGEST]
    assert read_back["value"] == {"magnitude": "143.86", "unit": "W"}
    # And the round trip reconstructs an equal object, so persisting the validated form did not
    # quietly change anything.
    assert Deterministic.model_validate(read_back) == belief


def test_the_stored_document_is_the_validated_payload(tmp_path):
    """What is hashed is what a validator saw -- that is the sentence the address stands on."""
    store = ObjectStore(tmp_path)
    belief = _deterministic_with(_pedigree())
    ref = store.put(belief, _provenance())
    assert object_address(belief) == ref
    assert hash_object(Deterministic.model_validate(store.get(ref))) == ref


def test_nested_documents_survive_copying_pickling_and_serialisation(tmp_path):
    """Compatibility, checked rather than assumed, since the fix changed what gets persisted."""
    import copy
    import pickle

    belief = _deterministic_with(_pedigree())
    store = ObjectStore(tmp_path)
    reference = store.put(belief, _provenance())
    for restored in (pickle.loads(pickle.dumps(belief)), copy.deepcopy(belief),
                     belief.model_copy(deep=True), copy.copy(belief)):
        assert restored == belief
        assert object_address(restored) == reference
        assert isinstance(restored.pedigree.sources, FrozenList)
        with pytest.raises(TypeError, match="frozen document"):
            restored.pedigree.sources.clear()
