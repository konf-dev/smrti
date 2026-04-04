//! Error types for smrti.
//!
//! All errors include context in their messages so LLMs and developers
//! can understand what went wrong and what to try next.

/// The primary error type for all smrti operations.
#[derive(Debug, thiserror::Error)]
pub enum SmrtiError {
    /// Failed to connect to the database.
    #[error("Connection failed: {0}")]
    Connection(String),

    /// Failed to apply a database migration.
    #[error("Migration failed: {0}")]
    Migration(String),

    /// Failed to apply an event to the event log or projection.
    #[error("Event error: {0}")]
    Event(String),

    /// The requested node was not found.
    #[error("Node '{node_id}' not found in namespace '{namespace}'")]
    NodeNotFound { node_id: String, namespace: String },

    /// The requested edge was not found.
    #[error("Edge '{edge_id}' not found")]
    EdgeNotFound { edge_id: String },

    /// Input validation failed. Check the message for details.
    #[error("Validation error: {0}")]
    Validation(String),

    /// Search operation failed.
    #[error("Search error: {0}")]
    Search(String),

    /// Embedding dimension mismatch or invalid embedding data.
    #[error("Embedding error: {0}")]
    Embedding(String),

    /// Namespace-related error (e.g., empty namespace).
    #[error("Namespace error: {0}")]
    Namespace(String),

    /// Underlying database error from sqlx.
    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),
}

/// Convenience type alias.
pub type Result<T> = std::result::Result<T, SmrtiError>;
