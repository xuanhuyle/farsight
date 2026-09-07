"""The geometry probe design: what ``farsight geometry --design PATH`` reads. ADR-024.

**This is not an ``ExperimentDesign``, and the name says so.** ADR-024 keeps ``farsight geometry``
as a leaf command for a scheduling reason it states plainly: weeks 1-2 have no planner, no ledger
and no package builder, and the geometry service must still be exercisable and hash-stable. A
``GeometryDesign`` is the smallest hashed document that makes that possible -- a kernel set, one
grid, and a list of requests. It carries no beliefs, no topology, no stages, no metrics and no
claims, because none of those exist yet and a placeholder for each would be a field nobody could
fill honestly.

**The consequence is stated rather than left to be discovered:** a ``GeometryDesign`` hash is not
an ``experiment_hash`` and must never be presented as one. It covers the kernels, the grid and the
conventions -- exactly what a geometry probe's answer depends on -- and nothing else.

**One check is deliberately NOT here.** Every request's ``epochs`` must be the digest of this
design's grid, and that check needs a canonicalizer. ``schemas`` is a leaf package and may not
import ``farsight.hashing`` (contract ``schemas_is_leaf``), and reaching it through a
function-local import would satisfy the linter's letter while defeating its purpose -- the
package would no longer stand alone, which is the property the contract protects. So the check
lives in :func:`farsight.registry.channels.check_requests_name_this_grid`, one layer up, where
hashing is legal. This module gets the structural rules that need no hashing, and no others.

**ADR-024 holds this command at 0.60 confidence.** Once ADR-018's run composition lands, geometry
may be expressible as a one-stage ``RunSpec``, at which point this verb is a second entry point
duplicating ``run``. That record requires the question settled before the first package ships in
week 4, after which the name is permanent. This module exists knowing it may be retired.
"""

from __future__ import annotations

from pydantic import model_validator

from farsight.schemas.channels import UniformGrid, validate_channel_name
from farsight.schemas.common import FrozenModel, VersionedDocument
from farsight.schemas.geometry import GeometryRequest
from farsight.schemas.kernels import KernelSet

__all__ = ["GeometryChannel", "GeometryDesign"]


class GeometryChannel(FrozenModel):
    """One request, the channel its answer is written to, and the unit that answer is in.

    ``unit`` is declared here rather than looked up from the adapter, and the reason is the whole
    argument of ADR-015 decision 6 applied one layer up. The unit enters every ``channel_hash``
    (ADR-011 decision 2). If it lived only in a table inside the SPICE adapter, changing it would
    move every channel hash while the design hash stayed put -- "the number changes, the hash
    changes, and nothing in the package says why", which is the shape ADR-015 Option 7 was
    rejected for.

    It is checked against what the provider actually produces rather than used to convert:
    a declared unit that disagrees with the computed one is refused, because converting here
    would be a second numeric path that no hash covers.
    """

    channel: str
    unit: str
    request: GeometryRequest

    @model_validator(mode="after")
    def _check_channel(self) -> GeometryChannel:
        validate_channel_name(self.channel)
        if not self.unit or self.unit.strip() != self.unit:
            raise ValueError(
                "a channel unit is a non-empty astropy-parseable symbol, '1' for dimensionless "
                "(ADR-008); an empty string is a second spelling for dimensionless"
            )
        return self


class GeometryDesign(VersionedDocument):
    """A kernel set, one grid, and the requests evaluated against them."""

    kernel_set: KernelSet
    grid: UniformGrid
    channels: tuple[GeometryChannel, ...]

    @model_validator(mode="after")
    def _check(self) -> GeometryDesign:
        if not self.channels:
            raise ValueError(
                "a geometry design with no channels computes nothing; an empty run that succeeds "
                "is the least useful green result there is"
            )

        names = [c.channel for c in self.channels]
        if len(set(names)) != len(names):
            duplicated = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(
                f"channels {duplicated} appear more than once. Each channel is one file, so a "
                f"duplicate is one request silently overwriting another's answer"
            )
        return self
