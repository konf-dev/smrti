//! PostgreSQL + pgvector storage provider.
//!
//! Implements [`StorageProvider`] using sqlx with a PgPool. All mutations go
//! through [`apply_event`] which atomically appends to the event log and
//! updates projections in a single transaction.
//!
//! ## Architecture notes
//!
//! - Projection functions are **module-level free functions** (not `&self`
//!   methods) to avoid async_trait + sqlx transaction lifetime conflicts.
//! - Search helpers are **private methods on `PostgresProvider`** since they
//!   only use `self.pool()` (no transactions).
//! - Row types (`NodeRow`, `EdgeRow`, `EventRow`) are private conversion
//!   structs with `sqlx::FromRow`.
//!
//! ## Security
//!
//! **Zero string interpolation for user values.** Every WHERE clause, filter,
//! and value uses `$N` bind parameters. Dynamic SQL is only used for DDL
//! (index names) after strict validation via `is_safe_identifier`.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use pgvector::Vector;
use serde_json::{json, Value};
use sqlx::postgres::PgPoolOptions;
use sqlx::{PgPool, Postgres, Row, Transaction};
use tracing::{debug, info};
use uuid::Uuid;

use crate::config::SmrtiConfig;
use crate::error::{Result, SmrtiError};
use crate::events::{Event, EventType};
use crate::models::{
    AggregateQuery, AggregateResult, Edge, GraphResult, Node, SearchQuery, SearchResult,
};
use crate::provider::{Direction, PurgeResult};

// ---------------------------------------------------------------------------
// SQL migration embedded at compile time
// ---------------------------------------------------------------------------

const V001_MIGRATION: &str = include_str!("../sql/migrations/v001_initial.sql");
const V002_MIGRATION: &str = include_str!("../sql/migrations/v002_session_state.sql");

// ---------------------------------------------------------------------------
// Private row types for sqlx::FromRow
// ---------------------------------------------------------------------------

#[derive(Debug, sqlx::FromRow)]
struct NodeRow {
    id: Uuid,
    namespace: String,
    node_key: Option<String>,
    node_type: String,
    content: String,
    content_type: String,
    metadata: Value,
    is_retracted: bool,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl From<NodeRow> for Node {
    fn from(r: NodeRow) -> Self {
        Node {
            id: r.id,
            namespace: r.namespace,
            node_key: r.node_key,
            node_type: r.node_type,
            content: r.content,
            content_type: r.content_type,
            metadata: r.metadata,
            is_retracted: r.is_retracted,
            created_at: r.created_at,
            updated_at: r.updated_at,
        }
    }
}

#[derive(Debug, sqlx::FromRow)]
struct EdgeRow {
    id: Uuid,
    namespace: String,
    source_node_id: Uuid,
    target_node_id: Uuid,
    edge_type: String,
    metadata: Value,
    valid_from: DateTime<Utc>,
    valid_to: Option<DateTime<Utc>>,
    is_retracted: bool,
    created_at: DateTime<Utc>,
}

impl From<EdgeRow> for Edge {
    fn from(r: EdgeRow) -> Self {
        Edge {
            id: r.id,
            namespace: r.namespace,
            source_node_id: r.source_node_id,
            target_node_id: r.target_node_id,
            edge_type: r.edge_type,
            metadata: r.metadata,
            valid_from: r.valid_from,
            valid_to: r.valid_to,
            is_retracted: r.is_retracted,
            created_at: r.created_at,
        }
    }
}

#[derive(Debug, sqlx::FromRow)]
struct EventRow {
    id: i64,
    namespace: String,
    event_type: String,
    payload: Value,
    metadata: Option<Value>,
    created_at: DateTime<Utc>,
}

impl TryFrom<EventRow> for Event {
    type Error = SmrtiError;

    fn try_from(r: EventRow) -> Result<Self> {
        let event_type: EventType = serde_json::from_value(Value::String(r.event_type.clone()))
            .map_err(|e| {
                SmrtiError::Event(format!("Unknown event type '{}': {}", r.event_type, e))
            })?;
        Ok(Event {
            id: Some(r.id),
            namespace: r.namespace,
            event_type,
            payload: r.payload,
            metadata: r.metadata,
            created_at: Some(r.created_at),
        })
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Validate that an identifier is safe for use in dynamic SQL (index names).
fn is_safe_identifier(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 63
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

/// Sanitize a model name for use in SQL index names (replace non-alnum with _).
fn sanitize_identifier(s: &str) -> String {
    s.chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '_' })
        .collect()
}

/// Map distance metric name to pgvector operator class.
fn distance_ops(metric: &str) -> &'static str {
    match metric {
        "l2" => "vector_l2_ops",
        "inner_product" => "vector_ip_ops",
        _ => "vector_cosine_ops",
    }
}

/// Map distance metric name to pgvector SQL operator.
#[allow(dead_code)]
fn distance_operator(metric: &str) -> &'static str {
    match metric {
        "l2" => "<->",
        "inner_product" => "<#>",
        _ => "<=>",
    }
}

/// Helper to extract a node from a `sqlx::Row` by column name.
fn node_from_row(row: &sqlx::postgres::PgRow) -> Node {
    Node {
        id: row.get("id"),
        namespace: row.get("namespace"),
        node_key: row.get("node_key"),
        node_type: row.get("node_type"),
        content: row.get("content"),
        content_type: row.get("content_type"),
        metadata: row.get("metadata"),
        is_retracted: row.get("is_retracted"),
        created_at: row.get("created_at"),
        updated_at: row.get("updated_at"),
    }
}

// ---------------------------------------------------------------------------
// Free projection functions (avoid async_trait + transaction lifetime issues)
// ---------------------------------------------------------------------------

/// Insert an event row into the event log and return the assigned BIGSERIAL id.
async fn insert_event_row(tx: &mut Transaction<'_, Postgres>, event: &Event) -> Result<i64> {
    let event_type_str = event.event_type.to_string();
    let meta_value = event.metadata.clone().unwrap_or_else(|| json!({}));

    let event_id: i64 = sqlx::query_scalar(
        r#"
        INSERT INTO events (namespace, event_type, payload, metadata)
        VALUES ($1, $2, $3::jsonb, $4::jsonb)
        RETURNING id
        "#,
    )
    .bind(&event.namespace)
    .bind(&event_type_str)
    .bind(&event.payload)
    .bind(&meta_value)
    .fetch_one(&mut **tx)
    .await?;

    Ok(event_id)
}

async fn apply_projection(
    tx: &mut Transaction<'_, Postgres>,
    event: &Event,
    config: &SmrtiConfig,
) -> Result<()> {
    match event.event_type {
        EventType::NodeCreated => project_node_created(tx, &event.namespace, &event.payload).await,
        EventType::NodeUpdated => project_node_updated(tx, &event.payload).await,
        EventType::NodeRetracted => project_node_retracted(tx, &event.payload).await,
        EventType::EdgeAdded => project_edge_added(tx, &event.namespace, &event.payload).await,
        EventType::EdgeUpdated => project_edge_updated(tx, &event.payload).await,
        EventType::EdgeRetracted => project_edge_retracted(tx, &event.payload).await,
        EventType::EmbeddingStored => {
            project_embedding_stored(
                tx,
                &event.payload,
                &config.distance_metric,
                config.hnsw_m,
                config.hnsw_ef_construction,
            )
            .await
        }
        EventType::RawInputReceived => {
            debug!("RAW_INPUT_RECEIVED logged (no projection)");
            Ok(())
        }
        EventType::NodesMerged => project_nodes_merged(tx, &event.payload).await,
    }
}

async fn project_node_created(
    tx: &mut Transaction<'_, Postgres>,
    namespace: &str,
    payload: &Value,
) -> Result<()> {
    let id: Uuid = serde_json::from_value(payload.get("id").cloned().unwrap_or(Value::Null))
        .map_err(|e| SmrtiError::Event(format!("NODE_CREATED missing/invalid id: {e}")))?;

    let node_key = payload.get("node_key").and_then(|v| v.as_str());
    let node_type = payload
        .get("node_type")
        .and_then(|v| v.as_str())
        .unwrap_or("default");
    let content = payload
        .get("content")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let content_type = payload
        .get("content_type")
        .and_then(|v| v.as_str())
        .unwrap_or("text");
    let metadata = payload.get("metadata").cloned().unwrap_or(json!({}));

    // Upsert: ON CONFLICT by (namespace, node_key) update content/metadata.
    sqlx::query(
        r#"
        INSERT INTO nodes (id, namespace, node_key, node_type, content, content_type, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        ON CONFLICT (namespace, node_key) WHERE node_key IS NOT NULL
        DO UPDATE SET
            content = EXCLUDED.content,
            node_type = EXCLUDED.node_type,
            content_type = EXCLUDED.content_type,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        "#,
    )
    .bind(id)
    .bind(namespace)
    .bind(node_key)
    .bind(node_type)
    .bind(content)
    .bind(content_type)
    .bind(&metadata)
    .execute(&mut **tx)
    .await?;

    debug!(node_id = %id, "Projected NODE_CREATED");
    Ok(())
}

/// Issue 6: Separate parameterized updates per field instead of dynamic SET.
async fn project_node_updated(tx: &mut Transaction<'_, Postgres>, payload: &Value) -> Result<()> {
    let id: Uuid = serde_json::from_value(payload.get("id").cloned().unwrap_or(Value::Null))
        .map_err(|e| SmrtiError::Event(format!("NODE_UPDATED missing/invalid id: {e}")))?;

    let mut any_updated = false;

    if let Some(content) = payload.get("content").and_then(|v| v.as_str()) {
        sqlx::query("UPDATE nodes SET content = $1, updated_at = NOW() WHERE id = $2")
            .bind(content)
            .bind(id)
            .execute(&mut **tx)
            .await?;
        any_updated = true;
    }

    if let Some(node_type) = payload.get("node_type").and_then(|v| v.as_str()) {
        sqlx::query("UPDATE nodes SET node_type = $1, updated_at = NOW() WHERE id = $2")
            .bind(node_type)
            .bind(id)
            .execute(&mut **tx)
            .await?;
        any_updated = true;
    }

    if let Some(metadata) = payload.get("metadata") {
        if !metadata.is_null() {
            sqlx::query("UPDATE nodes SET metadata = $1::jsonb, updated_at = NOW() WHERE id = $2")
                .bind(metadata)
                .bind(id)
                .execute(&mut **tx)
                .await?;
            any_updated = true;
        }
    }

    if let Some(content_type) = payload.get("content_type").and_then(|v| v.as_str()) {
        sqlx::query("UPDATE nodes SET content_type = $1, updated_at = NOW() WHERE id = $2")
            .bind(content_type)
            .bind(id)
            .execute(&mut **tx)
            .await?;
        any_updated = true;
    }

    if !any_updated {
        debug!(node_id = %id, "NODE_UPDATED with no fields to update");
    } else {
        debug!(node_id = %id, "Projected NODE_UPDATED");
    }

    Ok(())
}

async fn project_node_retracted(tx: &mut Transaction<'_, Postgres>, payload: &Value) -> Result<()> {
    let id: Uuid = serde_json::from_value(payload.get("id").cloned().unwrap_or(Value::Null))
        .map_err(|e| SmrtiError::Event(format!("NODE_RETRACTED missing/invalid id: {e}")))?;

    sqlx::query("UPDATE nodes SET is_retracted = TRUE, updated_at = NOW() WHERE id = $1")
        .bind(id)
        .execute(&mut **tx)
        .await?;

    debug!(node_id = %id, "Projected NODE_RETRACTED");
    Ok(())
}

async fn project_edge_added(
    tx: &mut Transaction<'_, Postgres>,
    namespace: &str,
    payload: &Value,
) -> Result<()> {
    let id: Uuid = serde_json::from_value(payload.get("id").cloned().unwrap_or(Value::Null))
        .map_err(|e| SmrtiError::Event(format!("EDGE_ADDED missing/invalid id: {e}")))?;
    let source_node_id: Uuid = serde_json::from_value(
        payload
            .get("source_node_id")
            .cloned()
            .unwrap_or(Value::Null),
    )
    .map_err(|e| SmrtiError::Event(format!("EDGE_ADDED missing source_node_id: {e}")))?;
    let target_node_id: Uuid = serde_json::from_value(
        payload
            .get("target_node_id")
            .cloned()
            .unwrap_or(Value::Null),
    )
    .map_err(|e| SmrtiError::Event(format!("EDGE_ADDED missing target_node_id: {e}")))?;
    let edge_type = payload
        .get("edge_type")
        .and_then(|v| v.as_str())
        .unwrap_or("RELATED_TO");
    let metadata = payload.get("metadata").cloned().unwrap_or(json!({}));

    let valid_from: Option<DateTime<Utc>> = payload
        .get("valid_from")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse().ok());
    let valid_to: Option<DateTime<Utc>> = payload
        .get("valid_to")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse().ok());

    sqlx::query(
        r#"
        INSERT INTO edges (id, namespace, source_node_id, target_node_id, edge_type,
                           metadata, valid_from, valid_to)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, COALESCE($7, NOW()), $8)
        "#,
    )
    .bind(id)
    .bind(namespace)
    .bind(source_node_id)
    .bind(target_node_id)
    .bind(edge_type)
    .bind(&metadata)
    .bind(valid_from)
    .bind(valid_to)
    .execute(&mut **tx)
    .await?;

    debug!(edge_id = %id, "Projected EDGE_ADDED");
    Ok(())
}

async fn project_edge_updated(tx: &mut Transaction<'_, Postgres>, payload: &Value) -> Result<()> {
    let id: Uuid = serde_json::from_value(payload.get("id").cloned().unwrap_or(Value::Null))
        .map_err(|e| SmrtiError::Event(format!("EDGE_UPDATED missing/invalid id: {e}")))?;

    let metadata = payload.get("metadata").cloned();
    let valid_to: Option<DateTime<Utc>> = payload
        .get("valid_to")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse().ok());
    let has_valid_to_field = payload.get("valid_to").is_some();

    match (metadata, has_valid_to_field) {
        (Some(m), true) => {
            sqlx::query("UPDATE edges SET metadata = $2::jsonb, valid_to = $3 WHERE id = $1")
                .bind(id)
                .bind(m)
                .bind(valid_to)
                .execute(&mut **tx)
                .await?;
        }
        (Some(m), false) => {
            sqlx::query("UPDATE edges SET metadata = $2::jsonb WHERE id = $1")
                .bind(id)
                .bind(m)
                .execute(&mut **tx)
                .await?;
        }
        (None, true) => {
            sqlx::query("UPDATE edges SET valid_to = $2 WHERE id = $1")
                .bind(id)
                .bind(valid_to)
                .execute(&mut **tx)
                .await?;
        }
        (None, false) => {
            debug!(edge_id = %id, "EDGE_UPDATED with no fields");
        }
    }

    debug!(edge_id = %id, "Projected EDGE_UPDATED");
    Ok(())
}

async fn project_edge_retracted(tx: &mut Transaction<'_, Postgres>, payload: &Value) -> Result<()> {
    let id: Uuid = serde_json::from_value(payload.get("id").cloned().unwrap_or(Value::Null))
        .map_err(|e| SmrtiError::Event(format!("EDGE_RETRACTED missing/invalid id: {e}")))?;

    sqlx::query("UPDATE edges SET is_retracted = TRUE WHERE id = $1")
        .bind(id)
        .execute(&mut **tx)
        .await?;

    debug!(edge_id = %id, "Projected EDGE_RETRACTED");
    Ok(())
}

async fn project_embedding_stored(
    tx: &mut Transaction<'_, Postgres>,
    payload: &Value,
    distance_metric: &str,
    hnsw_m: u32,
    hnsw_ef: u32,
) -> Result<()> {
    let node_id: Uuid =
        serde_json::from_value(payload.get("node_id").cloned().unwrap_or(Value::Null))
            .map_err(|e| SmrtiError::Embedding(format!("EMBEDDING_STORED missing node_id: {e}")))?;

    let model_name = payload
        .get("model_name")
        .and_then(|v| v.as_str())
        .unwrap_or("default");

    let embedding_arr: Vec<f32> =
        serde_json::from_value(payload.get("embedding").cloned().unwrap_or(Value::Null))
            .map_err(|e| SmrtiError::Embedding(format!("Invalid embedding array: {e}")))?;

    if embedding_arr.is_empty() {
        return Err(SmrtiError::Embedding("Embedding vector is empty".into()));
    }

    let dim = embedding_arr.len();
    let vector = Vector::from(embedding_arr);

    sqlx::query(
        r#"
        INSERT INTO node_embeddings (node_id, model_name, embedding)
        VALUES ($1, $2, $3)
        ON CONFLICT (node_id, model_name)
        DO UPDATE SET embedding = EXCLUDED.embedding, created_at = NOW()
        "#,
    )
    .bind(node_id)
    .bind(model_name)
    .bind(&vector)
    .execute(&mut **tx)
    .await?;

    // Ensure HNSW index exists for this model + dimension.
    ensure_hnsw_index(tx, model_name, dim, distance_metric, hnsw_m, hnsw_ef).await?;

    debug!(node_id = %node_id, model = model_name, dim = dim, "Projected EMBEDDING_STORED");
    Ok(())
}

async fn ensure_hnsw_index(
    tx: &mut Transaction<'_, Postgres>,
    model_name: &str,
    dim: usize,
    distance_metric: &str,
    hnsw_m: u32,
    hnsw_ef: u32,
) -> Result<()> {
    if !is_safe_identifier(model_name) {
        return Err(SmrtiError::Validation(format!(
            "Unsafe model_name for index creation: '{model_name}'"
        )));
    }

    let meta_key = format!("hnsw_index:{model_name}:{dim}");

    // Check if already tracked.
    let exists: Option<String> = sqlx::query_scalar("SELECT value FROM smrti_meta WHERE key = $1")
        .bind(&meta_key)
        .fetch_optional(&mut **tx)
        .await?;

    if exists.is_some() {
        return Ok(());
    }

    let sanitized = sanitize_identifier(model_name);
    let idx_name = format!("idx_embeddings_hnsw_{sanitized}_{dim}");
    let ops = distance_ops(distance_metric);

    // Dynamic DDL — model_name is validated by is_safe_identifier above.
    // DDL parameters cannot be bound with $N, so we use validated string
    // interpolation only for identifier names and integer constants.
    let ddl = format!(
        r#"CREATE INDEX IF NOT EXISTS {idx_name}
           ON node_embeddings USING hnsw ((embedding::vector({dim})) {ops})
           WITH (m = {hnsw_m}, ef_construction = {hnsw_ef})
           WHERE model_name = '{model_name}'"#
    );

    sqlx::query(&ddl).execute(&mut **tx).await.map_err(|e| {
        SmrtiError::Migration(format!("Failed to create HNSW index {idx_name}: {e}"))
    })?;

    sqlx::query("INSERT INTO smrti_meta (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING")
        .bind(&meta_key)
        .bind("created")
        .execute(&mut **tx)
        .await?;

    info!(index = idx_name, "Created HNSW index");
    Ok(())
}

async fn project_nodes_merged(tx: &mut Transaction<'_, Postgres>, payload: &Value) -> Result<()> {
    let kept_id: Uuid =
        serde_json::from_value(payload.get("kept_id").cloned().unwrap_or(Value::Null))
            .map_err(|e| SmrtiError::Event(format!("NODES_MERGED missing kept_id: {e}")))?;
    let removed_id: Uuid =
        serde_json::from_value(payload.get("removed_id").cloned().unwrap_or(Value::Null))
            .map_err(|e| SmrtiError::Event(format!("NODES_MERGED missing removed_id: {e}")))?;

    // Remap edges from removed_id to kept_id.
    sqlx::query("UPDATE edges SET source_node_id = $1 WHERE source_node_id = $2")
        .bind(kept_id)
        .bind(removed_id)
        .execute(&mut **tx)
        .await?;

    sqlx::query("UPDATE edges SET target_node_id = $1 WHERE target_node_id = $2")
        .bind(kept_id)
        .bind(removed_id)
        .execute(&mut **tx)
        .await?;

    // Retract the removed node.
    sqlx::query("UPDATE nodes SET is_retracted = TRUE, updated_at = NOW() WHERE id = $1")
        .bind(removed_id)
        .execute(&mut **tx)
        .await?;

    debug!(kept = %kept_id, removed = %removed_id, "Projected NODES_MERGED");
    Ok(())
}

// ---------------------------------------------------------------------------
// Dynamic query builder helpers (parameterized, zero interpolation)
// ---------------------------------------------------------------------------

/// Tracks bind parameter indices and collects values for dynamic queries.
/// All user values go through bind parameters ($N); never interpolated.
struct DynQuery {
    conditions: Vec<String>,
    /// We store boxed closures that bind values onto a query in order.
    /// Since sqlx Query types are generic, we store the values directly.
    string_vals: Vec<DynVal>,
    next_idx: usize,
}

/// A dynamic bind value.
#[derive(Clone)]
enum DynVal {
    Str(String),
    Json(Value),
    Timestamp(String),
    Uuid(Uuid),
}

impl DynQuery {
    fn new(start_idx: usize) -> Self {
        Self {
            conditions: Vec::new(),
            string_vals: Vec::new(),
            next_idx: start_idx,
        }
    }

    fn next_param(&mut self) -> usize {
        let idx = self.next_idx;
        self.next_idx += 1;
        idx
    }

    fn push_str_condition(&mut self, sql_template: &str, val: &str) {
        let idx = self.next_param();
        self.conditions
            .push(sql_template.replace("{}", &format!("${idx}")));
        self.string_vals.push(DynVal::Str(val.to_string()));
    }

    fn push_json_condition(&mut self, sql_template: &str, val: &Value) {
        let idx = self.next_param();
        self.conditions
            .push(sql_template.replace("{}", &format!("${idx}")));
        self.string_vals.push(DynVal::Json(val.clone()));
    }

    fn push_timestamp_condition(&mut self, sql_template: &str, val: &str) {
        let idx = self.next_param();
        self.conditions
            .push(sql_template.replace("{}", &format!("${idx}::timestamptz")));
        self.string_vals.push(DynVal::Timestamp(val.to_string()));
    }

    #[allow(dead_code)]
    fn push_uuid_condition(&mut self, sql_template: &str, val: Uuid) {
        let idx = self.next_param();
        self.conditions
            .push(sql_template.replace("{}", &format!("${idx}")));
        self.string_vals.push(DynVal::Uuid(val));
    }

    fn conditions_sql(&self) -> String {
        if self.conditions.is_empty() {
            String::new()
        } else {
            format!(" AND {}", self.conditions.join(" AND "))
        }
    }
}

/// Bind all dynamic values onto a sqlx query in order.
fn bind_dyn_vals<'q>(
    mut query: sqlx::query::Query<'q, Postgres, sqlx::postgres::PgArguments>,
    vals: &'q [DynVal],
) -> sqlx::query::Query<'q, Postgres, sqlx::postgres::PgArguments> {
    for val in vals {
        match val {
            DynVal::Str(s) => query = query.bind(s.as_str()),
            DynVal::Json(j) => query = query.bind(j),
            DynVal::Timestamp(t) => query = query.bind(t.as_str()),
            DynVal::Uuid(u) => query = query.bind(u),
        }
    }
    query
}

// ---------------------------------------------------------------------------
// Edge filter SQL builder (parameterized — no user-value interpolation)
// ---------------------------------------------------------------------------

/// Build parameterized edge filter subqueries.
/// Returns (sql_fragment, bind_values) where sql_fragment contains $N placeholders
/// starting from `start_idx`. Returns the next available parameter index.
fn build_edge_filter_sql(
    filters: &[crate::models::EdgeFilter],
    start_idx: usize,
) -> (String, Vec<DynVal>, usize) {
    if filters.is_empty() {
        return (String::new(), Vec::new(), start_idx);
    }

    let mut clauses = Vec::new();
    let mut vals: Vec<DynVal> = Vec::new();
    let mut idx = start_idx;

    for ef in filters {
        let mut conditions = Vec::new();

        // edge_type — bind parameter
        conditions.push(format!("e_filter.edge_type = ${idx}"));
        vals.push(DynVal::Str(ef.edge_type.clone()));
        idx += 1;

        conditions.push("e_filter.is_retracted = FALSE".into());
        conditions.push("e_filter.valid_from <= NOW()".into());
        conditions.push("(e_filter.valid_to IS NULL OR e_filter.valid_to >= NOW())".into());

        let direction_col = match ef.direction.to_lowercase().as_str() {
            "incoming" => "e_filter.target_node_id = n.id",
            "both" => "(e_filter.source_node_id = n.id OR e_filter.target_node_id = n.id)",
            _ => "e_filter.source_node_id = n.id", // outgoing (default)
        };
        conditions.push(direction_col.into());

        let mut join_target = String::new();

        if let Some(ref tid) = ef.target_node_id {
            conditions.push(format!("e_filter.target_node_id = ${idx}"));
            vals.push(DynVal::Uuid(*tid));
            idx += 1;
        }

        if let Some(ref ttype) = ef.target_node_type {
            join_target =
                " JOIN nodes n_target ON n_target.id = e_filter.target_node_id".to_string();
            conditions.push(format!("n_target.node_type = ${idx}"));
            vals.push(DynVal::Str(ttype.clone()));
            idx += 1;
        }

        if let Some(ref mf) = ef.metadata_filter {
            conditions.push(format!("e_filter.metadata @> ${idx}::jsonb"));
            vals.push(DynVal::Json(mf.clone()));
            idx += 1;
        }

        clauses.push(format!(
            "EXISTS (SELECT 1 FROM edges e_filter{join_target} WHERE {conds})",
            conds = conditions.join(" AND ")
        ));
    }

    let sql = format!(" AND {}", clauses.join(" AND "));
    (sql, vals, idx)
}

/// Build common WHERE extras for search queries with bind parameters.
/// Returns (sql_fragment, bind_values, next_idx).
fn build_search_where_extras(
    query: &SearchQuery,
    start_idx: usize,
) -> (String, Vec<DynVal>, usize) {
    let mut dq = DynQuery::new(start_idx);

    if let Some(ref nt) = query.node_type {
        dq.push_str_condition("n.node_type = {}", nt);
    }
    if let Some(ref mf) = query.metadata_filter {
        dq.push_json_condition("n.metadata @> {}::jsonb", mf);
    }
    if let Some(ref after) = query.after {
        dq.push_timestamp_condition("n.created_at > {}", after);
    }
    if let Some(ref before) = query.before {
        dq.push_timestamp_condition("n.created_at < {}", before);
    }

    let sql = dq.conditions_sql();
    (sql, dq.string_vals, dq.next_idx)
}

// ---------------------------------------------------------------------------
// PostgresProvider
// ---------------------------------------------------------------------------

/// PostgreSQL storage provider using sqlx and pgvector.
///
/// Holds a connection pool and configuration. Call [`connect()`] before
/// using any other methods.
///
/// All mutations go through [`apply_event()`], which atomically appends
/// to the event log and updates projections in one transaction.
pub struct PostgresProvider {
    config: SmrtiConfig,
    pool: Option<PgPool>,
}

impl PostgresProvider {
    /// Create a new provider from configuration. Call `connect()` to initialize the pool.
    pub fn new(config: SmrtiConfig) -> Self {
        Self { config, pool: None }
    }

    /// Get a reference to the pool, returning an error if not connected.
    fn pool(&self) -> Result<&PgPool> {
        self.pool
            .as_ref()
            .ok_or_else(|| SmrtiError::Connection("Not connected. Call connect() first.".into()))
    }

    // -----------------------------------------------------------------------
    // Private search methods
    // -----------------------------------------------------------------------

    async fn search_vector(&self, query: &SearchQuery) -> Result<Vec<SearchResult>> {
        let pool = self.pool()?;
        let query_vec = query
            .query_vector
            .as_ref()
            .ok_or_else(|| SmrtiError::Search("Vector search requires query_vector".into()))?;
        let model_name = query
            .model_name
            .as_deref()
            .unwrap_or(&self.config.embedding_model);
        let vector = Vector::from(query_vec.clone());
        let min_sim = if query.min_similarity > 0.0 {
            query.min_similarity
        } else {
            self.config.min_similarity
        };
        let limit = query.limit;

        // Build parameterized WHERE extras starting after $5
        let (where_extra, where_vals, next_idx) = build_search_where_extras(query, 6);
        let (edge_sql, edge_vals, _) = build_edge_filter_sql(&query.edge_filters, next_idx);

        let sql = format!(
            r#"
            SELECT n.id, n.namespace, n.node_key, n.node_type, n.content, n.content_type,
                   n.metadata, n.is_retracted, n.created_at, n.updated_at,
                   1 - (ne.embedding <=> $1::vector) AS similarity
            FROM nodes n
            JOIN node_embeddings ne ON ne.node_id = n.id
            WHERE n.namespace = ANY($2)
              AND n.is_retracted = FALSE
              AND ne.model_name = $3
              AND 1 - (ne.embedding <=> $1::vector) >= $4
              {where_extra}
              {edge_sql}
            ORDER BY ne.embedding <=> $1::vector
            LIMIT $5
            "#
        );

        let base_query = sqlx::query(&sql)
            .bind(&vector)
            .bind(&query.namespaces)
            .bind(model_name)
            .bind(min_sim)
            .bind(limit);

        let bound = bind_dyn_vals(base_query, &where_vals);
        let bound = bind_dyn_vals(bound, &edge_vals);

        let rows = bound.fetch_all(pool).await?;

        Ok(rows
            .iter()
            .map(|row| SearchResult {
                node: node_from_row(row),
                similarity: row.try_get::<f64, _>("similarity").unwrap_or(0.0),
                matched_by: vec!["vector".into()],
                edges: vec![],
            })
            .collect())
    }

    async fn search_text(&self, query: &SearchQuery) -> Result<Vec<SearchResult>> {
        let pool = self.pool()?;
        let text = query
            .text_query
            .as_deref()
            .ok_or_else(|| SmrtiError::Search("Text search requires text_query".into()))?;
        let language = &self.config.search_language;
        let limit = query.limit;

        // Build parameterized extras starting after $4
        let (where_extra, where_vals, next_idx) = build_search_where_extras(query, 5);
        let (edge_sql, edge_vals, _) = build_edge_filter_sql(&query.edge_filters, next_idx);

        // Primary: tsvector search using websearch_to_tsquery.
        let ts_sql = format!(
            r#"
            SELECT n.id, n.namespace, n.node_key, n.node_type, n.content, n.content_type,
                   n.metadata, n.is_retracted, n.created_at, n.updated_at,
                   ts_rank_cd(n.search_vector, websearch_to_tsquery($1::regconfig, $2)) AS similarity
            FROM nodes n
            WHERE n.namespace = ANY($3)
              AND n.is_retracted = FALSE
              AND n.search_vector @@ websearch_to_tsquery($1::regconfig, $2)
              {where_extra}
              {edge_sql}
            ORDER BY similarity DESC
            LIMIT $4
            "#
        );

        let base_query = sqlx::query(&ts_sql)
            .bind(language)
            .bind(text)
            .bind(&query.namespaces)
            .bind(limit);

        let bound = bind_dyn_vals(base_query, &where_vals);
        let bound = bind_dyn_vals(bound, &edge_vals);

        let ts_rows = bound.fetch_all(pool).await?;

        let mut results: Vec<SearchResult> = ts_rows
            .iter()
            .map(|row| SearchResult {
                node: node_from_row(row),
                similarity: row.try_get::<f32, _>("similarity").unwrap_or(0.0) as f64,
                matched_by: vec!["text".into()],
                edges: vec![],
            })
            .collect();

        // Issue 5: Check trigram fallback config before running trigram query.
        if (results.len() as i64) < limit && self.config.text_search_trigram_fallback {
            let remaining = limit - results.len() as i64;
            let found_ids: Vec<Uuid> = results.iter().map(|r| r.node.id).collect();

            // Build parameterized extras starting after $4
            let (trgm_where_extra, trgm_where_vals, trgm_next_idx) =
                build_search_where_extras(query, 5);
            let (trgm_edge_sql, trgm_edge_vals, _) =
                build_edge_filter_sql(&query.edge_filters, trgm_next_idx);

            let trgm_sql = format!(
                r#"
                SELECT n.id, n.namespace, n.node_key, n.node_type, n.content, n.content_type,
                       n.metadata, n.is_retracted, n.created_at, n.updated_at,
                       similarity(n.content, $1) AS sim
                FROM nodes n
                WHERE n.namespace = ANY($2)
                  AND n.is_retracted = FALSE
                  AND n.content % $1
                  AND n.id != ALL($3)
                  {trgm_where_extra}
                  {trgm_edge_sql}
                ORDER BY sim DESC
                LIMIT $4
                "#
            );

            let trgm_query = sqlx::query(&trgm_sql)
                .bind(text)
                .bind(&query.namespaces)
                .bind(&found_ids)
                .bind(remaining);

            let bound = bind_dyn_vals(trgm_query, &trgm_where_vals);
            let bound = bind_dyn_vals(bound, &trgm_edge_vals);

            let trgm_rows = bound.fetch_all(pool).await?;

            for row in &trgm_rows {
                results.push(SearchResult {
                    node: node_from_row(row),
                    similarity: row.try_get::<f32, _>("sim").unwrap_or(0.0) as f64,
                    matched_by: vec!["trigram".into()],
                    edges: vec![],
                });
            }
        }

        Ok(results)
    }

    async fn search_hybrid(&self, query: &SearchQuery) -> Result<Vec<SearchResult>> {
        let pool = self.pool()?;

        let query_vec = query
            .query_vector
            .as_ref()
            .ok_or_else(|| SmrtiError::Search("Hybrid search requires query_vector".into()))?;
        let text = query
            .text_query
            .as_deref()
            .ok_or_else(|| SmrtiError::Search("Hybrid search requires text_query".into()))?;
        let model_name = query
            .model_name
            .as_deref()
            .unwrap_or(&self.config.embedding_model);
        let vector = Vector::from(query_vec.clone());
        let language = &self.config.search_language;
        let rrf_k = self.config.rrf_k;
        let candidate_pool = self.config.hybrid_candidate_pool;
        let limit = query.limit;

        // Build parameterized extras starting after $8
        let (where_extra, where_vals, next_idx) = build_search_where_extras(query, 9);
        let (edge_sql, edge_vals, _) = build_edge_filter_sql(&query.edge_filters, next_idx);

        let sql = format!(
            r#"
            WITH vector_results AS (
                SELECT n.id,
                       1 - (ne.embedding <=> $1::vector) AS vector_sim,
                       ROW_NUMBER() OVER (ORDER BY ne.embedding <=> $1::vector) AS vector_rank
                FROM nodes n
                JOIN node_embeddings ne ON ne.node_id = n.id
                WHERE n.namespace = ANY($2)
                  AND n.is_retracted = FALSE
                  AND ne.model_name = $3
                  {where_extra}
                  {edge_sql}
                ORDER BY ne.embedding <=> $1::vector
                LIMIT $4
            ),
            text_results AS (
                SELECT n.id,
                       ts_rank_cd(n.search_vector, websearch_to_tsquery($5::regconfig, $6)) AS text_sim,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(n.search_vector, websearch_to_tsquery($5::regconfig, $6)) DESC
                       ) AS text_rank
                FROM nodes n
                WHERE n.namespace = ANY($2)
                  AND n.is_retracted = FALSE
                  AND n.search_vector @@ websearch_to_tsquery($5::regconfig, $6)
                  {where_extra}
                  {edge_sql}
                LIMIT $4
            ),
            rrf AS (
                SELECT
                    COALESCE(v.id, t.id) AS node_id,
                    COALESCE(1.0 / ($7 + v.vector_rank), 0) +
                    COALESCE(1.0 / ($7 + t.text_rank), 0) AS rrf_score,
                    COALESCE(v.vector_sim, 0) AS similarity,
                    CASE WHEN v.id IS NOT NULL AND t.id IS NOT NULL THEN TRUE
                         ELSE FALSE END AS both_matched
                FROM vector_results v
                FULL OUTER JOIN text_results t ON v.id = t.id
            )
            SELECT n.id, n.namespace, n.node_key, n.node_type, n.content, n.content_type,
                   n.metadata, n.is_retracted, n.created_at, n.updated_at,
                   rrf.similarity, rrf.rrf_score,
                   rrf.both_matched
            FROM rrf
            JOIN nodes n ON n.id = rrf.node_id
            ORDER BY rrf.rrf_score DESC
            LIMIT $8
            "#
        );

        let base_query = sqlx::query(&sql)
            .bind(&vector)
            .bind(&query.namespaces)
            .bind(model_name)
            .bind(candidate_pool)
            .bind(language)
            .bind(text)
            .bind(rrf_k)
            .bind(limit);

        let bound = bind_dyn_vals(base_query, &where_vals);
        let bound = bind_dyn_vals(bound, &edge_vals);

        let rows = bound.fetch_all(pool).await?;

        let mut results = Vec::with_capacity(rows.len());
        for row in &rows {
            let both: bool = row.try_get("both_matched").unwrap_or(false);
            let matched_by = if both {
                vec!["vector".into(), "text".into()]
            } else {
                vec!["hybrid".into()]
            };
            results.push(SearchResult {
                node: node_from_row(row),
                similarity: row.try_get::<f64, _>("similarity").unwrap_or(0.0),
                matched_by,
                edges: vec![],
            });
        }

        Ok(results)
    }
}

// ---------------------------------------------------------------------------
// StorageProvider implementation
// ---------------------------------------------------------------------------

#[async_trait]
impl super::StorageProvider for PostgresProvider {
    async fn connect(&mut self) -> Result<()> {
        self.config.validate()?;

        let pool = PgPoolOptions::new()
            .min_connections(self.config.pool_min)
            .max_connections(self.config.pool_max)
            .connect(&self.config.dsn)
            .await
            .map_err(|e| SmrtiError::Connection(format!("Failed to connect: {e}")))?;

        self.pool = Some(pool);
        info!("Connected to PostgreSQL");

        self.migrate().await?;
        Ok(())
    }

    async fn close(&mut self) -> Result<()> {
        if let Some(pool) = self.pool.take() {
            pool.close().await;
            info!("Connection pool closed");
        }
        Ok(())
    }

    async fn migrate(&self) -> Result<()> {
        let pool = self.pool()?;

        // Bootstrap smrti_meta (may not exist yet on fresh database).
        sqlx::query(
            "CREATE TABLE IF NOT EXISTS smrti_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        )
        .execute(pool)
        .await
        .map_err(|e| SmrtiError::Migration(format!("Failed to bootstrap smrti_meta: {e}")))?;

        // Check if v001 migration has been applied.
        let applied: Option<String> =
            sqlx::query_scalar("SELECT value FROM smrti_meta WHERE key = 'migration:v001_initial'")
                .fetch_optional(pool)
                .await
                .map_err(|e| SmrtiError::Migration(format!("Failed to check migrations: {e}")))?;

        if applied.is_none() {
            info!("Applying migration v001_initial");

            // The migration SQL contains function bodies with semicolons, so we
            // cannot naively split on ';'. Instead we split on semicolons that
            // are NOT inside $$ dollar-quoted blocks.
            for statement in split_sql_statements(V001_MIGRATION) {
                let trimmed = statement.trim();
                if trimmed.is_empty() {
                    continue;
                }
                // Skip pure comment blocks.
                let non_comment: String = trimmed
                    .lines()
                    .filter(|l| !l.trim().starts_with("--"))
                    .collect::<Vec<_>>()
                    .join("\n");
                if non_comment.trim().is_empty() {
                    continue;
                }

                sqlx::query(trimmed).execute(pool).await.map_err(|e| {
                    SmrtiError::Migration(format!(
                        "Migration v001 failed on statement: {e}\n---\n{trimmed}"
                    ))
                })?;
            }

            sqlx::query(
                "INSERT INTO smrti_meta (key, value) VALUES ('migration:v001_initial', 'applied')",
            )
            .execute(pool)
            .await
            .map_err(|e| SmrtiError::Migration(format!("Failed to record migration: {e}")))?;

            info!("Migration v001_initial applied successfully");
        }

        // v002: session state
        let v002_applied: Option<String> = sqlx::query_scalar(
            "SELECT value FROM smrti_meta WHERE key = 'migration:v002_session_state'",
        )
        .fetch_optional(pool)
        .await
        .map_err(|e| SmrtiError::Migration(format!("Failed to check migrations: {e}")))?;

        if v002_applied.is_none() {
            info!("Applying migration v002_session_state");
            for statement in split_sql_statements(V002_MIGRATION) {
                let trimmed = statement.trim();
                if trimmed.is_empty() {
                    continue;
                }
                sqlx::raw_sql(trimmed).execute(pool).await.map_err(|e| {
                    SmrtiError::Migration(format!(
                        "Migration v002 failed on statement: {e}\n---\n{trimmed}"
                    ))
                })?;
            }
            sqlx::query(
                "INSERT INTO smrti_meta (key, value) VALUES ('migration:v002_session_state', 'applied')",
            )
            .execute(pool)
            .await
            .map_err(|e| SmrtiError::Migration(format!("Failed to record migration: {e}")))?;

            info!("Migration v002_session_state applied successfully");
        }

        // Check/update search language if it differs from what is configured.
        let stored_lang: Option<String> =
            sqlx::query_scalar("SELECT value FROM smrti_meta WHERE key = 'search_language'")
                .fetch_optional(pool)
                .await?;

        let configured_lang = &self.config.search_language;
        let needs_update = match &stored_lang {
            Some(lang) => lang != configured_lang,
            None => configured_lang != "english",
        };

        if needs_update {
            info!(
                language = configured_lang.as_str(),
                "Updating search language trigger"
            );

            // The search language is used in a PL/pgSQL function body inside $$
            // dollar-quoting. It is not a user-supplied value (it comes from
            // server config), and there is no way to bind parameters inside
            // DDL/PL/pgSQL function definitions. We validate it is a safe
            // identifier to prevent injection.
            if !is_safe_identifier(configured_lang) {
                return Err(SmrtiError::Validation(format!(
                    "Unsafe search_language for trigger: '{configured_lang}'"
                )));
            }

            let trigger_fn = format!(
                r#"
                CREATE OR REPLACE FUNCTION smrti_nodes_search_vector_update() RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector := to_tsvector('{configured_lang}', NEW.content);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
                "#
            );
            sqlx::query(&trigger_fn).execute(pool).await.map_err(|e| {
                SmrtiError::Migration(format!("Failed to update search trigger: {e}"))
            })?;

            // Backfill existing tsvectors with the new language.
            // The language name is validated above via is_safe_identifier.
            let backfill = format!(
                "UPDATE nodes SET search_vector = to_tsvector('{configured_lang}', content)"
            );
            sqlx::query(&backfill).execute(pool).await.map_err(|e| {
                SmrtiError::Migration(format!("Failed to backfill search vectors: {e}"))
            })?;

            sqlx::query(
                "INSERT INTO smrti_meta (key, value) VALUES ('search_language', $1)
                 ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            )
            .bind(configured_lang)
            .execute(pool)
            .await?;

            info!("Search language updated to '{configured_lang}'");
        }

        Ok(())
    }

    async fn apply_event(&self, event: &Event) -> Result<i64> {
        let event = event.clone();
        let config = self.config.clone();

        let pool = self.pool()?.clone();
        let mut tx = pool.begin().await?;

        // Insert event into the append-only log.
        let event_id = insert_event_row(&mut tx, &event).await?;

        // Apply projection (free function -- no &self).
        apply_projection(&mut tx, &event, &config).await?;

        tx.commit().await?;

        debug!(event_id = event_id, event_type = %event.event_type, "Event applied");
        Ok(event_id)
    }

    /// Issue 2: Apply multiple events in a single transaction for atomicity.
    async fn apply_events_batch(&self, events: &[Event]) -> Result<Vec<i64>> {
        if events.is_empty() {
            return Ok(Vec::new());
        }

        let config = self.config.clone();
        let pool = self.pool()?.clone();
        let mut tx = pool.begin().await?;
        let mut ids = Vec::with_capacity(events.len());

        for event in events {
            let event = event.clone();
            let event_id = insert_event_row(&mut tx, &event).await?;
            apply_projection(&mut tx, &event, &config).await?;
            ids.push(event_id);
        }

        tx.commit().await?;
        Ok(ids)
    }

    async fn get_node(&self, node_id: Uuid) -> Result<Option<Node>> {
        let pool = self.pool()?;
        let row = sqlx::query_as::<_, NodeRow>(
            r#"
            SELECT id, namespace, node_key, node_type, content, content_type,
                   metadata, is_retracted, created_at, updated_at
            FROM nodes WHERE id = $1
            "#,
        )
        .bind(node_id)
        .fetch_optional(pool)
        .await?;

        Ok(row.map(Node::from))
    }

    async fn get_node_by_key(&self, namespace: &str, node_key: &str) -> Result<Option<Node>> {
        let pool = self.pool()?;
        let row = sqlx::query_as::<_, NodeRow>(
            r#"
            SELECT id, namespace, node_key, node_type, content, content_type,
                   metadata, is_retracted, created_at, updated_at
            FROM nodes
            WHERE namespace = $1 AND node_key = $2 AND is_retracted = FALSE
            "#,
        )
        .bind(namespace)
        .bind(node_key)
        .fetch_optional(pool)
        .await?;

        Ok(row.map(Node::from))
    }

    /// Issue 4: Atomic get_or_create with advisory lock for no-key path.
    async fn get_or_create_node(
        &self,
        namespace: &str,
        content: &str,
        node_type: &str,
        node_key: Option<&str>,
    ) -> Result<(Node, bool)> {
        let new_id = Uuid::new_v4();

        if let Some(key) = node_key {
            // Key path: ON CONFLICT DO NOTHING for atomicity.
            let pool = self.pool()?;
            let row = sqlx::query_as::<_, NodeRow>(
                r#"
                INSERT INTO nodes (id, namespace, node_key, node_type, content)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (namespace, node_key) WHERE node_key IS NOT NULL
                DO NOTHING
                RETURNING id, namespace, node_key, node_type, content, content_type,
                          metadata, is_retracted, created_at, updated_at
                "#,
            )
            .bind(new_id)
            .bind(namespace)
            .bind(key)
            .bind(node_type)
            .bind(content)
            .fetch_optional(pool)
            .await?;

            if let Some(r) = row {
                return Ok((Node::from(r), true));
            }

            // Already existed -- fetch it.
            let existing = sqlx::query_as::<_, NodeRow>(
                r#"
                SELECT id, namespace, node_key, node_type, content, content_type,
                       metadata, is_retracted, created_at, updated_at
                FROM nodes
                WHERE namespace = $1 AND node_key = $2
                "#,
            )
            .bind(namespace)
            .bind(key)
            .fetch_one(pool)
            .await?;

            Ok((Node::from(existing), false))
        } else {
            // No-key path: advisory lock + SELECT + INSERT in one transaction.
            let pool = self.pool()?.clone();
            let mut tx = pool.begin().await?;

            // Lock on hash of (namespace, content, node_type) for serialization.
            let lock_key: i64 = sqlx::query_scalar("SELECT hashtext($1 || $2 || $3)::bigint")
                .bind(namespace)
                .bind(content)
                .bind(node_type)
                .fetch_one(&mut *tx)
                .await?;

            sqlx::query("SELECT pg_advisory_xact_lock($1)")
                .bind(lock_key)
                .execute(&mut *tx)
                .await?;

            // Now safe: check if exists.
            let existing = sqlx::query_as::<_, NodeRow>(
                r#"
                SELECT id, namespace, node_key, node_type, content, content_type,
                       metadata, is_retracted, created_at, updated_at
                FROM nodes
                WHERE namespace = $1 AND node_type = $2 AND content = $3
                  AND is_retracted = FALSE
                LIMIT 1
                "#,
            )
            .bind(namespace)
            .bind(node_type)
            .bind(content)
            .fetch_optional(&mut *tx)
            .await?;

            if let Some(row) = existing {
                tx.commit().await?;
                return Ok((Node::from(row), false));
            }

            // Create new node.
            let row = sqlx::query_as::<_, NodeRow>(
                r#"
                INSERT INTO nodes (id, namespace, node_type, content)
                VALUES ($1, $2, $3, $4)
                RETURNING id, namespace, node_key, node_type, content, content_type,
                          metadata, is_retracted, created_at, updated_at
                "#,
            )
            .bind(new_id)
            .bind(namespace)
            .bind(node_type)
            .bind(content)
            .fetch_one(&mut *tx)
            .await?;

            tx.commit().await?;
            Ok((Node::from(row), true))
        }
    }

    async fn get_edges(
        &self,
        node_ids: &[Uuid],
        direction: Direction,
        edge_types: Option<&[String]>,
    ) -> Result<Vec<Edge>> {
        let pool = self.pool()?;

        let direction_clause = match direction {
            Direction::Outgoing => "source_node_id = ANY($1)",
            Direction::Incoming => "target_node_id = ANY($1)",
            Direction::Both => "(source_node_id = ANY($1) OR target_node_id = ANY($1))",
        };

        let type_clause = if edge_types.is_some() {
            " AND edge_type = ANY($2)"
        } else {
            ""
        };

        let sql = format!(
            r#"
            SELECT id, namespace, source_node_id, target_node_id, edge_type,
                   metadata, valid_from, valid_to, is_retracted, created_at
            FROM edges
            WHERE {direction_clause}
              AND is_retracted = FALSE
              AND valid_from <= NOW()
              AND (valid_to IS NULL OR valid_to >= NOW())
              {type_clause}
            ORDER BY created_at DESC
            "#
        );

        let rows = if let Some(types) = edge_types {
            sqlx::query_as::<_, EdgeRow>(&sql)
                .bind(node_ids)
                .bind(types)
                .fetch_all(pool)
                .await?
        } else {
            sqlx::query_as::<_, EdgeRow>(&sql)
                .bind(node_ids)
                .fetch_all(pool)
                .await?
        };

        Ok(rows.into_iter().map(Edge::from).collect())
    }

    async fn search_nodes(&self, query: &SearchQuery) -> Result<Vec<SearchResult>> {
        match query.mode.as_str() {
            "vector" => self.search_vector(query).await,
            "text" => self.search_text(query).await,
            "hybrid" => self.search_hybrid(query).await,
            other => Err(SmrtiError::Validation(format!(
                "Invalid search mode: '{other}'. Must be 'vector', 'text', or 'hybrid'."
            ))),
        }
    }

    /// Issue 3: Recursive CTE for graph traversal instead of Rust-side BFS.
    async fn traverse_graph(
        &self,
        start_node_id: Uuid,
        depth: u32,
        edge_types: Option<&[String]>,
        max_nodes: u32,
    ) -> Result<GraphResult> {
        let pool = self.pool()?;

        // Verify start node exists.
        let start_node =
            self.get_node(start_node_id)
                .await?
                .ok_or_else(|| SmrtiError::NodeNotFound {
                    node_id: start_node_id.to_string(),
                    namespace: "unknown".into(),
                })?;

        let effective_depth = depth.min(self.config.max_traversal_depth) as i32;
        let effective_max = max_nodes.min(self.config.max_traversal_nodes) as i64;

        // Build the recursive CTE. The optional edge_types filter uses ANY($4).
        let edge_type_filter = if edge_types.is_some() {
            "AND e.edge_type = ANY($4)"
        } else {
            ""
        };

        let sql = format!(
            r#"
            WITH RECURSIVE graph AS (
                SELECT e.id, e.source_node_id, e.target_node_id, e.edge_type,
                       e.metadata, e.namespace, e.valid_from, e.valid_to,
                       e.is_retracted, e.created_at, 1 AS depth
                FROM edges e
                WHERE e.source_node_id = $1
                  AND e.is_retracted = FALSE
                  AND e.valid_from <= NOW()
                  AND (e.valid_to IS NULL OR e.valid_to >= NOW())
                  {edge_type_filter}
                UNION ALL
                SELECT e.id, e.source_node_id, e.target_node_id, e.edge_type,
                       e.metadata, e.namespace, e.valid_from, e.valid_to,
                       e.is_retracted, e.created_at, g.depth + 1
                FROM edges e
                JOIN graph g ON e.source_node_id = g.target_node_id
                WHERE g.depth < $2
                  AND e.is_retracted = FALSE
                  AND e.valid_from <= NOW()
                  AND (e.valid_to IS NULL OR e.valid_to >= NOW())
                  {edge_type_filter}
            )
            SELECT DISTINCT ON (id) id, source_node_id, target_node_id, edge_type,
                   metadata, namespace, valid_from, valid_to, is_retracted, created_at
            FROM graph
            LIMIT $3
            "#
        );

        let edge_rows: Vec<EdgeRow> = if let Some(types) = edge_types {
            sqlx::query_as::<_, EdgeRow>(&sql)
                .bind(start_node_id)
                .bind(effective_depth)
                .bind(effective_max)
                .bind(types)
                .fetch_all(pool)
                .await?
        } else {
            sqlx::query_as::<_, EdgeRow>(&sql)
                .bind(start_node_id)
                .bind(effective_depth)
                .bind(effective_max)
                .fetch_all(pool)
                .await?
        };

        let edges: Vec<Edge> = edge_rows.into_iter().map(Edge::from).collect();

        // Collect all unique node IDs referenced by edges.
        let mut node_ids = std::collections::HashSet::new();
        node_ids.insert(start_node_id);
        for edge in &edges {
            node_ids.insert(edge.source_node_id);
            node_ids.insert(edge.target_node_id);
        }

        // Batch-fetch all referenced nodes.
        let node_id_vec: Vec<Uuid> = node_ids.into_iter().collect();
        let node_rows = sqlx::query_as::<_, NodeRow>(
            r#"
            SELECT id, namespace, node_key, node_type, content, content_type,
                   metadata, is_retracted, created_at, updated_at
            FROM nodes
            WHERE id = ANY($1) AND is_retracted = FALSE
            "#,
        )
        .bind(&node_id_vec)
        .fetch_all(pool)
        .await?;

        let mut nodes: Vec<Node> = node_rows.into_iter().map(Node::from).collect();

        // Ensure start node is present (even if retracted, it was explicitly requested).
        if !nodes.iter().any(|n| n.id == start_node_id) {
            nodes.insert(0, start_node);
        }

        // Cap nodes at effective_max.
        nodes.truncate(effective_max as usize);

        Ok(GraphResult { nodes, edges })
    }

    /// Issue 1: Fully parameterized aggregate_edges (no interpolation).
    async fn aggregate_edges(&self, query: &AggregateQuery) -> Result<AggregateResult> {
        let pool = self.pool()?;

        // Base conditions always present: $1 = edge_type, $2 = namespaces
        let mut conditions = vec![
            "e.edge_type = $1".to_string(),
            "e.namespace = ANY($2)".to_string(),
            "e.is_retracted = FALSE".to_string(),
        ];

        let mut dyn_vals: Vec<DynVal> = Vec::new();
        let mut next_idx: usize = 3;

        if let Some(ref at_time) = query.at_time {
            conditions.push(format!("e.valid_from <= ${next_idx}::timestamptz"));
            dyn_vals.push(DynVal::Timestamp(at_time.clone()));
            next_idx += 1;
            conditions.push(format!(
                "(e.valid_to IS NULL OR e.valid_to >= ${next_idx}::timestamptz)"
            ));
            dyn_vals.push(DynVal::Timestamp(at_time.clone()));
            next_idx += 1;
        } else {
            conditions.push("e.valid_from <= NOW()".into());
            conditions.push("(e.valid_to IS NULL OR e.valid_to >= NOW())".into());
        }

        if let Some(ref mf) = query.metadata_filter {
            conditions.push(format!("e.metadata @> ${next_idx}::jsonb"));
            dyn_vals.push(DynVal::Json(mf.clone()));
            next_idx += 1;
        }

        let where_sql = conditions.join(" AND ");

        if let Some(ref meta_key) = query.metadata_key {
            // Use a parameterized metadata key extraction via ->>
            let key_param = next_idx;
            dyn_vals.push(DynVal::Str(meta_key.clone()));
            // Note: we cannot parameterize the ->> key in standard SQL,
            // but we can use the jsonb_extract_path_text function with a bind param.
            let sql = format!(
                r#"
                SELECT
                    COUNT(*) AS cnt,
                    SUM((jsonb_extract_path_text(e.metadata, ${key_param}))::double precision) AS total,
                    AVG((jsonb_extract_path_text(e.metadata, ${key_param}))::double precision) AS average,
                    MIN((jsonb_extract_path_text(e.metadata, ${key_param}))::double precision) AS minimum,
                    MAX((jsonb_extract_path_text(e.metadata, ${key_param}))::double precision) AS maximum
                FROM edges e
                WHERE {where_sql}
                "#
            );

            let base_query = sqlx::query(&sql)
                .bind(&query.edge_type)
                .bind(&query.namespaces);
            let bound = bind_dyn_vals(base_query, &dyn_vals);

            let row = bound.fetch_one(pool).await?;

            Ok(AggregateResult {
                count: row.try_get::<i64, _>("cnt").unwrap_or(0),
                total: row.try_get::<Option<f64>, _>("total").unwrap_or(None),
                average: row.try_get::<Option<f64>, _>("average").unwrap_or(None),
                minimum: row.try_get::<Option<f64>, _>("minimum").unwrap_or(None),
                maximum: row.try_get::<Option<f64>, _>("maximum").unwrap_or(None),
            })
        } else {
            let sql = format!("SELECT COUNT(*) AS cnt FROM edges e WHERE {where_sql}");

            let base_query = sqlx::query(&sql)
                .bind(&query.edge_type)
                .bind(&query.namespaces);
            let bound = bind_dyn_vals(base_query, &dyn_vals);

            let row = bound.fetch_one(pool).await?;

            Ok(AggregateResult {
                count: row.try_get::<i64, _>("cnt").unwrap_or(0),
                total: None,
                average: None,
                minimum: None,
                maximum: None,
            })
        }
    }

    async fn get_events(
        &self,
        after_id: i64,
        namespace: Option<&str>,
        limit: i64,
    ) -> Result<Vec<Event>> {
        let pool = self.pool()?;
        let effective_limit = limit.min(self.config.max_events_export);

        let rows = if let Some(ns) = namespace {
            sqlx::query_as::<_, EventRow>(
                r#"
                SELECT id, namespace, event_type, payload, metadata, created_at
                FROM events
                WHERE id > $1 AND namespace = $2
                ORDER BY id ASC
                LIMIT $3
                "#,
            )
            .bind(after_id)
            .bind(ns)
            .bind(effective_limit)
            .fetch_all(pool)
            .await?
        } else {
            sqlx::query_as::<_, EventRow>(
                r#"
                SELECT id, namespace, event_type, payload, metadata, created_at
                FROM events
                WHERE id > $1
                ORDER BY id ASC
                LIMIT $2
                "#,
            )
            .bind(after_id)
            .bind(effective_limit)
            .fetch_all(pool)
            .await?
        };

        rows.into_iter().map(Event::try_from).collect()
    }

    async fn purge_namespace(&self, namespace: &str) -> Result<PurgeResult> {
        let pool = self.pool()?;

        if namespace.is_empty() {
            return Err(SmrtiError::Namespace("Cannot purge empty namespace".into()));
        }

        info!(namespace = namespace, "Purging namespace (GDPR)");

        // FK-safe delete order: session_state, edges, nodes (CASCADE embeddings), events.
        sqlx::query("DELETE FROM session_state WHERE namespace = $1")
            .bind(namespace)
            .execute(pool)
            .await?;

        let edges_deleted: i64 = sqlx::query_scalar(
            "WITH d AS (DELETE FROM edges WHERE namespace = $1 RETURNING 1) SELECT COUNT(*) FROM d",
        )
        .bind(namespace)
        .fetch_one(pool)
        .await?;

        let nodes_deleted: i64 = sqlx::query_scalar(
            "WITH d AS (DELETE FROM nodes WHERE namespace = $1 RETURNING 1) SELECT COUNT(*) FROM d",
        )
        .bind(namespace)
        .fetch_one(pool)
        .await?;

        let events_deleted: i64 = sqlx::query_scalar(
            "WITH d AS (DELETE FROM events WHERE namespace = $1 RETURNING 1) SELECT COUNT(*) FROM d",
        )
        .bind(namespace)
        .fetch_one(pool)
        .await?;

        // Write to GDPR audit log.
        sqlx::query(
            r#"
            INSERT INTO smrti_audit_log (action, namespace, details)
            VALUES ('PURGE_NAMESPACE', $1, $2::jsonb)
            "#,
        )
        .bind(namespace)
        .bind(json!({
            "events_deleted": events_deleted,
            "nodes_deleted": nodes_deleted,
            "edges_deleted": edges_deleted,
        }))
        .execute(pool)
        .await?;

        info!(
            namespace = namespace,
            events = events_deleted,
            nodes = nodes_deleted,
            edges = edges_deleted,
            "Namespace purged"
        );

        Ok(PurgeResult {
            events_deleted,
            nodes_deleted,
            edges_deleted,
        })
    }

    // ------------------------------------------------------------------ //
    // Session State (Working Memory)
    // ------------------------------------------------------------------ //

    async fn state_set(
        &self,
        namespace: &str,
        session_id: &str,
        key: &str,
        value: Value,
        ttl_seconds: Option<i64>,
    ) -> Result<()> {
        let pool = self.pool()?;
        sqlx::query(
            r#"
            INSERT INTO session_state (namespace, session_id, key, value, expires_at)
            VALUES ($1, $2, $3, $4, CASE WHEN $5::bigint IS NOT NULL THEN NOW() + ($5 || ' seconds')::interval ELSE NULL END)
            ON CONFLICT (namespace, session_id, key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = NOW(),
                          expires_at = EXCLUDED.expires_at
            "#,
        )
        .bind(namespace)
        .bind(session_id)
        .bind(key)
        .bind(&value)
        .bind(ttl_seconds)
        .execute(pool)
        .await?;
        Ok(())
    }

    async fn state_get(
        &self,
        namespace: &str,
        session_id: &str,
        key: &str,
    ) -> Result<Option<Value>> {
        let pool = self.pool()?;
        let row: Option<(Value,)> = sqlx::query_as(
            "SELECT value FROM session_state \
             WHERE namespace = $1 AND session_id = $2 AND key = $3 \
             AND (expires_at IS NULL OR expires_at > NOW())",
        )
        .bind(namespace)
        .bind(session_id)
        .bind(key)
        .fetch_optional(pool)
        .await?;
        Ok(row.map(|r| r.0))
    }

    async fn state_delete(&self, namespace: &str, session_id: &str, key: &str) -> Result<bool> {
        let pool = self.pool()?;
        let result = sqlx::query(
            "DELETE FROM session_state WHERE namespace = $1 AND session_id = $2 AND key = $3",
        )
        .bind(namespace)
        .bind(session_id)
        .bind(key)
        .execute(pool)
        .await?;
        Ok(result.rows_affected() > 0)
    }

    async fn state_clear(&self, namespace: &str, session_id: &str) -> Result<u64> {
        let pool = self.pool()?;
        let result =
            sqlx::query("DELETE FROM session_state WHERE namespace = $1 AND session_id = $2")
                .bind(namespace)
                .bind(session_id)
                .execute(pool)
                .await?;
        Ok(result.rows_affected())
    }

    async fn state_list(&self, namespace: &str, session_id: &str) -> Result<Vec<(String, Value)>> {
        let pool = self.pool()?;
        let rows: Vec<(String, Value)> = sqlx::query_as(
            "SELECT key, value FROM session_state \
             WHERE namespace = $1 AND session_id = $2 \
             AND (expires_at IS NULL OR expires_at > NOW()) \
             ORDER BY key",
        )
        .bind(namespace)
        .bind(session_id)
        .fetch_all(pool)
        .await?;
        Ok(rows)
    }

    async fn state_prune_expired(&self, namespace: Option<&str>) -> Result<u64> {
        let pool = self.pool()?;
        let result = if let Some(ns) = namespace {
            sqlx::query(
                "DELETE FROM session_state WHERE expires_at IS NOT NULL AND expires_at <= NOW() AND namespace = $1",
            )
            .bind(ns)
            .execute(pool)
            .await?
        } else {
            sqlx::query(
                "DELETE FROM session_state WHERE expires_at IS NOT NULL AND expires_at <= NOW()",
            )
            .execute(pool)
            .await?
        };
        Ok(result.rows_affected())
    }
}

// ---------------------------------------------------------------------------
// SQL statement splitter (handles $$ dollar-quoted function bodies)
// ---------------------------------------------------------------------------

/// Split SQL text into individual statements, respecting `$$` dollar-quoted
/// blocks and `--` line comments so that semicolons inside PL/pgSQL function
/// bodies or comments are not treated as statement terminators.
fn split_sql_statements(sql: &str) -> Vec<&str> {
    let mut statements = Vec::new();
    let mut start = 0;
    let mut in_dollar_quote = false;
    let bytes = sql.as_bytes();
    let len = bytes.len();
    let mut i = 0;

    while i < len {
        // Skip -- line comments (semicolons in comments are not terminators)
        if !in_dollar_quote && i + 1 < len && bytes[i] == b'-' && bytes[i + 1] == b'-' {
            while i < len && bytes[i] != b'\n' {
                i += 1;
            }
            continue;
        }
        if i + 1 < len && bytes[i] == b'$' && bytes[i + 1] == b'$' {
            in_dollar_quote = !in_dollar_quote;
            i += 2;
        } else if bytes[i] == b';' && !in_dollar_quote {
            let stmt = sql[start..i].trim();
            if !stmt.is_empty() {
                statements.push(stmt);
            }
            start = i + 1;
            i += 1;
        } else {
            i += 1;
        }
    }

    // Trailing content after last semicolon.
    let trailing = sql[start..].trim();
    if !trailing.is_empty() {
        statements.push(trailing);
    }

    statements
}
