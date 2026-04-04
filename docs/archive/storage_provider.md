# smrti — StorageProvider Specification

This document defines the interface and architectural requirements for the `smrti` storage layer.

---

## 1. Core Interface (Protocol)

The `StorageProvider` is the gateway to the database. It handles the atomicity of the event log and the efficiency of the projections.

### High-Level Requirements
- **Async-first:** All database operations are `awaitable`.
- **Atomic Operations:** Mutations must update the event log and projections in a single transaction.
- **Postgres-Native:** Leverage JSONB and pgvector features for performance.

---

## 2. Interface Definition

```python
class StorageProvider(Protocol):
    """
    Interface for smrti storage backends.
    """

    async def connect(self) -> None: ...
    async def migrate(self) -> None: ...

    # --- Mutation (The Event Path) ---
    async def apply_event(self, event: Event) -> int:
        """
        The ONLY way to modify data.
        1. Starts a transaction.
        2. Appends 'event' to the 'events' table.
        3. Updates 'nodes' or 'edges' projection based on event type.
        4. Commits and returns the event ID.
        """
        ...

    # --- Retrieval: Projections ---
    async def get_node(self, node_id: UUID) -> Optional[Node]: ...
    
    async def get_node_by_key(self, namespace: str, node_key: str) -> Optional[Node]: ...

    async def get_edges(
        self, 
        node_id: UUID, 
        direction: str = "both",
        edge_types: list[str] = None
    ) -> list[Edge]:
        """Retrieve relationship edges for a node."""
        ...

    # --- Retrieval: Core Query Methods (D15) ---
    async def search_nodes(
        self,
        query_vector: list[float],
        namespaces: list[str],
        filters: dict = None,      -- Supports nested JSONB path queries
        limit: int = 10,
        min_similarity: float = 0.0
    ) -> list[SearchResult]:
        """Semantic search with native SQL pre-filtering (D25)."""
        ...

    async def traverse_graph(
        self,
        start_node_id: UUID,
        depth: int = 1,
        edge_types: list[str] = None,
        max_nodes: int = 100
    ) -> GraphResult:
        """Graph walk from a starting node."""
        ...

    async def aggregate_edges(
        self, 
        edge_type: str, 
        namespaces: list[str],
        filters: dict = None
    ) -> dict:
        """Perform SQL-side aggregations on edge metadata."""
        ...

    # --- Utility ---
    async def get_events(self, after_id: int, limit: int = 100) -> list[Event]: ...
```

---

## 3. Design Decisions & Tradeoffs

### D29.1 Single-Transaction Application
**Decision:** `apply_event` is the single point of entry for writes. Projections are updated synchronously within the same database transaction as the event append.
- **Tradeoff:** This ensures immediate consistency, which is vital for real-time agents. The write-path complexity is contained entirely within the provider.

### D29.2 Rich Filtering (JSONB)
**Decision:** The `filters` parameter supports nested structures. The implementation should translate these into Postgres JSONB operators (e.g., `metadata @> '{"status": "active"}'`).
- **Tradeoff:** This leverages Postgres's specific strengths over basic key-value stores.

### D29.3 BIGINT for Event Sequencing
**Decision:** Events use a sequential `BIGSERIAL` ID.
- **Tradeoff:** This provides a definitive "Arrow of Time" for the system, making `memory.rebuild()` and `memory.export()` deterministic.
