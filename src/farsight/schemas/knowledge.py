"""Knowledge-plane objects: what we cite, and what we assume.

Finding G2. ``SourceRef`` and ``AssumptionRef`` were already live inside hashed documents --
``Pedigree.sources`` on every belief, ``Unknown.bounding_assumption_ref``, ADR-026's
``ModelVersion.source_refs`` and ``assumption_refs`` -- with no definition of what they point
at. That is verbatim the hazard ADR-026 was commissioned to close for ``ModelVersionRef``: *the
reference is live in a hashed document and its referent is undefined.* Closed for models, left
open for these two. You could traverse **to** a Source digest and not say what a Source is.

Both take ADR-021's ``Referent`` shape rather than ADR-026's two-object split: one
content-addressed object, an authored ``*_id`` name that is a label and never a key, a monotone
``revision``, and ``supersedes`` plus a typed ``revision_reason``. The split exists in ADR-026 so
that a ``ModelVersion`` digest changing does not orphan its history, and the price is a second
object that must carry nothing able to affect a number. For an ``Assumption`` that price buys
nothing and costs something real: ADR-007 requires the assumption register to carry each
assumption "with pedigree", and a parent thin enough to be stable is a parent with no pedigree on
it, so the register would have to reach through the split to say anything at all.

**What this module does not claim: that FarSight can tell whether two citations are the same
paper.** ADR-001 makes identity syntactic and says so in its own Consequences -- deduplication is
"syntactic, not semantic ... and nothing in the system will point this out". Normalizing a
citation into a comparison key is normalizing *value*, which the same record forbids validators
from doing. So the honest maximum, and what is built here, is narrower in a way worth stating
plainly:

  * an author may **declare** that two Source objects are the same work (``supersedes`` with
    ``revision_reason``), which is an ordinary forward pointer a human signs;
  * identifiers are carried **verbatim as printed**, so two transcriptions of one DOI collide as
    strings without anything having normalized them;
  * everything else is a **named residue**. Two spellings of a paper with no registrar-issued
    identifier are two objects, and no check here will notice.

There is deliberately **no freeze-time collision refusal** on identifiers. It was designed, and
then refuted by the flagship's own central source: DSN 810-005 is a numbered *series* whose
modules are separately issued under one designation, so a refusal keyed on the designation alone
rejects a legal document set. ``SourceIdentifier.part`` is what distinguishes the modules, and
:meth:`Source.collision_keys` reports the keys for a validator one layer up to *use* -- it is a
signal to be reported, not a rule enforced where the consequence of a false positive is that a
week-3 author disables the check and takes the whole mechanism with it.

**Deferred, and named rather than implied.** The assumption register's "objects that depend on
it" (ADR-007) is a reverse index, and every edge in FarSight is a forward pointer because a
back-pointer would change the hash of its target. It cannot live on the ``Assumption``: ADR-001
forecloses in-place annotation of frozen objects, and a ``used_by`` field would re-hash the
assumption -- and therefore every belief citing it -- each time a new dependent appeared. Its
only legal home is a materialized row in ``registers/assumptions.json``, recomputed by ``verify``
and refused on disagreement, which is the pattern ``draw_order`` and grouped expansion already
use. That register is ADR-007's document and is not built here; :func:`dependents_of` is the pure
half this module can honestly provide.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Literal

from pydantic import Field, field_validator, model_validator

from farsight.schemas.belief import Pedigree
from farsight.schemas.common import (
    FrozenModel,
    MAX_SEGMENT_CHARS,
    Quantity,
    Ref,
    SEGMENT_RE,
    VersionedDocument,
)

__all__ = [
    "SourceOrigin",
    "EXTERNAL_PUBLICATION_ORIGINS",
    "IdentifierScheme",
    "SourceIdentifier",
    "SourceRevisionReason",
    "Source",
    "AssumptionRevisionReason",
    "AssumptionBound",
    "Assumption",
    "dependents_of",
    "MIN_STATEMENT_CHARS",
    "MIN_CONSEQUENCE_CHARS",
]

# ADR-004 requires every non-speculative pedigree to cite a source, and ADR-021 forbids anything
# FarSight produces from being bound as a Referent. Those two rules pull in opposite directions
# on one type: `Pedigree.sources` legitimately cites our own hand calculation (the `derived_analysis`
# and `expert_judgment` pedigree levels exist for exactly that), while `Referent.source_refs` may
# cite none of it. So a Source has to say which kind it is, or one type cannot serve both fields.
#
# The vocabulary reconciles with ADR-006's golden-attestation `source` enum, which already ships
# `horizons_response`, `cited_paper`, `hand_calc_notebook` and `second_library` -- and which has
# no `farsight_output` member, deliberately.
SourceOrigin = Literal[
    "published_literature",   # a paper, book, thesis or conference proceeding
    "standard_or_handbook",   # DSN 810-005, CCSDS, ISO, a vendor handbook
    "agency_technical_report",  # a JPL/NASA/ESA technical report or memorandum
    "public_dataset",         # a published dataset or service response (Horizons, SPICE kernels)
    "private_communication",  # correspondence with a named person; not publicly retrievable
    "internal_hand_calc",     # our own worked calculation (ADR-006 `hand_calc_notebook`)
    "internal_analysis",      # our own analysis or study, cited by a `derived_analysis` pedigree
    "second_library_output",  # our execution of an independent library (ADR-006 `second_library`)
]

# The origins a `Referent` may cite. The three internal members are excluded because ADR-021's
# referent-laundering prohibition is about where a number ORIGINATED, not about who wrote the
# code: `second_library_output` is our own execution, so a referent backed by it would be
# FarSight scoring itself against itself, which is precisely the operation that record forbids.
#
# `private_communication` is external but is NOT publicly retrievable, so it is admissible here
# and separately visible -- AT-9 asks an auditor to check one referent point against its cited
# public source, and a referent resting only on private correspondence cannot support that step.
EXTERNAL_PUBLICATION_ORIGINS = frozenset(
    {
        "published_literature",
        "standard_or_handbook",
        "agency_technical_report",
        "public_dataset",
        "private_communication",
    }
)

# Registrar-issued identifier schemes. Closed, because each admits one printed form and an open
# list would readmit "urn:whatever" strings nothing can compare.
IdentifierScheme = Literal[
    "doi",
    "arxiv",
    "isbn",
    "issn",
    "handle",
    "report_number",          # e.g. a JPL D-number or NASA TM number
    "standard_designation",   # e.g. "810-005", "CCSDS 131.0-B-4"
]

SourceRevisionReason = Literal[
    "transcription_corrected",
    "identifier_added",
    "same_work_relinked",     # this and the superseded object are the same work
    "publisher_revised",      # the publication itself issued a new version
    "withdrawn",              # retracted or otherwise no longer citable
]

AssumptionRevisionReason = Literal[
    "bound_tightened",
    "bound_loosened",
    "statement_clarified",
    "evidence_added",
    "withdrawn",
]

MIN_STATEMENT_CHARS = 40   # an assumption a reviewer can check is a sentence, not a phrase
MIN_CONSEQUENCE_CHARS = 20  # what breaks if this is false; the first thing an auditor reads


def _check_id(v: str, field: str) -> str:
    if not SEGMENT_RE.match(v) or len(v) > MAX_SEGMENT_CHARS:
        raise ValueError(
            f"{field} {v!r} is outside the segment grammar (ADR-017 rule 3). It is a label a "
            f"human says out loud, never a key: identity is the digest (ADR-001), and two "
            f"objects sharing this name are still two objects."
        )
    return v


class SourceIdentifier(FrozenModel):
    """A registrar-issued identifier, transcribed exactly as the publication prints it.

    ``value`` is **verbatim**, and that is the whole design. A validator that lowercased a DOI or
    stripped hyphens from an ISBN would be normalizing value, which ADR-001 forbids; and a
    grammar strict enough to force one spelling just moves the normalization into the author's
    head, off the record, where it destroys the string equality the comparison rests on. So the
    only checks here are hygiene -- one line, no surrounding whitespace -- and the comparison is
    exact string equality between two things a human typed.

    ``part`` names a separately issued division of a numbered series. It exists because the
    flagship's central source needs it: DSN 810-005 is a handbook whose modules are individually
    issued under one designation, so ``("standard_designation", "810-005", "104")`` and the same
    with ``"105"`` are different documents that a designation-only key would merge.
    """

    scheme: IdentifierScheme
    value: str
    part: str | None

    @field_validator("value", "part")
    @classmethod
    def _hygiene(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("an identifier value may not be blank")
        if v != v.strip() or "\n" in v:
            raise ValueError(
                f"identifier {v!r} carries surrounding whitespace or a newline. This is the only "
                f"normalization performed: the value is otherwise transcribed exactly as printed, "
                f"because deciding that two spellings are one identifier is normalizing value "
                f"(ADR-001)."
            )
        return v

    def key(self) -> tuple[str, str, str]:
        """The exact triple two transcriptions must share to be the same printed identifier."""
        return (self.scheme, self.value, self.part or "")


class Source(VersionedDocument):
    """A citation of record: what was read, and where it came from.

    A ``Source`` is the *publication*; a ``DataArtifact`` is the *bytes*. ADR-021 keeps them
    apart deliberately -- a ``Referent`` carries ``source_refs`` and ``artifact_refs`` in two
    parallel lists -- and this object points at artifacts rather than absorbing them. Without
    that pointer ``origin`` would be an author's unfalsifiable word about where a number came
    from; with it, a source claiming to be external has to name bytes that are in the package's
    input closure.

    **A Source has no pedigree, and that is deliberate.** Provenance has to terminate somewhere
    or it regresses forever, and this is the terminal node: a belief cites a source, and the
    source cites nothing. What would go in a pedigree here -- who read it, how well -- is a
    property of the *reading*, and ADR-021 already puts that on the object that does the reading
    (``ReferentPoint.locator``, "where in the artifact this was read from").
    """

    source_id: str
    title: str
    origin: SourceOrigin
    issued: str
    identifiers: list[SourceIdentifier]
    artifact_refs: list[Ref]
    revision: int = 1
    supersedes: Ref | None = None
    revision_reason: SourceRevisionReason | None = None

    @field_validator("source_id")
    @classmethod
    def _check_source_id(cls, v: str) -> str:
        return _check_id(v, "source_id")

    @field_validator("title", "issued")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a source states a title and when it was issued")
        return v

    @field_validator("identifiers")
    @classmethod
    def _check_identifiers(cls, v: list[SourceIdentifier]) -> list[SourceIdentifier]:
        keys = [i.key() for i in v]
        if len(set(keys)) != len(keys):
            raise ValueError(f"source repeats an identifier: {sorted({k for k in keys if keys.count(k) > 1})}")
        if keys != sorted(keys):
            raise ValueError(
                "identifiers must be sorted by (scheme, value, part), so that two transcriptions "
                "of the same citation are the same document and hash alike"
            )
        return v

    @field_validator("artifact_refs")
    @classmethod
    def _check_artifacts(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("source cites the same artifact twice")
        if v != sorted(v):
            raise ValueError("artifact_refs must be byte-wise sorted")
        return v

    @model_validator(mode="after")
    def _check(self) -> "Source":
        if self.revision < 1:
            raise ValueError("revision is monotone and starts at 1; identity is still the digest")
        if (self.supersedes is None) != (self.revision_reason is None):
            raise ValueError(
                "supersedes and revision_reason travel together (ADR-021 decision 8, ADR-026): a "
                "supersession with no stated reason is an unexplained change to the record, and a "
                "reason with nothing superseded names no change at all"
            )
        # Keeps `revision` from being decorative. It cannot be checked against the superseded
        # object's revision without resolving the digest, but it can be kept consistent with the
        # existence of a chain, which is what stops revision 7 appearing on a first draft.
        if (self.revision > 1) != (self.supersedes is not None):
            raise ValueError(
                f"revision {self.revision} and supersedes={self.supersedes!r} disagree: a first "
                f"revision supersedes nothing, and a later one names what it replaced. Otherwise "
                f"the number is decoration a reader would take for a version history."
            )
        return self

    def is_external_publication(self) -> bool:
        """True when this source may back a ``Referent`` (ADR-021's laundering prohibition).

        The three internal origins are excluded because that record is about where a number
        *originated*, not who wrote the code: ``second_library_output`` is our own execution, so a
        referent resting on it would be FarSight scored against itself.

        This is the author's declaration, not proof. What anchors it is ``artifact_refs``: the
        freeze validator that pairs with this refuses an externally-declared source backing a
        referent unless it names bytes inside the package's input closure. That validator needs
        ADR-021's ``Referent`` and ADR-007's package, and is named in the module docstring rather
        than implied here.
        """
        return self.origin in EXTERNAL_PUBLICATION_ORIGINS

    def collision_keys(self) -> frozenset[tuple[str, str, str]]:
        """Identifier keys another source sharing one is probably the same work as.

        **Reported, never refused.** A freeze-time refusal on a shared key was designed and then
        refuted by the case it most needed to handle: a numbered series issues many documents
        under one designation, and a check that rejects them rejects a legal document set on the
        flagship's own central source. A validator one layer up may surface a shared key for a
        human to resolve -- which is a different act from refusing a design at freeze.
        """
        return frozenset(i.key() for i in self.identifiers)


class AssumptionBound(FrozenModel):
    """The bracket an assumption asserts. Never a point.

    This is the closure that makes ``Unknown.bounding_assumption_ref`` safe. An ``Unknown``
    discharged by an assumption is still NOT FITTED (ADR-007's unknown register), and if an
    assumption could carry a single value then discharging an unknown would hand it a concrete
    number -- reintroducing the silently-fitted default ADR-001 rule 6 forbids and AT-6 tests
    for. A bracket cannot do that: it says where the value lies, not what it is.

    One-sided bounds are carried as an **absent edge**, never as an invented finite one. "The
    throughput is at most 0.5" with a fabricated lower edge of 0 would put a number in the record
    that no source stated, which is the same fitting under a different name.
    """

    lower: Quantity | None
    upper: Quantity | None

    @model_validator(mode="after")
    def _check(self) -> "AssumptionBound":
        if self.lower is None and self.upper is None:
            raise ValueError(
                "an assumption states a bound; with neither edge it asserts nothing and cannot "
                "discharge an Unknown"
            )
        if self.lower is not None and self.upper is not None:
            if self.lower.unit != self.upper.unit:
                raise ValueError(
                    f"bound edges carry different units: {self.lower.unit!r} and "
                    f"{self.upper.unit!r}. Convert at the boundary before stating the bound."
                )
            if self.lower.as_decimal() > self.upper.as_decimal():
                raise ValueError(f"bound lower edge {self.lower} exceeds upper edge {self.upper}")
            if self.lower.as_decimal() == self.upper.as_decimal():
                raise ValueError(
                    f"bound edges are equal ({self.lower}), which is a point value wearing an "
                    f"interval's clothes. An assumption brackets a quantity nobody measured; a "
                    f"value we claim to know is a Deterministic belief with a pedigree, and "
                    f"letting this shape through is how an Unknown acquires a number (AT-6)."
                )
        return self

    def is_one_sided(self) -> bool:
        return (self.lower is None) != (self.upper is None)


class Assumption(VersionedDocument):
    """A standing claim we make without having measured it, and what it would cost if false.

    Reachable from a frozen design, it lands in ``registers/assumptions.json`` (ADR-007), which
    is the first file an external reviewer opens after the claim statement. That is what the
    prose floors are for: the register is read by a human deciding whether to trust the package,
    and a one-word assumption tells them nothing.

    ``pedigree`` is mandatory and is the same type every belief carries, so "on what basis" is
    answered in the same vocabulary and an assumption resting on ``speculative`` is exactly as
    visible as a speculative number. It is also why this type is not split into a thin identity
    plus a version: ADR-007 requires the register to carry each assumption *with pedigree*, and a
    parent stable enough to be worth splitting out is a parent with no pedigree on it.
    """

    assumption_id: str
    statement: str
    consequence_if_false: str
    bound: AssumptionBound | None
    pedigree: Pedigree
    source_refs: list[Ref]
    review_by: _dt.date | None
    revision: int = 1
    supersedes: Ref | None = None
    revision_reason: AssumptionRevisionReason | None = None

    @field_validator("assumption_id")
    @classmethod
    def _check_assumption_id(cls, v: str) -> str:
        return _check_id(v, "assumption_id")

    @field_validator("statement")
    @classmethod
    def _check_statement(cls, v: str) -> str:
        if len(v.strip()) < MIN_STATEMENT_CHARS:
            raise ValueError(
                f"state the assumption in a sentence a reviewer can check: at least "
                f"{MIN_STATEMENT_CHARS} characters. This text is what lands in the assumption "
                f"register, which is the first file an external reviewer opens."
            )
        return v

    @field_validator("consequence_if_false")
    @classmethod
    def _check_consequence(cls, v: str) -> str:
        if len(v.strip()) < MIN_CONSEQUENCE_CHARS:
            raise ValueError(
                f"say what breaks if this assumption is false, in at least "
                f"{MIN_CONSEQUENCE_CHARS} characters. An assumption whose consequence nobody "
                f"stated cannot be weighed against the conclusion that rests on it."
            )
        return v

    @field_validator("source_refs")
    @classmethod
    def _check_sources(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("assumption cites the same source twice")
        if v != sorted(v):
            raise ValueError("source_refs must be byte-wise sorted")
        return v

    @model_validator(mode="after")
    def _check(self) -> "Assumption":
        if self.revision < 1:
            raise ValueError("revision is monotone and starts at 1; identity is still the digest")
        if (self.supersedes is None) != (self.revision_reason is None):
            raise ValueError(
                "supersedes and revision_reason travel together: a supersession with no stated "
                "reason is an unexplained change to a record an auditor reads"
            )
        if (self.revision > 1) != (self.supersedes is not None):
            raise ValueError(
                f"revision {self.revision} and supersedes={self.supersedes!r} disagree: a first "
                f"revision supersedes nothing, and a later one names what it replaced"
            )
        if self.review_by is not None and self.pedigree.assessed_on >= self.review_by:
            raise ValueError(
                f"review_by {self.review_by} is not after the pedigree's assessment date "
                f"{self.pedigree.assessed_on}; an assumption due for review before it was made "
                f"was never valid"
            )
        return self

    def bounds_an_unknown(self) -> bool:
        """True when this assumption can discharge an ``Unknown`` at freeze.

        An assumption may legitimately state something unquantified -- "failures are conditionally
        independent given the declared factors" is an assumption with no bracket. Such an
        assumption belongs in the register and may not stand in for a missing number, which is
        what ``Unknown.bounding_assumption_ref`` would ask of it.
        """
        return self.bound is not None


# The dependency edges that make an assumption load-bearing. `supersedes` is deliberately absent:
# revision history is not dependency, and putting it in the one column the reverse index exists
# for would report a withdrawn assumption as still carrying weight.
_ASSUMPTION_EDGES = ("bounding_assumption_ref", "assumption_refs")


def _cites(node: Any, assumption_ref: str) -> bool:
    """True when ``assumption_ref`` appears under a dependency edge anywhere inside ``node``."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _ASSUMPTION_EDGES:
                if value == assumption_ref:
                    return True
                if isinstance(value, list) and assumption_ref in value:
                    return True
            if _cites(value, assumption_ref):
                return True
    elif isinstance(node, list):
        return any(_cites(item, assumption_ref) for item in node)
    return False


def dependents_of(
    assumption_ref: str, documents: Iterable[tuple[str, Any]]
) -> frozenset[str]:
    """The digests of documents that depend on ``assumption_ref``.

    The pure half of ADR-007's requirement that the assumption register carry each assumption
    "with pedigree and the objects that depend on it". It is a **forward** walk over documents
    already in hand: the reverse index is materialized from this into the register and recomputed
    by ``verify``, never stored on the assumption, because a back-pointer would change the hash
    of its target and re-version every belief citing it.

    ``documents`` is an iterable of ``(digest, document)`` pairs. The caller supplies the digest
    because ``schemas`` is a leaf package and may not import the hashing layer -- and the caller
    already holds both, since it read the documents out of a package by their addresses.

    The walk is recursive, because an ``assumption_refs`` list can sit nested inside a larger
    document (a ``ModelVersion`` inside a design, say) rather than at its top level. Matching is
    on the two dependency edges only.
    """
    return frozenset(
        digest
        for digest, doc in documents
        if _cites(doc.model_dump() if hasattr(doc, "model_dump") else doc, assumption_ref)
    )
