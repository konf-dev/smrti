# Smrti User Guide

**Smrti** is an intelligent, multi-tiered memory system for AI agents and applications. It provides persistent, context-aware memory with automatic consolidation, semantic search, and adaptive recall.

> 🚧 **Alpha Release**: Smrti is under active development. This guide covers currently implemented features and will be updated as new capabilities are added.

---

## Table of Contents

- [Overview](#overview)
  - [What is Smrti?](#what-is-smrti)
  - [Why Smrti?](#why-smrti)
  - [Key Features](#key-features)
- [Getting Started](#getting-started)
- [Core Concepts](#core-concepts)
- [Using Smrti](#using-smrti)
  - [Working Memory](#working-memory) ✅
  - [Short-term Memory](#short-term-memory) ✅
  - [Long-term Memory](#long-term-memory) ✅
  - [Episodic Memory](#episodic-memory) ✅
  - [Semantic Memory](#semantic-memory) 🚧
  - [Context Assembly](#context-assembly) ✅
  - [Hybrid Retrieval](#hybrid-retrieval) ✅
- [Using Smrti in Agentic AI Systems](#using-smrti-in-agentic-ai-systems)
  - [Real-Time Chat Processing](#real-time-chat-processing)
  - [Offline Insight Generation](#offline-insight-generation)
  - [Multi-Agent Collaboration](#multi-agent-collaboration)
  - [Common Use Cases](#common-use-cases)
- [Memory Tiers](#memory-tiers)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Best Practices](#best-practices)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)

**Legend**: ✅ Available Now | 🚧 Coming Soon

---

## Overview

### What is Smrti?

Smrti (Sanskrit: स्मृति, "memory") is a sophisticated memory management system designed for AI agents and applications that need:

- **Persistent Memory**: Store and recall information across sessions
- **Intelligent Organization**: Automatic categorization and consolidation of memories
- **Semantic Understanding**: Search by meaning, not just keywords
- **Adaptive Recall**: Surface the most relevant memories for any context
- **Scalable Architecture**: Handle millions of memory items efficiently

### Why Smrti?

Unlike traditional databases or simple caching layers, Smrti is purpose-built for AI agents:

| Traditional Databases | Vector Databases | **Smrti** |
|----------------------|------------------|-----------|
| Key-value lookups | Semantic similarity | ✅ **Multi-tiered memory** with automatic tier management |
| Manual data management | Single-mode search | ✅ **Hybrid retrieval** combining vector, lexical, temporal, and graph |
| No temporal awareness | No time-based decay | ✅ **Intelligent consolidation** with access-pattern based promotion |
| Static relationships | Limited relationships | ✅ **Knowledge graphs** for complex entity relationships |
| No automatic optimization | No automatic pruning | ✅ **Self-optimizing** with background consolidation and cleanup |
| Application-managed | No context assembly | ✅ **Built-in context assembly** respecting token budgets |

**Smrti is the memory layer AI agents have been missing.**

### Key Features

✅ **Multi-Tiered Architecture**
- Working Memory: Immediate, fast-access memory (< 1ms)
- Short-term Memory: Temporary storage with automatic consolidation
- Long-term Memory: Persistent semantic storage ✅
- Episodic Memory: Event timeline tracking ✅
- Semantic Memory: Knowledge graph representation (*coming soon*)

✅ **Intelligent Consolidation**
- Automatic promotion of frequently accessed items
- Configurable consolidation strategies
- Background processing to minimize latency

✅ **Production Ready**
- Built on proven technologies (Redis, PostgreSQL, Neo4j, ChromaDB)
- Comprehensive monitoring and observability
- Tenant isolation for multi-user applications
- Docker-based deployment

✅ **Agent-First Design**
- Purpose-built for agentic AI workflows
- Real-time and batch processing support
- Multi-agent collaboration patterns
- Context-aware memory retrieval

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for development)
- 4GB RAM minimum (8GB recommended)

### Quick Start

#### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/konf-dev/smrti.git
cd smrti

# Start the Docker environment
make docker-dev
```

This will start all required services:
- Redis (Working/Short-term Memory)
- PostgreSQL (Episodic Memory)
- Neo4j (Semantic Memory)
- ChromaDB (Vector Storage)
- Prometheus, Grafana, Jaeger (Monitoring)

#### 2. Install Smrti

```bash
# Install in development mode
pip install -e .

# Or install from PyPI (when released)
pip install smrti
```

#### 3. Basic Usage

```python
import asyncio
from smrti import WorkingMemory, ShortTermMemory

async def main():
    # Create a working memory instance
    working_mem = WorkingMemory(tenant_id="my_app")
    
    # Store a memory
    await working_mem.store(
        key="user_preference",
        value={"theme": "dark", "language": "en"},
        namespace="settings"
    )
    
    # Retrieve a memory
    item = await working_mem.retrieve("user_preference")
    print(f"Retrieved: {item.value}")
    
    # Cleanup
    await working_mem.shutdown()

asyncio.run(main())
```

---

## Core Concepts

### Memory Items

Every piece of information in Smrti is stored as a **Memory Item** with:

```python
MemoryItem(
    key="unique_identifier",          # Unique key for retrieval
    value=<any_data>,                  # The actual content (dict, str, list, etc.)
    tenant_id="your_app",              # Isolation boundary
    namespace="category",              # Logical grouping
    metadata=MemoryMetadata(           # Rich metadata
        access_count=3,                # How often accessed
        tags=["important", "user"],    # Searchable tags
        embedding=[0.1, 0.2, ...],     # Semantic vector
        # ... more metadata
    ),
    ttl=3600                           # Time-to-live in seconds
)
```

### Tenancy

Smrti supports **multi-tenancy** out of the box. Each tenant has completely isolated memory:

```python
# Tenant A's memory
memory_a = WorkingMemory(tenant_id="company_a")

# Tenant B's memory (completely separate)
memory_b = WorkingMemory(tenant_id="company_b")
```

### Namespaces

**Namespaces** provide logical grouping within a tenant:

```python
# Different namespaces for different purposes
await memory.store(key="user_name", value="Alice", namespace="users")
await memory.store(key="api_key", value="secret", namespace="credentials")
await memory.store(key="last_query", value="...", namespace="sessions")
```

### TTL (Time-to-Live)

Control how long memories persist:

```python
from datetime import timedelta

# Expires after 1 hour
await memory.store(key="session", value=data, ttl=timedelta(hours=1))

# Expires after 7 days
await memory.store(key="cache", value=data, ttl=timedelta(days=7))

# Never expires (use with caution!)
await memory.store(key="permanent", value=data, ttl=None)
```

---

## Using Smrti

### Working Memory

**Working Memory** is your fast, temporary storage for actively used data. Think of it as the "RAM" of your AI agent.

> ✅ **Status**: Available in v0.1-alpha

#### Creating a Working Memory

```python
from smrti.tiers.working import WorkingMemoryTier, WorkingMemoryConfig

# Basic usage
working_mem = WorkingMemoryTier(tenant_id="my_app")

# Advanced configuration
config = WorkingMemoryConfig(
    max_items=1000,              # Capacity limit
    eviction_policy="lru",       # LRU, LFU, or custom
    default_ttl=3600,            # 1 hour default
    auto_promote_to_short_term=True  # Automatic promotion
)
working_mem = WorkingMemoryTier(
    tenant_id="my_app",
    config=config
)

# Initialize (required before use)
await working_mem.initialize()
```

#### Storing Memories

```python
# Simple store
success = await working_mem.store(
    key="current_task",
    value="Processing user request #1234"
)

# Store with metadata
success = await working_mem.store(
    key="user_context",
    value={"user_id": "alice", "session": "xyz"},
    namespace="active_sessions",
    ttl=timedelta(minutes=30),
    metadata={
        "importance": "high",
        "source": "conversation"
    }
)
```

#### Retrieving Memories

```python
# Retrieve single item
item = await working_mem.retrieve("current_task")
if item:
    print(f"Task: {item.value}")
    print(f"Accessed {item.metadata.access_count} times")

# Batch retrieve
keys = ["user_context", "current_task", "last_action"]
items = await working_mem.batch_retrieve(keys)
for key, item in items.items():
    print(f"{key}: {item.value}")
```

#### Searching Memories

```python
# Search by namespace
items = await working_mem.search(namespace="active_sessions")

# Search by tags
items = await working_mem.search(tags=["important", "user"])

# Combined search
items = await working_mem.search(
    namespace="active_sessions",
    tags=["important"],
    limit=10
)
```

#### Deleting Memories

```python
# Delete single item
success = await working_mem.delete("old_task")

# Delete by namespace
count = await working_mem.delete_namespace("expired_sessions")
print(f"Deleted {count} items")

# Clear all (use with caution!)
await working_mem.clear()
```

#### Statistics

```python
# Get usage statistics
stats = await working_mem.get_statistics()
print(f"Total items: {stats.total_items}")
print(f"Memory usage: {stats.memory_usage_mb}MB")
print(f"Cache hit rate: {stats.cache_hit_rate:.2%}")
print(f"Most accessed: {stats.top_items[:5]}")
```

### Short-term Memory

**Short-term Memory** bridges Working Memory and Long-term Memory, providing intelligent consolidation and automatic promotion of important memories.

> ✅ **Status**: Available in v0.1-alpha

#### Creating Short-term Memory

```python
from smrti.tiers.shortterm import ShortTermMemory, ConsolidationConfig, ConsolidationStrategy

# Basic usage
short_mem = ShortTermMemory(tenant_id="my_app")

# Advanced configuration
config = ConsolidationConfig(
    strategy=ConsolidationStrategy.RECENCY_WEIGHTED,
    promotion_threshold=5,       # Promote after 5 accesses
    consolidation_window=timedelta(hours=1),
    max_items_per_batch=100
)
short_mem = ShortTermMemory(
    tenant_id="my_app",
    config=config
)

# Start background consolidation
await short_mem.start()
```

#### Consolidation Strategies

Choose how memories are consolidated:

```python
from smrti.tiers.shortterm import ConsolidationStrategy

# Promote based on access frequency
ConsolidationStrategy.ACCESS_FREQUENCY

# Weighted by recency (recent + frequent = priority)
ConsolidationStrategy.RECENCY_WEIGHTED

# Group similar memories together
ConsolidationStrategy.SEMANTIC_CLUSTERING

# Batch by time windows
ConsolidationStrategy.TEMPORAL_BATCHING
```

#### Using Short-term Memory

```python
# Store (same API as Working Memory)
await short_mem.store(
    key="important_fact",
    value="User prefers detailed explanations",
    ttl=timedelta(days=1)
)

# Retrieve (tracks access for promotion)
item = await short_mem.retrieve("important_fact")

# Register promotion callback
async def on_promote(item):
    print(f"Promoting {item.key} to long-term memory!")
    # Your logic to store in long-term memory

short_mem.register_promotion_callback(on_promote)

# Run consolidation manually (normally automatic)
candidates = await short_mem.run_consolidation()
print(f"Identified {len(candidates)} items for promotion")
```

#### Monitoring Consolidation

```python
# Get consolidation statistics
stats = short_mem.get_statistics()
print(f"Items stored: {stats['items_stored']}")
print(f"Items promoted: {stats['items_promoted']}")
print(f"Consolidations run: {stats['consolidations_run']}")
print(f"Cache hit rate: {stats['cache_hits'] / (stats['cache_hits'] + stats['cache_misses']):.2%}")
```

### Long-term Memory

**Long-term Memory** provides persistent, semantic storage for knowledge that needs to survive across sessions and be searchable by meaning.

> ✅ **Status**: Available now - Ready for production use (v0.2.0)

#### Creating Long-term Memory

```python
from smrti.tiers.longterm import LongTermMemory, LongTermConfig, SearchMode

# Basic usage
long_mem = LongTermMemory(tenant_id="my_app")

# Advanced configuration
config = LongTermConfig(
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    vector_dimension=384,
    similarity_threshold=0.7,
    max_results=100,
    enable_reranking=True
)
long_mem = LongTermMemory(
    tenant_id="my_app",
    config=config
)

await long_mem.initialize()
```

#### Storing Facts

```python
# Store a fact with automatic embedding generation
await long_mem.store_fact(
    key="python_expert",
    content="User is an expert in Python programming with 10+ years experience",
    metadata={
        "category": "user_profile",
        "confidence": 0.95,
        "source": "conversation_analysis"
    }
)

# Store with custom embedding
await long_mem.store_fact(
    key="user_preference_123",
    content="User prefers detailed technical explanations",
    embedding=custom_embedding_vector,
    ttl=None  # Persist indefinitely
)

# Batch store for efficiency
facts = [
    {"key": "fact_1", "content": "...", "metadata": {...}},
    {"key": "fact_2", "content": "...", "metadata": {...}},
]
await long_mem.batch_store(facts)
```

#### Semantic Search

```python
# Search by meaning, not keywords
results = await long_mem.search(
    query="What does the user know about databases?",
    limit=5
)

for result in results:
    print(f"Fact: {result.content}")
    print(f"Similarity: {result.score:.2f}")
    print(f"Metadata: {result.metadata}")

# Hybrid search (semantic + filters)
results = await long_mem.search(
    query="user technical skills",
    filters={
        "category": "user_profile",
        "confidence": {"$gte": 0.8}
    },
    limit=10
)

# Time-based filtering
from datetime import datetime, timedelta
results = await long_mem.search(
    query="recent user feedback",
    time_range=(
        datetime.now() - timedelta(days=7),
        datetime.now()
    )
)
```

#### Consolidation from Short-term

```python
# Automatic consolidation callback
async def consolidate_to_longterm(item: MemoryItem):
    """Called when short-term memory promotes an item."""
    # Extract key information
    content = extract_knowledge(item.value)
    
    # Store in long-term memory
    await long_mem.store_fact(
        key=f"consolidated_{item.key}",
        content=content,
        metadata={
            "source": "short_term_promotion",
            "original_key": item.key,
            "access_count": item.metadata.access_count
        }
    )

# Register with short-term memory
short_mem.register_promotion_callback(consolidate_to_longterm)
```

#### Archival and Pruning

```python
# Archive old facts to cold storage
archived = await long_mem.archive_old_facts(
    older_than=timedelta(days=365),
    min_access_count=5  # Keep frequently accessed
)
print(f"Archived {archived} facts")

# Prune low-quality facts
pruned = await long_mem.prune_facts(
    confidence_threshold=0.3,  # Remove low-confidence
    max_age=timedelta(days=180)
)
print(f"Pruned {pruned} facts")

# Merge similar facts
merged = await long_mem.merge_similar_facts(
    similarity_threshold=0.95,
    strategy="keep_most_recent"
)
print(f"Merged {merged} duplicate facts")
```

#### Retrieval Modes

```python
from smrti.tiers.longterm import SearchMode

# Pure vector similarity
results = await long_mem.search(
    query="machine learning",
    mode=SearchMode.VECTOR_ONLY
)

# Lexical search (BM25)
results = await long_mem.search(
    query="machine learning",
    mode=SearchMode.LEXICAL_ONLY
)

# Hybrid (default - best results)
results = await long_mem.search(
    query="machine learning",
    mode=SearchMode.HYBRID
)

# With reranking
results = await long_mem.search(
    query="machine learning",
    mode=SearchMode.HYBRID,
    rerank=True  # Uses cross-encoder for better ranking
)
```

### Episodic Memory

**Episodic Memory** stores temporal sequences of events, enabling timeline queries and causal reasoning.

> ✅ **Status**: Available now - Ready for production use (v0.2.0)

#### Creating Episodic Memory

```python
from smrti.tiers.episodic import EpisodicMemory, Episode, EpisodeType

# Basic usage
episodic_mem = EpisodicMemory(tenant_id="my_app")
await episodic_mem.initialize()
```

#### Recording Episodes

```python
from datetime import datetime

# Record a user action
await episodic_mem.record(
    episode_type=EpisodeType.USER_ACTION,
    action="clicked_button",
    context={
        "button_id": "submit_form",
        "page": "/checkout",
        "session_id": "abc123"
    },
    timestamp=datetime.now(),
    metadata={
        "user_id": "alice",
        "device": "mobile"
    }
)

# Record a system event
await episodic_mem.record(
    episode_type=EpisodeType.SYSTEM_EVENT,
    action="api_call",
    context={
        "endpoint": "/api/users",
        "method": "POST",
        "status": 200,
        "duration_ms": 145
    }
)

# Record conversation turn
await episodic_mem.record(
    episode_type=EpisodeType.CONVERSATION,
    action="message",
    context={
        "role": "user",
        "content": "How do I reset my password?",
        "intent": "password_reset"
    }
)
```

#### Timeline Queries

```python
# Get events in time range
episodes = await episodic_mem.get_timeline(
    start=datetime(2025, 10, 1),
    end=datetime(2025, 10, 3),
    episode_types=[EpisodeType.USER_ACTION]
)

# Get recent history
recent = await episodic_mem.get_recent(
    limit=20,
    filters={"action": "clicked_button"}
)

# Get episode sequence
sequence = await episodic_mem.get_sequence(
    start_episode_id="ep_123",
    length=10  # Next 10 episodes
)
```

#### Pattern Analysis

```python
# Find patterns in user behavior
patterns = await episodic_mem.find_patterns(
    episode_type=EpisodeType.USER_ACTION,
    window=timedelta(hours=1),
    min_frequency=3
)

for pattern in patterns:
    print(f"Pattern: {pattern.sequence}")
    print(f"Frequency: {pattern.count}")
    print(f"Confidence: {pattern.confidence}")

# Causal analysis
causes = await episodic_mem.analyze_causality(
    effect="purchase_completed",
    lookback=timedelta(minutes=30),
    min_correlation=0.7
)
```

#### Session Reconstruction

```python
# Reconstruct full user session
session = await episodic_mem.reconstruct_session(
    session_id="abc123",
    include_system_events=False
)

print(f"Session duration: {session.duration}")
print(f"Total events: {len(session.episodes)}")
print(f"Key actions: {session.key_actions}")
```

### Semantic Memory

**Semantic Memory** organizes knowledge as a graph, enabling relationship queries and knowledge inference.

> 🚧 **Status**: Coming in v0.2 - API documented below is planned interface

#### Creating Semantic Memory

```python
from smrti.tiers.semantic import SemanticMemory, Node, Relationship, RelationType

# Basic usage
semantic_mem = SemanticMemory(tenant_id="my_app")
await semantic_mem.initialize()
```

#### Creating Knowledge Nodes

```python
# Create entity nodes
user_node = await semantic_mem.create_node(
    node_type="Person",
    properties={
        "name": "Alice",
        "role": "Software Engineer",
        "expertise": ["Python", "Machine Learning"]
    }
)

skill_node = await semantic_mem.create_node(
    node_type="Skill",
    properties={
        "name": "Python",
        "category": "Programming Language",
        "proficiency_levels": ["Beginner", "Intermediate", "Expert"]
    }
)

# Create relationships
await semantic_mem.create_relationship(
    from_node=user_node.id,
    to_node=skill_node.id,
    relationship_type=RelationType.HAS_SKILL,
    properties={
        "level": "Expert",
        "years": 10,
        "last_used": datetime.now()
    }
)
```

#### Querying the Graph

```python
# Find related nodes
related = await semantic_mem.get_related(
    node_id=user_node.id,
    relationship_type=RelationType.HAS_SKILL,
    max_depth=2
)

# Path finding
path = await semantic_mem.find_path(
    from_node=user_node.id,
    to_node=project_node.id,
    max_length=5
)

# Subgraph extraction
subgraph = await semantic_mem.get_subgraph(
    center_node=user_node.id,
    radius=2,
    filters={"node_type": ["Person", "Skill", "Project"]}
)
```

#### Knowledge Inference

```python
# Infer new relationships
inferred = await semantic_mem.infer_relationships(
    node_id=user_node.id,
    min_confidence=0.8
)

# Community detection
communities = await semantic_mem.detect_communities(
    algorithm="louvain",
    min_size=3
)

# Similarity finding
similar = await semantic_mem.find_similar_nodes(
    node_id=user_node.id,
    similarity_threshold=0.7,
    limit=10
)
```

#### Graph Analytics

```python
# Centrality analysis
important = await semantic_mem.get_central_nodes(
    metric="pagerank",
    limit=20
)

# Traversal queries
results = await semantic_mem.traverse(
    start_node=user_node.id,
    pattern="(Person)-[HAS_SKILL]->(Skill)-[USED_IN]->(Project)",
    filters={"Project.status": "active"}
)

# Aggregate queries
stats = await semantic_mem.aggregate(
    node_type="Person",
    aggregations={
        "total_skills": "count(HAS_SKILL)",
        "avg_experience": "avg(HAS_SKILL.years)"
    }
)
```

### Context Assembly

**Context Assembly** intelligently constructs context windows for LLM prompts, respecting token budgets and optimizing for relevance.

> ✅ **Status**: Available now - Ready for production use (v0.2.0)

#### Creating Context Assembler

```python
from smrti.engines.context import ContextAssembler, AssemblyStrategy, Section

# Basic usage
assembler = ContextAssembler(
    max_tokens=4096,
    model="gpt-4",  # For accurate token counting
    tenant_id="my_app"
)
await assembler.initialize()
```

#### Defining Context Sections

```python
from smrti.engines.context import SectionType, Priority

# Define section requirements
sections = [
    Section(
        type=SectionType.SYSTEM_PROMPT,
        priority=Priority.REQUIRED,
        max_tokens=500,
        source="static",
        content="You are a helpful assistant..."
    ),
    Section(
        type=SectionType.CONVERSATION_HISTORY,
        priority=Priority.HIGH,
        max_tokens=2000,
        source="working_memory",
        query={"namespace": "conversation"}
    ),
    Section(
        type=SectionType.RELEVANT_FACTS,
        priority=Priority.MEDIUM,
        max_tokens=1000,
        source="long_term_memory",
        query="user preferences and context"
    ),
    Section(
        type=SectionType.EXAMPLES,
        priority=Priority.LOW,
        max_tokens=500,
        source="static",
        content=few_shot_examples
    )
]
```

#### Assembling Context

```python
# Assemble with automatic allocation
context = await assembler.assemble(
    sections=sections,
    strategy=AssemblyStrategy.PRIORITY_WEIGHTED,
    user_message="How do I change my password?"
)

print(f"Total tokens: {context.total_tokens}")
print(f"Sections included: {len(context.sections)}")
print(f"Final context: {context.text}")

# Access provenance
for section in context.sections:
    print(f"{section.type}: {section.tokens} tokens from {section.source}")
```

#### Adaptive Strategies

```python
from smrti.engines.context import AssemblyStrategy

# Priority-weighted (default)
context = await assembler.assemble(
    sections=sections,
    strategy=AssemblyStrategy.PRIORITY_WEIGHTED
)

# Recency-biased (prefer recent information)
context = await assembler.assemble(
    sections=sections,
    strategy=AssemblyStrategy.RECENCY_BIASED
)

# Relevance-optimized (semantic similarity to query)
context = await assembler.assemble(
    sections=sections,
    strategy=AssemblyStrategy.RELEVANCE_OPTIMIZED,
    query="password reset procedure"
)

# Balanced (mix of recency and relevance)
context = await assembler.assemble(
    sections=sections,
    strategy=AssemblyStrategy.BALANCED
)
```

#### Dynamic Reduction

```python
# Handle overflow with summarization
context = await assembler.assemble(
    sections=sections,
    overflow_strategy="summarize",  # or "truncate", "drop_lowest"
    summarizer=summarization_model
)

# Multi-level reduction
context = await assembler.assemble(
    sections=sections,
    overflow_strategy="hierarchical",
    reduction_levels=[
        {"threshold": 0.9, "strategy": "drop_lowest"},
        {"threshold": 0.95, "strategy": "truncate"},
        {"threshold": 1.0, "strategy": "summarize"}
    ]
)
```

### Hybrid Retrieval

**Hybrid Retrieval** combines multiple search methods (vector, lexical, temporal) with intelligent fusion for optimal results.

> ✅ **Status**: Available now - Ready for production use (v0.2.0)

#### Creating Hybrid Retriever

```python
from smrti.engines.retrieval import HybridRetriever, FusionStrategy

# Basic usage
retriever = HybridRetriever(
    tenant_id="my_app",
    fusion_strategy=FusionStrategy.RRF  # Reciprocal Rank Fusion
)
await retriever.initialize()
```

#### Multi-Modal Search

```python
# Automatic hybrid search
results = await retriever.search(
    query="machine learning best practices",
    limit=10
)

# With explicit weights
results = await retriever.search(
    query="machine learning best practices",
    weights={
        "vector": 0.5,      # Semantic similarity
        "lexical": 0.3,     # Keyword matching (BM25)
        "temporal": 0.2     # Recency
    }
)

# Enable all search modes
results = await retriever.search(
    query="user feedback on new feature",
    enable_vector=True,
    enable_lexical=True,
    enable_temporal=True,
    enable_graph=True,  # Graph-based relevance
    limit=20
)
```

#### Fusion Strategies

```python
from smrti.engines.retrieval import FusionStrategy

# Reciprocal Rank Fusion (default)
results = await retriever.search(
    query="...",
    fusion_strategy=FusionStrategy.RRF
)

# Weighted score combination
results = await retriever.search(
    query="...",
    fusion_strategy=FusionStrategy.WEIGHTED_SUM,
    weights={"vector": 0.6, "lexical": 0.4}
)

# Cascading (vector first, then lexical for ties)
results = await retriever.search(
    query="...",
    fusion_strategy=FusionStrategy.CASCADE
)

# Voting-based (consensus across methods)
results = await retriever.search(
    query="...",
    fusion_strategy=FusionStrategy.VOTING,
    min_votes=2  # Must appear in at least 2 search results
)
```

#### Advanced Filtering

```python
# Temporal decay
results = await retriever.search(
    query="user preferences",
    temporal_decay=True,
    decay_rate=0.1,  # Exponential decay
    half_life=timedelta(days=30)
)

# Multi-criteria filtering
results = await retriever.search(
    query="technical documentation",
    filters={
        "category": "engineering",
        "confidence": {"$gte": 0.8},
        "tags": {"$in": ["python", "api"]},
        "created_at": {"$gte": datetime.now() - timedelta(days=90)}
    }
)

# Faceted search
results = await retriever.search(
    query="user feedback",
    facets=["category", "sentiment", "date_bucket"],
    return_facet_counts=True
)

print(f"Results by category: {results.facets['category']}")
```

#### Reranking

```python
# Cross-encoder reranking for higher quality
results = await retriever.search(
    query="detailed explanation of async programming",
    initial_limit=100,  # Retrieve many candidates
    rerank=True,
    rerank_model="cross-encoder/ms-marco-MiniLM-L-12-v2",
    final_limit=10  # Return top 10 after reranking
)

# Custom reranking function
def custom_reranker(query: str, results: List[SearchResult]) -> List[SearchResult]:
    # Your custom scoring logic
    for result in results:
        result.score *= calculate_custom_score(result)
    return sorted(results, key=lambda x: x.score, reverse=True)

results = await retriever.search(
    query="...",
    rerank=True,
    rerank_fn=custom_reranker
)
```

---

## Using Smrti in Agentic AI Systems

Smrti is designed from the ground up to support intelligent AI agents that need sophisticated memory capabilities. Here's how to leverage Smrti in different agentic scenarios.

### Real-Time Chat Processing

#### Architecture Pattern

```python
from smrti import WorkingMemory, ShortTermMemory, LongTermMemory
from smrti.engines.context import ContextAssembler
from smrti.engines.retrieval import HybridRetriever

class ChatAgent:
    """AI Agent with Smrti-powered memory."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        
        # Memory tiers
        self.working = WorkingMemory(tenant_id=f"user_{user_id}")
        self.short_term = ShortTermMemory(tenant_id=f"user_{user_id}")
        self.long_term = LongTermMemory(tenant_id=f"user_{user_id}")
        
        # Retrieval and assembly
        self.retriever = HybridRetriever(tenant_id=f"user_{user_id}")
        self.assembler = ContextAssembler(
            max_tokens=4096,
            model="gpt-4-turbo"
        )
    
    async def initialize(self):
        """Initialize all memory components."""
        await self.working.initialize()
        await self.short_term.start()
        await self.long_term.initialize()
        await self.retriever.initialize()
        await self.assembler.initialize()
        
        # Setup promotion callback
        self.short_term.register_promotion_callback(
            self._promote_to_longterm
        )
    
    async def _promote_to_longterm(self, item):
        """Automatic promotion from short-term to long-term."""
        # Extract semantic meaning
        content = self._extract_knowledge(item.value)
        
        # Store as persistent fact
        await self.long_term.store_fact(
            key=f"fact_{item.key}",
            content=content,
            metadata={
                "promoted_from": "short_term",
                "access_count": item.metadata.access_count
            }
        )
    
    async def process_message(self, message: str) -> str:
        """Process user message with full memory context."""
        
        # 1. Store current message in working memory
        await self.working.store(
            key=f"msg_{datetime.now().timestamp()}",
            value={"role": "user", "content": message},
            namespace="conversation",
            ttl=timedelta(hours=1)
        )
        
        # 2. Retrieve relevant context using hybrid search
        relevant_facts = await self.retriever.search(
            query=message,
            limit=10,
            enable_vector=True,
            enable_temporal=True
        )
        
        # 3. Get recent conversation history
        history = await self.working.search(
            namespace="conversation",
            limit=20
        )
        
        # 4. Assemble context for LLM
        context = await self.assembler.assemble(
            sections=[
                Section(
                    type=SectionType.SYSTEM_PROMPT,
                    priority=Priority.REQUIRED,
                    max_tokens=300,
                    content=self._get_system_prompt()
                ),
                Section(
                    type=SectionType.RELEVANT_FACTS,
                    priority=Priority.HIGH,
                    max_tokens=1500,
                    content=self._format_facts(relevant_facts)
                ),
                Section(
                    type=SectionType.CONVERSATION_HISTORY,
                    priority=Priority.HIGH,
                    max_tokens=2000,
                    content=self._format_history(history)
                )
            ]
        )
        
        # 5. Generate response with LLM
        response = await self._generate_response(
            context=context.text,
            message=message
        )
        
        # 6. Store response
        await self.working.store(
            key=f"msg_{datetime.now().timestamp()}",
            value={"role": "assistant", "content": response},
            namespace="conversation",
            ttl=timedelta(hours=1)
        )
        
        # 7. Store important information in short-term
        if self._is_important(message, response):
            await self.short_term.store(
                key=f"important_{datetime.now().timestamp()}",
                value={
                    "message": message,
                    "response": response,
                    "extracted_facts": self._extract_facts(message, response)
                },
                ttl=timedelta(days=7)
            )
        
        return response
```

#### Benefits for Real-Time Chat

1. **Low Latency**: Working memory provides <1ms access to recent context
2. **Automatic Relevance**: Hybrid retrieval surfaces the most relevant memories
3. **Token Optimization**: Context assembler respects LLM token limits
4. **Progressive Learning**: Important information automatically promoted to long-term
5. **Session Continuity**: Conversation flows naturally across messages

### Offline Insight Generation

#### Pattern Mining Agent

```python
class InsightAgent:
    """Background agent for generating insights from memory."""
    
    async def generate_daily_insights(self, user_id: str):
        """Analyze user's memories to generate insights."""
        
        episodic = EpisodicMemory(tenant_id=f"user_{user_id}")
        semantic = SemanticMemory(tenant_id=f"user_{user_id}")
        long_term = LongTermMemory(tenant_id=f"user_{user_id}")
        
        # 1. Analyze temporal patterns
        patterns = await episodic.find_patterns(
            episode_type=EpisodeType.USER_ACTION,
            window=timedelta(days=7),
            min_frequency=3
        )
        
        # 2. Identify emerging topics
        topics = await long_term.cluster_facts(
            time_range=(
                datetime.now() - timedelta(days=7),
                datetime.now()
            ),
            min_cluster_size=5
        )
        
        # 3. Graph analysis for relationships
        communities = await semantic.detect_communities(
            algorithm="louvain"
        )
        
        # 4. Generate insights
        insights = {
            "behavioral_patterns": self._summarize_patterns(patterns),
            "trending_topics": self._summarize_topics(topics),
            "knowledge_clusters": self._summarize_communities(communities),
            "recommendations": await self._generate_recommendations(
                patterns, topics, communities
            )
        }
        
        # 5. Store insights for future use
        await long_term.store_fact(
            key=f"insights_{datetime.now().date()}",
            content=json.dumps(insights),
            metadata={
                "type": "automated_insight",
                "confidence": 0.85
            }
        )
        
        return insights
```

#### Memory Consolidation Agent

```python
class ConsolidationAgent:
    """Background agent for memory consolidation and cleanup."""
    
    async def run_nightly_consolidation(self, tenant_id: str):
        """Perform memory maintenance overnight."""
        
        short_term = ShortTermMemory(tenant_id=tenant_id)
        long_term = LongTermMemory(tenant_id=tenant_id)
        
        # 1. Force consolidation of short-term memories
        candidates = await short_term.run_consolidation()
        print(f"Promoted {len(candidates)} items to long-term")
        
        # 2. Merge duplicate facts
        merged = await long_term.merge_similar_facts(
            similarity_threshold=0.95
        )
        print(f"Merged {merged} duplicate facts")
        
        # 3. Archive old, rarely accessed memories
        archived = await long_term.archive_old_facts(
            older_than=timedelta(days=180),
            min_access_count=2
        )
        print(f"Archived {archived} old facts")
        
        # 4. Prune low-quality facts
        pruned = await long_term.prune_facts(
            confidence_threshold=0.3,
            max_age=timedelta(days=90)
        )
        print(f"Pruned {pruned} low-quality facts")
        
        # 5. Update embeddings for modified facts
        updated = await long_term.refresh_embeddings(
            modified_since=datetime.now() - timedelta(days=1)
        )
        print(f"Refreshed embeddings for {updated} facts")
```

### Multi-Agent Collaboration

#### Shared Memory Space

```python
class MultiAgentSystem:
    """Coordinate multiple agents with shared memory."""
    
    def __init__(self, team_id: str):
        self.team_id = team_id
        
        # Shared memory space
        self.shared_memory = WorkingMemory(tenant_id=f"team_{team_id}")
        self.knowledge_base = LongTermMemory(tenant_id=f"team_{team_id}")
        
        # Agent-specific memories
        self.agent_memories = {}
    
    async def create_agent(self, agent_id: str, role: str):
        """Create agent with access to shared and private memory."""
        
        # Private working memory
        private_memory = WorkingMemory(
            tenant_id=f"agent_{agent_id}"
        )
        
        agent = {
            "id": agent_id,
            "role": role,
            "private_memory": private_memory,
            "shared_memory": self.shared_memory,
            "knowledge_base": self.knowledge_base
        }
        
        self.agent_memories[agent_id] = agent
        return agent
    
    async def agent_communicate(
        self,
        from_agent: str,
        to_agent: str,
        message: dict
    ):
        """Enable agent-to-agent communication via shared memory."""
        
        # Store in shared memory with routing
        await self.shared_memory.store(
            key=f"msg_{datetime.now().timestamp()}",
            value={
                "from": from_agent,
                "to": to_agent,
                "content": message,
                "timestamp": datetime.now().isoformat()
            },
            namespace=f"comm_{to_agent}",
            ttl=timedelta(minutes=30)
        )
    
    async def agent_contribute_knowledge(
        self,
        agent_id: str,
        knowledge: str,
        confidence: float
    ):
        """Agent contributes to shared knowledge base."""
        
        await self.knowledge_base.store_fact(
            key=f"contrib_{agent_id}_{datetime.now().timestamp()}",
            content=knowledge,
            metadata={
                "contributor": agent_id,
                "confidence": confidence,
                "verified": False  # Requires consensus
            }
        )
```

### Common Use Cases

#### 1. Customer Support Agent

```python
class SupportAgent:
    """AI agent for customer support with memory."""
    
    async def handle_ticket(self, ticket_id: str, customer_id: str, issue: str):
        # Retrieve customer history
        history = await long_term.search(
            query=f"customer {customer_id} previous issues",
            filters={"customer_id": customer_id}
        )
        
        # Find similar resolved tickets
        similar = await retriever.search(
            query=issue,
            filters={"status": "resolved"},
            limit=5
        )
        
        # Generate response with context
        response = await self.generate_solution(
            issue=issue,
            customer_history=history,
            similar_cases=similar
        )
        
        # Store resolution for future reference
        await long_term.store_fact(
            key=f"ticket_{ticket_id}",
            content=f"Issue: {issue}. Resolution: {response}",
            metadata={
                "customer_id": customer_id,
                "resolved": True,
                "satisfaction": None  # To be updated
            }
        )
```

#### 2. Research Assistant

```python
class ResearchAgent:
    """AI agent for research and knowledge synthesis."""
    
    async def research_topic(self, topic: str):
        # Find relevant papers/documents
        documents = await retriever.search(
            query=topic,
            enable_vector=True,
            enable_graph=True,  # Find related concepts
            limit=50
        )
        
        # Build knowledge graph
        for doc in documents:
            await semantic_mem.create_node(
                node_type="Document",
                properties={"title": doc.title, "summary": doc.summary}
            )
            
            # Extract entities and relationships
            entities = self.extract_entities(doc.content)
            for entity in entities:
                await semantic_mem.create_relationship(
                    from_node=doc.id,
                    to_node=entity.id,
                    relationship_type=RelationType.MENTIONS
                )
        
        # Generate synthesis
        synthesis = await self.synthesize_findings(documents)
        
        # Store research result
        await long_term.store_fact(
            key=f"research_{topic}",
            content=synthesis,
            metadata={"type": "research_synthesis", "sources": len(documents)}
        )
```

#### 3. Personal AI Assistant

```python
class PersonalAssistant:
    """AI assistant with personalized memory."""
    
    async def learn_from_interaction(self, interaction: dict):
        # Extract preferences
        preferences = self.extract_preferences(interaction)
        
        for pref_key, pref_value in preferences.items():
            await long_term.store_fact(
                key=f"pref_{pref_key}",
                content=f"User prefers {pref_value}",
                metadata={"type": "preference", "confidence": 0.8}
            )
        
        # Update user model in semantic memory
        await semantic_mem.update_node(
            node_id=user_node_id,
            properties={
                "last_interaction": datetime.now(),
                "interaction_count": interaction_count + 1
            }
        )
    
    async def proactive_suggestion(self):
        # Analyze patterns
        patterns = await episodic.find_patterns(
            window=timedelta(days=30)
        )
        
        # Generate contextual suggestions
        suggestions = await self.generate_suggestions(
            patterns=patterns,
            current_context=await self.get_current_context()
        )
        
        return suggestions
```

#### 4. Code Review Agent

```python
class CodeReviewAgent:
    """AI agent for code review with project memory."""
    
    async def review_pr(self, pr_id: str, diff: str):
        # Find similar past issues
        similar_issues = await retriever.search(
            query=f"code issues in {self.extract_files(diff)}",
            filters={"type": "code_issue", "severity": ["medium", "high"]},
            limit=10
        )
        
        # Check against coding standards (semantic memory)
        standards = await semantic_mem.get_related(
            node_id=project_node_id,
            relationship_type=RelationType.HAS_STANDARD
        )
        
        # Generate review comments
        comments = await self.analyze_code(
            diff=diff,
            similar_issues=similar_issues,
            standards=standards
        )
        
        # Store review for future learning
        await long_term.store_fact(
            key=f"review_{pr_id}",
            content=json.dumps(comments),
            metadata={"pr_id": pr_id, "type": "code_review"}
        )
```

#### 5. Content Recommendation Agent

```python
class RecommendationAgent:
    """AI agent for personalized content recommendations."""
    
    async def recommend(self, user_id: str, context: dict):
        # Get user preferences
        preferences = await long_term.search(
            query="user preferences and interests",
            filters={"user_id": user_id, "type": "preference"}
        )
        
        # Analyze recent behavior
        recent_activity = await episodic.get_recent(
            limit=50,
            filters={"user_id": user_id, "action": "view_content"}
        )
        
        # Find similar users (collaborative filtering)
        similar_users = await semantic_mem.find_similar_nodes(
            node_id=user_node_id,
            similarity_threshold=0.7,
            limit=10
        )
        
        # Generate recommendations
        recommendations = await self.compute_recommendations(
            preferences=preferences,
            activity=recent_activity,
            similar_users=similar_users,
            context=context
        )
        
        return recommendations
```

### Performance Optimization for Agents

#### Caching Strategy

```python
class OptimizedAgent:
    """Agent with optimized memory access patterns."""
    
    def __init__(self):
        self.working = WorkingMemory(tenant_id="agent")
        self.cache_hit_count = 0
        self.cache_miss_count = 0
    
    async def get_with_cache(self, key: str, fetch_fn):
        """Get data with automatic caching."""
        
        # Try working memory first (fast)
        item = await self.working.retrieve(key)
        if item:
            self.cache_hit_count += 1
            return item.value
        
        # Cache miss - fetch from source
        self.cache_miss_count += 1
        value = await fetch_fn()
        
        # Store in working memory
        await self.working.store(
            key=key,
            value=value,
            ttl=timedelta(minutes=15)
        )
        
        return value
    
    async def batch_prefetch(self, keys: List[str]):
        """Prefetch frequently accessed items."""
        # Load into working memory for fast access
        items = await self.long_term.batch_retrieve(keys)
        for key, item in items.items():
            await self.working.store(
                key=key,
                value=item.value,
                ttl=timedelta(hours=1)
            )
```

#### Async Background Processing

```python
class BackgroundAgent:
    """Agent with background memory processing."""
    
    async def start_background_tasks(self):
        """Start non-blocking background tasks."""
        
        # Consolidation task
        asyncio.create_task(self._periodic_consolidation())
        
        # Insight generation task
        asyncio.create_task(self._periodic_insights())
        
        # Cleanup task
        asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_consolidation(self):
        """Run consolidation every hour."""
        while True:
            await asyncio.sleep(3600)  # 1 hour
            try:
                await self.short_term.run_consolidation()
            except Exception as e:
                logger.error(f"Consolidation failed: {e}")
    
    async def _periodic_insights(self):
        """Generate insights every 6 hours."""
        while True:
            await asyncio.sleep(21600)  # 6 hours
            try:
                insights = await self.generate_insights()
                await self.store_insights(insights)
            except Exception as e:
                logger.error(f"Insight generation failed: {e}")
```

---

## Memory Tiers

### Tier Hierarchy

```
┌─────────────────────────────────────────────────────┐
│  Working Memory (Fast, Temporary)                   │
│  • Immediate access (< 1ms)                         │
│  • LRU/LFU eviction                                 │
│  • Max 1000 items                                   │
└─────────────────┬───────────────────────────────────┘
                  │ Automatic Promotion
                  ▼
┌─────────────────────────────────────────────────────┐
│  Short-term Memory (Consolidation Layer)            │
│  • TTL-based aging                                  │
│  • Intelligent promotion                            │
│  • Background consolidation                         │
└─────────────────┬───────────────────────────────────┘
                  │ Promotion after N accesses
                  ▼
┌─────────────────────────────────────────────────────┐
│  Long-term Memory (Persistent, Semantic)            │
│  • Vector similarity search                         │
│  • Cross-session persistence                        │
│  • Semantic understanding                           │
└─────────────────────────────────────────────────────┘
```

### When to Use Each Tier

**Working Memory**: Use for...
- Current conversation context
- Temporary computation results
- Active session data
- Recently accessed items

**Short-term Memory**: Use for...
- Important session information
- Items that might need long-term storage
- Frequently accessed temporary data
- Bridge between ephemeral and permanent

**Long-term Memory** (*coming soon*): Use for...
- User preferences and history
- Knowledge base facts
- Cross-session information
- Semantic search requirements

---

## API Reference

### WorkingMemoryTier

#### Methods

```python
async def initialize() -> bool
```
Initialize the memory tier. Must be called before use.

```python
async def store(
    key: str,
    value: Any,
    namespace: str = "default",
    ttl: Optional[timedelta] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool
```
Store a memory item.

**Parameters:**
- `key`: Unique identifier
- `value`: Any JSON-serializable data
- `namespace`: Logical grouping (default: "default")
- `ttl`: Time-to-live (default: config.default_ttl)
- `metadata`: Additional metadata dict

**Returns:** True if stored successfully

```python
async def retrieve(key: str, namespace: str = "default") -> Optional[MemoryItem]
```
Retrieve a memory item by key.

**Returns:** MemoryItem if found, None otherwise

```python
async def batch_retrieve(keys: List[str], namespace: str = "default") -> Dict[str, MemoryItem]
```
Retrieve multiple items in one operation.

**Returns:** Dict mapping keys to MemoryItems (missing keys omitted)

```python
async def search(
    namespace: Optional[str] = None,
    tags: Optional[List[str]] = None,
    limit: int = 100
) -> List[MemoryItem]
```
Search for memory items matching criteria.

```python
async def delete(key: str, namespace: str = "default") -> bool
```
Delete a memory item.

```python
async def delete_namespace(namespace: str) -> int
```
Delete all items in a namespace. Returns count deleted.

```python
async def clear() -> bool
```
Clear all memories for this tenant. **Use with caution!**

```python
async def get_statistics() -> WorkingMemoryStats
```
Get usage statistics and metrics.

```python
async def shutdown() -> None
```
Gracefully shutdown, cleanup resources.

### ShortTermMemory

#### Methods

```python
async def start() -> None
```
Start background consolidation tasks.

```python
async def stop() -> None
```
Stop background tasks and cleanup.

```python
async def store(
    key: str,
    value: Any,
    metadata: Optional[MemoryMetadata] = None,
    ttl: Optional[timedelta] = None
) -> bool
```
Store item in short-term memory.

```python
async def retrieve(key: str) -> Optional[MemoryItem]
```
Retrieve item (increments access count for promotion tracking).

```python
async def batch_retrieve(keys: List[str]) -> Dict[str, MemoryItem]
```
Retrieve multiple items efficiently.

```python
async def run_consolidation() -> List[PromotionCandidate]
```
Manually trigger consolidation. Returns promotion candidates.

```python
def register_promotion_callback(callback: Callable) -> None
```
Register callback function called when items are promoted.

**Callback signature:**
```python
async def callback(item: MemoryItem) -> None
```

```python
def get_statistics() -> Dict[str, int]
```
Get consolidation statistics.

---

## Configuration

### Environment Variables

Smrti can be configured via environment variables:

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=smrti_dev_password
REDIS_DB=0

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=smrti
POSTGRES_PASSWORD=smrti_dev_password
POSTGRES_DB=smrti

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=smrti_password

# ChromaDB Configuration
CHROMA_HOST=localhost
CHROMA_PORT=8001

# Application Configuration
SMRTI_TENANT_ID=default
SMRTI_LOG_LEVEL=INFO
SMRTI_ENABLE_METRICS=true

# Memory Tier Configuration
WORKING_MEMORY_MAX_ITEMS=1000
WORKING_MEMORY_EVICTION_POLICY=lru
SHORT_TERM_MEMORY_TTL=86400  # 24 hours
```

### Configuration Files

For advanced configuration, use Python config objects:

```python
from smrti.tiers.working import WorkingMemoryConfig
from smrti.tiers.shortterm import ConsolidationConfig, ConsolidationStrategy

# Working Memory config
working_config = WorkingMemoryConfig(
    max_items=5000,
    max_memory_mb=500,
    eviction_policy="lfu",
    eviction_threshold=0.9,
    batch_eviction_size=50,
    track_access_patterns=True,
    promotion_threshold=3,
    default_ttl=7200
)

# Short-term Memory config
shortterm_config = ConsolidationConfig(
    strategy=ConsolidationStrategy.RECENCY_WEIGHTED,
    promotion_threshold=5,
    consolidation_window=timedelta(hours=2),
    max_items_per_batch=200,
    semantic_similarity_threshold=0.85
)
```

---

## Best Practices

### 1. Choose the Right Tier

```python
# ✅ Good: Use Working Memory for temporary session data
await working_mem.store("current_page", 5)

# ✅ Good: Use Short-term for potentially important data
await short_mem.store("user_feedback", "Loved the feature!")

# ❌ Avoid: Storing large objects in Working Memory
await working_mem.store("large_dataset", huge_list)  # Use disk instead
```

### 2. Use Namespaces Effectively

```python
# ✅ Good: Organize by purpose
await memory.store("user_123", data, namespace="users")
await memory.store("session_abc", data, namespace="sessions")
await memory.store("api_key", data, namespace="credentials")

# ❌ Avoid: Everything in default namespace
await memory.store("user_123", data)  # Hard to manage at scale
```

### 3. Set Appropriate TTLs

```python
# ✅ Good: Match TTL to data lifecycle
await memory.store("oauth_token", token, ttl=timedelta(hours=1))
await memory.store("cache_entry", data, ttl=timedelta(minutes=15))
await memory.store("user_prefs", prefs, ttl=timedelta(days=30))

# ❌ Avoid: Same TTL for everything
await memory.store("anything", data, ttl=timedelta(days=365))
```

### 4. Handle Retrieval Gracefully

```python
# ✅ Good: Check for None
item = await memory.retrieve("user_context")
if item:
    context = item.value
else:
    context = load_default_context()

# ❌ Avoid: Assuming item exists
item = await memory.retrieve("user_context")
context = item.value  # Could be None!
```

### 5. Use Batch Operations

```python
# ✅ Good: Batch retrieve for multiple items
items = await memory.batch_retrieve(["user1", "user2", "user3"])

# ❌ Avoid: Multiple individual calls
items = {}
for key in ["user1", "user2", "user3"]:
    items[key] = await memory.retrieve(key)  # Slower!
```

### 6. Clean Up Resources

```python
# ✅ Good: Always shutdown
async with WorkingMemoryTier(tenant_id="app") as memory:
    await memory.store("data", value)
# Automatic cleanup

# Or manually:
memory = WorkingMemoryTier(tenant_id="app")
try:
    await memory.initialize()
    await memory.store("data", value)
finally:
    await memory.shutdown()  # Always cleanup
```

### 7. Monitor and Observe

```python
# ✅ Good: Check statistics regularly
stats = await memory.get_statistics()
if stats.cache_hit_rate < 0.5:
    logger.warning("Low cache hit rate, consider increasing capacity")

# ✅ Good: Use monitoring tools
# Grafana dashboards at http://localhost:3000
# Prometheus metrics at http://localhost:9090
```

---

## Examples

### Example 1: Chatbot with Context

```python
import asyncio
from smrti.tiers.working import WorkingMemoryTier
from smrti.tiers.shortterm import ShortTermMemory

class ChatbotMemory:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.working = WorkingMemoryTier(tenant_id=f"user_{user_id}")
        self.short_term = ShortTermMemory(tenant_id=f"user_{user_id}")
    
    async def initialize(self):
        await self.working.initialize()
        await self.short_term.start()
    
    async def store_message(self, message: dict):
        """Store message in conversation history."""
        # Recent messages in working memory
        await self.working.store(
            key=f"msg_{message['id']}",
            value=message,
            namespace="conversation",
            ttl=timedelta(hours=1)
        )
        
        # Important messages in short-term
        if message.get('important'):
            await self.short_term.store(
                key=f"important_{message['id']}",
                value=message,
                ttl=timedelta(days=7)
            )
    
    async def get_context(self, limit: int = 10) -> list:
        """Get recent conversation context."""
        items = await self.working.search(
            namespace="conversation",
            limit=limit
        )
        return [item.value for item in sorted(
            items, 
            key=lambda x: x.metadata.created_at
        )]
    
    async def shutdown(self):
        await self.working.shutdown()
        await self.short_term.stop()

# Usage
async def main():
    memory = ChatbotMemory(user_id="alice")
    await memory.initialize()
    
    # Store conversation
    await memory.store_message({
        "id": "msg_1",
        "text": "Hello!",
        "timestamp": "2025-10-03T10:00:00Z",
        "important": False
    })
    
    # Get context for next response
    context = await memory.get_context(limit=5)
    print(f"Context: {context}")
    
    await memory.shutdown()

asyncio.run(main())
```

### Example 2: Caching API Responses

```python
import asyncio
from datetime import timedelta
from smrti.tiers.working import WorkingMemoryTier

class APICache:
    def __init__(self):
        self.cache = WorkingMemoryTier(tenant_id="api_cache")
    
    async def initialize(self):
        await self.cache.initialize()
    
    def _make_key(self, endpoint: str, params: dict) -> str:
        """Create cache key from endpoint and params."""
        import hashlib
        import json
        key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key.encode()).hexdigest()
    
    async def get(self, endpoint: str, params: dict = None):
        """Get cached response or None."""
        params = params or {}
        key = self._make_key(endpoint, params)
        item = await self.cache.retrieve(key, namespace="api_responses")
        return item.value if item else None
    
    async def set(self, endpoint: str, params: dict, response: dict, ttl_minutes: int = 15):
        """Cache API response."""
        params = params or {}
        key = self._make_key(endpoint, params)
        await self.cache.store(
            key=key,
            value=response,
            namespace="api_responses",
            ttl=timedelta(minutes=ttl_minutes)
        )
    
    async def invalidate(self, endpoint: str, params: dict = None):
        """Invalidate cached response."""
        if params is None:
            # Invalidate all for this endpoint
            # (would need search by prefix - future feature)
            pass
        else:
            key = self._make_key(endpoint, params)
            await self.cache.delete(key, namespace="api_responses")

# Usage
async def main():
    cache = APICache()
    await cache.initialize()
    
    # Try cache first
    response = await cache.get("/api/users", {"page": 1})
    if response is None:
        # Cache miss - fetch from API
        response = fetch_from_api("/api/users", {"page": 1})
        # Cache for 15 minutes
        await cache.set("/api/users", {"page": 1}, response, ttl_minutes=15)
    
    print(f"Response: {response}")

asyncio.run(main())
```

### Example 3: User Preferences

```python
import asyncio
from smrti.tiers.shortterm import ShortTermMemory

class UserPreferences:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.memory = ShortTermMemory(tenant_id=f"prefs_{user_id}")
    
    async def initialize(self):
        await self.memory.start()
        
        # Register callback for persistence
        self.memory.register_promotion_callback(self._save_to_database)
    
    async def _save_to_database(self, item):
        """Save promoted preferences to database."""
        print(f"Saving {item.key} to permanent storage")
        # Your database save logic here
    
    async def set(self, preference: str, value: any):
        """Set user preference."""
        await self.memory.store(
            key=f"pref_{preference}",
            value=value,
            ttl=timedelta(days=30)
        )
    
    async def get(self, preference: str, default=None):
        """Get user preference."""
        item = await self.memory.retrieve(f"pref_{preference}")
        return item.value if item else default
    
    async def get_all(self) -> dict:
        """Get all preferences."""
        items = await self.memory.batch_retrieve([
            "pref_theme", "pref_language", "pref_notifications"
        ])
        return {
            key.replace("pref_", ""): item.value 
            for key, item in items.items()
        }

# Usage
async def main():
    prefs = UserPreferences(user_id="alice")
    await prefs.initialize()
    
    # Set preferences
    await prefs.set("theme", "dark")
    await prefs.set("language", "en")
    await prefs.set("notifications", True)
    
    # Get preference
    theme = await prefs.get("theme")
    print(f"Theme: {theme}")
    
    # Get all
    all_prefs = await prefs.get_all()
    print(f"All preferences: {all_prefs}")

asyncio.run(main())
```

---

## Troubleshooting

### Connection Issues

**Problem**: Cannot connect to Redis/PostgreSQL/other services

**Solutions**:
```bash
# Check services are running
make docker-ps
docker ps

# Check logs
docker logs smrti-redis
docker logs smrti-postgres

# Restart services
make docker-down
make docker-dev

# Check network connectivity
docker exec smrti-redis redis-cli ping  # Should return PONG
```

### Memory Issues

**Problem**: "Max items reached" or eviction happening too frequently

**Solutions**:
```python
# Increase capacity
config = WorkingMemoryConfig(
    max_items=5000,  # Increase from default 1000
    max_memory_mb=500  # Increase memory limit
)

# Adjust eviction threshold
config = WorkingMemoryConfig(
    eviction_threshold=0.95  # Evict later (default 0.8)
)

# Use shorter TTLs
await memory.store(key, value, ttl=timedelta(minutes=5))
```

### Performance Issues

**Problem**: Slow retrieve operations

**Solutions**:
```python
# Use batch operations
items = await memory.batch_retrieve(keys)  # Much faster!

# Check cache hit rate
stats = await memory.get_statistics()
print(f"Hit rate: {stats.cache_hit_rate}")

# Increase capacity if hit rate is low
if stats.cache_hit_rate < 0.5:
    # Increase max_items in config
    pass
```

**Problem**: High memory usage

**Solutions**:
```python
# Set TTLs aggressively
await memory.store(key, value, ttl=timedelta(minutes=10))

# Clear old namespaces
await memory.delete_namespace("old_sessions")

# Monitor via Grafana at http://localhost:3000
```

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'smrti'`

**Solutions**:
```bash
# Ensure installed
pip install -e .

# Check installation
python -c "import smrti; print(smrti.__version__)"

# Reinstall if needed
pip uninstall smrti
pip install -e .
```

### Docker Issues

**Problem**: Services showing "unhealthy" status

**Note**: This is usually a health check configuration issue, not a real problem. Verify services are actually responding:

```bash
# Test services directly
curl http://localhost:8888/api  # Jupyter
curl http://localhost:8001/api/v2/heartbeat  # ChromaDB
docker exec smrti-redis redis-cli ping  # Redis

# Check logs for real errors
docker logs smrti-chroma
docker logs smrti-neo4j
```

---

## Roadmap

### Currently Available (v0.2.0)
- ✅ Working Memory tier
- ✅ Short-term Memory tier with consolidation
- ✅ **Long-term Memory tier with vector search**
- ✅ **Episodic Memory with timeline queries**
- ✅ **Context Assembly system**
- ✅ **Hybrid Retrieval engine**
- ✅ Multi-tenancy support
- ✅ Docker-based deployment
- ✅ Basic monitoring (Prometheus, Grafana)
- ✅ Redis and PostgreSQL integration
- ✅ Comprehensive API for storing and retrieving memories

### Coming Soon (v0.3)
- 🚧 Semantic Memory with knowledge graphs
- 🚧 Advanced consolidation strategies
- 🚧 Production adapters for all backends
- 🚧 Cross-encoder reranking
- 🚧 Advanced summarization strategies

### Future (v0.3+)
- 📋 Web UI for memory management
- 📋 Advanced analytics and insights
- 📋 Memory compression and optimization
- 📋 Cross-tenant memory sharing (opt-in)
- 📋 Memory export/import tools
- 📋 Multi-modal memory (images, audio, video)
- 📋 Federated memory across distributed systems

---

## Getting Help

### Documentation
- **User Guide**: This document
- **Development Guide**: `docs/DEVELOPMENT_GUIDE.md`
- **Docker Status**: `docs/DOCKER_STATUS.md`
- **API Docs**: `docs/API.md` *(coming soon)*

### Community
- **GitHub**: [github.com/konf-dev/smrti](https://github.com/konf-dev/smrti)
- **Issues**: Report bugs or request features
- **Discussions**: Ask questions, share examples

### Support
- **Email**: support@smrti.dev *(coming soon)*
- **Slack**: [smrti.slack.com](https://smrti.slack.com) *(coming soon)*

---

## License

Smrti is released under the MIT License. See `LICENSE` file for details.

---

**Last Updated**: October 3, 2025
**Version**: 0.1.0-alpha
**Status**: 🚧 Alpha - Under Active Development

> **Important**: Sections marked with 🚧 describe planned features that are not yet available. The API interfaces are proposed and subject to change. Currently available features are marked with ✅.
> 
> **Available Now (v0.1-alpha)**:
> - Working Memory
> - Short-term Memory
> - Basic consolidation
> - Multi-tenancy
> - Docker deployment
> 
> **Coming in v0.2**:
> - Long-term Memory (vector storage)
> - Episodic Memory (timeline tracking)
> - Semantic Memory (knowledge graphs)
> - Context Assembly
> - Hybrid Retrieval
> 
> Follow our [GitHub repository](https://github.com/konf-dev/smrti) for updates and release notifications.

---

*Built with ❤️ by the Smrti team*
