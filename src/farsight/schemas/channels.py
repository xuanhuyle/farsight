"""The sample grid and the channel declaration. ADR-020.

**Sample index *i* becomes a time here, and nowhere else.** ADR-009's "first violation is the
lowest sample index", ADR-006's Tier-B comparison epochs and ADR-010's predicate cadence all
presuppose a shared index that no record defined until ADR-020. This module is that definition.

**The grid is expanded in exact arithmetic, never by accumulating a float.** ADR-020 decision 4
says sample *i* sits at ``epoch0`` advanced by ``i * step``, computed from the decimal-string step.
The distinction is not pedantic: accumulating ``t += 0.1`` eight thousand times drifts, and the
drift lands in an epoch that feeds a geometry call, so the resulting error is a wrong position
rather than a wrong timestamp. :func:`epoch_seconds` multiplies instead of accumulating, in
``Decimal``, which makes the *i*-th epoch independent of every epoch before it.

**One grid per run, shared by every channel.** Stronger than ADR-018's composition rule, and
deliberately: ADR-009's metrics consume channels from different stages in one elementwise
expression, so equality only along binding edges is not enough. That restriction is what lets
runs be indexed against each other without anyone interpolating -- and **no interpolation exists
anywhere in the truth loop**.

**Absence is a code, never a non-finite.** ADR-020 decision 2. ADR-023 makes any non-finite sample
a divergence, so an engine writing NaN into a dead entity's column marks the whole run diverged
and pushes verdicts toward indeterminate -- precisely for the runs whose attrition physics worked
as designed. That interaction is invisible until a campaign returns all-indeterminate for no
discoverable reason, which is why the convention is stated rather than discovered.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from farsight.schemas.common import FrozenModel, Quantity, Ref, validate_path, validate_segment
from farsight.schemas.geometry import SECONDS, Epoch

__all__ = [
    "CODE_MAX",
    "RUN_CHANNELS",
    "RUN_NAMESPACE",
    "RUN_T_ELAPSED",
    "ChannelDecl",
    "ExplicitGrid",
    "SampleGrid",
    "UniformGrid",
    "elapsed_seconds",
    "epoch_seconds",
    "validate_channel_name",
]

# ADR-020 decision 1. The one namespace not resolved against the topology, and its closed
# membership. `run` is forbidden as a topology node name by ADR-017, which is what keeps the two
# name spaces from colliding.
RUN_NAMESPACE = "run"
RUN_T_ELAPSED = "run.t_elapsed"
RUN_CHANNELS: frozenset[str] = frozenset({RUN_T_ELAPSED})

# ADR-020 decision 2: codes are integers in [-2**53, 2**53], so equality against a code is exact
# in float64 rather than a floating-point comparison in disguise.
CODE_MAX = 2**53


class UniformGrid(FrozenModel):
    """``epoch0`` advanced by ``i * step``. The ordinary case."""

    kind: Literal["uniform"] = "uniform"
    epoch0: Epoch
    step: Quantity
    n_samples: int = Field(ge=1)

    @field_validator("step")
    @classmethod
    def _check_step(cls, v: Quantity) -> Quantity:
        if v.unit != SECONDS:
            raise ValueError(f"a grid step is an interval in {SECONDS!r}, not {v.unit!r}")
        if v.as_decimal() <= 0:
            raise ValueError(
                f"a grid step is strictly positive; {v.magnitude!r} would give a grid whose "
                f"sample order is not its time order, and every record that speaks of 'the "
                f"lowest sample index' (ADR-009) assumes those are the same thing"
            )
        return v


class ExplicitGrid(FrozenModel):
    """A grid that is not uniform -- pass-scheduled sampling, for instance.

    The epochs live in a hash-pinned ``DataArtifact`` that ships in ``inputs/`` rather than as
    thousands of numbers embedded in a hashed JSON document.
    """

    kind: Literal["explicit"] = "explicit"
    epochs_artifact: Ref


SampleGrid = Annotated[UniformGrid | ExplicitGrid, Field(discriminator="kind")]


def epoch_seconds(grid: UniformGrid, i: int) -> Decimal:
    """TDB seconds past J2000 for sample ``i``, exactly.

    ``epoch0 + i * step`` by multiplication in ``Decimal``, so sample *i* does not depend on the
    samples before it and no rounding accumulates along the grid. ADR-020 decision 4 requires
    exactly this and forbids the accumulating alternative by name.
    """
    if not 0 <= i < grid.n_samples:
        raise IndexError(
            f"sample index {i} is outside the grid's {grid.n_samples} samples. There is no "
            f"extrapolation here: a comparison epoch off the grid is a freeze-time refusal "
            f"(ADR-020 decision 4), never a resampling"
        )
    return grid.epoch0.seconds_past_j2000.as_decimal() + Decimal(i) * grid.step.as_decimal()


def elapsed_seconds(grid: UniformGrid, i: int) -> float:
    """Seconds elapsed from ``epoch0``, as the float64 ``run.t_elapsed`` carries.

    ADR-020 decision 5: ``t_elapsed[0]`` is exactly ``0.0``. It deliberately carries *elapsed*
    seconds rather than an absolute epoch, because a float64 cannot hold ADR-015's epoch
    representation without a precision claim ADR-020 declines to make -- while elapsed seconds
    over a mission arc are exact to well under a microsecond.
    """
    if not 0 <= i < grid.n_samples:
        raise IndexError(f"sample index {i} is outside the grid's {grid.n_samples} samples")
    return float(Decimal(i) * grid.step.as_decimal())


def validate_channel_name(name: str) -> str:
    """A channel name is a topology path plus a leaf, with one reserved namespace. ADR-020 rule 1.

    Grammar and the ``run`` namespace only. That the prefix resolves to a node of *this run's*
    topology is a check that needs a topology in hand, and it lives where one exists.
    """
    validate_path(name)
    segments = name.split(".")
    if len(segments) < 2:
        raise ValueError(
            f"channel name {name!r} has one segment; a channel name is a topology path plus a "
            f"leaf, so it has at least two (ADR-020 rule 1)"
        )
    if segments[0] == RUN_NAMESPACE and name not in RUN_CHANNELS:
        raise ValueError(
            f"{name!r} is under the reserved `run` namespace, whose membership is closed and is "
            f"currently {sorted(RUN_CHANNELS)}. An engine diagnostic belonging to no node is not "
            f"a channel; it goes in the engine manifest that collect() returns (ADR-003)"
        )
    return name


class ChannelDecl(FrozenModel):
    """What a node promises to emit. ADR-020 decision 2.

    Knowledge-plane rather than design-plane, because ADR-010's ``FaultMode.detection`` is a
    knowledge-plane object that names channels, and a knowledge-plane record may not reference a
    design-plane one.

    **No field for aberration, frame, or any other production convention.** ADR-020 states the
    rule and the reason: a second, independently authored label can disagree with the config that
    actually produced the numbers, and nothing would catch it. The authoritative record stays in
    the producing stage's hashed ``GeometryRequest`` (ADR-015). ``description`` may say a channel
    is a geometric range; it is not what makes it one.
    """

    name: str                                   # local segment; full path is <node path>.<name>
    unit: str                                   # astropy-parseable; "1" for dimensionless
    components: int = Field(default=1, ge=1)    # trailing axis width; 1 means a scalar channel
    component_labels: list[str] | None = None
    code_map: dict[str, int] | None = None
    description: str
    conforms_to: str | None = None              # optional ObservableDef digest (ADR-028)

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return validate_segment(v, what="channel name")

    @field_validator("unit")
    @classmethod
    def _check_unit(cls, v: str) -> str:
        if v == "" or v.strip() != v:
            raise ValueError(
                "a channel unit is a non-empty astropy-parseable symbol, '1' for dimensionless "
                "(ADR-008). An empty string is a second spelling for dimensionless and is refused"
            )
        return v

    @field_validator("description")
    @classmethod
    def _check_description(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "a channel description is required and non-empty: it is what an auditor reads to "
                "learn what the numbers are, and a blank one is a channel nobody can check"
            )
        return v

    @model_validator(mode="after")
    def _check_axis_and_codes(self) -> ChannelDecl:
        if self.component_labels is not None:
            if len(self.component_labels) != self.components:
                raise ValueError(
                    f"component_labels has {len(self.component_labels)} entries for "
                    f"{self.components} components. The labels are what let an auditor say which "
                    f"relay column 42 is and join it to a fault record naming that relay "
                    f"(ADR-020 decision 2); a mismatched list points at the wrong entity"
                )
            for label in self.component_labels:
                validate_segment(label, what="component label")
            if len(set(self.component_labels)) != len(self.component_labels):
                raise ValueError(
                    "component_labels are join keys, so two columns sharing a label make the "
                    "join ambiguous in a way that reads as a physics result"
                )

        if self.code_map is not None:
            for label, code in self.code_map.items():
                validate_segment(label, what="code_map label")
                if not -CODE_MAX <= code <= CODE_MAX:
                    raise ValueError(
                        f"code {code} for {label!r} is outside [-2**53, 2**53], so equality "
                        f"against it in float64 is no longer exact -- which turns a categorical "
                        f"comparison into a floating-point one in disguise (ADR-020 decision 2)"
                    )
            # Not stated by ADR-020, and refused here for the reason the record gives for codes
            # existing at all: two labels sharing a code make `== "safe"` and `== "idle"` the
            # same predicate, silently. A categorical channel whose distinct states are not
            # distinct is worse than no code map.
            codes = list(self.code_map.values())
            if len(set(codes)) != len(codes):
                raise ValueError(
                    "two labels in code_map share a code, which makes two different predicates "
                    "the same predicate without saying so"
                )

        return self
