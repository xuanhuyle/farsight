"""Run composition and path-preserving lowering (ADR-018, finding G1).

Two of ADR-018's named enforcement items live here: `test_run_composition_schema` asserts the
composition rules, and `test_stage_binding_closure` asserts that `StageInput` has exactly three
members and that none can name a run. The second is an *absence* test -- it exists so the
absence cannot be edited away, in the same style as ADR-006's golden attestation.

The G1 tests assert a property the previous shape could not have: that from a `RunSpec` alone,
every value can be traced back to the parameter it came from. The check that matters is the last
one -- the collapse-taint intersection ADR-004 requires `verify` to recompute -- because that is
the query the missing edge made unanswerable.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from farsight.hashing.canonical import canonicalize, content_hash
from farsight.schemas.belief import CollapseScope
from farsight.schemas.common import Quantity
from farsight.schemas.execution import (
    STAGE_INPUT_MEMBERS,
    ArtifactSource,
    ChannelSource,
    GridRef,
    RunSpec,
    SpecCompositionError,
    StageModel,
    StageSpec,
    ValueSource,
    model_versions,
    parameter_paths,
    paths_reaching_stage,
    value_sources_for_path,
)

HEX = "a" * 64
JITTER = "flight.laser.pointing_jitter_sigma"
ATMOS = "ground.palomar.atmosphere"
APERTURE = "ground.palomar.aperture"


def vs(path: str, mag: str = "1", origin: str = "deterministic", **kw) -> ValueSource:
    return ValueSource(value=Quantity(magnitude=mag, unit="m"), path=path, origin=origin, **kw)


def stage(stage_id, kind="geometry", bindings=None, emits=None, grid="pass_grid",
          provider="spice", models=None):
    return StageSpec(
        stage_id=stage_id, kind=kind, provider_id=provider, config_dialect=provider,
        config_ref=HEX, grid=GridRef(grid_id=grid), bindings=bindings or {}, emits=emits or [],
        models=models or [],
    )


def dsoc_run() -> RunSpec:
    """The flagship shape: SPICE geometry then the link chain, in one run."""
    geometry = stage(
        "geometry", emits=["in_view", "range"],
        bindings={"target": vs("spacecraft.psyche.target", "1")},
    )
    link = stage(
        "link", kind="engine", provider="linkchain", emits=["margin"],
        bindings={
            "range_m": ChannelSource(from_stage="geometry", channel="range"),
            "jitter_rad": vs(JITTER, "0.16", "aleatory_draw"),
            "atmos_db": vs(ATMOS, "0.55", "collapse"),
            "aperture_m": vs(APERTURE, "5.1", "deterministic"),
        },
    )
    return RunSpec(experiment_hash=HEX, run_index=4242, stages=[geometry, link])


# --------------------------------------------------------------------------------------
# G1: a value cannot exist in a run without saying where it came from
# --------------------------------------------------------------------------------------


def test_a_value_must_name_the_parameter_it_came_from():
    """The G1 repair. A literal with no declared origin path is precisely the silently-fitted
    constant ADR-001 rule 6 forbids, so the type refuses to express one."""
    with pytest.raises(ValidationError):
        ValueSource(value=Quantity(magnitude="1", unit="m"), origin="deterministic")
    with pytest.raises(ValidationError):
        ValueSource(value=Quantity(magnitude="1", unit="m"), path=JITTER)


def test_every_bound_value_traces_to_a_path():
    run = dsoc_run()
    assert parameter_paths(run) == {JITTER, ATMOS, APERTURE, "spacecraft.psyche.target"}


def test_lineage_survives_the_thing_that_made_a_value_join_impossible():
    """ADR-001 makes "0.220" != "0.22" so that a value is never a key. Two parameters sharing a
    magnitude must still be distinguishable, which is exactly what a decimal-string join could
    not do."""
    run = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage(
        "s", bindings={"a": vs(JITTER, "0.22"), "b": vs(APERTURE, "0.22")},
    )])
    assert parameter_paths(run) == {JITTER, APERTURE}
    assert value_sources_for_path(run, JITTER)[0].value.magnitude == "0.22"
    assert len(value_sources_for_path(run, APERTURE)) == 1


def test_an_unknown_with_no_declared_sweep_has_no_origin_to_name():
    """AT-6: a RunSpec assigning a point value to a flagged Unknown must be rejected by schema.
    `ValueOrigin` has a member for a point from a DECLARED sweep and none for anything else, so
    the refusal is structural rather than a validator somebody can relax."""
    vs(JITTER, "0.5", "unknown_sweep_point")  # legitimate: a bracket we declared and are scanning
    for absent in ("unknown", "assumed", "default", "literal", ""):
        with pytest.raises(ValidationError):
            vs(JITTER, "0.5", absent)


def test_origins_are_the_routes_the_records_sanction():
    for origin in ("deterministic", "derived", "aleatory_draw", "epistemic_point",
                   "unknown_sweep_point", "unknown_bounded", "collapse"):
        assert vs(JITTER, "1", origin).origin == origin


# --------------------------------------------------------------------------------------
# The per-group case: the one time several values share a path
# --------------------------------------------------------------------------------------


def test_a_per_group_draw_keeps_one_path_and_distinct_members():
    """ADR-027: a per-group sampling scope draws len(members) values from ONE binding at ONE
    topology path. Without a member qualifier those values are indistinguishable in the run."""
    run = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage("s", bindings={
        "j1": vs(JITTER, "0.16", "aleatory_draw", group_member="pass_one"),
        "j2": vs(JITTER, "0.19", "aleatory_draw", group_member="pass_two"),
    })])
    values = value_sources_for_path(run, JITTER)
    assert [v.group_member for v in values] == ["pass_one", "pass_two"]
    assert parameter_paths(run) == {JITTER}  # one parameter, however many draws


def test_two_unqualified_values_at_one_path_is_the_run_contradicting_itself():
    with pytest.raises(SpecCompositionError, match="without distinct group members"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[stage("s", bindings={
            "a": vs(JITTER, "0.16"), "b": vs(JITTER, "0.19"),
        })])
    with pytest.raises(SpecCompositionError, match="without distinct group members"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[stage("s", bindings={
            "a": vs(JITTER, "0.16", "aleatory_draw", group_member="pass_one"),
            "b": vs(JITTER, "0.19", "aleatory_draw", group_member="pass_one"),
        })])


def test_a_group_member_is_only_meaningful_for_a_per_group_draw():
    """A GroupedBinding expands at freeze into per-member PATHS, so its values are already told
    apart by path; a member qualifier there would be a second, disagreeing answer."""
    for origin in ("deterministic", "derived", "epistemic_point", "collapse"):
        with pytest.raises(ValidationError, match="carries a group_member"):
            vs(JITTER, "1", origin, group_member="pass_one")


def test_a_member_name_is_a_name_and_never_a_position():
    """Numeric member names are legal -- ADR-017 permits numeric segments and says a numeric
    suffix is characters only. What is asserted is that nothing here reads it as an index:
    byte-wise ordering puts "10" before "3", which is why position must never be inferred."""
    vs(JITTER, "1", "aleatory_draw", group_member="3")
    assert sorted(["3", "10"]) == ["10", "3"]
    with pytest.raises(ValidationError, match="segment grammar"):
        vs(JITTER, "1", "aleatory_draw", group_member="Pass One")


# --------------------------------------------------------------------------------------
# The query the missing edge made unanswerable (ADR-004 line 160)
# --------------------------------------------------------------------------------------


def test_collapse_taint_can_now_be_recomputed_from_the_run():
    """This is the whole point of G1. `verify` must RECOMPUTE taint by intersecting a collapse's
    scope with the paths a result depends on, and treat a stored `false` the recomputation
    contradicts as an integrity failure. Before the path survived lowering there was nothing to
    intersect for the deterministic half."""
    run = dsoc_run()
    touching = CollapseScope(experiment_hash=HEX, parameter_paths=[ATMOS])
    assert touching.covers(parameter_paths(run)) == {ATMOS}

    untouching = CollapseScope(experiment_hash=HEX, parameter_paths=["ground.goldstone.gain"])
    assert untouching.covers(parameter_paths(run)) == frozenset()

    # And the failure a recomputation must be able to name: which parameter caused the taint.
    assert sorted(touching.covers(parameter_paths(run))) == [ATMOS]


def test_a_channel_binding_needs_no_path_because_its_lineage_is_the_stage():
    """A ChannelSource already carries a reconstructible edge -- from_stage plus channel -- and
    the producing stage's own literals are in the union, so no traversal is needed."""
    run = dsoc_run()
    assert "spacecraft.psyche.target" in parameter_paths(run)  # the geometry stage's own literal


# --------------------------------------------------------------------------------------
# ADR-018 Enforcement item 2: the closed derivation, enforced by absence
# --------------------------------------------------------------------------------------


def test_stage_binding_closure():
    """`StageInput` has exactly three members and none can name a run, a run index or an output
    hash. The closed (experiment_hash, run_index) -> spec_hash derivation rests on this, and
    this test is what keeps the absence from being edited away."""
    assert len(STAGE_INPUT_MEMBERS) == 3
    assert {m.__name__ for m in STAGE_INPUT_MEMBERS} == {
        "ChannelSource", "ArtifactSource", "ValueSource"
    }
    forbidden = {"run", "run_index", "run_ref", "output_hash", "from_run", "run_output"}
    for member in STAGE_INPUT_MEMBERS:
        assert not (set(member.model_fields) & forbidden), (
            f"{member.__name__} names a run or an output hash; that turns the pure derivation "
            f"into a two-phase plan-execute-plan protocol (ADR-018)"
        )
    # ChannelSource names a STAGE of the same run, which is not a run reference.
    assert "from_stage" in ChannelSource.model_fields
    assert "artifact_ref" in ArtifactSource.model_fields


# --------------------------------------------------------------------------------------
# ADR-018 Enforcement item 1: the six composition rules
# --------------------------------------------------------------------------------------


def test_a_run_has_at_least_one_stage():
    with pytest.raises(SpecCompositionError, match="at least one stage"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[])


def test_stage_ids_are_unique_and_their_nodes_do_not_overlap():
    with pytest.raises(SpecCompositionError, match="unique"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[stage("geo"), stage("geo")])
    with pytest.raises(SpecCompositionError, match="overlap"):
        RunSpec(experiment_hash=HEX, run_index=0,
                stages=[stage("ground"), stage("ground.palomar")])
    # A shared prefix that is not an ancestor is fine: "link" does not contain "link_margin".
    RunSpec(experiment_hash=HEX, run_index=0, stages=[stage("link"), stage("link_margin")])


def test_at_most_one_engine_stage_and_it_is_last():
    with pytest.raises(SpecCompositionError, match="at most one engine stage"):
        RunSpec(experiment_hash=HEX, run_index=0,
                stages=[stage("a", kind="engine"), stage("b", kind="engine")])
    with pytest.raises(SpecCompositionError, match="must be last"):
        RunSpec(experiment_hash=HEX, run_index=0,
                stages=[stage("a", kind="engine"), stage("b")])


def test_channel_bindings_name_a_strictly_earlier_stage_and_a_declared_channel():
    with pytest.raises(SpecCompositionError, match="strictly earlier"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[
            stage("a", bindings={"x": ChannelSource(from_stage="b", channel="r")}),
            stage("b", emits=["r"]),
        ])
    with pytest.raises(SpecCompositionError, match="strictly earlier"):  # self-reference
        RunSpec(experiment_hash=HEX, run_index=0, stages=[
            stage("a", bindings={"x": ChannelSource(from_stage="a", channel="r")}, emits=["r"]),
        ])
    with pytest.raises(SpecCompositionError, match="does not declare it"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[
            stage("a", emits=["q"]),
            stage("b", bindings={"x": ChannelSource(from_stage="a", channel="r")}),
        ])


def test_a_channel_may_only_be_consumed_on_its_own_grid():
    """Elementwise consumption of a channel computed on a different time base is the
    silent-killer class ADR-018 rule 4 exists to close."""
    with pytest.raises(SpecCompositionError, match="grid"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[
            stage("a", emits=["r"], grid="fine"),
            stage("b", bindings={"x": ChannelSource(from_stage="a", channel="r")}, grid="coarse"),
        ])


def test_emitted_channel_names_are_sorted_and_unique():
    with pytest.raises(ValidationError, match="sorted"):
        stage("a", emits=["z", "a"])
    with pytest.raises(ValidationError, match="twice"):
        stage("a", emits=["r", "r"])


def test_the_engine_is_computed_never_stored():
    """ADR-018: computing it keeps "a GeometryProvider is not an Engine" literally true -- no
    code path can call a geometry provider an engine. None is a legitimate answer."""
    assert dsoc_run().engine_id() == "linkchain"
    geometry_only = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage("geometry")])
    assert geometry_only.engine_id() is None


def test_unenforceable_rules_are_declared_rather_than_silently_skipped():
    """Two of the six rules need types that do not exist yet. A deferred check that says nothing
    is indistinguishable from a check that passed, which is the failure C4 was about."""
    rules = dsoc_run().unenforced_rules()
    assert len(rules) == 5
    assert any("SystemTopology" in r for r in rules)
    assert any("supports_stepping" in r for r in rules)
    assert any("binding completeness" in r for r in rules)
    assert any("origin agreement" in r for r in rules)
    assert any("model_binding_consistent" in r for r in rules)


# --------------------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------------------


def test_a_runspec_canonicalizes_without_a_float_and_carries_its_schema_version():
    run = dsoc_run()
    out = canonicalize(run.model_dump(mode="json"))
    assert '"schema_version":1' in out
    assert JITTER in out
    assert content_hash(run.model_dump(mode="json"))


def test_the_origin_is_part_of_identity():
    """Two runs binding the same number at the same path by different routes are different
    documents. If they hashed alike, a collapse-derived value and a measured one would be the
    same run, and the taint would depend on which document you happened to read."""
    a = RunSpec(experiment_hash=HEX, run_index=0,
                stages=[stage("s", bindings={"x": vs(JITTER, "0.16", "deterministic")})])
    b = RunSpec(experiment_hash=HEX, run_index=0,
                stages=[stage("s", bindings={"x": vs(JITTER, "0.16", "collapse")})])
    assert content_hash(a.model_dump(mode="json")) != content_hash(b.model_dump(mode="json"))


def test_run_index_is_a_position_in_an_enumeration():
    with pytest.raises(ValidationError, match="never negative"):
        RunSpec(experiment_hash=HEX, run_index=-1, stages=[stage("a")])


# --------------------------------------------------------------------------------------
# Dependency granularity: the narrowest set verify can compute, and its honest limits
# --------------------------------------------------------------------------------------


def test_a_metric_over_an_early_stage_is_not_charged_with_later_stages():
    """The whole-run union credits a geometry metric with the link chain's parameters too, which
    is true and useless. Stage-granular attribution is the narrowest set `verify` can compute."""
    run = dsoc_run()
    assert paths_reaching_stage(run, "geometry") == {"spacecraft.psyche.target"}
    assert ATMOS not in paths_reaching_stage(run, "geometry")

    # A collapse on an atmosphere term must NOT taint a purely geometric verdict.
    collapse = CollapseScope(experiment_hash=HEX, parameter_paths=[ATMOS])
    assert collapse.covers(paths_reaching_stage(run, "geometry")) == frozenset()
    assert collapse.covers(paths_reaching_stage(run, "link")) == {ATMOS}


def test_dependence_is_transitive_through_channel_bindings():
    """The link stage reads geometry.range, so geometry's literals reach it. Stage order is
    total, so the walk terminates without a cycle check."""
    run = dsoc_run()
    assert "spacecraft.psyche.target" in paths_reaching_stage(run, "link")
    assert paths_reaching_stage(run, "link") == parameter_paths(run)


def test_a_stage_that_reads_nothing_upstream_stays_narrow():
    """Two independent stages: the second must not inherit the first's parameters merely by
    being later in the list."""
    run = RunSpec(experiment_hash=HEX, run_index=0, stages=[
        stage("first", bindings={"a": vs(JITTER, "1")}, emits=["out"]),
        stage("second", bindings={"b": vs(APERTURE, "2")}),
    ])
    assert paths_reaching_stage(run, "second") == {APERTURE}
    assert parameter_paths(run) == {JITTER, APERTURE}


def test_asking_about_a_stage_that_is_not_in_the_run_is_an_error():
    with pytest.raises(KeyError, match="no stage"):
        paths_reaching_stage(dsoc_run(), "nonexistent")


def test_an_unknown_discharged_by_a_bounding_assumption_can_be_lowered():
    """ADR-004 gives an Unknown two legal resolutions at freeze -- a declared sweep OR a named
    bounding assumption -- and `Unknown.freeze_ready` returns True for either. An enum covering
    only the first makes a legal frozen design impossible to lower, which is a worse failure
    than the one the omission was guarding against.
    """
    import datetime as dt

    from farsight.schemas.belief import Pedigree, Unknown

    unknown = Unknown(
        what_is_missing="No measurement of the receiver optical train throughput exists.",
        bounding_assumption_ref="b" * 64,
        pedigree=Pedigree(level="speculative", assessor="jh", assessed_on=dt.date(2026, 9, 3)),
    )
    assert unknown.freeze_ready() and unknown.sweep_declaration is None
    assert vs(APERTURE, "0.45", "unknown_bounded").origin == "unknown_bounded"


def test_the_module_does_not_claim_lineage_it_cannot_deliver():
    """Two routes carry numbers into a run without attribution: a DataArtifact's contents, and
    the opaque per-dialect config document ADR-003 forbids FarSight from reading. Neither is
    closed here, and the deferred check that bounds them is named rather than implied."""
    run = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage(
        "s", bindings={"table": ArtifactSource(artifact_ref="c" * 64)},
    )])
    # An artifact-bound stage contributes no paths, and the query says so rather than guessing.
    assert parameter_paths(run) == frozenset()
    assert any("binding completeness" in r for r in run.unenforced_rules())


# --------------------------------------------------------------------------------------
# D1: the Model -> Run edge (ADR-026 quantified over a StageSpec field ADR-018 never defined)
# --------------------------------------------------------------------------------------

MODEL_A = "1" * 64
MODEL_B = "2" * 64
PROP_MODEL_PATH = "flight.link.propagation_model"


def test_a_stage_names_the_model_versions_it_runs():
    """ADR-026's model_binding_consistent is written against "every StageSpec naming that
    model", and ADR-026's own Related-ADRs line says "a stage names the model it runs" -- but
    ADR-018's StageSpec had eight fields and none of them named a ModelVersion. The validator
    quantified over something unwritable."""
    run = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage(
        "link", kind="engine", provider="linkchain",
        models=[StageModel(model_version_ref=MODEL_A, path=None),
                StageModel(model_version_ref=MODEL_B, path=None)],
    )])
    assert model_versions(run) == {MODEL_A, MODEL_B}


def test_a_stage_must_state_its_models_even_when_there_are_none():
    """Required with no default. An empty list is an assertion -- this stage runs no separately
    identified model version, which is true of a SPICE geometry stage -- and a `= None` default
    would make that indistinguishable from a field nobody reached."""
    with pytest.raises(ValidationError):
        StageSpec(stage_id="s", kind="geometry", provider_id="spice", config_dialect="spice",
                  config_ref=HEX, grid=GridRef(grid_id="g"), bindings={}, emits=[])
    assert stage("s").models == []
    assert model_versions(RunSpec(experiment_hash=HEX, run_index=0,
                                  stages=[stage("s")])) == frozenset()


def test_a_model_family_coordinate_keeps_its_path():
    """The reason this is not just a bare digest. A model family is enumerated as
    EpistemicSet.members: list[ModelVersionRef] (ADR-004), so which model runs can be an
    epistemic coordinate. It cannot lower through ValueSource, whose value is a Quantity and
    cannot hold a digest -- so without a path here it would be exactly the unattributed value
    G1 was about, for a different value type."""
    run = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage(
        "link", kind="engine", provider="linkchain",
        models=[StageModel(model_version_ref=MODEL_A, path=PROP_MODEL_PATH)],
    )])
    assert PROP_MODEL_PATH in parameter_paths(run)
    assert PROP_MODEL_PATH in paths_reaching_stage(run, "link")

    # And the question that motivates all of it: does this verdict depend on that choice?
    scope = CollapseScope(experiment_hash=HEX, parameter_paths=[PROP_MODEL_PATH])
    assert scope.covers(parameter_paths(run)) == {PROP_MODEL_PATH}


def test_a_fixed_model_contributes_no_path():
    """None means the design fixed this model, not that a parameter chose it. That is a
    different claim and must not appear as a parameter dependency."""
    run = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage(
        "link", kind="engine", models=[StageModel(model_version_ref=MODEL_A, path=None)],
    )])
    assert parameter_paths(run) == frozenset()
    assert model_versions(run) == {MODEL_A}


def test_a_path_cannot_be_both_a_value_and_a_model_selection():
    """ADR-017 decision 4: a path may be bound exactly once by exactly one route, and two routes
    claiming one path is a freeze failure naming the path. Model selection is the second
    lowering site, so the rule has to span both."""
    with pytest.raises(SpecCompositionError, match="both as a value and as a model selection"):
        RunSpec(experiment_hash=HEX, run_index=0, stages=[
            stage("geo", bindings={"x": vs(PROP_MODEL_PATH, "1")}),
            stage("link", kind="engine",
                  models=[StageModel(model_version_ref=MODEL_A, path=PROP_MODEL_PATH)]),
        ])


def test_model_lists_are_sorted_and_a_model_is_named_once():
    with pytest.raises(ValidationError, match="same ModelVersion twice"):
        stage("s", models=[StageModel(model_version_ref=MODEL_A, path=None),
                           StageModel(model_version_ref=MODEL_A, path=None)])
    with pytest.raises(ValidationError, match="sorted"):
        stage("s", models=[StageModel(model_version_ref=MODEL_B, path=None),
                           StageModel(model_version_ref=MODEL_A, path=None)])


def test_a_model_selection_path_obeys_the_topology_grammar():
    with pytest.raises(ValidationError, match="ADR-017 grammar"):
        StageModel(model_version_ref=MODEL_A, path="Flight.Link")


def test_the_model_edge_is_part_of_run_identity():
    """Two runs differing only in which model version ran must be different documents, or
    "which model produced this number" has two answers with one hash."""
    a = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage(
        "link", kind="engine", models=[StageModel(model_version_ref=MODEL_A, path=None)])])
    b = RunSpec(experiment_hash=HEX, run_index=0, stages=[stage(
        "link", kind="engine", models=[StageModel(model_version_ref=MODEL_B, path=None)])])
    assert content_hash(a.model_dump(mode="json")) != content_hash(b.model_dump(mode="json"))
