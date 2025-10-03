-- ==============================================================================
-- Smrti PostgreSQL Database Initialization
-- Episodic Memory Table Structures and Indexes
-- ==============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create schema for smrti
CREATE SCHEMA IF NOT EXISTS smrti;

-- ==============================================================================
-- EPISODIC MEMORY TABLES
-- ==============================================================================

-- Main episodic events table
CREATE TABLE IF NOT EXISTS smrti.episodic_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant VARCHAR(128) NOT NULL,
    namespace VARCHAR(128) NOT NULL,
    user_id VARCHAR(256),
    event_type VARCHAR(64) NOT NULL,
    event_data JSONB NOT NULL,
    content TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id VARCHAR(128),
    sequence_number INTEGER,
    metadata JSONB DEFAULT '{}',
    embedding_vector REAL[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Event sequences for temporal ordering
CREATE TABLE IF NOT EXISTS smrti.event_sequences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant VARCHAR(128) NOT NULL,
    namespace VARCHAR(128) NOT NULL,
    user_id VARCHAR(256),
    session_id VARCHAR(128) NOT NULL,
    sequence_name VARCHAR(256),
    start_timestamp TIMESTAMPTZ NOT NULL,
    end_timestamp TIMESTAMPTZ,
    event_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Event relationships for causal chains
CREATE TABLE IF NOT EXISTS smrti.event_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_event_id UUID NOT NULL REFERENCES smrti.episodic_events(id) ON DELETE CASCADE,
    target_event_id UUID NOT NULL REFERENCES smrti.episodic_events(id) ON DELETE CASCADE,
    relationship_type VARCHAR(64) NOT NULL, -- 'caused_by', 'followed_by', 'related_to'
    strength REAL DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==============================================================================
-- INDEXES FOR PERFORMANCE
-- ==============================================================================

-- Primary access patterns
CREATE INDEX IF NOT EXISTS idx_episodic_events_tenant_namespace 
    ON smrti.episodic_events(tenant, namespace);
    
CREATE INDEX IF NOT EXISTS idx_episodic_events_user_timestamp 
    ON smrti.episodic_events(user_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_episodic_events_session 
    ON smrti.episodic_events(session_id, sequence_number);

-- Temporal queries
CREATE INDEX IF NOT EXISTS idx_episodic_events_timestamp 
    ON smrti.episodic_events USING BRIN(timestamp);
    
CREATE INDEX IF NOT EXISTS idx_episodic_events_event_type_timestamp 
    ON smrti.episodic_events(event_type, timestamp DESC);

-- Full-text search on content
CREATE INDEX IF NOT EXISTS idx_episodic_events_content_gin 
    ON smrti.episodic_events USING GIN(to_tsvector('english', content));

-- JSON metadata queries
CREATE INDEX IF NOT EXISTS idx_episodic_events_metadata_gin 
    ON smrti.episodic_events USING GIN(metadata);
    
CREATE INDEX IF NOT EXISTS idx_episodic_events_event_data_gin 
    ON smrti.episodic_events USING GIN(event_data);

-- Sequence-based queries
CREATE INDEX IF NOT EXISTS idx_event_sequences_session 
    ON smrti.event_sequences(tenant, namespace, session_id);
    
CREATE INDEX IF NOT EXISTS idx_event_sequences_timerange 
    ON smrti.event_sequences(start_timestamp, end_timestamp);

-- Relationship queries
CREATE INDEX IF NOT EXISTS idx_event_relationships_source 
    ON smrti.event_relationships(source_event_id, relationship_type);
    
CREATE INDEX IF NOT EXISTS idx_event_relationships_target 
    ON smrti.event_relationships(target_event_id, relationship_type);

-- ==============================================================================
-- FUNCTIONS AND TRIGGERS
-- ==============================================================================

-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION smrti.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply update triggers
CREATE TRIGGER update_episodic_events_updated_at 
    BEFORE UPDATE ON smrti.episodic_events 
    FOR EACH ROW EXECUTE FUNCTION smrti.update_updated_at_column();

-- Sequence counter update function
CREATE OR REPLACE FUNCTION smrti.update_event_sequence_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE smrti.event_sequences 
        SET event_count = event_count + 1,
            end_timestamp = NEW.timestamp
        WHERE session_id = NEW.session_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE smrti.event_sequences 
        SET event_count = event_count - 1
        WHERE session_id = OLD.session_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ language 'plpgsql';

-- Apply sequence counter trigger
CREATE TRIGGER update_sequence_count_on_event_change
    AFTER INSERT OR DELETE ON smrti.episodic_events
    FOR EACH ROW EXECUTE FUNCTION smrti.update_event_sequence_count();

-- ==============================================================================
-- VIEWS FOR COMMON QUERIES
-- ==============================================================================

-- Recent events view with user context
CREATE OR REPLACE VIEW smrti.recent_events AS
SELECT 
    e.id,
    e.tenant,
    e.namespace, 
    e.user_id,
    e.event_type,
    e.content,
    e.timestamp,
    e.session_id,
    e.sequence_number,
    s.sequence_name,
    e.metadata
FROM smrti.episodic_events e
LEFT JOIN smrti.event_sequences s ON e.session_id = s.session_id
WHERE e.timestamp >= NOW() - INTERVAL '7 days'
ORDER BY e.timestamp DESC;

-- Event chains view for causal analysis
CREATE OR REPLACE VIEW smrti.event_chains AS
SELECT 
    r.relationship_type,
    r.strength,
    e1.id as source_id,
    e1.event_type as source_type,
    e1.timestamp as source_timestamp,
    e1.content as source_content,
    e2.id as target_id,
    e2.event_type as target_type, 
    e2.timestamp as target_timestamp,
    e2.content as target_content
FROM smrti.event_relationships r
JOIN smrti.episodic_events e1 ON r.source_event_id = e1.id
JOIN smrti.episodic_events e2 ON r.target_event_id = e2.id
ORDER BY e1.timestamp, r.strength DESC;

-- ==============================================================================
-- PERMISSIONS
-- ==============================================================================

-- Grant permissions to smrti user
GRANT ALL PRIVILEGES ON SCHEMA smrti TO smrti;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA smrti TO smrti;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA smrti TO smrti;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA smrti TO smrti;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA smrti GRANT ALL ON TABLES TO smrti;
ALTER DEFAULT PRIVILEGES IN SCHEMA smrti GRANT ALL ON SEQUENCES TO smrti;
ALTER DEFAULT PRIVILEGES IN SCHEMA smrti GRANT ALL ON FUNCTIONS TO smrti;

-- ==============================================================================
-- SAMPLE DATA (for development)
-- ==============================================================================

-- Insert sample event sequences
INSERT INTO smrti.event_sequences (tenant, namespace, user_id, session_id, sequence_name, start_timestamp) VALUES
('demo_tenant', 'chat', 'user_123', 'session_001', 'customer_inquiry', NOW() - INTERVAL '1 hour'),
('demo_tenant', 'chat', 'user_456', 'session_002', 'support_ticket', NOW() - INTERVAL '30 minutes');

-- Insert sample events
INSERT INTO smrti.episodic_events (tenant, namespace, user_id, event_type, event_data, content, session_id, sequence_number) VALUES
('demo_tenant', 'chat', 'user_123', 'message_sent', '{"type": "user_message"}', 'Hello, I need help with my account', 'session_001', 1),
('demo_tenant', 'chat', 'user_123', 'message_received', '{"type": "bot_response"}', 'Hi! I can help you with your account. What specific issue are you experiencing?', 'session_001', 2),
('demo_tenant', 'chat', 'user_456', 'ticket_created', '{"priority": "high", "category": "billing"}', 'User created billing inquiry ticket', 'session_002', 1);

COMMIT;