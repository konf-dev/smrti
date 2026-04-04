# smrti Session State — Feature Spec

**Date:** 2026-04-04
**Status:** Ready for implementation
**Parent spec:** `docs/specs/2026-04-04-konf-platform-design.md` (Section 3.1)

---

## What

Add a lightweight session-scoped KV store to smrti for working memory. This gives agents a scratchpad for intermediate state during complex tasks — plans, sub-task lists, accumulated results — without cluttering the long-term knowledge graph.

## Why

- Agents working on multi-step tasks need somewhere to store intermediate state
- Storing scratchpad data as graph nodes creates noise (not searchable, not relational, temporary by nature)
- A separate state service would duplicate smrti's namespace isolation, Postgres connection, and auth boundary
- Keeping it in smrti means one library owns all per-user data storage

## Requirements

### API Surface

Add to the Memory class (Layer 1):

```python
async def state_set(self, key: str, value: Any, *, session_id: str, namespace: str = None) -> dict
async def state_get(self, key: str, *, session_id: str, namespace: str = None) -> dict
async def state_delete(self, key: str, *, session_id: str, namespace: str = None) -> dict
async def state_clear(self, *, session_id: str, namespace: str = None) -> dict
async def state_list(self, *, session_id: str, namespace: str = None) -> dict
```

All return dicts with `_meta` (consistent with existing smrti API pattern).

Add to StorageProvider trait (Layer 2):

```rust
async fn state_set(&self, namespace: &str, session_id: &str, key: &str, value: Value) -> Result<(), SmrtiError>;
async fn state_get(&self, namespace: &str, session_id: &str, key: &str) -> Result<Option<Value>, SmrtiError>;
async fn state_delete(&self, namespace: &str, session_id: &str, key: &str) -> Result<bool, SmrtiError>;
async fn state_clear(&self, namespace: &str, session_id: &str) -> Result<u64, SmrtiError>;
async fn state_list(&self, namespace: &str, session_id: &str) -> Result<Vec<(String, Value)>, SmrtiError>;
```

### Storage

New Postgres table:

```sql
CREATE TABLE session_state (
    namespace   TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,              -- optional TTL, NULL = no expiry
    PRIMARY KEY (namespace, session_id, key)
);

CREATE INDEX idx_session_state_expiry ON session_state (expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_session_state_session ON session_state (namespace, session_id);
```

### Behavior

- `state_set` upserts (INSERT ON CONFLICT UPDATE). Overwrites value and resets `updated_at`.
- `state_get` returns `None`/null if key doesn't exist or has expired.
- `state_delete` removes a single key. Returns whether the key existed.
- `state_clear` removes ALL keys for a session. Returns count of keys removed.
- `state_list` returns all non-expired keys for a session as `[(key, value)]`.
- Expired rows are filtered on read (`WHERE expires_at IS NULL OR expires_at > NOW()`).
- Expired rows are cleaned up periodically (lazy cleanup on read is fine; optional background cleanup).

### TTL

`state_set` accepts an optional `ttl_seconds: int` parameter. If set, `expires_at = NOW() + interval`. If not set, `expires_at = NULL` (lives until explicitly cleared or session ends).

```python
# Expires in 1 hour
await memory.state_set("plan", {"steps": [...]}, session_id="abc", ttl_seconds=3600)

# No expiry — lives until state_clear
await memory.state_set("preferences", {"format": "markdown"}, session_id="abc")
```

### Configuration

Add to `SmrtiConfig`:

```python
session_state_default_ttl: int | None = None       # default TTL in seconds, None = no expiry
session_state_cleanup_interval: int = 3600          # seconds between expired row cleanup (0 = disabled)
```

### What This Is NOT

- NOT event-sourced. No events in the event log. This is ephemeral state.
- NOT searchable. No embeddings, no full-text search, no vector index.
- NOT graph data. No nodes, no edges, no relationships.
- NOT a cache. It's user-facing working memory, not an optimization layer.

### Error Handling

- `state_get` for non-existent key: returns `{"value": null, "_meta": {"found": false}}`
- `state_set` with invalid value (not JSON-serializable): raises `ValidationError`
- `state_clear` for non-existent session: returns `{"cleared": 0, "_meta": {...}}` (not an error)

### Testing

- Basic CRUD: set, get, delete, clear, list
- Upsert: set same key twice, verify overwrite
- TTL: set with TTL, verify expiry filtering
- Namespace isolation: set in namespace A, verify not visible in namespace B
- Session isolation: set in session A, verify not visible in session B
- Concurrent access: multiple sets to same key from different tasks
- Large values: JSONB with nested structures, arrays
- state_list ordering: consistent ordering (by key name)
