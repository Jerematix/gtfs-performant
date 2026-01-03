#!/bin/bash
# Quick commands for devcontainer

case "$1" in
    "start")
        echo "🚀 Starting devcontainer..."
        docker-compose -f .devcontainer/docker-compose.yml up -d
        echo "✅ Container started!"
        echo "📝 Use './dev.sh shell' to enter the container"
        ;;
    
    "stop")
        echo "🛑 Stopping devcontainer..."
        docker-compose -f .devcontainer/docker-compose.yml down
        echo "✅ Container stopped!"
        ;;
    
    "shell")
        echo "🐚 Opening shell in devcontainer..."
        docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev bash
        ;;
    
    "test")
        echo "🧪 Running tests..."
        docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev pytest custom_components/gtfs_performant/tests/ -v || echo "⚠️  Tests not found or failed"
        ;;
    
    "format")
        echo "🎨 Formatting code..."
        docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev black custom_components/gtfs_performant/
        ;;
    
    "lint")
        echo "🔍 Linting code..."
        docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev ruff check custom_components/gtfs_performant/
        ;;
    
    "validate")
        echo "✅ Running all validation..."
        docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev bash -c "make validate"
        ;;
    
    "rebuild")
        echo "🔨 Rebuilding devcontainer..."
        docker-compose -f .devcontainer/docker-compose.yml up --build -d
        echo "✅ Container rebuilt!"
        ;;
    
    "logs")
        echo "📋 Showing container logs..."
        docker-compose -f .devcontainer/docker-compose.yml logs -f
        ;;
    
    *)
        echo "🚀 GTFS Performant Devcontainer Commands"
        echo ""
        echo "Usage: ./dev.sh [command]"
        echo ""
        echo "Available commands:"
        echo "  start     - Start the devcontainer"
        echo "  stop      - Stop the devcontainer" 
        echo "  shell     - Open a shell in the container"
        echo "  test      - Run tests"
        echo "  format    - Format code with black"
        echo "  lint      - Run linting with ruff"
        echo "  validate  - Run all validation (lint + test)"
        echo "  rebuild   - Rebuild the container"
        echo "  logs      - Show container logs"
        echo ""
        echo "Example:"
        echo "  ./dev.sh start    # Start container"
        echo "  ./dev.sh shell    # Enter container"
        echo "  ./dev.sh test     # Run tests"
        ;;
esac