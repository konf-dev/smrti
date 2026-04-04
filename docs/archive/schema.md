# smrti — Database Schema (PostgreSQL + pgvector)

Version: 0.1.1
Last Updated: 2026-04-04

This document defines the PostgreSQL schema for `smrti`. It is optimized for `pgvector` and `JSONB` for high-performance vector search and structured metadata filtering.

---

## 1. Core Extensions

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

---

## 2. The Event Log (Source of Truth)

Immutable record of every change. Every write to `smrti` MUST begin here.

```sql
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    namespace TEXT NOT NULL,
    event_type TEXT NOT NULL, -- e.g., 'NODE_CREATED', 'EDGE_ADDED', 'RETRACTION'
    payload JSONB NOT NULL,    -- The full data of the event (node/edge data)
    metadata JSONB,            -- System metadata (model versions, timestamps, prompt IDs)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_namespace ON events(namespace);
CREATE INDEX idx_events_created_at ON events(created_at);
```

---

## 3. Nodes (Projection)

Current state of entities, facts, or concepts.

```sql
CREATE TABLE nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace TEXT NOT NULL,
    node_key TEXT,            -- Optional unique key for "Identity Anchoring" (e.g., 'user_123')
    node_type TEXT NOT NULL,  -- User-defined type (e.g., 'person', 'task', 'concept')
    content TEXT NOT NULL,    -- The actual memory content / description
    content_type TEXT NOT NULL DEFAULT 'text',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(namespace, node_key) -- Ensures node_key is unique per namespace
);

CREATE INDEX idx_nodes_namespace ON nodes(namespace);
CREATE INDEX idx_nodes_type ON nodes(node_type);
CREATE INDEX idx_nodes_metadata ON nodes USING GIN (metadata);
```

---

## 4. Node Embeddings (Vector Storage)

Stored separately to allow multiple embedding models per node (D19).

```sql
CREATE TABLE node_embeddings (
    id BIGSERIAL PRIMARY KEY,
    node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    embedding vector,         -- Dimension-agnostic; index requires fixed dimension
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_embeddings_node_id ON node_embeddings(node_id);
-- Note: Indexing 'vector' without dimension works in pgvector 0.5.0+, 
-- but high-performance HNSW indexes usually require a specific dimension.
-- Implementation should create indexes like:
-- CREATE INDEX ... ON node_embeddings USING hnsw (embedding vector_cosine_ops);
```

---

## 5. Edges (Temporal Relationships)

Typed connections between nodes with temporal validity (D27).

```sql
CREATE TABLE edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace TEXT NOT NULL,
    source_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,  -- e.g., 'WORKS_AT', 'LIVES_IN'
    metadata JSONB DEFAULT '{}',
    
    -- Temporal Validity
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ, -- NULL means "currently true"
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_edges_source ON edges(source_node_id);
CREATE INDEX idx_edges_target ON edges(target_node_id);
CREATE INDEX idx_edges_type ON edges(edge_type);
CREATE INDEX idx_edges_validity ON edges(valid_from, valid_to);
```

---

## 6. Convenience Views

```sql
CREATE VIEW active_edges AS
SELECT * FROM edges
WHERE valid_from <= NOW() 
  AND (valid_to IS NULL OR valid_to >= NOW());
```
