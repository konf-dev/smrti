//! Core data models for smrti's knowledge graph.
//!
//! These models represent the graph structure: nodes (entities/facts),
//! edges (relationships), and search/traversal results.

use chrono::{DateTime, Utc};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

/// A node in the knowledge graph — an entity, concept, fact, or event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub id: Uuid,
    pub namespace: String,

    /// Optional unique key for identity anchoring (e.g., "user_123").
    /// Unique per namespace — used for upsert-by-key semantics.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node_key: Option<String>,

    /// User-defined type (e.g., "person", "task", "concept", "expense").
    pub node_type: String,

    /// The memory text — the main semantic content of this node.
    pub content: String,

    /// Original source type: "text", "image", "audio", "url", etc.
    /// Content field is always text; this records provenance.
    #[serde(default = "default_content_type")]
    pub content_type: String,

    /// User-defined metadata. Stored as JSONB, queryable via @> containment.
    #[serde(default)]
    pub metadata: Value,

    /// Soft-delete flag. Set by NODE_RETRACTED events.
    #[serde(default)]
    pub is_retracted: bool,

    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

fn default_content_type() -> String {
    "text".to_string()
}

/// A typed, directed relationship between two nodes with temporal validity.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    pub id: Uuid,
    pub namespace: String,
    pub source_node_id: Uuid,
    pub target_node_id: Uuid,

    /// User-defined type (e.g., "WORKS_AT", "TRACKS_METRIC", "DEPENDS_ON").
    pub edge_type: String,

    /// Edge-specific data (e.g., {"value": 50, "unit": "USD"}).
    #[serde(default)]
    pub metadata: Value,

    /// When this relationship became true.
    pub valid_from: DateTime<Utc>,

    /// When this relationship stopped being true. None means currently valid.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub valid_to: Option<DateTime<Utc>>,

    /// Soft-delete flag. Set by EDGE_RETRACTED events.
    #[serde(default)]
    pub is_retracted: bool,

    pub created_at: DateTime<Utc>,
}

/// A node returned by semantic search, with similarity score.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub node: Node,

    /// Cosine similarity score (0.0 to 1.0). Higher = more similar.
    pub similarity: f64,

    /// Which search modes found this result (e.g., ["vector", "text"]).
    #[serde(default)]
    pub matched_by: Vec<String>,

    /// Optionally populated edges connected to this node.
    #[serde(default)]
    pub edges: Vec<Edge>,
}

/// Result of a graph traversal — a subgraph of nodes and edges.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GraphResult {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
}

/// Input for adding a node (caller provides pre-computed data).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeInput {
    pub node_type: String,
    pub content: String,

    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node_key: Option<String>,

    #[serde(default = "default_content_type")]
    pub content_type: String,

    #[serde(default)]
    pub metadata: Value,

    /// Pre-computed embedding vector. If None, node is text-searchable only.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub embedding: Option<Vec<f32>>,

    /// Embedding model name. Required if embedding is provided.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model_name: Option<String>,
}

/// Input for adding an edge.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeInput {
    pub source_node_id: String,
    pub target_node_id: String,
    pub edge_type: String,

    #[serde(default)]
    pub metadata: Value,

    /// ISO 8601 string. Defaults to now if not provided.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub valid_from: Option<String>,

    /// ISO 8601 string. None means currently valid.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub valid_to: Option<String>,
}

/// Filter search results by edge relationships (provider-level, typed).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeFilter {
    /// Required: the edge type to filter by.
    pub edge_type: String,

    /// "outgoing", "incoming", or "both".
    #[serde(default = "default_direction")]
    pub direction: String,

    /// If provided, require the edge to connect to this specific node.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_node_id: Option<Uuid>,

    /// If provided, require the connected node to have this type.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_node_type: Option<String>,

    /// If provided, require edge metadata to contain these key-value pairs.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata_filter: Option<Value>,
}

fn default_direction() -> String {
    "outgoing".to_string()
}

/// Parameters for a search operation.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SearchQuery {
    /// Pre-computed query vector (required for vector/hybrid modes).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub query_vector: Option<Vec<f32>>,

    /// Text query for full-text/hybrid search.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub text_query: Option<String>,

    /// Namespaces to search.
    pub namespaces: Vec<String>,

    /// Search mode: "vector", "text", or "hybrid".
    #[serde(default = "default_search_mode")]
    pub mode: String,

    /// Embedding model name (for vector search).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model_name: Option<String>,

    /// Filter to specific node type.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node_type: Option<String>,

    /// Edge-based filters.
    #[serde(default)]
    pub edge_filters: Vec<EdgeFilter>,

    /// JSONB metadata containment filter.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata_filter: Option<Value>,

    /// Only nodes created after this time (ISO 8601).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub after: Option<String>,

    /// Only nodes created before this time (ISO 8601).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub before: Option<String>,

    /// Max results to return.
    #[serde(default = "default_limit")]
    pub limit: i64,

    /// Minimum similarity threshold (0.0-1.0).
    #[serde(default)]
    pub min_similarity: f64,
}

fn default_search_mode() -> String {
    "hybrid".to_string()
}

fn default_limit() -> i64 {
    10
}

/// Parameters for an aggregation operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AggregateQuery {
    pub edge_type: String,
    pub namespaces: Vec<String>,

    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata_key: Option<String>,

    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata_filter: Option<Value>,

    /// Point-in-time query: only include edges valid at this timestamp.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub at_time: Option<String>,
}

/// Result of an aggregation operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AggregateResult {
    pub count: i64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub total: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub average: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub minimum: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub maximum: Option<f64>,
}

/// An LLM-extracted node before reconciliation (used by callers).
///
/// Uses temporary string IDs (assigned by the LLM) that the caller
/// resolves to real UUIDs before storing in smrti.
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct CandidateNode {
    /// LLM-assigned label like "entity_1". Never a database ID.
    pub temp_id: String,

    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node_key: Option<String>,

    pub node_type: String,
    pub content: String,

    #[serde(default = "default_content_type")]
    pub content_type: String,

    #[serde(default)]
    pub metadata: Value,
}

/// An LLM-extracted edge before reconciliation (used by callers).
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct CandidateEdge {
    pub source_temp_id: String,
    pub target_temp_id: String,
    pub edge_type: String,

    #[serde(default)]
    pub metadata: Value,

    /// ISO 8601 string.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub valid_from: Option<String>,

    /// ISO 8601 string.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub valid_to: Option<String>,
}

/// Complete output from LLM extraction (used by callers).
///
/// Derives `JsonSchema` so callers can generate the JSON schema
/// to pass to their LLM for structured output.
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema, Default)]
pub struct ExtractionResult {
    #[serde(default)]
    pub nodes: Vec<CandidateNode>,

    #[serde(default)]
    pub edges: Vec<CandidateEdge>,
}
