#!/bin/bash
# Home Assistant development commands

case "$1" in
    "start")
        echo "🏠 Starting Home Assistant with GTFS Performant..."
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml up -d
        echo "✅ Home Assistant started!"
        echo ""
        echo "🌐 Access Home Assistant at: http://localhost:8123"
        echo "📋 Access logs with: ./ha.sh logs"
        echo "🛑 Stop with: ./ha.sh stop"
        ;;
    
    "stop")
        echo "🛑 Stopping Home Assistant..."
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml down
        echo "✅ Home Assistant stopped!"
        ;;
    
    "restart")
        echo "🔄 Restarting Home Assistant..."
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml restart
        echo "✅ Home Assistant restarted!"
        ;;
    
    "logs")
        echo "📋 Showing Home Assistant logs (Ctrl+C to exit)..."
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml logs -f homeassistant
        ;;
    
    "shell")
        echo "🐚 Opening shell in Home Assistant container..."
        docker exec -it gtfs-performant-ha bash
        ;;
    
    "config")
        echo "🔧 Opening Home Assistant configuration..."
        echo "Config is stored in Docker volume: ha-config"
        docker exec -it gtfs-performant-ha cat /config/configuration.yaml || echo "Configuration not found"
        ;;
    
    "update")
        echo "🔄 Updating Home Assistant..."
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml pull
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml up -d
        echo "✅ Home Assistant updated!"
        ;;
    
    "status")
        echo "📊 Home Assistant Status:"
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml ps
        echo ""
        echo "🌐 Home Assistant UI: http://localhost:8123"
        echo "📊 Container stats:"
        docker stats gtfs-performant-ha --no-stream
        ;;
    
    "dev")
        echo "🚀 Starting development environment + Home Assistant..."
        docker-compose -f .devcontainer/docker-compose.yml up -d
        docker-compose -f .devcontainer/docker-compose.home-assistant.yml up -d
        echo "✅ Both environments started!"
        echo ""
        echo "🏠 Home Assistant: http://localhost:8123"
        echo "🐚 Dev container: ./dev.sh shell"
        ;;
    
    *)
        echo "🏠 Home Assistant Development Commands"
        echo ""
        echo "Usage: ./ha.sh [command]"
        echo ""
        echo "Available commands:"
        echo "  start     - Start Home Assistant with GTFS Performant"
        echo "  stop      - Stop Home Assistant"
        echo "  restart   - Restart Home Assistant"
        echo "  logs      - Show Home Assistant logs"
        echo "  shell     - Open shell in Home Assistant container"
        echo "  config    - Show Home Assistant configuration"
        echo "  update    - Update Home Assistant to latest version"
        echo "  status    - Show Home Assistant status"
        echo "  dev       - Start both dev container + Home Assistant"
        echo ""
        echo "Home Assistant UI: http://localhost:8123"
        echo ""
        echo "Quick start:"
        echo "  ./ha.sh start     # Start Home Assistant"
        echo "  ./ha.sh dev       # Start full dev environment"
        ;;
esac