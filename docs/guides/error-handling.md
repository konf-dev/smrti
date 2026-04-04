# Error handling

## Exception types

smrti raises standard Python exceptions:

| Exception | When |
|---|---|
| `ValueError` | Validation errors: bad config, missing required fields, invalid UUIDs, invalid search mode, etc. |
| `RuntimeError` | All other errors: connection failures, migration errors, database errors, node-not-found, event serialization, etc. |

There is no custom exception hierarchy. All errors include a descriptive message string.

## Common patterns

### Connection errors

```python
from smrti import Memory

try:
    memory = Memory.connect("postgresql://localhost:5432/nonexistent")
except RuntimeError as e:
    print(f"Could not connect: {e}")
```

### Validation errors

```python
try:
    memory = Memory.connect(
        "postgresql://localhost/myapp",
        pool_max=0,
    )
except ValueError as e:
    print(f"Bad config: {e}")
```

### Missing required fields

```python
try:
    memory.add_nodes([{"content": "missing node_type"}])
except ValueError as e:
    print(e)  # "node_type is required"
```

### Invalid node ID

```python
try:
    memory.retract_node("not-a-uuid")
except ValueError as e:
    print(e)  # "Invalid node_id: ..."
```

### Empty input

```python
try:
    memory.add_nodes([])
except ValueError as e:
    print(e)  # "nodes list is empty"
```

### Search mode mismatch

```python
try:
    # hybrid mode requires both query_vector and text_query
    memory.search(text_query="hello", mode="hybrid")
except ValueError as e:
    print(e)  # "hybrid mode requires both query_vector and text_query"
```

### Node not found

```python
try:
    memory.update_node("00000000-0000-0000-0000-000000000000", content="new")
except RuntimeError as e:
    print(e)  # node not found error
```

## Best practices

1. **Catch `ValueError` for input problems** -- these are always fixable by the caller.
2. **Catch `RuntimeError` for infrastructure problems** -- connection drops, timeouts, etc. Consider retrying with backoff.
3. **Use `_meta` for diagnostics** -- every successful response includes `_meta` with `duration_ms` and other operational data. Log it.
4. **Validate early** -- check that embeddings are the right dimensionality before calling `add_nodes()`. smrti will store whatever you pass, but mismatched dimensions will produce bad search results.
