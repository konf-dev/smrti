# Smrti: Intelligent Multi-Tier Memory System - Architecture & Product Requirements Document

**Version:** 0.1.0 (Draft)
**Date:** 2025-10-03  
**Organization:** KonfSutra  
**Audience:** AI Platform Engineers, Backend Engineers, Applied Researchers, Solution Architects, Observability & Reliability Engineers  
**Status:** In Progress

---
## Executive Summary

### Vision
**Smrti** (Sanskrit: स्मृति – "remembrance") is a **standalone, provider-agnostic cognitive memory substrate** for AI systems. It enables agents and LLM-powered workflows to retain, organize, retrieve, and evolve knowledge across five complementary tiers: **Working, Short-Term, Long-Term, Episodic, and Semantic**. Smrti provides a principled, neuroscience-inspired abstraction for memory lifecycle: perception → encoding → consolidation → retrieval → decay.

Unlike simplistic conversation buffers or flat vector stores, Smrti unifies **real-time context**, **session continuity**, **durable factual knowledge**, **temporal event chains**, and **structured semantic facts** behind a single protocol. It optimizes **token efficiency**, **retrieval relevance**, and **system latency**, while remaining **database-, embedding-, and model-agnostic**.

### Problem Statement
LLM applications today suffer from one or more of the following:
1. Lost continuity beyond a single session (no consolidation).
2. Retrieval noise due to oversaturated vector databases (no decay/deduplication).
3. Token waste from dumping entire chat histories (no adaptive budgeting).
4. Lack of context blending (e.g., user preferences + recent events + semantic facts).
5. Vendor lock-in to a single database or embedding provider.
6. Inability to explain *why* a piece of context was retrieved (no provenance).

Smrti addresses these with a layered design + explicit lifecycle model + adaptive context assembly pipeline.

### Core Value Propositions
1. **Hierarchical Cognitive Model** – Five distinct memory types with clear semantics and lifecycles.
2. **Adaptive Context Builder** – Produces optimal, token-budget-aware, structured context for LLM prompts.
3. **Hybrid Retrieval Engine** – Fuses BM25 keyword, dense vector similarity, temporal filters, and graph traversal.
4. **Lifecycle Intelligence** – Consolidation (STM→LTM), summarization, deduplication, decay curves, conflict resolution.
5. **Database & Embedding Agnostic** – Plug-in adapters (Redis, ChromaDB, Pinecone, Weaviate, Postgres, Neo4j, AWS services, local in-memory).
6. **Enterprise-Grade Observability** – Latency, relevance, cache efficiency, decay actions, consolidation metrics.
7. **Multi-Tenant Isolation** – Namespaces + tenant scoping; cryptographic IDs; optional encryption-at-rest hooks.
8. **Extensibility by Construction** – Protocol + adapter architecture, optional extras, deferred multimodal hooks.
9. **Cost Efficiency** – Reduces average prompt context tokens by 40–70% through relevance ranking + summarization.
10. **Explainability & Provenance** – Every retrieved fragment includes origin metadata (memory_type, source_id, timestamp, relevance_score, transformation_chain).

### Key Architectural Decisions (Summary)
| Decision | Rationale | Trade-off Accepted |
|----------|-----------|--------------------|
| Five-tier memory taxonomy (WM/STM/LTM/Episodic/Semantic) | Mirrors cognitive science; separates concerns; improves retrieval precision | Higher conceptual onboarding cost |
| Protocol-based adapters for storage & embeddings | Avoid vendor lock-in; enable BYO infra; encourage community plugins | Slightly more boilerplate for new integrations |
| Hybrid retrieval (BM25 + Vector + Graph + Temporal) | Increases recall & precision vs single modality | Additional query planning complexity |
| Adaptive context token budgeting | Minimizes LLM cost & improves focus | Requires token counting + dynamic pruning |
| Consolidation & decay background jobs | Prevent unbounded growth + noise accumulation | Requires scheduler / async tasks |
| Provenance-rich context objects | Improves explainability & debugging | Slightly larger payload size |
| Query-time re-ranking (cross-encoder optional) | Boosts semantic accuracy for top-k | Additional latency (amortized via caching) |
| Separation from orchestration layer (no Sutra dependency) | Ensures standalone adoption & portability | Lost opportunity for tight vertical optimization |
| Dev Kit with docker-compose (optional) | Lowers local setup friction | Must document that production should use managed services |
| Multimodal-ready schemas (extensible content types) | Future-proof for images/audio/video | Minor upfront abstraction overhead |

### Success Criteria (First 6 Months)
| Dimension | Metric | Target | Rationale |
|----------|--------|--------|-----------|
| Retrieval Performance | p95 semantic query latency | < 300 ms | Feels responsive in chat UX |
| Relevance Quality | Top-5 recall (golden benchmark) | ≥ 85% | Competitive with tuned RAG stacks |
| Token Efficiency | Avg context tokens vs naive full history | ≥ 50% reduction | Cost savings & better model focus |
| Memory Growth Control | Orphan/low-relevance memory ratio | < 20% | Indicates effective decay & consolidation |
| Multi-Tenancy Safety | Cross-tenant leakage incidents | 0 | Hard requirement |
| Adapter Ecosystem | Official adapters shipped | ≥ 5 (Redis, Chroma, Pinecone, Postgres, Neo4j) | Demonstrates extensibility |
| Reliability | Consolidation job success rate | ≥ 99% | Lifecycle stability |
| Observability Coverage | Metrics & traces implemented | 100% of critical paths | Production readiness |
| Extensibility | Community adapters contributed | ≥ 2 | Ecosystem traction |
| Developer Velocity | Time to add new storage adapter | < 2 hours | Low integration friction |

### Risk & Mitigation Overview
| Risk | Severity | Category | Mitigation |
|------|---------|----------|-----------|
| Retrieval latency spikes (vector DB scaling) | HIGH | Performance | Connection pooling, async batching, ANN index tuning, fallback tiers |
| Memory bloat (unbounded growth) | HIGH | Cost / Quality | Decay curves, consolidation summarization, size quotas, alerts |
| Poor relevance (bad embeddings) | HIGH | Accuracy | Pluggable embedding providers, model A/B tests, hybrid fusion |
| Cross-tenant data leak | HIGH | Security | Namespace enforcement, integration tests, optional encryption, deny-by-default guardrails |
| Adapter fragmentation (inconsistent quality) | MEDIUM | Ecosystem | Adapter certification checklist, reference tests, version compatibility matrix |
| Summarization drift (loss of factual fidelity) | MEDIUM | Integrity | Fact extraction + validation, keep raw archival copy, checksum comparisons |
| Token budget overflow | MEDIUM | Cost | Early pruning, streaming truncation, hard caps, metrics alerts |
| Complexity deters adoption | MEDIUM | Adoption | Progressive documentation (start with 2 tiers), scaffold generator |
| Background job failures silent | MEDIUM | Reliability | Heartbeat metrics, failure queues, DLQ inspection tooling |
| Vendor API changes (LLM/embedding) | LOW | Stability | Protocol abstraction + feature flags |

### Document Navigation Guide
- **Sections 1-3**: Purpose, scope, architecture overview, component responsibilities
- **Sections 4-8**: Memory tier semantics, retrieval, context assembly, lifecycle mechanics
- **Sections 9-12**: Observability, security, performance engineering, testing strategy
- **Sections 13-16**: Extensibility model, packaging & distribution, roadmap, future-proofing (multimodal)
- **Section 17**: Implementation kickoff checklist & env var conventions
- **Appendices**: Reference schemas, adapter templates, decision records (ADRs), example integration flows

---
## 0. Reader Assumptions
- Familiarity with general LLM application architecture (prompt → model → response)
- Basic understanding of vector similarity search concepts (embeddings, top-k)
- No prior knowledge of Sutra or any other internal framework required
- Comfortable with Python async patterns (for adapter implementation)

---
<!-- NOTE: All sections populated. This comment retained to indicate living document status. -->

---
## 1. Purpose & Scope

### 1.1 Purpose
Smrti provides a **unified abstraction for AI application memory** that replaces ad-hoc mixtures of chat buffers, vector databases, raw logs, and brittle prompt stuffing logic. It defines a *portable cognitive substrate* that any agent / workflow / service can consume to:

1. Store new percepts and interactions in the correct tier automatically.
2. Consolidate transient session context into durable long-term knowledge.
3. Retrieve a *blend* of relevant facts, events, and contextual signals under a strict token budget.
4. Evolve over time (decay, summarization, conflict resolution) to prevent entropy accumulation.
5. Explain *why* any piece of memory appears in an assembled context (provenance & ranking transparency).

### 1.2 Goals
| Goal | Description | Measurable Indicator |
|------|-------------|----------------------|
| Unified Memory Model | Provide consistent API across heterogeneous backends | One protocol drives ≥5 adapters |
| High Relevance Retrieval | Blend semantic, lexical, temporal, and structural signals | ≥85% top-5 recall on benchmark set |
| Cost Efficiency | Reduce unnecessary LLM tokens | ≥50% avg token reduction vs naive append |
| Extensibility | Enable rapid addition of new storage/embedding providers | New adapter < 2 hrs dev time |
| Lifecycle Health | Prevent uncontrolled growth & duplication | Orphan ratio < 20%; duplicate merge rate tracked |
| Observability | First-class introspection of internal decisions | 100% critical spans traced; ≥10 core metrics exported |
| Security & Isolation | Strong tenant & namespace boundaries | Zero cross-tenant leakage in tests |

### 1.3 Non-Goals (Deliberate Exclusions)
| Area | Reason for Exclusion | Delegated To |
|------|---------------------|--------------|
| UI / Visualization Portal | Not core to memory substrate MVP | External observability tooling (Grafana, Kibana, Neo4j Browser) |
| Authentication / RBAC | Orthogonal concern | Hosting application / API gateway |
| Proprietary Model Hosting | Scope creep | Model providers / inference layer |
| Full ETL / Data Lake Ingestion | Different problem space | Data platform pipelines |
| Real-time Streaming Analytics | Latency-critical CEP not needed | Stream processors (Kafka/Flink) |
| Autonomic Agent Orchestration | Division of responsibility | External agent framework (any) |

### 1.4 In-Scope Capabilities
| Category | Included Elements |
|----------|------------------|
| Memory Tiers | Working, Short-Term, Long-Term, Episodic, Semantic |
| Retrieval Modes | Hybrid (lexical + vector + temporal + graph), re-ranking, query expansion |
| Lifecycle | Consolidation, summarization, decay, deduplication, conflict resolution (phase 2), archival |
| Context Assembly | Adaptive token budgeting, prioritization, provenance annotations |
| Adapters | Storage (Redis, Vector DBs, SQL, Graph), Embeddings, Caches |
| Observability | Metrics, tracing spans, structured logs, internal decision audit trail |
| Security | Namespace isolation, optional encryption hooks, PII redaction filters |
| Extensibility | Plugin registration for adapters & embedding providers |

### 1.5 Stakeholders
| Stakeholder | Interest | Interaction Mode |
|------------|----------|------------------|
| Platform Engineers | Operability, scaling | Deploy, tune, monitor |
| Applied Researchers | Retrieval quality | Benchmark, adjust ranking knobs |
| Product Engineers | Fast integration | Use high-level SmrtiClient APIs |
| Observability/SRE | Reliability signals | Consume metrics & traces |
| Security/Compliance | Data boundaries | Review namespace isolation, retention policies |

---
## 2. Architecture Overview

### 2.1 Conceptual Diagram (Narrative)

```
		  ┌─────────────────────────────────────────────────┐
		  │                    Consumers                    │
		  │  (Agent runtimes, LLM pipelines, services)      │
		  └───────────────────────┬─────────────────────────┘
								  │  (SmrtiContext Request)
						 ┌────────▼────────┐
						 │  Context Builder │  <-- Adaptive assembly + token budgeting
						 └────────┬────────┘
								  │ (MemoryQuery graph)
				┌─────────────────┼──────────────────┐
				│                 │                  │
		┌───────▼──────┐  ┌───────▼──────┐   ┌───────▼──────┐
		│ Retrieval     │  │ Lifecycle    │   │ Ranking /     │
		│ Orchestrator  │  │ Engine       │   │ Fusion Engine │
		└───────┬──────┘  └───────┬──────┘   └───────┬──────┘
				│                 │                  │
	 ┌──────────┼─────────────────┼──────────────────┼──────────┐
	 │          │                 │                  │          │
┌────▼───┐ ┌────▼───┐       ┌─────▼────┐       ┌──────▼────┐ ┌──▼────────┐
│Working │ │Short-  │       │ Long-Term│       │ Episodic   │ │ Semantic  │
│Memory  │ │ Term   │       │ Memory   │       │ Memory     │ │ Memory    │
│(Redis) │ │(Redis) │       │(Vector + │       │(Events +   │ │(Facts +   │
│        │ │        │       │ SQL)     │       │ Timeline)  │ │ Graph)    │
└───┬────┘ └───┬────┘       └────┬─────┘       └──────┬────┘ └────┬──────┘
	│          │                  │                       │          │
	└────┬─────┴──────────┬───────┴─────────────┬─────────┴──────────┘
		 │                │                     │
   ┌─────▼──────┐   ┌─────▼──────┐        ┌─────▼──────┐
   │ Embeddings │   │ Lexical     │        │ Graph /    │
   │ Providers  │   │ Index (BM25)│        │ Entity DB  │
   └────────────┘   └─────────────┘        └────────────┘
```

### 2.2 Core Subsystems
| Subsystem | Responsibility | Key Interfaces |
|-----------|----------------|----------------|
| Memory Tier Stores | Persist tier-specific records | `TierStore` protocol |
| Retrieval Orchestrator | Plans multi-stage queries across tiers | `RetrievalPlanner`, `MemoryQuery` |
| Lifecycle Engine | Consolidation, summarization, decay, dedup | `LifecycleController` |
| Context Builder | Assembles structured prompt context under constraints | `ContextBuilder`, `TokenBudget` |
| Ranking & Fusion | Hybrid scoring & cross-encoder re-ranking | `Ranker`, `FusionStrategy` |
| Embedding Layer | Embedding generation + caching | `EmbeddingProvider`, `EmbeddingCache` |
| Provenance & Audit | Attach metadata & transformation lineage | `ProvenanceRecord` |
| Observability | Metrics, traces, structured diagnostics | `TelemetryEmitter` |
| Adapter Registry | Discovery & configuration of pluggable backends | `AdapterRegistry` |

### 2.3 Data Flow (Retrieval Request)
1. **Consumer issues `build_context(user_id, query, token_budget=8000)`**
2. Context Builder formulates a **`MemoryQueryPlan`** (set of sub-queries: WM, semantic, episodic, LTM summaries).
3. Retrieval Orchestrator executes sub-queries **in parallel** with adaptive timeouts.
4. Embedding layer computes (or cache-hits) query embedding for vector & hybrid retrieval.
5. Tier Stores return raw candidates (with scores + metadata).
6. Fusion Engine merges lexical, vector, temporal, graph scores → unified ranked list.
7. Re-ranking (optional cross-encoder) refines top-N.
8. TokenBudget prunes / summarizes overflow segments.
9. Provenance records attached; final `SmrtiContext` serialized back.

### 2.4 Data Flow (Write / Encoding)
1. New percept (message, event, fact) arrives via `record_event()` / `store_fact()` / `append_conversation_turn()`.
2. Tier classifier decides target tier (WM vs episodic vs semantic) using rule + embedding heuristics.
3. Writes are **batched** per tier (configurable flush interval) to reduce I/O overhead.
4. LTM writes also persist redundant minimal metadata row in SQL (for filtering) alongside vector store insert.
5. Async enrichment pipeline extracts entities + candidate facts (Phase 2+: conflict resolution & graph linking).
6. Deduplication service compares new items (high-similarity threshold) → merges or discards.
7. Lifecycle scheduler marks items with initial decay parameters.

### 2.5 Memory Tier Characteristics (Preview)
| Tier | Latency Target (p95) | Retention | Purpose | Backend Defaults |
|------|----------------------|-----------|---------|------------------|
| Working | < 15 ms | Minutes | Immediate turn context | Redis / In-memory |
| Short-Term | < 25 ms | Hours / Session | Session continuity | Redis (TTL) |
| Long-Term | < 300 ms | Months | Durable factual + summarized knowledge | Vector DB + SQL metadata |
| Episodic | < 200 ms | Weeks–Months (summarized later) | Temporal sequences of events | Append log + vector optional |
| Semantic | < 350 ms | Months (with archival) | Structured facts, entities, relationships | Graph DB + Vector index |

### 2.6 Design Principles
1. **Separation of Semantics & Storage** – Memory meaning is not bound to a specific database technology.
2. **Progressive Enhancement** – Consumers can start with 2 tiers (WM + LTM) and scale upward.
3. **Asynchronous First** – All I/O boundaries are async; internal CPU-light orchestration.
4. **Deterministic Core, Adaptive Edge** – Retrieval plan deterministic; ranking selects adaptive strategies.
5. **Observability Coupled to Critical Paths** – No feature considered “done” without metrics & spans.
6. **Composable Fusion** – Lexical / vector / graph signals are modular; enable/disable switches per query.
7. **Future-Proof Multimodal Hooks** – Memory records abstract over `content_type` (text, image_ref, audio_ref) early.

### 2.7 Alternatives Considered
| Alternative | Why Not Adopted | Justification for Current Approach |
|-------------|-----------------|-------------------------------------|
| Single flat vector store | Lacks temporal & semantic differentiation | Tiered model improves precision & cost control |
| RDBMS-only (SQL) | Poor semantic similarity performance | Hybrid search critical for relevance |
| Always-on cross-encoder re-ranking | Latency & cost overhead | Make optional; cache results |
| Embedding provider lock-in | Limits portability & experimentation | Protocol abstraction yields flexibility |
| Global chronological conversation log only | Token bloat & irrelevance accumulation | Tiered summarization + pruning superior |

---
## 3. Module Responsibilities

### 3.1 High-Level Module Map
| Module | Purpose | Key Types |
|--------|---------|-----------|
| `core.context` | Orchestrates context assembly & token budgeting | `ContextBuilder`, `TokenBudget`, `SmrtiContext` |
| `core.retrieval` | Multi-tier query planning & execution | `RetrievalPlanner`, `MemoryQueryPlan`, `QueryFragment` |
| `core.ranking` | Score fusion & re-ranking | `FusionStrategy`, `Ranker`, `ReRanker` |
| `core.lifecycle` | Consolidation, summarization, decay, dedup | `LifecycleController`, `DecayPolicy`, `ConsolidationJob` |
| `core.provenance` | Traceability & attribution | `ProvenanceRecord`, `LineageChain` |
| `adapters.storage` | Pluggable tier storage backends | `TierStore`, concrete adapters (RedisStore, ChromaStore) |
| `adapters.embedding` | Embedding model providers & caching | `EmbeddingProvider`, `EmbeddingCache` |
| `adapters.graph` | Entity & relationship persistence | `GraphStore`, `EntityNode`, `RelationEdge` |
| `adapters.lexical` | BM25 / keyword index | `LexicalIndex`, `LexicalResult` |
| `adapters.cache` | Secondary caching (optional) | `ResultCache` |
| `api.client` | Public high-level entrypoints | `SmrtiClient` |
| `api.protocols` | Public interfaces & TypedDicts | `SmrtiProvider`, `StoreCapabilities` |
| `telemetry` | Metrics / tracing / logging glue | `TelemetryEmitter`, `MetricNames` |
| `config` | Settings loading & validation | `Settings`, `TierConfig`, `AdapterConfig` |
| `cli` | Dev kit commands (init, verify, benchmark) | CLI handlers |
| `testing` | Fixtures & harness for adapter certification | `AdapterTestSuite` |

### 3.2 `SmrtiClient` (Facade)
Responsibilities:
1. Expose **minimal ergonomic API** for application developers.
2. Translate high-level ops (`store_event`, `get_context`) into internal protocol calls.
3. Manage adapter instantiation & dependency graph.
4. Enforce namespace / tenant scoping at call boundary.
5. Provide optional sync wrappers around async methods (for legacy stacks).

### 3.3 `SmrtiProvider` Protocol (Preview)
```
class SmrtiProvider(Protocol):
	async def build_context(
		self,
		*,
		user_id: str,
		query: str,
		token_budget: int,
		options: ContextOptions | None = None,
	) -> SmrtiContext: ...

	async def record_event(self, event: EventRecord) -> None: ...
	async def store_fact(self, fact: FactRecord) -> None: ...
	async def append_conversation_turn(self, turn: ConversationTurn) -> None: ...
```
Full specification in Section 5.

### 3.4 Adapter Contracts
| Adapter Type | Mandatory Methods | Optional Extensions |
|--------------|-------------------|---------------------|
| Storage Tier | `write_batch`, `fetch`, `fetch_batch`, `search` | `approximate_search`, `stream_changes` |
| Embedding | `embed_texts`, `embed_query` | `embed_multimodal` (future), `model_metadata` |
| Graph | `upsert_entities`, `upsert_relations`, `traverse` | `cypher_query`, `path_rank` |
| Lexical | `index_documents`, `search` | `suggest_terms` |

### 3.5 Configuration Model (Preview)
| Config Section | Purpose | Example |
|----------------|---------|---------|
| `tiers.working` | Latency-first ephemeral tuning | `backend=redis, ttl=300s` |
| `tiers.short_term` | Session continuity | `backend=redis, ttl=24h` |
| `tiers.long_term` | Durable facts & summaries | `backend=chroma, metadata_backend=postgres` |
| `tiers.episodic` | Event sequences | `backend=postgres` |
| `tiers.semantic` | Structured facts + graph | `backend=neo4j` |
| `retrieval.hybrid` | Fusion weights & enabled modes | `lexical_weight=0.2, vector_weight=0.6, graph_weight=0.2` |
| `lifecycle.decay` | Decay parameters per tier | `half_life_days=30` |
| `context.budget` | Default token budget & priority fractions | `total=8000, wm=0.1, semantic=0.4, episodic=0.3` |

### 3.6 Operational Concerns
| Area | Strategy |
|------|----------|
| Scaling | Horizontal: shard by tenant/user hash; vertical: tune ANN parameters |
| Backpressure | Apply concurrency limits & fast-fail partial retrievals |
| Fault Tolerance | Tier-level fallbacks (e.g., skip semantic if timeout) + partial context assembly |
| Warmup | Preload hot embeddings & lexical index caches at startup |
| Config Reload | Hot reload via immutable config snapshots + atomic swap |
| Schema Evolution | Versioned record envelopes (Section 15) |

### 3.7 Open Questions (To Finalize in Later Sections)
| Question | Impact | Resolution Path |
|----------|--------|-----------------|
| Cross-encoder default on? | Latency vs accuracy | Benchmark Phase 1 dataset |
| Default decay curve shape | Relevance retention | Simulate conversation corpora |
| Graph store: required or optional | Complexity threshold | Make optional adapter (lazy activation) |
| Multimodal embedding path | Future-proofing | Reserve interface; implement Phase 3 |

---
## 4. Memory Types Deep-Dive

### 4.1 Rationale for Five Tiers (Why Not 3 or 7?)
| Candidate Model | Description | Issues | Rejected Because |
|-----------------|-------------|--------|------------------|
| 3-tier (Short / Long / Vector) | Flat separation between ephemeral & persistent | Collides episodic + semantic; no temporal reasoning | Conflates qualitative differences → lower retrieval precision |
| 4-tier (+Episodic) | Adds temporal event chain | Still merges structured facts (preferences) into vector soup | Lacks fact integrity & provenance distinctions |
| 6–7 tier (adds Emotional, Procedural) | Closer to cognitive theory | Over-engineers MVP, raises onboarding cost | Can be deferred; integrate as overlays |
| 5-tier (Chosen) | Working, Short-Term, Long-Term, Episodic, Semantic | Balanced granularity | Clear lifecycle transitions |

The chosen 5-tier taxonomy maximizes orthogonality (each tier answers a distinct class of query) while minimizing conceptual overhead. Emotional / procedural extensions are modeled as **facets** on episodic / semantic records later (Phase 3+).

### 4.2 Unified Record Envelope
All stored items conform (logically) to a canonical envelope enabling consistent introspection & provenance regardless of tier.

```
RecordEnvelope {
  id: UUIDv7,
  tenant: str,
  namespace: str,
  user_id: str | None,           // Optional for global/system memory
  tier: Enum(TIER),
  content_type: Enum(TEXT|FACT|EVENT|SUMMARY|EMBED_REF|MULTIMODAL_PLACEHOLDER),
  payload: Any,                  // Tier-specific body (normalized text, JSON fact, event struct)
  embedding: float[] | None,     // Present if vector-indexed
  semantic_hash: str | None,     // LSH or SimHash for dedup detection
  created_at: timestamp,
  updated_at: timestamp,
  relevance_score: float,        // Dynamic, decays over time
  importance_score: float,       // Static or learning-based weight (Phase 2)
  access_count: int,
  last_accessed_at: timestamp | None,
  decay_params: { half_life_days: float, floor: float },
  lineage: [RecordID],           // Source records (for summaries, consolidations)
  provenance: { source: str, agent: str | None, tool: str | None },
  integrity: { checksum: str | None, version: int },
  metadata: { arbitrary_kv },
  archived: bool
}
```

### 4.3 Working Memory (WM)
| Attribute | Spec |
|-----------|------|
| Purpose | Holds ephemeral turn-local data (current user input, partial tool outputs, ephemeral scratch space). |
| Retention | Minutes (default TTL = 300s); manual explicit flush after turn. |
| Storage Backend | Redis / in-memory ring buffer; fallback: Python dict with LRU. |
| Access Pattern | High write/read frequency, low size (< 2KB per record). |
| Indexing | Keyed by `(tenant, namespace, conversation_id)`; no vector indexing. |
| Lifecycle | Items expire automatically; not consolidated unless flagged. |
| Failure Handling | If unavailable, skip working context; degrade gracefully. |

**Design Choices**:
1. No vector indexing → latency minimized; ephemeral content rarely reused semantically.
2. TTL vs manual deletion → reduces programmer error forgetting to clear conversation residuals.
3. Lightweight schema → boundaries guard against memory explosion.

### 4.4 Short-Term Memory (STM)
| Attribute | Spec |
|-----------|------|
| Purpose | Maintains session continuity across turns (dialog state, unresolved tasks). |
| Retention | Hours (default TTL 6–24h) or bound to `session_id`. |
| Storage Backend | Redis with persistent snapshot or Redis-cluster; optional persistence to disk. |
| Indexing | Optional lexical (message text) + semantic embedding for session summarization triggers. |
| Promotion Trigger | When session closes OR aggregate token size > threshold → summarized into LTM. |
| Consolidation | Summarization pipeline condenses 100+ messages → ~3–5 factual blocks + narrative summary. |

**Multiple Sessions Per User** handled by namespacing `user_id:session_id`. Old sessions decayed or consolidated automatically.

### 4.5 Long-Term Memory (LTM)
| Attribute | Spec |
|-----------|------|
| Purpose | Durable, cross-session factual knowledge + consolidated summaries. |
| Storage Backend | Vector DB (Chroma / Pinecone / Weaviate / Qdrant) + metadata store (Postgres) for filters. |
| Indexing | HNSW / IVF depending on backend; dense embeddings + lexical (BM25) side index (optional). |
| Write Path | Dual-write (vector insert + metadata row). Batched to reduce RPC overhead. |
| Dedup Strategy | Compare semantic_hash + cosine > 0.95 → merge lineage. |
| Summaries | Tag `content_type=SUMMARY`, attach lineage of raw STM source items. Raw items may be archived. |
| Decay | Weighted by last_access + access_count (reinforcement) + base importance. |

**Factual Integrity**: Raw source events preserved (archived) enabling re-summarization if summarizer improves (future model upgrades).

### 4.6 Episodic Memory (EM)
| Attribute | Spec |
|-----------|------|
| Purpose | Sequence of temporally ordered events enabling reconstructable timelines. |
| Storage Backend | Append-only log (Postgres table or time-series DB) + optional vector embedding column for semantic filtering. |
| Indexing | (timestamp, user_id, namespace), optional `(embedding)` for similarity. |
| Query Modes | Time window (e.g., last 7d), event type filter, semantic + temporal hybrid. |
| Summarization | Periodic slicing (e.g., per day) → narrative episodes stored in LTM with lineage. |
| Conflict Handling | Multiple versions of same event retained; NOT mutated retroactively. |

**Reasoning Support**: Enables “What changed since last login?”, “List steps user took before error”.

### 4.7 Semantic Memory (SM)
| Attribute | Spec |
|-----------|------|
| Purpose | Structured facts & entity relationships (preferences, profile data, stable attributes). |
| Storage Backend | Graph DB (Neo4j / Memgraph) + optional vector embedding per node/edge for hybrid queries. |
| Fact Schema | `Fact(entity_id, predicate, object, confidence, valid_from, valid_until | null)`. |
| Entity Resolution | Similarity clustering + alias sets maintained during ingestion. |
| Conflict Resolution | New fact with overlapping `(entity,predicate)` closes `valid_until` of prior (temporal versioning) unless uncertain (< confidence threshold). |
| Graph Queries | Neighborhood expansion, path ranking, attribute roll-ups. |

**Motivation**: Factual queries outperform vector search when structure explicit (e.g., “preferred currency”, “team size”).

### 4.8 Promotion & Demotion Rules
| Source → Target | Trigger Condition | Action | Notes |
|-----------------|------------------|--------|-------|
| WM → STM | Turn completion & flagged as session-relevant | Copy & mark lineage | Avoids polluting STM with transient scratch |
| STM → LTM | Session end OR size > token threshold OR idle > N hours | Summarize → create SUMMARY record → archive raw | Batched summarization saves tokens |
| Episodic → LTM | Periodic window closure (e.g., daily) | Generate daily episode summary | Maintain reconstructability |
| Episodic → Semantic | Fact extraction confidence ≥ threshold | Insert fact (with provenance) | Enables knowledge graph growth |
| Semantic → Archived | Superseded by higher-confidence fact | Close validity; mark archived | Temporal querying preserved |

### 4.9 Decay & Relevance Model
Relevance Score formula (updated opportunistically):
```
relevance = base_importance
			 * exp(-λ * age_days)
			 * (1 + log1p(access_count) * α)
			 * freshness_boost
```
| Term | Meaning |
|------|---------|
| `λ` | Tier-specific decay constant (e.g., WM > high λ, LTM < low λ) |
| `access_count` | Reinforcement: frequently used items persist |
| `freshness_boost` | Temporary multiplier for newly consolidated summaries |
| `base_importance` | Derived from ingestion context (e.g., explicit user preference) |

**Decay Policies**:
| Tier | Half-life (default) | Floor (minimum relevance) |
|------|---------------------|---------------------------|
| WM | 5 min | 0 (hard expire) |
| STM | 6 h | 0.05 |
| LTM | 60 d | 0.1 |
| Episodic (raw) | 30 d | 0.05 |
| Semantic facts | 90 d | 0.2 (facts rarely decayed aggressively) |

### 4.10 Archival & Cold Storage
| Purpose | Policy |
|---------|--------|
| Cost control | Offload low-relevance, low-access raw records to object storage (S3 / GCS) |
| Re-summarization | Retain raw lineage blobs for future summarizer upgrades |
| Compliance | Allows full export / data deletion at user request |

**Mechanism**: Records moved to cold tier with pointer stub (keeps metadata + lineage + minimal payload digest). Retrieval pipeline **skips** unless explicitly requested with `include_archived=true`.

### 4.11 Consistency & Integrity
| Aspect | Strategy |
|--------|----------|
| Write Atomicity | Use idempotent batch tokens; on partial failure mark retry set |
| Lineage Integrity | Disallow deletion of sources while summaries reference them (unless cascading) |
| Schema Evolution | Versioned record envelope; migration script upgrades lazily on read |
| Duplicate Prevention | LSH + threshold gating before vector insert |

### 4.12 Multimodal Preparedness (No Implementation Yet)
| Future Content Type | Placeholder Handling Now | Future Extension Point |
|---------------------|-------------------------|-----------------------|
| Image | `content_type=EMBED_REF` + metadata | Add `ImageEmbeddingProvider`, CLIP adapter |
| Audio | Treat as transcript (payload.text) | Add waveform fingerprint + emotion facets |
| Video | Keyframe extracted as multiple EMBED_REF items | Frame sampling pipeline & temporal alignment |
| Document | Pre-split into sections (payload: chunk) | Structural table / figure extraction |

## 5. Provider & Adapter Protocols

### 5.1 Design Goals
| Goal | Implication |
|------|-------------|
| Minimal surface area | Narrow, essential async methods only |
| Capability discovery | Adapters declare supported features via flags |
| Failure isolation | Partial failures produce degraded but usable context |
| Observability-first | Every provider call emits standardized spans + metrics |
| Testability | Reference harness auto-validates contract adherence |

### 5.2 Core Public Interfaces (Conceptual)
```
class SmrtiProvider(Protocol):
	async def build_context(
		self,
		*,
		user_id: str,
		query: str,
		token_budget: int,
		options: ContextOptions | None = None,
	) -> SmrtiContext: ...

	async def record_event(self, event: EventRecord) -> None: ...
	async def store_fact(self, fact: FactRecord) -> None: ...
	async def append_conversation_turn(self, turn: ConversationTurn) -> None: ...
	async def flush(self) -> None: ...  # Force batch flush

class TierStore(Protocol):
	async def write_batch(self, records: list[RecordEnvelope]) -> WriteResult: ...
	async def fetch(self, record_id: str) -> RecordEnvelope | None: ...
	async def search(self, query: TierSearchQuery) -> list[RecordEnvelope]: ...
	async def approximate_search(self, query: VectorQuery) -> list[VectorResult]: ...  # optional
	async def stats(self) -> TierStats: ...

class EmbeddingProvider(Protocol):
	async def embed_texts(self, texts: list[str], *, model: str | None=None) -> list[list[float]]: ...
	async def embed_query(self, text: str, *, model: str | None=None) -> list[float]: ...
	def metadata(self) -> EmbeddingMetadata: ...

class GraphStore(Protocol):
	async def upsert_entities(self, entities: list[EntityNode]) -> None: ...
	async def upsert_relations(self, relations: list[RelationEdge]) -> None: ...
	async def traverse(self, request: GraphTraverseRequest) -> GraphTraverseResult: ...

class LexicalIndex(Protocol):
	async def index_documents(self, docs: list[LexicalDocument]) -> None: ...
	async def search(self, query: str, top_k: int) -> list[LexicalHit]: ...
```

### 5.3 Capability Flags
Adapters publish capabilities for dynamic planning:
```
StoreCapabilities {
  supports_vector: bool,
  supports_hybrid: bool,
  supports_approximate: bool,
  supports_temporal_range: bool,
  supports_graph_ops: bool,
  durability_level: Enum(MEMORY|LOCAL_PERSIST|REPLICATED|DISTRIBUTED),
  max_batch_size: int,
  estimated_p95_latency_ms: int
}
```

Planner uses capabilities matrix to choose fallback paths (e.g., if semantic tier lacking hybrid → rely on lexical + vector tiers).

### 5.4 Error Taxonomy
| Category | Definition | Handling Strategy |
|---------|------------|-------------------|
| `RetryableTransient` | Network hiccup, timeout, rate limit | Exponential backoff (≤ 3 attempts), emit metric |
| `PartialDegradation` | Some tiers fail, others succeed | Return partial context + warnings |
| `NonRetryable` | Validation error, malformed adapter response | Surface error, do not retry |
| `CapacityExceeded` | Batch > configured limits | Split & re-attempt; adjust planner heuristics |
| `IntegrityViolation` | Lineage inconsistency, checksum mismatch | Quarantine record, alert |

### 5.5 Adapter Lifecycle Hooks
| Phase | Hook | Purpose |
|-------|------|---------|
| Initialization | `async def initialize()` | Establish connections, warm caches |
| Health Check | `async def health()` | Readiness probe (latency + basic ops) |
| Warmup | `async def warm_indexes()` | Preload hot embeddings / lexical shards |
| Shutdown | `async def close()` | Flush buffers, close sockets |

### 5.6 Configuration Precedence
1. **Runtime kwargs** (highest)
2. Environment variables (`SMRTI_*` prefix)
3. Config file (YAML / TOML)
4. Adapter defaults
5. Hardcoded safe fallback (lowest)

Conflicting keys resolved by *first-found wins*; all resolved config exported via `settings_snapshot()` for audit.

### 5.7 Deployment Topology Examples
| Topology | Description | Use Case |
|----------|-------------|----------|
| Minimal Dev | In-memory WM + STM, local Chroma for LTM, no graph | Quick prototyping |
| Standard SaaS | Redis cluster (WM/STM), Pinecone (LTM), Postgres (episodic), Neo4j (semantic) | Multi-tenant app |
| High Throughput | Redis + Weaviate (GPU ANN), Kafka ingest for episodic stream | Real-time analytics assistants |
| Cost Optimized | Redis (shared), Qdrant (LTM), Skip graph until needed | Early-stage product |
| Compliance Focused | Encrypted Postgres (facts), BYOK KMS, dedicated tenancy | Regulated industries |

### 5.8 Adapter Certification Checklist
| Requirement | Test | Pass Criterion |
|-------------|------|---------------|
| Idempotent write_batch | Re-send same batch | No duplicate records |
| Latency budget | 500 sample ops | p95 < declared capability |
| Failure isolation | Induce vector store failure | Other tiers unaffected |
| Consistent search ordering | Same query repeated | Deterministic ordering for identical scores (stable sort) |
| Provenance retention | Ingest + retrieve | Lineage preserved exactly |

### 5.9 Reference Pseudo-Implementations
```
class RedisWorkingStore(TierStore):
	async def write_batch(self, records):
		# Pipeline writes with EX TTL per record
		...
	async def fetch(self, record_id): ...
	async def search(self, query): return []  # Not supported; WM direct key access

class VectorLongTermStore(TierStore):
	async def write_batch(self, records):
		# Extract embeddings, bulk upsert
		...
	async def approximate_search(self, query):
		# Delegate to backend ANN search
		...

class Neo4jSemanticGraph(GraphStore):
	async def upsert_entities(self, entities): ...
	async def traverse(self, request): ...
```

### 5.10 Extensibility Guidelines
| Aspect | Guideline |
|--------|-----------|
| Naming | Use `smrti-<adapter>-<backend>` for external PyPI packages |
| Versioning | Follow semantic versioning; breaking API → major bump |
| Documentation | MUST include capability table & config keys |
| Testing | MUST pass `AdapterTestSuite` with ≥ 95% critical tests green |
| Security | Never log secrets; redact connection URIs |

### 5.11 Open Issues (To Resolve in Later Sections)
| Issue | Concern | Proposed Path |
|-------|---------|---------------|
| Cross-encoder model selection | Latency variance | Benchmark small vs large models; dynamic switch |
| Adaptive decay tuning | Avoid over-pruning | Feedback loop using retrieval miss analysis |
| Graph store optionality | Complexity vs benefit | Lazy load only if semantic tier configured |
| Cold storage indexing | Search archived efficiently | Maintain side metadata index |

---
## 6. Context Assembly (Adaptive Prompt Construction)

### 6.1 Objectives
Produce the *most useful* composite context for an LLM under a strict token budget while:
1. Preserving high-signal information (facts, recent intent shifts, unresolved tasks)
2. Ensuring diversity (avoid overfitting to only semantic facts or only recency)
3. Maintaining explainability (why each fragment was included)
4. Minimizing latency (parallel retrieval + early pruning)
5. Enabling downstream formatting neutrality (consumer chooses final prompt style)

### 6.2 Inputs & Outputs
| Element | Description |
|---------|-------------|
| `user_id` | Subject principal (may be anonymous or system) |
| `query` | Natural language or structured retrieval intent |
| `token_budget` | Hard upper bound (e.g., 8000) |
| `ContextOptions` | Overrides (disable graph, force include facts, min_relevance, max_facts, etc.) |
| Output: `SmrtiContext` | Structured object with ordered sections + provenance + token_estimate |

### 6.3 High-Level Algorithm
```
function build_context(user_id, query, token_budget):
	plan = planner.create_plan(user_id, query)
	parallel_results = execute_subqueries(plan)  # WM, semantic, episodic, facts, summaries
	ranked = fusion_engine.rank(parallel_results)
	bucketed = bucket_by_section(ranked)  # working, semantic_facts, episodic_events, ltm_summaries, user_profile
	allocate_tokens(bucketed, token_budget)  # priority-based → soft caps
	while over_budget():
			apply_reduction_strategy(next_priority())  # summarize, prune low relevance, collapse similar facts
	attach_provenance(bucketed)
	return assemble_context(bucketed)
```

### 6.4 Section Priority & Default Allocation
| Section | Typical Content | Default Allocation (fraction of budget) | Reduction Order |
|---------|-----------------|-----------------------------------------|-----------------|
| Working Memory | Current turn input, tool interim outputs | 0.10 | Summarize tool outputs → keep raw input |
| Semantic Facts | High-confidence profile/preferences | 0.25 | Drop lowest relevance facts → cluster similar |
| Episodic Events | Recent time-bounded events (7d) | 0.25 | Summarize chronological blocks |
| LTM Summaries | Session or periodic summaries | 0.20 | Switch to ultra-short summary form |
| Derived Patterns | Behavior patterns, usage stats | 0.10 | Remove pattern block entirely |
| Reserved Slack | Buffer for late expansions | 0.10 | Eliminated last |

*All fractions configurable via `context.budget`.*

### 6.5 Reduction Strategies (Applied Iteratively)
| Strategy | Trigger | Action | Cost Impact |
|----------|---------|--------|-------------|
| Summarize Episodic Block | Episodic > 1.2× share | LLM or rule-based summarizer compresses events to bullet timeline | 40–70% tokens saved |
| Fact Clustering | > N facts of similar cosine ≥ 0.92 | Replace cluster with merged representative + counts | 20–50% reduction in fact tokens |
| Pattern Downgrade | Over budget and low pattern relevance | Remove pattern section | Up to 10% |
| Summary Compression | LTM summaries exceed share | Convert paragraphs → bullet abstractions | 30–50% |
| Drop Low Relevance Tail | Relevance < adaptive threshold T | Remove tail items | Linear w/ removed items |
| Fallback Minimal Context | Still > budget after all | Keep working + top-K facts + 1 summary | Hard fallback |

### 6.6 Provenance Schema (Per Fragment)
```
ProvenanceRecord {
	record_id: str,
	tier: str,
	source_type: str,            // FACT|EVENT|SUMMARY|PATTERN|WORKING
	original_tokens: int,
	current_tokens: int,
	relevance_score: float,
	selection_reason: str,       // top_k|explicit|high_importance|boosted
	transformations: [           // chronological transformations
		{ type: "summarize", model: "gpt-4o-mini", reduction_ratio: 0.55 },
		{ type: "cluster-merge", cluster_size: 4 }
	]
}
```

### 6.7 Token Estimation & Enforcement
| Phase | Method | Notes |
|-------|--------|-------|
| Pre-Retrieval | Heuristic (avg chars/token) | Fast, coarse (for planning) |
| Post-Ranking | Tiktoken count per fragment | Accurate; costlier but limited to candidates |
| Final Assembly | Hard cap enforcement | If overflow → trigger additional reductions |

**Overflow Loop**: Maximum 5 reduction cycles; after that minimal fallback.

### 6.8 Context Object (Conceptual Structure)
```
SmrtiContext {
	user_id: str,
	query: str,
	generated_at: timestamp,
	token_budget: int,
	estimated_tokens: int,
	sections: [
		{ name: "working", items: [...] },
		{ name: "semantic_facts", items: [...] },
		{ name: "episodic_recent", items: [...] },
		{ name: "summaries", items: [...] },
		{ name: "patterns", items: [...] }
	],
	provenance: [ProvenanceRecord],
	stats: { reductions_applied: int, discarded_items: int, version: 1 }
}
```

### 6.9 Edge Cases
| Scenario | Handling |
|----------|----------|
| Extremely short budget (< 500 tokens) | Skip episodic & patterns; emit top facts only |
| No retrievable memories | Return working section + empty placeholders |
| High duplication detected | Force clustering before ranking |
| Time-constrained retrieval (timeout) | Partial subset labeled with warnings |
| Query requests archived items | Planner enables archived scan path |

### 6.10 Determinism & Caching
Cache key: hash(user_id, query_embedding, budget, enabled_sections, revision_hash)
| Layer | TTL | Content |
|-------|-----|---------|
| Query Embedding Cache | 5–30 min | Embedding vector |
| Retrieval Candidate Cache | 1–5 min | Raw candidate IDs per subquery |
| Final Context Cache | 30–120 s | Fully assembled context (avoid duplicate consecutive calls) |

### 6.11 Open Issues
| Issue | Concern | Mitigation Path |
|-------|---------|-----------------|
| Explainability verbosity | Large provenance payload | Allow compression / omit transforms flag |
| Cross-user shared memories | Potential leakage risk | Strict opt-in & masked provenance |
| Importance score learning | Cold start | Begin with heuristic weights; collect feedback telemetry |

---
## 7. Query & Retrieval Strategies

### 7.1 Retrieval Pipeline Stages
| Stage | Description | Parallelizable |
|-------|-------------|----------------|
| Query Embedding | Encode query text | Yes |
| Subquery Generation | Plan lexical / semantic / episodic / graph subqueries | Yes |
| Candidate Retrieval | Execute backend searches | Yes |
| Score Normalization | Map different score domains to [0,1] | Yes |
| Fusion & Ranking | Combine weighted scores → unified order | No (aggregation) |
| Optional Re-Ranking | Cross-encoder refine top N | Partially (batch) |

### 7.2 Hybrid Score Fusion
Scores normalized via min-max per modality batch.
```
final_score = w_vector * s_vector
						 + w_lexical * s_lexical
						 + w_graph * s_graph
						 + w_temporal * s_temporal
						 + w_recency * recency_boost
```
| Weight | Default | Notes |
|--------|---------|-------|
| `w_vector` | 0.45 | Primary semantic relevance |
| `w_lexical` | 0.20 | Exact term precision |
| `w_graph` | 0.15 | Entity linkage strength |
| `w_temporal` | 0.10 | Episodic recency alignment |
| `w_recency` | 0.10 | General freshness bias |

Dynamic adjustment: If lexical results sparse (< K) shift 50% of lexical weight to vector & graph proportionally.

### 7.3 Query Expansion Techniques
| Technique | Implementation | Use Case |
|-----------|---------------|----------|
| Synonym Expansion | Static domain synonym map + embedding nearest neighbors | Domain-specific vocab |
| Entity Alias Resolution | Graph alias set retrieval | Users / product codes |
| Semantic Paraphrase | Lightweight LLM pass (temperature=0) | Ambiguous queries |
| Temporal Augmentation | Add inferred time window tokens ("past week") | Episodic alignment |
| Intent Pattern Injection | Recognize question type (who/what/when) | Fact vs event prioritization |

**Expansion Budget Cap**: Limit expanded variants to 5 to avoid recall noise.

### 7.4 Re-Ranking
| Mode | Model | Trigger | Notes |
|------|-------|--------|-------|
| Disabled | - | Default when latency-sensitive | p95 < 150 ms aim |
| Lightweight | MiniLM cross-encoder | Candidate count > 30 | Adds ~30–50 ms |
| High Fidelity | Larger cross-encoder / reranker LLM | High importance queries flag | Adds 120–250 ms |

Results cached by (query_embedding_hash, top_k_ids, reranker_model_version).

### 7.5 Temporal Scoring
```
recency_boost = exp(-μ * age_days)
```
μ tuned per tier (episodic > ltm). Combined multiplicatively in fusion formula.

### 7.6 Graph Traversal Heuristics
| Query Pattern | Traversal Strategy |
|---------------|-------------------|
| Fact look-up ("preferred currency") | Direct predicate index → fact node |
| Relationship expansion ("team members") | 1-hop outward with role filter |
| Context enrichment ("project status") | 2-hop radius then prune by relevance threshold |
| Alias resolution | Alias node → canonical entity → facts |

### 7.7 Failure Degradation Matrix
| Failure | Fallback |
|---------|----------|
| Vector store timeout | Lexical + graph only |
| Lexical index missing | Increase vector weight; attempt vector-only rerank |
| Graph store disabled | Skip graph weights; redistribute to vector |
| Re-ranker timeout | Use pre-fusion order |
| Embedding provider failure | Use cached previous embedding or lexical only |

### 7.8 Retrieval Metrics (Preview)
| Metric | Definition |
|--------|-----------|
| `retrieval_latency_ms{stage}` | Duration per pipeline stage |
| `retrieval_candidates_total{modality}` | Candidate count returned |
| `retrieval_cache_hit_ratio{layer}` | Cache efficacy |
| `retrieval_rerank_delta{model}` | Improvement in MAP / NDCG |
| `retrieval_degradation_total{type}` | Number of fallback activations |

### 7.9 Planner Adaptation
Planner monitors rolling window of:
1. Average recall drop when skipping lexical
2. Latency impact of re-ranker
3. Weight effectiveness (feature attribution)

Adjusts weights within bounded ranges (±0.1 per 15-minute interval) under stability guard (no oscillation > 3 adjustments/hour).

### 7.10 Open Questions
| Question | Impact | Resolution |
|----------|--------|-----------|
| Should weights learn from user feedback? | Personalization | Phase 2 implicit feedback loop |
| Multi-query batching usefulness? | Latency vs complexity | Benchmark; maybe enable for bulk retrieval use cases |
| Semantic drift detection threshold? | Relevance stability | Track variance in top embedding neighbors |

---
## 8. Lifecycle Management

### 8.1 Objectives
Maintain memory *quality* over time by preventing uncontrolled growth, redundancy, and factual inconsistency while preserving reconstructability and auditability.

### 8.2 Lifecycle Stages
| Stage | Description | Applies To |
|-------|-------------|-----------|
| Ingestion | Raw record creation with initial metadata | All tiers |
| Enrichment | Embedding, entity extraction, semantic hash calc | LTM, episodic, semantic |
| Consolidation | Summarization & promotion | STM → LTM, episodic → LTM |
| Deduplication | Merge high-similarity items | LTM, semantic |
| Conflict Resolution | Temporal closure of superseded facts | Semantic facts |
| Decay | Relevance recomputation & potential archival | All persistent tiers |
| Archival | Offload cold payloads | LTM raw, episodic raw |
| Re-summarization | Regenerate improved summaries w/ better models | Summaries |

### 8.3 Consolidation Pipeline
```
trigger: (session_end OR stm_size > threshold OR idle_time > X)
	→ collect STM messages
	→ cluster by topic (semantic embedding + agglomerative)
	→ per-cluster summarization (LLM or rule heuristics)
	→ extract candidate facts (entity + predicate patterns)
	→ create SUMMARY record (lineage = original message IDs)
	→ mark originals archived (if configured)
```

| Step | Failure Handling |
|------|------------------|
| Clustering fail | Fallback single block summary |
| Summarization timeout | Retry once then short-form extractive summary |
| Fact extraction low confidence | Skip fact emission; record metric |

### 8.4 Summarization Strategies
| Mode | Description | Use Case |
|------|-------------|----------|
| Extractive | Select key sentences via scoring (TextRank / MMR) | Fast, low compute budgets |
| Abstractive LLM | LLM guided + constraints (max tokens) | Rich, user-facing quality |
| Hybrid | Extractive shortlist → LLM condense | Balanced accuracy & brevity |

Default: Hybrid (extractive reduces LLM input tokens by ~60%).

### 8.5 Fact Extraction Pipeline
```
summary_text → NER (entities) → relation templates → candidate triples
	→ normalize entities (alias resolution) → confidence scoring
	→ insert Fact(entity, predicate, object, confidence)
```
Confidence scoring factors: model certainty, predicate whitelist, duplication penalty.

### 8.6 Conflict Resolution
| Scenario | Resolution Logic |
|----------|------------------|
| New fact same (entity,predicate) higher confidence | Close previous `valid_until = now` |
| Equal confidence conflicting objects | Keep both; mark ambiguous; lower relevance weight |
| Lower confidence update | Store as tentative; not surfaced unless requested |

### 8.7 Entity Resolution
| Step | Technique |
|------|----------|
| Candidate Generation | Embedding nearest neighbors (cosine > 0.85) |
| Blocking | First letter + length band + hash prefix |
| Scoring | Weighted sum (name similarity, context overlap, co-mentioned frequency) |
| Merge Decision | Threshold > 0.9 OR manual (future) |

Alias set stored; future mentions normalized to canonical ID.

### 8.8 Deduplication
| Dimension | Method |
|----------|--------|
| Semantic | Embedding cosine > 0.95 + length ratio | Merge payload; aggregate lineage |
| Lexical | MinHash / SimHash | Quick pre-filter |
| Structural | Same fact triple | Increment access_count |

### 8.9 Decay Scheduler
Runs periodic job (default every 6h):
```
for record in active_records:
	age_days = (now - created_at)/86400
	relevance = compute_relevance(record)
	if relevance < archive_threshold[tier]:
			archive(record)
	else if relevance < compress_threshold and record.is_summary:
			compress_summary(record)
```

### 8.10 Maintenance Jobs Overview
| Job | Frequency | SLA Target | Notes |
|-----|-----------|-----------|-------|
| Consolidation | Event-driven + hourly sweep | p95 < 2s per batch | Batches ≤ 500 messages |
| Decay Recompute | Every 6h | Completes < 10 min | Sharded by tenant |
| Dedup Sweep | Daily | Completes < 30 min | Work queue + backpressure |
| Fact Re-validation | Weekly | Completes < 2 h | Re-score low-confidence facts |
| Re-summarization (model upgrade) | Ad hoc | N/A | Version gating |

### 8.11 Failure Modes & Mitigations
| Failure | Impact | Mitigation |
|---------|--------|-----------|
| Consolidation backlog | STM growth, token waste | Backpressure alerts, scale workers |
| Dedup false positives | Data loss risk | Confidence gating + lineage retention |
| Aggressive decay | Loss of relevant context | Floor relevance, anomaly alerts |
| Entity over-merge | Fact contamination | Reversible merge log, rollback tool |
| Archival index corruption | Unreachable cold data | Redundant metadata index snapshot |

### 8.12 Observability Hooks (Preview)
| Metric | Purpose |
|--------|---------|
| `lifecycle_consolidations_total` | Volume & trend |
| `lifecycle_decay_archived_total{tier}` | Data churn visibility |
| `lifecycle_dedup_merged_total` | Redundancy savings |
| `lifecycle_fact_conflict_total` | Knowledge volatility |
| `lifecycle_entity_merge_total` | Resolution aggressiveness |

### 8.13 Open Questions
| Question | Impact | Resolution Path |
|----------|--------|-----------------|
| Should summarization be user-tunable model selection? | Cost vs quality trade | Provide per-tenant override |
| Learn decay parameters online? | Adaptive retention | Phase 3 reinforcement loop |
| Should ambiguous facts trigger human review queue? | Data trust | Optional callback hook |

---
<!-- Section content stabilized; further changes tracked via ADR updates. -->
## 9. Observability & Telemetry

### 9.1 Objectives
Provide deep, low-overhead introspection into memory operations such that engineers can answer:
1. Why did this context include (or exclude) a given fact?
2. Which tier is the latency bottleneck this hour?
3. Are decay & consolidation reducing noise effectively?
4. How do retrieval relevance metrics trend over releases?

### 9.2 Metrics Catalog
| Metric | Type | Labels (cardinality guidance) | Description |
|--------|------|-------------------------------|-------------|
| `smrti_request_total` | Counter | `status` (success|error), `operation` (build_context|store_event|store_fact) | High-level API usage |
| `smrti_request_latency_ms` | Histogram | `operation` | End-to-end latency distribution |
| `retrieval_stage_latency_ms` | Histogram | `stage` (embed|plan|fetch|fusion|rerank) | Per pipeline stage duration |
| `retrieval_candidates_total` | Counter | `modality` (vector|lexical|graph|episodic) | Raw candidate volume |
| `retrieval_fusion_weight` | Gauge | `modality` | Effective runtime weight after adaptation |
| `retrieval_degradation_total` | Counter | `type` (vector_timeout|graph_disabled|rerank_timeout) | Fallback activations |
| `context_reduction_steps_total` | Counter | `strategy` (summarize|cluster|drop_tail|minimal) | Reduction strategy invocation count |
| `context_final_tokens` | Histogram | none | Token size of final context |
| `context_token_savings_ratio` | Histogram | none | (raw_estimate - final)/raw_estimate |
| `lifecycle_consolidations_total` | Counter | `result` (success|error|partial) | Consolidation executions |
| `lifecycle_decay_archived_total` | Counter | `tier` | Records archived due to decay |
| `lifecycle_dedup_merged_total` | Counter | `tier` | Duplicates merged |
| `fact_conflict_total` | Counter | `resolution` (supersede|ambiguous|tentative) | Fact conflict outcomes |
| `entity_merge_total` | Counter | `decision` (auto|manual|rollback) | Entity resolution operations |
| `tier_storage_usage_bytes` | Gauge | `tier` | Approx logical payload footprint |
| `adapter_latency_ms` | Histogram | `adapter`, `method` | Adapter call latency |
| `embedding_provider_latency_ms` | Histogram | `model` | Embedding call performance |
| `cache_hit_ratio` | Gauge | `layer` (embedding|candidates|context) | Cache effectiveness |
| `error_total` | Counter | `category` (retryable|non_retryable|integrity) | Error volumes segmented |

### 9.3 Tracing Model
Root Span: `smrti.build_context`
Child Spans (examples):
| Span | Attributes |
|------|-----------|
| `planner.create_plan` | `query_length`, `plan_subqueries` |
| `retrieval.execute` | `subquery_count` |
| `adapter.vector.search` | `top_k`, `latency_ms`, `backend` |
| `fusion.rank` | `candidates_in`, `candidates_out` |
| `rerank.apply` | `model`, `latency_ms`, `before_ndcg`, `after_ndcg` |
| `budget.allocate` | `initial_estimate_tokens`, `budget` |
| `reduction.apply` | `strategy`, `tokens_saved` |

Trace Events: reduction cycle application, fallback activation, partial degradation annotation.

### 9.4 Log Strategy
| Level | Content | Redaction |
|-------|---------|-----------|
| DEBUG | Detailed planning decisions (disabled in prod by default) | PII masking enforced |
| INFO | Lifecycle job outcomes, adapter registration, config snapshot hash | No raw payloads |
| WARN | Partial degradations, nearing storage quotas | PII stripped |
| ERROR | Adapter failures, integrity violations | Scrub embeddings & secrets |

Structure: JSON lines including `trace_id`, `span_id`, `tenant`, `namespace`.

### 9.5 Cardinality Controls
- Enforce adapter label whitelist to prevent cardinality explosion.
- Hash user identifiers when used for debug (not in metrics).
- Collapse unknown errors into `error_total{category="non_retryable"}` with opaque code mapping table for internal correlation.

### 9.6 Observability Deployment
| Component | Integration |
|-----------|------------|
| Metrics | Prometheus endpoint `/metrics` |
| Tracing | OpenTelemetry OTLP exporter (gRPC/HTTP) |
| Logs | Structured JSON → stdout (ingest by Fluent Bit) |
| RUM (Optional) | Not applicable (no user-facing UI) |

### 9.7 SLO Drafts
| SLO | Objective | Initial Target |
|-----|----------|----------------|
| Build Context Latency | p95 < 400 ms | 99% over 30-day window |
| Vector Retrieval Error Rate | < 0.5% | Rolling 7-day |
| Consolidation Success Rate | ≥ 99% | Rolling 30-day |
| Recall Benchmark Stability | ±5% variance | Per release |

### 9.8 Debug Tooling Concepts
| Tool | Description |
|------|-------------|
| `smrti trace <trace_id>` | Formats provenance + ranking rationale |
| `smrti metrics diff --window=1h` | Compares current vs previous hour aggregated metrics |
| `smrti replay --context-id` | Reconstructs context assembly for audit |

### 9.9 Open Issues
| Issue | Concern | Follow-up |
|-------|---------|-----------|
| Provenance size inflation | Increases network payload | Compression toggle |
| Metric overload | Developer overwhelm | Provide default Grafana dashboards |

---
## 10. Security & Privacy

### 10.1 Threat Model (Condensed)
| Threat | Vector | Mitigation |
|--------|--------|-----------|
| Cross-tenant data leak | Namespace mishandling | Mandatory namespace param, integration tests, deny on missing namespace |
| PII exposure in logs | Logging raw payloads | Central redaction filter (regex + structured fields), security review gates |
| Unauthorized memory access | Weak control plane | Delegate authN/Z to integrator; enforce signed `tenant` + hashed `user_id` contract |
| Poisoning (malicious content inserted) | Unvalidated ingest | Size limits, content-type validation, optional allowlist heuristics |
| Re-identification after hashing | Weak hashing | Use salted HMAC (tenant-specific salt) |
| Injection in graph queries | Dynamic Cypher | Parameterized queries only |
| Stale revoked data persisting | Delayed deletion | Triage queue + deletion SLA metrics |

### 10.2 Data Classification
| Class | Examples | Handling |
|-------|----------|----------|
| PUBLIC | Generic product facts | No special controls |
| INTERNAL | Non-sensitive interaction logs | Namespace isolation |
| SENSITIVE | Emails, addresses, payment hints | Redact display; encrypt at rest (adapter-provided) |
| HIGHLY_SENSITIVE | Health, financial specifics | Exclude by default; require explicit flag |

### 10.3 Privacy-by-Design Principles
1. **Minimize**: Do not store raw large payloads when normalized fact sufficient (if configured).
2. **Partition**: Tenant & namespace always explicit; never default global storage implicitly.
3. **Provenance Without Payload**: Provenance may outlive archived content safely.
4. **Right to Erasure**: Lookup by hashed user identifier; cascade deletes across envelope tables; maintain tombstone to prevent re-ingest confusion.
5. **Configurable Retention**: Tier-level `max_retention_days`; archived beyond retention → purge.

### 10.4 PII Redaction Filters
| Pattern | Technique | Notes |
|---------|----------|-------|
| Emails | Regex + canonicalization | Replace with `<email:hash>` |
| Phone Numbers | Region-aware regex | `<phone:hash>` |
| Credit Card Fragments | Luhn partial detection | Remove or mask; never store full PAN |
| Names (Optional) | NER-based (precision tuned) | Only if configured (risk of over-redaction) |

### 10.5 Encryption Strategy (Adapter Mediated)
| Layer | Strategy |
|-------|----------|
| At Rest | Rely on underlying managed service (KMS) OR envelope encrypt payload before storage |
| In Transit | TLS enforced to all adapters |
| Key Management | Provided by integrator; Smrti exposes interface for custom encrypt/decrypt hooks |

### 10.6 Integrity & Tampering
| Mechanism | Purpose |
|----------|---------|
| Checksums (SHA-256) | Detect accidental corruption |
| Signed Fact Records (optional) | Non-repudiation for high-trust domains |
| Immutable Lineage Links | Prevent silent history rewrites |

### 10.7 Access Patterns & Least Privilege
Split credentials per tier adapter (scoped). Graph adapter cannot modify vector store; vector store credentials read-only outside ingestion path.

### 10.8 Compliance Readiness (Foundational)
| Standard | Preparedness |
|----------|-------------|
| GDPR | Erasure hooks + data classification |
| SOC2 | Audit logs + change management guidelines |
| HIPAA (future) | Need additional encryption attestations |

### 10.9 Open Issues
| Issue | Impact | Path |
|-------|--------|------|
| Fine-grained field-level encryption | Complexity vs need | Defer until regulated customer demand |
| Differential privacy for analytics | Resource cost | Feasibility study after baseline adoption |

---
## 11. Performance & Scalability

### 11.1 Targets (Revisited)
| Scenario | p50 | p95 | Notes |
|----------|-----|-----|------|
| build_context (cold) | 180 ms | 400 ms | Cold = empty caches |
| build_context (warm) | 90 ms | 250 ms | Warm embeddings + candidate cache |
| vector_search (single) | 40 ms | 120 ms | ANN tuned indexes |
| lexical_search | 10 ms | 25 ms | In-process / Redis-backed BM25 |
| graph_traversal | 30 ms | 150 ms | Dependent on hop count |
| consolidation_batch | 500 ms | 2000 ms | Batch 200 messages |

### 11.2 Scaling Levers
| Lever | Impact | Trade-off |
|-------|--------|----------|
| Horizontal Sharding | Linear throughput increase | Complexity in routing |
| Async Concurrency | Hides I/O latency | Potential adapter saturation |
| Query Batching | Reduced RPC overhead | Slight additional latency per user |
| Embedding Caching | Lower embedding calls | Memory footprint |
| ANN Parameters (M, ef) | Latency vs recall control | Tuning effort |
| Re-rank Sampling | Lower cost | Potential quality drop |
| Write Buffering | Higher throughput | Risk of data loss on crash (mitigate flush intervals) |

### 11.3 Capacity Planning Model (Simplified)
```
Qps_context = Users_active * Requests_per_user_per_min / 60
Vector_Qps = Qps_context * Avg_vector_subqueries
Required_nodes_vector = ceil( Vector_Qps * Avg_latency_ms / (1000 * Target_utilization) )
```
Target utilization ≤ 0.65 for headroom.

### 11.4 Backpressure Strategy
| Condition | Action |
|-----------|--------|
| Queue depth > threshold | Drop low-priority episodic subquery first |
| Embedding latency spike | Temporarily disable rerank & reduce vector top_k |
| Consolidation lagging | Increase worker pool or raise summarization thresholds |

### 11.5 Hot Path Optimizations
| Optimization | Implementation |
|-------------|----------------|
| Zero-copy payload passing | Use memoryviews / avoid JSON roundtrips internally |
| Structured binary provenance (optional) | Serialize to MessagePack internally | JSON only at API boundary |
| Adaptive top_k | Start large (k=100) then truncate early after lexical/graph fusion | Saves embedding re-rank cost |
| Parallel summarization | Async gather per topic cluster | Reduces consolidation latency |

### 11.6 Cost Controls
| Area | Technique |
|------|----------|
| Embeddings | Cache; batch encode; choose small model default |
| Storage | Compress archived summaries (zstd) |
| Re-ranking | Apply only when candidate_count > threshold |
| Graph | Lazy enable only if semantic tier configured |

### 11.7 Benchmarking Methodology
| Layer | Tooling |
|-------|---------|
| Micro (adapter) | Custom async harness + pytest-benchmark |
| End-to-end | Locust / k6 (build_context scenarios) |
| Relevance | Golden dataset (query→expected fact/event IDs) |
| Lifecycle | Synthetic corpora growth simulation |

### 11.8 Open Issues
| Issue | Impact | Plan |
|-------|--------|------|
| Multi-region latency variance | Cross-geo users | Introduce region pinning + replication |
| Graph becoming bottleneck | Fusion slowdowns | Add result sampling + caching |
| Memory footprint of caches | Resource pressure | Size-based eviction + metrics alerts |

---
## 12. Testing & Quality Strategy

### 12.1 Testing Pillars
| Pillar | Goal |
|--------|------|
| Correctness | Protocol & adapter contract fidelity |
| Relevance | Retrieval quality stays within SLO bounds |
| Performance | Latency & throughput targets maintained |
| Resilience | Graceful degradation on partial failures |
| Security | Isolation & redaction enforced |
| Regression | Prevent drift after refactors |

### 12.2 Test Matrix
| Test Type | Scope | Tooling | Frequency |
|----------|-------|--------|-----------|
| Unit | Pure functions (ranking, decay formula) | pytest + hypothesis | On change / CI |
| Adapter Contract | Each adapter vs harness | Async test suite | On new adapter / CI |
| Integration | Multi-tier end-to-end build_context | docker-compose ephemeral env | CI nightly |
| Load | Sustained QPS, spike tests | Locust / k6 | Pre-release & weekly |
| Relevance Benchmark | Golden dataset evaluation | Custom evaluator | Per release |
| Chaos | Induced adapter timeouts/failures | Fault injection layer | Weekly canary |
| Security | Redaction, namespace isolation | Static + runtime tests | CI + quarterly review |
| Migration | Schema version upgrade simulation | Migration harness | On version bump |

### 12.3 Golden Dataset Strategy
| Dataset | Content |
|---------|---------|
| `facts_v1.json` | 1K curated user profile facts with conflicts |
| `episodic_v1.jsonl` | 500 synthetic event timelines |
| `queries_v1.json` | 300 queries + expected ID sets (top-5) |
| `sessions_v1.jsonl` | 100 full sessions for consolidation validation |

### 12.4 Relevance Metrics
| Metric | Definition | Target |
|--------|-----------|--------|
| Recall@5 | Retrieved relevant / total relevant | ≥ 0.85 |
| MRR | Mean reciprocal rank | ≥ 0.75 |
| NDCG@10 | Discounted gain | ≥ 0.80 |
| Summary Fidelity Score | Human eval scale 1–5 | ≥ 4.0 |

### 12.5 Chaos Scenarios
| Scenario | Expected Behavior |
|----------|------------------|
| Vector backend 50% timeout | Lexical + graph fill; warning attached |
| Redis eviction spike | WM misses; degrade gracefully w/out fatal error |
| Embedding provider 429s | Backoff; fallback lexical-only retrieval |
| Graph returns inconsistent edge | Quarantine entity; log integrity error |

### 12.6 Quality Gates (CI)
| Gate | Tool | Threshold |
|------|------|-----------|
| Type Checking | mypy (strict) | 0 errors |
| Lint | ruff / flake8 | No critical violations |
| Tests | pytest | ≥ 90% critical path coverage |
| Bench Smoke | microbench threshold | No regression > 15% |
| Security Scan | bandit / secret scanner | No high severity |

### 12.7 Release Checklist
1. All adapter contract tests green
2. Relevance benchmark within ±2% of prior release
3. Latency percentile dashboards stable
4. No open HIGH severity security issues
5. Migration scripts (if any) tested on staging snapshot
6. Updated ADR if architectural change introduced

### 12.8 Open Issues
| Issue | Impact | Planned Action |
|-------|--------|---------------|
| Synthetic data realism | Benchmark representativeness | Collect anonymized opt-in telemetry for refinement |
| Human eval scalability | Manual bottleneck | Semi-automate via LLM rubric grading |
| Coverage metric gaming | False sense of safety | Focus on mutation testing Phase 2 |

---
<!-- Sections 13+ complete. -->
## 13. Extensibility & Plugin Architecture

### 13.1 Goals
| Goal | Description | Success Indicator |
|------|-------------|-------------------|
| Low-friction adapter authoring | Create new storage / embedding adapter quickly | < 2 hours dev time |
| Safe community contributions | Prevent quality & security regressions | Certification checklist enforced |
| Feature discovery | Dynamically adapt retrieval plan to capabilities | Capability flags consumed in 100% of plans |
| Backwards compatibility | Upgrades do not break existing adapters | SemVer contract adherence |

### 13.2 Plugin Categories
| Category | Examples | Notes |
|----------|----------|-------|
| Storage Tier Adapters | `smrti-redis`, `smrti-pinecone`, `smrti-qdrant` | Provide `TierStore` implementation |
| Embedding Providers | `smrti-openai-embed`, `smrti-hf-sentence` | Provide `EmbeddingProvider` |
| Graph Backends | `smrti-neo4j`, `smrti-memgraph` | Provide `GraphStore` |
| Lexical Index | `smrti-opensearch-bm25`, `smrti-lucene` | Provide `LexicalIndex` |
| Rerankers | `smrti-crossencoder-mini`, `smrti-colbert` | Expose `ReRanker` interface |
| Summarizers | `smrti-llm-gpt4`, `smrti-llm-mistral` | Provide summarization strategy |

### 13.3 Discovery Mechanism
1. **Entry Points (Python)**: `smrti.adapters` group exposes adapter classes.
2. Manual registration API: `register_adapter(name, factory, capabilities)`.
3. Lazy loading: Adapters are only imported when referenced in config (reduces cold start cost).

### 13.4 Adapter Manifest
```
AdapterManifest {
	name: str,
	version: str,
	type: Enum(storage|embedding|graph|lexical|reranker|summarizer),
	capabilities: StoreCapabilities | EmbeddingCapabilities,
	config_schema: dict,               // JSON schema for adapter config validation
	optional: bool,                    // If core features can work without this
	dependencies: list[str],           // Python package extras
	license: str
}
```

### 13.5 Capability Negotiation
Planner introspects all registered manifests and builds a **capability matrix**. Missing optional capabilities (e.g., `supports_graph_ops=false`) trigger weight redistribution (Section 7). 

### 13.6 Feature Flags
| Flag | Purpose | Default |
|------|---------|---------|
| `enable_graph_traversal` | Activate graph-based enrichment | Off if no graph adapter |
| `enable_rerank` | Allow cross-encoder passes | On (lightweight) |
| `enable_fact_extraction` | Run fact pipeline post-consolidation | On |
| `enable_conflict_resolution` | Activate semantic fact supersession | On |
| `enable_entity_resolution` | Merge entity aliases | On |
| `enable_adaptive_weights` | Runtime weight tuning in fusion | On |

Flags controlled via config or env vars (`SMRTI_FEATURE_*`).

### 13.7 Contribution Workflow
1. Fork repo & implement adapter in `providers/<category>/<name>`
2. Provide manifest + config schema.
3. Run `make adapter-cert` → executes contract & performance tests.
4. Submit PR with benchmark summary (latency, pass rates).
5. Maintainers review security (redaction, no secret logs) & license compatibility.
6. Merge & publish; update adapter matrix table in docs.

### 13.8 Versioning Policy
| Change Type | SemVer Impact |
|-------------|---------------|
| Add optional field / capability | MINOR |
| Add new adapter interface method (required) | MAJOR |
| Deprecate config key (with alternative) | MINOR (add warn) → MAJOR (removal) |
| Change default fusion weight | MINOR (document) |
| Alter record envelope structure | MAJOR |

### 13.9 Deprecation Flow
1. Introduce replacement + emit WARN log on old usage.
2. Provide automated migration script if applicable.
3. After ≥2 MINOR releases, remove with MAJOR bump.

### 13.10 Governance Considerations
| Aspect | Policy |
|--------|-------|
| Adapter Ownership | Maintainer or designated steward |
| Security Disclosure | Private email (`security@konf.dev`) |
| Release Cadence | Core every 4–6 weeks; adapters independent |
| Compatibility Matrix | Published table (core version ↔ adapter tested version) |

### 13.11 Open Issues
| Issue | Concern | Path |
|-------|--------|------|
| Standardizing summarizer output schema | Varies by LLM | Provide strict schema & validator |
| Capability explosion | Complexity | Group into capability tiers |

---
## 14. Packaging & Distribution

### 14.1 Project Layout (Conceptual)
```
smrti/
	core/              # context, retrieval, lifecycle, ranking
	adapters/          # built-in minimal adapters (in-memory, null)
	api/               # SmrtiClient & protocol exports
	telemetry/         # metrics + tracing utilities
	contrib/           # optional reference examples
	tests/
```

### 14.2 Install Profiles
| Extra | Includes | Use Case |
|-------|----------|---------|
| `smrti` (base) | Core only (no external deps beyond std + minimal) | Library embedding |
| `smrti[redis]` | redis-py | Working/STM production |
| `smrti[vector-basic]` | chromadb | Local dev vector store |
| `smrti[vector-enterprise]` | pinecone-client | Hosted vector SaaS |
| `smrti[graph]` | neo4j, networkx | Semantic facts graph |
| `smrti[rerank]` | sentence-transformers | Cross-encoder |
| `smrti[all]` | Union of above | Exploration |

### 14.3 Environment Variables (Prefix `SMRTI_`)
| Variable | Purpose | Example |
|----------|---------|---------|
| `SMRTI_LOG_LEVEL` | Logging verbosity | `info` |
| `SMRTI_FEATURE_ENABLE_RERANK` | Force enable/disable reranking | `true` |
| `SMRTI_CONTEXT_DEFAULT_BUDGET` | Default token budget | `8000` |
| `SMRTI_DECAY_HALF_LIFE_LTM_DAYS` | Override LTM decay | `45` |
| `SMRTI_TIER_WORKING_BACKEND` | Override working tier backend | `redis` |
| `SMRTI_EMBEDDING_DEFAULT_MODEL` | Default embedding model name | `minilm` |
| `SMRTI_GRAPH_BACKEND_URI` | Graph DB connection | `bolt://...` |
| `SMRTI_REDACT_PATTERNS` | Comma list of regex keys | `email,phone` |

### 14.4 Configuration Sources
Precedence already defined (Section 5.6). Provide CLI: `smrti config dump` for resolved snapshot & diff tool.

### 14.5 Distribution Strategy
| Channel | Content |
|---------|---------|
| PyPI | Core package & optional extras |
| Docker (dev kit) | Pre-bundled local stack (`redis + chroma + neo4j`) |
| Docs Site | API reference, adapter matrix, quickstarts |
| Example Repo | End-to-end notebooks & benchmark scripts |

### 14.6 Release Channels
| Channel | Tag Pattern | Usage |
|---------|-------------|-------|
| Stable | `vX.Y.Z` | Production consumption |
| Pre-release | `vX.Y.Z-rcN` | Final regression pass |
| Nightly (optional) | `vX.Y.Z.dev<date>` | Early adopter feedback |

### 14.7 Licensing & Compliance
Proposed: **Apache 2.0** (permissive, encourages ecosystem growth). Adapters may include differing compatible licenses (must declare).

### 14.8 Binary Artifacts (Deferred)
Potential optional Rust-accelerated embedding cache compiled wheels (Phase 3+).

### 14.9 Deprecation Tracking
Changelog sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Security`, `Performance`.

### 14.10 Open Issues
| Issue | Concern | Path |
|-------|--------|------|
| Extra explosion | Hard to communicate combos | Provide meta-extras (e.g., `prod-minimal`) |
| Multi-platform wheels | Build overhead | Defer until Rust components introduced |

---
## 15. Roadmap (6-Month Plan)

### 15.1 Phase Overview
| Phase | Weeks | Theme | Key Deliverables |
|-------|-------|-------|------------------|
| 0 | 1 | Foundations bootstrap | Repo + scaffolding + CI + base envelope models |
| 1 | 2–4 | Core Retrieval & WM/STM | Redis adapter, basic context builder, vector integration (chroma) |
| 2 | 5–8 | LTM + Hybrid Retrieval | Vector + lexical fusion, initial ranking, summarization pipeline |
| 3 | 9–12 | Episodic & Semantic | Event timelines, graph adapter optional, fact extraction v1 |
| 4 | 13–16 | Lifecycle Maturity | Decay scheduler, dedup, conflict resolution, provenance enhancements |
| 5 | 17–20 | Optimization & Observability | Re-ranker integration, adaptive weights, full metrics/tracing suite |
| 6 | 21–24 | Hardening & Ecosystem | Adapter certification harness, docs site, ADR finalization, pre-1.0 polish |

### 15.2 Milestones & Exit Criteria
| Milestone | Criteria |
|----------|----------|
| M1 (Week 4) | `build_context` returns WM+STM+LTM (vector) sections, tests ≥ 70% |
| M2 (Week 8) | Hybrid retrieval (lexical+vector) recall@5 ≥ 0.78 on golden set |
| M3 (Week 12) | Episodic queries & fact graph queries functional |
| M4 (Week 16) | Decay + consolidation + dedup produce < 20% orphan ratio |
| M5 (Week 20) | Rerank improves NDCG@10 by ≥ 8% vs baseline |
| M6 (Week 24) | 1.0-RC: All critical SLOs met; ≥ 5 official adapters released |

### 15.3 Risk Checkpoints
| Phase | Risk Focus | Mitigation Review |
|-------|-----------|-------------------|
| 2 | Retrieval quality lag | Adjust hybrid weights earlier |
| 3 | Graph complexity slowdown | Make semantic optional & lazy |
| 4 | Decay over-pruning | Tune half-life using simulation |
| 5 | Latency regression w/ rerank | Introduce dynamic rerank gating |

### 15.4 Resource Estimate (Indicative)
| Role | FTE | Focus |
|------|-----|-------|
| Core Engineer | 2 | Retrieval, lifecycle, context builder |
| Infra/Perf | 1 | Metrics, scaling, caching, benchmarking |
| ML / Relevance | 1 (shared) | Fact extraction, ranking tuning |
| Tech Writer | 0.5 | Docs, adapter guides |

### 15.5 Stretch Objectives (If Ahead)
| Objective | Benefit |
|----------|---------|
| Online learning for weight tuning | Personalization boost |
| Light affective memory facet | More empathetic agent responses |
| SaaS reference deployment chart | Fast adoption |

### 15.6 Deferral List (Post 1.0)
| Item | Reason |
|------|--------|
| Multimodal embeddings | Scope containment |
| Procedural memory tier | Requires agent action learning integration |
| Federated memory sync | Cross-region complexity |

### 15.7 Communication Cadence
| Artifact | Frequency |
|---------|-----------|
| Standup (async) | Daily |
| Milestone retro | End of phase |
| Public changelog | Per release |
| ADR updates | As decisions finalize |

### 15.8 KPIs by Phase
| Phase | KPI Focus |
|-------|-----------|
| 1 | Latency baseline established |
| 2 | Recall@5 uplift |
| 3 | Episodic query success rate |
| 4 | Orphan reduction |
| 5 | Token savings % |
| 6 | Adapter ecosystem size |

### 15.9 Open Issues
| Issue | Impact | Consideration |
|-------|--------|---------------|
| Roadmap dependency on external adapter authors | Slippage risk | Provide internal fallback adapters |
| Ranking quality plateau | Stagnation | Introduce learning-to-rank later |

---
## 16. Future-Proofing & Evolution

### 16.1 Multimodal Readiness Recap
Current abstractions already include `content_type` & flexible payload; enabling future adapters for images/audio/video requires adding specialized embedding providers and retrieval scoring features (e.g., CLIP similarity). No schema migration expected.

### 16.2 Potential Evolution Tracks
| Track | Description | Trigger |
|-------|-------------|--------|
| Affective Signals | Track sentiment & emotional intensity as memory facet | Customer need for empathetic agents |
| Procedural Memory | Store learned tool invocation patterns | Repeated workflow detection signal |
| Online Learning Weights | Incrementally adapt fusion weights per tenant | Sufficient feedback telemetry |
| Rust Acceleration | Replace hot embedding / ranking loops | Profiling identifies Python overhead > 15% |
| Federated Memory | Multi-region synchronization & locality-aware retrieval | Global latency constraints |
| Privacy Enhancements | Differential privacy for aggregated analytics | Enterprise compliance demand |

### 16.3 Upgrade Strategy
| Change Type | Migration Pattern |
|------------|------------------|
| Envelope field addition | Backward-compatible; doc update |
| Field removal | Mark deprecated → soft ignore → major removal |
| Tier addition (new) | Treat as optional adapter; does not break existing plans |
| Embedding model shift | Store `embedding_model_version`; re-encode lazily |
| Graph schema extension | Versioned predicate namespaces |

### 16.4 ADR (Architectural Decision Record) Index (Initial Set)
| ADR # | Title | Status |
|-------|-------|--------|
| 001 | Adopt Five-Tier Memory Taxonomy | Accepted |
| 002 | Hybrid Retrieval (Lexical + Vector + Graph + Temporal) | Accepted |
| 003 | Protocol-Based Adapter Architecture | Accepted |
| 004 | Provenance Envelope for All Records | Accepted |
| 005 | Decay & Consolidation Lifecycle Jobs | Accepted |
| 006 | Deferred Multimodal Implementation (Design Hooks Only) | Accepted |
| 007 | Optional Graph Tier Activation | Accepted |
| 008 | Capability Flags over Hard Type Hierarchy | Accepted |
| 009 | Summarization Hybrid Strategy (Extractive→LLM) | Draft |
| 010 | Cross-Encoder Re-ranking Optional Path | Draft |

### 16.5 SaaS Offering Considerations (Exploratory)
| Aspect | SaaS Mode Option |
|--------|------------------|
| Multi-Tenancy Isolation | Per-tenant logical namespace + row-level encryption |
| Billing Metrics | Count context builds, embedding tokens, storage consumption |
| Tiered Plans | Basic (WM+LTM), Pro (+Episodic), Enterprise (+Semantic graph) |
| Data Residency | Region pinning at ingest | 

### 16.6 Sunset & Deprecation Policy
| Stage | Description | Duration |
|-------|-------------|----------|
| Announce | Mark feature deprecated in changelog & warn logs | 1 release |
| Soft Remove | Default disabled; can re-enable via flag | 1–2 releases |
| Hard Remove | Code removed; migration tool archived | Major release |

### 16.7 Open Questions
| Question | Impact | Path |
|----------|--------|------|
| Introduce plugin marketplace? | Ecosystem growth vs moderation overhead | Evaluate post 1.0 adoption |
| LLM-based adaptive planning? | More relevance vs latency | Experiment sandbox |
| Data residency enforcement granularity | Compliance complexity | Start coarse (region-level) |

---
<!-- Appendices complete. -->
## Appendix A: Core Schemas (Conceptual / Pydantic Sketches)

```python
class RecordEnvelope(BaseModel):
		id: UUID
		tenant: str
		namespace: str
		user_id: str | None
		tier: Literal["working","short_term","long_term","episodic","semantic"]
		content_type: Literal["TEXT","FACT","EVENT","SUMMARY","EMBED_REF","MULTIMODAL_PLACEHOLDER"]
		payload: dict | str
		embedding: list[float] | None = None
		semantic_hash: str | None = None
		created_at: datetime
		updated_at: datetime
		relevance_score: float = 1.0
		importance_score: float = 0.0
		access_count: int = 0
		last_accessed_at: datetime | None = None
		decay_params: dict[str, Any] | None = None
		lineage: list[str] = []
		provenance: dict[str, Any] = {}
		integrity: dict[str, Any] = {}
		metadata: dict[str, Any] = {}
		archived: bool = False

class MemoryQuery(BaseModel):
		user_id: str
		query: str
		token_budget: int = 8000
		include_archived: bool = False
		disable_sections: list[str] = []
		min_relevance: float = 0.1
		force_sections: list[str] = []

class ProvenanceRecord(BaseModel):
		record_id: str
		tier: str
		source_type: str
		original_tokens: int
		current_tokens: int
		relevance_score: float
		selection_reason: str
		transformations: list[dict[str, Any]]

class ContextSection(BaseModel):
		name: str
		items: list[dict[str, Any]]

class SmrtiContext(BaseModel):
		user_id: str
		query: str
		generated_at: datetime
		token_budget: int
		estimated_tokens: int
		sections: list[ContextSection]
		provenance: list[ProvenanceRecord]
		stats: dict[str, Any]

class TierConfig(BaseModel):
		backend: str
		ttl_seconds: int | None = None
		half_life_days: float | None = None
		archive_threshold: float | None = None
		compress_threshold: float | None = None

class Settings(BaseModel):
		tiers: dict[str, TierConfig]
		fusion_weights: dict[str, float]
		feature_flags: dict[str, bool]
		default_token_budget: int = 8000
```

## Appendix B: Adapter Skeletons

```python
class RedisWorkingStore:
		def __init__(self, client, ttl=300):
				self.client = client; self.ttl = ttl
		async def write_batch(self, records):
				pipe = self.client.pipeline()
				for r in records:
						key = f"wm:{r.tenant}:{r.namespace}:{r.id}"
						pipe.set(key, json.dumps(r.payload), ex=self.ttl)
				await pipe.execute()
		async def fetch(self, record_id): ...
		async def search(self, query): return []  # Not applicable

class ChromaLongTermStore:
		def __init__(self, chroma_client, collection_name):
				self.collection = chroma_client.get_or_create_collection(collection_name)
		async def write_batch(self, records):
				ids = [r.id for r in records]
				embeddings = [r.embedding for r in records]
				metadatas = [r.metadata | {"tier": r.tier} for r in records]
				docs = [r.payload if isinstance(r.payload, str) else json.dumps(r.payload) for r in records]
				self.collection.add(ids=ids, embeddings=embeddings, documents=docs, metadatas=metadatas)
		async def approximate_search(self, query):
				return self.collection.query(query_embeddings=[query.embedding], n_results=20)
```

## Appendix C: Example Integration Flow

```python
from smrti import SmrtiClient, Settings

settings = Settings(
		tiers={
			"working": {"backend": "redis", "ttl_seconds": 300},
			"short_term": {"backend": "redis", "ttl_seconds": 86400},
			"long_term": {"backend": "chroma", "half_life_days": 60},
		},
		fusion_weights={"vector": 0.5, "lexical": 0.3, "recency": 0.2},
		feature_flags={"enable_rerank": True}
)

client = SmrtiClient(settings=settings, adapters=...)  # inject constructed adapter instances

await client.append_conversation_turn({
	"user_id": "u123", "text": "I just moved to Seattle.", "tenant": "acme", "namespace": "support"})

await client.store_fact({
	"entity_id": "user:u123", "predicate": "location", "object": "Seattle", "confidence": 0.95})

ctx = await client.build_context(user_id="u123", query="What's the user's current location?", token_budget=2000)
print(ctx.sections[1].items)
```

## Appendix D: ADR Summaries (Full Text Abridged)

**ADR 001: Adopt Five-Tier Memory Taxonomy**  
Status: Accepted  
Context: Flat vector or simple short/long dichotomies either over-retain ephemeral noise or under-represent temporal structure.  
Decision: Implement WM, STM, LTM, Episodic, Semantic tiers.  
Consequences: Slightly higher onboarding complexity; higher retrieval precision & cost control.

**ADR 002: Hybrid Retrieval (Lexical + Vector + Graph + Temporal)**  
Status: Accepted  
Decision: Combine normalized modality scores for final ranking.  
Rationale: Improves recall & precision vs single modality; enables graceful degradation.  
Trade-offs: Additional engineering complexity; weight tuning required.

**ADR 003: Protocol-Based Adapter Architecture**  
Decision: Define minimal async protocols for TierStore, EmbeddingProvider, GraphStore, LexicalIndex.  
Consequence: Integration overhead for new backends; vendor flexibility gained.

**ADR 004: Provenance Envelope for All Records**  
Decision: Uniform metadata to support explainability & lineage preservation.  
Consequence: Slight storage overhead; enables audit & summarization re-runs.

**ADR 005: Decay & Consolidation Lifecycle Jobs**  
Decision: Scheduled jobs enforce memory health (summarization, archiving, dedup).  
Consequence: Operational complexity (monitoring), prevents entropy & cost blow-up.

**ADR 006: Deferred Multimodal Implementation (Hooks Only)**  
Decision: Introduce placeholder content types + embedding provider extensibility; postpone actual multimodal exec.  
Consequence: Future features unblock without premature scope expansion.

**ADR 007: Optional Graph Tier Activation**  
Decision: Graph only initialized if configured; retrieval adapts weights accordingly.  
Consequence: Simpler adoption path; potential missed graph benefits if not enabled.

**ADR 008: Capability Flags over Hard Type Hierarchy**  
Decision: Planner uses declared capabilities instead of rigid subclass structures.  
Consequence: More dynamic planning; risk of inconsistent adapter declarations (mitigated by certification tests).

**ADR 009: Summarization Hybrid Strategy (Extractive→LLM)**  
Status: Draft  
Intent: Control LLM costs while increasing coherence.

**ADR 010: Cross-Encoder Re-ranking Optional Path**  
Status: Draft  
Intent: Provide accuracy uplift only when needed; gated by latency budget.

## Appendix E: Benchmark Blueprint

| Benchmark | Script | KPI |
|-----------|--------|-----|
| Latency Baseline | `bench_latency.py` | p50/p95 per stage |
| Retrieval Quality | `bench_relevance.py` | Recall@5, NDCG@10 |
| Consolidation Efficiency | `bench_consolidation.py` | Token reduction % |
| Decay Simulation | `bench_decay.py` | Orphan ratio after 30d |
| Rerank Impact | `bench_rerank.py` | NDCG uplift |

Execution Environment Recommendations: pinned dataset snapshot, fixed embedding model, deterministic seeds, isolated network.

## Appendix F: Migration & Versioning Reference

| Scenario | Approach |
|----------|----------|
| Add new optional tier | Provide config stub; planner ignores if absent |
| Change default decay half-life | Mark in release notes; allow env override |
| Introduce new record field | Add with default; bump MINOR |
| Remove obsolete field | Deprecate → warn 2 releases → remove MAJOR |
| Embedding dimensionality change | Store model_version; re-embed lazily on retrieval cache miss |

## Appendix G: Glossary
| Term | Definition |
|------|------------|
| Candidate Set | Raw unfiltered retrieval results per modality |
| Fusion | Weighted combination of modality scores |
| Lineage | List of source record IDs a derived record depends on |
| Orphan Ratio | % of low-relevance, low-access records in tier |
| Promotion | Movement of information to more durable tier via summarization |
| Reduction Cycle | Iteration applying a token reduction strategy |

## Appendix H: Example Config (YAML)
```yaml
tiers:
	working:
		backend: redis
		ttl_seconds: 300
	short_term:
		backend: redis
		ttl_seconds: 86400
	long_term:
		backend: chroma
		half_life_days: 60
	episodic:
		backend: postgres
	semantic:
		backend: neo4j

fusion_weights:
	vector: 0.45
	lexical: 0.20
	graph: 0.15
	temporal: 0.10
	recency: 0.10

feature_flags:
	enable_rerank: true
	enable_fact_extraction: true
	enable_entity_resolution: true
	enable_graph_traversal: false

context:
	default_budget: 8000
	allocation:
		working: 0.10
		semantic: 0.25
		episodic: 0.25
		summaries: 0.20
		patterns: 0.10
		slack: 0.10
```

## Appendix I: Minimal Quickstart Checklist
1. Install: `pip install smrti[redis,vector-basic]`
2. Run dev stack (optional): `docker compose up -d redis chroma`
3. Configure YAML (Appendix H) → `smrti config validate config.yaml`
4. Initialize client → ingest sample events → call `build_context`
5. Inspect metrics endpoint & enable tracing exporter
6. Evaluate recall with golden dataset baseline
7. Tune fusion weights if recall < target

---
## Appendix J: Complete Protocol Specifications (LLM Implementation Reference)

### J.1 Core Data Models (Full Pydantic Definitions)

```python
"""
smrti/schemas/models.py - Core data models with validation
"""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator, model_validator

# Tier enumeration
TierType = Literal["working", "short_term", "long_term", "episodic", "semantic"]
ContentType = Literal["TEXT", "FACT", "EVENT", "SUMMARY", "EMBED_REF", "MULTIMODAL_PLACEHOLDER"]

class RecordEnvelope(BaseModel):
    """Universal memory record wrapper. All tiers use this structure."""
    id: UUID = Field(default_factory=uuid4, description="Unique record identifier")
    tenant: str = Field(..., min_length=1, max_length=128, description="Tenant namespace for isolation")
    namespace: str = Field(..., min_length=1, max_length=128, description="Sub-namespace (e.g., 'support', 'sales')")
    user_id: str | None = Field(None, max_length=256, description="User principal; None for system/global memory")
    tier: TierType = Field(..., description="Memory tier classification")
    content_type: ContentType = Field(..., description="Payload semantic type")
    payload: dict[str, Any] | str = Field(..., description="Actual content (text string or structured dict)")
    embedding: list[float] | None = Field(None, description="Dense vector representation (if applicable)")
    semantic_hash: str | None = Field(None, max_length=64, description="LSH/SimHash for deduplication")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    relevance_score: float = Field(1.0, ge=0.0, le=1.0, description="Dynamic decay-adjusted relevance")
    importance_score: float = Field(0.0, ge=0.0, le=1.0, description="Static priority weight")
    access_count: int = Field(0, ge=0, description="Retrieval frequency (reinforcement signal)")
    last_accessed_at: datetime | None = None
    decay_params: dict[str, Any] = Field(default_factory=dict, description="Tier-specific decay config override")
    lineage: list[str] = Field(default_factory=list, description="Parent record IDs (for summaries/consolidations)")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Origin metadata (agent, tool, etc.)")
    integrity: dict[str, Any] = Field(default_factory=dict, description="Checksums, version, signatures")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary key-value extensions")
    archived: bool = Field(False, description="Flagged for cold storage")

    @field_validator("tenant", "namespace")
    @classmethod
    def validate_namespace_chars(cls, v: str) -> str:
        """Enforce safe namespace characters (alphanumeric + underscore + hyphen)."""
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(f"Invalid namespace format: {v}")
        return v

    @model_validator(mode='after')
    def validate_embedding_dimensions(self):
        """Ensure embedding vector has consistent dimensions if present."""
        if self.embedding and len(self.embedding) not in [384, 512, 768, 1024, 1536, 3072]:
            raise ValueError(f"Unsupported embedding dimension: {len(self.embedding)}")
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "id": "01234567-89ab-cdef-0123-456789abcdef",
                "tenant": "acme_corp",
                "namespace": "customer_support",
                "user_id": "user_12345",
                "tier": "long_term",
                "content_type": "SUMMARY",
                "payload": {"text": "User prefers email notifications.", "confidence": 0.92},
                "embedding": [0.1, 0.2, 0.3],  # truncated for example
                "relevance_score": 0.87,
                "created_at": "2025-10-01T10:00:00Z"
            }
        }


class MemoryQuery(BaseModel):
    """Request specification for context retrieval."""
    user_id: str = Field(..., min_length=1, max_length=256)
    query: str = Field(..., min_length=1, max_length=8000, description="Natural language or structured query")
    token_budget: int = Field(8000, ge=100, le=32000, description="Maximum tokens in assembled context")
    include_archived: bool = Field(False, description="Whether to search cold-stored records")
    disable_sections: list[str] = Field(default_factory=list, description="Section names to skip (e.g., ['patterns'])")
    min_relevance: float = Field(0.1, ge=0.0, le=1.0, description="Minimum relevance threshold")
    force_sections: list[str] = Field(default_factory=list, description="Sections to include regardless of budget")
    tenant: str = Field(..., min_length=1, max_length=128)
    namespace: str = Field(..., min_length=1, max_length=128)
    retrieval_options: dict[str, Any] = Field(default_factory=dict, description="Advanced tuning (e.g., rerank model)")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_12345",
                "query": "What are the user's notification preferences?",
                "token_budget": 4000,
                "tenant": "acme_corp",
                "namespace": "customer_support",
                "min_relevance": 0.2
            }
        }


class ProvenanceRecord(BaseModel):
    """Provenance metadata for each context fragment."""
    record_id: str = Field(..., description="Source RecordEnvelope ID")
    tier: TierType
    source_type: ContentType
    original_tokens: int = Field(ge=0)
    current_tokens: int = Field(ge=0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    selection_reason: str = Field(..., description="Why included: top_k|explicit|high_importance|boosted")
    transformations: list[dict[str, Any]] = Field(default_factory=list, description="Reduction/summarization steps")


class ContextSection(BaseModel):
    """Logical section within assembled context."""
    name: str = Field(..., description="Section identifier (working|semantic_facts|episodic_recent|...)")
    items: list[dict[str, Any]] = Field(default_factory=list, description="Ordered memory items")
    estimated_tokens: int = Field(0, ge=0)


class SmrtiContext(BaseModel):
    """Final assembled context returned to consumer."""
    user_id: str
    query: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    token_budget: int
    estimated_tokens: int = Field(ge=0)
    sections: list[ContextSection]
    provenance: list[ProvenanceRecord]
    stats: dict[str, Any] = Field(default_factory=dict, description="Assembly metrics (reductions, discards, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_12345",
                "query": "notification preferences",
                "generated_at": "2025-10-03T14:22:00Z",
                "token_budget": 4000,
                "estimated_tokens": 3200,
                "sections": [
                    {"name": "working", "items": [], "estimated_tokens": 0},
                    {"name": "semantic_facts", "items": [{"text": "Prefers email"}], "estimated_tokens": 50}
                ],
                "provenance": [],
                "stats": {"reductions_applied": 1, "discarded_items": 3}
            }
        }


class EventRecord(BaseModel):
    """Episodic event ingestion payload."""
    tenant: str
    namespace: str
    user_id: str | None
    event_type: str = Field(..., max_length=128, description="Event classification (e.g., 'user_login', 'error')")
    event_data: dict[str, Any] = Field(..., description="Event-specific payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactRecord(BaseModel):
    """Semantic fact ingestion payload."""
    tenant: str
    namespace: str
    entity_id: str = Field(..., min_length=1, max_length=256, description="Entity identifier")
    predicate: str = Field(..., min_length=1, max_length=128, description="Relationship/attribute type")
    object: str | int | float | bool = Field(..., description="Fact value")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    """Dialog turn ingestion for STM."""
    tenant: str
    namespace: str
    user_id: str
    session_id: str = Field(..., description="Conversation session identifier")
    role: Literal["user", "assistant", "system", "tool"] = Field(...)
    content: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# Configuration models
class TierConfig(BaseModel):
    """Per-tier storage and lifecycle configuration."""
    backend: str = Field(..., description="Adapter name (redis|chroma|postgres|neo4j|...)")
    ttl_seconds: int | None = Field(None, ge=60, description="Time-to-live for ephemeral tiers")
    half_life_days: float | None = Field(None, ge=0.1, description="Decay half-life duration")
    archive_threshold: float | None = Field(None, ge=0.0, le=1.0, description="Relevance below which to archive")
    compress_threshold: float | None = Field(None, ge=0.0, le=1.0, description="Threshold to trigger compression")
    adapter_config: dict[str, Any] = Field(default_factory=dict, description="Backend-specific settings (connection URI, etc.)")


class Settings(BaseModel):
    """Global Smrti configuration."""
    tiers: dict[TierType, TierConfig] = Field(..., description="Configuration per memory tier")
    fusion_weights: dict[str, float] = Field(
        default_factory=lambda: {"vector": 0.45, "lexical": 0.20, "graph": 0.15, "temporal": 0.10, "recency": 0.10}
    )
    feature_flags: dict[str, bool] = Field(
        default_factory=lambda: {
            "enable_rerank": True,
            "enable_graph_traversal": False,
            "enable_fact_extraction": True,
            "enable_entity_resolution": True
        }
    )
    default_token_budget: int = Field(8000, ge=100, le=32000)
    context_allocation: dict[str, float] = Field(
        default_factory=lambda: {
            "working": 0.10,
            "semantic": 0.25,
            "episodic": 0.25,
            "summaries": 0.20,
            "patterns": 0.10,
            "slack": 0.10
        }
    )
    embedding_model: str = Field("sentence-transformers/all-MiniLM-L6-v2", description="Default embedding model")
    log_level: Literal["DEBUG", "INFO", "WARN", "ERROR"] = Field("INFO")

    @model_validator(mode='after')
    def validate_allocation_sums_to_one(self):
        """Ensure context allocation fractions sum to ~1.0."""
        total = sum(self.context_allocation.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(f"context_allocation must sum to 1.0 (got {total})")
        return self
```

### J.2 Complete Protocol Interfaces with Docstrings

```python
"""
smrti/api/protocols.py - Protocol definitions for adapters
"""
from typing import Protocol, runtime_checkable
from smrti.schemas.models import RecordEnvelope, TierType, EventRecord, FactRecord, ConversationTurn, SmrtiContext, MemoryQuery

@runtime_checkable
class SmrtiProvider(Protocol):
    """High-level public interface for Smrti memory system."""
    
    async def build_context(
        self,
        *,
        user_id: str,
        query: str,
        token_budget: int = 8000,
        options: dict[str, Any] | None = None,
    ) -> SmrtiContext:
        """
        Assemble optimal context for LLM prompt under token budget.
        
        Args:
            user_id: Principal identifier
            query: Natural language retrieval intent
            token_budget: Maximum tokens in final context
            options: Override config (disable_sections, min_relevance, etc.)
            
        Returns:
            SmrtiContext with sections, provenance, and stats
            
        Raises:
            ValueError: If user_id or query invalid
            PartialDegradationError: If some tiers failed but partial result available
        """
        ...
    
    async def record_event(self, event: EventRecord) -> None:
        """
        Ingest episodic event into memory system.
        
        Args:
            event: Structured event payload
            
        Raises:
            ValidationError: If event data malformed
        """
        ...
    
    async def store_fact(self, fact: FactRecord) -> None:
        """
        Store structured semantic fact.
        
        Args:
            fact: Entity-predicate-object triple with confidence
            
        Raises:
            ValidationError: If fact data invalid
        """
        ...
    
    async def append_conversation_turn(self, turn: ConversationTurn) -> None:
        """
        Add dialog turn to short-term memory.
        
        Args:
            turn: Conversation message with role and session context
        """
        ...
    
    async def flush(self) -> None:
        """Force flush of all pending batch writes across tiers."""
        ...


@runtime_checkable
class TierStore(Protocol):
    """Storage adapter interface for a single memory tier."""
    
    async def write_batch(self, records: list[RecordEnvelope]) -> dict[str, Any]:
        """
        Persist batch of records atomically (or mark failures).
        
        Args:
            records: List of memory envelopes to write
            
        Returns:
            dict with {"success_count": int, "failed_ids": list[str], "errors": list[str]}
            
        Raises:
            CapacityExceededError: If batch size > backend limit
        """
        ...
    
    async def fetch(self, record_id: str) -> RecordEnvelope | None:
        """
        Retrieve single record by ID.
        
        Args:
            record_id: UUID string
            
        Returns:
            RecordEnvelope or None if not found
        """
        ...
    
    async def search(self, query: dict[str, Any]) -> list[RecordEnvelope]:
        """
        Execute metadata/lexical search.
        
        Args:
            query: dict with filters (user_id, date_range, content_type, etc.)
            
        Returns:
            List of matching records (may be empty)
        """
        ...
    
    async def approximate_search(self, query_embedding: list[float], top_k: int = 20) -> list[tuple[RecordEnvelope, float]]:
        """
        Vector similarity search (optional; raise NotImplementedError if unsupported).
        
        Args:
            query_embedding: Dense vector
            top_k: Number of results
            
        Returns:
            List of (record, cosine_score) tuples sorted descending by score
        """
        ...
    
    async def stats(self) -> dict[str, Any]:
        """
        Return tier statistics.
        
        Returns:
            dict with {"record_count": int, "storage_bytes": int, "avg_latency_ms": float}
        """
        ...
    
    async def initialize(self) -> None:
        """Establish connections, create indexes, warm caches."""
        ...
    
    async def health(self) -> dict[str, Any]:
        """
        Readiness check.
        
        Returns:
            dict with {"status": "healthy"|"degraded"|"down", "latency_ms": float}
        """
        ...
    
    async def close(self) -> None:
        """Gracefully shut down connections and flush buffers."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Embedding model adapter."""
    
    async def embed_texts(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: Input strings
            model: Optional model override (uses default if None)
            
        Returns:
            List of dense vectors (same length as texts)
            
        Raises:
            EmbeddingError: If model call fails
        """
        ...
    
    async def embed_query(self, text: str, *, model: str | None = None) -> list[float]:
        """
        Generate single query embedding (may apply query-specific prompt).
        
        Args:
            text: Query string
            model: Optional override
            
        Returns:
            Dense vector
        """
        ...
    
    def metadata(self) -> dict[str, Any]:
        """
        Return model metadata.
        
        Returns:
            dict with {"model_name": str, "dimensions": int, "max_tokens": int}
        """
        ...


@runtime_checkable
class GraphStore(Protocol):
    """Graph database adapter for semantic facts."""
    
    async def upsert_entities(self, entities: list[dict[str, Any]]) -> None:
        """
        Create or update entity nodes.
        
        Args:
            entities: List of dicts with {"id": str, "type": str, "properties": dict}
        """
        ...
    
    async def upsert_relations(self, relations: list[dict[str, Any]]) -> None:
        """
        Create or update edges.
        
        Args:
            relations: List of dicts with {"from_id": str, "to_id": str, "type": str, "properties": dict}
        """
        ...
    
    async def traverse(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Execute graph traversal query.
        
        Args:
            request: dict with {"start_id": str, "max_hops": int, "edge_types": list[str]}
            
        Returns:
            dict with {"nodes": list, "edges": list, "paths": list}
        """
        ...


@runtime_checkable
class LexicalIndex(Protocol):
    """BM25/keyword search adapter."""
    
    async def index_documents(self, docs: list[dict[str, Any]]) -> None:
        """
        Add documents to lexical index.
        
        Args:
            docs: List of dicts with {"id": str, "text": str, "metadata": dict}
        """
        ...
    
    async def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        """
        Execute keyword search.
        
        Args:
            query: Search string
            top_k: Number of results
            
        Returns:
            List of dicts with {"id": str, "score": float, "text": str}
        """
        ...
```

### J.3 Exception Hierarchy

```python
"""
smrti/core/exceptions.py - Custom exception types
"""

class SmrtiError(Exception):
    """Base exception for all Smrti errors."""
    pass


class ValidationError(SmrtiError):
    """Input data failed validation."""
    pass


class PartialDegradationError(SmrtiError):
    """Some tiers failed but partial result available."""
    def __init__(self, message: str, partial_context: SmrtiContext, failed_tiers: list[str]):
        super().__init__(message)
        self.partial_context = partial_context
        self.failed_tiers = failed_tiers


class RetryableError(SmrtiError):
    """Transient failure; safe to retry."""
    pass


class CapacityExceededError(SmrtiError):
    """Batch size or rate limit exceeded."""
    pass


class IntegrityError(SmrtiError):
    """Data corruption or lineage inconsistency detected."""
    pass


class EmbeddingError(SmrtiError):
    """Embedding provider failure."""
    pass


class AdapterError(SmrtiError):
    """Generic adapter operational failure."""
    pass
```

### J.4 Implementation Pseudocode for Core Flows

#### J.4.1 Context Assembly Flow

```python
"""
smrti/core/context.py - Context builder implementation sketch
"""
from smrti.schemas.models import MemoryQuery, SmrtiContext, RecordEnvelope
from smrti.core.retrieval import RetrievalPlanner
from smrti.core.ranking import FusionEngine
from smrti.core.budget import TokenBudget

class ContextBuilder:
    def __init__(self, settings, adapters, telemetry):
        self.settings = settings
        self.adapters = adapters
        self.telemetry = telemetry
        self.planner = RetrievalPlanner(settings, adapters)
        self.fusion = FusionEngine(settings)
        self.budget = TokenBudget(settings)
    
    async def build_context(self, query: MemoryQuery) -> SmrtiContext:
        """Main assembly orchestration."""
        with self.telemetry.span("smrti.build_context"):
            # Step 1: Plan subqueries
            plan = await self.planner.create_plan(query)
            
            # Step 2: Execute parallel retrieval
            raw_candidates = await self._execute_parallel(plan)
            
            # Step 3: Fuse & rank
            ranked = self.fusion.rank(raw_candidates, query.query)
            
            # Step 4: Bucket by section
            sections = self._bucket_by_section(ranked)
            
            # Step 5: Apply budget & reduction
            final_sections = await self.budget.allocate_and_reduce(
                sections, query.token_budget, query
            )
            
            # Step 6: Attach provenance
            provenance = self._build_provenance(final_sections)
            
            # Step 7: Assemble result
            return SmrtiContext(
                user_id=query.user_id,
                query=query.query,
                token_budget=query.token_budget,
                estimated_tokens=self.budget.estimate_tokens(final_sections),
                sections=final_sections,
                provenance=provenance,
                stats={"reductions_applied": self.budget.reduction_count}
            )
    
    async def _execute_parallel(self, plan):
        """Execute all subqueries concurrently."""
        import asyncio
        tasks = [self._execute_subquery(sq) for sq in plan.subqueries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # Handle exceptions: log degradation, continue with partial
        return [r for r in results if not isinstance(r, Exception)]
    
    def _bucket_by_section(self, ranked: list[RecordEnvelope]) -> list[ContextSection]:
        """Group records into logical sections by tier/content_type."""
        from collections import defaultdict
        buckets = defaultdict(list)
        for record in ranked:
            section_name = self._determine_section(record)
            buckets[section_name].append(record)
        return [ContextSection(name=k, items=v) for k, v in buckets.items()]
    
    def _determine_section(self, record: RecordEnvelope) -> str:
        """Map record to section name."""
        if record.tier == "working":
            return "working"
        elif record.content_type == "FACT":
            return "semantic_facts"
        elif record.tier == "episodic":
            return "episodic_recent"
        elif record.content_type == "SUMMARY":
            return "summaries"
        else:
            return "other"
```

#### J.4.2 Write Path (Ingestion Flow)

```python
"""
smrti/core/ingestion.py - Write path orchestration
"""
from smrti.schemas.models import EventRecord, FactRecord, ConversationTurn, RecordEnvelope
from smrti.adapters.embedding import EmbeddingProvider
from smrti.core.dedup import DeduplicationService

class IngestionPipeline:
    def __init__(self, tier_stores, embedding_provider, dedup_service):
        self.tier_stores = tier_stores
        self.embedding = embedding_provider
        self.dedup = dedup_service
        self.write_buffer = {}  # tier -> list[RecordEnvelope]
    
    async def record_event(self, event: EventRecord) -> None:
        """Episodic event ingestion."""
        # 1. Convert to RecordEnvelope
        envelope = self._event_to_envelope(event)
        
        # 2. Optional embedding
        if self.settings.should_embed_events:
            text = self._extract_text(event.event_data)
            envelope.embedding = await self.embedding.embed_texts([text])[0]
        
        # 3. Compute semantic hash for dedup
        envelope.semantic_hash = self.dedup.compute_hash(envelope)
        
        # 4. Dedup check
        if await self.dedup.is_duplicate(envelope):
            # Merge or skip
            await self.dedup.merge_duplicate(envelope)
            return
        
        # 5. Buffer write
        self._buffer_write("episodic", envelope)
        
        # 6. Trigger flush if buffer full
        if len(self.write_buffer["episodic"]) >= self.settings.batch_size:
            await self.flush_tier("episodic")
    
    async def store_fact(self, fact: FactRecord) -> None:
        """Semantic fact ingestion."""
        envelope = self._fact_to_envelope(fact)
        
        # Check for conflict (same entity+predicate)
        existing = await self._find_conflicting_fact(fact)
        if existing:
            await self._resolve_conflict(existing, envelope)
        else:
            self._buffer_write("semantic", envelope)
    
    def _buffer_write(self, tier: str, envelope: RecordEnvelope):
        """Add to batch buffer."""
        if tier not in self.write_buffer:
            self.write_buffer[tier] = []
        self.write_buffer[tier].append(envelope)
    
    async def flush_tier(self, tier: str) -> None:
        """Flush buffered writes for a tier."""
        if tier not in self.write_buffer or not self.write_buffer[tier]:
            return
        
        records = self.write_buffer[tier]
        store = self.tier_stores[tier]
        
        result = await store.write_batch(records)
        
        if result["failed_ids"]:
            # Log failures, optionally retry
            self.telemetry.counter("write_failures", len(result["failed_ids"]))
        
        self.write_buffer[tier] = []
```

#### J.4.3 Consolidation Job

```python
"""
smrti/core/lifecycle.py - Consolidation pipeline
"""
import asyncio
from smrti.core.summarization import Summarizer

class ConsolidationJob:
    def __init__(self, stm_store, ltm_store, summarizer: Summarizer):
        self.stm_store = stm_store
        self.ltm_store = ltm_store
        self.summarizer = summarizer
    
    async def run_consolidation(self, session_id: str) -> None:
        """Consolidate STM session into LTM summary."""
        # 1. Fetch all STM messages for session
        messages = await self.stm_store.search({"session_id": session_id})
        
        if not messages:
            return
        
        # 2. Cluster by topic
        clusters = self._cluster_by_topic(messages)
        
        # 3. Summarize each cluster
        summaries = []
        for cluster in clusters:
            summary_text = await self.summarizer.summarize(cluster)
            summary_envelope = self._create_summary_envelope(
                summary_text, lineage=[m.id for m in cluster]
            )
            summaries.append(summary_envelope)
        
        # 4. Write summaries to LTM
        await self.ltm_store.write_batch(summaries)
        
        # 5. Mark originals archived
        for msg in messages:
            msg.archived = True
        await self.stm_store.write_batch(messages)
    
    def _cluster_by_topic(self, messages):
        """Use embedding similarity + agglomerative clustering."""
        from sklearn.cluster import AgglomerativeClustering
        import numpy as np
        
        embeddings = np.array([m.embedding for m in messages if m.embedding])
        clustering = AgglomerativeClustering(n_clusters=None, distance_threshold=0.5)
        labels = clustering.fit_predict(embeddings)
        
        clusters = {}
        for msg, label in zip(messages, labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(msg)
        
        return list(clusters.values())
```

### J.5 Validation Rules Reference

| Model | Field | Validation Logic |
|-------|-------|------------------|
| RecordEnvelope | tenant, namespace | Alphanumeric + underscore/hyphen only |
| RecordEnvelope | embedding | Dimensions in [384, 512, 768, 1024, 1536, 3072] |
| RecordEnvelope | relevance_score, importance_score | Range [0.0, 1.0] |
| MemoryQuery | query | Length [1, 8000] characters |
| MemoryQuery | token_budget | Range [100, 32000] |
| Settings | context_allocation | Values must sum to ~1.0 (tolerance ±0.02) |
| EventRecord | event_type | Max 128 chars, no whitespace |
| FactRecord | confidence | Range [0.0, 1.0] |
| ConversationTurn | role | Enum: user|assistant|system|tool |

### J.6 State Machine for Record Lifecycle

```
[CREATED] --ingestion--> [ACTIVE]
                           |
                           +--(access)--> [ACTIVE] (access_count++, last_accessed_at updated)
                           |
                           +--(decay check)--> [LOW_RELEVANCE] (relevance < threshold)
                           |                      |
                           |                      +--(archive)--> [ARCHIVED]
                           |
                           +--(consolidation)--> [SUMMARIZED] (new SUMMARY record created)
                                                     |
                                                     +--(original)--> [ARCHIVED]
```

### J.7 Configuration Validation Examples

```python
# Valid minimal config
settings = Settings(
    tiers={
        "working": TierConfig(backend="redis", ttl_seconds=300),
        "long_term": TierConfig(backend="chroma", half_life_days=60.0)
    }
)

# Invalid: context_allocation doesn't sum to 1.0
settings = Settings(
    tiers={...},
    context_allocation={"working": 0.5, "semantic": 0.3}  # sums to 0.8 -> ValidationError
)

# Invalid: namespace with spaces
envelope = RecordEnvelope(
    tenant="acme corp",  # ValidationError: spaces not allowed
    namespace="support",
    tier="working",
    content_type="TEXT",
    payload="test"
)
```

---
End of Document.

---
## 17. Implementation Kickoff Checklist

### 17.1 Prerequisites
| Item | Status Target | Notes |
|------|---------------|-------|
| Repository scaffold created | Week 1 | `smrti/` layout per Section 14.1 |
| CI pipeline (lint, type, tests) | Week 1 | mypy strict + ruff + pytest |
| Core models (RecordEnvelope, Settings) | Week 1 | Minimal fields only (no unused future fields) |
| Async adapter protocol stubs | Week 1 | TierStore, EmbeddingProvider |
| Dev docker-compose (redis + chroma) | Week 1 | Fast local bootstrap |

### 17.2 Phase 1 (Foundations) Exit Gate Validation
| Gate | Validation Action |
|------|-------------------|
| Record serialization stable | Round-trip tests (json -> model -> json) |
| Retrieval stub returns WM only | Unit test `test_context_wm_only` |
| Metrics skeleton exposed | `/metrics` returns base counters |
| Feature flags load from env | Inject `SMRTI_FEATURE_ENABLE_RERANK=false` in test |

### 17.3 Environment Variable Conventions
| Aspect | Convention | Example |
|--------|-----------|---------|
| Prefix | All vars start with `SMRTI_` | `SMRTI_LOG_LEVEL` |
| Feature Flags | `SMRTI_FEATURE_<NAME>` (upper snake) | `SMRTI_FEATURE_ENABLE_RERANK` |
| Tier Backend Override | `SMRTI_TIER_<TIERNAME>_BACKEND` | `SMRTI_TIER_WORKING_BACKEND=redis` |
| Decay Overrides | `SMRTI_DECAY_<TIER>_HALF_LIFE_DAYS` | `SMRTI_DECAY_LTM_HALF_LIFE_DAYS=45` |
| Token Budget | `SMRTI_CONTEXT_DEFAULT_BUDGET` | `SMRTI_CONTEXT_DEFAULT_BUDGET=8000` |
| Embeddings | `SMRTI_EMBEDDING_DEFAULT_MODEL` | `SMRTI_EMBEDDING_DEFAULT_MODEL=minilm` |

Normalization Rules:
1. Prose uses hyphenated names for tiers ("Short-Term Memory"); code/config uses snake_case (`short_term`).
2. All environment variables are uppercase snake with `SMRTI_` prefix.
3. Feature flags are booleans parsed case-insensitively (`true/false/1/0`).

### 17.4 Minimal Initial Milestone Tasks
| Task | Owner | Done When |
|------|-------|-----------|
| Implement `SmrtiClient.build_context` stub | Core Eng | Returns structured empty sections |
| Implement RedisWorkingStore MVP | Core Eng | write_batch + fetch pass tests |
| Implement ChromaLongTermStore MVP | Core Eng | approximate_search returns results |
| Add embedding provider (OpenAI or LiteLLM) | ML Eng | embed_texts / embed_query functional |
| Expose metrics endpoint | Infra Eng | Prometheus scrapes basic metrics |
| Add basic provenance (record_id + tier) | Core Eng | Included in context response |

### 17.5 Risk Early Detection Checklist
| Risk | Probe Test |
|------|-----------|
| Retrieval latency > target | Benchmark WM+LTM stub at 50 QPS |
| Over-complex adapter config | Add new dummy adapter in <30 mins |
| Missing provenance fields | Unit asserting presence in all context items |

### 17.6 Kickoff Definition of Done
| Criterion | Evidence |
|----------|----------|
| CI green on main | CI dashboard screenshot / badge |
| Base context assembly under 50ms (WM only) | Micro-benchmark output |
| Documentation quickstart validated | Engineer walkthrough log |

### 17.7 Post-Kickoff Next Steps
1. Implement STM → LTM summarization pipeline skeleton.
2. Add lexical BM25 index for hybrid retrieval.
3. Introduce reduction strategies with token estimation.

---
