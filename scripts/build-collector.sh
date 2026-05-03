#!/usr/bin/env bash
# Build the custom OpenTelemetry Collector using the official ocb Docker image.
# Requires Docker. Produces: dist/otel-custom/otel-custom
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p dist

IMG="${OTEL_OCB_IMAGE:-otel/opentelemetry-collector-builder:0.129.0}"

# Cross-compile so the binary runs on the host OS (Docker image is Linux; default target was linux/amd64).
if [ -z "${GOOS:-}" ]; then
  case "$(uname -s)" in
    Darwin) GOOS=darwin ;;
    *) GOOS=linux ;;
  esac
fi
if [ -z "${GOARCH:-}" ]; then
  GOARCH="$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
fi

echo "Using image: $IMG"
echo "Target: GOOS=$GOOS GOARCH=$GOARCH (set GOOS/GOARCH to override)"

docker run --rm \
  -e CGO_ENABLED=0 \
  -e GOOS="$GOOS" \
  -e GOARCH="$GOARCH" \
  -v "$ROOT:/build" \
  -w /build \
  "$IMG" \
  --config=/build/collector/builder-config.yaml

echo "Binary: $ROOT/dist/otel-custom/otel-custom"
