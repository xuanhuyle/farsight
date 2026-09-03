"""The closed arithmetic expression grammar for derived parameter values.

ADR-029. Seven node kinds, two of them leaves. No functions, no powers, no transcendentals, no
conditionals. **An eighth kind is a decision, not a feature** -- the same ceiling discipline
ADR-010 puts on its predicate grammar and ADR-017 on its node kinds. The moment this grammar
grows a ``sqrt`` it has started to become a modelling language, and modelling belongs in engines.

This is a *separate* AST from ADR-010's ``PredicateAST``, deliberately. Predicates are booleans
over channels at run time; derivations are quantities over parameters at freeze time. Fusing
them would put arithmetic into the fault-trigger surface, which ADR-010 closed on purpose.

**Why this is its own module.** ADR-029 sketches these classes under ``schemas/design.py``. They
live here because ``design.py`` imports ``belief.py`` (an ``UncertaintySpec`` holds ``Belief``
objects) and ``belief.py`` needs the expression type (a derived value materializes as a
``Deterministic`` carrying its derivation), so the sketch's placement is an import cycle. A leaf
module both can import is the smallest resolution. Recorded as DEV-5.

**What this module deliberately does not do.** It performs no arithmetic and no dimensional
analysis. ``schemas`` is a leaf package that may not import a unit library (the
``no_units_lib_in_core`` import contract), and ADR-029 puts evaluation at freeze in SI float64
through ``farsight.units.to_si``. So this module can say that an expression is *well-formed*,
and cannot say that it is *dimensionally coherent* or what it evaluates to. Those checks belong
to the freeze validator, and pretending otherwise here would be the more dangerous error --
a caller could believe an expression had been dimensionally checked when it had not.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import Field, field_validator, model_validator

from farsight.schemas.common import (
    FrozenModel,
    Quantity,
    validate_path,
)

__all__ = [
    "ParamLeaf",
    "ConstLeaf",
    "Add",
    "Sub",
    "Mul",
    "Div",
    "Neg",
    "ArithExpr",
    "Derivation",
    "param_paths",
    "expr_size",
    "MAX_EXPR_NODES",
    "MAX_EXPR_DEPTH",
]

# Ceilings on expression size. ADR-029 caps the node *kinds* at seven and says an eighth is a
# decision; it says nothing about how many nodes one expression may have, and unbounded is the
# wrong default in a document that gets canonicalized by a recursive writer. Without a cap, a
# deep enough expression reaches `canonical._write` and raises RecursionError -- a crash where
# the system's whole discipline is to refuse with a reason. These numbers are generous by two
# orders of magnitude against the motivating case (`spacing / speed` is three nodes); they exist
# to convert a crash into a refusal, not to constrain honest authoring.
MAX_EXPR_NODES = 64
MAX_EXPR_DEPTH = 12


class ParamLeaf(FrozenModel):
    """A reference to another bound parameter, by topology path."""

    kind: Literal["param"] = "param"
    path: str

    @field_validator("path")
    @classmethod
    def _check_path(cls, v: str) -> str:
        return validate_path(v)


class ConstLeaf(FrozenModel):
    """A literal appearing in a derivation.

    It is a full ``Quantity``, not a bare number, because a unitless constant in a physical
    expression is how a unit error enters a document that everything downstream trusts. A
    genuinely dimensionless factor says so with ``unit: "1"`` (ADR-008).
    """

    kind: Literal["const"] = "const"
    value: Quantity


class Add(FrozenModel):
    kind: Literal["add"] = "add"
    lhs: "ArithExpr"
    rhs: "ArithExpr"


class Sub(FrozenModel):
    kind: Literal["sub"] = "sub"
    lhs: "ArithExpr"
    rhs: "ArithExpr"


class Mul(FrozenModel):
    kind: Literal["mul"] = "mul"
    lhs: "ArithExpr"
    rhs: "ArithExpr"


class Div(FrozenModel):
    kind: Literal["div"] = "div"
    lhs: "ArithExpr"
    rhs: "ArithExpr"


class Neg(FrozenModel):
    kind: Literal["neg"] = "neg"
    operand: "ArithExpr"


ArithExpr = Annotated[
    Union[ParamLeaf, ConstLeaf, Add, Sub, Mul, Div, Neg],
    Field(discriminator="kind"),
]

for _node in (Add, Sub, Mul, Div, Neg):
    _node.model_rebuild()


def _children(node: Any) -> tuple[Any, ...]:
    if isinstance(node, Neg):
        return (node.operand,)
    if isinstance(node, (Add, Sub, Mul, Div)):
        return (node.lhs, node.rhs)
    return ()


def param_paths(expr: Any) -> frozenset[str]:
    """Every topology path this expression reads.

    The lineage edge G1 exists to preserve: a derived parameter's value is one number bound at
    one path, and this is the only way back to the parameters it was computed from. Returns a
    set, so a path read twice in one expression counts once -- the question downstream is
    "does this depend on that parameter", not "how many times".
    """
    found: set[str] = set()
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, ParamLeaf):
            found.add(node.path)
        stack.extend(_children(node))
    return frozenset(found)


def expr_size(expr: Any) -> tuple[int, int]:
    """``(node_count, depth)``. Iterative, so measuring an over-deep tree cannot itself recurse."""
    count = 0
    depth = 0
    stack = [(expr, 1)]
    while stack:
        node, d = stack.pop()
        count += 1
        depth = max(depth, d)
        for child in _children(node):
            stack.append((child, d + 1))
    return count, depth


class Derivation(FrozenModel):
    """How a derived parameter's value was computed, carried by the value itself.

    ADR-029 decision 4: the freeze *evaluates* a ``DerivedBinding`` and materializes an ordinary
    ``Deterministic`` belief at the target path, "carrying the hashed expression as its
    derivation record". This is that record. A reader of a frozen design sees a number **and**
    the derivation that produced it, never a formula still waiting to be evaluated.

    Without it the derived half of the parameter space is a dead end for lineage: the value
    reaches a run through ``ValueSource.path`` like any other deterministic value, and there the
    trail stops, because nothing says the number was computed from three other parameters. That
    is finding G1 one hop further in -- and it is the hop that decides whether "which parameters
    does this result depend on" is answered transitively or only to depth one.

    ``inputs`` is redundant with ``expression`` and is materialized anyway, following
    ``draw_order`` (ADR-017) and grouped expansion (ADR-027): **the hashed document contains what
    actually happened, and the rule that produced it, and the two are checked against each
    other.** Here the check is stronger than either of those, because both halves are inside one
    object -- the validator below is total, so this particular redundancy cannot rot even in
    principle.
    """

    expression: "ArithExpr"
    inputs: list[str]
    note: str

    @model_validator(mode="after")
    def _check(self) -> "Derivation":
        count, depth = expr_size(self.expression)
        if count > MAX_EXPR_NODES:
            raise ValueError(
                f"derivation expression has {count} nodes, over the {MAX_EXPR_NODES} ceiling. "
                f"A derivation states a relationship between a few declared parameters; an "
                f"expression this large is a model, and models belong in engines (ADR-029)."
            )
        if depth > MAX_EXPR_DEPTH:
            raise ValueError(
                f"derivation expression is {depth} levels deep, over the {MAX_EXPR_DEPTH} "
                f"ceiling. The limit exists so that an over-deep expression is refused here "
                f"rather than raising RecursionError inside the canonicalizer."
            )

        recomputed = sorted(param_paths(self.expression))
        if self.inputs != recomputed:
            raise ValueError(
                f"derivation inputs {self.inputs} disagree with the paths its expression "
                f"actually reads, {recomputed}. `inputs` is materialized so that a lineage "
                f"query need not walk the AST; it is checked so that the shortcut can never "
                f"disagree with the authority."
            )
        if not self.note.strip():
            raise ValueError(
                "a derivation states in one sentence why this quantity is derived rather than "
                "chosen (ADR-029). A reader looking at a number and a formula still needs to "
                "know why the author thought the formula was the right one."
            )
        return self

    def depends_on(self) -> frozenset[str]:
        """The parameter paths this value was computed from. One hop, not transitive.

        Transitive closure needs the whole design, because an input may itself be derived, so it
        lives with the freeze validator rather than here -- a belief cannot see its siblings.
        """
        return frozenset(self.inputs)


Derivation.model_rebuild()
