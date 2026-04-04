// PyO3's #[pymethods] macro generates .into() calls that clippy flags as useless.
#![allow(clippy::useless_conversion)]

//! Python bindings for smrti — graph-based memory for AI agents.
//!
//! This is a THIN wrapper over `smrti-core`. Zero business logic.
//! All methods: convert Python types → Rust, call smrti-core, convert back.
//!
//! Uses sync Python API with `block_on` + `allow_threads` (same pattern
//! as Polars, pydantic-core, cryptography).

use std::sync::LazyLock;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use pythonize::{depythonize, pythonize};
use serde_json::Value;
use tokio::runtime::Runtime;

// Shared tokio runtime for all blocking calls.
static RUNTIME: LazyLock<Runtime> =
    LazyLock::new(|| Runtime::new().expect("Failed to create tokio runtime"));

/// Convert SmrtiError to Python exception.
fn to_py_err(e: smrti_core::SmrtiError) -> PyErr {
    // Map specific variants to appropriate Python exception types
    match &e {
        smrti_core::SmrtiError::Validation(_) => PyValueError::new_err(e.to_string()),
        _ => PyRuntimeError::new_err(e.to_string()),
    }
}

/// Convert serde_json::Value to Python object.
fn value_to_py(py: Python<'_>, val: &Value) -> PyResult<PyObject> {
    let bound = pythonize(py, val)
        .map_err(|e| PyRuntimeError::new_err(format!("Serialization error: {e}")))?;
    Ok(bound.into())
}

/// Convert Python object to serde_json::Value.
fn py_to_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    depythonize(obj).map_err(|e| PyValueError::new_err(format!("Invalid value: {e}")))
}

/// The main Memory class exposed to Python.
///
/// Usage:
///     from smrti import Memory
///     memory = Memory.connect("postgresql://localhost/mydb")
///     result = memory.add_nodes([{"node_type": "person", "content": "Alice"}])
#[pyclass]
struct Memory {
    inner: smrti_core::Memory,
}

#[pymethods]
impl Memory {
    /// Connect to the database and return a ready Memory instance.
    ///
    /// Args:
    ///     dsn: PostgreSQL connection string
    ///     **kwargs: Additional SmrtiConfig fields (search_mode, search_limit, etc.)
    #[staticmethod]
    #[pyo3(signature = (dsn, **kwargs))]
    fn connect(py: Python<'_>, dsn: &str, kwargs: Option<&Bound<'_, PyDict>>) -> PyResult<Self> {
        let mut config_map = serde_json::Map::new();
        config_map.insert("dsn".into(), Value::String(dsn.into()));

        if let Some(kw) = kwargs {
            for (key, val) in kw.iter() {
                let k: String = key.extract()?;
                let v = py_to_value(&val)?;
                config_map.insert(k, v);
            }
        }

        let config: smrti_core::SmrtiConfig = serde_json::from_value(Value::Object(config_map))
            .map_err(|e| PyValueError::new_err(format!("Invalid config: {e}")))?;

        let inner = py
            .allow_threads(|| RUNTIME.block_on(smrti_core::Memory::connect(config)))
            .map_err(to_py_err)?;

        Ok(Memory { inner })
    }

    /// Close the database connection.
    fn close(&mut self, py: Python<'_>) -> PyResult<()> {
        py.allow_threads(|| RUNTIME.block_on(self.inner.close()))
            .map_err(to_py_err)
    }

    // ------------------------------------------------------------------ //
    // Write
    // ------------------------------------------------------------------ //

    /// Add nodes to the knowledge graph.
    ///
    /// Args:
    ///     nodes: List of dicts with node_type, content, and optionally
    ///            node_key, content_type, metadata, embedding, model_name.
    ///     namespace: Optional namespace (default from config).
    ///
    /// Returns: dict with node_ids and _meta.
    #[pyo3(signature = (nodes, namespace=None))]
    fn add_nodes(
        &self,
        py: Python<'_>,
        nodes: &Bound<'_, PyAny>,
        namespace: Option<&str>,
    ) -> PyResult<PyObject> {
        let nodes_val: Vec<Value> = depythonize(nodes)?;
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.add_nodes(&nodes_val, namespace)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Add edges to the knowledge graph.
    #[pyo3(signature = (edges, namespace=None))]
    fn add_edges(
        &self,
        py: Python<'_>,
        edges: &Bound<'_, PyAny>,
        namespace: Option<&str>,
    ) -> PyResult<PyObject> {
        let edges_val: Vec<Value> = depythonize(edges)?;
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.add_edges(&edges_val, namespace)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Get or create a node atomically.
    #[pyo3(signature = (content, node_type, node_key=None, namespace=None))]
    fn get_or_create(
        &self,
        py: Python<'_>,
        content: &str,
        node_type: &str,
        node_key: Option<&str>,
        namespace: Option<&str>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(
                    self.inner
                        .get_or_create(content, node_type, node_key, namespace),
                )
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Update a node's content, metadata, or type.
    #[pyo3(signature = (node_id, content=None, metadata=None, node_type=None))]
    fn update_node(
        &self,
        py: Python<'_>,
        node_id: &str,
        content: Option<&str>,
        metadata: Option<&Bound<'_, PyAny>>,
        node_type: Option<&str>,
    ) -> PyResult<PyObject> {
        let meta_val: Option<Value> = metadata.map(|m| py_to_value(m)).transpose()?;
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(self.inner.update_node(
                    node_id,
                    content,
                    meta_val.as_ref(),
                    node_type,
                ))
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Soft-delete a node.
    fn retract_node(&self, py: Python<'_>, node_id: &str) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.retract_node(node_id)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Soft-delete an edge.
    fn retract_edge(&self, py: Python<'_>, edge_id: &str) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.retract_edge(edge_id)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Merge two nodes.
    fn merge_nodes(&self, py: Python<'_>, keep_id: &str, remove_id: &str) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.merge_nodes(keep_id, remove_id)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    // ------------------------------------------------------------------ //
    // Search
    // ------------------------------------------------------------------ //

    /// Search the knowledge graph.
    ///
    /// Args:
    ///     query_vector: Pre-computed embedding (list of floats). Required for vector/hybrid.
    ///     text_query: Text to search for. Required for text/hybrid.
    ///     namespaces: List of namespaces to search (default from config).
    ///     mode: "vector", "text", or "hybrid" (default from config).
    ///     node_type: Filter to specific node type.
    ///     edge_type: Filter to nodes with this edge type.
    ///     edge_target: Filter to nodes connected to this target.
    ///     metadata_filter: JSONB containment filter (dict).
    ///     after: ISO date string — only nodes created after this.
    ///     before: ISO date string — only nodes created before this.
    ///     limit: Max results.
    ///     min_similarity: Minimum similarity threshold (0.0-1.0).
    ///
    /// Returns: dict with results and _meta.
    #[pyo3(signature = (
        query_vector=None, text_query=None, namespaces=None, mode=None,
        node_type=None, edge_type=None, edge_target=None,
        metadata_filter=None, after=None, before=None,
        limit=None, min_similarity=None
    ))]
    #[allow(clippy::too_many_arguments)]
    fn search(
        &self,
        py: Python<'_>,
        query_vector: Option<Vec<f32>>,
        text_query: Option<&str>,
        namespaces: Option<Vec<String>>,
        mode: Option<&str>,
        node_type: Option<&str>,
        edge_type: Option<&str>,
        edge_target: Option<&str>,
        metadata_filter: Option<&Bound<'_, PyAny>>,
        after: Option<&str>,
        before: Option<&str>,
        limit: Option<i64>,
        min_similarity: Option<f64>,
    ) -> PyResult<PyObject> {
        let mf: Option<Value> = metadata_filter.map(|m| py_to_value(m)).transpose()?;
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(self.inner.search(
                    query_vector,
                    text_query,
                    namespaces,
                    mode,
                    node_type,
                    edge_type,
                    edge_target,
                    mf.as_ref(),
                    after,
                    before,
                    limit,
                    min_similarity,
                ))
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Traverse the graph from a starting node.
    #[pyo3(signature = (node_id, depth=None, edge_types=None, max_nodes=None))]
    fn traverse(
        &self,
        py: Python<'_>,
        node_id: &str,
        depth: Option<u32>,
        edge_types: Option<&str>,
        max_nodes: Option<u32>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(self.inner.traverse(node_id, depth, edge_types, max_nodes))
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Aggregate over edges.
    #[pyo3(signature = (edge_type, namespace=None, metadata_key=None, filters=None, at_time=None))]
    fn aggregate(
        &self,
        py: Python<'_>,
        edge_type: &str,
        namespace: Option<&str>,
        metadata_key: Option<&str>,
        filters: Option<&Bound<'_, PyAny>>,
        at_time: Option<&str>,
    ) -> PyResult<PyObject> {
        let f: Option<Value> = filters.map(|m| py_to_value(m)).transpose()?;
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(self.inner.aggregate(
                    edge_type,
                    namespace,
                    metadata_key,
                    f.as_ref(),
                    at_time,
                ))
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Get edges for a node.
    #[pyo3(signature = (node_id, direction=None, edge_types=None))]
    fn get_edges(
        &self,
        py: Python<'_>,
        node_id: &str,
        direction: Option<&str>,
        edge_types: Option<&str>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(self.inner.get_edges(node_id, direction, edge_types))
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    // ------------------------------------------------------------------ //
    // Session State
    // ------------------------------------------------------------------ //

    /// Set a session state key-value pair.
    #[pyo3(signature = (key, value, session_id, namespace=None, ttl_seconds=None))]
    fn state_set(
        &self,
        py: Python<'_>,
        key: &str,
        value: &Bound<'_, PyAny>,
        session_id: &str,
        namespace: Option<&str>,
        ttl_seconds: Option<i64>,
    ) -> PyResult<PyObject> {
        let val = py_to_value(value)?;
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(self.inner.state_set(
                    key,
                    &val,
                    session_id,
                    namespace,
                    ttl_seconds,
                ))
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Get a session state value.
    #[pyo3(signature = (key, session_id, namespace=None))]
    fn state_get(
        &self,
        py: Python<'_>,
        key: &str,
        session_id: &str,
        namespace: Option<&str>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.state_get(key, session_id, namespace)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Delete a session state key.
    #[pyo3(signature = (key, session_id, namespace=None))]
    fn state_delete(
        &self,
        py: Python<'_>,
        key: &str,
        session_id: &str,
        namespace: Option<&str>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.state_delete(key, session_id, namespace)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Clear all session state for a session.
    #[pyo3(signature = (session_id, namespace=None))]
    fn state_clear(
        &self,
        py: Python<'_>,
        session_id: &str,
        namespace: Option<&str>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.state_clear(session_id, namespace)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// List all session state keys.
    #[pyo3(signature = (session_id, namespace=None))]
    fn state_list(
        &self,
        py: Python<'_>,
        session_id: &str,
        namespace: Option<&str>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.state_list(session_id, namespace)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    // ------------------------------------------------------------------ //
    // Import/Export
    // ------------------------------------------------------------------ //

    /// Export events from the log.
    #[pyo3(signature = (after_id=None, namespace=None, limit=None))]
    fn export_events(
        &self,
        py: Python<'_>,
        after_id: Option<i64>,
        namespace: Option<&str>,
        limit: Option<i64>,
    ) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| {
                RUNTIME.block_on(self.inner.export_events(after_id, namespace, limit))
            })
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    /// Import events by replaying them.
    fn import_events(&self, py: Python<'_>, events: &Bound<'_, PyAny>) -> PyResult<PyObject> {
        let events_val: Vec<Value> = depythonize(events)?;
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.import_events(&events_val)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }

    // ------------------------------------------------------------------ //
    // GDPR
    // ------------------------------------------------------------------ //

    /// Physically delete all data for a namespace.
    fn purge_namespace(&self, py: Python<'_>, namespace: &str) -> PyResult<PyObject> {
        let result = py
            .allow_threads(|| RUNTIME.block_on(self.inner.purge_namespace(namespace)))
            .map_err(to_py_err)?;
        value_to_py(py, &result)
    }
}

/// smrti Python module.
#[pymodule]
fn smrti(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Memory>()?;
    Ok(())
}
