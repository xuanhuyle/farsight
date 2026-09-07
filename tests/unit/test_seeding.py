"""Seed derivation (ADR-005) and the `no-naked-rng` lint.

The property that matters is not "the numbers look random". It is that **every** random number in
the system is a pure function of one root seed and a run's address -- so replay is cheap, resume
is correct without bookkeeping, and running on one worker or eight gives identical results.

Two tests here are shaped by what a single machine cannot prove. Cross-platform equality is
asserted against a checked-in golden compared on both CI legs, because a same-platform assertion
passes vacuously. Cross-process determinism runs a real subprocess, because an in-process check
cannot see state that a fresh interpreter would not have.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from farsight.experiments.seeding import (
    DESIGN_SCOPE_TAG,
    RESERVED_STREAM_IDS,
    STREAM_REGISTRY_VERSION,
    STREAMS,
    SeedingError,
    derived_state,
    new_root_seed,
    state_words,
    stream_id_for,
    stream_rng,
)

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "farsight"
GOLDEN = REPO / "tests" / "golden" / "seed_derivation.json"

ROOT = 31415926535897932384626433832795028841


# --------------------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------------------


def test_the_registry_is_exactly_three_streams():
    """ADR-005 is the authority: any other record naming a fourth stream is wrong, not ahead."""
    assert dict(STREAMS) == {
        "aleatory_draws": 0, "engine_module_seeds": 1, "sampler_internal": 2
    }
    assert STREAM_REGISTRY_VERSION == 1


def test_there_is_no_fault_activations_stream():
    """Rejected deliberately. A fault's magnitude is a physical quantity drawn from a Belief like
    any other; a separate stream would draw two parameters of one physical model from different
    bit streams for no reason a reader could reconstruct."""
    with pytest.raises(SeedingError, match="not a registered stream"):
        stream_id_for("fault_activations")


def test_an_unregistered_stream_name_is_refused_not_defaulted():
    """A typo falling back to stream 0 would mix sampler bookkeeping into the physics draws, and
    nothing downstream could tell."""
    with pytest.raises(SeedingError, match="not a registered stream"):
        stream_id_for("aleatory_draw")  # singular; a plausible typo
    assert stream_id_for("aleatory_draws") == 0


def test_ids_three_to_fifteen_are_reserved_for_append():
    assert RESERVED_STREAM_IDS == frozenset(range(3, 16))
    assert not (set(STREAMS.values()) & RESERVED_STREAM_IDS)
    state_words(ROOT, 0, 3, 2)  # a reserved id derives; it simply has no name yet
    with pytest.raises(SeedingError, match="outside the registry"):
        state_words(ROOT, 0, 16, 2)


# --------------------------------------------------------------------------------------
# Derivation is direct and collision-free
# --------------------------------------------------------------------------------------


def test_derivation_is_collision_free_across_runs_and_streams():
    """The cross product matters, not just the run axis. If only run_index varied, deleting
    stream_id from spawn_key would leave the test green while all three streams of a run
    collided."""
    seen: dict[tuple, tuple] = {}
    for run_index in range(400):
        for stream_id in STREAMS.values():
            words = tuple(state_words(ROOT, run_index, stream_id, 4))
            assert words not in seen, f"collision: {(run_index, stream_id)} vs {seen[words]}"
            seen[words] = (run_index, stream_id)
    assert len(seen) == 400 * len(STREAMS)


def test_the_three_streams_of_one_run_differ():
    """The specific case the cross-product test exists to protect."""
    words = {sid: tuple(state_words(ROOT, 4242, sid, 4)) for sid in STREAMS.values()}
    assert len(set(words.values())) == len(STREAMS)


def test_derivation_is_enumeration_order_independent():
    """Forward, reverse and interleaved must give identical words. A stateful implementation --
    a module-level counter mixed into the key, say -- would pass a single-pass test and fail
    this one."""
    forward = [state_words(ROOT, i, 0, 3) for i in range(50)]
    reverse = [state_words(ROOT, i, 0, 3) for i in reversed(range(50))][::-1]
    interleaved = [None] * 50
    for i in list(range(0, 50, 2)) + list(range(1, 50, 2)):
        interleaved[i] = state_words(ROOT, i, 0, 3)
    assert forward == reverse == interleaved


def test_stream_rng_is_keyed_on_the_full_address():
    """`stream_rng` is the function ADR-005 specifies and the runner will call, and every other
    test here goes through `state_words`. Without this, dropping `run_index` from the generator's
    spawn_key would leave the whole suite green while every run in a campaign drew the same
    numbers."""
    draws = {}
    for run_index in (0, 1, 4242):
        for stream_id in STREAMS.values():
            draws[(run_index, stream_id)] = [stream_rng(ROOT, run_index, stream_id).random()
                                             for _ in range(3)]
    assert len({tuple(v) for v in draws.values()}) == len(draws)

    # And it is a pure function: the same address twice gives the same draws.
    first = [stream_rng(ROOT, 7, 0).random() for _ in range(3)]
    assert first == [stream_rng(ROOT, 7, 0).random() for _ in range(3)]


def test_stream_rng_and_state_words_share_one_derivation():
    """They must key identically, or the archived words describe a stream nobody drew from."""
    import numpy as np  # noqa: PLC0415

    expected = np.random.Generator(
        np.random.Philox(np.random.SeedSequence(entropy=ROOT, spawn_key=(4242, 0)))
    ).random()
    assert stream_rng(ROOT, 4242, 0).random() == expected


def test_a_seed_is_a_pure_function_of_its_address():
    assert state_words(ROOT, 4242, 0, 4) == state_words(ROOT, 4242, 0, 4)
    assert state_words(ROOT, 4242, 0, 4) != state_words(ROOT + 1, 4242, 0, 4)


def test_negative_addresses_are_refused():
    with pytest.raises(SeedingError, match="negative"):
        state_words(ROOT, -1, 0, 2)
    with pytest.raises(SeedingError, match="non-negative"):
        state_words(-1, 0, 0, 2)


# --------------------------------------------------------------------------------------
# What one machine cannot prove
# --------------------------------------------------------------------------------------


def test_derivation_matches_the_checked_in_golden():
    """ADR-005 requires identical words on Windows and Linux. A same-platform assertion cannot
    show that, so the words are checked in and this test runs on both CI legs.

    If this fails, the question is what changed in the derivation or in NumPy. Regenerating the
    golden to make the build green would retire the guarantee silently.
    """
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert doc["root_seed"] == str(ROOT)
    assert doc["stream_registry_version"] == STREAM_REGISTRY_VERSION
    assert doc["keys"], "an empty golden would pass vacuously"
    for entry in doc["keys"]:
        assert state_words(
            ROOT, entry["run_index"], entry["stream_id"], len(entry["words"])
        ) == entry["words"], f"drift at run {entry['run_index']} stream {entry['stream']}"


def test_derivation_survives_a_process_boundary():
    """A fresh interpreter, not a fresh call. An in-process check cannot see state a new process
    would not have -- hash randomisation, an import-time cache, a module-level counter."""
    program = (
        "from farsight.experiments.seeding import state_words;"
        f"print(','.join(state_words({ROOT}, 4242, 0, 4)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, cwd=str(REPO)
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().split(",") == state_words(ROOT, 4242, 0, 4)


# --------------------------------------------------------------------------------------
# The archive
# --------------------------------------------------------------------------------------


def test_derived_state_records_an_unused_stream_as_empty_not_absent():
    """An empty list asserts the stream was not used; an absent key would be indistinguishable
    from one nobody recorded -- the empty-versus-missing rule ADR-007 applies to registers."""
    state = derived_state(ROOT, 7, {"aleatory_draws": 2, "sampler_internal": 0})
    assert state["sampler_internal"] == []
    assert len(state["aleatory_draws"]) == 2


def test_derived_state_refuses_a_stream_outside_the_registry():
    with pytest.raises(SeedingError, match="not in the registry"):
        derived_state(ROOT, 7, {"fault_activations": 2})


def test_state_words_are_hex_and_stable_in_width():
    for word in state_words(ROOT, 1, 0, 8):
        assert word.startswith("0x") and len(word) == 10
        int(word, 16)


# --------------------------------------------------------------------------------------
# The root seed, and the one place randomness enters
# --------------------------------------------------------------------------------------


def test_a_root_seed_is_128_bits_and_fresh_each_time():
    seeds = {new_root_seed() for _ in range(8)}
    assert len(seeds) == 8
    assert all(0 <= s < 2**128 for s in seeds)


def test_os_urandom_appears_exactly_once_in_the_source_tree():
    """ADR-005 states this as a property of the codebase: `os.urandom` appears in exactly one
    function, `new_root_seed`. Asserted rather than trusted."""
    hits = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "urandom"
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
            ):
                hits.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(hits) == 1, f"os.urandom call sites: {hits}"
    assert hits[0][0].endswith("experiments/seeding.py")


def test_no_naked_rng_anywhere_outside_seeding():
    """ADR-005's `no-naked-rng` lint. Randomness constructed outside the derivation would break
    the one property the whole scheme rests on: that every draw traces to the root seed.

    PARTIALLY MECHANIZED (SEED-1): an AST lint sees syntactic construction sites. It does not see
    randomness reached through an alias, a getattr, or a third-party call that seeds itself.
    """
    forbidden_roots = {"random", "secrets"}
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel.endswith("experiments/seeding.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_roots:
                        offenders.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in forbidden_roots or node.module.startswith("numpy.random"):
                    offenders.append(f"{rel}:{node.lineno}: from {node.module} import ...")
            elif isinstance(node, ast.Attribute):
                # numpy.random.<anything>
                inner = node.value
                if (
                    isinstance(inner, ast.Attribute)
                    and inner.attr == "random"
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id in {"np", "numpy"}
                ):
                    offenders.append(f"{rel}:{node.lineno}: numpy.random.{node.attr}")
    assert not offenders, "randomness constructed outside seeding.py:\n  " + "\n  ".join(offenders)


def test_the_lint_actually_recognises_a_violation():
    """The lint above scans a tree that currently contains no violation, so it would pass just as
    happily if its matching were broken. Feed it the shapes it must catch."""
    samples = [
        "import random\nx = random.random()\n",
        "import secrets\nx = secrets.token_bytes(8)\n",
        "import numpy as np\ng = np.random.default_rng()\n",
        "from numpy.random import default_rng\n",
    ]
    for source in samples:
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= any(a.name.split(".")[0] in {"random", "secrets"} for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found |= node.module.split(".")[0] in {"random", "secrets"} or \
                    node.module.startswith("numpy.random")
            elif isinstance(node, ast.Attribute):
                inner = node.value
                found |= (
                    isinstance(inner, ast.Attribute) and inner.attr == "random"
                    and isinstance(inner.value, ast.Name) and inner.value.id in {"np", "numpy"}
                )
        assert found, f"the lint would not have caught:\n{source}"


# --------------------------------------------------------------------------------------
# The design-scope tag
# --------------------------------------------------------------------------------------


def test_design_scoped_keys_are_separated_by_entropy_not_by_tag_value():
    """ADR-005 says the design-scope tag 0xD5 is "deliberately outside the run-index range". It
    is not: 0xD5 is 213, and ADR-004's own illustrative campaign is 9,600 runs, so run_index 213
    exists. Recorded as DEV-11.

    What actually separates them is the entropy: design-scoped keys are rooted at `design_seed`,
    a different value from `root_seed`, so a shared spawn_key prefix collides with nothing. This
    test asserts the separation that is real rather than the one the record claims.
    """
    assert DESIGN_SCOPE_TAG == 0xD5 == 213

    design_seed = ROOT + 1  # any value distinct from the root seed
    import numpy as np  # noqa: PLC0415 - constructing the comparison directly, not drawing

    design_words = list(
        np.random.SeedSequence(entropy=design_seed, spawn_key=(DESIGN_SCOPE_TAG, 0))
        .generate_state(4, dtype=np.uint32)
    )
    run_words = [int(w, 16) for w in state_words(ROOT, DESIGN_SCOPE_TAG, 0, 4)]
    assert design_words != run_words
