"""The append-only hash-chained audit log. ADR-012 decision 4.

ADR-012 names ``test_audit_chain`` and states what the log is and is not: tamper-*evident*, never
tamper-*proof*. An operator with write access can recompute the whole chain, so these tests assert
detection of an alteration that did not recompute -- which is the property the design actually
has -- and never that alteration is prevented.
"""

from __future__ import annotations

import itertools
import sqlite3

import pytest

from farsight.registry.audit import (
    AUDIT_ACTIONS,
    GENESIS_PREV_HASH,
    AuditError,
    AuditLog,
    row_hash,
    validate_detail,
)

TS = "2026-09-07T12:00:00+00:00"


def _log(tmp_path) -> AuditLog:
    return AuditLog(tmp_path / "farsight.sqlite")


def test_the_genesis_row_carries_sixty_four_zeros(tmp_path):
    log = _log(tmp_path)
    row = log.append("plan", {"design_path": "designs/a.json"}, ts_utc=TS, actor="t")
    assert row["prev_hash"] == GENESIS_PREV_HASH
    assert len(GENESIS_PREV_HASH) == 64


def test_each_row_links_to_the_one_before_it(tmp_path):
    log = _log(tmp_path)
    rows = [
        log.append("plan", {"design_path": "a.json"}, ts_utc=TS, actor="t"),
        log.append("run", {"design_path": "a.json"}, ts_utc=TS, actor="t"),
        log.append("package", {"out_dir": "pkg"}, ts_utc=TS, actor="t"),
    ]
    for earlier, later in itertools.pairwise(rows):
        assert later["prev_hash"] == earlier["row_hash"]
    log.verify_chain()


def test_altering_a_row_is_detected_and_the_failure_names_the_row(tmp_path):
    """AT-3 requires a nonzero exit *naming the exact item*, so the message must identify which
    row broke rather than reporting that something somewhere is wrong."""
    path = tmp_path / "farsight.sqlite"
    log = AuditLog(path)
    log.append("run", {"design_path": "a.json"}, ts_utc=TS, actor="t")
    log.append("run", {"design_path": "b.json"}, ts_utc=TS, actor="t")
    log.verify_chain()

    conn = sqlite3.connect(path)
    conn.execute("UPDATE audit_log SET detail_json='{\"design_path\":\"c.json\"}' WHERE seq=1")
    conn.commit()
    conn.close()

    with pytest.raises(AuditError) as exc:
        log.verify_chain()
    assert "seq=1" in str(exc.value)


def test_removing_a_row_breaks_the_chain(tmp_path):
    path = tmp_path / "farsight.sqlite"
    log = AuditLog(path)
    for i in range(3):
        log.append("run", {"design_path": f"d{i}.json"}, ts_utc=TS, actor="t")

    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM audit_log WHERE seq=2")
    conn.commit()
    conn.close()

    with pytest.raises(AuditError, match="chain is broken"):
        log.verify_chain()


def test_a_recomputed_chain_verifies_which_is_why_this_is_evidence_and_not_proof(tmp_path):
    """The honest negative result, asserted rather than described in prose.

    ADR-012 says the log is tamper-evident and not tamper-proof, and this is what that means
    mechanically: an operator who edits a row *and recomputes every hash after it* produces a
    chain that verifies. Nothing here catches that, and nothing claims to. Anchoring it externally
    is deferred with the signing story.
    """
    path = tmp_path / "farsight.sqlite"
    log = AuditLog(path)
    log.append("run", {"design_path": "a.json"}, ts_utc=TS, actor="t")
    log.append("run", {"design_path": "b.json"}, ts_utc=TS, actor="t")

    rows = log.rows()
    rows[0]["detail_json"] = '{"design_path":"forged.json"}'
    rows[0]["row_hash"] = row_hash(rows[0])
    rows[1]["prev_hash"] = rows[0]["row_hash"]
    rows[1]["row_hash"] = row_hash(rows[1])

    conn = sqlite3.connect(path)
    for r in rows:
        conn.execute(
            "UPDATE audit_log SET detail_json=?, prev_hash=?, row_hash=? WHERE seq=?",
            (r["detail_json"], r["prev_hash"], r["row_hash"], r["seq"]),
        )
    conn.commit()
    conn.close()

    log.verify_chain()  # passes: the forgery is complete and internally consistent
    assert log.rows()[0]["detail_json"] == '{"design_path":"forged.json"}'


def test_the_action_enumeration_is_closed(tmp_path):
    """ADR-012 owns the enumeration and it is closed. `geometry` is deliberately NOT a member:
    ADR-024 says the geometry verb writes `run` and distinguishes itself in detail_json."""
    log = _log(tmp_path)
    assert "geometry" not in AUDIT_ACTIONS
    assert set(AUDIT_ACTIONS) == {
        "freeze", "plan", "run", "resume", "fetch", "package",
        "verify", "replay", "alias_set", "collapse_authorize",
    }
    with pytest.raises(AuditError, match="closed enumeration"):
        log.append("geometry", {"design_path": "a.json"}, ts_utc=TS, actor="t")


def test_detail_json_refuses_a_magnitude_however_it_is_spelled():
    """ADR-012's separation rule is a data boundary: logs carry paths, hashes and declared labels,
    never a parameter magnitude and never a channel value. The log lives under $FARSIGHT_HOME
    while mission data lives only under operator-declared data_roots, so a magnitude here is
    mission data that has left its boundary."""
    validate_detail({"design_path": "designs/psyche.json", "verb": "geometry"})
    validate_detail({"shadow_units": False, "note": None})

    for bad in ({"margin": 3.2}, {"margin": 42}, {"margin": "3.2"}, {"margin": "-1.5e-3"}):
        with pytest.raises(AuditError):
            validate_detail(bad)

    # A nested structure is a place for a magnitude to hide.
    for bad in ({"v": [1, 2]}, {"v": {"a": 1}}):
        with pytest.raises(AuditError, match="Only strings"):
            validate_detail(bad)

    with pytest.raises(AuditError, match="segment grammar"):
        validate_detail({"Design Path": "a.json"})


def test_the_actor_is_the_os_user_and_carries_nothing_else(tmp_path):
    """ADR-012: OS user only -- no email, no installation id. A structural property rather than a
    privacy setting, which is what makes the no-telemetry claim checkable."""
    log = _log(tmp_path)
    row = log.append("run", {"design_path": "a.json"}, ts_utc=TS)
    assert "@" not in row["actor"]
    assert row["actor"]


def test_an_object_hash_is_an_address_and_never_content(tmp_path):
    log = _log(tmp_path)
    log.append("run", {"design_path": "a.json"}, object_hash="a" * 64, ts_utc=TS, actor="t")
    for bad in ("not-a-hash", "A" * 64, "a" * 63):
        with pytest.raises(AuditError, match="64-hex content address"):
            log.append("run", {"design_path": "a.json"}, object_hash=bad, ts_utc=TS, actor="t")


def test_the_timestamp_is_supplied_rather_than_read_from_the_clock(tmp_path):
    """A row's hash covers its timestamp, so a self-stamping writer produces a chain no test can
    state an expected value for. Requiring the caller to pass one is what makes the chain
    testable -- and the timestamp still never enters an evidence hash (ADR-006)."""
    import inspect

    signature = inspect.signature(AuditLog.append)
    assert signature.parameters["ts_utc"].default is inspect.Parameter.empty
    assert signature.parameters["ts_utc"].kind is inspect.Parameter.KEYWORD_ONLY


def test_the_actor_field_survives_an_environment_that_names_no_user(tmp_path, monkeypatch):
    """`getpass.getuser()` is not total.

    With no USERNAME/USER/LOGNAME set it falls back to `import pwd`, which does not exist on
    Windows -- so a container, a service account or a spawned worker with a minimal environment
    would raise from inside an audit write. Found by a subprocess test that stripped the
    environment to prove hash stability across a process boundary; the audit write crashed before
    the hashes could be compared.
    """
    import getpass

    from farsight.registry.audit import UNKNOWN_ACTOR

    def _no_user():
        raise ModuleNotFoundError("No module named 'pwd'")

    monkeypatch.setattr(getpass, "getuser", _no_user)
    log = AuditLog(tmp_path / "farsight.sqlite")
    row = log.append("run", {"design_path": "a.json"}, ts_utc=TS)
    assert row["actor"] == UNKNOWN_ACTOR
    log.verify_chain()
