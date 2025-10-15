#!/bin/bash

# Optimized Docker build script
set -e

echo "🚀 Starting optimized Docker build..."

# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1

# Build with optimizations
docker build \
    --platform linux/amd64 \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    --cache-from finops-ai:latest \
    -t finops-ai:latest \
    -f Dockerfile \
    .

echo "✅ Build completed successfully!"

# Optional: Show image size
echo "📊 Image size:"
docker images finops-ai:latest --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"