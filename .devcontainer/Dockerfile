FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install development tools
RUN pip install --no-cache-dir \
    pytest>=7.4.0 \
    pytest-homeassistant-custom-component>=0.13.0 \
    pytest-asyncio>=0.21.0 \
    pytest-cov>=4.1.0 \
    black>=23.0.0 \
    ruff>=0.1.0 \
    mypy>=1.7.0 \
    aiohttp>=3.9.0 \
    gtfs-realtime-bindings>=1.0.0 \
    aiosqlite>=0.19.0

# Set working directory
WORKDIR /workspaces/gtfs-performant

# Copy project files
COPY custom_components/gtfs_performant/ /workspaces/gtfs-performant/custom_components/gtfs_performant/
COPY requirements.txt pyproject.toml README.md LICENSE .devcontainer/ ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e .

# Set up development environment
ENV PYTHONPATH=/workspaces/gtfs-performant:$PYTHONPATH
ENV DEVCONTAINER=true

CMD ["bash"]