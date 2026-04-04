# Core Concepts

This page explains the ideas behind smrti for someone who has never used a graph memory system. If you already know what nodes and edges are, skim the headings and read the sections that are new to you.

## What is graph memory?

Most AI applications store context in one of two ways:

- **Vector stores** hold chunks of text as embeddings. You search by similarity: "find me text that sounds like X." This works well for retrieval-augmented generation (RAG), but everything is flat. There is no structure, no relationships, no way to say "Alice works at Acme" except by hoping the embedding captures it.

- **RAG pipelines** combine a vector store with a prompt. They retrieve relevant chunks and stuff them into the LLM's context window. This is a good start, but it hits limits fast: duplicate information, no entity tracking, no temporal awareness, no way to aggregate ("how much did I spend last month?").

**Graph memory** adds structure. Instead of flat text chunks, you store entities (people, places, concepts) as *nodes* and relationships between them as *edges*. "Alice works at Acme" becomes a node for Alice, a node for Acme, and a WORKS_AT edge connecting them. You can still do similarity search (smrti embeds every node), but you can also traverse the graph, filter by relationships, aggregate over edges, and track how things change over time.

smrti gives you both: the semantic search of a vector store and the structured relationships of a graph, all backed by PostgreSQL.

## Nodes

A node represents a single entity, fact, or concept in your knowledge graph. Every node has three required properties:

- **content** — a text description. This is what gets embedded for semantic search. Example: `"Alice is a software engineer who specializes in distributed systems"`
- **node_type** — a label that categorizes the node. Examples: `"person"`, `"company"`, `"concept"`, `"event"`, `"fact"`. You define these; smrti does not enforce a fixed set.
- **node_key** — an optional identity anchor. If two nodes in the same namespace have the same `node_key`, they are the same entity. This prevents duplicates. Example: `"alice-johnson"` or `"acme-corp"`.

Nodes can also carry:

- **metadata** — a dictionary of arbitrary key-value pairs for filtering. Example: `{"department": "engineering", "level": "senior"}`. You can search by metadata with containment filters.
- **content_type** — defaults to `"text"`. Reserved for future support of other formats.

When you add a node, smrti automatically generates a vector embedding of its content and stores it alongside the node. This is what powers semantic search.

## Edges

An edge is a directed relationship between two nodes. "Alice WORKS_AT Acme" is an edge where Alice is the source, Acme is the target, and `WORKS_AT` is the edge type.

Edges have:

- **source_node_id** and **target_node_id** — the two nodes being connected. Direction matters: the edge goes from source to target.
- **edge_type** — a string label for the relationship. Examples: `"WORKS_AT"`, `"KNOWS"`, `"LOCATED_IN"`, `"SPENT"`, `"AUTHORED"`.
- **metadata** — arbitrary key-value pairs. Example: `{"role": "engineer", "since": "2024"}` on a WORKS_AT edge, or `{"amount": 50.00}` on a SPENT edge.

### Temporal validity

Every edge has a `valid_from` timestamp (defaults to now) and an optional `valid_to` timestamp (defaults to null, meaning "currently valid"). Only edges that are temporally valid right now appear in searches, traversals, and aggregations.

This lets you model change over time without deleting history. If Alice switches jobs, you do not delete the old WORKS_AT edge — you set its `valid_to` to the date she left, and create a new edge with the new employer. Both edges remain in the system. Queries about the current state see only the active one; the full history is preserved.

### Append-only semantics

Edges are never overwritten. Every `add_edges` call creates new edges. Removing an edge is done with `retract_edge`, which soft-deletes it (sets `is_retracted = TRUE`) rather than physically deleting the row. The original data is always preserved in the event log.

## Why edges are not unique

This is important enough to deserve its own section.

In many graph systems, there is a uniqueness constraint: only one edge of a given type can exist between two nodes. If you insert "Alice WORKS_AT Acme" twice, the second write either fails or overwrites the first.

smrti deliberately has **no** such constraint. Multiple edges of the same type between the same two nodes are valid and expected.

**Why this matters — the A1 bug story:**

During an early audit, a uniqueness constraint on edges was identified as the single most dangerous bug in the system — designated "A1" (highest severity). Here is the scenario that makes it dangerous:

Imagine an AI agent tracking expenses. The user says "I spent $50 on groceries." The agent creates an edge: Alice SPENT $50 -> Groceries. An hour later, the user says "I spent $50 on groceries" again — a separate purchase. With a uniqueness constraint, one of two things happens:

1. The insert fails silently. The second purchase is lost.
2. The insert overwrites the first edge. The first purchase is lost.

Both outcomes destroy data. The correct answer is two separate SPENT edges, each with `{"amount": 50.00}` in their metadata. When you aggregate, you get a total of $100 — which is correct.

This is not a theoretical concern. LLM extraction pipelines regularly produce the same relationship multiple times from different conversations. Each occurrence may carry different metadata, different temporal context, or represent a genuinely repeated event. A uniqueness constraint cannot distinguish between "same fact restated" and "same type of event happened again." Keeping both is always safe; discarding one is sometimes catastrophic.

If you do need deduplication, you can retract the duplicate edge explicitly, or use `merge_nodes` to combine entities that turned out to be the same. The point is that this decision is yours to make, not something the database does silently.

## Events

Every change in smrti — creating a node, adding an edge, storing an embedding — is recorded as an event in an append-only log. The event log is the source of truth. The nodes and edges tables you query against are *projections*: materialized views derived from the event log.

This design has several practical consequences:

- **Full audit trail.** You can see exactly what happened, when, and in what order. Every event has a monotonically increasing ID (the "arrow of time") and a timestamp.
- **Rebuild from scratch.** If the projection tables get corrupted or you change the schema, you can drop them and replay all events to reconstruct the current state. `memory.rebuild()` does this.
- **Import/export.** `memory.export_events()` gives you a complete, lossless dump of all data. `memory.import_events()` replays it into another database.

The event types are: `NODE_CREATED`, `NODE_UPDATED`, `NODE_RETRACTED`, `EDGE_ADDED`, `EDGE_UPDATED`, `EDGE_RETRACTED`, `EMBEDDING_STORED`, `RAW_INPUT_RECEIVED`, and `NODES_MERGED`.

Every write goes through a single function, `apply_event()`, which appends to the event log and updates the projection tables in a single database transaction. If the projection update fails, the event is also rolled back. There are no ghost events and no inconsistencies between the log and the tables.

## Namespaces

A namespace is a string that isolates data. Nodes and edges belong to exactly one namespace. Searches and traversals are scoped to one or more namespaces.

Common uses:

- **Per-user isolation.** `namespace="user:alice"` keeps Alice's memory separate from Bob's.
- **Per-agent isolation.** `namespace="agent:support"` and `namespace="agent:sales"` for different agent personas.
- **Multi-namespace search.** You can search across multiple namespaces at once by passing a comma-separated string: `namespace="user:alice,shared"`. This lets you have private memory per user plus a shared knowledge base.

The default namespace is `"default"`. You can change this with `SmrtiConfig.default_namespace`.

Namespaces are not declared upfront. They come into existence the first time you create a node in them. There is no cost to having many namespaces.

## Search modes

smrti supports three search modes, each suited to different use cases.

### Vector search

Embeds your query text and finds nodes whose embeddings are most similar (cosine similarity). This is the classic semantic search: "find things that mean something similar to X" even if they do not share any keywords.

Use vector search when the user's query is conceptual or paraphrased. "Who knows about distributed systems?" will match a node containing "Alice specializes in building large-scale distributed architectures" even though the words barely overlap.

### Text search

Uses PostgreSQL's built-in full-text search (tsvector) with a trigram similarity fallback. This is keyword matching with stemming: "running" matches "run", "runner", "runs". If the full-text search returns too few results, smrti falls back to trigram similarity (fuzzy matching), which catches typos and partial matches.

Use text search when the user is looking for a specific term, name, or identifier. "Acme Corp" will reliably find nodes containing that exact name, even if the embedding space has many semantically similar companies.

### Hybrid search

Runs both vector and text search, then combines the results using Reciprocal Rank Fusion (RRF). An item that ranks highly in both lists scores higher than one that ranks highly in only one. This gives you the best of both worlds: semantic understanding and keyword precision.

Hybrid is the default mode. In most cases, it is the right choice. The `rrf_k` configuration parameter (default 60) controls how aggressively the fusion smooths rank differences.

## Dual API: Memory and Provider

smrti has two layers, and you only need to know about one of them.

**Memory** is the layer you use. It has flat parameters (strings, ints, dicts), returns plain dictionaries, and is designed to work well as an LLM tool. You never write SQL or import database types. Node IDs are strings. Dates are ISO 8601 strings. Everything is simple.

**StorageProvider** (specifically PostgresProvider) is the layer underneath. It uses typed parameters (UUIDs, datetimes, Pydantic models), owns all the SQL, manages connection pooling, and handles migrations. You would only touch this layer if you are writing a custom storage backend or extending smrti's internals.

The Memory layer calls the Provider layer for all data operations. It translates between the two: converting string IDs to UUIDs, parsing date strings to datetimes, converting Pydantic model results back to plain dicts. This separation means the user-facing API stays simple while the storage layer stays type-safe.

## _meta: operational transparency

Every dictionary returned by Memory includes a `_meta` key. This is not optional — it is always there. It tells you what the library actually did:

- After a search: which search mode was used, how many candidates were considered, how long it took, which namespaces were searched.
- After adding nodes: which event IDs were created, how many nodes were added, which namespace they went into.
- After a traversal: which node was the starting point, how deep the traversal went, how many nodes and edges were found.

This matters because smrti is designed to be called by LLMs. When an LLM calls `search()` and gets back results, the `_meta` tells it (and you) whether the search was effective. If `total_candidates` is 0, the search found nothing — not that there were no results after filtering. If `search_modes_used` only contains `["text"]` in a hybrid search, that means no vector results contributed, which might mean the embedding model is not matching well.

Treat `_meta` as your debugging and observability layer. It is the same data that populates OpenTelemetry spans if you have tracing enabled.

## Configuration

Everything in smrti is configurable through `SmrtiConfig`. There are no magic numbers buried in code. Some examples:

- `search_limit` — how many results to return by default (default: 10)
- `min_similarity` — minimum cosine similarity threshold (default: 0.0)
- `search_mode` — default search mode: `"vector"`, `"text"`, or `"hybrid"` (default: `"hybrid"`)
- `merge_threshold` — how similar two nodes must be to be considered the same entity during extraction (default: 0.85)
- `max_traversal_depth` — safety limit on graph traversal depth (default: 5)
- `rrf_k` — the RRF fusion constant for hybrid search (default: 60)
- `hnsw_m` and `hnsw_ef_construction` — pgvector HNSW index tuning parameters
- `pool_min` and `pool_max` — database connection pool size
- `default_namespace` — the namespace used when none is specified (default: `"default"`)

Every parameter is validated. Passing an invalid value raises a clear error at configuration time, not at query time.

See the [API Reference](../reference/) for the full list of configuration options.
