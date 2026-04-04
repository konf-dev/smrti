//! # smrti-core
//!
//! Graph-based memory for AI agents, built on PostgreSQL + pgvector.
//!
//! smrti is a **dumb storage layer** — it does not call LLMs or generate
//! embeddings. It accepts pre-computed data (nodes, edges, embeddings)
//! and provides powerful search (vector, text, hybrid), graph traversal,
//! and aggregation.
//!
//! ## Architecture
//!
//! Two API layers:
//!
//! - **`Memory`** (Layer 1): flat params, string IDs, JSON returns with `_meta`.
//!   Designed for LLM tool calling and Python bindings.
//! - **`StorageProvider`** (Layer 2): typed params, UUIDs, Rust structs.
//!   For developers building custom pipelines.
//!
//! ## Quick Start (Rust)
//!
//! ```ignore
//! use smrti_core::{Memory, SmrtiConfig};
//!
//! let config = SmrtiConfig { dsn: "postgresql://localhost/mydb".into(), ..Default::default() };
//! let mut memory = Memory::connect(config).await?;
//!
//! // Store a node with pre-computed embedding
//! let result = memory.add_nodes(&[NodeInput {
//!     node_type: "person".into(),
//!     content: "Alice is an engineer".into(),
//!     embedding: Some(vec![0.1, 0.2, 0.3]),
//!     model_name: Some("nomic-embed-text".into()),
//!     ..Default::default()
//! }], None).await?;
//! ```

pub mod config;
pub mod error;
pub mod events;
pub mod memory;
pub mod models;
pub mod provider;
pub mod telemetry;

// Re-exports for convenience
pub use config::SmrtiConfig;
pub use error::{Result, SmrtiError};
pub use events::{Event, EventType};
pub use memory::{Memory, ScopedMemory};
pub use models::{
    AggregateQuery, AggregateResult, CandidateEdge, CandidateNode, Edge, EdgeFilter, EdgeInput,
    ExtractionResult, GraphResult, Node, NodeInput, SearchQuery, SearchResult,
};
pub use provider::{Direction, PurgeResult, StorageProvider};
