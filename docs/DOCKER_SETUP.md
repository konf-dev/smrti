# 🐳 Smrti Docker Setup Guide

Complete Docker containerization for the Smrti Memory System with all databases, APIs, and monitoring tools.

## 📋 Quick Start

### Prerequisites
- Docker & Docker Compose
- 8GB+ RAM recommended  
- 10GB+ disk space

### 1. Clone and Setup
```bash
git clone <repository>
cd smrti
cp .env.docker .env  # Customize if needed
```

### 2. Start Development Environment
```bash
# Full development stack with monitoring
make docker-dev

# Or basic services only
make docker-up
```

### 3. Verify Installation
```bash
# Check all services
make docker-status

# Test vector adapter
make vector-test

# Check health endpoints
make health
```

## 🌐 Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| **Smrti API** | http://localhost:8000 | - |
| **Grafana Dashboard** | http://localhost:3000 | admin/smrti_password |
| **Prometheus Metrics** | http://localhost:9090 | - |
| **Jaeger Tracing** | http://localhost:16686 | - |
| **Neo4j Browser** | http://localhost:7474 | neo4j/smrti_password |
| **Redis Commander** | http://localhost:8081 | - |
| **pgAdmin** | http://localhost:8082 | admin@smrti.dev/smrti_password |
| **Jupyter Lab** | http://localhost:8888 | token: smrti_dev_token |

## 🗄️ Database Architecture

### Storage Tiers
- **Redis** (ports 6379) - Working & Short-term Memory
- **ChromaDB** (port 8001) - Vector storage for Long-term Memory  
- **PostgreSQL** (port 5432) - Episodic Memory sequences
- **Neo4j** (ports 7474, 7687) - Semantic Memory facts & relationships

### Data Persistence
All data is persisted in Docker volumes:
- `redis-data` - Redis snapshots & AOF
- `chroma-data` - Vector embeddings & indexes
- `postgres-data` - Relational event data  
- `neo4j-data` - Graph database & indexes

## 🚀 Development Workflow

### Start Development
```bash
# Full stack with hot reload
make docker-dev

# View logs
make docker-logs

# Shell into container
make docker-shell
```

### Testing
```bash
# Run all tests in Docker
make docker-test

# Test vector storage specifically
make vector-test

# Run benchmarks
docker-compose run --rm smrti-app pytest tests/benchmarks --benchmark-only
```

### Database Operations
```bash
# Initialize with sample data
make db-init

# Reset all databases (destructive!)
make db-reset

# Create backups
make db-backup
```

## 📊 Monitoring & Observability

### Metrics (Prometheus + Grafana)
- **Application metrics**: Request latency, memory tier performance, error rates
- **Infrastructure metrics**: Database performance, resource utilization  
- **Business metrics**: Memory consolidation rates, retrieval accuracy

### Tracing (Jaeger)
- **Request tracing**: End-to-end request flows across memory tiers
- **Performance analysis**: Identify bottlenecks in retrieval pipeline
- **Error debugging**: Trace errors through the system

### Logs (Structured JSON)
```bash
# Follow application logs
docker-compose logs -f smrti-app

# Search logs
docker-compose logs smrti-app | grep "ERROR"
```

## 🔧 Configuration

### Environment Variables
Key settings in `.env`:
```bash
# Memory tier backends
SMRTI_TIER_WORKING_BACKEND=redis
SMRTI_TIER_LONG_TERM_BACKEND=chroma

# Feature flags  
SMRTI_FEATURE_ENABLE_RERANK=true
SMRTI_FEATURE_ENABLE_GRAPH=true

# Performance tuning
SMRTI_CONTEXT_DEFAULT_BUDGET=8000
MAX_BATCH_SIZE=1000
```

### Service Configuration
- **Prometheus**: `docker/prometheus/prometheus.yml`
- **Grafana**: `docker/grafana/provisioning/`
- **PostgreSQL**: `docker/postgres/init/`

## 🔒 Security Considerations

### Development vs Production
- Development uses simple passwords for convenience
- Production should use:
  - Strong passwords & secrets management
  - TLS encryption between services
  - Network policies & firewalls
  - Resource limits & monitoring

### Data Privacy
- PII redaction enabled by default
- Tenant isolation enforced
- Optional encryption at rest

## 🚨 Troubleshooting

### Common Issues

**Services won't start:**
```bash
# Check Docker resources
docker system df
docker system prune -f

# Reset everything
make docker-clean
make docker-dev
```

**Database connection errors:**
```bash
# Check service health
make docker-status
make health

# Restart databases
docker-compose restart redis postgres neo4j chroma
```

**Out of memory:**
```bash
# Check resource usage
docker stats

# Reduce memory limits in docker-compose.yml
# Or increase Docker Desktop memory allocation
```

**Permission errors:**
```bash
# Fix data directory permissions
sudo chown -R $USER:$USER ./data ./logs
```

### Performance Tuning

**Slow vector searches:**
- Increase ChromaDB memory allocation
- Tune embedding batch sizes
- Enable query result caching

**High memory usage:**
- Adjust Redis maxmemory policy
- Reduce embedding cache size
- Enable memory tier consolidation

**Network connectivity:**
```bash
# Test inter-service connectivity
docker-compose exec smrti-app ping redis
docker-compose exec smrti-app ping postgres
```

## 📈 Production Deployment

### Scaling Recommendations
- **Redis**: Cluster mode for high availability
- **PostgreSQL**: Read replicas for episodic queries
- **Neo4j**: Clustering for semantic memory
- **ChromaDB**: Distributed deployment for large vectors

### Monitoring in Production
- Set up alerting rules in Prometheus
- Configure Grafana dashboards for ops team
- Enable log aggregation (ELK/Loki)
- Set up health check endpoints

### Backup Strategy
- Automated daily backups of all databases
- Point-in-time recovery for PostgreSQL  
- Neo4j dump exports for graph data
- Vector index snapshots for ChromaDB

## 🎯 Next Steps

1. **Complete Vector Storage**: Install ChromaDB dependencies
2. **Run Integration Tests**: Validate all memory tiers  
3. **Load Sample Data**: Test with realistic datasets
4. **Configure Monitoring**: Set up alerts and dashboards
5. **Performance Testing**: Benchmark under load

## 📚 Additional Resources

- **API Documentation**: http://localhost:8000/docs (when running)
- **Prometheus Metrics**: http://localhost:9090/targets
- **Neo4j Manual**: https://neo4j.com/docs/
- **ChromaDB Docs**: https://docs.trychroma.com/