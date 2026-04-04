-- smrti v002: Session state (working memory)
-- Lightweight KV store scoped by namespace + session.
-- NOT event-sourced, NOT searchable — ephemeral scratchpad.

CREATE TABLE IF NOT EXISTS session_state (
    namespace   TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,
    PRIMARY KEY (namespace, session_id, key)
);

CREATE INDEX IF NOT EXISTS idx_session_state_expiry
    ON session_state (expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_session_state_session
    ON session_state (namespace, session_id);
