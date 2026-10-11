#!/bin/bash

# Enable strict mode
set -euo pipefail

IMAGE_REGISTRY="${DOCKER_REGISTRY}/${IMAGE_NAME}"
BUILD_TAG="$IMAGE_REGISTRY:$IMAGE_TAG"
LATEST_TAG="$IMAGE_REGISTRY:latest"

# Enable Docker BuildKit
export DOCKER_BUILDKIT=1

# Build Docker image
echo "Building Docker image..."
docker build -f "$DOCKERFILE_PATH" --no-cache -t "$BUILD_TAG" ./

# Docker image tag latest

docker tag "$BUILD_TAG" "$LATEST_TAG"

# Push Docker image to ECR
echo "Pushing Docker image to ECR..."

docker push $LATEST_TAG
docker push $BUILD_TAG

echo "Script completed successfully."