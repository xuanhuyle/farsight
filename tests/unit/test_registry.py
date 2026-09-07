"""The object store, atomic writes, and DataArtifact (ADR-011, ADR-001, ADR-012).

The store's whole job is that an address is a guarantee rather than a filename. Two tests carry
that: reading back verifies the hash rather than trusting the path, and an interrupted write
leaves the destination either untouched or complete, never a mixture.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from farsight.hashing.canonical import content_hash
from farsight.registry.atomic import AtomicWriteError, write_atomic
from farsight.registry.objects import ObjectStore, ObjectStoreError, object_address
from farsight.schemas.common import Provenance, Quantity
from farsight.schemas.knowledge import DataArtifact

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "farsight"

import datetime as dt


def prov(**over) -> Provenance:
    base = dict(
        created_at=dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc),
        frozen_by="operator:jh",
        authorization="attended",
        tool_version="0.0.1",
    )
    return Provenance(**{**base, **over})


def artifact(**over) -> DataArtifact:
    base = dict(
        url="https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls",
        sha256="b" * 64,
        size_bytes=5386,
        modified=False,
        license_note="NAIF: public domain, no restrictions on redistribution.",
    )
    return DataArtifact(**{**base, **over})


# --------------------------------------------------------------------------------------
# Atomic writes
# --------------------------------------------------------------------------------------


def test_a_write_either_lands_completely_or_not_at_all(tmp_path, monkeypatch):
    """The failure has to be injected BEFORE os.replace. Patching after it has already run tests
    nothing -- the rename is the atomic step, so anything after it is past the danger."""
    target = tmp_path / "thing.json"
    write_atomic(target, b"original")

    import farsight.registry.atomic as atomic_module

    def explode(_src, _dst):
        raise RuntimeError("power loss")

    monkeypatch.setattr(atomic_module.os, "replace", explode)
    with pytest.raises(RuntimeError, match="power loss"):
        write_atomic(target, b"replacement")

    assert target.read_bytes() == b"original", "a failed write must not disturb the destination"
    assert list(tmp_path.glob("*.tmp.*")) == [], "a failed write must not leave debris"


def test_a_fresh_write_leaves_no_file_when_it_fails(tmp_path, monkeypatch):
    import farsight.registry.atomic as atomic_module

    target = tmp_path / "new.json"
    monkeypatch.setattr(
        atomic_module.os, "replace", lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with pytest.raises(RuntimeError):
        write_atomic(target, b"data")
    assert not target.exists()
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_the_temp_file_is_a_sibling_of_the_destination(tmp_path):
    """os.replace is atomic only within one filesystem. A temp file in the system temp directory
    and a destination on another volume would silently become a copy with a window in the middle."""
    seen: list[Path] = []
    target = tmp_path / "sub" / "thing.json"

    real_open = open

    def watching_open(path, *args, **kwargs):
        seen.append(Path(path))
        return real_open(path, *args, **kwargs)

    import builtins

    original = builtins.open
    builtins.open = watching_open
    try:
        write_atomic(target, b"x")
    finally:
        builtins.open = original

    temps = [p for p in seen if ".tmp." in p.name]
    assert temps, "expected a temp file"
    assert temps[0].parent == target.parent


def test_bytes_are_written_verbatim_on_every_platform(tmp_path):
    """Text mode would translate '\\n' into '\\r\\n' on Windows and change the very bytes about
    to be hashed. The failure would surface as a cross-platform hash mismatch far from its cause."""
    payload = b"line one\nline two\n"
    target = write_atomic(tmp_path / "x.txt", payload)
    assert target.read_bytes() == payload
    assert len(target.read_bytes()) == len(payload)


def test_text_is_refused_rather_than_encoded_for_the_caller():
    with pytest.raises(AtomicWriteError, match="takes bytes"):
        write_atomic("unused.txt", "a string")


# --------------------------------------------------------------------------------------
# The object store
# --------------------------------------------------------------------------------------


def test_an_object_round_trips_through_disk(tmp_path):
    store = ObjectStore(tmp_path)
    ref = store.put(artifact(), prov())
    assert store.exists(ref)
    assert store.get(ref) == artifact().model_dump(mode="json")


def test_the_address_is_computed_from_the_bytes_not_from_the_object_in_memory(tmp_path):
    """A round-trip test that hashes the in-memory model would pass even if the writer mangled
    the file. Read the bytes back off disk and hash those."""
    store = ObjectStore(tmp_path)
    ref = store.put(artifact(), prov())

    envelope = json.loads(store.path_for(ref).read_text(encoding="utf-8"))
    assert content_hash(envelope["object"]) == ref


def test_the_provenance_half_does_not_change_the_address(tmp_path):
    """ADR-001 decision 4: content_hash is over `object` alone. If provenance entered the hash,
    freezing identical content twice on different days would give two addresses, and nothing
    would be reproducible by construction."""
    store = ObjectStore(tmp_path)
    first = store.put(artifact(), prov())

    other = ObjectStore(tmp_path / "other")
    second = other.put(
        artifact(),
        prov(created_at=dt.datetime(2029, 1, 1, tzinfo=dt.timezone.utc), frozen_by="operator:xy"),
    )
    assert first == second


def test_the_envelope_has_exactly_two_top_level_keys(tmp_path):
    store = ObjectStore(tmp_path)
    ref = store.put(artifact(), prov())
    envelope = json.loads(store.path_for(ref).read_text(encoding="utf-8"))
    assert set(envelope) == {"object", "provenance"}


def test_reading_verifies_the_hash_rather_than_trusting_the_path(tmp_path):
    """Without this the address is a filename, and an edit in place is invisible until something
    downstream disagrees."""
    store = ObjectStore(tmp_path)
    ref = store.put(artifact(), prov())

    path = store.path_for(ref)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["object"]["size_bytes"] = 999999
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ObjectStoreError, match="hashes to"):
        store.get(ref)


def test_a_malformed_envelope_is_refused_naming_the_rule(tmp_path):
    store = ObjectStore(tmp_path)
    ref = store.put(artifact(), prov())
    store.path_for(ref).write_text(json.dumps({"object": {}}), encoding="utf-8")
    with pytest.raises(ObjectStoreError, match="exactly the two top-level keys"):
        store.get(ref)


def test_freezing_is_idempotent_and_does_not_rewrite_provenance(tmp_path):
    """ADR-001 decision 6: refreezing identical content yields the identical hash and writes
    nothing. The first writer's account of who froze it stands -- rewriting it would erase the
    attestation the audit log exists to preserve."""
    store = ObjectStore(tmp_path)
    ref = store.put(artifact(), prov(frozen_by="operator:first"))
    again = store.put(artifact(), prov(frozen_by="operator:second"))

    assert again == ref
    assert store.get_provenance(ref)["frozen_by"] == "operator:first"


def test_the_layout_is_sharded_by_the_first_two_hex_digits(tmp_path):
    store = ObjectStore(tmp_path)
    ref = store.put(artifact(), prov())
    expected = tmp_path / "objects" / ref[:2] / f"{ref}.json"
    assert store.path_for(ref) == expected
    assert expected.exists()


def test_an_alias_cannot_be_used_as_an_address(tmp_path):
    """ADR-001 rule 7: a Ref is 64 lowercase hex with no algorithm prefix, so an alias cannot
    syntactically appear where a reference belongs."""
    store = ObjectStore(tmp_path)
    for bad in ("refs/model/link_budget", "sha256:" + "a" * 64, "A" * 64, ""):
        with pytest.raises(ObjectStoreError, match="not a content address"):
            store.path_for(bad)


def test_refs_lists_what_is_there_and_nothing_else(tmp_path):
    store = ObjectStore(tmp_path)
    assert store.refs() == []
    a = store.put(artifact(), prov())
    b = store.put(artifact(size_bytes=1), prov())
    (tmp_path / "objects" / "zz").mkdir(parents=True)
    (tmp_path / "objects" / "zz" / "not-a-hash.json").write_text("{}", encoding="utf-8")
    assert store.refs() == sorted([a, b])


def test_a_missing_object_is_an_error_not_an_empty_result(tmp_path):
    store = ObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError, match="no object at"):
        store.get("c" * 64)


def test_object_address_agrees_with_put(tmp_path):
    store = ObjectStore(tmp_path)
    assert object_address(artifact()) == store.put(artifact(), prov())


# --------------------------------------------------------------------------------------
# DataArtifact
# --------------------------------------------------------------------------------------


def test_a_data_artifact_carries_no_timestamp(tmp_path):
    """ADR-012's sketch lists `fetched_at_utc`; ADR-001 decision 4 forbids it in the hashed half.
    Two fetches of identical bytes must produce one address, or the dedup that
    `Referent.artifact_refs` and the kernel cache rely on is gone."""
    assert "fetched_at_utc" not in DataArtifact.model_fields
    with pytest.raises(Exception):
        DataArtifact(
            url="https://x/y", sha256="b" * 64, size_bytes=1, modified=False,
            license_note="n", fetched_at_utc="2026-09-07T00:00:00Z",
        )


def test_two_fetches_of_the_same_bytes_give_one_address():
    assert object_address(artifact()) == object_address(artifact())


def test_the_url_is_inside_the_hash():
    """ADR-016's KERN-2 check is that the DataArtifact carries the source URL. A publisher not
    covered by the digest is a provenance claim nothing protects."""
    assert object_address(artifact()) != object_address(artifact(url="https://elsewhere/y"))


def test_the_byte_hash_is_a_bare_digest():
    with pytest.raises(Exception, match="64 lowercase hex"):
        artifact(sha256="sha256:" + "b" * 64)


def test_a_modified_artifact_must_name_its_modifier():
    """ADR-012: kernels are redistributed only unmodified, and the flag exists because a modified
    kernel must be re-attributed."""
    artifact(modified=True, license_note="Trimmed to the 2024 coverage window by FarSight.")
    with pytest.raises(Exception, match="must carry a license note"):
        artifact(modified=True, license_note="   ")


# --------------------------------------------------------------------------------------
# ADR-011 Enforcement 10: the atomic-write discipline lint (due week 2)
# --------------------------------------------------------------------------------------

_WRITE_CALLS = {"write_text", "write_bytes", "save"}
_EXEMPT = {"registry/atomic.py"}


def test_nothing_writes_a_file_except_the_atomic_helper():
    """ADR-011 Enforcement 10. A direct `open(..., "w")` bypasses the fsync-and-replace sequence,
    so a crash mid-write leaves a truncated file that looks complete -- and the object store's
    address would then name bytes that were never fully written.

    PARTIALLY MECHANIZED (STORE-1): an AST lint sees syntactic call sites, not a write reached
    through an alias or a third-party helper.
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC.parent.parent).as_posix().replace("src/farsight/", "")
        if rel in _EXEMPT or rel.startswith("analysis/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                mode = _mode_of(node)
                if mode and ("w" in mode or "a" in mode or "x" in mode):
                    offenders.append(f"{rel}:{node.lineno}: open(..., {mode!r})")
            elif isinstance(func, ast.Attribute) and func.attr in _WRITE_CALLS:
                offenders.append(f"{rel}:{node.lineno}: .{func.attr}()")
    assert not offenders, (
        "file writes outside the atomic helper (ADR-011 Enforcement 10):\n  " + "\n  ".join(offenders)
    )


def _mode_of(call: ast.Call) -> str | None:
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        return str(call.args[1].value)
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return None


def test_the_write_lint_recognises_what_it_is_meant_to_catch():
    """The lint above scans a tree that currently has no violation, so it would pass just as
    happily if its matching were broken."""
    samples = [
        'open("x", "w")',
        'open("x", "wb")',
        'open("x", mode="a")',
        'Path("x").write_text("y")',
        'Path("x").write_bytes(b"y")',
        'np.save("x", arr)',
    ]
    for source in samples:
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                mode = _mode_of(node)
                found |= bool(mode and ("w" in mode or "a" in mode or "x" in mode))
            elif isinstance(func, ast.Attribute) and func.attr in _WRITE_CALLS:
                found = True
        assert found, f"the lint would not have caught: {source}"


# --------------------------------------------------------------------------------------
# Provenance, the unhashed half
# --------------------------------------------------------------------------------------


def test_provenance_requires_an_unambiguous_timestamp():
    """It is not hashed, but it is read by a human deciding whether to trust a package. A naive
    timestamp means something different to every reader."""
    prov()
    with pytest.raises(Exception, match="UTC offset"):
        prov(created_at=dt.datetime(2026, 9, 7, 12, 0))


def test_provenance_names_who_froze_it_and_with_what():
    """ADR-001 states the consequence bluntly: the hash does NOT attest to who froze the object.
    That attestation is here, and it is worthless if blank."""
    for blank in ("", "   "):
        with pytest.raises(Exception, match="names who froze"):
            prov(frozen_by=blank)
        with pytest.raises(Exception, match="names who froze"):
            prov(tool_version=blank)


def test_authorization_is_a_closed_pair():
    prov(authorization="unattended")
    with pytest.raises(Exception):
        prov(authorization="semi_attended")
