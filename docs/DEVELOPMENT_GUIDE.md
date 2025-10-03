# Smrti Development Guide

## Quick Start with Docker

### 1. Start Development Environment

```bash
# Start all services (Redis, PostgreSQL, Neo4j, ChromaDB, monitoring tools)
make docker-dev

# Check service status
make docker-ps

# View logs
make docker-logs
```

### 2. Access Development Tools

Once the environment is running, access these services:

| Service | URL | Purpose |
|---------|-----|---------|
| **Redis Insight** | http://localhost:8001 | Redis database GUI |
| **pgAdmin** | http://localhost:5050 | PostgreSQL admin (admin@admin.com / admin) |
| **Neo4j Browser** | http://localhost:7474 | Neo4j graph database (neo4j / password) |
| **Grafana** | http://localhost:3000 | Metrics dashboards (admin / admin) |
| **Prometheus** | http://localhost:9090 | Metrics collection |
| **Jaeger** | http://localhost:16686 | Distributed tracing |
| **Jupyter** | http://localhost:8888 | Interactive notebooks |

### 3. Run Tests

```bash
# Run all tests
make docker-test

# Run specific test file
docker-compose exec smrti-app pytest tests/test_shortterm_memory.py -v

# Run tests with coverage
docker-compose exec smrti-app pytest --cov=smrti tests/
```

### 4. Development Workflow

#### Hot Reloading
The development environment mounts your source code as a volume, so changes are immediately reflected:

```bash
# Edit files locally - changes are live in container
vim smrti/tiers/shortterm.py

# Test changes immediately
docker-compose exec smrti-app pytest tests/test_shortterm_memory.py
```

#### Interactive Development

```bash
# Open Python shell in container
docker-compose exec smrti-app python

# Open IPython shell
docker-compose exec smrti-app ipython

# Access Jupyter notebooks
# Navigate to http://localhost:8888
```

## Current Progress

### ✅ Completed Components

1. **Storage Adapters**
   - Redis adapter with async operations, batch processing, TTL
   - Memory adapter (in-memory fallback) with TTL simulation
   - Vector storage adapter (ChromaDB) with embeddings and similarity search

2. **Memory Tiers**
   - Working Memory tier with LRU/LFU eviction, access tracking
   - **Short-term Memory tier** with consolidation and promotion logic

3. **Infrastructure**
   - Complete Docker containerization for all dependencies
   - Development and production configurations
   - Observability stack (Prometheus, Grafana, Jaeger)

### 🚧 In Progress

- Testing Short-term Memory tier implementation
- Validation of consolidation strategies

### 📋 Next Steps

1. **Long-term Memory Tier** (Priority 1)
   - Vector storage integration for semantic search
   - Archival capabilities for durable storage
   - Fact consolidation from Short-term Memory
   
2. **Context Assembly System** (Priority 2)
   - Token budgeting and allocation
   - Section prioritization
   - Reduction strategies
   
3. **Hybrid Retrieval Engine** (Priority 3)
   - Vector similarity search
   - Lexical search (BM25)
   - Temporal filtering
   - Fusion scoring

## Development Commands

### Docker Management

```bash
# Start services
make docker-dev              # Start with dev tools
make docker-up               # Start production stack only

# Stop services
make docker-down             # Stop all services
make docker-stop             # Stop without removing containers

# Restart services
make docker-restart          # Restart all services

# View status
make docker-ps               # List running containers
make docker-logs             # View logs (all services)
make docker-logs-smrti       # View Smrti app logs only

# Cleanup
make docker-clean            # Remove containers and volumes
make docker-prune            # Deep clean (removes everything)
```

### Testing Commands

```bash
# Run all tests
make docker-test

# Run specific test categories
docker-compose exec smrti-app pytest -m unit
docker-compose exec smrti-app pytest -m integration
docker-compose exec smrti-app pytest -m benchmark

# Run with detailed output
docker-compose exec smrti-app pytest -vv --tb=long

# Run with coverage report
docker-compose exec smrti-app pytest --cov=smrti --cov-report=html
# Open htmlcov/index.html to view coverage
```

### Database Management

#### Redis
```bash
# Connect to Redis CLI
docker-compose exec redis redis-cli

# Monitor Redis operations
docker-compose exec redis redis-cli MONITOR

# Check memory usage
docker-compose exec redis redis-cli INFO memory
```

#### PostgreSQL
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U smrti -d smrti

# Run migrations
docker-compose exec smrti-app alembic upgrade head

# Create new migration
docker-compose exec smrti-app alembic revision --autogenerate -m "description"
```

#### Neo4j
```bash
# Cypher shell
docker-compose exec neo4j cypher-shell -u neo4j -p password

# Example query
MATCH (n) RETURN count(n);
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │  Query   │  │ Context  │  │   Consolidation      │  │
│  │  Engine  │  │ Assembly │  │      Engine          │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                    Memory Tiers                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Working  │─▶│  Short-  │─▶│    Long-term         │  │
│  │  Memory  │  │   term   │  │     Memory           │  │
│  │ (active) │  │ (6 hours)│  │   (permanent)        │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│                  Storage Adapters                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │  Redis   │  │  Vector  │  │    PostgreSQL        │  │
│  │ (cache)  │  │(ChromaDB)│  │   (episodic)         │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Code Organization

```
smrti/
├── adapters/
│   ├── storage/
│   │   ├── redis.py              # Redis adapter ✅
│   │   ├── memory_adapter.py     # In-memory fallback ✅
│   │   └── vector_adapter.py     # ChromaDB vector storage ✅
│   └── embedding/                # Embedding adapters (planned)
├── tiers/
│   ├── working.py                # Working Memory ✅
│   ├── shortterm.py              # Short-term Memory ✅
│   └── longterm.py               # Long-term Memory (TODO)
├── engines/
│   ├── consolidation/            # Consolidation logic (partial)
│   ├── retrieval/                # Retrieval engine (TODO)
│   └── context/                  # Context assembly (TODO)
└── models/
    ├── base.py                   # Base models
    └── memory.py                 # Memory item models

tests/
├── test_redis_simple.py          # Redis adapter tests ✅
├── test_memory_simple.py         # Memory adapter tests ✅
├── test_vector_adapter.py        # Vector adapter tests ✅
├── test_working_memory.py        # Working Memory tests ✅
├── test_shortterm_memory.py      # Short-term Memory tests ✅
└── test_integration_comprehensive.py  # Integration tests ✅
```

## Common Development Tasks

### Adding a New Memory Tier

1. Create tier implementation in `smrti/tiers/`
2. Implement required interfaces from base models
3. Create comprehensive test suite in `tests/`
4. Update `smrti/tiers/__init__.py`
5. Run tests to validate implementation

### Adding a New Storage Adapter

1. Create adapter in `smrti/adapters/storage/`
2. Implement storage interface (store, retrieve, delete, etc.)
3. Add async support where applicable
4. Create adapter-specific tests
5. Update `smrti/adapters/storage/__init__.py`

### Debugging

```bash
# View real-time logs
docker-compose logs -f smrti-app

# Access container shell
docker-compose exec smrti-app bash

# Run debugger
docker-compose exec smrti-app python -m pdb smrti/tiers/shortterm.py

# Check memory usage
docker stats
```

## Performance Optimization

### Monitoring

Access Grafana at http://localhost:3000 for:
- Memory tier performance metrics
- Cache hit/miss rates
- Consolidation statistics
- Query latency
- Resource utilization

### Profiling

```bash
# Profile specific function
docker-compose exec smrti-app python -m cProfile -o profile.stats script.py

# Analyze profile
docker-compose exec smrti-app python -m pstats profile.stats
```

## Best Practices

1. **Always use async/await** for I/O operations
2. **Implement proper error handling** with fallbacks
3. **Add comprehensive logging** for debugging
4. **Write tests first** (TDD approach)
5. **Use type hints** for better IDE support
6. **Document complex logic** with docstrings
7. **Monitor performance** using observability tools
8. **Implement proper cleanup** in `__del__` or context managers

## Troubleshooting

### Docker Issues

**Problem**: Containers won't start
```bash
# Check logs
make docker-logs

# Restart from scratch
make docker-clean
make docker-dev
```

**Problem**: Port already in use
```bash
# Find process using port
lsof -i :6379  # Example for Redis

# Kill process or change port in docker-compose.yml
```

### Test Failures

**Problem**: Import errors
```bash
# Rebuild container
make docker-build

# Verify installation
docker-compose exec smrti-app pip list | grep smrti
```

**Problem**: Database connection errors
```bash
# Verify services are running
make docker-ps

# Check health status
docker-compose ps
```

## Next Development Session

**Focus**: Long-term Memory Tier Implementation

1. Create `smrti/tiers/longterm.py`
2. Integrate with vector storage adapter
3. Implement semantic search capabilities
4. Add archival and retrieval logic
5. Create comprehensive tests
6. Validate with integration tests

**Key Features to Implement**:
- Vector-based similarity search
- Fact consolidation from Short-term Memory
- Cross-session persistence
- Archival strategies
- Query optimization

---

**Need Help?** Check:
- [Docker Setup Guide](DOCKER_SETUP.md)
- [PRD Document](smrti-prd.md)
- [API Documentation](https://smrti.konf.dev)
