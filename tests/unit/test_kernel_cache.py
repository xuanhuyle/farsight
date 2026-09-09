"""The kernel cache and the acquisition path (ADR-016, ADR-012).

Everything here runs on synthetic bytes. The transport is injected, so the only untested line in
the whole path is the socket itself — which is the right split, because the interesting failures
are "bytes did not match what was declared" and "a cached file was replaced afterwards", and
neither of those needs a network to reproduce.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from farsight.acquire.fetch import MAX_FETCH_BYTES, AcquisitionError, fetch_kernel
from farsight.cli import exit_codes
from farsight.cli.main import app
from farsight.registry.kernel_cache import KernelCache, KernelCacheError, sha256_bytes, sha256_file
from farsight.registry.paths import HOME_ENV_VAR, farsight_home, kernel_cache_root
from farsight.schemas.knowledge import DataArtifact

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "farsight"

# A stand-in for a leapsecond kernel: small, but real bytes with a real digest.
KERNEL_BYTES = b"KPL/LSK\nDELTET/DELTA_T_A = 32.184\nBEGINTEXT\nsynthetic\nENDTEXT\n"
KERNEL_SHA = hashlib.sha256(KERNEL_BYTES).hexdigest()
URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls"

runner = CliRunner()


def opener_returning(data: bytes):
    """A transport that yields fixed bytes. The seam that keeps this suite offline."""
    def _open(_url: str) -> bytes:
        return data
    return _open


# --------------------------------------------------------------------------------------
# The cache: keyed only by content
# --------------------------------------------------------------------------------------


def test_the_path_carries_no_name_and_no_extension(tmp_path):
    """ADR-016 decision 5: no extension and no logical name in the path, so nothing can resolve a
    kernel by anything but its content. A file called naif0012.tls would invite exactly the
    ambient-kernel-directory habit the record rejects."""
    cache = KernelCache(tmp_path)
    path = cache.path_for(KERNEL_SHA)
    assert path == tmp_path / KERNEL_SHA[:2] / KERNEL_SHA
    assert path.suffix == ""
    assert "naif" not in str(path)


def test_bytes_that_do_not_match_never_enter_the_cache(tmp_path):
    """Verified ON INSERT. An unchecked insert would file bytes under an address that does not
    describe them, and every later read would inherit the lie."""
    cache = KernelCache(tmp_path)
    with pytest.raises(KernelCacheError, match="not to the"):
        cache.put(b"different bytes", KERNEL_SHA)
    assert not cache.has(KERNEL_SHA)
    assert list(tmp_path.rglob("*")) == [] or not any(p.is_file() for p in tmp_path.rglob("*"))


def test_a_replaced_cache_file_is_caught_on_read(tmp_path):
    """ADR-016 Enforcement 6: a cache file whose bytes do not hash to its own path name is
    rejected on read, naming the path. The path IS the assertion."""
    cache = KernelCache(tmp_path)
    path = cache.put(KERNEL_BYTES, KERNEL_SHA)
    path.write_bytes(b"tampered")

    with pytest.raises(KernelCacheError, match="its own path"):
        cache.get_path(KERNEL_SHA)


def test_the_verification_memo_is_per_process_and_keyed_on_path_and_digest(tmp_path):
    """Re-hashing a multi-hundred-megabyte SPK on every furnish is where this rule gets
    expensive, so a verified pair is remembered for the life of the process -- and forgotten
    between processes, which is what keeps the check honest."""
    cache = KernelCache(tmp_path)
    cache.put(KERNEL_BYTES, KERNEL_SHA)

    assert cache.verified_count() == 0
    cache.get_path(KERNEL_SHA)
    assert cache.verified_count() == 1
    cache.get_path(KERNEL_SHA)
    assert cache.verified_count() == 1, "a second read must not re-hash"

    # A fresh cache object stands in for a fresh process: nothing carries over.
    assert KernelCache(tmp_path).verified_count() == 0


def test_the_memo_does_not_survive_into_a_new_process(tmp_path):
    """ADR-016 names the residue rather than hiding it: another process could modify a cache file
    mid-campaign, and nothing catches that until the next process starts. This asserts the second
    half of that sentence -- the next process DOES catch it."""
    cache = KernelCache(tmp_path)
    path = cache.put(KERNEL_BYTES, KERNEL_SHA)
    cache.get_path(KERNEL_SHA)  # memoized in this "process"

    path.write_bytes(b"tampered mid-campaign")
    assert cache.get_path(KERNEL_SHA)  # the memo means this one does NOT catch it

    with pytest.raises(KernelCacheError, match="its own path"):
        KernelCache(tmp_path).get_path(KERNEL_SHA)  # a fresh process does


def test_inserting_the_same_bytes_twice_is_a_no_op(tmp_path):
    cache = KernelCache(tmp_path)
    first = cache.put(KERNEL_BYTES, KERNEL_SHA)
    second = cache.put(KERNEL_BYTES, KERNEL_SHA)
    assert first == second
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 1


def test_an_address_must_be_a_bare_digest(tmp_path):
    cache = KernelCache(tmp_path)
    for bad in ("naif0012.tls", "sha256:" + "a" * 64, "A" * 64, ""):
        with pytest.raises(KernelCacheError, match="not a bare 64-hex digest"):
            cache.path_for(bad)


def test_a_missing_kernel_is_an_error_not_a_silent_empty(tmp_path):
    with pytest.raises(KernelCacheError, match="no cached bytes"):
        KernelCache(tmp_path).get_path("f" * 64)


def test_streaming_and_in_memory_hashing_agree(tmp_path):
    """`sha256_file` streams so a large kernel is never loaded whole; it must still agree with
    the in-memory path exactly, or insert and read would disagree about the same bytes."""
    target = tmp_path / "blob"
    big = KERNEL_BYTES * 50_000
    target.write_bytes(big)
    assert sha256_file(target) == sha256_bytes(big)


# --------------------------------------------------------------------------------------
# Acquisition
# --------------------------------------------------------------------------------------


def test_a_fetch_verifies_against_the_declared_digest(tmp_path):
    """The digest is a PRECONDITION, not a description. Hashing whatever arrived and recording
    that would make the record a log line rather than a check."""
    cache = KernelCache(tmp_path)
    artifact, path = fetch_kernel(
        URL, KERNEL_SHA, cache,
        license_note="NAIF: public domain.",
        opener=opener_returning(KERNEL_BYTES),
    )
    assert isinstance(artifact, DataArtifact)
    assert artifact.sha256 == KERNEL_SHA
    assert artifact.size_bytes == len(KERNEL_BYTES)
    assert artifact.url == URL
    assert path.read_bytes() == KERNEL_BYTES


def test_wrong_bytes_are_refused_and_nothing_is_cached(tmp_path):
    cache = KernelCache(tmp_path)
    with pytest.raises(AcquisitionError, match="not the"):
        fetch_kernel(
            URL, KERNEL_SHA, cache,
            license_note="x",
            opener=opener_returning(b"a different file entirely"),
        )
    assert not cache.has(KERNEL_SHA)


def test_a_transport_failure_is_an_acquisition_error(tmp_path):
    def failing(_url: str) -> bytes:
        raise ConnectionResetError("connection reset")

    with pytest.raises(AcquisitionError, match="transport failed"):
        fetch_kernel(URL, KERNEL_SHA, KernelCache(tmp_path), license_note="x", opener=failing)


def test_an_oversized_response_is_refused(tmp_path):
    """The cache is never garbage-collected, so an unbounded fetch spends disk permanently."""
    def flood(_url: str) -> bytes:
        return b"\0" * (MAX_FETCH_BYTES + 1)

    with pytest.raises(AcquisitionError, match="ceiling"):
        fetch_kernel(URL, KERNEL_SHA, KernelCache(tmp_path), license_note="x", opener=flood)


def test_plaintext_transport_is_refused_by_the_real_opener():
    """The digest check would catch alteration in flight; the honest fix is not to offer the
    channel. Asserted against the real opener, which is otherwise untested here."""
    from farsight.acquire.fetch import default_opener

    with pytest.raises(AcquisitionError, match="not https"):
        default_opener("http://example.invalid/kernel.bsp")
    with pytest.raises(AcquisitionError, match="not https"):
        default_opener("ftp://example.invalid/kernel.bsp")


def test_the_artifact_records_no_timestamp(tmp_path):
    """DEV-12. Two fetches of identical bytes must produce one address, or the dedup the cache
    exists for is gone."""
    cache = KernelCache(tmp_path)
    first, _ = fetch_kernel(URL, KERNEL_SHA, cache, license_note="n",
                            opener=opener_returning(KERNEL_BYTES))
    second, _ = fetch_kernel(URL, KERNEL_SHA, cache, license_note="n",
                             opener=opener_returning(KERNEL_BYTES))
    assert first == second
    assert "fetched_at_utc" not in first.model_dump()


# --------------------------------------------------------------------------------------
# The CLI verb
# --------------------------------------------------------------------------------------


def test_the_fetch_verb_exists_and_reports_failure_with_exit_code_30(tmp_path):
    """ADR-024: 30 is acquisition_failure -- bytes did not match --expect-sha256, or transport
    failed. A generic nonzero would leave a script unable to tell this from tamper."""
    result = runner.invoke(app, [
        "fetch", "kernel", "--url", "http://example.invalid/x.tls",
        "--expect-sha256", KERNEL_SHA, "--into", str(tmp_path),
    ])
    assert result.exit_code == exit_codes.ACQUISITION_FAILURE


def test_the_digest_flag_is_required():
    """There is no flag to skip it. A fetch without a declared digest records whatever arrived."""
    result = runner.invoke(app, ["fetch", "kernel", "--url", URL])
    assert result.exit_code != exit_codes.OK


# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------


def test_the_home_override_beats_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path / "from_env"))
    assert farsight_home() == tmp_path / "from_env"
    assert farsight_home(tmp_path / "explicit") == tmp_path / "explicit"


def test_resolving_a_path_creates_nothing(monkeypatch, tmp_path):
    """A resolver that makes a tree on import turns a typo in an environment variable into a
    scattering of empty folders."""
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path / "nowhere"))
    assert kernel_cache_root() == tmp_path / "nowhere" / "kernels"
    assert not (tmp_path / "nowhere").exists()


# --------------------------------------------------------------------------------------
# ADR-016 Enforcement 6: only one code path writes to the cache
# --------------------------------------------------------------------------------------


def test_only_the_cache_module_writes_to_the_cache():
    """ADR-016 decision 5: only `farsight.acquire`, via `farsight fetch`, writes to the cache;
    every other package treats it as read-only. A second writer means bytes could enter without
    having been verified against a declared hash.

    Enforced structurally as well as by this lint: `KernelCache.put` is the only function that
    calls `write_atomic` with a cache path, and `farsight.acquire` reaches it through that method.
    """
    writers: list[str] = []
    for path in python_sources(SRC):
        rel = path.relative_to(SRC.parent.parent).as_posix().replace("src/farsight/", "")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "write_atomic"):
                writers.append(rel)
    # The sanctioned writers, each named with what it owns. This list is the point of the lint:
    # a fourth entry appearing without a reason is a second path by which bytes reach disk.
    #
    #   registry/objects.py       the content-addressed object store
    #   registry/kernel_cache.py  the kernel cache -- the one ADR-016 decision 5 is about
    #   registry/channels.py      channel .npy files and channels_manifest.json (ADR-011)
    #
    # `registry/audit.py` is deliberately absent and is NOT an oversight: SQLite owns its own
    # durability there (WAL plus `synchronous=FULL`), which is what ADR-011 chose a database for.
    # It writes no file through this helper, so it cannot appear in this list.
    sanctioned = {"registry/objects.py", "registry/kernel_cache.py", "registry/channels.py"}
    assert set(writers) <= sanctioned, (
        f"write_atomic called outside the sanctioned stores: {sorted(set(writers) - sanctioned)}"
    )
    # ADR-016 decision 5 is specifically about the CACHE, so the added writer must not touch it.
    channels_src = (SRC / "registry" / "channels.py").read_text(encoding="utf-8")
    assert "kernel_cache" not in channels_src and "cache_root" not in channels_src, (
        "registry/channels.py references the kernel cache; only KernelCache.put may write there"
    )


def _imports_acquire(node: ast.AST) -> bool:
    """True when this node imports anything under `farsight.acquire`, either spelling."""
    if isinstance(node, ast.ImportFrom):
        return (node.module or "").startswith("farsight.acquire")
    if isinstance(node, ast.Import):
        return any(a.name.startswith("farsight.acquire") for a in node.names)
    return False


def test_acquire_is_imported_only_by_the_cli_fetch_module():
    """ADR-012: `farsight.acquire` is the only package permitted a networking library, and the
    CLI's fetch subcommand is its only importer. That chain is what makes 'zero network calls in
    the truth loop' structural rather than a promise."""
    importers: list[str] = []
    for path in python_sources(SRC):
        rel = path.relative_to(SRC.parent.parent).as_posix().replace("src/farsight/", "")
        if rel.startswith("acquire/"):
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if _imports_acquire(node):
                importers.append(rel)
    assert set(importers) <= {"cli/fetch.py"}, (
        f"unexpected importers of acquire: {sorted(set(importers))}"
    )


# --------------------------------------------------------------------------------------
# The pinned-kernel manifest (offline: it is a file in the repo, not a fetch)
# --------------------------------------------------------------------------------------

import json as _json
import re

from ._guards import python_sources

MANIFEST = REPO / "kernels" / "pinned_kernels.json"


def test_the_pinned_manifest_is_well_formed():
    """`farsight fetch kernel` requires --expect-sha256 and has no flag to skip it. This file is
    where that value comes from, so a malformed row is a fetch nobody can perform correctly."""
    doc = _json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert doc["kernels"], "an empty manifest would pass every other check vacuously"
    for row in doc["kernels"]:
        for field in ("logical_name", "kernel_type", "url", "sha256", "size_bytes",
                      "acquired_on", "acquisition", "license_note"):
            assert field in row, f"{row.get('logical_name')} is missing {field}"
        assert len(row["sha256"]) == 64 and row["sha256"].islower()
        int(row["sha256"], 16)
        assert row["size_bytes"] > 0
        assert row["url"].startswith("https://")


ACQUISITION_MODES = {
    # NAIF publishes no checksums for the generic kernels, so a file taken from there and nowhere
    # else was verified against nothing on its first fetch. Genuinely weaker than the rest of the
    # system provides, and a row that did not say so would read as verified provenance (DEV-16).
    "trust_on_first_use",
    # A PDS4 bundle ships a checksum.tab, so these bytes were checked against a digest FarSight
    # did not produce. MD5, so not collision-resistant -- but INDEPENDENT, which TOFU never was.
    "publisher_checksum_verified",
}


def test_every_pin_declares_how_it_was_acquired():
    """A pin has to say what its digest is worth, because the two modes are not equivalent.

    Checked against a CANARY row rather than by looping over clean data. Every real row currently
    carries a valid mode, so a plain `assert row["acquisition"] in ...` cannot fail and deleting
    it would change no test outcome -- a guard that passes vacuously is a guard nobody is keeping.
    The canary makes the check itself observable: it must catch exactly the bad row and no real
    one.
    """
    doc = _json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = list(doc["kernels"])
    canary = dict(rows[0], logical_name="__canary__", acquisition="verified")

    unrecognised = [r["logical_name"] for r in [*rows, canary]
                    if r["acquisition"] not in ACQUISITION_MODES]
    assert unrecognised == ["__canary__"], (
        f"expected only the canary to be rejected, got {unrecognised}. A real pin with an "
        f"unrecognised acquisition mode does not say what its digest is worth"
    )


def test_a_publisher_verified_pin_carries_the_digest_and_where_it_came_from():
    """`publisher_checksum_verified` is a stronger claim than `trust_on_first_use`, so it has to
    be checkable: the digest and the manifest URL are both recorded, and anyone can re-run the
    comparison. A mode that asserted verification without saying against what would be worse than
    the honest weaker label."""
    doc = _json.loads(MANIFEST.read_text(encoding="utf-8"))
    for row in doc["kernels"]:
        if row["acquisition"] != "publisher_checksum_verified":
            continue
        name = row["logical_name"]
        assert re.fullmatch(r"[0-9a-f]{32}", row.get("publisher_md5", "")), name
        assert row.get("publisher_checksum_url", "").startswith("https://"), name


def test_no_pin_points_at_a_mutable_alias():
    """`latest_leapseconds.tls` is a symlink NAIF updates in place, so the same URL returns
    different bytes over time -- exactly what content addressing exists to prevent."""
    doc = _json.loads(MANIFEST.read_text(encoding="utf-8"))
    for row in doc["kernels"]:
        assert "latest_" not in row["url"], f"{row['url']} is a mutable alias, not a pinned file"


def test_no_pin_takes_the_windows_line_ending_variant():
    """NAIF ships naif0012.tls.pc: identical physics, CRLF line endings, 5409 bytes instead of
    5257 -- a different content address. Fetching it on Windows would give a design frozen there
    a different kernel_set_hash from one frozen on Linux, and ADR-006's cross-platform golden
    would fail for a reason that has nothing to do with physics."""
    doc = _json.loads(MANIFEST.read_text(encoding="utf-8"))
    for row in doc["kernels"]:
        assert not row["url"].endswith(".pc"), f"{row['url']} is the CRLF variant"


def test_the_pinned_lsk_digest_is_the_one_this_repo_fetched():
    """A regression pin. If this value ever changes, the question is what NAIF reissued or what
    went wrong -- never what this test says."""
    doc = _json.loads(MANIFEST.read_text(encoding="utf-8"))
    lsk = [r for r in doc["kernels"] if r["kernel_type"] == "lsk"]
    assert len(lsk) == 1, (
        "ADR-016 decision 6: exactly one LSK, so 'the pinned LSK' denotes one file"
    )
    assert lsk[0]["sha256"] == (
        "678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b"
    )
    assert lsk[0]["size_bytes"] == 5257


# ------------------------------------------------------------------------------------------
# Publisher digests. DEV-16 recorded that a first acquisition could verify nothing, because our
# own address is not knowable until the bytes exist. A publisher's manifest breaks that circle.
# ------------------------------------------------------------------------------------------


def test_a_publisher_md5_verifies_a_first_acquisition(tmp_path):
    """The case trust-on-first-use could not cover.

    PDS4 bundles publish a `checksum.tab` of MD5s, so a file being fetched for the FIRST time --
    whose SHA-256 nobody has stated yet, because it is computed from the very bytes in question --
    can still be checked against something the downloader did not produce.
    """
    import hashlib

    payload = b"KPL/LSK\nfictional bytes for a first acquisition\n"
    md5 = hashlib.md5(payload).hexdigest()

    artifact, path = fetch_kernel(
        URL, None, KernelCache(tmp_path), license_note="test",
        expect_md5=md5, opener=lambda _u: payload,
    )
    assert path.read_bytes() == payload
    # Our address is still SHA-256, computed from the bytes the publisher attested to.
    assert artifact.sha256 == hashlib.sha256(payload).hexdigest()


def test_bytes_that_do_not_match_the_published_digest_are_refused(tmp_path):
    import hashlib

    payload = b"the bytes that actually arrived"
    wrong_md5 = hashlib.md5(b"the bytes the manifest describes").hexdigest()

    with pytest.raises(AcquisitionError, match="the publisher listed"):
        fetch_kernel(URL, None, KernelCache(tmp_path), license_note="test",
                     expect_md5=wrong_md5, opener=lambda _u: payload)


def test_both_digests_are_checked_when_both_are_given(tmp_path):
    """A pinned file fetched again is checked against BOTH: our address and the publisher's."""
    import hashlib

    payload = b"pinned and published"
    good_md5 = hashlib.md5(payload).hexdigest()
    good_sha = hashlib.sha256(payload).hexdigest()

    fetch_kernel(URL, good_sha, KernelCache(tmp_path), license_note="t",
                 expect_md5=good_md5, opener=lambda _u: payload)

    # A wrong SHA-256 is still refused even when the publisher's MD5 matches.
    with pytest.raises(AcquisitionError, match="not the"):
        fetch_kernel(URL, "f" * 64, KernelCache(tmp_path / "b"), license_note="t",
                     expect_md5=good_md5, opener=lambda _u: payload)


def test_a_fetch_with_no_declared_digest_is_refused(tmp_path):
    """The precondition survives the new parameter.

    Allowing both to be None would turn this function into one that hashes whatever turned up and
    files the result as provenance -- which is the distinction the module docstring draws between
    provenance and a log line.
    """
    with pytest.raises(AcquisitionError, match="digest declared before the bytes arrive"):
        fetch_kernel(URL, None, KernelCache(tmp_path), license_note="t",
                     opener=lambda _u: b"anything")
