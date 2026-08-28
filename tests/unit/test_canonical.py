"""Canonical JSON and content addressing (ADR-001).

Every reproducibility and tamper-evidence claim in the product rests on this module producing
identical bytes for identical content, so these tests are deliberately paranoid about the
things that silently differ between platforms and JSON libraries: key ordering, escaping,
number handling, and process boundaries.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from farsight.hashing.canonical import (
    CanonicalizationError,
    canonical_bytes,
    canonicalize,
    content_hash,
    is_content_hash,
)

# --------------------------------------------------------------------------------------
# Rule 2: no JSON floats, ever
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc",
    [
        0.1,
        {"a": 1.0},
        {"a": {"b": [1, 2, 3.5]}},
        [0.0],
        {"nested": {"deep": {"deeper": 2.5}}},
    ],
)
def test_floats_are_refused_anywhere(doc):
    with pytest.raises(CanonicalizationError, match="float"):
        canonicalize(doc)


def test_float_refusal_names_the_location():
    with pytest.raises(CanonicalizationError) as exc:
        canonicalize({"outer": {"inner": [1, 2.5]}})
    assert "/outer/inner/1" in str(exc.value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_refused(value):
    # Rule 3. These are floats, so the float rule catches them first -- what matters is that
    # they never reach a hash, not which rule stops them.
    with pytest.raises(CanonicalizationError):
        canonicalize({"x": value})


def test_negative_zero_refused_as_a_float():
    # -0.0 is the classic canonicalization trap: it compares equal to 0.0 but serializes
    # differently in many implementations. Forbidding floats outright disposes of it.
    with pytest.raises(CanonicalizationError):
        canonicalize({"x": -0.0})


def test_integers_permitted_within_exact_range():
    assert canonicalize({"n": 42}) == '{"n":42}'
    assert canonicalize({"n": -7}) == '{"n":-7}'
    assert canonicalize({"n": 2**53}) == '{"n":9007199254740992}'


def test_integers_outside_exact_range_refused():
    with pytest.raises(CanonicalizationError, match="exactly-representable"):
        canonicalize({"n": 2**53 + 1})


def test_bools_are_not_integers():
    # bool subclasses int in Python; `True` must serialize as `true`, not `1`.
    assert canonicalize({"a": True, "b": False}) == '{"a":true,"b":false}'


# --------------------------------------------------------------------------------------
# Key ordering and structural invariance
# --------------------------------------------------------------------------------------


def test_key_order_does_not_affect_output():
    a = {"zebra": 1, "alpha": 2, "mike": 3}
    b = {"mike": 3, "alpha": 2, "zebra": 1}
    assert canonicalize(a) == canonicalize(b) == '{"alpha":2,"mike":3,"zebra":1}'
    assert content_hash(a) == content_hash(b)


def test_nested_key_order_does_not_affect_output():
    a = {"outer": {"z": 1, "a": 2}, "first": [{"q": 1, "b": 2}]}
    b = {"first": [{"b": 2, "q": 1}], "outer": {"a": 2, "z": 1}}
    assert content_hash(a) == content_hash(b)


def test_array_order_is_significant():
    # Arrays are ordered data. A canonicalizer that sorted them would silently equate two
    # different kernel sequences, which ADR-016 relies on being different.
    assert content_hash([1, 2]) != content_hash([2, 1])


def test_no_insignificant_whitespace():
    out = canonicalize({"a": [1, 2], "b": {"c": 3}})
    assert out == '{"a":[1,2],"b":{"c":3}}'
    assert " " not in out
    assert not out.endswith("\n")


def test_utf16_code_unit_ordering():
    # JCS sorts object keys by UTF-16 code unit, not by code point, and the two orders
    # genuinely disagree. U+E000 is a single UTF-16 unit 0xE000; U+10000 is the surrogate pair
    # 0xD800 0xDC00. So by code point U+E000 comes first, and by UTF-16 code unit U+10000
    # comes first. A canonicalizer using Python's default string sort would emit the wrong
    # order here, and every hash containing such a key would diverge from a conforming
    # implementation in another language.
    bmp = ""
    supp = "\U00010000"

    assert bmp < supp  # Python: by code point, 0xE000 < 0x10000
    assert sorted([bmp, supp]) == [bmp, supp]  # what a naive implementation would do

    out = canonicalize({bmp: 1, supp: 2})
    assert out.index('"' + supp) < out.index('"' + bmp)  # JCS: by UTF-16 unit, 0xD800 < 0xE000


def test_bmp_keys_sort_identically_under_both_orders():
    # The disagreement above is confined to supplementary characters. Across the whole BMP the
    # two orders coincide, which is why the bug is easy to miss without a targeted test.
    keys = ["a", "A", "z", "0", "_", "é", "ÿ", "퟿"]
    out = canonicalize({k: 1 for k in keys})
    positions = [out.index('"' + k + '"') for k in sorted(keys)]
    assert positions == sorted(positions)


def test_unicode_is_not_escaped():
    # ECMAScript JSON.stringify emits literal UTF-8 for non-ASCII; json.dumps would escape it
    # by default. Divergence here would change every hash containing a non-ASCII character.
    assert canonicalize({"k": "café"}) == '{"k":"café"}'
    assert canonical_bytes({"k": "café"}) == '{"k":"café"}'.encode("utf-8")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('a"b', '"a\\"b"'),
        ("a\\b", '"a\\\\b"'),
        ("a\nb", '"a\\nb"'),
        ("a\tb", '"a\\tb"'),
        ("a\rb", '"a\\rb"'),
        ("a\bb", '"a\\bb"'),
        ("a\fb", '"a\\fb"'),
        ("a\x00b", '"a\\u0000b"'),
        ("a\x1fb", '"a\\u001fb"'),
    ],
)
def test_string_escaping(raw, expected):
    assert canonicalize(raw) == expected


def test_output_parses_back_to_the_same_value():
    doc = {"b": [1, {"z": "x", "a": None}], "a": True, "u": "café\n"}
    assert json.loads(canonicalize(doc)) == doc


# --------------------------------------------------------------------------------------
# Refusals that protect the hash from meaning something we did not validate
# --------------------------------------------------------------------------------------


def test_non_string_keys_refused():
    with pytest.raises(CanonicalizationError, match="non-string object key"):
        canonicalize({1: "a"})


def test_unserializable_types_refused():
    class Widget:
        pass

    with pytest.raises(CanonicalizationError, match="unserializable type"):
        canonicalize({"w": Widget()})


def test_sets_refused():
    # A set has no canonical order and no JSON representation; accepting one would make the
    # hash depend on Python's iteration order.
    with pytest.raises(CanonicalizationError):
        canonicalize({"s": {1, 2, 3}})


# --------------------------------------------------------------------------------------
# Content addressing
# --------------------------------------------------------------------------------------


def test_content_hash_is_bare_lowercase_hex64():
    h = content_hash({"a": 1})
    assert is_content_hash(h)
    assert len(h) == 64
    assert h == h.lower()
    assert not h.startswith("sha256:")


def test_content_hash_equals_sha256_of_the_canonical_bytes():
    # The identifier is exactly sha256 over the canonical UTF-8 bytes and nothing else: no
    # salt, no length prefix, no domain separator. An auditor reproduces it with sha256sum,
    # which is the property ADR-007 sells and the reason nothing clever belongs here.
    import hashlib

    doc = {"b": 2, "a": 1}
    assert canonical_bytes(doc) == b'{"a":1,"b":2}'
    assert content_hash(doc) == hashlib.sha256(b'{"a":1,"b":2}').hexdigest()


def test_is_content_hash_rejects_prefixed_and_uppercase():
    h = content_hash({"a": 1})
    assert not is_content_hash("sha256:" + h)
    assert not is_content_hash(h.upper())
    assert not is_content_hash(h[:63])


def test_hash_is_stable_across_a_process_boundary(tmp_path: Path):
    # Guards against anything process-local leaking into the digest: hash randomization,
    # dict ordering, locale, interpreter state. ADR-006 forbids exactly this class of
    # dependency, and a subprocess with a different PYTHONHASHSEED is the cheap proof.
    src = Path(__file__).resolve().parents[2] / "src"
    script = tmp_path / "child.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(src)!r})\n"
        "from farsight.hashing.canonical import content_hash\n"
        "print(content_hash({'zebra': [1, {'b': 'café', 'a': None}], 'alpha': True}))\n",
        encoding="utf-8",
    )
    local = content_hash({"zebra": [1, {"b": "café", "a": None}], "alpha": True})
    out = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONHASHSEED": "12345", "PATH": ""},
        check=True,
    )
    assert out.stdout.strip() == local
