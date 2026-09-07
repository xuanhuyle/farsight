"""A self-contained set of objects addressed by their own digests. ADR-001, ADR-011.

A ``RunSpec`` is mostly references: ``StageSpec.grid`` names a grid descriptor, ``config_ref``
names a provider config, ``inputs`` name artifacts. Something has to turn a digest back into a
document, and there are two honest ways to do it -- resolve against the object store, or carry the
objects alongside the spec. This module is the second, and it exists because the first would make
a week-1 geometry probe require a pre-populated store before it could run once.

**Every object is verified against the address that names it.** That is not a formality: a bundle
whose ``config_ref`` names one document while carrying a different one would compute something
other than what the spec says, and every downstream hash would be internally consistent about the
wrong thing. Re-hashing each object and comparing to its key is the AT-3 tamper class caught at
the cheapest possible point, and it is the same check ``farsight evidence verify`` performs over a
package -- so a bundle is a package's shape, one order of magnitude smaller.

**The two-key envelope is understood.** ADR-001 rule 4: a stored object is ``{object,
provenance}`` and only ``object`` is hashed. A bundle entry may be written either way, and a bare
document is treated as its own object half -- because requiring a hand-authored probe to carry a
provenance block would teach an author to fill one with noise.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from farsight.hashing.canonical import content_hash, is_content_hash
from farsight.schemas.errors import FarSightError

__all__ = ["BundleError", "RefBundle", "object_half"]


class BundleError(FarSightError, ValueError):
    """A bundle is malformed, or an object does not match the address naming it."""


def object_half(entry: Any) -> Any:
    """The hashed half of a bundle entry. ADR-001 rule 4.

    An entry with exactly the two keys ``object`` and ``provenance`` is an envelope; anything else
    is a bare document and is its own object half. Requiring exactly those two keys rather than
    merely the presence of ``object`` matters: a document that happens to have a field called
    ``object`` is not an envelope, and guessing wrong would hash the wrong bytes.
    """
    if isinstance(entry, dict) and set(entry.keys()) == {"object", "provenance"}:
        return entry["object"]
    return entry


class RefBundle:
    """Digest-addressed objects, verified on construction."""

    def __init__(self, objects: Mapping[str, Any]) -> None:
        if not isinstance(objects, Mapping):
            raise BundleError(
                f"a bundle's `objects` is a mapping from content address to document, not a "
                f"{type(objects).__name__}"
            )

        verified: dict[str, Any] = {}
        for ref, entry in objects.items():
            if not is_content_hash(ref):
                raise BundleError(
                    f"bundle key {ref!r} is not a bare lowercase 64-hex content address "
                    f"(ADR-001 rule 7). A name where an address belongs is how two different "
                    f"documents come to share a key"
                )
            body = object_half(entry)
            actual = content_hash(body)
            if actual != ref:
                raise BundleError(
                    f"bundle object filed under {ref[:12]}... actually hashes to "
                    f"{actual[:12]}.... The document is not the one this address names, so "
                    f"anything computed from it would be internally consistent about the wrong "
                    f"input (the AT-3 tamper class)"
                )
            verified[ref] = body
        self._objects = verified

    def __contains__(self, ref: str) -> bool:
        return ref in self._objects

    def __len__(self) -> int:
        return len(self._objects)

    def refs(self) -> list[str]:
        return sorted(self._objects)

    def resolve(self, ref: str, *, what: str = "object") -> Any:
        """The document at ``ref``, or a refusal naming what could not be resolved.

        AT-3 requires a failure to name the exact item, so the message says which reference was
        unresolvable and what it was needed for -- not that something was missing.
        """
        if ref not in self._objects:
            raise BundleError(
                f"{what} {ref[:12]}... is not in the bundle. A reference that resolves to nothing "
                f"is an unresolved input hash, which is a completeness failure rather than a "
                f"schema one: the document is well-formed and describes something absent. "
                f"Bundle carries {len(self._objects)} object(s): "
                f"{[r[:12] + '...' for r in self.refs()]}"
            )
        return self._objects[ref]

    def resolve_as(self, ref: str, model: Any, *, what: str = "object") -> Any:
        """Resolve and validate into ``model``, keeping the address in the failure message."""
        body = self.resolve(ref, what=what)
        try:
            return model.model_validate(body)
        except Exception as exc:
            raise BundleError(
                f"{what} {ref[:12]}... does not validate as {model.__name__}: {exc}"
            ) from exc
