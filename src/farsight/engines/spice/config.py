"""The SPICE provider's own config document. ADR-003, ADR-018.

``StageSpec.config_ref`` is an **opaque** content address as far as the core is concerned: ADR-003
makes provider config the provider's business, and ADR-018 calls it an "opaque engine-native
config document". This module is where that opacity ends -- the one place that knows what
``config_dialect: "spice_geometry_v1"`` means.

Living under ``engines/spice/`` rather than in ``schemas/`` is the point, not an accident. If the
core could parse this, ``config_dialect`` would be decoration and every new provider would need a
core change to describe itself.

**What the document carries**, and why each piece is here rather than in the ``StageSpec``:

* the ordered ``KernelSet`` -- ADR-018 says the worker "furnishes the stage's ordered ``KernelRef``
  list" from this document, and ADR-016 makes the order part of the set's identity;
* one entry per emitted channel, each pairing an ADR-015 ``GeometryRequest`` with the **unit** its
  answer is in and the channel name it lands on.

The unit is a declared, hashed input rather than a lookup inside the adapter. It enters every
``channel_hash`` (ADR-011 decision 2), so if it lived only in a table here, changing it would move
every channel hash while every design hash stood still -- "the number changes, the hash changes,
and nothing in the package says why", which is the shape ADR-015 Option 7 was rejected for. It is
checked against what the provider actually produces and never used to convert, because a
conversion here would be a second numeric path no hash covers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from farsight.schemas.channels import validate_channel_name
from farsight.schemas.common import FrozenModel, VersionedDocument, validate_segment
from farsight.schemas.geometry import GeometryRequest
from farsight.schemas.kernels import KernelSet

__all__ = ["SPICE_GEOMETRY_DIALECT", "EmittedQuantity", "SpiceGeometryConfig"]

# ADR-003: `config_dialect` names the provider's OWN schema, so the version lives in the dialect
# string. A change to this document's shape is a new dialect, not a silent reinterpretation of an
# archived config_ref.
SPICE_GEOMETRY_DIALECT = "spice_geometry_v1"


class EmittedQuantity(FrozenModel):
    """One channel this stage emits: what to compute, in what unit, under what name.

    ``emit`` is a channel path **relative to the stage's node** (ADR-020, ADR-018). The run-level
    name is ``stage_id + "." + emit``, so a stage with ``stage_id: "geometry"`` emitting ``range``
    produces ``geometry.range`` -- which is the spelling ADR-009's examples already use.
    """

    emit: str
    unit: str
    request: GeometryRequest

    @model_validator(mode="after")
    def _check(self) -> EmittedQuantity:
        # A single segment, because the qualifier is supplied by the stage id. A dotted `emit`
        # would let a stage emit into another stage's namespace, which ADR-018's pairwise
        # non-overlap rule exists to prevent.
        validate_segment(self.emit, what="emitted channel name")
        if not self.unit or self.unit.strip() != self.unit:
            raise ValueError(
                "a channel unit is a non-empty astropy-parseable symbol, '1' for dimensionless "
                "(ADR-008); an empty string is a second spelling for dimensionless"
            )
        return self


class SpiceGeometryConfig(VersionedDocument):
    """Everything the SPICE geometry provider needs, and nothing the core has to understand."""

    dialect: Literal["spice_geometry_v1"]
    kernel_set: KernelSet
    quantities: tuple[EmittedQuantity, ...]

    @model_validator(mode="after")
    def _check(self) -> SpiceGeometryConfig:
        if not self.quantities:
            raise ValueError(
                "a geometry stage with no quantities computes nothing; an empty stage that "
                "succeeds is the least useful green result there is"
            )
        names = [q.emit for q in self.quantities]
        if len(set(names)) != len(names):
            duplicated = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(
                f"emitted channels {duplicated} appear more than once. Each channel is one file, "
                f"so a duplicate is one request silently overwriting another's answer"
            )
        return self

    def qualified_names(self, stage_id: str) -> list[str]:
        """The run-level channel names this config produces under ``stage_id``.

        Validated here rather than assembled by the caller, so the qualification rule lives with
        the grammar that constrains it.
        """
        return [validate_channel_name(f"{stage_id}.{q.emit}") for q in self.quantities]
