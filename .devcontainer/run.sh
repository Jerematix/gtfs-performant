#!/bin/bash
# Script to run devcontainer without VS Code

set -e

echo "🚀 Starting GTFS Performant Development Container..."

# Build and run container
docker-compose -f .devcontainer/docker-compose.yml up -d

# Attach to container
echo "✅ Container started! Attaching shell..."
docker-compose -f .devcontainer/docker-compose.yml exec -T gtfs-performant-dev bash || docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev bash

# Or you can run commands directly:
# docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev pytest