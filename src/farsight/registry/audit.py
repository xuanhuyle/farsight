"""The append-only, hash-chained audit log. ADR-012 decision 4.

Every mutating CLI action writes one row here, from v0. ADR-011 owns the SQLite file; ADR-012 owns
this table, its columns and its chaining rule, and they are reproduced rather than redefined.

**Tamper-evident, not tamper-proof, and the difference is stated because it is load-bearing.**
An operator with write access can recompute the whole chain. So this will never support an
insider-threat claim without external anchoring, which ADR-012 defers along with the signing
story. What the chain does buy is that a row cannot be altered or removed *quietly* -- every
later row's hash depends on it.

**`detail_json` is a data-leak boundary, not a free-form notes field.** ADR-012's separation rule:
logs record paths, hashes and declared labels, never a parameter magnitude and never a channel
value. That matters because the log lives under ``$FARSIGHT_HOME`` while mission data lives only
under operator-declared ``data_roots``, and a magnitude copied into a log is mission data that has
escaped that boundary. :func:`validate_detail` enforces the part of this that is mechanizable and
:data:`DETAIL_RESIDUE` states the part that is not.

**Timestamps are here and never in an evidence hash.** ``ts_utc`` is real wall-clock time, which
is exactly why the audit log is not package content (ADR-006, ADR-001 rule 4).
"""

from __future__ import annotations

import getpass
import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from farsight.hashing.canonical import canonical_bytes, is_content_hash
from farsight.schemas.common import DECIMAL_RE, validate_segment
from farsight.schemas.errors import FarSightError

__all__ = [
    "AUDIT_ACTIONS",
    "DETAIL_RESIDUE",
    "GENESIS_PREV_HASH",
    "UNKNOWN_ACTOR",
    "AuditError",
    "AuditLog",
    "row_hash",
    "validate_detail",
]

# ADR-012 decision 4. The enumeration is CLOSED: a new operator workflow that needs a row this
# list cannot express is ADR-012's own stated revisit trigger, not a reason to append quietly.
# `farsight geometry` writes `run` -- ADR-024 says so explicitly, because `run` is the only
# admissible member, and its detail_json carries the design path, which is what tells an auditor
# a week-1 geometry probe from a campaign.
AUDIT_ACTIONS: tuple[str, ...] = (
    "freeze", "plan", "run", "resume", "fetch", "package",
    "verify", "replay", "alias_set", "collapse_authorize",
)

GENESIS_PREV_HASH = "0" * 64

DETAIL_RESIDUE = (
    "PARTIALLY MECHANIZED: validate_detail refuses a value that IS a magnitude. It cannot refuse "
    "a magnitude embedded inside a longer string -- a path named `thrust_412.5N.json` passes, and "
    "so would a free-text note carrying a number. The mechanized half is the shape of a value; "
    "the residue is what a caller chooses to put in one."
)


class AuditError(FarSightError, ValueError):
    """A row cannot be written, or a chain does not verify."""


def validate_detail(detail: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse anything in ``detail_json`` that is not path-shaped, hash-shaped, or a label.

    ADR-012's content rule, as far as a shape check reaches. Numbers are refused by type AND by
    spelling, because ``{"margin": 3.2}`` and ``{"margin": "3.2"}`` leak the same value and only
    the first is caught by a type check.
    """
    clean: dict[str, Any] = {}
    for key, value in detail.items():
        try:
            validate_segment(key, what="detail_json key")
        except ValueError as exc:
            # Re-raised as an AuditError so the whole boundary has one exception type: a caller
            # guarding it with `except AuditError` would otherwise miss a malformed key.
            raise AuditError(str(exc)) from exc

        if isinstance(value, bool) or value is None:
            clean[key] = value
            continue
        if isinstance(value, (int, float)):
            raise AuditError(
                f"detail_json[{key!r}] is the number {value!r}. ADR-012 confines the log to "
                f"paths, hashes and declared labels: a magnitude here is mission data that has "
                f"left the operator-declared data_roots and landed in $FARSIGHT_HOME"
            )
        if not isinstance(value, str):
            raise AuditError(
                f"detail_json[{key!r}] is a {type(value).__name__}. Only strings, booleans and "
                f"null are admissible; a nested structure is a place for a magnitude to hide"
            )
        if DECIMAL_RE.match(value):
            raise AuditError(
                f"detail_json[{key!r}] is {value!r}, which is a magnitude spelled as a string. "
                f"Quoting a number does not make it a label (ADR-012 decision 4)"
            )
        clean[key] = value
    return clean


UNKNOWN_ACTOR = "unknown"


def _os_user() -> str:
    """The OS user, or ``"unknown"`` when the environment does not say.

    `actor` is the OS user and nothing else: no email, no installation id, no hostname. ADR-012
    makes that a structural property rather than a privacy setting.

    Guarded because ``getpass.getuser()`` is not total. With no ``USERNAME``/``USER``/``LOGNAME``
    in the environment it falls back to ``import pwd``, which does not exist on Windows -- so a
    stripped environment (a container, a service account, a CI runner, a spawned worker that
    inherited a minimal env) raises ``ModuleNotFoundError`` from inside an audit write. Failing a
    whole command because a cosmetic field could not be filled is the wrong trade: an audit row
    that says `unknown` is more useful than an audit row that was never written, and the chain's
    integrity does not depend on this value.
    """
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - see docstring
        return UNKNOWN_ACTOR


def row_hash(row: Mapping[str, Any]) -> str:
    """``sha256(JCS of the row minus row_hash)``. ADR-012 decision 4.

    ``detail_json`` is hashed as the string actually stored, not as a re-parsed object, so the
    hash covers the bytes in the column rather than a reconstruction of them.
    """
    payload = {k: v for k, v in row.items() if k != "row_hash"}
    return __import__("hashlib").sha256(canonical_bytes(payload)).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc      TEXT NOT NULL,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  object_hash TEXT,
  detail_json TEXT NOT NULL,
  prev_hash   TEXT NOT NULL,
  row_hash    TEXT NOT NULL
);
"""


class AuditLog:
    """The chain, over one SQLite file.

    Single-writer by design. ADR-011 decision 5 keeps workers out of SQLite entirely -- they
    return records over the pool boundary and the parent folds them in -- which is what gives this
    file a crash model with one writer rather than a locking story.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def append(
        self,
        action: str,
        detail: Mapping[str, Any],
        *,
        object_hash: str | None = None,
        ts_utc: str,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Append one row and return it.

        ``ts_utc`` is a required parameter rather than a call to the clock. The reason is
        testability of the chain itself: a row's hash covers its timestamp, so a self-stamping
        writer produces a chain no test can state an expected value for, and the one property
        worth testing here is that the chain links.
        """
        if action not in AUDIT_ACTIONS:
            raise AuditError(
                f"action {action!r} is not in ADR-012's closed enumeration {AUDIT_ACTIONS}. "
                f"A workflow needing a row this list cannot express is that record's stated "
                f"revisit trigger, not a reason to add a member here"
            )
        if object_hash is not None and not is_content_hash(object_hash):
            raise AuditError(
                f"object_hash {object_hash!r} is not a bare 64-hex content address. The column "
                f"holds the address of the affected object, never its content (ADR-012)"
            )

        clean = validate_detail(detail)
        who = actor if actor is not None else _os_user()

        with self._connect() as conn:
            prev = conn.execute(
                "SELECT row_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev[0] if prev else GENESIS_PREV_HASH
            next_seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM audit_log"
            ).fetchone()[0] + 1

            row = {
                "seq": next_seq,
                "ts_utc": ts_utc,
                "actor": who,
                "action": action,
                "object_hash": object_hash,
                "detail_json": json.dumps(clean, sort_keys=True, separators=(",", ":")),
                "prev_hash": prev_hash,
            }
            row["row_hash"] = row_hash(row)
            conn.execute(
                "INSERT INTO audit_log (seq, ts_utc, actor, action, object_hash, detail_json,"
                " prev_hash, row_hash) VALUES (:seq,:ts_utc,:actor,:action,:object_hash,"
                ":detail_json,:prev_hash,:row_hash)",
                row,
            )
        return row

    def rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY seq")]

    def verify_chain(self) -> None:
        """Recompute every row hash and every link, or raise naming the first bad row.

        AT-3 requires a nonzero exit *naming the exact item*, so this reports which row broke and
        how, rather than that something somewhere is wrong.
        """
        expected_prev = GENESIS_PREV_HASH
        for i, row in enumerate(self.rows()):
            if row["prev_hash"] != expected_prev:
                raise AuditError(
                    f"audit row seq={row['seq']} carries prev_hash {row['prev_hash'][:12]}... but "
                    f"the previous row hashes to {expected_prev[:12]}.... The chain is broken at "
                    f"this row, which means a row before it was altered or removed"
                )
            recomputed = row_hash(row)
            if recomputed != row["row_hash"]:
                raise AuditError(
                    f"audit row seq={row['seq']} ({row['action']}) does not hash to its stored "
                    f"row_hash: stored {row['row_hash'][:12]}..., recomputed "
                    f"{recomputed[:12]}.... This row's own contents were altered"
                )
            if i == 0 and row["prev_hash"] != GENESIS_PREV_HASH:
                raise AuditError("the first audit row must carry 64 zeros as prev_hash")
            expected_prev = row["row_hash"]


def chain_of(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """The row hashes in order. Convenience for tests and for `verify --audit`."""
    return [r["row_hash"] for r in rows]
