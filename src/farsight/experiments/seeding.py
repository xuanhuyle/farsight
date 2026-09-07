"""Seed derivation: every random number in FarSight traces to one root, by arithmetic.

ADR-005. One 128-bit root seed per experiment, and every bit stream in every run derived from it
by a **direct** function of ``(root_seed, run_index, stream_id)`` -- never sequentially.

That single property is what makes the rest work. Replaying run 4242 costs one derivation rather
than 4,242 of them; resume is trivially correct because no run's seed depends on any other run
having happened; and running the campaign on one worker or eight gives identical numbers, because
nothing about the seed depends on execution order. A sequential scheme would make all three of
those either expensive or false.

**The registry is exactly three streams, and the ids are numbers rather than hashed names.**
Hashing the stream name would mean a rename silently changes every result in every campaign.
Ids 3 through 15 are reserved; an existing id is never renumbered, and appending id 3 later moves
nothing in streams 0, 1 or 2 -- old campaigns are untouched and only ``STREAM_REGISTRY_VERSION``
advances for new packages.

There is deliberately **no** ``fault_activations`` stream. A fault's magnitude is a physical
quantity drawn from a Belief like any other, and giving it its own stream would mean two
parameters of the same physical model are drawn from different bit streams for no reason a reader
could reconstruct. The accepted cost is stated plainly in ADR-005: editing a fault campaign moves
every aleatory draw downstream of the edit within each affected run. A campaign whose fault set
changed is a **new campaign**, and its ``experiment_hash`` says so.

**Philox, and why the choice is named rather than defaulted.** NumPy's own guarantee, quoted from
``numpy.random.Philox`` as installed (NumPy 2.5.2):

    **Compatibility Guarantee** ``Philox`` makes a guarantee that a fixed ``seed`` will always
    produce the same random integer stream.

``default_rng``'s choice of bit generator is not itself pinned by that guarantee, which is why
this module names Philox explicitly. The guarantee is about the *bit generator*; it is not a
promise that any particular ``Generator`` method maps words to values identically forever, which
is why ADR-005 archives the derived words and has replay read the archive rather than re-derive.

**Archived, not re-derived.** ``runs/seeds_<i>.json`` records the ``generate_state`` words that
were actually consumed. Replay reads them; ``--verify-derivation`` re-derives and compares, and a
mismatch is reported as an environment or library finding rather than as a package verification
failure. That is the decision that lets a 2026 package replay in 2029 regardless of what NumPy
did in between.

**This module is the only place randomness is created.** ``os.urandom`` appears in exactly one
function here, and the ``no-naked-rng`` lint fails CI on any construction of ``numpy.random.*``,
``random.*`` or ``secrets.*`` anywhere else under ``src/farsight/``.
"""

from __future__ import annotations

import os
from types import MappingProxyType
from typing import Final, Mapping

import numpy as np

__all__ = [
    "STREAMS",
    "STREAM_REGISTRY_VERSION",
    "RESERVED_STREAM_IDS",
    "DESIGN_SCOPE_TAG",
    "ROOT_SEED_BYTES",
    "SeedingError",
    "new_root_seed",
    "stream_id_for",
    "stream_rng",
    "state_words",
    "derived_state",
]

from farsight.schemas.errors import FarSightError


class SeedingError(FarSightError, ValueError):
    """A seed could not be derived from the tuple it was asked for.

    ``ValueError`` as well, so a refusal raised from inside a validator folds into a
    ``ValidationError`` rather than escaping as a second exception type.
    """


# ADR-005: append-only, and the authority. Any other record naming a stream that is not one of
# these three is wrong, not ahead.
STREAMS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "aleatory_draws": 0,       # every aleatory value, drawn at plan time in sorted path order
        "engine_module_seeds": 1,  # integers for adapters declaring seed_scope == "per_module"
        "sampler_internal": 2,     # LHS permutations and sampler bookkeeping only
    }
)

STREAM_REGISTRY_VERSION: Final = 1

# Reserved for append. The intended first tenant is per-entity realization inside a
# FarSight-native engine, with a key shape of (run_index, 3, entity_ordinal). Not designed here.
RESERVED_STREAM_IDS: Final = frozenset(range(3, 16))

# ADR-005: design-scoped keys are a second derivation, not a fourth stream. They are rooted at
# `design_seed` rather than `root_seed`, consumed once by the planner, and produce stratum
# assignments rather than physical values. `stream_rng` is never called with one.
DESIGN_SCOPE_TAG: Final = 0xD5

ROOT_SEED_BYTES: Final = 16  # 128 bits


def new_root_seed() -> int:
    """Mint a fresh 128-bit root seed.

    The **only** call to ``os.urandom`` in ``src/farsight/``, enforced by the ``no-naked-rng``
    lint. Everything else in the system is a pure function of a root seed that was either minted
    here or supplied explicitly for a replication study.
    """
    return int.from_bytes(os.urandom(ROOT_SEED_BYTES), "big")


def stream_id_for(name: str) -> int:
    """The registry id for a stream name, or a refusal naming the registry.

    A refusal rather than a lookup default: a typo'd stream name silently falling back to stream
    0 would mix sampler bookkeeping into the physics draws, and nothing downstream could tell.
    """
    try:
        return STREAMS[name]
    except KeyError:
        raise SeedingError(
            f"{name!r} is not a registered stream. The registry is exactly "
            f"{sorted(STREAMS)} (ADR-005, which is the authority on it). Ids 3-15 are reserved "
            f"for append; a new stream is a decision, because stream_id enters spawn_key and a "
            f"fourth stream means different drawn values and different hashes for every run "
            f"that touches it."
        ) from None


def _check_key(root_seed: int, run_index: int, stream_id: int) -> None:
    if root_seed < 0:
        raise SeedingError(f"root_seed must be non-negative; got {root_seed}")
    if run_index < 0:
        raise SeedingError(
            f"run_index {run_index} is negative. It is a position in a deterministic "
            f"enumeration of (outer epistemic point, inner aleatory draw)."
        )
    if stream_id not in set(STREAMS.values()) | RESERVED_STREAM_IDS:
        raise SeedingError(
            f"stream_id {stream_id} is outside the registry {sorted(set(STREAMS.values()))} and "
            f"the reserved range {min(RESERVED_STREAM_IDS)}-{max(RESERVED_STREAM_IDS)}."
        )


def stream_rng(root_seed: int, run_index: int, stream_id: int) -> np.random.Generator:
    """The generator for one stream of one run. A pure function of its three arguments.

    ``spawn_key`` is constructed directly rather than by spawning from a parent sequence, which
    is what makes this O(1) with no predecessors to generate.
    """
    _check_key(root_seed, run_index, stream_id)
    sequence = np.random.SeedSequence(entropy=root_seed, spawn_key=(run_index, stream_id))
    return np.random.Generator(np.random.Philox(sequence))


def state_words(root_seed: int, run_index: int, stream_id: int, n: int) -> list[str]:
    """``n`` ``generate_state`` words for one stream, as ``0x``-prefixed 32-bit hex strings.

    These are what ``runs/seeds_<i>.json`` archives, and what ``--verify-derivation`` compares
    against. Words rather than drawn values on purpose: the words are the output of the part
    NumPy guarantees, while the mapping from words to a normal deviate is a ``Generator`` method
    whose stability across versions is a weaker promise.
    """
    _check_key(root_seed, run_index, stream_id)
    if n < 1:
        raise SeedingError(f"asked for {n} state words; a stream that consumed none is recorded as []")
    sequence = np.random.SeedSequence(entropy=root_seed, spawn_key=(run_index, stream_id))
    return [f"0x{int(w):08x}" for w in sequence.generate_state(n, dtype=np.uint32)]


def derived_state(root_seed: int, run_index: int, words_per_stream: Mapping[str, int]) -> dict[str, list[str]]:
    """The ``derived_state`` block of a seed archive: the words each stream actually consumed.

    ``words_per_stream`` comes from the consumer, because how many words a run used is a fact
    about the run rather than about the derivation. A stream that consumed nothing is recorded as
    an empty list, which is an assertion that it was not used -- not an absence.
    """
    unknown = sorted(set(words_per_stream) - set(STREAMS))
    if unknown:
        raise SeedingError(
            f"derived_state names streams that are not in the registry: {unknown}. "
            f"The registry is {sorted(STREAMS)} (ADR-005)."
        )
    return {
        name: (state_words(root_seed, run_index, STREAMS[name], count) if count else [])
        for name, count in sorted(words_per_stream.items())
    }
