# Smrti: Intelligent Multi-Tier Memory System

**Sanskrit: स्मृति - "remembrance"**

A standalone, provider-agnostic cognitive memory substrate for AI systems. Smrti enables agents and LLM-powered workflows to retain, organize, retrieve, and evolve knowledge across five complementary tiers: **Working**, **Short-Term**, **Long-Term**, **Episodic**, and **Semantic** memory.

[![CI](https://github.com/konf-dev/smrti/workflows/CI/badge.svg)](https://github.com/konf-dev/smrti/actions)
[![codecov](https://codecov.io/gh/konf-dev/smrti/branch/main/graph/badge.svg)](https://codecov.io/gh/konf-dev/smrti)
[![PyPI version](https://badge.fury.io/py/smrti.svg)](https://badge.fury.io/py/smrti)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## 🚀 Quick Start

### Installation

```bash
# Basic installation
pip install smrti

# With Redis and vector store support
pip install smrti[redis,vector-basic]

# Full development setup
pip install smrti[all]
```

### Basic Usage

```python
from smrti import SmrtiClient, Settings

# Configure memory tiers
settings = Settings(
    tiers={
        "working": {"backend": "redis", "ttl_seconds": 300},
        "long_term": {"backend": "chroma", "half_life_days": 60},
    }
)

# Initialize client
client = SmrtiClient(settings=settings)

# Store events and facts
await client.record_event({
    "user_id": "user123",
    "event_type": "user_login", 
    "event_data": {"timestamp": "2025-10-03T10:00:00Z"},
    "tenant": "acme",
    "namespace": "app"
})

await client.store_fact({
    "entity_id": "user123",
    "predicate": "preferred_language", 
    "object": "python",
    "confidence": 0.95,
    "tenant": "acme",
    "namespace": "app"
})

# Build context for LLM
context = await client.build_context(
    user_id="user123",
    query="What programming languages does the user know?",
    token_budget=4000
)

print(context.sections[0].items)  # Retrieved facts and events
```

## 🏗️ Architecture

### Five-Tier Memory System

| Tier | Purpose | Retention | Backend Examples |
|------|---------|-----------|------------------|
| **Working** | Current turn context | Minutes | Redis (TTL) |
| **Short-Term** | Session continuity | Hours/Days | Redis (session-scoped) |
| **Long-Term** | Durable knowledge | Months | ChromaDB, Pinecone, Weaviate |
| **Episodic** | Temporal events | Weeks/Months | PostgreSQL, time-series DB |
| **Semantic** | Structured facts | Months+ | Neo4j, NetworkX graphs |

### Hybrid Retrieval Engine

Smrti combines multiple retrieval modalities for maximum relevance:

- **Vector Similarity**: Dense embeddings for semantic search
- **Lexical Search**: BM25 keyword matching
- **Graph Traversal**: Entity relationships and fact chains  
- **Temporal Filtering**: Time-based event sequences
- **Adaptive Fusion**: Weighted score combination with re-ranking

### Provider-Agnostic Architecture

```python
# Easy adapter swapping - no code changes needed
settings = Settings(
    tiers={
        "long_term": {
            "backend": "pinecone",  # Switch from ChromaDB to Pinecone
            "adapter_config": {
                "api_key": "your-key",
                "index_name": "smrti-ltm"
            }
        }
    },
    embedding_provider="openai",  # Switch from Sentence Transformers
)
```

## 🔧 Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Redis, PostgreSQL, ChromaDB, Neo4j (via Docker)

### Full Development Environment

```bash
# Clone repository
git clone https://github.com/konf-dev/smrti.git
cd smrti

# Setup development environment
make setup-dev

# Run tests
make test

# Start development services
make docker-up

# Validate configuration
make config-validate
```

### Docker Development Stack

```bash
# Start all services
docker-compose up -d

# Services available:
# - Redis: localhost:6379
# - ChromaDB: localhost:8000  
# - PostgreSQL: localhost:5432
# - Neo4j: localhost:7474 (browser), localhost:7687 (bolt)
```

## 📊 Key Features

### 🧠 Cognitive Memory Model
- **Neuroscience-Inspired**: Five-tier taxonomy mirrors human memory systems
- **Lifecycle Management**: Automatic consolidation, summarization, and decay
- **Provenance Tracking**: Full lineage and transformation history

### ⚡ Performance & Scalability  
- **Adaptive Context**: Token-budget aware assembly with reduction strategies
- **Parallel Retrieval**: Concurrent multi-tier searches with failure isolation
- **Caching Layers**: Embedding, candidate, and context result caching

### 🔒 Enterprise Ready
- **Multi-Tenant**: Strict namespace isolation with optional encryption
- **Observability**: OpenTelemetry tracing + Prometheus metrics
- **Security**: PII redaction, data classification, integrity checks

### 🔌 Extensible Architecture
- **Plugin System**: Easy adapter development for new backends
- **Future-Proof**: Multimodal hooks for images, audio, video
- **Hot Swappable**: Runtime provider switching without restarts

## 📈 Performance Targets

| Operation | p95 Latency | Notes |
|-----------|-------------|-------|
| `build_context` (warm) | < 250ms | With embedding cache hits |
| Vector search | < 120ms | ANN-optimized indexes |  
| Hybrid retrieval | < 400ms | Full lexical + vector + graph |
| Consolidation batch | < 2s | 200 messages → summary |

## 🛡️ Security & Privacy

### Data Protection
- **Namespace Isolation**: Mandatory tenant/namespace scoping
- **PII Redaction**: Configurable pattern-based filtering
- **Encryption Hooks**: Adapter-mediated encryption at rest
- **Integrity Validation**: Checksums and lineage verification

### Compliance Ready
- **GDPR**: Right to erasure with cascade deletion
- **SOC2**: Audit logs and change management
- **Multi-Region**: Data residency controls (roadmap)

## 📚 Documentation

- **[User Guide](./docs/USER_GUIDE.md)**: Complete guide to using Smrti - start here!
- **[Development Guide](./docs/DEVELOPMENT_GUIDE.md)**: Contributing and extending Smrti
- **[Docker Setup](./docs/DOCKER_SETUP.md)**: Running Smrti with Docker
- **[Examples](./examples/)**: Working code examples and demos

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](./CONTRIBUTING.md) for details.

### Development Workflow

```bash
# Create feature branch
git checkout -b feature/new-adapter

# Make changes and test
make quality-gate
make test
make adapter-cert

# Submit PR
git push origin feature/new-adapter
```

### Adapter Certification

New adapters must pass our certification harness:

```bash
# Run full adapter certification
make adapter-cert

# Certify specific adapter  
make adapter-cert-redis
```

## 📋 Roadmap

### Current (Phase 1-3)
- ✅ Core five-tier memory system
- ✅ Hybrid retrieval engine  
- ✅ Redis + ChromaDB + PostgreSQL + Neo4j adapters
- ✅ OpenTelemetry observability
- ✅ Full test coverage + CI/CD

### Near Term (Phase 4-5) 
- 🔄 Advanced lifecycle management
- 🔄 Cross-encoder re-ranking
- 🔄 Adaptive weight learning
- 🔄 Enterprise security enhancements

### Future (Phase 6+)
- 🗓️ Multimodal memory (images, audio, video)
- 🗓️ Federated memory synchronization  
- 🗓️ Procedural memory tier
- 🗓️ Differential privacy features

## 📄 License

Licensed under the Apache License, Version 2.0. See [LICENSE](./LICENSE) for details.

## 🙏 Acknowledgments

- **Sanskrit Etymology**: स्मृति (smrti) - remembrance, memory, mindfulness
- **Cognitive Science**: Inspired by Atkinson-Shiffrin multi-store memory model
- **Community**: Built with ❤️ by [KonfSutra](https://konf.dev) and contributors

---

**Ready to give your AI systems perfect memory?** Get started with the [User Guide](./docs/USER_GUIDE.md) or explore the [examples](./examples/).
