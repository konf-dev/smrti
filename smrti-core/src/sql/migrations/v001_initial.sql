-- smrti v001: Initial schema
-- PostgreSQL + pgvector + pg_trgm

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Migration tracking
CREATE TABLE IF NOT EXISTS smrti_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Event log (source of truth, append-only)
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    namespace  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload    JSONB NOT NULL DEFAULT '{}',
    metadata   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_namespace
    ON events (namespace);
CREATE INDEX IF NOT EXISTS idx_events_namespace_created
    ON events (namespace, created_at DESC);

-- Nodes (projection from events)
CREATE TABLE IF NOT EXISTS nodes (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace     TEXT NOT NULL,
    node_key      TEXT,
    node_type     TEXT NOT NULL,
    content       TEXT NOT NULL,
    content_type  TEXT NOT NULL DEFAULT 'text',
    metadata      JSONB NOT NULL DEFAULT '{}',
    search_vector TSVECTOR,
    is_retracted  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_namespace_key
    ON nodes (namespace, node_key) WHERE node_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_nodes_namespace
    ON nodes (namespace);
CREATE INDEX IF NOT EXISTS idx_nodes_namespace_type
    ON nodes (namespace, node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_namespace_retracted
    ON nodes (namespace, is_retracted);
CREATE INDEX IF NOT EXISTS idx_nodes_metadata
    ON nodes USING GIN (metadata jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_nodes_search_vector
    ON nodes USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_nodes_content_trgm
    ON nodes USING GIN (content gin_trgm_ops);

-- tsvector trigger (uses 'english' by default - provider updates if config differs)
CREATE OR REPLACE FUNCTION smrti_nodes_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_nodes_search_vector ON nodes;
CREATE TRIGGER trg_nodes_search_vector
    BEFORE INSERT OR UPDATE OF content ON nodes
    FOR EACH ROW
    EXECUTE FUNCTION smrti_nodes_search_vector_update();

-- Node embeddings (separate table for multi-model support)
CREATE TABLE IF NOT EXISTS node_embeddings (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    node_id    UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    embedding  vector,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (node_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_node_id
    ON node_embeddings (node_id);

-- HNSW indexes are created dynamically per model_name + dimension.
-- See PostgresProvider._ensure_hnsw_index()

-- Edges (projection from events, with temporal validity)
CREATE TABLE IF NOT EXISTS edges (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace      TEXT NOT NULL,
    source_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    edge_type      TEXT NOT NULL,
    metadata       JSONB NOT NULL DEFAULT '{}',
    valid_from     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to       TIMESTAMPTZ,
    is_retracted   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- No UNIQUE constraint on (source_node_id, target_node_id, edge_type).
-- This is intentional: multiple edges of the same type between the same
-- nodes are valid (e.g., multiple TRACKS_METRIC entries). See A1 principle.

CREATE INDEX IF NOT EXISTS idx_edges_source
    ON edges (source_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_target
    ON edges (target_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_namespace_type
    ON edges (namespace, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_validity
    ON edges (valid_from, valid_to);

-- Convenience view: active edges (non-retracted, temporally valid)
CREATE OR REPLACE VIEW active_edges AS
SELECT *
FROM edges
WHERE is_retracted = FALSE
  AND valid_from <= NOW()
  AND (valid_to IS NULL OR valid_to >= NOW());

-- GDPR audit log (no user data, only purge records)
CREATE TABLE IF NOT EXISTS smrti_audit_log (
    id         BIGSERIAL PRIMARY KEY,
    action     TEXT NOT NULL,
    namespace  TEXT,
    details    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
