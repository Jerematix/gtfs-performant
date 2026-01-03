#!/bin/bash
set -e

echo "🚀 Setting up GTFS Performant development environment..."

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
uv pip install -r requirements.txt
uv pip install -e .

# Install development dependencies
echo "📦 Installing development dependencies..."
uv pip install \
    pytest>=7.4.0 \
    pytest-homeassistant-custom-component>=0.13.0 \
    pytest-asyncio>=0.21.0 \
    pytest-cov>=4.1.0 \
    black>=23.0.0 \
    ruff>=0.1.0 \
    mypy>=1.7.0

# Create necessary directories
echo "📁 Creating project directories..."
mkdir -p custom_components/gtfs_performant/tests
mkdir -p .github/workflows
mkdir -p tests_output

# Set up pre-commit hooks (if pre-commit is installed)
if command -v pre-commit &> /dev/null; then
    echo "🪝 Setting up pre-commit hooks..."
    pre-commit install
fi

# Create test configuration
echo "📋 Creating test configuration..."
cat > setup.cfg << 'EOF'
[tool:pytest]
testpaths = custom_components/gtfs_performant/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --cov=custom_components/gtfs_performant
    --cov-report=html
    --cov-report=term-missing
    --asyncio-mode=auto
EOF

# Create development configuration
echo "📋 Creating development configuration..."
cat > configuration.yaml << 'EOF'
# Home Assistant Development Configuration
homeassistant:
  name: Home
  latitude: 52.52
  longitude: 13.405
  elevation: 34
  unit_system: metric
  time_zone: Europe/Berlin

# Enable dev tools
logger:
  default: info
  logs:
    custom_components.gtfs_performant: debug

# Enable debug mode
debug: true

# Enable frontend
frontend:
  themes: !include_dir_merge_named themes

# Example GTFS Performant configuration (commented out)
# sensor:
#   - platform: gtfs_performant
#     static_url: "https://download.gtfs.de/germany/rv_free/latest.zip"
#     realtime_url: "https://realtime.gtfs.de/realtime-free.pb"
#     name: "German Transit"

EOF

echo "✅ Development environment setup complete!"
echo ""
echo "🔧 Available commands:"
echo "  - pytest                    : Run tests"
echo "  - black .                   : Format code"
echo "  - ruff check .              : Lint code"
echo "  - mypy custom_components/   : Type check"
echo ""
echo "🚀 You can now start developing!"