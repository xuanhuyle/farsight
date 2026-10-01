"""The object store: frozen documents, addressed by what they contain.

ADR-011 decision 1. Frozen content-addressed documents live at
``objects/<first2>/<hash>.json``, each file being the two-key ``{"object", "provenance"}``
envelope of ADR-001 decision 4. The address is ``sha256(JCS(object))`` -- the ``provenance`` half
is **not** part of it.

**Why a file store and not a table.** ADR-011 puts exactly three tables in SQLite -- the run
ledger, the alias registry and the audit log -- and says "no evidence content ever lives here".
Losing the database costs an index rebuild, never evidence. An auditor opening a package finds
JSON they can read in a text editor rather than a storage engine standing between them and the
numbers, which ADR-011 gives as its reason for rejecting the SQLite-as-primary-store option.

**Bytes are elsewhere.** ADR-016 keeps kernel bytes in a parallel cache at
``kernels/<first2>/<sha256>``, keyed identically but with no extension, precisely because this
store "is walked in full by ``verify``, by package build and by dedup" -- putting
multi-hundred-megabyte binaries in that walk makes all three proportional to kernel volume. So a
``DataArtifact`` *record* is an object here; the bytes it describes are not.

**Freezing is idempotent.** ADR-001 decision 6: refreezing identical content yields the identical
hash and writes nothing. This store implements that literally -- ``put`` of an object already
present is a no-op that returns the same address, and does **not** overwrite the existing
provenance. The first writer's account of who froze it stands, because rewriting it would erase
the very attestation the audit log exists to preserve.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from farsight.hashing.canonical import canonical_bytes, content_hash
from farsight.registry.atomic import write_atomic
from farsight.schemas.common import Provenance, is_ref
from farsight.schemas.errors import FarSightError

__all__ = ["ObjectStore", "ObjectStoreError", "document_of"]


class ObjectStoreError(FarSightError, ValueError):
    """An object could not be stored or retrieved, or what came back was not what was asked for."""


class ObjectStore:
    """A content-addressed file store rooted at a directory.

    The root holds ``objects/<first2>/<hash>.json``. Nothing else in this class knows about
    workspaces, packages or ``$FARSIGHT_HOME`` -- the caller supplies a root, which keeps the
    store testable in a temp directory and usable for both a workspace and a package.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, ref: str) -> Path:
        """Where the object with address ``ref`` lives. Pure; touches no disk."""
        if not is_ref(ref):
            raise ObjectStoreError(
                f"{ref!r} is not a content address. A Ref is 64 lowercase hex with no algorithm "
                f"prefix (ADR-001 rule 7); an alias cannot syntactically appear here."
            )
        return self.root / "objects" / ref[:2] / f"{ref}.json"

    def put(self, obj: Any, provenance: Provenance) -> str:
        """Store ``obj`` with its provenance and return its content address.

        Idempotent by ADR-001 decision 6. If the address already exists on disk, nothing is
        written and the existing provenance is left alone -- see the module docstring.
        """
        document = document_of(obj)
        ref = content_hash(document)
        destination = self.path_for(ref)

        if destination.exists():
            return ref

        envelope = {
            "object": document,
            "provenance": provenance.model_dump(mode="json"),
        }
        # json.dumps rather than the canonicalizer: only the `object` half is canonicalized, and
        # it already was, above, to produce `ref`. The envelope file's own bytes are protected by
        # the package file manifest (ADR-007), not by being canonical themselves. Newline "\n"
        # explicitly so Windows text translation cannot change what lands on disk.
        payload = json.dumps(envelope, indent=2, sort_keys=True) + "\n"
        write_atomic(destination, payload.encode("utf-8"))
        return ref

    def get(self, ref: str) -> dict[str, Any]:
        """Read the object half back, verifying that it still hashes to ``ref``.

        The verification is the point. A store that returned whatever bytes were at the path would
        make the address a filename rather than a guarantee, and tampering would be invisible
        until something downstream disagreed.
        """
        destination = self.path_for(ref)
        if not destination.exists():
            raise ObjectStoreError(f"no object at {ref} (looked in {destination})")

        envelope = json.loads(destination.read_text(encoding="utf-8"))
        if set(envelope) != {"object", "provenance"}:
            raise ObjectStoreError(
                f"{destination} does not have exactly the two top-level keys 'object' and "
                f"'provenance' (ADR-001 decision 4); found {sorted(envelope)}"
            )

        actual = content_hash(envelope["object"])
        if actual != ref:
            raise ObjectStoreError(
                f"object at {destination} hashes to {actual}, not to the {ref} its path claims. "
                f"The address is the identity, so this file is either corrupt or was edited in "
                f"place -- neither of which the store may paper over."
            )
        return envelope["object"]

    def get_provenance(self, ref: str) -> dict[str, Any]:
        """The unhashed half. Read separately because it is not part of what the object *is*."""
        destination = self.path_for(ref)
        if not destination.exists():
            raise ObjectStoreError(f"no object at {ref} (looked in {destination})")
        return json.loads(destination.read_text(encoding="utf-8"))["provenance"]

    def exists(self, ref: str) -> bool:
        return self.path_for(ref).exists()

    def refs(self) -> list[str]:
        """Every address in the store, sorted. Used by ``verify`` and by package build.

        ADR-016 rejected putting large binaries in this store precisely because this walk exists
        and must stay proportional to the number of documents rather than to kernel volume.
        """
        objects_dir = self.root / "objects"
        if not objects_dir.is_dir():
            return []
        found = []
        for path in objects_dir.glob("*/*.json"):
            ref = path.stem
            if is_ref(ref) and path.parent.name == ref[:2]:
                found.append(ref)
        return sorted(found)


def document_of(obj: Any) -> Any:
    """The JSON document of ``obj``, after re-running its schema.

    **Why the store validates and the hash function does not.**
    :func:`farsight.hashing.canonical.hash_object` is a byte operation: give it any mapping and
    it addresses what it was given, which is the correct behaviour for a general-purpose hash
    and is what ``verify`` needs when re-addressing raw JSON read back from disk.

    This path is different, because storing a document is where FarSight starts making
    evidence-grade claims about it. ADR-001's rule is that **a content address is the address
    of a validated document**, so the address minted here has to mean that a validator saw this
    exact content -- not that one saw some earlier state of the object.

    Two routes reach a schema-violating instance even though the model is frozen and its
    containers now refuse mutation (:class:`farsight.schemas.common.FrozenList`):
    ``model_construct``, which skips every validator by design, and ``object.__setattr__``.
    Neither is exotic: ``model_construct`` is what a caller reaches for when profiling says
    validation is hot. Revalidating here costs one pass per stored object and closes both,
    whatever new route appears later.

    A non-model (a plain dict read back from disk, say) is passed through unchanged. There is no
    schema to re-run, and this function does not invent one.

    **The payload is validated, not the object.** MEASURED 2026-09-30: an earlier version
    validated ``dict(obj.__dict__)``, which hands Pydantic the *already-constructed* nested model
    instances. Pydantic accepts an instance of the right class without re-running its field
    validators, so a ``Pedigree`` built by ``model_construct`` with ``sources=["not-a-digest"]``,
    embedded in an otherwise valid ``Deterministic``, passed straight through -- while validating
    the serialized payload rejects it. Nested documents are the normal shape here, so a guard
    that stops at the outer model guards almost nothing.

    Validating ``model_dump(mode="json")`` is the fix, and it is the right object to validate for
    a second reason: it is exactly what gets written to disk and hashed, so the address attests
    to a payload a validator actually saw. The validated model is then re-dumped and that is what
    is persisted, so any normalization a validator performs is in the stored bytes rather than
    only in memory.
    """
    if not isinstance(obj, BaseModel):
        return obj
    payload = obj.model_dump(mode="json")
    try:
        validated = type(obj).model_validate(payload)
    except ValidationError as exc:
        raise ObjectStoreError(
            f"refusing to address a {type(obj).__name__} that does not satisfy its own schema. "
            f"A content address is the address of a validated document (ADR-001), so this "
            f"object cannot be stored until it is valid:\n{exc}"
        ) from exc
    return validated.model_dump(mode="json")


def envelope_bytes(obj: Any, provenance: Provenance) -> bytes:
    """The exact bytes :meth:`ObjectStore.put` would write. Exposed for tests and package build."""
    envelope = {"object": document_of(obj), "provenance": provenance.model_dump(mode="json")}
    return (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode("utf-8")


def object_address(obj: Any) -> str:
    """The address ``obj`` would be stored at. Pure, and the same function ``put`` uses."""
    return content_hash(document_of(obj))


# Re-exported so callers do not reach into the hashing package for the one thing they need here.
__all__ += ["canonical_bytes", "envelope_bytes", "object_address"]
