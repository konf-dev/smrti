# smrti — LLM Extraction Pipeline

This document defines the process of converting raw text into a structured, reconciled knowledge graph.

---

## 1. Overview: The Asynchronous Refinery

Extraction in `smrti` is a multi-stage process designed to balance user-perceived performance with graph integrity.

1. **Ingestion:** Raw text is received and logged as a `RAW_INPUT_RECEIVED` event.
2. **Extraction:** An LLM parses the text into "candidate" nodes and edges.
3. **Reconciliation:** The candidates are compared against the existing graph to prevent duplication.
4. **Embedding:** Every new or updated node is embedded via the configured provider.
5. **Integration:** Finalized changes are applied to the storage layer atomically.

---

## 2. Stages in Detail

### Stage 1: Extraction (Discovery)
The system calls the configured LLM with a prompt that includes:
- The raw input text.
- Optional: User-defined Pydantic schemas for specific node/edge types (D11).
- Optional: A "hint" of recent context to help with pronoun resolution (e.g., "it", "he", "then").

**Output:** A list of `CandidateNode` and `CandidateEdge` objects with local, temporary IDs.

### Stage 2: Reconciliation (Anchoring & Deduplication)
This is the "Identity Management" phase. For every `CandidateNode`:
1. **Explicit Key:** If a `node_key` is provided (e.g., `user_id:123`), look up the node in the `nodes` table.
2. **Semantic Match:** If no key exists, search the graph for similar nodes using vector similarity (D15).
    - **High-confidence match:** If similarity > `MERGE_THRESHOLD`, treat the candidate as an update to the existing node.
    - **Ambiguous match:** If similarity is in the "gray zone," optionally trigger a small "Resolution LLM" pass to decide if they are the same entity.
    - **No match:** Treat the candidate as a new node.

### Stage 3: Embedding & Integration
1. **Embedding:** Call the embedding provider for all new content.
2. **Atomic Write:** Call `StorageProvider.apply_event()` for the finalized event (e.g., `NODE_UPDATED`, `EDGE_ADDED`). The event payload contains the resolved UUIDs.

---

## 3. Design Decisions & Tradeoffs

### D30.1 Asynchronous by Default
**Decision:** High-level `memory.store()` returns immediately after logging the raw input event. The extraction pipeline runs in a background task (e.g., `asyncio.create_task` or a task queue).
- **Tradeoff:** Improves chat responsiveness (D17) but introduces a small "memory lag" (sub-second to a few seconds).
- **Mitigation:** The API will support `await memory.store(..., wait=True)` for cases requiring immediate consistency.

### D30.2 "Universal" vs. "Domain-Specific" Extraction
**Decision:** `smrti` provides a default "Universal" extraction prompt, but users can register custom prompts for specific node types.
- **Tradeoff:** A single prompt is cheaper and faster; multiple passes are more accurate. 
- **Opinion:** Start with a single-pass "Universal" extractor that handles 80% of cases, and provide an "Expert Extractor" interface for complex domains.

### D30.3 Entity Resolution is "Propose, then Commit"
**Decision:** The reconciliation logic does not "delete" or "overwrite" data. It appends an update event.
- **Tradeoff:** The graph history is preserved (D5), but the `nodes` projection only shows the "latest" merged state.

---

## 4. Extraction Logic Opinions

- **No LLM-generated UUIDs:** The LLM should never be responsible for generating database IDs. It uses string labels (e.g., "entity_1"), and the `smrti` core maps these to UUIDs during reconciliation.
- **Metadata as the Indexing Engine:** While the node `content` is for semantic search, the `metadata` is for hard filtering. The extraction prompt should explicitly ask the LLM to extract "Filterable Attributes" (e.g., `status`, `priority`, `date`) into the metadata block.
- **Edge Directionality:** All edges are directed (`source` -> `target`). Bi-directional relationships (e.g., "X is a friend of Y") should be extracted as two edges or a single edge with a `Symmetric` flag in metadata.
- **Resolution over Creation:** The pipeline should be biased toward "finding a match" rather than "creating a new node" to prevent graph explosion.
