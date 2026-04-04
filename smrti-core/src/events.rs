//! Event types for the append-only event log.
//!
//! Every mutation in smrti is recorded as an event. Events are the source
//! of truth — nodes and edges are projections derived from the event stream.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// All mutation types that can be recorded in the event log.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Hash)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum EventType {
    /// A new node was created.
    NodeCreated,
    /// An existing node was updated (content, metadata, or type).
    NodeUpdated,
    /// A node was soft-deleted (is_retracted = true).
    NodeRetracted,
    /// A new edge was created between two nodes.
    EdgeAdded,
    /// An existing edge was updated (metadata or valid_to).
    EdgeUpdated,
    /// An edge was soft-deleted (is_retracted = true).
    EdgeRetracted,
    /// An embedding vector was stored for a node.
    EmbeddingStored,
    /// Raw text was received (audit trail for caller's extraction pipeline).
    RawInputReceived,
    /// Two nodes were merged (edges remapped, one retracted).
    NodesMerged,
}

impl std::fmt::Display for EventType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Serialize to the SCREAMING_SNAKE_CASE string
        let s = serde_json::to_value(self)
            .ok()
            .and_then(|v| v.as_str().map(String::from))
            .unwrap_or_else(|| format!("{self:?}"));
        f.write_str(&s)
    }
}

/// An immutable event in the append-only log.
///
/// Events are the source of truth. Nodes, edges, and embeddings are
/// projections derived from the event stream. Each event is assigned
/// a monotonically increasing BIGSERIAL id by the database.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    /// Sequential ID assigned by the database. `None` before insertion.
    pub id: Option<i64>,

    /// Namespace this event belongs to.
    pub namespace: String,

    /// The type of mutation this event represents.
    pub event_type: EventType,

    /// Full event data — node fields, edge fields, embedding vectors, etc.
    #[serde(default)]
    pub payload: Value,

    /// System metadata — trace IDs, model versions, prompt IDs, etc.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,

    /// Timestamp assigned by the database. `None` before insertion.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub created_at: Option<DateTime<Utc>>,
}

impl Event {
    /// Create a new event (before database insertion).
    pub fn new(namespace: impl Into<String>, event_type: EventType, payload: Value) -> Self {
        Self {
            id: None,
            namespace: namespace.into(),
            event_type,
            payload,
            metadata: None,
            created_at: None,
        }
    }

    /// Attach system metadata to this event.
    pub fn with_metadata(mut self, metadata: Value) -> Self {
        self.metadata = Some(metadata);
        self
    }
}
