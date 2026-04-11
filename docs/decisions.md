# smrti — Design Decisions

Decisions made during the design phase, in order.

---

## D1. Library-first, service optional

smrti is a Python library (`pip install smrti`). Users import it into their application process. A service wrapper (Docker/API) may come later as a separate package but is not the core product.

**Why:** Low barrier to entry. Works with local setups (Ollama + SQLite), works embedded in larger apps, no extra infra to manage. The target user is a developer building an AI agent, not an ops team running a memory service.

## D2. Sits on top of existing databases, not a database itself

smrti is an orchestration layer. It does not implement storage engines, ACID, write-ahead logs, or vector indexing. It uses existing databases for all of that.

Comparable to Mem0, Graphiti, LangMem (Python, on top of DBs) — not comparable to PostgreSQL, Qdrant, Neo4j (C/Rust/Go/Java, are DBs).

**Why:** We don't need to solve storage. We need to solve memory semantics for agents. Existing databases are battle-tested. Python is the right language for an orchestration layer in the AI ecosystem.

## D3. PostgreSQL first, SQLite later — trait-based dual backend

PostgreSQL with pgvector is the first and primary storage backend. SQLite with sqlite-vec will be added later as a second backend behind the same `StorageProvider` trait (D29). The trait ensures identical behavior — same test suite runs against both.

**Why:** Postgres is the production choice. SQLite enables local/embedded/offline use (single file, no server). Building Postgres first gives a proven reference implementation. The trait-based abstraction (enforced at compile time in Rust) ensures SQLite plugs in cleanly without touching core logic. See D31 for sequencing.

## D4. Graph data model: nodes + edges + embeddings

Memories are stored as a knowledge graph: nodes (entities, concepts, events) with typed edges (relationships between them). Both carry metadata. Nodes carry vector embeddings for semantic search.

**Why:** Learned from Unspool — typed edges give structure to extraction (write path) and power efficient SQL views (read path). Retrieval is primarily flat (semantic search + metadata filtering), with optional graph traversal for context-heavy queries.

## D5. Append-only, event-sourced core

The source of truth is an immutable event log. Every write (node created, edge added, status changed) is an append to the event stream. Graph tables are projections that can be rebuilt from events.

No deletions of source events. "Deleting" a memory appends a retraction event. Derived views can filter, aggregate, compact — but the log is sacred.

**Why:** Eliminates an entire class of data-loss bugs (the Unspool audit doc cataloged ~12 issues caused by destructive operations on projections). If a projection is wrong, replay from events.

## D6. LLM-integrated but model-agnostic

smrti orchestrates LLM calls for extraction, embedding, and synthesis — but ships with zero hardcoded models. Users configure which provider and model to use for each pipeline stage, and provide their own prompts/schemas for extraction.

**Why:** Every use case has different extraction needs. A personal assistant extracts tasks and deadlines. A code agent extracts functions and dependencies. The pipeline (call LLM, parse output, store result) is universal; the content (prompts, schemas, edge types) is domain-specific. Users shouldn't write plumbing, but they must own their domain logic.

## D7. Schema-agnostic: no hardcoded node/edge types

smrti does not prescribe types like IS_STATUS, HAS_DEADLINE, TRACKS_METRIC. Users define what node types and edge types exist in their domain. smrti provides the storage and query primitives.

**Why:** Hardcoded types make the library useful for one use case. Generic types make it useful for all of them.

## D8. Multi-tenant with namespace isolation

All operations are scoped by namespace. A namespace is an opaque string (e.g., `"user:123"`, `"org:acme:project:7"`). No cross-namespace data leakage at the query level.

**Why:** Agents serve multiple users. Memory must be isolated per user/session/org without requiring separate databases.

## D9. Rust core, Python + Rust consumers

smrti-core is written in Rust. Python users consume it via PyO3 bindings (`pip install smrti`). Rust users consume it as a crate (`cargo add smrti-core`). Konflux integrates natively.

**Why:** Rust gives compile-time trait enforcement for the dual-backend abstraction, native integration with Konflux (zero-overhead in-process tools), single-binary deployment, and the ability to run on embedded/local without Python. PyO3 bindings ensure Python developers — the largest AI agent audience — still get `pip install` simplicity. See D30 for full rationale.

## D10. Embedding is required

Every memory gets embedded. Semantic search is the primary retrieval mechanism — that's the whole point. Without embeddings, you'd just do RAG over raw text. User must configure an embedding provider.

**Why:** The library's value proposition is semantic memory. Making embeddings optional would compromise the core functionality.

## D11. Freeform storage, optional Pydantic schema support

Node types and edge types are stored as plain strings — no schema declaration required. Users can optionally define Pydantic models that smrti uses to generate JSON schemas for LLM structured output and validate extraction results.

**Why:** Freeform keeps getting-started simple. Pydantic is the standard for structured data in the Python AI ecosystem (LangChain, OpenAI SDK, Anthropic SDK, FastAPI all use it). Users would write these classes anyway — smrti should provide base classes to eliminate boilerplate.

## D12. Dual API: high-level pipeline + low-level primitives

Two ways to store memories:
- **High-level:** `memory.store("raw text")` — smrti handles LLM extraction, parsing, validation, embedding, and storage.
- **Low-level:** `memory.add_nodes(...)`, `memory.add_edges(...)` — user handles extraction themselves, passes structured data directly.

**Why:** High-level is what makes smrti worth using over raw SQL. Low-level is essential for advanced use cases and custom extraction pipelines. Both must exist.

## D13. No built-in synthesis — provide primitives, user writes logic

smrti does NOT ship a synthesis/maintenance framework. Operations like merging duplicates, decaying weights, archiving old items are all domain-specific. smrti provides the primitives (search similar, merge nodes, update metadata, bulk operations) and users write their own synthesis logic, triggered however they want (cron, QStash, end of session, etc.).

**Why:** Every synthesis rule is use-case-specific. Shipping opinionated maintenance logic disguised as general-purpose features adds bloat. Users can build what they need from primitives.

## D14. Migrations: auto-create + explicit upgrade

First connection auto-creates tables if they don't exist (frictionless start). Schema upgrades across smrti versions require explicit `memory.migrate()` call.

**Why:** Auto-create is great for getting started. Explicit upgrades give production users control over when schema changes hit their database.

## D15. Separate query methods, each does one thing

Three retrieval methods, each with a clear purpose:
- `memory.search(query, ...)` — semantic search with optional metadata/edge filters
- `memory.traverse(node_id, depth=1, ...)` — graph walk from a node
- `memory.aggregate(edge_type, ...)` — aggregate operations on edges

**Why:** One god-method with 15 parameters gets confusing. Separate methods are easier to learn, document, and type-hint. "Do one thing well" is the project philosophy.

## D16. Project philosophy: do one thing well

Applies at every level — each method, each module, each component has a single clear purpose. No Swiss-army-knife APIs. No features that try to serve multiple concerns. Composability over configurability.

## D17. Optimized for real-time chat, targeting non-tech end users

The developer using smrti builds the agent; the end user just chats. This means:
- **Read path: sub-100ms.** No LLM calls during retrieval. Vector search + SQL only.
- **Write path: can be async.** Extraction can happen in background. Chat should never block on graph construction.
- **Local-first is first-class.** Postgres + Ollama + lightweight local embeddings must work well on a laptop, not just as a fallback.
- **Memory footprint matters.** Can't require a 2GB embedding model for a chat app.

**Why:** Most agent tools target developers. We're building for applications that serve general, non-technical people. Performance on the read path directly affects user experience.

## D18. Security boundary: smrti owns data isolation, app owns identity

smrti guarantees namespace isolation at the query level — every operation is scoped by namespace with parameterized SQL. No cross-namespace operations exist in the API. SQL injection is prevented by parameterized statements everywhere.

smrti does NOT handle authentication or authorization. The app is responsible for mapping authenticated users to namespaces. smtp trusts whatever namespace it receives.

**Why:** Same model as SQLAlchemy, Redis clients, and every other database library. The library handles data isolation; the app handles identity. Trying to own auth inside a library creates coupling and false security guarantees. Clear documentation of the security boundary is more valuable than a half-baked auth layer.

## D19. Separate embeddings table, not vector column on nodes

Embeddings stored in `node_embeddings(node_id, model_name, embedding)`, not as a column on the nodes table. Enables:
- Multiple embeddings per node (multilingual, multimodal, different models)
- Embedding model migration without re-embedding everything at once
- Clean separation of content from vector representation

**Why:** Real users switch models, use multiple models, or need different embedding types (text + CLIP). A single vector column forces one model forever or painful migrations.

## D20. API designed for LLM tool calling

Since smrti methods will often be exposed as LLM tools, the API follows LLM-friendly conventions:
- Simple, flat parameters (no nested objects)
- String types for dates (ISO format, parsed internally)
- Few parameters per method (3-5, not 15)
- Descriptive parameter names (LLMs use names to decide what to pass)
- Structured dict/list returns (not ORM objects)
- Good docstrings (frameworks generate tool schemas from these)

**Why:** The primary consumer of smrti's query API is often an LLM deciding what to search for. The API should be readable from a function signature alone.

## D21. Temporal queries: time-range filters on search

Search and filter operations support `after` and `before` parameters (ISO date strings) to scope queries by time. This enables "how much did I spend in June" and "what did I say about X in the last 20 days."

Full point-in-time graph reconstruction ("show me the graph as it was on March 5th") is deferred — the event log makes it possible, but surfacing it is a future feature.

**Why:** Time-scoped queries are the most common temporal need. Point-in-time reconstruction is complex and rarely needed.

## D22. Nodes/edges are projections, events are source of truth

The nodes and edges tables are projections built from the event stream. smrti ships:
- `nodes` — latest state of each node
- `edges` — current edges

Users create their own SQL views on smrti's tables for domain-specific queries. smrti documents the schema clearly but does not provide a view builder API — SQL is more powerful than any abstraction over it.

**Why:** Domain-specific views (like Unspool's vw_actionable, vw_timeline) are always custom. A view builder would be a leaky abstraction. Users who need views know SQL.

## D23. Import/export via event stream

`memory.export()` returns events (the source of truth). `memory.import()` replays them. Handles backup and sharing memory between agents.

**Why:** Events are the complete representation. Exporting nodes/edges would lose history. Event replay reconstructs everything.

## D24. Multimodal via content_type, not binary storage

Nodes have a `content_type` field (`"text"`, `"image"`, `"audio"`, `"url"`, etc.) indicating original source. The `content` field is always text (transcript, description, OCR output). Binary storage is the app's responsibility — store a URI/path in metadata.

The separate embeddings table (D19) means a node can have both a text embedding and a CLIP embedding.

**Why:** smrti is a graph memory engine, not a blob store. Text representation keeps the core simple. content_type preserves provenance for the app to use.

## D25. Hybrid SQL filtering via pgvector

Metadata filtering happens in SQL alongside vector search — not post-filtering in Python. pgvector supports native WHERE clauses with vector ORDER BY, giving true pre-filtered vector search in a single query.

GIN index on JSONB metadata created automatically. No user-facing index management API — users who need additional indexes can create them directly on smrti's tables.

**Why:** Post-filtering in Python has a correctness bug: if the top N vector matches don't pass the filter, the user gets 0 results even though matches exist. With Postgres-only (D3), we get native pre-filtering for free — no workarounds needed.

## D26. Multi-namespace search

Search accepts a list of namespaces: `search(namespaces=["user:123", "global"])`. Implemented as `WHERE namespace IN (...)` — single query, unified ranking across namespaces. Write operations remain single-namespace only.

**Why:** "Shared knowledge + personal memory" is a common pattern (company docs + user's project). Searching two namespaces separately and merging results loses semantic ranking across the combined set. A namespaces list is trivial to implement and solves this correctly.

## D27. Temporal validity intervals on edges

Edges support optional `valid_from` and `valid_to` fields (timestamps). `valid_to` is nullable (meaning "currently true"). Queries filter by validity: `WHERE valid_from <= :now AND (valid_to IS NULL OR valid_to >= :now)`.

**Why:** Temporal reasoning is critical for agent memory. "Alice worked at Acme from 2020 to 2024" is one edge with a validity interval, not create + retract events. Small schema addition, big payoff.

## D28. Namespace isolation is strict, no built-in hierarchies

Namespaces are flat, opaque strings. No built-in namespace hierarchies or parent-child relationships between namespaces. Multi-namespace search (D26) covers the "global + personal" pattern without adding hierarchy complexity.

**Why:** Hierarchies add complexity to every query path. The multi-namespace list parameter solves the common case. Apps with complex namespace logic handle it themselves.

## D29. StorageProvider Abstraction (No Leaky Logic)

The core `Memory` class must never contain raw SQL or database-specific logic (e.g., pgvector operators). All data access must pass through a `StorageProvider` interface (Protocol).

**Why:** This enforces clean separation of concerns. The core logic handles LLM orchestration and graph semantics; the provider handles the "how" of storage. By routing all mutations through a single `apply_event` method, we guarantee that the event log (source of truth) and the graph projections (read model) remain perfectly synchronized within a single database transaction.

## D30. Rust core with Python bindings (PyO3)

smrti-core is written in Rust. Python users get `pip install smrti` via PyO3 bindings. Rust users get `cargo add smrti-core`. The Rust crate is the single source of truth for all behavior.

**Why:** Rust gives us (1) dual-backend capability — Postgres for production, SQLite for local/embedded, both with vector search, behind the same trait, (2) integration with Konflux (Rust workflow engine) as in-process tools with zero overhead, (3) single binary deployment for applications like Unspool, (4) memory safety and no GIL for concurrent operations. Python bindings ensure the library is still accessible to the largest AI developer audience.

## D31. Postgres first, SQLite later (stubbed)

PostgresProvider (sqlx + pgvector) is the first implementation. SqliteProvider (rusqlite + sqlite-vec) is stubbed in the trait but implemented after the Postgres path is mature and battle-tested. Both must have identical behavior — the Postgres implementation becomes the reference spec for the SQLite port.

**Why:** Building both simultaneously doubles the work and testing before either is proven. Postgres first gives us a solid, production-ready foundation. The StorageProvider trait (D29) ensures SQLite plugs in cleanly when ready. The SQLite provider can be validated by running the exact same test suite.

## D32. Three distribution targets

- `smrti-core` (Rust crate on crates.io) — for Rust applications and Konflux integration
- `smrti` (Python package on PyPI via PyO3) — for Python agent developers
- `konf-smrti` (Rust crate) — Konflux tool integration, exposes smrti as workflow tools

**Why:** Each target serves a different consumer without coupling them. A Python developer using smrti doesn't need Konflux. A Konflux workflow doesn't need Python. Both use the same core.

---

## External Review Notes

Feedback from external review (Gemini analysis, 2026-04-04). Decisions on what to adopt:

| Suggestion | Decision |
|-----------|----------|
| Snapshotted projections for replay | Good idea, defer. Replay is rare (explicit rebuild), not a hot path. |
| SQLite WAL mode | No longer needed — Postgres-only (D3) |
| Dedup/merge primitives | Already covered — these are storage/query primitives, not synthesis |
| Namespace hierarchies/search paths | Multi-namespace search adopted (D26), hierarchies rejected (D28) |
| Hybrid SQL pre-filtering | Adopted — native with Postgres/pgvector (D25) |
| Temporal validity intervals on edges | Adopted as D27 |
| Schema registration for IDE/LLM help | Already covered by optional Pydantic support (D11) |

---

## Open Questions

- Exact method signatures and return types
- Configuration format (code-based, YAML, or both)
- Extraction prompt template system (how users define their prompts)
- Project name (current name "smrti" is taken on PyPI and by cyqlelabs)
- Visualizer / debug tooling (future)
- Streaming (search results? event feed? extraction output?)
- Node content versioning (history of changes — event log has it, should we surface it?)
