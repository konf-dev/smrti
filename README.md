# Smrti v2.0 - Multi-Tier Memory Storage System

**Production-grade memory storage for agentic AI applications**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

## Overview

Smrti is a specialized storage system designed for agentic AI applications that require multi-tier memory management. It provides **5 distinct memory types**, each optimized for different access patterns and retention policies.

### Key Features

- **5 Memory Tiers**: Working, Short-term, Long-term, Episodic, and Semantic
- **Protocol-Based Architecture**: Pluggable storage adapters
- **Multi-Tenant**: Complete namespace isolation from day one
- **Production-Ready**: Comprehensive tests, structured logging, metrics
- **Async-First**: Non-blocking I/O throughout
- **Observable**: Prometheus metrics and structured logs

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Poetry (for local development)

### Running with Docker Compose (Recommended)

```bash
# Start all services (Redis, Qdrant, PostgreSQL, API)
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
docker-compose ps

# View logs
docker-compose logs -f api

# Test the API
curl http://localhost:8000/health
```

See [Docker Setup Guide](docker/README.md) for detailed instructions.

### Local Development Setup

```bash
# Install dependencies
poetry install

# Copy environment configuration
cp .env.example .env

# Edit .env with your settings
# Set connection strings for Redis, Qdrant, and PostgreSQL
vim .env

# Start external services (requires Docker)
# Redis
docker run -d -p 6379:6379 redis:7-alpine

# Qdrant
docker run -d -p 6333:6333 qdrant/qdrant:latest

# PostgreSQL (and initialize schema)
docker run -d -p 5432:5432 \
  -e POSTGRES_USER=smrti \
  -e POSTGRES_PASSWORD=smrti \
  -e POSTGRES_DB=smrti \
  postgres:15-alpine

# Initialize PostgreSQL schema
PGPASSWORD=smrti psql -h localhost -U smrti -d smrti -f src/smrti/storage/init_db.sql

# Run the API server
poetry run smrti

# Or with uvicorn directly
poetry run uvicorn smrti.api.main:app --reload
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         External Clients                         │
└─────────────────────────────────────────────────────────────────┘
                              ▼ HTTP
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer (FastAPI)                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │ Auth Middleware│  │  CORS Middleware│  │ Logging Middle │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Manager                             │
│          (Routes requests to appropriate adapter)                │
└─────────────────────────────────────────────────────────────────┘
         ▼                ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Redis     │  │   Qdrant    │  │  Postgres   │  │  Embedding  │
│  Adapters   │  │   Adapter   │  │  Adapters   │  │   Service   │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

## Memory Types

| Type | Storage | TTL | Use Case | Backend |
|------|---------|-----|----------|---------|
| **WORKING** | In-memory | 5 min | Current context, immediate tasks | Redis |
| **SHORT_TERM** | In-memory | 1 hour | Session summary, recent history | Redis |
| **LONG_TERM** | Persistent | ∞ | Semantic facts, knowledge base | Qdrant |
| **EPISODIC** | Persistent | ∞ | Event timeline, temporal queries | PostgreSQL |
| **SEMANTIC** | Persistent | ∞ | Knowledge graph, entity relationships | PostgreSQL |

## API Examples

All API requests require:
- **Authorization** header: `Bearer <api_key>`
- **X-Namespace** header: Namespace identifier (e.g., `user:123` or `org:acme:project:alpha`)

### Store a Memory

```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "EPISODIC",
    "data": {
      "text": "User completed workout goal",
      "event_type": "goal_completed"
    },
    "metadata": {
      "impact": "high",
      "category": "fitness"
    }
  }'
```

### Retrieve Memories

```bash
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "EPISODIC",
    "query": "workout",
    "limit": 10,
    "filters": {
      "event_type": "goal_completed"
    }
  }'
```

### Delete Memory

```bash
curl -X DELETE "http://localhost:8000/memory/episodic/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123"
```

### Health Check

```bash
# No authentication required for health endpoint
curl http://localhost:8000/health
```

## Development

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run unit tests only (fast)
poetry run pytest -m unit

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test file
poetry run pytest tests/unit/test_config.py -v
```

### Code Quality

```bash
# Format code
poetry run black src tests

# Lint code
poetry run ruff check src tests

# Type check
poetry run mypy src

# Run all quality checks
poetry run black src tests && poetry run ruff check src tests && poetry run mypy src
```

## Configuration

All configuration is via environment variables. See [.env.example](.env.example) for available options.

### Key Configuration Options

- `API_KEYS`: Comma-separated list of valid API keys
- `REDIS_URL`: Redis connection URL
- `QDRANT_URL`: Qdrant server URL  
- `POSTGRES_URL`: PostgreSQL connection URL
- `EMBEDDING_PROVIDER`: `local` or `api`
- `LOG_LEVEL`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

## Monitoring

### Health Checks

```bash
# Liveness (is API responding?)
curl http://localhost:8000/health

# Readiness (are backends connected?)
curl http://localhost:8000/health
```

### Metrics

Prometheus metrics are exposed at `/metrics`:

```bash
curl http://localhost:8000/metrics
```

Key metrics:
- `smrti_http_requests_total` - Total HTTP requests
- `smrti_storage_operations_total` - Storage operations
- `smrti_embedding_generations_total` - Embeddings generated
- `smrti_errors_total` - Error counts

## Project Structure

```
smrti/
├── src/smrti/
│   ├── api/                    # FastAPI application
│   │   ├── routes/             # API endpoints (health, memory)
│   │   ├── auth.py             # API key authentication middleware
│   │   ├── models.py           # Pydantic request/response models
│   │   ├── storage_manager.py  # Coordinates all adapters
│   │   └── main.py             # FastAPI app & lifespan
│   ├── core/                   # Core types, config, logging
│   │   ├── types.py            # MemoryType enum
│   │   ├── config.py           # Pydantic settings
│   │   ├── logging.py          # Structured logging
│   │   ├── metrics.py          # Prometheus metrics
│   │   └── exceptions.py       # Exception hierarchy
│   ├── storage/                # Storage adapters
│   │   ├── protocol.py         # StorageAdapter protocol
│   │   ├── init_db.sql         # PostgreSQL schema
│   │   └── adapters/
│   │       ├── redis_working.py       # WORKING tier (5min TTL)
│   │       ├── redis_short_term.py    # SHORT_TERM tier (1hr TTL)
│   │       ├── qdrant_long_term.py    # LONG_TERM tier (vectors)
│   │       ├── postgres_episodic.py   # EPISODIC tier (events)
│   │       └── postgres_semantic.py   # SEMANTIC tier (knowledge)
│   ├── embedding/              # Embedding generation
│   │   ├── protocol.py         # EmbeddingProvider protocol
│   │   └── local.py            # Local sentence-transformers
│   └── cli.py                  # Command-line interface
├── tests/
│   ├── unit/                   # Fast, isolated tests (88 tests)
│   ├── integration/            # Tests with real databases
│   └── conftest.py             # Pytest configuration
├── docs/                       # Documentation
│   └── prompts/                # Development prompts
├── legacy_code/                # Previous implementation (arch-v1)
└── pyproject.toml              # Project configuration
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and quality checks
5. Commit with clear messages (`git commit -m 'Add amazing feature'`)
6. Push to your branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Standards

- **Type hints**: Required on all functions
- **Docstrings**: Google style on all public interfaces
- **Tests**: 90%+ coverage, test all error paths
- **Async**: Use async/await for all I/O
- **Logging**: Structured logging with structlog
- **Formatting**: black (line length 100)
- **Linting**: ruff (strict mode)
- **Type checking**: mypy (strict mode)

## License

MIT License - see [LICENSE](LICENSE) for details

## Acknowledgments

Built with ❤️ by the Konf Dev team for the agentic AI community.

---

**Status**: v2.0 - Production Ready 🚀
