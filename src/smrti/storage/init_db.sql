-- PostgreSQL schema for Smrti memory storage
-- Tables for EPISODIC and SEMANTIC memory tiers

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For full-text search

-- ============================================================================
-- EPISODIC MEMORIES TABLE
-- ============================================================================
-- Purpose: Store time-series events and experiences
-- Retrieval: Time-range queries, full-text search, event type filtering
-- Performance: Indexed on timestamp, namespace, event_type

CREATE TABLE IF NOT EXISTS episodic_memories (
    memory_id UUID PRIMARY KEY,
    namespace VARCHAR(500) NOT NULL,
    memory_type VARCHAR(50) NOT NULL DEFAULT 'EPISODIC',
    
    -- Core data
    text TEXT NOT NULL,
    data JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    
    -- Temporal fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_time TIMESTAMPTZ,  -- Time when event occurred (may differ from created_at)
    
    -- Event classification
    event_type VARCHAR(100),  -- e.g., "goal", "observation", "action", "outcome"
    
    -- Full-text search
    search_vector tsvector
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_episodic_namespace ON episodic_memories(namespace);
CREATE INDEX IF NOT EXISTS idx_episodic_created_at ON episodic_memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_event_time ON episodic_memories(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_event_type ON episodic_memories(event_type);
CREATE INDEX IF NOT EXISTS idx_episodic_namespace_time ON episodic_memories(namespace, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_search_vector ON episodic_memories USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_episodic_metadata ON episodic_memories USING GIN(metadata);

-- Trigger to automatically update search_vector
CREATE OR REPLACE FUNCTION episodic_memories_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.text, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.event_type, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.data::text, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS episodic_memories_search_update ON episodic_memories;
CREATE TRIGGER episodic_memories_search_update 
    BEFORE INSERT OR UPDATE ON episodic_memories
    FOR EACH ROW EXECUTE FUNCTION episodic_memories_search_trigger();

-- ============================================================================
-- SEMANTIC MEMORIES TABLE
-- ============================================================================
-- Purpose: Store structured knowledge, entities, relationships
-- Retrieval: Entity lookup, relationship traversal, graph queries
-- Performance: Indexed on entities and relationships JSONB fields

CREATE TABLE IF NOT EXISTS semantic_memories (
    memory_id UUID PRIMARY KEY,
    namespace VARCHAR(500) NOT NULL,
    memory_type VARCHAR(50) NOT NULL DEFAULT 'SEMANTIC',
    
    -- Core data
    text TEXT NOT NULL,
    data JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    
    -- Temporal fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Semantic fields
    entities JSONB NOT NULL DEFAULT '[]',  -- Array of entities: [{"type": "person", "name": "Alice"}]
    relationships JSONB NOT NULL DEFAULT '[]',  -- Array of relationships: [{"from": "Alice", "to": "Bob", "type": "knows"}]
    
    -- Knowledge classification
    knowledge_type VARCHAR(100),  -- e.g., "fact", "rule", "concept", "definition"
    confidence FLOAT DEFAULT 1.0,  -- Confidence score (0.0-1.0)
    
    -- Full-text search
    search_vector tsvector
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_semantic_namespace ON semantic_memories(namespace);
CREATE INDEX IF NOT EXISTS idx_semantic_created_at ON semantic_memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_semantic_knowledge_type ON semantic_memories(knowledge_type);
CREATE INDEX IF NOT EXISTS idx_semantic_entities ON semantic_memories USING GIN(entities);
CREATE INDEX IF NOT EXISTS idx_semantic_relationships ON semantic_memories USING GIN(relationships);
CREATE INDEX IF NOT EXISTS idx_semantic_metadata ON semantic_memories USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_semantic_search_vector ON semantic_memories USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_semantic_confidence ON semantic_memories(confidence DESC);

-- Specialized indexes for entity lookup
CREATE INDEX IF NOT EXISTS idx_semantic_entities_jsonb_path ON semantic_memories USING GIN((entities -> 'name'));
CREATE INDEX IF NOT EXISTS idx_semantic_entities_jsonb_type ON semantic_memories USING GIN((entities -> 'type'));

-- Trigger to automatically update search_vector and updated_at
CREATE OR REPLACE FUNCTION semantic_memories_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.text, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.knowledge_type, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.data::text, '')), 'C') ||
        setweight(to_tsvector('english', COALESCE(NEW.entities::text, '')), 'C');
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS semantic_memories_search_update ON semantic_memories;
CREATE TRIGGER semantic_memories_search_update 
    BEFORE INSERT OR UPDATE ON semantic_memories
    FOR EACH ROW EXECUTE FUNCTION semantic_memories_search_trigger();

-- ============================================================================
-- UTILITY VIEWS
-- ============================================================================

-- View for recent episodic memories by namespace
CREATE OR REPLACE VIEW recent_episodic_by_namespace AS
SELECT 
    namespace,
    COUNT(*) as memory_count,
    MAX(created_at) as latest_memory,
    MIN(created_at) as oldest_memory
FROM episodic_memories
GROUP BY namespace;

-- View for semantic knowledge by entity
CREATE OR REPLACE VIEW semantic_by_entity AS
SELECT 
    namespace,
    jsonb_array_elements(entities) as entity,
    COUNT(*) as memory_count
FROM semantic_memories
GROUP BY namespace, entity;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE episodic_memories IS 'Time-series storage for events and experiences';
COMMENT ON TABLE semantic_memories IS 'Structured knowledge storage with entities and relationships';

COMMENT ON COLUMN episodic_memories.namespace IS 'Hierarchical namespace for multi-tenant isolation (e.g., tenant:123:user:456)';
COMMENT ON COLUMN episodic_memories.event_type IS 'Classification of event: goal, observation, action, outcome, etc.';
COMMENT ON COLUMN episodic_memories.search_vector IS 'Full-text search vector (auto-generated)';

COMMENT ON COLUMN semantic_memories.entities IS 'Array of entities: [{"type": "person", "name": "Alice", "id": "..."}]';
COMMENT ON COLUMN semantic_memories.relationships IS 'Array of relationships: [{"from": "entity1", "to": "entity2", "type": "knows"}]';
COMMENT ON COLUMN semantic_memories.confidence IS 'Confidence score for knowledge validity (0.0-1.0)';
