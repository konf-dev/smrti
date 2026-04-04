# Error Handling Guide

## Philosophy

smrti errors are designed for three audiences simultaneously:

1. **Developers** debugging integration issues
2. **LLMs** calling smrti as a tool and needing to decide what to do next
3. **End users** who may see error messages surfaced through an agent

Every exception is typed (so you can catch specific failures), includes a human-readable message (so LLMs can report it), and carries enough context to determine the correct recovery action.

All exceptions inherit from `SmrtiError`. You can catch the base class to handle all smrti errors, or catch specific subclasses for targeted recovery.

```python
from smrti.errors import (
    SmrtiError,
    ConnectionError,
    MigrationError,
    EventError,
    ExtractionError,
    EmbeddingError,
    NodeNotFoundError,
    EdgeNotFoundError,
    ValidationError,
    SearchError,
    NamespaceError,
)
```

## Exception Reference

### SmrtiError

The base class for all smrti exceptions. Never raised directly -- always a subclass.

```python
try:
    result = await memory.search("test")
except SmrtiError as e:
    # Catches any smrti error
    print(f"smrti error: {e}")
```

**LLM action:** Report the error message to the user.

---

### ConnectionError

**When raised:** Database is unreachable, connection pool creation fails, connection timeout.

**Example message:** `"Failed to connect: connection refused on localhost:5432"`

**What to do about it:**
- Check that PostgreSQL is running and reachable at the configured DSN
- Verify credentials
- Check network/firewall rules
- Ensure the database exists

```python
try:
    await memory.connect()
except ConnectionError as e:
    print(f"Database unreachable: {e}")
    # Do not retry immediately -- fix the connection first
```

**LLM action:** Tell the user to check the database connection and credentials. Do not retry.

---

### MigrationError

**When raised:** A SQL migration file fails to execute during `connect()` or `migrate()`.

**Example message:** `"Failed to apply v001_initial.sql: relation \"nodes\" already exists with incompatible schema"`

**What to do about it:**
- This usually indicates a version mismatch between the smrti library and the database schema
- Check if the database was previously used with a different version of smrti
- Consider running `memory.rebuild()` if projections are corrupted (events are preserved)

```python
try:
    await memory.connect()
except MigrationError as e:
    print(f"Schema issue: {e}")
```

**LLM action:** Tell the user there is a database schema issue, likely a version mismatch. Do not retry.

---

### EventError

**When raised:** `apply_event()` fails during the projection update step. The event and its projection are rolled back atomically -- no partial state.

**Example message:** `"Projection failed for NODE_CREATED: duplicate key violates unique constraint"`

**What to do about it:**
- Retry the operation -- this can be a transient issue (deadlock, serialization failure)
- If persistent, the event payload may conflict with existing data
- Check that node_key values are unique within their namespace

```python
try:
    result = await memory.add_nodes([{"node_type": "person", "content": "Alice"}])
except EventError as e:
    print(f"Event failed: {e}")
    # Retry is reasonable here
```

**LLM action:** Retry the operation. If it persists, report to the developer.

---

### ExtractionError

**When raised:** The LLM extraction pipeline fails, or `store()` is called without an `llm_provider` configured.

**Example messages:**
- `"LLM provider not configured"`
- `"Extraction failed: LLM returned invalid JSON"`
- `"Extraction failed: rate limit exceeded"`

**What to do about it:**
- If "provider not configured": set `llm_provider` in `SmrtiConfig`, or use low-level methods (`add_nodes`, `add_edges`) instead of `store()`
- If LLM failure: check LLM provider status, API key, rate limits
- If invalid JSON: the LLM produced unparseable output -- retry (LLMs are non-deterministic)

```python
try:
    result = await memory.store("Alice works at Acme Corp", wait=True)
except ExtractionError as e:
    if "not configured" in str(e):
        # Use low-level API instead
        await memory.add_nodes([...])
    else:
        # LLM failure -- retry
        result = await memory.store("Alice works at Acme Corp", wait=True)
```

**LLM action:** If provider missing, tell the user that `store()` requires an LLM provider. If LLM failure, retry once.

---

### EmbeddingError

**When raised:** The embedding provider fails (network error, model not found, API key invalid).

**Example messages:**
- `"Embedding failed: model 'nomic-embed-text' not found"`
- `"Embedding failed: connection refused on localhost:11434"`

**What to do about it:**
- Check that the embedding provider is running (e.g., Ollama is started, OpenAI API is reachable)
- Verify the model name is correct
- Check API credentials

```python
try:
    result = await memory.add_nodes([{"node_type": "fact", "content": "test"}])
except EmbeddingError as e:
    print(f"Embedding provider issue: {e}")
```

**LLM action:** Retry once. If persistent, check embedding provider configuration.

---

### NodeNotFoundError

**When raised:** An operation references a node ID that does not exist in the database.

**Example message:** `"Node not found: 550e8400-e29b-41d4-a716-446655440000"`

**What to do about it:**
- Verify the node ID is correct (typo? wrong UUID?)
- The node may have been retracted (soft-deleted) -- retracted nodes are excluded from most lookups
- Search for the node by content instead of ID

```python
try:
    result = await memory.update_node("bad-uuid", content="new content")
except NodeNotFoundError as e:
    print(f"Node not found: {e}")
    # Try searching for it instead
    results = await memory.search("the content I'm looking for")
```

**LLM action:** Verify the node ID. It may have been retracted. Search by content as a fallback.

---

### EdgeNotFoundError

**When raised:** An operation references an edge ID that does not exist.

**Example message:** `"Edge not found: 550e8400-e29b-41d4-a716-446655440000"`

**What to do about it:**
- Verify the edge ID is correct
- The edge may have been retracted
- List edges for the relevant node with `memory.get_edges(node_id)` to find valid edge IDs

```python
try:
    result = await memory.retract_edge("bad-edge-id")
except EdgeNotFoundError as e:
    print(f"Edge not found: {e}")
```

**LLM action:** Verify the edge ID is correct. List the node's edges to find valid IDs.

---

### ValidationError

**When raised:** Input validation fails. This covers missing required fields, invalid types, invalid enum values, empty strings, and constraint violations.

**Example messages:**
- `"Validation error: node_type is required"`
- `"Validation error: mode must be 'vector', 'text', or 'hybrid'"`
- `"Validation error: text cannot be empty"`
- `"Validation error: no fields provided for update"`

**What to do about it:**
- Read the error message -- it tells you exactly what's wrong
- Fix the input and retry

```python
try:
    result = await memory.search("test", mode="invalid")
except ValidationError as e:
    print(f"Bad input: {e}")
    # Fix the mode parameter
    result = await memory.search("test", mode="hybrid")
```

**LLM action:** Fix the input parameters and retry immediately.

---

### SearchError

**When raised:** A search operation fails due to configuration or state issues (not input validation).

**Example messages:**
- `"Search failed: vector mode requires an embedding but embedding failed"`
- `"Search failed: no embeddings exist for model 'unknown-model'"`

**What to do about it:**
- Check search parameters (mode, namespace)
- Ensure nodes have been embedded with the expected model
- Fall back to text mode if vector search is unavailable

```python
try:
    result = await memory.search("test", mode="vector")
except SearchError as e:
    # Fall back to text search
    result = await memory.search("test", mode="text")
```

**LLM action:** Check search parameters. Consider falling back to a different search mode.

---

### NamespaceError

**When raised:** A namespace string is invalid (empty, contains invalid characters).

**Example message:** `"Invalid namespace: namespace cannot be empty"`

**What to do about it:**
- Provide a valid, non-empty namespace string
- Common pattern: `"user:{id}"`, `"team:{name}"`, `"project:{slug}"`

```python
try:
    result = await memory.search("test", namespace="")
except NamespaceError as e:
    result = await memory.search("test", namespace="default")
```

**LLM action:** Provide a valid namespace string and retry.

## Error Propagation

Errors flow through two layers, but the contract is simple:

1. **Provider layer** (PostgresProvider) raises typed exceptions when database operations fail
2. **Memory layer** passes them through unchanged -- no wrapping, no transformation

This means the exception you catch from `memory.search()` is the same exception that the provider raised. The error type and message are always accurate to the root cause.

```python
# These raise the same exception types:
await memory.search(...)        # Memory layer -- passes through
await provider.search_nodes(...) # Provider layer -- originates the error
```

## Idempotent Operations

Some operations are designed to be safe to repeat without errors:

- **Retract an already-retracted node:** Returns `False` / a no-op result. Does not raise `NodeNotFoundError`.
- **Retract an already-retracted edge:** Same behavior -- returns gracefully, no error.
- **`close()` called multiple times:** No-op after the first call.
- **`connect()` with already-applied migrations:** Migrations are tracked and skipped if already applied.

This is intentional. Idempotent operations simplify retry logic and make LLM tool calling more robust -- an LLM that accidentally calls retract twice won't crash the conversation.

## How LLMs Should Interpret Errors

When smrti is used as a tool by an LLM agent, the error type determines the correct action:

| Error Type | Action |
|-----------|--------|
| `ValidationError` | Fix the parameters and retry immediately |
| `NodeNotFoundError` | Search for the node by content instead of ID |
| `EdgeNotFoundError` | List edges for the node to find valid IDs |
| `SearchError` | Try a different search mode or check namespace |
| `NamespaceError` | Use a valid namespace string |
| `EmbeddingError` | Retry once, then report to user |
| `EventError` | Retry once, then report to user |
| `ExtractionError` | If missing provider, use low-level API. Otherwise retry once |
| `ConnectionError` | Report to user -- cannot recover without human intervention |
| `MigrationError` | Report to user -- cannot recover without human intervention |

The general rule: **ValidationError and NotFoundError are fixable by the LLM. ConnectionError and MigrationError require human intervention. Everything else deserves one retry.**
