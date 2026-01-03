.PHONY: help install lint format test clean devcontainer-build devcontainer-up devcontainer-down

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	uv pip install -r requirements.txt
	uv pip install -e .
	uv pip install pytest pytest-homeassistant-custom-component pytest-asyncio pytest-cov black ruff mypy

lint: ## Run linting
	ruff check custom_components/gtfs_performant/
	mypy custom_components/gtfs_performant/

format: ## Format code
	black custom_components/gtfs_performant/
	ruff check --fix custom_components/gtfs_performant/

test: ## Run tests
	pytest custom_components/gtfs_performant/tests/ -v --cov=custom_components/gtfs_performant --cov-report=html

test-quick: ## Run tests without coverage
	pytest custom_components/gtfs_performant/tests/ -v

validate: lint test-quick ## Run all validation (lint + test)

clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.db" -delete
	rm -rf .pytest_cache .coverage htmlcov tests_output

devcontainer-build: ## Build devcontainer
	docker build -f .devcontainer/Dockerfile -t gtfs-performant-dev .

devcontainer-up: ## Start devcontainer
	docker-compose -f .devcontainer/docker-compose.yml up -d

devcontainer-down: ## Stop devcontainer
	docker-compose -f .devcontainer/docker-compose.yml down

devcontainer-shell: ## Open shell in devcontainer
	docker-compose -f .devcontainer/docker-compose.yml exec gtfs-performant-dev bash

hacs-validate: ## Validate HACS metadata
	docker run --rm -v $(PWD):/workspaces/gtfs-performant -w /workspaces/gtfs-performant ghcr.io/hacs/action:main validate

release-check: hacs-validate validate ## Run all checks before release
	@echo "✅ All checks passed! Ready for release."