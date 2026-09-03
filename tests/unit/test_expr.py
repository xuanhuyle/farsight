"""The derivation record: how a computed value keeps the edge to what computed it (ADR-029).

The property under test is a lineage property, not an arithmetic one. This module performs no
arithmetic and no dimensional analysis -- `schemas` may not import a unit library -- so what is
asserted here is that a derived value cannot exist without a truthful, machine-readable
statement of which parameters it was computed from.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from farsight.hashing.canonical import canonicalize, content_hash
from farsight.schemas.belief import Deterministic, Pedigree
from farsight.schemas.common import Quantity
from farsight.schemas.expr import (
    MAX_EXPR_DEPTH,
    MAX_EXPR_NODES,
    Add,
    ConstLeaf,
    Derivation,
    Div,
    Mul,
    Neg,
    ParamLeaf,
    Sub,
    expr_size,
    param_paths,
)

HEX = "a" * 64
SPACING = "corridor.probe.spacing"
SPEED = "corridor.probe.cruise_speed"
NOTE = (
    "Launch interval follows from probe spacing and cruise speed; stating all three "
    "independently would let the design contradict itself."
)


def q(mag: str, unit: str = "m") -> Quantity:
    return Quantity(magnitude=mag, unit=unit)


def interval_expr():
    return Div(lhs=ParamLeaf(path=SPACING), rhs=ParamLeaf(path=SPEED))


def derivation(**over) -> Derivation:
    expr = over.pop("expression", None) or interval_expr()
    base = dict(expression=expr, inputs=sorted(param_paths(expr)), note=NOTE)
    return Derivation(**{**base, **over})


def ped(level: str = "derived_analysis") -> Pedigree:
    sources = [] if level == "speculative" else [HEX]
    return Pedigree(level=level, sources=sources, assessor="jh", assessed_on=dt.date(2026, 9, 3))


# --------------------------------------------------------------------------------------
# The lineage edge itself
# --------------------------------------------------------------------------------------


def test_derivation_reports_the_paths_it_reads():
    d = derivation()
    assert d.depends_on() == {SPACING, SPEED}
    assert d.inputs == sorted([SPACING, SPEED])  # byte-wise, so equal scopes hash alike


def test_a_path_read_twice_counts_once():
    """The downstream question is "does this depend on that parameter", never "how often"."""
    expr = Sub(lhs=ParamLeaf(path=SPACING), rhs=ParamLeaf(path=SPACING))
    assert param_paths(expr) == {SPACING}
    assert derivation(expression=expr).inputs == [SPACING]


def test_nested_expressions_are_walked_to_the_leaves():
    expr = Add(
        lhs=Mul(lhs=ParamLeaf(path=SPACING), rhs=ConstLeaf(value=q("2", "1"))),
        rhs=Neg(operand=Div(lhs=ParamLeaf(path=SPEED), rhs=ParamLeaf(path="ground.dsn.rate"))),
    )
    assert param_paths(expr) == {SPACING, SPEED, "ground.dsn.rate"}
    assert expr_size(expr) == (8, 4)


def test_a_derivation_over_constants_alone_has_no_inputs_and_says_so():
    """Legal, and worth a test: an expression of pure constants depends on no parameter, so an
    empty `inputs` here is a computed fact rather than an unpopulated field."""
    expr = Mul(lhs=ConstLeaf(value=q("2", "1")), rhs=ConstLeaf(value=q("3", "m")))
    assert derivation(expression=expr).inputs == []


def test_materialized_inputs_cannot_disagree_with_the_expression():
    """`inputs` is a shortcut so a lineage query need not walk the AST. The check is what stops
    the shortcut from becoming a second, wrong source of truth -- the draw_order pattern, and
    here it is total, since both halves live inside one object."""
    expr = interval_expr()
    with pytest.raises(ValidationError, match="disagree with the paths"):
        Derivation(expression=expr, inputs=[SPACING], note=NOTE)          # too few
    with pytest.raises(ValidationError, match="disagree with the paths"):
        Derivation(expression=expr, inputs=[SPACING, SPEED, "x.y"], note=NOTE)  # too many
    # Unsorted. SPEED sorts BEFORE SPACING ("cruise_speed" < "spacing"), so the wrong order is
    # the one that reads naturally -- which is exactly why the check is mechanical.
    assert sorted([SPACING, SPEED]) == [SPEED, SPACING]
    with pytest.raises(ValidationError, match="disagree with the paths"):
        Derivation(expression=expr, inputs=[SPACING, SPEED], note=NOTE)


def test_a_derivation_states_why_it_is_derived():
    with pytest.raises(ValidationError, match="why this quantity is derived"):
        derivation(note="   ")


def test_param_leaf_paths_obey_the_topology_grammar():
    with pytest.raises(ValidationError, match="ADR-017 grammar"):
        ParamLeaf(path="Corridor.Probe")


def test_a_constant_carries_a_unit():
    """A bare number in a physical expression is how a unit error enters a trusted document. A
    genuinely dimensionless factor says so with unit "1" (ADR-008)."""
    ConstLeaf(value=q("2", "1"))
    with pytest.raises(ValidationError):
        ConstLeaf(value={"magnitude": "2"})


# --------------------------------------------------------------------------------------
# Ceilings: a refusal, not a crash
# --------------------------------------------------------------------------------------


def test_over_deep_expression_is_refused_before_the_canonicalizer_recurses():
    deep = ConstLeaf(value=q("1"))
    for _ in range(MAX_EXPR_DEPTH + 2):
        deep = Neg(operand=deep)
    with pytest.raises(ValidationError, match="levels deep"):
        Derivation(expression=deep, inputs=[], note=NOTE)


def test_over_large_expression_is_refused_as_a_model_in_disguise():
    wide = ConstLeaf(value=q("1"))
    for _ in range(MAX_EXPR_NODES):
        wide = Add(lhs=wide, rhs=ConstLeaf(value=q("1")))
    with pytest.raises(ValidationError, match="nodes, over the"):
        Derivation(expression=wide, inputs=[], note=NOTE)


def test_expressions_at_the_ceiling_are_accepted():
    """The ceilings convert a crash into a refusal; they must not refuse honest authoring."""
    expr = ConstLeaf(value=q("1"))
    for _ in range(MAX_EXPR_DEPTH - 1):
        expr = Neg(operand=expr)
    assert expr_size(expr)[1] == MAX_EXPR_DEPTH
    derivation(expression=expr)


# --------------------------------------------------------------------------------------
# The belief that carries it
# --------------------------------------------------------------------------------------


def test_a_derived_value_may_not_claim_to_have_been_measured():
    """The wrong combination is easy to write and invisible afterwards: a number carrying a
    formula and a measured_flight pedigree reads as an observation in every register."""
    d = derivation()
    Deterministic(value=q("1.5", "yr"), pedigree=ped("derived_analysis"), derivation=d)
    for level in ("measured_flight", "measured_ground_test", "published_design",
                  "expert_judgment", "speculative"):
        with pytest.raises(ValidationError, match="carries a derivation but its pedigree"):
            Deterministic(value=q("1.5", "yr"), pedigree=ped(level), derivation=d)


def test_derived_analysis_without_an_expression_stays_legal():
    """One-directional on purpose. An engineer who computed a value by hand is doing derived
    analysis; demanding a seven-node AST first would push honest work outside the record."""
    b = Deterministic(value=q("1.5", "yr"), pedigree=ped("derived_analysis"))
    assert b.derivation is None


def test_authored_and_derived_are_different_documents():
    """None means authored, not unknown -- and the two must not hash alike, or a reader cannot
    tell a chosen number from a computed one."""
    authored = Deterministic(value=q("1.5", "yr"), pedigree=ped("derived_analysis"))
    derived = Deterministic(value=q("1.5", "yr"), pedigree=ped("derived_analysis"),
                            derivation=derivation())
    assert content_hash(authored.model_dump(mode="json")) != content_hash(
        derived.model_dump(mode="json")
    )
    # The absence is explicit in the bytes rather than omitted, so "not derived" is a statement
    # a reader can find rather than an inference from a missing key.
    assert '"derivation":null' in canonicalize(authored.model_dump(mode="json"))


def test_a_derived_belief_canonicalizes_without_a_float():
    b = Deterministic(value=q("1.5", "yr"), pedigree=ped("derived_analysis"),
                      derivation=derivation())
    out = canonicalize(b.model_dump(mode="json"))
    assert SPACING in out and SPEED in out
    assert content_hash(b.model_dump(mode="json"))


def test_copying_a_derived_belief_still_validates():
    """FrozenModel.model_copy routes through validation, so the pedigree rule holds on copies
    too -- otherwise a derived value could be relabelled as measured by copy."""
    b = Deterministic(value=q("1.5", "yr"), pedigree=ped("derived_analysis"),
                      derivation=derivation())
    with pytest.raises(ValidationError):
        b.model_copy(update={"pedigree": ped("measured_flight")})
