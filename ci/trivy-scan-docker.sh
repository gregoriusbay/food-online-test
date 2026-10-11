#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

mkdir -p trivy .trivycache

# Full image reference (avoid overwriting IMAGE_NAME variable)
IMAGE_REGISTRY="${DOCKER_REGISTRY}/${IMAGE_NAME}"
BUILD_TAG="$IMAGE_REGISTRY:$IMAGE_TAG"
LATEST_TAG="$IMAGE_REGISTRY:latest"

echo "Trivy image scan for: $BUILD_TAG"
trivy --version || true

# cache cleanup is needed when scanning images with the same tags, it does not remove the database
trivy clean --scan-cache

echo "Generate Trivy Docker scan json Report..."
trivy image --ignore-unfixed \
  --scanners vuln \
  --cache-dir .trivycache/ \
  --severity HIGH,CRITICAL \
  --format json -o "$CI_PROJECT_DIR/trivy/${CI_PROJECT_NAME}_${IMAGE_TAG}_vulnerability.json" \
  "$BUILD_TAG"

echo "Generate Trivy Docker scan sarif Report..."
trivy image --ignore-unfixed \
  --scanners vuln \
  --cache-dir .trivycache/ \
  --severity HIGH,CRITICAL \
  --format sarif -o "$CI_PROJECT_DIR/trivy/${CI_PROJECT_NAME}_${IMAGE_TAG}_vulnerability.sarif" \
  "$BUILD_TAG"

echo "Generate SBOM Report (CycloneDX JSON)..."
trivy image \
  --format cyclonedx \
  --cache-dir .trivycache/ \
  -o "$CI_PROJECT_DIR/trivy/${CI_PROJECT_NAME}_${IMAGE_TAG}_sbom.cdx.json" \
  "$BUILD_TAG"

echo "Generate BOV Report (CycloneDX JSON)..."
trivy image \
  --format cyclonedx \
  --scanners vuln \
  --severity HIGH,CRITICAL \
  --cache-dir .trivycache/ \
  -o "$CI_PROJECT_DIR/trivy/${CI_PROJECT_NAME}_${IMAGE_TAG}_bov.cdx.json" \
  "$BUILD_TAG"

echo "Scanning Docker Image..."
trivy image --ignore-unfixed \
  --scanners vuln \
  --cache-dir .trivycache/ \
  --severity HIGH,CRITICAL --exit-code 1 \
  "$BUILD_TAG"