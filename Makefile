.PHONY: help install install-dev lint type-check format test test-unit test-integration test-adapters test-benchmarks test-coverage clean build docs serve-docs pre-commit adapter-cert docker-up docker-down

# Default target
help: ## Show this help message
	@echo "Smrti Development Commands"
	@echo "========================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Installation
install: ## Install production dependencies
	pip install -e .

install-dev: ## Install development dependencies
	pip install -e .[dev]
	python -m spacy download en_core_web_sm
	pre-commit install

# Code quality
lint: ## Run ruff linter
	ruff check smrti tests

lint-fix: ## Run ruff linter with fixes
	ruff check smrti tests --fix

type-check: ## Run mypy type checker
	mypy smrti

format: ## Format code with black and isort
	black smrti tests
	isort smrti tests

format-check: ## Check code formatting
	black --check smrti tests
	isort --check-only smrti tests

# Testing
test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit -v

test-integration: ## Run integration tests only
	pytest tests/integration -v

test-adapters: ## Run adapter certification tests
	pytest tests/adapters -v

test-benchmarks: ## Run performance benchmarks
	pytest tests/benchmarks --benchmark-only

test-coverage: ## Run tests with coverage report
	pytest tests/ --cov=smrti --cov-report=html --cov-report=term-missing

test-security: ## Run security tests
	bandit -r smrti
	pytest tests/security -v

# Quality gates (for CI)
quality-gate: lint type-check format-check test-security ## Run all quality checks

# Development utilities
clean: ## Clean build artifacts and caches
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .coverage htmlcov/ .pytest_cache/ .mypy_cache/

build: ## Build package
	python -m build

docs: ## Generate documentation
	mkdocs build

serve-docs: ## Serve documentation locally
	mkdocs serve

pre-commit: ## Run pre-commit hooks on all files
	pre-commit run --all-files

# Adapter certification
adapter-cert: ## Run adapter certification harness
	python -m smrti.testing.certification --all-adapters

adapter-cert-redis: ## Certify Redis adapters only
	python -m smrti.testing.certification --adapter redis

adapter-cert-chroma: ## Certify ChromaDB adapter only
	python -m smrti.testing.certification --adapter chroma

# Docker operations
docker-build: ## Build all Docker images
	docker-compose build --no-cache

docker-up: ## Start development services (Redis, ChromaDB, PostgreSQL, Neo4j)
	docker-compose up -d

docker-dev: ## Start full development environment with tools
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo "✅ Development environment started!"
	@echo ""
	@echo "🌐 Available services:"
	@echo "   Smrti API:        http://localhost:8000"
	@echo "   Grafana:          http://localhost:3000 (admin/smrti_password)"
	@echo "   Prometheus:       http://localhost:9090"
	@echo "   Jaeger:           http://localhost:16686"
	@echo "   Neo4j Browser:    http://localhost:7474 (neo4j/smrti_password)"
	@echo "   Redis Commander:  http://localhost:8081"
	@echo "   pgAdmin:          http://localhost:8082 (admin@smrti.dev/smrti_password)"
	@echo "   Jupyter:          http://localhost:8888 (token: smrti_dev_token)"

docker-down: ## Stop development services
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml down

docker-logs: ## Show development service logs
	docker-compose logs -f

docker-reset: ## Reset development services (remove volumes)
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v
	docker-compose up -d

docker-shell: ## Shell into running Smrti container
	docker-compose exec smrti-app /bin/bash

docker-test: ## Run tests in Docker
	docker-compose run --rm smrti-app pytest -v

vector-test: ## Test vector storage adapter in Docker
	docker-compose run --rm smrti-app python test_vector_adapter.py

docker-clean: ## Remove all Smrti Docker resources
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v --rmi local --remove-orphans

# CLI utilities
cli-help: ## Show smrti CLI help
	smrti --help

config-validate: ## Validate configuration
	smrti config validate

config-dump: ## Dump resolved configuration
	smrti config dump

benchmark-quick: ## Run quick performance benchmark
	smrti benchmark --quick

trace-analyze: ## Analyze traces (requires trace ID)
	@echo "Usage: make trace-analyze TRACE_ID=<trace_id>"
	smrti trace $(TRACE_ID)

# Development environment setup
setup-dev: install-dev docker-up ## Complete development setup
	@echo "Development environment ready!"
	@echo "Run 'make test' to verify installation"

# Release preparation
release-check: quality-gate test adapter-cert ## Full release readiness check
	@echo "Release checks passed!"

# Monitoring and observability
metrics: ## Show current metrics endpoint
	curl -s http://localhost:8000/metrics | head -20

health: ## Check health endpoints
	curl -s http://localhost:8000/health | jq

# Database utilities (requires services running)
db-migrate: ## Run database migrations
	alembic upgrade head

db-reset: ## Reset databases to clean state
	alembic downgrade base
	alembic upgrade head
	
db-seed: ## Seed databases with test data
	python scripts/seed_test_data.py