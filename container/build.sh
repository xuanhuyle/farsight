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

# SOURCE_DATE_EPOCH makes timestamps in the image deterministic where the builder honours it.
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1756684800}"

"$BUILDER" build \
  --file "$HERE/Dockerfile" \
  --tag "$IMAGE:$TAG" \
  ${SOURCE_DATE_EPOCH:+--build-arg SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH"} \
  "$REPO"

echo
echo "--- measuring the Tier-A predicate from inside the image (ADR-019 decision 2) ---"
"$BUILDER" run --rm "$IMAGE:$TAG" python -c \
  'import json,sys; from farsight.engines.environment import numeric_environment, numeric_environment_hash
d = numeric_environment()
print(json.dumps(d, indent=2, sort_keys=True))
print("numeric_environment_hash:", numeric_environment_hash(d), file=sys.stderr)'

echo
echo "Record the hash above in container/digests.json under numeric_environment_hash."
echo "It is MEASURED, never declared: a predicate we cannot measure is one we cannot enforce."
