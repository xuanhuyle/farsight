"""Canonical JSON (RFC 8785 / JCS profile) and content addressing.

ADR-001. Identity is SHA-256 over the canonical serialization of an object, so every
reproducibility, provenance and tamper-evidence claim in the product rests on this module
producing the same bytes for the same content, on every platform, forever.

Two properties are load-bearing and are enforced here rather than trusted:

  * **No JSON floats, ever, in a hashed document.** Only integers within the exactly
    representable range are permitted. This removes JCS number serialization -- the hardest
    and least portable part of the spec -- from the trust surface entirely. Physical
    quantities are decimal strings plus a unit (``farsight.schemas.common.Quantity``).
  * **No NaN and no Infinity.** Ignorance is structural (an ``Unknown`` belief), never a
    non-finite float. Non-finite values may exist in raw channel arrays from a diverged run;
    they may never exist in a spec.

Both are refusals, not coercions: a float in a hashed document raises, and the message names
the path, because silently accepting one would make the resulting hash a lie about what
FarSight can guarantee.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from farsight.schemas.errors import FarSightError

__all__ = [
    "CanonicalizationError",
    "canonicalize",
    "canonical_bytes",
    "content_hash",
    "hash_object",
    "is_content_hash",
]

# JSON integers are restricted to the range where a float64 round-trip is exact. The bound is
# the same one ADR-020 uses for channel code maps, for the same reason: a value outside it
# cannot survive a trip through a JSON parser that uses doubles, and we must not emit an
# identifier that a conforming reader in another language cannot reproduce.
_MAX_EXACT_INT = 2**53
_MIN_EXACT_INT = -(2**53)


class CanonicalizationError(FarSightError, ValueError):
    """A document cannot be canonicalized, and therefore cannot be hashed.

    Raised rather than worked around. Every instance names the JSON pointer of the offending
    value, because the failure is nearly always a schema defect one layer up.

    Both bases are load-bearing. ``FarSightError`` because ADR-023 decision 8 requires every
    exception defined under ``src/farsight/`` to sit in the hierarchy -- one that does not is a
    site nobody classified, and the worker boundary needs a closed exception-to-``failure_class``
    mapping. ``ValueError`` because this is raised from inside Pydantic validators as well as
    directly, and Pydantic only folds ``ValueError`` and ``AssertionError`` into a
    ``ValidationError``; dropping it would make a hashing failure inside a validator escape as a
    second exception type callers would have to catch separately.
    """


def _pointer(path: tuple[str | int, ...]) -> str:
    """Render a location as an RFC 6901 JSON pointer for error messages."""
    if not path:
        return "<root>"
    out = []
    for part in path:
        token = str(part).replace("~", "~0").replace("/", "~1")
        out.append(token)
    return "/" + "/".join(out)


def _escape_string(s: str) -> str:
    """Serialize a string with JCS escaping.

    JCS mandates the ECMAScript ``JSON.stringify`` escape set: the two-character escapes where
    they exist, ``\\u00XX`` for the remaining control characters, and literal UTF-8 for
    everything else -- notably *no* ``\\uXXXX`` escaping of non-ASCII, which is where a naive
    ``json.dumps`` default would diverge.
    """
    out = ['"']
    for ch in s:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16_sort_key(s: str) -> tuple[int, ...]:
    """Sort key giving JCS's UTF-16 code-unit ordering.

    Python sorts strings by code point; JCS sorts object keys by UTF-16 code unit. The two
    agree across the entire Basic Multilingual Plane and disagree only where a supplementary
    character (which UTF-16 encodes as a surrogate pair beginning 0xD800-0xDBFF) meets a BMP
    character at or above U+E000. Encoding to UTF-16 and comparing units is the definition, so
    we use it directly rather than reasoning about when the shortcut is safe.
    """
    encoded = s.encode("utf-16-be")
    return tuple(int.from_bytes(encoded[i : i + 2], "big") for i in range(0, len(encoded), 2))


def _write(value: Any, out: list[str], path: tuple[str | int, ...]) -> None:
    if value is None:
        out.append("null")
        return

    # bool before int: bool is a subclass of int in Python, and `True` must serialize as
    # `true`, not as `1`.
    if value is True:
        out.append("true")
        return
    if value is False:
        out.append("false")
        return

    if isinstance(value, int):
        if not (_MIN_EXACT_INT <= value <= _MAX_EXACT_INT):
            raise CanonicalizationError(
                f"integer out of exactly-representable range at {_pointer(path)}: {value}. "
                f"Values beyond +/-2**53 cannot round-trip through a conforming JSON reader; "
                f"express this as a decimal-string Quantity instead (ADR-001 rule 2)."
            )
        out.append(str(value))
        return

    if isinstance(value, float):
        raise CanonicalizationError(
            f"float at {_pointer(path)}: {value!r}. No JSON floating-point number may appear "
            f"in a hashed document (ADR-001 rule 2). A physical quantity is a decimal string "
            f"plus a unit: {{'magnitude': '...', 'unit': '...'}}."
        )

    if isinstance(value, str):
        out.append(_escape_string(value))
        return

    if isinstance(value, dict):
        keys = list(value.keys())
        for k in keys:
            if not isinstance(k, str):
                raise CanonicalizationError(
                    f"non-string object key at {_pointer(path)}: {k!r}. JSON object keys are "
                    f"strings; a non-string key has no canonical ordering."
                )
        keys.sort(key=_utf16_sort_key)
        out.append("{")
        for i, k in enumerate(keys):
            if i:
                out.append(",")
            out.append(_escape_string(k))
            out.append(":")
            _write(value[k], out, path + (k,))
        out.append("}")
        return

    if isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _write(item, out, path + (i,))
        out.append("]")
        return

    raise CanonicalizationError(
        f"unserializable type at {_pointer(path)}: {type(value).__name__}. Only null, bool, "
        f"int, str, list and dict may appear in a hashed document; dump Pydantic models with "
        f"model_dump(mode='json') before canonicalizing."
    )


def canonicalize(value: Any) -> str:
    """Return the JCS canonical JSON text of ``value``.

    No trailing newline, no insignificant whitespace, object keys sorted by UTF-16 code unit.
    Raises :class:`CanonicalizationError` on floats, non-finite values, out-of-range integers,
    non-string keys and unserializable types.
    """
    out: list[str] = []
    _write(value, out, ())
    return "".join(out)


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON encoded UTF-8 -- the exact byte sequence that gets hashed."""
    return canonicalize(value).encode("utf-8")


def content_hash(value: Any) -> str:
    """Content address of ``value``: lowercase 64-character SHA-256 hex, no algorithm prefix.

    The bare form is deliberate (ADR-001 rule 7): a ``sha256:`` prefix appears only in
    human-facing CLI output and in prose, never inside a hashed document, so that a `Ref`
    field and a raw digest field are the same 64 characters everywhere.
    """
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def hash_object(model: Any) -> str:
    """Content address of a Pydantic model, via ``model_dump(mode='json')``.

    Convenience for the common case. Accepts anything exposing ``model_dump``; anything else
    is passed through to :func:`content_hash` unchanged.
    """
    dump = getattr(model, "model_dump", None)
    if dump is None:
        return content_hash(model)
    return content_hash(dump(mode="json"))


def is_content_hash(s: str) -> bool:
    """True when ``s`` is a bare lowercase 64-character hex digest (ADR-001 rule 7)."""
    if len(s) != 64:
        return False
    return all(c in "0123456789abcdef" for c in s)
