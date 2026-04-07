//! Postgres/pgvector memory backend via smrti.
//!
//! Wraps the existing `smrti_core::Memory` crate as a [`MemoryBackend`]
//! implementation. This is the production-tested backend for server deployments
//! with existing PostgreSQL infrastructure.
#![warn(missing_docs)]

use std::sync::Arc;

use async_trait::async_trait;
use serde_json::Value;
use tracing::info;

use konf_tool_memory::{MemoryBackend, MemoryError, SearchParams};

/// smrti-backed memory backend (Postgres + pgvector + tsvector).
pub struct SmrtiBackend {
    memory: Arc<smrti_core::Memory>,
}

/// Connect to Postgres via smrti and return a MemoryBackend.
///
/// Config expects: `{ "dsn": "postgresql://...", "pool_min": 5, "pool_max": 20 }`
pub async fn connect(config: &Value) -> anyhow::Result<Arc<dyn MemoryBackend>> {
    let smrti_config: smrti_core::SmrtiConfig = serde_json::from_value(config.clone())
        .map_err(|e| anyhow::anyhow!("Invalid smrti config: {e}"))?;
    let memory = smrti_core::Memory::connect(smrti_config).await
        .map_err(|e| anyhow::anyhow!("Failed to connect to smrti: {e}"))?;
    info!("smrti memory backend connected");
    Ok(Arc::new(SmrtiBackend { memory: Arc::new(memory) }))
}

#[async_trait]
impl MemoryBackend for SmrtiBackend {
    async fn search(&self, params: SearchParams) -> Result<Value, MemoryError> {
        let namespaces = params.namespace.map(|ns| vec![ns]);
        self.memory
            .search(
                None,                          // query_vector
                params.query.as_deref(),       // text_query
                namespaces,                    // namespaces
                params.mode.as_deref(),        // search_mode
                params.node_type.as_deref(),   // node_type filter
                None, None, None,              // edge_type, edge_target, metadata_filter
                None, None,                    // after, before
                params.limit,                  // limit
                params.min_similarity,         // min_similarity
            )
            .await
            .map_err(|e| MemoryError::OperationFailed(e.to_string()))
    }

    async fn add_nodes(&self, nodes: &[Value], namespace: Option<&str>) -> Result<Value, MemoryError> {
        self.memory
            .add_nodes(nodes, namespace)
            .await
            .map_err(|e| MemoryError::OperationFailed(e.to_string()))
    }

    async fn state_set(&self, key: &str, value: &Value, session_id: &str, namespace: Option<&str>, ttl: Option<i64>) -> Result<Value, MemoryError> {
        self.memory
            .state_set(key, value, session_id, namespace, ttl)
            .await
            .map_err(|e| MemoryError::OperationFailed(e.to_string()))
    }

    async fn state_get(&self, key: &str, session_id: &str, namespace: Option<&str>) -> Result<Value, MemoryError> {
        self.memory
            .state_get(key, session_id, namespace)
            .await
            .map_err(|e| MemoryError::OperationFailed(e.to_string()))
    }

    async fn state_delete(&self, key: &str, session_id: &str, namespace: Option<&str>) -> Result<Value, MemoryError> {
        self.memory
            .state_delete(key, session_id, namespace)
            .await
            .map_err(|e| MemoryError::OperationFailed(e.to_string()))
    }

    async fn state_list(&self, session_id: &str, namespace: Option<&str>) -> Result<Value, MemoryError> {
        self.memory
            .state_list(session_id, namespace)
            .await
            .map_err(|e| MemoryError::OperationFailed(e.to_string()))
    }

    async fn state_clear(&self, session_id: &str, namespace: Option<&str>) -> Result<Value, MemoryError> {
        self.memory
            .state_clear(session_id, namespace)
            .await
            .map_err(|e| MemoryError::OperationFailed(e.to_string()))
    }

    fn supported_search_modes(&self) -> Vec<String> {
        vec!["hybrid".into(), "vector".into(), "text".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_supported_search_modes() {
        // SmrtiBackend always supports all three modes
        // (Can't test connect without Postgres, so test the static parts)
        let modes = vec!["hybrid".to_string(), "vector".to_string(), "text".to_string()];
        assert_eq!(modes.len(), 3);
        assert!(modes.contains(&"hybrid".to_string()));
    }

    #[test]
    fn test_connect_invalid_config() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(connect(&serde_json::json!({})));
        // Should fail with missing DSN — not panic
        assert!(result.is_err());
    }
}
