# Quickstart

This tutorial walks through every core operation in smrti. Each code block is a complete, runnable example. All examples use async/await because smrti is an async library.

## Setup

Every example in this guide assumes the following setup. Adjust the connection string and embedding provider to match your environment.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

config = SmrtiConfig(
    dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
    embedding_provider=OllamaEmbedding(),
)
```

## Connect to the database

Before you can do anything, you need to connect. This creates a connection pool and runs any pending database migrations (creating tables on first run).

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()
    print("Connected.")
    await memory.close()

asyncio.run(main())
```

## Add nodes

Nodes are the entities in your graph: people, places, concepts, facts — anything you want to remember. Each node has a `node_type`, a `content` string, and optional `metadata`.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    result = await memory.add_nodes([
        {"node_type": "person", "content": "Alice is a software engineer in Portland"},
        {"node_type": "person", "content": "Bob is a data scientist in Seattle"},
        {"node_type": "company", "content": "Acme Corp builds developer tools"},
    ])

    print(f"Created {result['_meta']['count']} nodes")
    print(f"Node IDs: {result['node_ids']}")
    # Each node is automatically embedded for semantic search.

    await memory.close()

asyncio.run(main())
```

You can attach metadata for filtering:

```python
result = await memory.add_nodes([
    {
        "node_type": "person",
        "content": "Carol manages the infrastructure team",
        "metadata": {"department": "engineering", "level": "senior"},
    },
])
```

## Add edges

Edges are directed relationships between nodes. They have a type (like `WORKS_AT` or `KNOWS`) and optional metadata.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    # Create nodes first
    nodes = await memory.add_nodes([
        {"node_type": "person", "content": "Alice is a software engineer"},
        {"node_type": "company", "content": "Acme Corp builds developer tools"},
    ])
    alice_id, acme_id = nodes["node_ids"]

    # Create an edge: Alice WORKS_AT Acme
    edges = await memory.add_edges([
        {
            "source_node_id": alice_id,
            "target_node_id": acme_id,
            "edge_type": "WORKS_AT",
            "metadata": {"role": "engineer", "since": "2024"},
        },
    ])

    print(f"Created {edges['_meta']['count']} edge(s)")
    print(f"Edge ID: {edges['edge_ids'][0]}")

    await memory.close()

asyncio.run(main())
```

## Search

smrti supports three search modes: `vector` (semantic similarity), `text` (keyword and fuzzy matching), and `hybrid` (combines both using rank fusion). Hybrid is the default.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    # Add some data
    await memory.add_nodes([
        {"node_type": "fact", "content": "Python was created by Guido van Rossum in 1991"},
        {"node_type": "fact", "content": "PostgreSQL started as the POSTGRES project at UC Berkeley"},
        {"node_type": "fact", "content": "Rust was first released by Mozilla in 2010"},
    ])

    # Hybrid search (default) — combines vector and text ranking
    results = await memory.search("who created Python")
    for r in results["results"]:
        print(f"  [{r['similarity']:.3f}] {r['content']}")

    # Pure vector search — finds semantically similar content
    results = await memory.search("programming language history", mode="vector")
    for r in results["results"]:
        print(f"  [{r['similarity']:.3f}] {r['content']}")

    # Text search — keyword matching with fuzzy fallback
    results = await memory.search("Berkeley", mode="text")
    for r in results["results"]:
        print(f"  [{r['similarity']:.3f}] {r['content']}")

    await memory.close()

asyncio.run(main())
```

You can filter search results by node type or metadata:

```python
# Only search person nodes
results = await memory.search("engineer", node_type="person")

# Filter by metadata
results = await memory.search("engineer", filters={"department": "engineering"})
```

## Traverse the graph

Traversal walks outward from a starting node, following edges. You control how many hops deep to go and which edge types to follow.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    # Build a small graph
    nodes = await memory.add_nodes([
        {"node_type": "person", "content": "Alice"},
        {"node_type": "company", "content": "Acme Corp"},
        {"node_type": "city", "content": "Portland"},
    ])
    alice_id, acme_id, portland_id = nodes["node_ids"]

    await memory.add_edges([
        {"source_node_id": alice_id, "target_node_id": acme_id, "edge_type": "WORKS_AT"},
        {"source_node_id": acme_id, "target_node_id": portland_id, "edge_type": "LOCATED_IN"},
    ])

    # Traverse 2 hops from Alice
    graph = await memory.traverse(alice_id, depth=2)

    print(f"Found {graph['_meta']['nodes_found']} nodes, {graph['_meta']['edges_found']} edges")
    for node in graph["nodes"]:
        print(f"  {node['node_type']}: {node['content']}")

    # Traverse only WORKS_AT edges
    graph = await memory.traverse(alice_id, depth=1, edge_types="WORKS_AT")
    print(f"Work connections: {graph['_meta']['nodes_found']} nodes")

    await memory.close()

asyncio.run(main())
```

## Temporal edges

Edges support `valid_from` and `valid_to` timestamps. This lets you model relationships that change over time. Only temporally valid edges appear in search, traversal, and aggregation.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    nodes = await memory.add_nodes([
        {"node_type": "person", "content": "Alice"},
        {"node_type": "company", "content": "OldCo"},
        {"node_type": "company", "content": "NewCo"},
    ])
    alice_id, oldco_id, newco_id = nodes["node_ids"]

    # Alice worked at OldCo from 2020 to 2023
    await memory.add_edges([{
        "source_node_id": alice_id,
        "target_node_id": oldco_id,
        "edge_type": "WORKS_AT",
        "valid_from": "2020-01-01T00:00:00Z",
        "valid_to": "2023-06-30T00:00:00Z",
    }])

    # Alice works at NewCo from 2023 onward (no valid_to = currently valid)
    await memory.add_edges([{
        "source_node_id": alice_id,
        "target_node_id": newco_id,
        "edge_type": "WORKS_AT",
        "valid_from": "2023-07-01T00:00:00Z",
    }])

    # Only the NewCo edge appears (OldCo edge has expired)
    edges = await memory.get_edges(alice_id, edge_types="WORKS_AT")
    print(f"Active WORKS_AT edges: {edges['_meta']['count']}")
    for e in edges["edges"]:
        print(f"  -> {e['target_node_id']} (from {e['valid_from']})")

    await memory.close()

asyncio.run(main())
```

## The get_or_create pattern

When you are not sure if a node already exists, `get_or_create` handles it atomically. If you provide a `node_key`, it uses database-level uniqueness to prevent duplicates even under concurrent access.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    # First call creates the node
    result = await memory.get_or_create(
        content="Acme Corp builds developer tools",
        node_type="company",
        node_key="acme-corp",
    )
    print(f"Created: {result['created']}")  # True
    print(f"Node ID: {result['node_id']}")

    # Second call returns the existing node
    result2 = await memory.get_or_create(
        content="Acme Corp builds developer tools",
        node_type="company",
        node_key="acme-corp",
    )
    print(f"Created: {result2['created']}")  # False
    print(f"Same ID: {result['node_id'] == result2['node_id']}")  # True

    await memory.close()

asyncio.run(main())
```

## Aggregate edges

Aggregation computes counts, sums, averages, minimums, and maximums over edges — all done in SQL, not in Python. This is useful for answering questions like "how much did I spend this month?" without loading thousands of edges into memory.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    nodes = await memory.add_nodes([
        {"node_type": "person", "content": "Alice"},
        {"node_type": "category", "content": "Groceries"},
        {"node_type": "category", "content": "Coffee"},
    ])
    alice_id, groceries_id, coffee_id = nodes["node_ids"]

    # Record some spending
    await memory.add_edges([
        {
            "source_node_id": alice_id,
            "target_node_id": groceries_id,
            "edge_type": "SPENT",
            "metadata": {"amount": 50.00},
        },
        {
            "source_node_id": alice_id,
            "target_node_id": groceries_id,
            "edge_type": "SPENT",
            "metadata": {"amount": 35.00},
        },
        {
            "source_node_id": alice_id,
            "target_node_id": coffee_id,
            "edge_type": "SPENT",
            "metadata": {"amount": 5.50},
        },
    ])

    # Aggregate all SPENT edges
    stats = await memory.aggregate("SPENT", metadata_key="amount")
    print(f"Transactions: {stats['count']}")
    print(f"Total spent: ${stats['total']:.2f}")
    print(f"Average: ${stats['average']:.2f}")
    print(f"Range: ${stats['minimum']:.2f} - ${stats['maximum']:.2f}")

    await memory.close()

asyncio.run(main())
```

## Understanding _meta

Every value returned by smrti includes a `_meta` key with operational information: what happened, how long it took, which namespaces were involved, how many candidates were considered. This is not decoration — it gives you (and your LLM) full transparency into what the library did.

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def main():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    await memory.add_nodes([
        {"node_type": "fact", "content": "The speed of light is 299,792,458 m/s"},
    ])

    results = await memory.search("speed of light")
    meta = results["_meta"]

    print(f"Search mode: {meta['search_mode']}")
    print(f"Modes used: {meta['search_modes_used']}")
    print(f"Candidates considered: {meta['total_candidates']}")
    print(f"Duration: {meta['duration_ms']:.1f}ms")

    await memory.close()

asyncio.run(main())
```

## Clean up and close

Always close the memory connection when you are done. This releases the database connection pool.

```python
await memory.close()
```

If you are using smrti in a web server or long-running process, connect once at startup and close on shutdown:

```python
import asyncio
from smrti import Memory, SmrtiConfig
from smrti.embedding import OllamaEmbedding

async def app():
    config = SmrtiConfig(
        dsn="postgresql://smrti:smrti@localhost:5432/smrti_dev",
        embedding_provider=OllamaEmbedding(),
    )
    memory = Memory(config)
    await memory.connect()

    try:
        # Your application logic here
        pass
    finally:
        await memory.close()

asyncio.run(app())
```

## Next steps

- Read [Concepts](concepts.md) to understand the design behind nodes, edges, events, and namespaces
- See the [API Reference](../reference/) for the full method signatures
- Check the [Guides](../guides/) for patterns like multi-namespace search and LLM extraction
