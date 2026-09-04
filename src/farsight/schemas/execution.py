"""Run composition, and the boundary where a parameter becomes a number an engine sees.

ADR-018. A ``RunSpec`` carries an ordered list of stages and the worker composes them in one
process. This module owns the *lowering* half of that: what a stage binds, and -- the subject of
finding G1 -- what a bound value remembers about where it came from.

**The defect this module exists to close.** ADR-018 lowered a parameter into
``ValueSource{kind, value}``: the number, and nothing else. The topology path it was bound at
was dropped. Only *aleatory* draws kept their path, through ``seeds_<i>.json.aleatory_values``.
So every deterministic and every derived parameter had no reconstructible edge into any run, and
the only join available was matching decimal strings -- which ADR-001 makes meaningless on
purpose, since ``"0.220"`` and ``"0.22"`` are different objects precisely so that a value is
never a key.

Two things depended on that missing edge, and neither is small. ADR-004 requires ``verify`` to
**recompute** collapse taint by intersecting a collapse's scope with the parameter paths a result
depends on; with the paths gone there was nothing to intersect for the deterministic half. And
"show every claim materially dependent on a speculative assumption" -- the question the product
exists to answer -- was unanswerable for the majority of beliefs.

**The decision here is that a value lowered as a stage binding cannot exist without saying where
it came from.** ``ValueSource.path`` is required, not optional. A literal with no declared origin
is exactly the silently-fitted constant ADR-001 rule 6 forbids, so the type refuses to express
one.

**That sentence is deliberately narrower than "a number cannot enter a run unattributed", which
would be false.** Two other routes carry numbers into a run and neither is closed here:

  * ``ArtifactSource`` cites a ``DataArtifact`` by digest, and a data artifact may contain any
    number of physical quantities with no topology paths attached. A planner could put forty
    deterministic parameters into one artifact and bind it as a single input. The artifact is
    hashed, so the values are *fixed and auditable*, but they are not *attributed* -- nothing
    says which ``ParameterDecl`` each came from. Closing this needs a schema for ``DataArtifact``
    content, which no record has written.
  * ``config_ref`` is the larger hole and is **structural, not an oversight**. ADR-003 makes a
    provider's config document opaque per dialect and commits FarSight to never reading it
    physically; ADR-018 restates that. So a link-chain config can carry a detector dark-count
    rate that moves the answer, and no validator here or anywhere may look inside to find it. No
    change to this module can close it without contradicting an accepted record.

The check that actually bounds both is ADR-017 decision 5's binding completeness -- every
``ParameterDecl`` under an active subtree must be bound exactly once -- which turns "a quantity
lives in an opaque blob" into "a quantity that should have been a declared parameter is missing
from the design". That check needs a ``SystemTopology`` and is listed in
:meth:`RunSpec.unenforced_rules`. Until it runs, this module makes lineage *complete for the
values it lowers* and says nothing about values that arrive by the other two routes. Claiming
otherwise would be the same class of overstatement the product exists to prevent.

``origin`` is the second half, and it is what a bare ``path`` cannot do:

  * A per-group aleatory parameter draws ``len(members)`` values **from one binding at one
    topology path** (ADR-027). Several ``ValueSource`` objects in one run therefore share a path,
    and ``group_member`` is what tells them apart.
  * AT-6 requires that a ``RunSpec`` assigning a point value to a flagged ``Unknown`` be
    *rejected by schema*. But an ``Unknown`` carrying a declared sweep legitimately produces
    point values. A path alone cannot distinguish "scanning a bracket we declared" from
    "inventing a number for something we admitted we do not know". ``ValueOrigin`` has a member
    for the first and none for the second, so the refusal is structural rather than a validator
    somebody can relax.

**What this module does not yet contain.** ``RunSpec`` here is deliberately partial: it carries
what ADR-018, ADR-001 and ADR-005 pin by name, and omits the sample grid, the time span and the
end epoch, which are ADR-015's and ADR-020's types and do not exist yet. The omission is stated
rather than filled with a placeholder, because a placeholder in the most-hashed document in the
system is a decision disguised as a stub. Two of ADR-018's six composition rules likewise cannot
run yet and say so where they would be checked, rather than passing silently (see
``RunSpec.unenforced_rules``).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import Field, field_validator, model_validator

from farsight.schemas.errors import SpecCompositionError
from farsight.schemas.common import (
    FrozenModel,
    MAX_SEGMENT_CHARS,
    Quantity,
    Ref,
    SEGMENT_RE,
    VersionedDocument,
    is_under,
    validate_path,
)

__all__ = [
    "SpecCompositionError",
    "ValueOrigin",
    "GridRef",
    "ChannelSource",
    "ArtifactSource",
    "ValueSource",
    "StageInput",
    "StageModel",
    "StageSpec",
    "RunSpec",
    "STAGE_INPUT_MEMBERS",
    "model_versions",
    "parameter_paths",
    "paths_reaching_stage",
    "value_sources_for_path",
]


# The origin of a value that reached a run. Closed, and the closure is the point.
#
# Every member names a route that ADR-004 or ADR-005 explicitly sanctions:
#
#   deterministic       an authored Deterministic belief (ADR-004)
#   derived             a Deterministic carrying a Derivation, evaluated at freeze (ADR-029)
#   aleatory_draw       a planner draw from stream 0, at plan time, in sorted path order (ADR-005)
#   epistemic_point     an outer-scan coordinate: an interval vertex or a set member (ADR-004)
#   unknown_sweep_point a point from an Unknown's DECLARED sweep (ADR-004); the evidence package
#                       stamps these NOT FITTED, and that stamp needs this to be distinguishable
#   unknown_bounded     an Unknown discharged by a named bounding assumption (ADR-004). This is
#                       the SECOND of the two legal resolutions -- `Unknown.freeze_ready` returns
#                       True for a sweep declaration OR a bounding assumption -- and omitting it
#                       would make a legal frozen design impossible to lower, which is a worse
#                       failure than the one the omission was guarding against.
#   collapse            the chosen value of a human-authorized EpistemicCollapse (ADR-004)
#
# There is deliberately NO member for a value assigned to an Unknown that declared NEITHER a
# sweep nor a bounding assumption (AT-6), and none for a literal with no parameter behind it at
# all (ADR-001 rule 6). Both are enforced by the absence of a way to say them -- the technique of
# ADR-018's own missing `run_output` member and ADR-006's golden attestation, which has no
# `farsight_output` enum member.
#
# A collapse whose `chosen` is `Aleatory` (ADR-004 types it `Deterministic | Aleatory`) lowers
# the DRAWN value as `aleatory_draw`, not as `collapse`: what reached the engine is a draw, and
# `collapse` names a value the collapse fixed directly. Nothing is lost, because taint is
# recomputed from the scope-path intersection and the register, never from this field -- which is
# ADR-004's rule that the recomputation, not a stored marker, is the authority.
ValueOrigin = Literal[
    "deterministic",
    "derived",
    "aleatory_draw",
    "epistemic_point",
    "unknown_sweep_point",
    "unknown_bounded",
    "collapse",
]

# Origins for which a `group_member` qualifier is meaningful. A GroupedBinding (ADR-027) expands
# at freeze into per-member *paths*, so its values are already distinguished by path; only a
# per-group SAMPLING SCOPE keeps one path and draws once per member.
_GROUPED_ORIGINS = frozenset({"aleatory_draw"})


class GridRef(FrozenModel):
    """A reference to the run's sample grid. ADR-020 owns the descriptor itself."""

    grid_id: str

    @field_validator("grid_id")
    @classmethod
    def _check(cls, v: str) -> str:
        if not SEGMENT_RE.match(v) or len(v) > MAX_SEGMENT_CHARS:
            raise ValueError(f"grid_id {v!r} is outside the segment grammar (ADR-017 rule 3)")
        return v


class ChannelSource(FrozenModel):
    """A binding to a channel emitted by a strictly earlier stage of the same run."""

    kind: Literal["channel"] = "channel"
    from_stage: str
    channel: str

    @field_validator("from_stage", "channel")
    @classmethod
    def _check_paths(cls, v: str) -> str:
        return validate_path(v)


class ArtifactSource(FrozenModel):
    """A binding to a hash-addressed input artifact listed in ``RunSpec.inputs``."""

    kind: Literal["artifact"] = "artifact"
    artifact_ref: Ref


class ValueSource(FrozenModel):
    """A literal value, and the parameter it came from.

    ``path`` and ``origin`` are the G1 repair. Both are mandatory: a value that reached a run
    without a declared parameter behind it is a hidden default, and hidden defaults with
    scientific meaning are what ADR-001 rule 6 exists to forbid.

    Note what this does **not** claim. The path is checked as a *grammar*, not resolved: whether
    it names a real ``ParameterDecl`` under an active subtree is ADR-017 decision 5's freeze
    check, which needs the topology. And ``origin`` is asserted by the planner, not proved here;
    the freeze validator is what cross-checks each one against the belief actually bound at that
    path. Recording the claim is still worth it, because a *wrong* origin is then a detectable
    disagreement between two documents, where a *missing* origin was undetectable by anything.

    **Why ``derived`` is a member but ``grouped`` is not**, since the asymmetry looks arbitrary.
    ADR-017 decision 4 says a ``GroupedBinding`` and a ``DerivedBinding`` both materialize into
    ordinary ``ParameterBinding`` objects "so the completeness rule in decision 5, the sort order,
    and everything downstream of it are unchanged by either", and ADR-027 goes further: a grouped
    object and its hand-authored expansion must yield an **identical** ``experiment_hash``. A
    ``grouped`` origin would break that outright, since the same design authored two ways would
    lower to different bytes. Derivation is different in kind: ADR-029 decision 4 materializes a
    belief carrying ``pedigree.level: "derived_analysis"`` and its expression, so the frozen
    design already distinguishes a computed value from an authored one. Recording it here reads a
    fact the design states; recording a group route would invent one the design deliberately
    erases.

    **Hyperparameter coordinates do not appear at this boundary**, and the absence is deliberate
    rather than an oversight a later reader should repair. When an epistemic interval is a
    *hyperparameter* of a distribution -- a Rayleigh whose sigma is an interval -- the outer scan
    resolves sigma and the planner then *draws* from the resolved distribution. What reaches a
    stage is the drawn value, lowered as ``aleatory_draw`` at the belief's own path; sigma itself
    never becomes a stage input. So no field addressing "which hyperparameter" is needed here,
    and taint stays correct because a collapse scoped at that path covers the draw. Recording the
    outer coordinate itself is ADR-004's and ADR-022's business, one document up.
    """

    kind: Literal["value"] = "value"
    value: Quantity
    path: str
    origin: ValueOrigin
    group_member: str | None = None

    @field_validator("path")
    @classmethod
    def _check_path(cls, v: str) -> str:
        return validate_path(v)

    @model_validator(mode="after")
    def _check_group_member(self) -> "ValueSource":
        if self.group_member is None:
            return self
        if not SEGMENT_RE.match(self.group_member) or len(self.group_member) > MAX_SEGMENT_CHARS:
            raise ValueError(
                f"group_member {self.group_member!r} is outside the segment grammar. It names an "
                f"enumeration member (ADR-027)."
            )
        # A numeric-looking member name is legal: ADR-017 permits numeric segments, and "a
        # numeric suffix is characters only and carries no meaning". It is not refused here
        # because refusing it would be a rule no record states. What matters is that nothing
        # downstream may read it as a position -- members are ordered by byte-wise sort of their
        # names, so an enumeration with members "3" and "10" orders "10" first, and any code
        # that treats this field as an index is wrong regardless of what it contains.
        if self.origin not in _GROUPED_ORIGINS:
            raise ValueError(
                f"origin {self.origin!r} carries a group_member, but only a per-group SAMPLING "
                f"SCOPE keeps one path across several members (ADR-027). A GroupedBinding "
                f"expands at freeze into per-member paths, so its values are already told apart "
                f"by their path and a member qualifier here would be a second, disagreeing "
                f"answer to the same question."
            )
        return self


StageInput = Annotated[
    Union[ChannelSource, ArtifactSource, ValueSource],
    Field(discriminator="kind"),
]

# ADR-018 Enforcement item 2. Named so that `test_stage_binding_closure` asserts against a
# constant rather than a literal it could drift from. A fourth member is a violation of a named
# enforcement test, not a schema extension: the closed
# `(experiment_hash, run_index) -> spec_hash` derivation rests on no stage input being able to
# name another run's output.
STAGE_INPUT_MEMBERS = (ChannelSource, ArtifactSource, ValueSource)


class StageModel(FrozenModel):
    """A ``ModelVersion`` this stage runs, and how it came to be the one running.

    The Model to Run edge (finding D1). ADR-026's freeze validator
    ``model_binding_consistent`` is written against "every ``StageSpec`` (ADR-018) naming that
    model", and ADR-026's Related-ADRs line says "a stage names the model it runs" -- but
    ADR-018's ``StageSpec`` has eight fields and none of them names a ``ModelVersion``. The edge
    existed in prose in two accepted records and in no field, so the validator quantified over
    something unwritable and "which model produced this number" had no answer.

    ``path`` is what stops this from re-opening G1 for a different value type. A model *family*
    is enumerated as ``EpistemicSet.members: list[ModelVersionRef]`` (ADR-004) -- "the
    atmospheric law is Kolmogorov or it is von Karman, and we do not know which" -- so which
    model runs can itself be an epistemic coordinate that the outer scan varies. That choice
    cannot lower through :class:`ValueSource`, whose ``value`` is a ``Quantity`` and cannot hold
    a digest. So this is the lowering site for it, and without a path a model-family coordinate
    would be exactly the unattributed value G1 was about.

    ``path`` is required and explicitly nullable, which is a different thing from optional.
    ``None`` is an authored statement -- *this stage runs this model because the design says so,
    not because a parameter selected it* -- and the author has to write it. A ``= None`` default
    would make "fixed by the design" and "nobody filled this in" the same document, which is the
    hidden-default shape ADR-001 rule 6 forbids.
    """

    model_version_ref: Ref
    path: str | None

    @field_validator("path")
    @classmethod
    def _check_path(cls, v: str | None) -> str | None:
        return v if v is None else validate_path(v)


class StageSpec(FrozenModel):
    """One stage of a run: a geometry provider or an engine, with its bindings.

    ``bindings`` maps a **provider-dialect** parameter name to its source. That dict key is the
    engine's own vocabulary, which is exactly why ``ValueSource.path`` has to exist: the key
    says what the engine calls the number, and only the path says what FarSight calls it.

    ``models`` is required and may be empty. Empty is an assertion -- *this stage runs no
    separately identified model version* -- and it is true of a SPICE geometry stage, whose
    ephemerides are data (ADR-016 ``KernelRef``) rather than a modelled thing. Because the field
    has no default, writing ``[]`` is a statement an author made rather than a field nobody
    reached, which is the distinction ADR-007 already draws for registers: an empty register is
    an assertion, a missing register is a verification failure.

    Plural, not the ``model_ref`` singular the review sketched: ADR-026's validator says "every
    `StageSpec` naming that model", and one stage legitimately runs several -- the DSOC link
    chain has an atmospheric model and a detector model, and they version independently.
    """

    stage_id: str
    kind: Literal["geometry", "engine"]
    provider_id: str
    config_dialect: str
    config_ref: Ref
    grid: GridRef
    bindings: dict[str, StageInput]
    emits: list[str]
    models: list[StageModel]

    @field_validator("models")
    @classmethod
    def _check_models(cls, v: list[StageModel]) -> list[StageModel]:
        # An entry is a *selection*, not an execution, so uniqueness is on the (model, path)
        # pair. Two paths naming one model version is ordinary: a grouped binding over three
        # relay hops (ADR-027) selects a propagation model per hop, and two hops choosing the
        # same version is a coincidence, not a contradiction. Deduplicating on the digest alone
        # would refuse that legal document -- and `model_versions` already collapses the set for
        # callers asking which models ran.
        keys = [(m.model_version_ref, m.path) for m in v]
        if len(set(keys)) != len(keys):
            raise ValueError(
                f"stage repeats the same (model, path) selection: "
                f"{sorted({k for k in keys if keys.count(k) > 1})}. The same model selected at "
                f"the same path twice says nothing the single entry does not."
            )
        if keys != sorted(keys, key=lambda k: (k[0], k[1] or "")):
            raise ValueError(
                "models must be byte-wise sorted by (model_version_ref, path), so that two "
                "stages running the same models are the same document and hash alike"
            )
        paths = [m.path for m in v if m.path is not None]
        if len(set(paths)) != len(paths):
            raise ValueError(
                f"one path selects more than one model version in this stage: "
                f"{sorted({p for p in paths if paths.count(p) > 1})}. A parameter names the "
                f"model that runs; naming two is the design disagreeing with itself about which "
                f"physics executed."
            )
        return v

    @field_validator("stage_id")
    @classmethod
    def _check_stage_id(cls, v: str) -> str:
        # ADR-020: a stage_id must be a node path in ADR-017's grammar, which is what makes a
        # qualified channel name a topology path.
        return validate_path(v)

    @field_validator("provider_id", "config_dialect")
    @classmethod
    def _check_segment(cls, v: str) -> str:
        if not SEGMENT_RE.match(v) or len(v) > MAX_SEGMENT_CHARS:
            raise ValueError(f"{v!r} is outside the segment grammar (ADR-017 rule 3)")
        return v

    @field_validator("emits")
    @classmethod
    def _check_emits(cls, v: list[str]) -> list[str]:
        for name in v:
            validate_path(name)
        if len(set(v)) != len(v):
            raise ValueError(f"stage emits a channel name twice: {sorted({c for c in v if v.count(c) > 1})}")
        if v != sorted(v):
            raise ValueError(
                "emitted channel names must be byte-wise sorted, so that two stages emitting the "
                "same set are the same document (ADR-017 decision 5's reasoning, applied here)"
            )
        return v

    def value_sources(self) -> list[ValueSource]:
        """Every literal bound into this stage, in binding-key order."""
        return [b for _, b in sorted(self.bindings.items()) if isinstance(b, ValueSource)]

    def selection_paths(self) -> frozenset[str]:
        """Paths whose bound parameter selected one of this stage's model versions."""
        return frozenset(m.path for m in self.models if m.path is not None)


class RunSpec(VersionedDocument):
    """The complete causal input to one run (ADR-018, plan §4).

    **Partial by declaration.** ADR-018 writes this class as ``stages`` plus ``...``. The fields
    here are the ones records pin by name: ``experiment_hash`` and ``run_index`` (ADR-005's run
    addressing), ``stages`` (ADR-018), ``inputs`` (the ``DataArtifact`` digests an
    ``ArtifactSource`` may name). The sample grid, the time span and ``end_time`` belong to
    ADR-015 and ADR-020, whose types do not exist yet, and are **absent rather than stubbed** --
    a placeholder field inside ``spec_hash`` would be a decision disguised as a stub.
    """

    experiment_hash: Ref
    run_index: int
    stages: list[StageSpec]
    inputs: list[Ref] = Field(default_factory=list)

    @field_validator("run_index")
    @classmethod
    def _check_index(cls, v: int) -> int:
        if v < 0:
            raise ValueError("run_index is a position in a deterministic enumeration, never negative")
        return v

    @model_validator(mode="after")
    def _compose(self) -> "RunSpec":
        stages = self.stages

        # Rule 6 -- a run must contain at least one stage.
        if not stages:
            raise SpecCompositionError(
                "a run must contain at least one stage (ADR-018 rule 6). An empty stage list is "
                "a run that computes nothing, which is a design error rather than a fast run."
            )

        # Rule 1 (structural half) -- stage ids unique and pairwise non-overlapping. The half
        # that needs a SystemTopology is named in `unenforced_rules`.
        ids = [s.stage_id for s in stages]
        if len(set(ids)) != len(ids):
            raise SpecCompositionError(
                f"stage ids must be unique within a run; repeated: "
                f"{sorted({i for i in ids if ids.count(i) > 1})}. The stage id qualifies every "
                f"channel name this run produces (ADR-018), so a duplicate makes two different "
                f"channels indistinguishable by name."
            )
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if is_under(a, b) or is_under(b, a):
                    raise SpecCompositionError(
                        f"stage nodes {a!r} and {b!r} overlap (ADR-018 rule 1): no stage's node "
                        f"may equal or be an ancestor of another's, or their channel namespaces "
                        f"collide."
                    )

        # Rule 2 -- at most one engine stage, and if present it is last.
        engine_at = [i for i, s in enumerate(stages) if s.kind == "engine"]
        if len(engine_at) > 1:
            raise SpecCompositionError(
                f"a run has at most one engine stage (ADR-018 rule 2); found "
                f"{[stages[i].stage_id for i in engine_at]}. There is no third stage kind, and "
                f"the absence of one is the mechanical form of 'this is not a workflow engine'."
            )
        if engine_at and engine_at[0] != len(stages) - 1:
            raise SpecCompositionError(
                f"the engine stage {stages[engine_at[0]].stage_id!r} must be last (ADR-018 rule "
                f"2); geometry is materialized before the engine stage begins, which is what "
                f"lets a state-dependent trigger reference geometry without a second SPICE call."
            )

        # Rules 3 and 4 -- channel bindings name a strictly earlier stage, a channel that stage
        # actually declares, and a stage sharing this one's grid.
        seen: dict[str, StageSpec] = {}
        for stage in stages:
            for key, source in sorted(stage.bindings.items()):
                if not isinstance(source, ChannelSource):
                    continue
                producer = seen.get(source.from_stage)
                if producer is None:
                    raise SpecCompositionError(
                        f"stage {stage.stage_id!r} binding {key!r} reads "
                        f"{source.from_stage!r}, which is not a strictly earlier stage of this "
                        f"run (ADR-018 rule 3). Order is total, so acyclicity is structural -- "
                        f"a forward or self reference is refused rather than checked for cycles."
                    )
                if source.channel not in producer.emits:
                    raise SpecCompositionError(
                        f"stage {stage.stage_id!r} binding {key!r} reads channel "
                        f"{source.channel!r} from {source.from_stage!r}, which does not declare "
                        f"it; that stage emits {producer.emits} (ADR-018 rule 3)."
                    )
                if producer.grid.grid_id != stage.grid.grid_id:
                    raise SpecCompositionError(
                        f"stage {stage.stage_id!r} (grid {stage.grid.grid_id!r}) reads a channel "
                        f"from {source.from_stage!r} (grid {producer.grid.grid_id!r}) "
                        f"(ADR-018 rule 4). Elementwise consumption of a channel computed on a "
                        f"different time base is the silent-killer class this rule closes."
                    )
            seen[stage.stage_id] = stage

        # G1: a per-group draw is the one case where several values share a path. Anywhere else,
        # two values at one path in one run means the run states the same parameter twice.
        by_path: dict[str, list[ValueSource]] = {}
        for stage in stages:
            for v in stage.value_sources():
                by_path.setdefault(v.path, []).append(v)
        for path, sources in sorted(by_path.items()):
            members = [v.group_member for v in sources]
            if len(sources) > 1 and (None in members or len(set(members)) != len(members)):
                raise SpecCompositionError(
                    f"path {path!r} is bound to {len(sources)} values in this run without "
                    f"distinct group members. One path carries one value per run, except a "
                    f"per-group sampling scope which draws once per enumeration member "
                    f"(ADR-027). Two unqualified values at one path is the run disagreeing with "
                    f"itself about what the parameter is."
                )

        # D1: a model selection is the second lowering site, so the "bound exactly once" rule
        # (ADR-017 decision 4) has to span both. A path that is a value in one stage and a model
        # choice in another is two routes claiming one parameter, which that record makes a
        # freeze failure naming the path.
        model_paths: dict[str, list[str]] = {}
        for stage in stages:
            for model in stage.models:
                if model.path is not None:
                    model_paths.setdefault(model.path, []).append(stage.stage_id)
        for path, owners in sorted(model_paths.items()):
            if path in by_path:
                raise SpecCompositionError(
                    f"path {path!r} is bound both as a value and as a model selection "
                    f"(stages {sorted(owners)}). A path may be bound exactly once by exactly "
                    f"one route (ADR-017 decision 4); two routes claiming one path is a freeze "
                    f"failure naming the path."
                )
            if len(set(owners)) != len(owners):
                raise SpecCompositionError(
                    f"path {path!r} selects more than one model within a single stage "
                    f"({sorted(owners)}). One parameter names one model version per run."
                )
        return self

    def engine_id(self) -> str | None:
        """The engine this run belongs to, computed and never stored (ADR-018).

        ``None`` is a legitimate answer: a run with no engine stage is a geometry-only run, and
        computing this rather than storing it keeps ADR-003's "a GeometryProvider is not an
        Engine" literally true -- no code path can call a geometry provider an engine.
        """
        return next((s.provider_id for s in self.stages if s.kind == "engine"), None)

    def unenforced_rules(self) -> list[str]:
        """ADR-018 composition rules this schema cannot check yet, and what each one needs.

        Returned rather than documented so the gap is machine-readable: a test asserts this list
        shrinks to empty as the missing types land, which is what stops a deferred check from
        quietly becoming a forgotten one. Compare ``Aleatory.sample`` and ``enumerate_outer``,
        which refuse outright -- these cannot, because a run must still be constructible before
        ``knowledge.py`` exists, so the honest form is a declared absence rather than silence.
        """
        return [
            "rule 1 (resolution half): each stage_id resolves to a node in the run's "
            "SystemTopology -- needs schemas/knowledge.py",
            "rule 5: a ConditionSchedule predicate over an engine channel requires that provider "
            "to declare supports_stepping -- needs schemas/faults.py and the engine capability "
            "registry",
            "binding completeness (ADR-017 decision 5): every ParameterDecl under an active "
            "subtree is bound exactly once, and no value arrives by a route that skips a "
            "declaration -- needs schemas/knowledge.py. This is the check that bounds the "
            "ArtifactSource and config_ref gaps described in the module docstring",
            "model_binding_consistent (ADR-026): a ModelVersion with an engine_native binding "
            "names an engine_id and a config_dialect, and every StageSpec naming it carries a "
            "config_ref whose dialect matches -- needs schemas/knowledge.py. This schema "
            "supplies the edge the validator quantifies over; it cannot yet resolve the digest",
            "origin agreement: each ValueSource's declared origin and magnitude match the belief "
            "actually bound at its path in the frozen design -- needs schemas/design.py. Until "
            "it runs, an origin is a planner assertion this schema records but does not prove",
        ]


def parameter_paths(spec: RunSpec) -> frozenset[str]:
    """Every topology path this run's inputs came from.

    This is the set ADR-004 requires ``verify`` to intersect with a collapse's scope. It is a
    union over *all* stages, which is complete for a run: a ``ChannelSource`` reads an earlier
    stage of the same run, and that stage's own literals are already in the union, so no
    traversal is needed.

    **One hop, not transitive.** A derived value's own inputs (ADR-029) live on the belief in the
    frozen design, not in the run, so closing over them needs the design as well. That step
    belongs to the freeze validator, which has both documents; doing it here would require this
    function to accept a design and would make the run-level question -- which parameters were
    *bound into this run* -- unaskable on its own.

    **Prefer :func:`paths_reaching_stage` when the question is about one metric.** This
    whole-run union is the coarsest honest answer, and a taint computed from it credits a metric
    over a geometry channel with the engine stage's parameters too. Use this only when the
    question really is "what went into this run".

    **The transitive closure has a dependency worth stating, because nothing checks it yet.**
    Walking from a derived value to its contributing parameters requires the package to carry the
    complete frozen ``UncertaintySpec``, including every materialized ``Deterministic.derivation``
    -- not merely the runs. If the evidence package ever ships the run set without that, this
    function stays correct and the transitive question silently becomes unanswerable for an
    external auditor, which is the failure G1 was about, one level up. Recorded in
    ``docs/adr/IMPLEMENTATION_DEVIATIONS.md`` DEV-6 rather than left as a comment nobody reads.
    """
    paths = {v.path for stage in spec.stages for v in stage.value_sources()}
    # A model-family choice is a bound parameter too (ADR-004 enumerates ModelVersionRefs as an
    # EpistemicSet), so leaving it out would answer "which parameters does this run depend on"
    # while omitting the one that decides which physics ran.
    paths.update(p for stage in spec.stages for p in stage.selection_paths())
    return frozenset(paths)


def paths_reaching_stage(spec: RunSpec, stage_id: str) -> frozenset[str]:
    """The paths that can influence ``stage_id``'s output: its own, plus every upstream stage's.

    This is the narrowest dependency set ``verify`` is *able* to compute, and using it rather
    than :func:`parameter_paths` is what stops a taint from being wider than it has to be. A
    metric over ``geometry.range`` depends on the geometry stage alone; crediting it with the
    link chain's whole parameter set as well would be true and useless.

    Traversal is transitive through ``ChannelSource``: if the link stage reads
    ``geometry.range``, geometry's literals reach it. Stage order is total (ADR-018 rule 3), so
    the walk terminates without a cycle check.

    **This is an upper bound on dependence, not dependence.** It is a structural answer -- every
    path that *could* flow into the stage -- because the precise one is a physical question.
    ADR-003 makes a provider's config opaque and promises FarSight never reads it physically, and
    ADR-007 decision 7 says ``verify`` "never executes physics", so no verifier can know that a
    parameter reached a stage and changed nothing. Two consequences worth stating plainly rather
    than discovering later:

      * On a run like the DSOC flagship, whose engine stage consumes nearly the whole flight-side
        parameter set, this set is nearly everything. A single collapse anywhere can therefore
        taint nearly every verdict.
      * That is a real risk of the advisory-flag failure ADR-004's Option 2 was rejected for --
        reached by a different road. If ``contains_epistemic_collapse`` is true everywhere,
        reviewers stop reading it.

    The instrument that answers the narrow question is sensitivity, not lineage: ADR-004's outer
    scan already perturbs a coordinate across its declared range and observes whether the verdict
    moves. Lineage says *what could have mattered*; sensitivity says *what did*. Conflating them
    would make this function claim a precision it cannot have.
    """
    by_id = {s.stage_id: s for s in spec.stages}
    if stage_id not in by_id:
        raise KeyError(f"run has no stage {stage_id!r}; stages are {sorted(by_id)}")

    reached: set[str] = set()
    pending = [stage_id]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        stage = by_id[current]
        reached.update(v.path for v in stage.value_sources())
        reached.update(stage.selection_paths())
        for source in stage.bindings.values():
            if isinstance(source, ChannelSource):
                pending.append(source.from_stage)
    return frozenset(reached)


def model_versions(spec: RunSpec) -> frozenset[str]:
    """Every ``ModelVersion`` digest this run runs, across all stages.

    The Model to Run edge read in the direction an auditor asks it: *which models produced this
    number*. ADR-026 decision 6 requires a package to ship every referenced ``ModelVersion``
    object, and this is what enumerates them for a run.
    """
    return frozenset(m.model_version_ref for stage in spec.stages for m in stage.models)


def value_sources_for_path(spec: RunSpec, path: str) -> list[ValueSource]:
    """Every value this run bound at ``path``, in stage then binding-key order.

    More than one is legitimate only for a per-group draw. Returning the list rather than a
    single value keeps that case expressible instead of forcing a caller to guess.
    """
    return [v for stage in spec.stages for v in stage.value_sources() if v.path == path]
