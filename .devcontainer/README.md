# GTFS Performant Development Container

This directory contains the configuration for the VS Code development container, providing a complete development environment for GTFS Performant.

## 🚀 Quick Start

### Prerequisites

- Git
- Docker
- VS Code
- [Remote - Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension

### Getting Started

1. **Clone the repository**
   ```bash
   git clone https://github.com/jerematix/gtfs-performant.git
   cd gtfs-performant
   ```

2. **Open in VS Code**
   ```bash
   code .
   ```

3. **Reopen in Container**
   - When prompted, click "Reopen in Container"
   - Or use Command Palette: `Ctrl+Shift+P` → "Remote-Containers: Reopen in Container"

4. **Wait for setup**
   - The container will build automatically (first time takes a few minutes)
   - Post-create scripts will install dependencies
   - VS Code will reload when ready

## 🛠️ Development Tools Included

### Python Environment
- Python 3.12
- All project dependencies installed
- Development tools (pytest, black, ruff, mypy)

### VS Code Extensions
- Python IntelliSense, linting, and formatting
- GitHub Copilot (if available)
- GitLens for Git integration
- YAML and JSON validation

### Pre-configured Settings
- Auto-formatting with Black on save
- Pylint and MyPy type checking
- Test discovery and running
- Home Assistant configuration validation

## 📋 Available Commands

Inside the devcontainer, you can use:

```bash
# Run tests
make test

# Format code
make format

# Run linting
make lint

# All validation
make validate

# Clean generated files
make clean
```

## 🔧 Troubleshooting

### Container won't start
- Ensure Docker is running: `docker ps`
- Check container logs: `docker-compose -f .devcontainer/docker-compose.yml logs`

### Extensions not installing
- Rebuild container: Command Palette → "Remote-Containers: Rebuild Container"

### Tests failing
- Check Python path: `echo $PYTHONPATH`
- Reinstall dependencies: `make install`

## 📚 Additional Resources

- [Home Assistant Development](https://developers.home-assistant.io/)
- [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)
- [HACS Contribution Guide](https://hacs.xyz/docs/contributing/)