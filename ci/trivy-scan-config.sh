#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

mkdir -p trivy .trivycache

echo "Trivy Configuration Scan (IaC)..."
trivy --version || true

# Cache cleanup
trivy clean --scan-cache

echo "Generate Trivy Config scan json Report..."
trivy config \
  --severity HIGH,CRITICAL \
  --format json -o "$CI_PROJECT_DIR/trivy/${CI_PROJECT_NAME}_config-scan_${CI_COMMIT_REF_SLUG}_${CI_COMMIT_SHORT_SHA}.json" \
  "$CI_PROJECT_DIR"

echo "Generate Trivy Config scan sarif Report..."
trivy config \
  --severity HIGH,CRITICAL \
  --format sarif -o "$CI_PROJECT_DIR/trivy/${CI_PROJECT_NAME}_config-scan_${CI_COMMIT_REF_SLUG}_${CI_COMMIT_SHORT_SHA}.sarif" \
  "$CI_PROJECT_DIR"

echo "Scanning Infrastructure Configurations..."
trivy config \
  --severity HIGH,CRITICAL --exit-code 1 \
  "$CI_PROJECT_DIR"
