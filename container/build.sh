#!/usr/bin/env bash
# Deterministic build entrypoint. ADR-019 decision 1: used by CI and by hand, so that "how the
# image was built" is not folk knowledge held by whoever built it last.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
IMAGE="${FARSIGHT_IMAGE:-farsight-reference}"
TAG="${FARSIGHT_TAG:-local}"

# A tag is a moving reference, so an image built from one is not an artifact anyone can obtain
# again. This is the check that makes ADR-019's "base pinned by digest" a fact about the build
# rather than a sentence in a record.
if ! grep -qE '^FROM[[:space:]]+[^[:space:]]+@sha256:[0-9a-f]{64}' "$HERE/Dockerfile"; then
  echo "REFUSED: container/Dockerfile has a FROM line with no @sha256: digest." >&2
  echo "A tag-pinned base makes the image unreproducible (ADR-019 decision 1)." >&2
  exit 1
fi

# podman and docker are both acceptable: the OCI image content is what matters, and neither
# builder's identity enters `numeric_environment_hash`, which is measured inside the running
# container rather than asserted by whatever built it.
BUILDER="${FARSIGHT_BUILDER:-}"
if [ -z "$BUILDER" ]; then
  if command -v podman >/dev/null 2>&1; then BUILDER=podman
  elif command -v docker >/dev/null 2>&1; then BUILDER=docker
  else echo "REFUSED: neither podman nor docker is available." >&2; exit 1; fi
fi
echo "builder: $BUILDER ($($BUILDER --version 2>/dev/null | head -1))"

# Export the CHOICE, so that whatever runs the image afterwards runs the one that was just built.
# A GitHub runner has both podman and docker; this script prefers podman, and a caller that then
# said `docker run` looked in the other store and got "Unable to find image ... locally" after a
# perfectly successful build.
if [ -n "${GITHUB_ENV:-}" ]; then
  echo "FARSIGHT_BUILDER=$BUILDER" >> "$GITHUB_ENV"
fi

# SOURCE_DATE_EPOCH makes timestamps in the image deterministic where the builder honours it.
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1756684800}"

# shellcheck disable=SC2086 -- FARSIGHT_BUILD_ARGS is a deliberate word-split (e.g. --no-cache),
# which is how the stability check forces a real re-resolve instead of reusing the install layer.
"$BUILDER" build ${FARSIGHT_BUILD_ARGS:-} \
  --file "$HERE/Dockerfile" \
  --tag "$IMAGE:$TAG" \
  ${SOURCE_DATE_EPOCH:+--build-arg SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH"} \
  "$REPO"

echo
echo "--- measuring the Tier-A predicate from inside the image (ADR-019 decision 2) ---"

# Written to a FILE rather than printed alongside the hash. An earlier version sent the document
# to stdout and the hash to stderr from one command; CI merges the two streams and interleaved
# them mid-line, so the document in the log could not be parsed -- which defeats the point of
# emitting a document anyone can inspect.
OUT="${FARSIGHT_FINGERPRINT:-fingerprint.json}"
"$BUILDER" run --rm "$IMAGE:$TAG" python -c \
  'import json; from farsight.engines.environment import numeric_environment; print(json.dumps(numeric_environment(), indent=2, sort_keys=True))' \
  > "$OUT"

HASH="$("$BUILDER" run --rm "$IMAGE:$TAG" python -c \
  'from farsight.engines.environment import numeric_environment_hash; print(numeric_environment_hash())')"

# The bill of materials apt actually resolved. DEV-22 promised this file records it, and until
# now it did not -- a note describing behaviour the code did not have.
APT_OUT="${FARSIGHT_APT_VERSIONS:-apt_versions.txt}"
"$BUILDER" run --rm "$IMAGE:$TAG" \
  sh -c 'dpkg-query -W -f="\${binary:Package}=\${Version}\n"' > "$APT_OUT" 2>/dev/null || true

echo "numeric_environment_hash: $HASH"
echo "document written to: $OUT"
echo
echo "It is MEASURED, never declared: a predicate we cannot measure is one we cannot enforce."
echo "Record it in container/digests.json only once two INDEPENDENT builds agree on it."

if [ -n "${GITHUB_ENV:-}" ]; then
  echo "FARSIGHT_PREDICATE=$HASH" >> "$GITHUB_ENV"
fi
