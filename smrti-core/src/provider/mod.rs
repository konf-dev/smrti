//! Storage provider trait and implementations.
//!
//! The `StorageProvider` trait defines the interface for all storage backends.
//! All mutations go through `apply_event()`, which atomically appends to the
//! event log and updates projections in a single transaction.

pub mod postgres;

use async_trait::async_trait;
use serde_json::Value;
use uuid::Uuid;

use crate::error::Result;
use crate::events::Event;
use crate::models::{
    AggregateQuery, AggregateResult, Edge, GraphResult, Node, SearchQuery, SearchResult,
};

/// Direction for edge queries.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    Outgoing,
    Incoming,
    Both,
}

impl Direction {
    /// Parse from string (case-insensitive). Defaults to `Both`.
    pub fn parse(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "outgoing" => Self::Outgoing,
            "incoming" => Self::Incoming,
            _ => Self::Both,
        }
    }
}

/// Result of a purge_namespace operation.
#[derive(Debug, Clone)]
pub struct PurgeResult {
    pub events_deleted: i64,
    pub nodes_deleted: i64,
    pub edges_deleted: i64,
}

/// The storage provider interface. All data access goes through this trait.
///
/// Implementations must guarantee:
/// - `apply_event()` is atomic (event log + projection in one transaction)
/// - All reads filter out retracted nodes/edges
/// - All temporal edge queries respect valid_from/valid_to
/// - Namespace isolation is enforced on every query
#[async_trait]
pub trait StorageProvider: Send + Sync {
    /// Initialize connection pool and run migrations.
    async fn connect(&mut self) -> Result<()>;

    /// Close connection pool.
    async fn close(&mut self) -> Result<()>;

    /// Apply pending database migrations.
    async fn migrate(&self) -> Result<()>;

    /// The single mutation entry point.
    ///
    /// Atomically: append event to log + update projection.
    /// Returns the event ID (BIGSERIAL).
    async fn apply_event(&self, event: &Event) -> Result<i64>;

    /// Apply multiple events in a single transaction. Returns event IDs.
    ///
    /// Default implementation calls `apply_event` in a loop (no transaction
    /// grouping). Backends should override for true batch atomicity.
    async fn apply_events_batch(&self, events: &[Event]) -> Result<Vec<i64>> {
        let mut ids = Vec::with_capacity(events.len());
        for event in events {
            ids.push(self.apply_event(event).await?);
        }
        Ok(ids)
    }

    /// Fetch a single node by ID.
    async fn get_node(&self, node_id: Uuid) -> Result<Option<Node>>;

    /// Fetch a node by identity anchor key within a namespace.
    async fn get_node_by_key(&self, namespace: &str, node_key: &str) -> Result<Option<Node>>;

    /// Atomic find-or-create by node_key or content+type.
    /// Returns (node, created: bool).
    async fn get_or_create_node(
        &self,
        namespace: &str,
        content: &str,
        node_type: &str,
        node_key: Option<&str>,
    ) -> Result<(Node, bool)>;

    /// Retrieve active edges for one or more nodes.
    async fn get_edges(
        &self,
        node_ids: &[Uuid],
        direction: Direction,
        edge_types: Option<&[String]>,
    ) -> Result<Vec<Edge>>;

    /// Semantic/text/hybrid search with native SQL pre-filtering.
    async fn search_nodes(&self, query: &SearchQuery) -> Result<Vec<SearchResult>>;

    /// BFS graph walk from a starting node.
    async fn traverse_graph(
        &self,
        start_node_id: Uuid,
        depth: u32,
        edge_types: Option<&[String]>,
        max_nodes: u32,
    ) -> Result<GraphResult>;

    /// SQL-side aggregation on edge metadata.
    async fn aggregate_edges(&self, query: &AggregateQuery) -> Result<AggregateResult>;

    /// Retrieve events from the log for replay or export.
    async fn get_events(
        &self,
        after_id: i64,
        namespace: Option<&str>,
        limit: i64,
    ) -> Result<Vec<Event>>;

    /// Physically delete ALL data for a namespace (GDPR).
    async fn purge_namespace(&self, namespace: &str) -> Result<PurgeResult>;

    // --- Session State (Working Memory) ---

    /// Set a key-value pair in session state. Upserts (overwrites if exists).
    async fn state_set(
        &self,
        namespace: &str,
        session_id: &str,
        key: &str,
        value: Value,
        ttl_seconds: Option<i64>,
    ) -> Result<()>;

    /// Get a value from session state. Returns None if not found or expired.
    async fn state_get(
        &self,
        namespace: &str,
        session_id: &str,
        key: &str,
    ) -> Result<Option<Value>>;

    /// Delete a key from session state. Returns true if the key existed.
    async fn state_delete(&self, namespace: &str, session_id: &str, key: &str) -> Result<bool>;

    /// Clear all keys for a session. Returns count of keys removed.
    async fn state_clear(&self, namespace: &str, session_id: &str) -> Result<u64>;

    /// List all non-expired keys for a session, ordered by key name.
    async fn state_list(&self, namespace: &str, session_id: &str) -> Result<Vec<(String, Value)>>;

    /// Delete all expired session state rows. Returns count deleted.
    /// Optionally scope to a single namespace.
    /// Call on a schedule if expired row accumulation is a concern.
    async fn state_prune_expired(&self, namespace: Option<&str>) -> Result<u64>;
}
