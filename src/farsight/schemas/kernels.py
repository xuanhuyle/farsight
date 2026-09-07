"""Kernel sets: an ordered sequence, where the order is the decision.

ADR-016 decisions 1 and 2. A ``KernelSet`` is the hashed run input, and **reordering it is an
identity change** -- a different order is a different object even when the multiset of kernels is
identical. That is not fussiness about hashing. In a furnished SPICE pool, a later kernel
overrides an earlier one, so the sequence determines which values a run actually reads; two
orderings of the same files are two different physical configurations.

``logical_name`` is provenance and display only, and nothing resolves a kernel by it. That is what
stops a file called ``earth_latest_high_prec.bpc`` from being a moving target inside a frozen
document: the name can say whatever the publisher called it, and the identity is the digest.

``kernel_type`` deliberately has **no** ``mk`` member. A metakernel is an import format, never a
run input (ADR-016 decision 3): it names kernels by path, which reintroduces exactly the ambient
directory the content-addressed cache exists to remove.

``frame_sources`` is the semantic half of the same defence. Which kernel actually realizes
``ITRF93`` in a furnished pool is otherwise an emergent property of ordering that nobody reads;
declaring it makes the answer checkable at freeze. The value is a tuple rather than one digest
because a frame is routinely defined by one kernel and driven by another -- a frames kernel plus
the binary orientation PCK that supplies its data.
"""

from __future__ import annotations

from typing import Literal, Mapping

from pydantic import field_validator, model_validator

from farsight.schemas.common import FrozenModel, VersionedDocument, is_ref

__all__ = ["KernelType", "Attribution", "KernelRef", "KernelSet"]

KernelType = Literal["spk", "pck", "ck", "sclk", "lsk", "ik", "fk", "dsk", "ek"]

Attribution = Literal[
    "naif_unmodified",
    "third_party_unmodified",
    "farsight_authored",
    "modified",
]


class KernelRef(FrozenModel):
    """A content address plus the metadata redistribution and validation need."""

    sha256: str
    kernel_type: KernelType
    logical_name: str
    size_bytes: int
    attribution: Attribution
    modifier: str | None
    parent_sha256: str | None
    license_note: str

    @field_validator("sha256", "parent_sha256")
    @classmethod
    def _digest(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not is_ref(v):
            raise ValueError(
                f"{v!r} must be 64 lowercase hex over the kernel file bytes, with no algorithm "
                f"prefix (ADR-001 rule 7). The digest is the only identity a kernel has."
            )
        return v

    @field_validator("logical_name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a kernel carries the publisher's own file name, for humans")
        return v

    @field_validator("size_bytes")
    @classmethod
    def _size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"size_bytes {v} is not a positive count")
        return v

    @model_validator(mode="after")
    def _attribution_is_complete(self) -> "KernelRef":
        unmodified = self.attribution.endswith("_unmodified")
        if not unmodified and self.attribution != "farsight_authored" and not self.modifier:
            raise ValueError(
                f"attribution {self.attribution!r} requires a named modifier. ADR-012: a modified "
                f"kernel must be re-attributed to whoever modified it, because redistributing it "
                f"under the publisher's name would misstate who is responsible for the bytes."
            )
        if self.attribution == "modified" and not self.parent_sha256:
            raise ValueError(
                "a modified kernel names the parent it was derived from. Without it the "
                "modification is unreviewable: nobody can diff it against what it came from."
            )
        if unmodified and self.parent_sha256:
            raise ValueError(
                f"attribution {self.attribution!r} claims the bytes are unmodified, yet names a "
                f"parent. Those are contradictory statements about the same file."
            )
        return self


class KernelSet(VersionedDocument):
    """The ordered furnish sequence, hashed as a run input.

    ``kernel_set_hash = sha256(JCS(object))``. Reordering changes it, which is the point.
    """

    kernels: tuple[KernelRef, ...]
    frame_sources: Mapping[str, tuple[str, ...]] = {}

    @field_validator("kernels")
    @classmethod
    def _sequence(cls, v: tuple[KernelRef, ...]) -> tuple[KernelRef, ...]:
        if not v:
            raise ValueError("a kernel set furnishes at least one kernel")
        digests = [k.sha256 for k in v]
        if len(set(digests)) != len(digests):
            repeated = sorted({d for d in digests if digests.count(d) > 1})
            raise ValueError(
                f"the sequence repeats {[d[:12] + '...' for d in repeated]}. A repeat is always "
                f"either a mistake or a no-op: furnishing the same file twice cannot change what "
                f"the pool contains, so the second entry states nothing."
            )
        lsk_count = sum(1 for k in v if k.kernel_type == "lsk")
        if lsk_count != 1:
            raise ValueError(
                f"a kernel set contains exactly one leapsecond kernel; found {lsk_count}. "
                f"ADR-015 speaks of 'the pinned LSK' as a single thing, and it only denotes "
                f"something if there is exactly one. Zero means no time conversion is defined; "
                f"two means the later silently overrides the earlier."
            )
        return v

    @model_validator(mode="after")
    def _frame_sources_resolve(self) -> "KernelSet":
        present = {k.sha256 for k in self.kernels}
        for frame, sources in sorted(self.frame_sources.items()):
            if not sources:
                raise ValueError(
                    f"frame {frame!r} declares no source. An empty tuple asserts that nothing "
                    f"realizes the frame, which is not a claim anybody means to make."
                )
            missing = [s for s in sources if s not in present]
            if missing:
                raise ValueError(
                    f"frame {frame!r} names kernels that are not in this set: "
                    f"{[m[:12] + '...' for m in missing]}. A frame realized by a kernel the run "
                    f"does not furnish is a declaration nothing backs."
                )
        return self

    def lsk(self) -> KernelRef:
        """The one leapsecond kernel. Singular by construction, so this cannot be ambiguous."""
        return next(k for k in self.kernels if k.kernel_type == "lsk")

    def digests(self) -> tuple[str, ...]:
        """The furnish order, as digests. The order is the decision."""
        return tuple(k.sha256 for k in self.kernels)
