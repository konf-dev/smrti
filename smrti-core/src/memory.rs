//! Memory — the high-level, LLM-friendly API for smrti.
//!
//! Memory is a strict translation layer over [`StorageProvider`]. It:
//! - Validates inputs (raises [`SmrtiError::Validation`] for bad params)
//! - Translates flat string params to typed provider calls
//! - Adds `_meta` to every return value
//! - Returns `serde_json::Value` (maps to Python dicts via PyO3)
//!
//! Memory contains **zero SQL** and **zero database logic**. All data
//! access goes through the provider.

use std::time::Instant;

use serde_json::{json, Value};
use tracing::debug;
use uuid::Uuid;

use crate::config::SmrtiConfig;
use crate::error::{Result, SmrtiError};
use crate::events::{Event, EventType};
use crate::models::{AggregateQuery, EdgeFilter, SearchQuery};
use crate::provider::postgres::PostgresProvider;
use crate::provider::{Direction, StorageProvider};

/// High-level, LLM-friendly API for smrti.
///
/// All methods return `serde_json::Value` with a `_meta` key containing
/// operational metadata (duration_ms, event_ids, search_modes_used, etc.).
/// String IDs are used instead of UUIDs for LLM tool compatibility.
pub struct Memory {
    config: SmrtiConfig,
    provider: PostgresProvider,
}

impl Memory {
    /// Connect to the database, run migrations, and return a ready Memory instance.
    ///
    /// # Errors
    /// - `SmrtiError::Validation` if config is invalid
    /// - `SmrtiError::Connection` if database is unreachable
    /// - `SmrtiError::Migration` if migrations fail
    pub async fn connect(config: SmrtiConfig) -> Result<Self> {
        config.validate()?;
        let mut provider = PostgresProvider::new(config.clone());
        provider.connect().await?;
        Ok(Self { config, provider })
    }

    /// Close the database connection pool. Safe to call multiple times.
    pub async fn close(&mut self) -> Result<()> {
        self.provider.close().await
    }

    /// Default namespace from config.
    fn ns<'a>(&'a self, namespace: Option<&'a str>) -> &'a str {
        namespace.unwrap_or(&self.config.default_namespace)
    }

    // ------------------------------------------------------------------ //
    // Write
    // ------------------------------------------------------------------ //

    /// Add one or more nodes to the knowledge graph.
    ///
    /// Each node must have `node_type` and `content`. Optional: `node_key`,
    /// `content_type`, `metadata`, `embedding` (Vec<f32>), `model_name`.
    pub async fn add_nodes(&self, nodes: &[Value], namespace: Option<&str>) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);
        debug!(
            namespace = ns,
            count = nodes.len(),
            "smrti.memory.add_nodes"
        );

        if nodes.is_empty() {
            return Err(SmrtiError::Validation("nodes list is empty".into()));
        }

        // Build all events first (validation), then batch-apply in one transaction
        let mut node_ids = Vec::new();
        let mut events = Vec::new();

        for node in nodes {
            let node_type = node["node_type"]
                .as_str()
                .ok_or_else(|| SmrtiError::Validation("node_type is required".into()))?;
            let content = node["content"]
                .as_str()
                .ok_or_else(|| SmrtiError::Validation("content is required".into()))?;

            let id = Uuid::new_v4();
            let node_id = id.to_string();

            events.push(Event::new(
                ns,
                EventType::NodeCreated,
                json!({
                    "id": node_id,
                    "node_key": node.get("node_key").and_then(|v| v.as_str()),
                    "node_type": node_type,
                    "content": content,
                    "content_type": node.get("content_type").and_then(|v| v.as_str()).unwrap_or("text"),
                    "metadata": node.get("metadata").unwrap_or(&json!({})),
                }),
            ));

            // Embedding event (same transaction)
            if let Some(embedding) = node.get("embedding") {
                if !embedding.is_null() {
                    let model = node
                        .get("model_name")
                        .and_then(|v| v.as_str())
                        .unwrap_or(&self.config.embedding_model);

                    events.push(Event::new(
                        ns,
                        EventType::EmbeddingStored,
                        json!({
                            "node_id": node_id,
                            "model_name": model,
                            "embedding": embedding,
                        }),
                    ));
                }
            }

            node_ids.push(node_id);
        }

        // Single transaction for all events
        let event_ids = self.provider.apply_events_batch(&events).await?;

        Ok(json!({
            "node_ids": node_ids,
            "_meta": {
                "event_ids": event_ids,
                "namespace": ns,
                "count": node_ids.len(),
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Add one or more edges to the knowledge graph.
    ///
    /// Each edge must have `source_node_id`, `target_node_id`, `edge_type`.
    /// Optional: `metadata`, `valid_from`, `valid_to`.
    pub async fn add_edges(&self, edges: &[Value], namespace: Option<&str>) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);
        debug!(
            namespace = ns,
            count = edges.len(),
            "smrti.memory.add_edges"
        );

        if edges.is_empty() {
            return Err(SmrtiError::Validation("edges list is empty".into()));
        }

        // Build all events first, then batch-apply in one transaction
        let mut edge_ids = Vec::new();
        let mut events = Vec::new();

        for edge in edges {
            let source = edge["source_node_id"]
                .as_str()
                .ok_or_else(|| SmrtiError::Validation("source_node_id is required".into()))?;
            let target = edge["target_node_id"]
                .as_str()
                .ok_or_else(|| SmrtiError::Validation("target_node_id is required".into()))?;
            let edge_type = edge["edge_type"]
                .as_str()
                .ok_or_else(|| SmrtiError::Validation("edge_type is required".into()))?;

            let id = Uuid::new_v4().to_string();

            events.push(Event::new(
                ns,
                EventType::EdgeAdded,
                json!({
                    "id": id,
                    "source_node_id": source,
                    "target_node_id": target,
                    "edge_type": edge_type,
                    "metadata": edge.get("metadata").unwrap_or(&json!({})),
                    "valid_from": edge.get("valid_from"),
                    "valid_to": edge.get("valid_to"),
                }),
            ));
            edge_ids.push(id);
        }

        // Single transaction for all edge events
        let event_ids = self.provider.apply_events_batch(&events).await?;

        Ok(json!({
            "edge_ids": edge_ids,
            "_meta": {
                "event_ids": event_ids,
                "namespace": ns,
                "count": edge_ids.len(),
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Get an existing node or create a new one atomically.
    pub async fn get_or_create(
        &self,
        content: &str,
        node_type: &str,
        node_key: Option<&str>,
        namespace: Option<&str>,
    ) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);
        debug!(
            namespace = ns,
            node_type = node_type,
            has_key = node_key.is_some(),
            "smrti.memory.get_or_create"
        );

        let (node, created) = self
            .provider
            .get_or_create_node(ns, content, node_type, node_key)
            .await?;

        Ok(json!({
            "node_id": node.id.to_string(),
            "created": created,
            "node": serde_json::to_value(&node).map_err(|e| SmrtiError::Event(format!("Serialization error: {e}")))?,
            "_meta": {
                "namespace": ns,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Update fields on an existing node.
    pub async fn update_node(
        &self,
        node_id: &str,
        content: Option<&str>,
        metadata: Option<&Value>,
        node_type: Option<&str>,
    ) -> Result<Value> {
        let start = Instant::now();

        let uuid = Uuid::parse_str(node_id)
            .map_err(|e| SmrtiError::Validation(format!("Invalid node_id: {e}")))?;

        // Verify node exists
        self.provider
            .get_node(uuid)
            .await?
            .ok_or_else(|| SmrtiError::NodeNotFound {
                node_id: node_id.into(),
                namespace: "unknown".into(),
            })?;

        let mut payload = json!({"id": node_id});
        if let Some(c) = content {
            payload["content"] = json!(c);
        }
        if let Some(m) = metadata {
            payload["metadata"] = m.clone();
        }
        if let Some(t) = node_type {
            payload["node_type"] = json!(t);
        }

        let eid = self
            .provider
            .apply_event(&Event::new("", EventType::NodeUpdated, payload))
            .await?;

        Ok(json!({
            "node_id": node_id,
            "_meta": {
                "event_id": eid,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Soft-delete a node.
    pub async fn retract_node(&self, node_id: &str) -> Result<Value> {
        let start = Instant::now();

        Uuid::parse_str(node_id)
            .map_err(|e| SmrtiError::Validation(format!("Invalid node_id: {e}")))?;

        let eid = self
            .provider
            .apply_event(&Event::new(
                "",
                EventType::NodeRetracted,
                json!({"id": node_id}),
            ))
            .await?;

        Ok(json!({
            "node_id": node_id,
            "_meta": {
                "event_id": eid,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Soft-delete an edge.
    pub async fn retract_edge(&self, edge_id: &str) -> Result<Value> {
        let start = Instant::now();

        Uuid::parse_str(edge_id)
            .map_err(|e| SmrtiError::Validation(format!("Invalid edge_id: {e}")))?;

        let eid = self
            .provider
            .apply_event(&Event::new(
                "",
                EventType::EdgeRetracted,
                json!({"id": edge_id}),
            ))
            .await?;

        Ok(json!({
            "edge_id": edge_id,
            "_meta": {
                "event_id": eid,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Merge two nodes. Edges from remove_id are remapped to keep_id.
    pub async fn merge_nodes(&self, keep_id: &str, remove_id: &str) -> Result<Value> {
        let start = Instant::now();

        Uuid::parse_str(keep_id)
            .map_err(|e| SmrtiError::Validation(format!("Invalid keep_id: {e}")))?;
        Uuid::parse_str(remove_id)
            .map_err(|e| SmrtiError::Validation(format!("Invalid remove_id: {e}")))?;

        let eid = self
            .provider
            .apply_event(&Event::new(
                "",
                EventType::NodesMerged,
                json!({
                    "kept_id": keep_id,
                    "removed_id": remove_id,
                }),
            ))
            .await?;

        Ok(json!({
            "kept_id": keep_id,
            "removed_id": remove_id,
            "_meta": {
                "event_id": eid,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    // ------------------------------------------------------------------ //
    // Search
    // ------------------------------------------------------------------ //

    /// Search the knowledge graph.
    ///
    /// Supports three modes: "vector", "text", "hybrid" (default from config).
    /// All params are flat strings for LLM tool compatibility.
    #[allow(clippy::too_many_arguments)]
    pub async fn search(
        &self,
        query_vector: Option<Vec<f32>>,
        text_query: Option<&str>,
        namespaces: Option<Vec<String>>,
        mode: Option<&str>,
        node_type: Option<&str>,
        edge_type: Option<&str>,
        edge_target: Option<&str>,
        metadata_filter: Option<&Value>,
        after: Option<&str>,
        before: Option<&str>,
        limit: Option<i64>,
        min_similarity: Option<f64>,
    ) -> Result<Value> {
        let start = Instant::now();

        let mode = mode.unwrap_or(&self.config.search_mode);
        let ns_list = namespaces.unwrap_or_else(|| vec![self.config.default_namespace.clone()]);
        let limit = limit.unwrap_or(self.config.search_limit);
        debug!(
            mode = mode,
            namespaces = ?ns_list,
            limit = limit,
            has_vector = query_vector.is_some(),
            has_text = text_query.is_some(),
            "smrti.memory.search"
        );

        // Validate mode-specific requirements
        match mode {
            "vector" => {
                if query_vector.is_none() {
                    return Err(SmrtiError::Validation(
                        "vector mode requires query_vector".into(),
                    ));
                }
            }
            "text" => {
                if text_query.is_none() {
                    return Err(SmrtiError::Validation(
                        "text mode requires text_query".into(),
                    ));
                }
            }
            "hybrid" => {
                if query_vector.is_none() || text_query.is_none() {
                    return Err(SmrtiError::Validation(
                        "hybrid mode requires both query_vector and text_query".into(),
                    ));
                }
            }
            _ => {
                return Err(SmrtiError::Validation(format!(
                    "mode must be 'vector', 'text', or 'hybrid', got '{mode}'"
                )))
            }
        }

        // Build edge filters from flat params
        let mut edge_filters = Vec::new();
        if let Some(et) = edge_type {
            edge_filters.push(EdgeFilter {
                edge_type: et.to_string(),
                direction: "outgoing".into(),
                target_node_id: edge_target.and_then(|s| Uuid::parse_str(s).ok()),
                target_node_type: None,
                metadata_filter: None,
            });
        }

        let query = SearchQuery {
            query_vector,
            text_query: text_query.map(String::from),
            namespaces: ns_list.clone(),
            mode: mode.to_string(),
            model_name: Some(self.config.embedding_model.clone()),
            node_type: node_type.map(String::from),
            edge_filters,
            metadata_filter: metadata_filter.cloned(),
            after: after.map(String::from),
            before: before.map(String::from),
            limit,
            min_similarity: min_similarity.unwrap_or(self.config.min_similarity),
        };

        let results = self.provider.search_nodes(&query).await?;

        let results_json: Vec<Value> = results
            .iter()
            .map(|r| {
                json!({
                    "node_id": r.node.id.to_string(),
                    "content": r.node.content,
                    "node_type": r.node.node_type,
                    "similarity": r.similarity,
                    "matched_by": r.matched_by,
                    "metadata": r.node.metadata,
                })
            })
            .collect();

        let total = results_json.len();

        Ok(json!({
            "results": results_json,
            "_meta": {
                "search_mode": mode,
                "search_modes_used": results.iter()
                    .flat_map(|r| r.matched_by.iter().cloned())
                    .collect::<std::collections::HashSet<_>>(),
                "namespace": ns_list,
                "returned": total,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Walk the graph from a starting node.
    pub async fn traverse(
        &self,
        node_id: &str,
        depth: Option<u32>,
        edge_types: Option<&str>,
        max_nodes: Option<u32>,
    ) -> Result<Value> {
        let start = Instant::now();
        debug!(node_id = node_id, depth = ?depth, "smrti.memory.traverse");

        let uuid = Uuid::parse_str(node_id)
            .map_err(|e| SmrtiError::Validation(format!("Invalid node_id: {e}")))?;
        let depth = depth.unwrap_or(1);
        let max_nodes = max_nodes.unwrap_or(self.config.max_traversal_nodes);

        let edge_type_list: Option<Vec<String>> =
            edge_types.map(|s| s.split(',').map(|t| t.trim().to_string()).collect());

        let result = self
            .provider
            .traverse_graph(uuid, depth, edge_type_list.as_deref(), max_nodes)
            .await?;

        Ok(json!({
            "nodes": result.nodes.iter().map(|n| json!({
                "node_id": n.id.to_string(),
                "content": n.content,
                "node_type": n.node_type,
                "metadata": n.metadata,
            })).collect::<Vec<_>>(),
            "edges": result.edges.iter().map(|e| json!({
                "edge_id": e.id.to_string(),
                "source_node_id": e.source_node_id.to_string(),
                "target_node_id": e.target_node_id.to_string(),
                "edge_type": e.edge_type,
                "metadata": e.metadata,
            })).collect::<Vec<_>>(),
            "_meta": {
                "start_node_id": node_id,
                "depth": depth,
                "nodes_found": result.nodes.len(),
                "edges_found": result.edges.len(),
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Aggregate over edges of a given type.
    pub async fn aggregate(
        &self,
        edge_type: &str,
        namespace: Option<&str>,
        metadata_key: Option<&str>,
        filters: Option<&Value>,
        at_time: Option<&str>,
    ) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);
        debug!(
            edge_type = edge_type,
            namespace = ns,
            "smrti.memory.aggregate"
        );

        let query = AggregateQuery {
            edge_type: edge_type.into(),
            namespaces: vec![ns.into()],
            metadata_key: metadata_key.map(String::from),
            metadata_filter: filters.cloned(),
            at_time: at_time.map(String::from),
        };

        let result = self.provider.aggregate_edges(&query).await?;

        Ok(json!({
            "count": result.count,
            "total": result.total,
            "average": result.average,
            "minimum": result.minimum,
            "maximum": result.maximum,
            "_meta": {
                "edge_type": edge_type,
                "namespace": ns,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Get active edges for a node.
    pub async fn get_edges(
        &self,
        node_id: &str,
        direction: Option<&str>,
        edge_types: Option<&str>,
    ) -> Result<Value> {
        let start = Instant::now();

        let uuid = Uuid::parse_str(node_id)
            .map_err(|e| SmrtiError::Validation(format!("Invalid node_id: {e}")))?;
        let dir = Direction::parse(direction.unwrap_or("both"));
        let type_list: Option<Vec<String>> =
            edge_types.map(|s| s.split(',').map(|t| t.trim().to_string()).collect());

        let edges = self
            .provider
            .get_edges(&[uuid], dir, type_list.as_deref())
            .await?;

        let edges_json: Vec<Value> = edges
            .iter()
            .map(|e| {
                json!({
                    "edge_id": e.id.to_string(),
                    "source_node_id": e.source_node_id.to_string(),
                    "target_node_id": e.target_node_id.to_string(),
                    "edge_type": e.edge_type,
                    "metadata": e.metadata,
                    "valid_from": e.valid_from.to_rfc3339(),
                    "valid_to": e.valid_to.map(|t| t.to_rfc3339()),
                })
            })
            .collect();

        Ok(json!({
            "edges": edges_json,
            "_meta": {
                "node_id": node_id,
                "direction": direction.unwrap_or("both"),
                "count": edges_json.len(),
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    // ------------------------------------------------------------------ //
    // Import / Export
    // ------------------------------------------------------------------ //

    /// Export events from the log.
    pub async fn export_events(
        &self,
        after_id: Option<i64>,
        namespace: Option<&str>,
        limit: Option<i64>,
    ) -> Result<Value> {
        let start = Instant::now();
        let limit = limit.unwrap_or(self.config.max_events_export);

        let events = self
            .provider
            .get_events(after_id.unwrap_or(0), namespace, limit)
            .await?;

        let events_json: Vec<Value> = events
            .iter()
            .map(|e| serde_json::to_value(e).unwrap_or_default())
            .collect();

        let first_id = events.first().and_then(|e| e.id);
        let last_id = events.last().and_then(|e| e.id);

        Ok(json!({
            "events": events_json,
            "_meta": {
                "count": events.len(),
                "first_id": first_id,
                "last_id": last_id,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Import events by replaying them.
    pub async fn import_events(&self, events: &[Value]) -> Result<Value> {
        let start = Instant::now();

        let mut imported = 0;
        let mut first_id: Option<i64> = None;
        let mut last_id: Option<i64> = None;

        for event_val in events {
            let event: Event = serde_json::from_value(event_val.clone())
                .map_err(|e| SmrtiError::Event(format!("Invalid event: {e}")))?;

            let eid = self.provider.apply_event(&event).await?;
            if first_id.is_none() {
                first_id = Some(eid);
            }
            last_id = Some(eid);
            imported += 1;
        }

        Ok(json!({
            "imported": imported,
            "_meta": {
                "event_id_range": [first_id, last_id],
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    // ------------------------------------------------------------------ //
    // GDPR
    // ------------------------------------------------------------------ //

    /// Physically delete ALL data for a namespace.
    pub async fn purge_namespace(&self, namespace: &str) -> Result<Value> {
        let start = Instant::now();
        debug!(namespace = namespace, "smrti.memory.purge_namespace");
        let result = self.provider.purge_namespace(namespace).await?;

        Ok(json!({
            "purged": true,
            "namespace": namespace,
            "_meta": {
                "events_deleted": result.events_deleted,
                "nodes_deleted": result.nodes_deleted,
                "edges_deleted": result.edges_deleted,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    // ------------------------------------------------------------------ //
    // Session State (Working Memory)
    // ------------------------------------------------------------------ //

    /// Set a key-value pair in session state. Upserts (overwrites if exists).
    pub async fn state_set(
        &self,
        key: &str,
        value: &Value,
        session_id: &str,
        namespace: Option<&str>,
        ttl_seconds: Option<i64>,
    ) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);
        let ttl = ttl_seconds.or(self.config.session_state_default_ttl);
        debug!(
            namespace = ns,
            session_id = session_id,
            key = key,
            "smrti.memory.state_set"
        );

        self.provider
            .state_set(ns, session_id, key, value.clone(), ttl)
            .await?;

        Ok(json!({
            "key": key,
            "_meta": {
                "namespace": ns,
                "session_id": session_id,
                "ttl_seconds": ttl,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Get a value from session state. Returns null if not found or expired.
    pub async fn state_get(
        &self,
        key: &str,
        session_id: &str,
        namespace: Option<&str>,
    ) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);

        let value = self.provider.state_get(ns, session_id, key).await?;
        let found = value.is_some();

        Ok(json!({
            "value": value,
            "_meta": {
                "found": found,
                "namespace": ns,
                "session_id": session_id,
                "key": key,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Delete a key from session state.
    pub async fn state_delete(
        &self,
        key: &str,
        session_id: &str,
        namespace: Option<&str>,
    ) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);

        let existed = self.provider.state_delete(ns, session_id, key).await?;

        Ok(json!({
            "deleted": existed,
            "_meta": {
                "namespace": ns,
                "session_id": session_id,
                "key": key,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Clear all keys for a session.
    pub async fn state_clear(&self, session_id: &str, namespace: Option<&str>) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);

        let cleared = self.provider.state_clear(ns, session_id).await?;

        Ok(json!({
            "cleared": cleared,
            "_meta": {
                "namespace": ns,
                "session_id": session_id,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// List all non-expired keys for a session.
    pub async fn state_list(&self, session_id: &str, namespace: Option<&str>) -> Result<Value> {
        let start = Instant::now();
        let ns = self.ns(namespace);

        let entries = self.provider.state_list(ns, session_id).await?;
        let items: Vec<Value> = entries
            .iter()
            .map(|(k, v)| json!({"key": k, "value": v}))
            .collect();

        Ok(json!({
            "entries": items,
            "_meta": {
                "namespace": ns,
                "session_id": session_id,
                "count": items.len(),
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    /// Prune expired session state rows. Returns count deleted.
    pub async fn state_prune_expired(&self, namespace: Option<&str>) -> Result<Value> {
        let start = Instant::now();
        let pruned = self.provider.state_prune_expired(namespace).await?;

        Ok(json!({
            "pruned": pruned,
            "_meta": {
                "namespace": namespace,
                "duration_ms": start.elapsed().as_millis() as f64,
            }
        }))
    }

    // ------------------------------------------------------------------ //
    // Scoped context
    // ------------------------------------------------------------------ //

    /// Return a namespace-bound wrapper. All calls use the given namespace
    /// by default. The underlying provider and pool are shared.
    pub fn scoped(&self, namespace: &str) -> ScopedMemory<'_> {
        ScopedMemory {
            memory: self,
            namespace: namespace.to_string(),
        }
    }
}

/// A namespace-bound wrapper over Memory. All calls use the configured
/// namespace unless explicitly overridden.
pub struct ScopedMemory<'a> {
    memory: &'a Memory,
    namespace: String,
}

impl<'a> ScopedMemory<'a> {
    /// Add nodes in the scoped namespace.
    pub async fn add_nodes(&self, nodes: &[Value]) -> Result<Value> {
        self.memory.add_nodes(nodes, Some(&self.namespace)).await
    }

    /// Add edges in the scoped namespace.
    pub async fn add_edges(&self, edges: &[Value]) -> Result<Value> {
        self.memory.add_edges(edges, Some(&self.namespace)).await
    }

    /// Search in the scoped namespace.
    pub async fn search(
        &self,
        query_vector: Option<Vec<f32>>,
        text_query: Option<&str>,
        mode: Option<&str>,
        node_type: Option<&str>,
        limit: Option<i64>,
    ) -> Result<Value> {
        self.memory
            .search(
                query_vector,
                text_query,
                Some(vec![self.namespace.clone()]),
                mode,
                node_type,
                None,
                None,
                None,
                None,
                None,
                limit,
                None,
            )
            .await
    }

    /// Traverse in the scoped namespace.
    pub async fn traverse(&self, node_id: &str, depth: Option<u32>) -> Result<Value> {
        self.memory.traverse(node_id, depth, None, None).await
    }

    /// Aggregate in the scoped namespace.
    pub async fn aggregate(&self, edge_type: &str, metadata_key: Option<&str>) -> Result<Value> {
        self.memory
            .aggregate(edge_type, Some(&self.namespace), metadata_key, None, None)
            .await
    }
}
