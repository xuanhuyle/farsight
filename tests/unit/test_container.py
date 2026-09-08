"""The reference image's definition, and the Tier-A predicate. ADR-019.

Everything here runs without a container runtime. The image cannot be built on every machine --
it needs virtualization, and the host this was written on has Intel VT-x disabled in firmware --
so the checks that need a running image live in the `container` CI job, and the checks that are
really about the *definition* live here where they always run.

That split matters: a test suite that skipped all of ADR-019 whenever Docker was missing would go
green on a machine that could not have caught a single one of these mistakes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIB = "/usr/lib/x86_64-linux-gnu"
CONTAINER = REPO / "container"
DOCKERFILE = CONTAINER / "Dockerfile"
DIGESTS = CONTAINER / "digests.json"


def test_the_container_directory_has_what_the_record_names():
    """ADR-019 decision 1 lists the four files by name."""
    for name in ("Dockerfile", "packages.txt", "build.sh", "digests.json"):
        assert (CONTAINER / name).exists(), f"container/{name} is missing (ADR-019 decision 1)"


def test_the_base_image_is_pinned_by_digest_and_never_by_tag():
    """ADR-019 decision 1: "a `FROM` line without an `@sha256:` prefix fails the build job".

    A tag is a moving reference, so an image built from one is not an artifact anyone can obtain
    again -- which makes every Tier-A claim resting on it unfalsifiable rather than merely weak.
    """
    lines = [ln for ln in DOCKERFILE.read_text(encoding="utf-8").splitlines()
             if ln.strip().upper().startswith("FROM")]
    assert lines, "no FROM line"
    for line in lines:
        assert re.match(r"^FROM\s+\S+@sha256:[0-9a-f]{64}\s*$", line.strip()), line


def test_the_pinned_digest_is_the_one_recorded_in_digests_json():
    """The Dockerfile and the manifest have to agree, or the record describes a different image
    from the one that would be built."""
    doc = json.loads(DIGESTS.read_text(encoding="utf-8"))
    recorded = doc["base_image"]["index_digest"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", recorded)
    assert recorded in DOCKERFILE.read_text(encoding="utf-8")


def test_the_interpreter_is_not_the_base_images():
    """ADR-019 decision 1: uv installs and pins the interpreter, "so 'Python 3.12' is one artifact
    identity shared by the Windows development machine and the container rather than an ambient
    property of each".

    Asserted by `python3` being absent from packages.txt: installing Debian's interpreter is
    exactly how that identity would become ambient again.
    """
    packages = [ln.strip() for ln in (CONTAINER / "packages.txt").read_text(encoding="utf-8")
                .splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert packages, "packages.txt lists nothing"
    for forbidden in ("python3", "python3-minimal", "python3.11", "python3-numpy"):
        assert forbidden not in packages, (
            f"{forbidden!r} in packages.txt would make the interpreter an ambient property of the "
            f"base image, which ADR-019 decision 1 exists to prevent"
        )
    assert "uv" in DOCKERFILE.read_text(encoding="utf-8")


def test_the_isa_and_thread_pins_agree_between_the_image_and_the_code():
    """A drift hazard with no other guard.

    The Dockerfile sets these variables and `farsight.engines.environment` declares what it
    expects them to be. Nothing but this test stops the two from diverging -- and if they did, the
    image would pin one dispatch baseline while `numeric_environment` recorded a different
    expectation, so the predicate would describe an environment nobody was running in.
    """
    from farsight.engines.environment import ISA_ENV, THREAD_ENV

    text = DOCKERFILE.read_text(encoding="utf-8")
    for key, value in {**ISA_ENV, **THREAD_ENV}.items():
        # ENV lines may quote the value or not; both spellings must carry the same content.
        pattern = rf"{re.escape(key)}=\"?{re.escape(value)}\"?"
        assert re.search(pattern, text), (
            f"the image does not set {key}={value!r}, but engines/environment.py declares it. "
            f"A pin the code expects and the image does not apply is a predicate describing an "
            f"environment nobody ran in"
        )


def test_pythonhashseed_is_set_in_the_image_and_not_from_python():
    """CPython reads PYTHONHASHSEED only at interpreter startup, so setting it inside a running
    process is a no-op that a readback test would not notice. The image is the right place, and
    this asserts it is there."""
    assert re.search(r"PYTHONHASHSEED=0", DOCKERFILE.read_text(encoding="utf-8"))


def test_unmeasured_fields_are_null_rather_than_plausible():
    """The honest-null rule, mechanized.

    ADR-019 makes `numeric_environment_hash` a MEASURED value: "a predicate we cannot measure is a
    predicate we cannot enforce". No image has been built here, so a 64-hex string in this file
    would be a fabrication that every later Tier-A comparison would inherit. This test fails if
    anyone fills these in without the build that produces them.
    """
    doc = json.loads(DIGESTS.read_text(encoding="utf-8"))
    status = doc["measurement_status"]["state"]

    if status == "unmeasured":
        assert doc["numeric_environment_hash"] is None
        assert doc["build_manifest_hash"] is None
        assert doc["accepted_image_digests"] == []
        assert doc["apt"]["resolved_versions"] is None
        assert doc["measurement_status"]["reason"]
        assert doc["measurement_status"]["blocked_on"]
    else:
        assert status == "measured", status
        assert re.fullmatch(r"[0-9a-f]{64}", doc["numeric_environment_hash"] or "")
        assert doc["accepted_image_digests"], "a measured environment has at least one image"
        assert doc["apt"]["resolved_versions"], "a measured build records what apt resolved"


def test_build_sh_refuses_an_unpinned_base():
    """The check has to live in the build, not only in this suite: CI builds the image by running
    `build.sh`, and a guard that exists only in pytest would not stop a hand build."""
    script = (CONTAINER / "build.sh").read_text(encoding="utf-8")
    assert "@sha256:" in script and "REFUSED" in script


# ------------------------------------------------------------------------------------------
# The Tier-A predicate itself.
# ------------------------------------------------------------------------------------------


def test_a_tier_a_predicate_is_refused_off_linux():
    """ADR-006: "We can never claim bitwise reproducibility across operating systems, so a
    Windows-only customer is permanently a Tier-B customer and must be told so."

    So the module refuses rather than emitting a weaker document shaped like the real one. A
    fingerprint that silently means less on one platform is worse than none, because it would be
    compared against a real one and appear to agree.
    """
    import sys

    from farsight.engines.environment import EnvironmentUnavailable, mapped_libraries

    if sys.platform.startswith("linux"):
        libraries = mapped_libraries()
        assert libraries, "a running Linux process maps at least libc"
        assert all(set(entry) == {"soname", "path", "sha256", "size_bytes"} for entry in libraries)
        assert [e["path"] for e in libraries] == sorted(e["path"] for e in libraries), (
            "mapped_libraries must be sorted, or the same environment hashes differently between "
            "runs depending on loader order"
        )
    else:
        with pytest.raises(EnvironmentUnavailable, match="permanently Tier B"):
            mapped_libraries()


def test_the_residue_about_libm_is_stated_rather_than_implied():
    """ADR-019 argues ISA normalization entirely in OpenBLAS and NumPy terms, and SPICE geometry
    goes through neither -- it is CSPICE arithmetic over glibc's libm. The gap is real, it is not
    closed by anything in this repository, and it is recorded where someone reading the pins will
    see it."""
    from farsight.engines.environment import ISA_RESIDUE

    assert "PARTIALLY MECHANIZED" in ISA_RESIDUE
    assert "libm" in ISA_RESIDUE and "GLIBC_TUNABLES" in ISA_RESIDUE
    # And the Dockerfile names the lever it deliberately does not pull.
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "GLIBC_TUNABLES" in text
    assert not re.search(r"^\s*ENV\s+GLIBC_TUNABLES", text, re.MULTILINE), (
        "GLIBC_TUNABLES is set in the image without the two-CPU measurement that would justify it"
    )


def test_maps_parsing_and_ordering_are_testable_off_linux():
    """The guard that a mutation walked straight through.

    `mapped_libraries` can only run on Linux, so every assertion about how it parses and orders
    sat inside a platform branch that never executed on the machine this was written on -- and a
    mutation deleting the sort survived. Extracting the pure part is what makes the property
    checkable where the code is actually developed.
    """
    from farsight.engines.environment import parse_maps

    sample = "\n".join([
        f"7f0a00000000-7f0a00021000 r--p 00000000 08:01 1310721   {LIB}/libz.so.1",
        f"7f0a00021000-7f0a00030000 r-xp 00021000 08:01 1310721   {LIB}/libz.so.1",
        f"7f0b00000000-7f0b00100000 r-xp 00000000 08:01 1310700   {LIB}/libc.so.6",
        f"7f0c00000000-7f0c00050000 r-xp 00000000 08:01 1310800   {LIB}/libm.so.6",
        "7ffd00000000-7ffd00021000 rw-p 00000000 00:00 0         [stack]",
        "7f0d00000000-7f0d00010000 rw-p 00000000 00:00 0 ",
        "7f0e00000000-7f0e00010000 r--p 00000000 08:01 1311000   /farsight/README.md",
        # A PATH-BEARING mapping with inode 0. Real maps files carry these -- /dev/zero
        # mappings and deleted SysV segments among them -- and they have no file behind them
        # to hash. Included because without it the inode check is never reached: the regex is
        # anchored on a leading "/", so a pathless anonymous line is rejected before the check
        # runs, and a mutation deleting the check survived on a sample that had only those.
        "7f0f00000000-7f0f00010000 rw-s 00000000 00:00 0         /dev/zero.so (deleted)",
    ])
    paths = parse_maps(sample)

    # Sorted -- loader order is a property of the run, not of the environment, and this list goes
    # into a hashed document.
    assert paths == sorted(paths)
    assert paths == [f"{LIB}/libc.so.6", f"{LIB}/libm.so.6", f"{LIB}/libz.so.1"]
    # Deduplicated: one file mapped twice is one library.
    assert len(paths) == len(set(paths))
    # Anonymous mappings (inode 0) have no file to hash, and non-libraries are not libraries.
    assert not any("stack" in p or p.endswith(".md") for p in paths)


def test_the_engine_fingerprint_is_asked_of_the_adapter():
    """`geometry_is_not_an_engine` makes spiceypy importable only under `farsight.engines.spice`,
    so the environment probe must ask the adapter rather than import the toolkit itself. Asserted
    because the alternative -- widening the contract -- would have been the easy fix and the wrong
    one."""
    import ast

    source = (REPO / "src" / "farsight" / "engines" / "environment.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "spiceypy" not in imported, (
        "environment.py imports spiceypy directly; ask farsight.engines.spice.build instead"
    )
    assert (REPO / "src" / "farsight" / "engines" / "spice" / "build.py").exists()


def test_build_sh_is_executable_in_git():
    """The bit Windows does not track, and CI needs.

    `chmod +x` on a Windows checkout changes nothing Git records, so `build.sh` went to the
    repository as mode 100644 and the container job died with `Permission denied` (exit 126)
    before it built anything. Setting it needs `git update-index --chmod=+x`, and nothing but this
    test would notice it being lost again -- least of all a developer on Windows, where the mode
    is invisible.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files", "-s", "container/build.sh"],
            capture_output=True, text=True, cwd=REPO, check=False,
        )
    except FileNotFoundError:
        # The reference image has no git, and correctly so -- it is not in packages.txt, because
        # the image installs what the evidence path needs and nothing else. The index mode is a
        # property of the repository, and the repository is where it can be checked.
        pytest.skip("no git binary (expected inside the reference image)")

    if result.returncode != 0 or not result.stdout.strip():
        pytest.skip("not a git checkout")

    mode = result.stdout.split()[0]
    assert mode == "100755", (
        f"container/build.sh is mode {mode} in the index, not 100755. CI runs it as "
        f"`./container/build.sh` and a non-executable file fails with exit 126 before the build "
        f"starts. Fix with: git update-index --chmod=+x container/build.sh"
    )


def test_the_image_contains_everything_the_suite_reads():
    """The image must hold the repository the tests believe they are running against.

    The CI container job runs the full suite INSIDE the image. An earlier Dockerfile copied a
    hand-listed subset, and five paths the suite reads were not on it -- `.gitattributes`,
    `docs/`, `container/`, `experiments/` and `EXPERT_REVIEW_BACKLOG.md`. Every test touching them
    would have failed in-image for a reason with nothing to do with the container.

    So this computes the paths the suite actually reads and checks none is excluded from the build
    context. Nobody has to remember to update a list.
    """
    import fnmatch

    read_paths: set[str] = set()
    for path in sorted((REPO / "tests" / "unit").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        read_paths.update(re.findall(r'REPO\s*/\s*"([^"]+)"', text))
        if '".gitattributes"' in text:
            read_paths.add(".gitattributes")
    assert read_paths, "found no repo-relative reads; the extraction pattern has drifted"

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^COPY \. \.$", dockerfile, re.MULTILINE), (
        "the Dockerfile no longer copies the whole context, so the include list and the paths the "
        "suite reads can drift apart again"
    )

    ignore_text = (REPO / ".dockerignore").read_text(encoding="utf-8")
    patterns = [ln.strip().rstrip("/") for ln in ignore_text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    excluded = sorted(
        p for p in read_paths
        if any(fnmatch.fnmatch(p, pat) or p == pat or p.startswith(pat + "/") for pat in patterns)
    )
    assert not excluded, (
        f"the suite reads {excluded}, which .dockerignore excludes from the build context. Those "
        f"tests would fail inside the image for a reason unrelated to the container"
    )


def test_every_copy_source_exists_in_the_build_context():
    """A pre-flight the build itself would otherwise be the only way to run.

    `build.sh` passes the REPOSITORY ROOT as the build context, so every `COPY` source is resolved
    from there -- not from `container/`. `COPY packages.txt` therefore named a file that does not
    exist at the root, and the build would have died at that step. It was invisible locally
    because no container runtime exists on the machine that wrote it.

    Checking the sources against the context is cheap, needs no Docker, and is the difference
    between finding this in a second and finding it in a CI round trip.
    """
    import fnmatch

    ignore = [ln.strip().rstrip("/") for ln in (REPO / ".dockerignore").read_text(encoding="utf-8")
              .splitlines() if ln.strip() and not ln.strip().startswith("#")]

    missing: list[str] = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        parts = [p for p in stripped.split()[1:] if not p.startswith("--")]
        if len(parts) < 2:
            continue
        for source in parts[:-1]:            # the last token is the destination
            if source == "." or "*" in source:
                continue                      # whole context, or a glob that may match nothing
            hidden = any(fnmatch.fnmatch(source, pat) or source.startswith(pat + "/")
                         for pat in ignore)
            if not (REPO / source).exists():
                missing.append(source)
            elif hidden:
                missing.append(f"{source} (excluded by .dockerignore)")

    assert not missing, (
        f"COPY sources absent from the build context (the repository root, which is what "
        f"build.sh passes): {missing}"
    )


def test_ci_runs_the_image_with_the_builder_that_built_it():
    """A runner with both podman and docker will happily build into one store and fail to find the
    image in the other.

    That is what happened: `build.sh` prefers podman, GitHub's runner has it, and the CI steps
    afterwards said `docker run` -- so a successful build was followed by "Unable to find image
    ... locally" and exit 125. The build script now exports its choice and the steps use it.
    """
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    container_job = workflow[workflow.index("\n  container:"):]

    assert "FARSIGHT_BUILDER" in container_job, (
        "the container job does not use the builder build.sh selected"
    )
    assert not re.search(r"(?<![\"$])\bdocker run\b", container_job), (
        "the container job hardcodes `docker run` while build.sh auto-detects a builder; on a "
        "runner with both, that reads from the wrong store"
    )
    assert "GITHUB_ENV" in (CONTAINER / "build.sh").read_text(encoding="utf-8"), (
        "build.sh does not export its builder choice, so CI cannot follow it"
    )


def test_the_image_does_not_install_the_quarantined_analysis_extra():
    """ADR-013 quarantines pandas and matplotlib from the truth loop; ADR-019 decision 1 names the
    three extras the image takes -- `spice`, `basilisk`, `dev`.

    `uv sync --all-extras` is one word shorter and installs a fourth, putting the quarantined
    stack into the evidence-producing image: the one environment it must not be in. The
    quarantine is enforced by an import contract, so nothing would have IMPORTED it -- which is
    exactly why this needs its own check. A dependency that is present but unimported is invisible
    until someone imports it.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    sync = [ln for ln in text.splitlines() if "uv sync" in ln]
    assert sync, "the image does not sync a locked environment"
    for line in sync:
        assert "--all-extras" not in line, (
            "`uv sync --all-extras` installs the quarantined `analysis` extra (pandas, "
            "matplotlib) into the evidence-producing image. ADR-019 names three extras: "
            "--extra spice --extra basilisk --extra dev"
        )
        assert "--locked" in line, "the sync must be --locked, or the lock is decorative"
    for extra in ("spice", "basilisk", "dev"):
        assert f"--extra {extra}" in text, f"ADR-019 names the {extra} extra"


def test_the_lock_exists_and_pins_what_the_predicate_depends_on():
    """With no uv.lock, `numeric_environment.uv_lock_sha256` is the empty string and the Tier-A
    predicate does not pin the dependency set -- two images built a month apart could resolve
    different wheels and still produce the same predicate, which is the one thing the predicate
    exists to prevent."""
    import tomllib

    lock = REPO / "uv.lock"
    assert lock.exists(), "no uv.lock: the Tier-A predicate cannot pin the dependency set"

    doc = tomllib.loads(lock.read_text(encoding="utf-8"))
    versions = {p["name"]: p.get("version") for p in doc["package"]}

    # The three that actually reach a number: the toolkit, the array library, and the linter whose
    # version is pinned in pyproject precisely so the enforced rule set cannot move.
    for name in ("spiceypy", "numpy", "ruff"):
        assert versions.get(name), f"{name} is not pinned by the lock"

    root = next(p for p in doc["package"] if p["name"] == "farsight")
    groups = set(root.get("optional-dependencies", {}))
    assert {"spice", "basilisk", "dev"} <= groups, groups
