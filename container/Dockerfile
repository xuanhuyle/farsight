# The FarSight reference image. ADR-019 decision 1.
#
# This is the EVIDENCE-PRODUCING environment. It must never be confused with the zero-extras
# auditor install of ADR-013 -- that is a `pip install farsight` with no engine extras, and it
# exists to prove `verify` needs no engines. Different artifact, different purpose, different
# property. This image, by contrast, carries every extra, so that every Tier-A claim the MVP makes
# is executable inside one image.
#
# THE BASE IS PINNED BY DIGEST AND NEVER BY TAG. `container/build.sh` refuses a `FROM` line with
# no `@sha256:`, because a tag is a moving reference and an image built from one is not an
# artifact anyone can obtain again. The digest below is `debian:bookworm-slim` as it stood on
# 2026-09-07; `container/digests.json` records it alongside the linux/amd64 manifest it resolves
# to, and ADR-019 decision 5 gives base-image changes a named owner and a monthly refresh job
# rather than letting them arrive silently.
FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171

# APT IS PINNED TO A SNAPSHOT, WHICH IS HOW THE PACKAGE VERSIONS BECOME DETERMINISTIC.
#
# ADR-019 decision 1 asks for "every apt package with an exact =version pin, one per line". A
# snapshot timestamp reaches the same property by a stronger route: it fixes the entire archive
# the resolver sees, so transitive dependencies are pinned too -- which a hand-written list of
# top-level `=version` pins does not do. `packages.txt` still enumerates what is installed, and
# `build.sh` records the exact versions apt actually resolved into `digests.json`, so the built
# image reports its own bill of materials rather than trusting this file to have been kept true.
# The divergence from the record's literal wording is DEV-22.
ARG DEBIAN_SNAPSHOT=20260901T000000Z
RUN set -eux; \
    printf 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/%s bookworm main\n' "$DEBIAN_SNAPSHOT" > /etc/apt/sources.list; \
    printf 'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/%s bookworm-security main\n' "$DEBIAN_SNAPSHOT" >> /etc/apt/sources.list; \
    printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99snapshot

COPY packages.txt /tmp/packages.txt
RUN set -eux; \
    apt-get update; \
    grep -vE '^\s*(#|$)' /tmp/packages.txt | xargs apt-get install -y --no-install-recommends; \
    rm -rf /var/lib/apt/lists/*; \
    rm -f /tmp/packages.txt

# THE INTERPRETER IS NOT THE BASE IMAGE'S. ADR-019: "uv installs and pins it exactly as ADR-014
# decided, so 'Python 3.12' is one artifact identity shared by the Windows development machine and
# the container rather than an ambient property of each." That is why `python3` is absent from
# packages.txt: taking Debian's interpreter would make the version an ambient property of whichever
# base digest is current.
ARG UV_VERSION=0.5.11
ARG PYTHON_VERSION=3.12.8
ENV UV_INSTALL_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_NO_MODIFY_PATH=1
RUN set -eux; \
    curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" -o /tmp/uv-install.sh; \
    sh /tmp/uv-install.sh; \
    rm -f /tmp/uv-install.sh; \
    uv python install "${PYTHON_VERSION}"

WORKDIR /farsight
COPY pyproject.toml uv.lock* README.md ./
COPY src ./src
COPY tests ./tests
COPY kernels ./kernels
COPY scripts ./scripts

# `--locked` and not `--frozen`: the lock file must already satisfy the manifest, and a build that
# would have had to re-resolve fails instead of quietly resolving something else.
RUN set -eux; \
    if [ -f uv.lock ]; then uv sync --locked --all-extras; \
    else uv venv && uv pip install -e ".[dev,spice]"; fi

# ADR-002 owns the thread pins and ADR-019 owns the ISA pins. They are set HERE, in the image, and
# not from inside Python, because both are read at load time by libraries that have already
# started: assigning them to `os.environ` in a running interpreter is a no-op for anything that
# read them at import. This is the same failure shape as PYTHONHASHSEED, which CPython reads only
# at interpreter startup.
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    OPENBLAS_CORETYPE=Haswell \
    NPY_DISABLE_CPU_FEATURES="AVX512F AVX512CD AVX512_SKX AVX512_CLX AVX512_CNL AVX512_ICL" \
    PYTHONHASHSEED=0 \
    TZ=UTC \
    LC_ALL=C \
    LANG=C \
    SOURCE_DATE_EPOCH=1756684800

# A LEVER THIS IMAGE DOES NOT PULL, AND WHY IT IS WRITTEN DOWN RATHER THAN LEFT OUT.
#
# ADR-019 argues ISA normalization entirely in OpenBLAS and NumPy terms. SPICE geometry is CSPICE
# arithmetic over glibc's libm, which resolves sin/cos/atan2/exp/pow to FMA/AVX2/AVX-512 variants
# through IFUNC at load time -- so neither variable above constrains the code path the weeks 1-2
# exit gate is actually about. `GLIBC_TUNABLES` is the candidate lever:
#
#     ENV GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX2_Usable,-AVX512F_Usable
#
# It is NOT set, because setting it would be an unmeasured claim. Its effect has to be verified on
# two physically different CPU generations before this image can assert it changes anything, and
# no such measurement exists. `numeric_environment_hash` records the libm actually mapped, so a
# different libm is at least VISIBLE as a different predicate; that is weaker than making two CPUs
# agree, and the difference is the point. Tracked as DEV-23.

ENTRYPOINT ["uv", "run", "--"]
CMD ["python", "-c", "import farsight; print(farsight.__file__)"]
