//! Configuration for smrti.
//!
//! Every parameter has a documented default. All values are validated
//! before use. Config can be loaded from code, TOML files, or
//! environment variables via `figment`.

use crate::error::{Result, SmrtiError};
use serde::Deserialize;

/// Configuration for a smrti Memory instance.
///
/// All parameters have sensible defaults except `dsn` (required).
/// Use `SmrtiConfig::validate()` after construction to check all invariants.
#[derive(Debug, Clone, Deserialize)]
pub struct SmrtiConfig {
    // === Required ===
    /// PostgreSQL connection string.
    /// Example: `"postgresql://user:pass@localhost:5432/mydb"`
    pub dsn: String,

    // === Namespacing ===
    /// Namespace used when none is specified in API calls.
    #[serde(default = "default_namespace")]
    pub default_namespace: String,

    // === Connection Pool ===
    /// Minimum connections in the sqlx pool.
    #[serde(default = "default_pool_min")]
    pub pool_min: u32,

    /// Maximum connections in the sqlx pool.
    #[serde(default = "default_pool_max")]
    pub pool_max: u32,

    // === Search ===
    /// Default number of results for search operations.
    #[serde(default = "default_search_limit")]
    pub search_limit: i64,

    /// Default minimum cosine similarity threshold (0.0-1.0).
    #[serde(default)]
    pub min_similarity: f64,

    /// Default search mode: "vector", "text", or "hybrid".
    #[serde(default = "default_search_mode")]
    pub search_mode: String,

    /// PostgreSQL text search configuration name.
    /// Used in `to_tsvector()` and `websearch_to_tsquery()`.
    #[serde(default = "default_search_language")]
    pub search_language: String,

    /// Reciprocal Rank Fusion constant. Higher values smooth rank differences.
    #[serde(default = "default_rrf_k")]
    pub rrf_k: i64,

    /// Candidates fetched from each search mode before RRF fusion.
    #[serde(default = "default_hybrid_candidate_pool")]
    pub hybrid_candidate_pool: i64,

    /// Whether to fall back to trigram similarity when full-text search
    /// returns no results. Disable for high-volume namespaces where
    /// trigram index maintenance cost is prohibitive.
    #[serde(default = "default_text_search_trigram_fallback")]
    pub text_search_trigram_fallback: bool,

    // === Traversal ===
    /// Maximum allowed depth for graph traversal.
    #[serde(default = "default_max_traversal_depth")]
    pub max_traversal_depth: u32,

    /// Maximum nodes returned from a traversal.
    #[serde(default = "default_max_traversal_nodes")]
    pub max_traversal_nodes: u32,

    // === Events ===
    /// Maximum events returned by `export_events()` in a single call.
    #[serde(default = "default_max_events_export")]
    pub max_events_export: i64,

    // === pgvector ===
    /// HNSW index: max connections per node. Higher = better recall, more memory.
    #[serde(default = "default_hnsw_m")]
    pub hnsw_m: u32,

    /// HNSW index: build-time search width. Higher = better recall, slower build.
    #[serde(default = "default_hnsw_ef_construction")]
    pub hnsw_ef_construction: u32,

    /// Vector distance metric: "cosine", "l2", or "inner_product".
    #[serde(default = "default_distance_metric")]
    pub distance_metric: String,

    // === Embedding ===
    /// Default model name stored in node_embeddings.model_name.
    #[serde(default = "default_embedding_model")]
    pub embedding_model: String,

    // === Session State ===
    /// Default TTL for session state entries (seconds). None = no expiry.
    #[serde(default)]
    pub session_state_default_ttl: Option<i64>,
}

impl SmrtiConfig {
    /// Validate all configuration invariants.
    ///
    /// Returns `Err(SmrtiError::Validation)` with a descriptive message
    /// if any field is invalid.
    pub fn validate(&self) -> Result<()> {
        if !self.dsn.starts_with("postgresql://") && !self.dsn.starts_with("postgres://") {
            return Err(SmrtiError::Validation(
                "dsn must start with 'postgresql://' or 'postgres://'".into(),
            ));
        }
        if self.default_namespace.is_empty() {
            return Err(SmrtiError::Validation(
                "default_namespace must not be empty".into(),
            ));
        }
        if self.pool_min < 1 {
            return Err(SmrtiError::Validation("pool_min must be >= 1".into()));
        }
        if self.pool_max < self.pool_min {
            return Err(SmrtiError::Validation(format!(
                "pool_max ({}) must be >= pool_min ({})",
                self.pool_max, self.pool_min
            )));
        }
        if self.search_limit < 1 {
            return Err(SmrtiError::Validation("search_limit must be >= 1".into()));
        }
        if !(0.0..=1.0).contains(&self.min_similarity) {
            return Err(SmrtiError::Validation(format!(
                "min_similarity must be 0.0-1.0, got {}",
                self.min_similarity
            )));
        }
        if !["vector", "text", "hybrid"].contains(&self.search_mode.as_str()) {
            return Err(SmrtiError::Validation(format!(
                "search_mode must be 'vector', 'text', or 'hybrid', got '{}'",
                self.search_mode
            )));
        }
        if self.rrf_k < 1 {
            return Err(SmrtiError::Validation("rrf_k must be >= 1".into()));
        }
        if self.hybrid_candidate_pool < 10 {
            return Err(SmrtiError::Validation(
                "hybrid_candidate_pool must be >= 10".into(),
            ));
        }
        if self.max_traversal_depth < 1 {
            return Err(SmrtiError::Validation(
                "max_traversal_depth must be >= 1".into(),
            ));
        }
        if self.max_traversal_nodes < 1 {
            return Err(SmrtiError::Validation(
                "max_traversal_nodes must be >= 1".into(),
            ));
        }
        if self.hnsw_m < 2 {
            return Err(SmrtiError::Validation("hnsw_m must be >= 2".into()));
        }
        if self.hnsw_ef_construction < 16 {
            return Err(SmrtiError::Validation(
                "hnsw_ef_construction must be >= 16".into(),
            ));
        }
        if !["cosine", "l2", "inner_product"].contains(&self.distance_metric.as_str()) {
            return Err(SmrtiError::Validation(format!(
                "distance_metric must be 'cosine', 'l2', or 'inner_product', got '{}'",
                self.distance_metric
            )));
        }
        Ok(())
    }
}

// === Default functions ===

fn default_namespace() -> String {
    "default".into()
}
fn default_pool_min() -> u32 {
    2
}
fn default_pool_max() -> u32 {
    10
}
fn default_search_limit() -> i64 {
    10
}
fn default_search_mode() -> String {
    "hybrid".into()
}
fn default_search_language() -> String {
    "english".into()
}
fn default_rrf_k() -> i64 {
    60
}
fn default_hybrid_candidate_pool() -> i64 {
    100
}
fn default_max_traversal_depth() -> u32 {
    5
}
fn default_max_traversal_nodes() -> u32 {
    100
}
fn default_max_events_export() -> i64 {
    10000
}
fn default_hnsw_m() -> u32 {
    16
}
fn default_hnsw_ef_construction() -> u32 {
    64
}
fn default_distance_metric() -> String {
    "cosine".into()
}
fn default_embedding_model() -> String {
    "default".into()
}
fn default_text_search_trigram_fallback() -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_config() -> SmrtiConfig {
        serde_json::from_str(r#"{"dsn": "postgresql://localhost/test"}"#).unwrap()
    }

    #[test]
    fn test_defaults() {
        let config = valid_config();
        assert_eq!(config.default_namespace, "default");
        assert_eq!(config.pool_min, 2);
        assert_eq!(config.pool_max, 10);
        assert_eq!(config.search_limit, 10);
        assert_eq!(config.min_similarity, 0.0);
        assert_eq!(config.search_mode, "hybrid");
        assert_eq!(config.search_language, "english");
        assert_eq!(config.rrf_k, 60);
        assert_eq!(config.hybrid_candidate_pool, 100);
        assert_eq!(config.max_traversal_depth, 5);
        assert_eq!(config.max_traversal_nodes, 100);
        assert_eq!(config.max_events_export, 10000);
        assert_eq!(config.hnsw_m, 16);
        assert_eq!(config.hnsw_ef_construction, 64);
        assert_eq!(config.distance_metric, "cosine");
        assert_eq!(config.embedding_model, "default");
        assert!(config.text_search_trigram_fallback);
    }

    #[test]
    fn test_validation_passes() {
        let config = valid_config();
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_invalid_dsn() {
        let config: SmrtiConfig =
            serde_json::from_str(r#"{"dsn": "mysql://localhost/test"}"#).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.to_string().contains("dsn must start with"));
    }

    #[test]
    fn test_invalid_search_mode() {
        let config: SmrtiConfig = serde_json::from_str(
            r#"{"dsn": "postgresql://localhost/test", "search_mode": "invalid"}"#,
        )
        .unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.to_string().contains("search_mode must be"));
    }

    #[test]
    fn test_invalid_distance_metric() {
        let config: SmrtiConfig = serde_json::from_str(
            r#"{"dsn": "postgresql://localhost/test", "distance_metric": "hamming"}"#,
        )
        .unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.to_string().contains("distance_metric must be"));
    }

    #[test]
    fn test_pool_max_lt_min() {
        let config: SmrtiConfig = serde_json::from_str(
            r#"{"dsn": "postgresql://localhost/test", "pool_min": 5, "pool_max": 2}"#,
        )
        .unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.to_string().contains("pool_max"));
    }

    #[test]
    fn test_similarity_out_of_range() {
        let config: SmrtiConfig = serde_json::from_str(
            r#"{"dsn": "postgresql://localhost/test", "min_similarity": 1.5}"#,
        )
        .unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.to_string().contains("min_similarity"));
    }
}
