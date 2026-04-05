//! Integration tests for PostgresProvider.
//!
//! Requires Docker running with the pgvector/pgvector:pg17 image available.
//! Uses ONE shared container for all tests. Each test uses a unique namespace
//! for isolation instead of data cleanup.

use serde_json::json;
use smrti_core::config::SmrtiConfig;
use smrti_core::events::{Event, EventType};
use smrti_core::models::{AggregateQuery, SearchQuery};
use smrti_core::provider::postgres::PostgresProvider;
use smrti_core::provider::{Direction, StorageProvider};
use testcontainers::runners::AsyncRunner;
use testcontainers::{GenericImage, ImageExt};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Shared container (started once, reused by all tests)
// ---------------------------------------------------------------------------

/// Shared DSN + migration (run exactly once).
static SETUP: tokio::sync::OnceCell<String> = tokio::sync::OnceCell::const_new();

/// Ensure container is running AND migrations are applied. Returns DSN.
async fn ensure_setup() -> &'static str {
    SETUP
        .get_or_init(|| async {
            let image = GenericImage::new("pgvector/pgvector", "pg17")
                .with_wait_for(testcontainers::core::WaitFor::message_on_stderr(
                    "database system is ready to accept connections",
                ))
                .with_exposed_port(testcontainers::core::ContainerPort::Tcp(5432))
                .with_env_var("POSTGRES_USER", "test")
                .with_env_var("POSTGRES_PASSWORD", "test")
                .with_env_var("POSTGRES_DB", "smrti_test");

            let container = image
                .start()
                .await
                .expect("Failed to start pgvector container");

            let port = container.get_host_port_ipv4(5432).await.unwrap();
            let dsn = format!("postgresql://test:test@127.0.0.1:{port}/smrti_test");

            // Leak so container lives for entire test process
            std::mem::forget(container);

            // Run migration exactly once — prevents concurrent CREATE EXTENSION races
            let config: SmrtiConfig = serde_json::from_value(json!({
                "dsn": &dsn,
                "pool_min": 1,
                "pool_max": 2,
            }))
            .unwrap();
            let mut provider = PostgresProvider::new(config);
            provider
                .connect()
                .await
                .expect("Failed to connect for initial migration");
            provider.close().await.ok();

            dsn
        })
        .await
}

/// Create a provider per test. Migration already done by ensure_setup().
async fn setup_provider() -> PostgresProvider {
    let dsn = ensure_setup().await;
    let config: SmrtiConfig = serde_json::from_value(json!({
        "dsn": dsn,
        "pool_min": 1,
        "pool_max": 5,
    }))
    .unwrap();

    let mut provider = PostgresProvider::new(config);
    // connect() calls migrate() which is idempotent (checks smrti_meta),
    // but the expensive CREATE EXTENSION was already done by ensure_setup().
    provider.connect().await.expect("Failed to connect");
    provider
}

/// Generate a unique namespace for test isolation.
fn unique_ns() -> String {
    format!(
        "test_{}",
        Uuid::new_v4().to_string().split('-').next().unwrap()
    )
}

/// Helper to create a node event.
fn node_event(namespace: &str, content: &str, node_type: &str) -> (String, Event) {
    let id = Uuid::new_v4().to_string();
    let event = Event::new(
        namespace,
        EventType::NodeCreated,
        json!({
            "id": id,
            "node_type": node_type,
            "content": content,
        }),
    );
    (id, event)
}

/// Helper to create a node event with a node_key.
fn node_event_with_key(
    namespace: &str,
    content: &str,
    node_type: &str,
    key: &str,
) -> (String, Event) {
    let id = Uuid::new_v4().to_string();
    let event = Event::new(
        namespace,
        EventType::NodeCreated,
        json!({
            "id": id,
            "node_key": key,
            "node_type": node_type,
            "content": content,
        }),
    );
    (id, event)
}

/// Helper to create an edge event.
fn edge_event(namespace: &str, source: &str, target: &str, edge_type: &str) -> (String, Event) {
    let id = Uuid::new_v4().to_string();
    let event = Event::new(
        namespace,
        EventType::EdgeAdded,
        json!({
            "id": id,
            "source_node_id": source,
            "target_node_id": target,
            "edge_type": edge_type,
        }),
    );
    (id, event)
}

/// Helper to create an embedding event.
fn embedding_event(namespace: &str, node_id: &str, embedding: Vec<f32>, model: &str) -> Event {
    Event::new(
        namespace,
        EventType::EmbeddingStored,
        json!({
            "node_id": node_id,
            "model_name": model,
            "embedding": embedding,
        }),
    )
}

// ---------------------------------------------------------------------------
// Node CRUD
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_create_and_get_node() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (id, event) = node_event(ns, "Alice is an engineer", "person");
    provider.apply_event(&event).await.unwrap();

    let node = provider
        .get_node(Uuid::parse_str(&id).unwrap())
        .await
        .unwrap()
        .expect("Node should exist");

    assert_eq!(node.content, "Alice is an engineer");
    assert_eq!(node.node_type, "person");
    assert!(!node.is_retracted);
}

#[tokio::test]
async fn test_get_nonexistent_node() {
    let provider = setup_provider().await;
    let result = provider.get_node(Uuid::new_v4()).await.unwrap();
    assert!(result.is_none());
}

#[tokio::test]
async fn test_node_key_upsert() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    // Create with key
    let (_id1, event1) = node_event_with_key(ns, "Bob v1", "person", "user_bob");
    provider.apply_event(&event1).await.unwrap();

    let found = provider
        .get_node_by_key(ns, "user_bob")
        .await
        .unwrap()
        .expect("Should find by key");
    assert_eq!(found.content, "Bob v1");

    // Upsert with same key — content should update
    let (_id2, event2) = node_event_with_key(ns, "Bob v2", "person", "user_bob");
    provider.apply_event(&event2).await.unwrap();

    let found2 = provider
        .get_node_by_key(ns, "user_bob")
        .await
        .unwrap()
        .expect("Should still find by key");
    assert_eq!(found2.content, "Bob v2");
    // Should be the same node (same UUID from first insert)
    assert_eq!(found.id, found2.id);
}

#[tokio::test]
async fn test_update_node() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (id, event) = node_event(ns, "original content", "fact");
    provider.apply_event(&event).await.unwrap();

    // Update content
    provider
        .apply_event(&Event::new(
            ns,
            EventType::NodeUpdated,
            json!({"id": id, "content": "updated content"}),
        ))
        .await
        .unwrap();

    let node = provider
        .get_node(Uuid::parse_str(&id).unwrap())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(node.content, "updated content");
}

#[tokio::test]
async fn test_retract_node() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (id, event) = node_event(ns, "will be retracted", "temp");
    provider.apply_event(&event).await.unwrap();

    provider
        .apply_event(&Event::new(ns, EventType::NodeRetracted, json!({"id": id})))
        .await
        .unwrap();

    let node = provider
        .get_node(Uuid::parse_str(&id).unwrap())
        .await
        .unwrap()
        .unwrap();
    assert!(node.is_retracted);
}

// ---------------------------------------------------------------------------
// get_or_create
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_get_or_create_with_key_new() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (node, created) = provider
        .get_or_create_node(ns, "Alice", "person", Some("alice_key"))
        .await
        .unwrap();

    assert!(created);
    assert_eq!(node.content, "Alice");
    assert_eq!(node.node_key.as_deref(), Some("alice_key"));
}

#[tokio::test]
async fn test_get_or_create_with_key_existing() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    // Create first
    let (node1, created1) = provider
        .get_or_create_node(ns, "Alice", "person", Some("alice_key"))
        .await
        .unwrap();
    assert!(created1);

    // Get existing
    let (node2, created2) = provider
        .get_or_create_node(ns, "Alice updated", "person", Some("alice_key"))
        .await
        .unwrap();
    assert!(!created2);
    assert_eq!(node1.id, node2.id); // Same node
}

#[tokio::test]
async fn test_get_or_create_by_content() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (node1, created1) = provider
        .get_or_create_node(ns, "The sky is blue", "fact", None)
        .await
        .unwrap();
    assert!(created1);

    // Same content + type → should find existing
    let (node2, created2) = provider
        .get_or_create_node(ns, "The sky is blue", "fact", None)
        .await
        .unwrap();
    assert!(!created2);
    assert_eq!(node1.id, node2.id);
}

// ---------------------------------------------------------------------------
// Edges
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_create_and_get_edges() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "Alice", "person");
    let (n2, e2) = node_event(ns, "Bob", "person");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    let (_eid, edge_event) = edge_event(ns, &n1, &n2, "KNOWS");
    provider.apply_event(&edge_event).await.unwrap();

    let edges = provider
        .get_edges(&[Uuid::parse_str(&n1).unwrap()], Direction::Outgoing, None)
        .await
        .unwrap();

    assert_eq!(edges.len(), 1);
    assert_eq!(edges[0].edge_type, "KNOWS");
}

#[tokio::test]
async fn test_multiple_edges_same_type() {
    // A1 principle: multiple edges of same type between same nodes are valid
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "Alice", "person");
    let (n2, e2) = node_event(ns, "Groceries", "metric");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    // Two TRACKS_METRIC edges with different metadata
    let (_, edge1) = edge_event(ns, &n1, &n2, "TRACKS_METRIC");
    let (_, edge2) = edge_event(ns, &n1, &n2, "TRACKS_METRIC");
    provider.apply_event(&edge1).await.unwrap();
    provider.apply_event(&edge2).await.unwrap();

    let edges = provider
        .get_edges(
            &[Uuid::parse_str(&n1).unwrap()],
            Direction::Outgoing,
            Some(&["TRACKS_METRIC".to_string()]),
        )
        .await
        .unwrap();

    assert_eq!(edges.len(), 2); // Both exist, no dedup
}

#[tokio::test]
async fn test_retract_edge() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "A", "x");
    let (n2, e2) = node_event(ns, "B", "x");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    let (eid, edge_ev) = edge_event(ns, &n1, &n2, "KNOWS");
    provider.apply_event(&edge_ev).await.unwrap();

    // Retract
    provider
        .apply_event(&Event::new(
            ns,
            EventType::EdgeRetracted,
            json!({"id": eid}),
        ))
        .await
        .unwrap();

    let edges = provider
        .get_edges(&[Uuid::parse_str(&n1).unwrap()], Direction::Both, None)
        .await
        .unwrap();
    assert_eq!(edges.len(), 0); // Retracted edge not returned
}

#[tokio::test]
async fn test_batch_get_edges() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "A", "x");
    let (n2, e2) = node_event(ns, "B", "x");
    let (n3, e3) = node_event(ns, "C", "x");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();
    provider.apply_event(&e3).await.unwrap();

    let (_, edge1) = edge_event(ns, &n1, &n2, "NEXT");
    let (_, edge2) = edge_event(ns, &n2, &n3, "NEXT");
    provider.apply_event(&edge1).await.unwrap();
    provider.apply_event(&edge2).await.unwrap();

    // Batch fetch for both n1 and n2
    let edges = provider
        .get_edges(
            &[Uuid::parse_str(&n1).unwrap(), Uuid::parse_str(&n2).unwrap()],
            Direction::Outgoing,
            None,
        )
        .await
        .unwrap();

    assert_eq!(edges.len(), 2);
}

// ---------------------------------------------------------------------------
// Search: Vector
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_vector_search() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "cats are fluffy", "fact");
    let (n2, e2) = node_event(ns, "dogs are loyal", "fact");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    provider
        .apply_event(&embedding_event(ns, &n1, vec![1.0, 0.0, 0.0], "test-model"))
        .await
        .unwrap();
    provider
        .apply_event(&embedding_event(ns, &n2, vec![0.0, 1.0, 0.0], "test-model"))
        .await
        .unwrap();

    let results = provider
        .search_nodes(&SearchQuery {
            query_vector: Some(vec![0.9, 0.1, 0.0]),
            namespaces: vec![ns.clone()],
            mode: "vector".into(),
            model_name: Some("test-model".into()),
            limit: 10,
            ..Default::default()
        })
        .await
        .unwrap();

    assert_eq!(results.len(), 2);
    assert_eq!(results[0].node.content, "cats are fluffy"); // Closer to [0.9, 0.1, 0]
    assert!(results[0].similarity > results[1].similarity);
}

#[tokio::test]
async fn test_search_namespace_isolation() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let ns1 = &format!("{ns}_1");
    let ns2 = &format!("{ns}_2");

    let (n1, e1) = node_event(ns1, "secret data", "fact");
    provider.apply_event(&e1).await.unwrap();
    provider
        .apply_event(&embedding_event(ns1, &n1, vec![1.0, 0.0, 0.0], "m"))
        .await
        .unwrap();

    // Search in different namespace
    let results = provider
        .search_nodes(&SearchQuery {
            query_vector: Some(vec![1.0, 0.0, 0.0]),
            namespaces: vec![ns2.clone()],
            mode: "vector".into(),
            model_name: Some("m".into()),
            limit: 10,
            ..Default::default()
        })
        .await
        .unwrap();

    assert_eq!(results.len(), 0); // Isolated
}

#[tokio::test]
async fn test_search_multi_namespace() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let ns1 = &format!("{ns}_1");
    let ns2 = &format!("{ns}_2");

    let (n1, e1) = node_event(ns1, "from ns1", "fact");
    let (n2, e2) = node_event(ns2, "from ns2", "fact");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();
    provider
        .apply_event(&embedding_event(ns1, &n1, vec![1.0, 0.0, 0.0], "m"))
        .await
        .unwrap();
    provider
        .apply_event(&embedding_event(ns2, &n2, vec![0.9, 0.1, 0.0], "m"))
        .await
        .unwrap();

    let results = provider
        .search_nodes(&SearchQuery {
            query_vector: Some(vec![1.0, 0.0, 0.0]),
            namespaces: vec![ns1.clone(), ns2.clone()],
            mode: "vector".into(),
            model_name: Some("m".into()),
            limit: 10,
            ..Default::default()
        })
        .await
        .unwrap();

    assert_eq!(results.len(), 2);
}

#[tokio::test]
async fn test_search_excludes_retracted() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "will retract", "fact");
    provider.apply_event(&e1).await.unwrap();
    provider
        .apply_event(&embedding_event(ns, &n1, vec![1.0, 0.0, 0.0], "m"))
        .await
        .unwrap();

    // Retract
    provider
        .apply_event(&Event::new(ns, EventType::NodeRetracted, json!({"id": n1})))
        .await
        .unwrap();

    let results = provider
        .search_nodes(&SearchQuery {
            query_vector: Some(vec![1.0, 0.0, 0.0]),
            namespaces: vec![ns.clone()],
            mode: "vector".into(),
            model_name: Some("m".into()),
            limit: 10,
            ..Default::default()
        })
        .await
        .unwrap();

    assert_eq!(results.len(), 0);
}

// ---------------------------------------------------------------------------
// Search: Text
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_text_search() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (_, e1) = node_event(ns, "Alice is a software engineer at Acme", "person");
    let (_, e2) = node_event(ns, "Bob manages the infrastructure team", "person");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    let results = provider
        .search_nodes(&SearchQuery {
            text_query: Some("software engineer".into()),
            namespaces: vec![ns.clone()],
            mode: "text".into(),
            limit: 10,
            ..Default::default()
        })
        .await
        .unwrap();

    assert!(!results.is_empty());
    assert!(results[0].node.content.contains("Alice"));
}

// ---------------------------------------------------------------------------
// Search: Hybrid
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_hybrid_search() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "Alice the software engineer", "person");
    let (n2, e2) = node_event(ns, "Bob the manager", "person");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();
    provider
        .apply_event(&embedding_event(ns, &n1, vec![1.0, 0.0, 0.0], "m"))
        .await
        .unwrap();
    provider
        .apply_event(&embedding_event(ns, &n2, vec![0.0, 1.0, 0.0], "m"))
        .await
        .unwrap();

    let results = provider
        .search_nodes(&SearchQuery {
            query_vector: Some(vec![0.9, 0.1, 0.0]),
            text_query: Some("Alice".into()),
            namespaces: vec![ns.clone()],
            mode: "hybrid".into(),
            model_name: Some("m".into()),
            limit: 10,
            ..Default::default()
        })
        .await
        .unwrap();

    assert!(!results.is_empty());
    // Alice should rank highest (matched by both vector AND text)
    assert!(results[0].node.content.contains("Alice"));
    assert!(results[0].matched_by.contains(&"vector".to_string()));
    assert!(results[0].matched_by.contains(&"text".to_string()));
}

// ---------------------------------------------------------------------------
// Traversal
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_traverse_depth_1() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "A", "x");
    let (n2, e2) = node_event(ns, "B", "x");
    let (n3, e3) = node_event(ns, "C", "x");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();
    provider.apply_event(&e3).await.unwrap();

    let (_, edge1) = edge_event(ns, &n1, &n2, "NEXT");
    let (_, edge2) = edge_event(ns, &n2, &n3, "NEXT");
    provider.apply_event(&edge1).await.unwrap();
    provider.apply_event(&edge2).await.unwrap();

    let result = provider
        .traverse_graph(Uuid::parse_str(&n1).unwrap(), 1, None, 100)
        .await
        .unwrap();

    assert_eq!(result.edges.len(), 1); // Only A→B at depth 1
    let contents: Vec<&str> = result.nodes.iter().map(|n| n.content.as_str()).collect();
    assert!(contents.contains(&"A"));
    assert!(contents.contains(&"B"));
}

#[tokio::test]
async fn test_traverse_depth_2() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "A", "x");
    let (n2, e2) = node_event(ns, "B", "x");
    let (n3, e3) = node_event(ns, "C", "x");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();
    provider.apply_event(&e3).await.unwrap();

    let (_, edge1) = edge_event(ns, &n1, &n2, "NEXT");
    let (_, edge2) = edge_event(ns, &n2, &n3, "NEXT");
    provider.apply_event(&edge1).await.unwrap();
    provider.apply_event(&edge2).await.unwrap();

    let result = provider
        .traverse_graph(Uuid::parse_str(&n1).unwrap(), 2, None, 100)
        .await
        .unwrap();

    assert_eq!(result.edges.len(), 2); // A→B and B→C
    let contents: Vec<&str> = result.nodes.iter().map(|n| n.content.as_str()).collect();
    assert!(contents.contains(&"A"));
    assert!(contents.contains(&"B"));
    assert!(contents.contains(&"C"));
}

// ---------------------------------------------------------------------------
// Aggregation
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_aggregate_with_metadata() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "Alice", "person");
    let (n2, e2) = node_event(ns, "Spending", "metric");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    // Two metric edges with values
    provider
        .apply_event(&Event::new(
            ns,
            EventType::EdgeAdded,
            json!({
                "id": Uuid::new_v4().to_string(),
                "source_node_id": n1,
                "target_node_id": n2,
                "edge_type": "TRACKS_METRIC",
                "metadata": {"value": 50},
            }),
        ))
        .await
        .unwrap();

    provider
        .apply_event(&Event::new(
            ns,
            EventType::EdgeAdded,
            json!({
                "id": Uuid::new_v4().to_string(),
                "source_node_id": n1,
                "target_node_id": n2,
                "edge_type": "TRACKS_METRIC",
                "metadata": {"value": 30},
            }),
        ))
        .await
        .unwrap();

    let result = provider
        .aggregate_edges(&AggregateQuery {
            edge_type: "TRACKS_METRIC".into(),
            namespaces: vec![ns.clone()],
            metadata_key: Some("value".into()),
            metadata_filter: None,
            at_time: None,
        })
        .await
        .unwrap();

    assert_eq!(result.count, 2);
    assert_eq!(result.total, Some(80.0));
    assert_eq!(result.average, Some(40.0));
    assert_eq!(result.minimum, Some(30.0));
    assert_eq!(result.maximum, Some(50.0));
}

#[tokio::test]
async fn test_aggregate_count_only() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (n1, e1) = node_event(ns, "A", "x");
    let (n2, e2) = node_event(ns, "B", "x");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    let (_, edge_ev) = edge_event(ns, &n1, &n2, "KNOWS");
    provider.apply_event(&edge_ev).await.unwrap();

    let result = provider
        .aggregate_edges(&AggregateQuery {
            edge_type: "KNOWS".into(),
            namespaces: vec![ns.clone()],
            metadata_key: None,
            metadata_filter: None,
            at_time: None,
        })
        .await
        .unwrap();

    assert_eq!(result.count, 1);
    assert!(result.total.is_none());
}

// ---------------------------------------------------------------------------
// Event log
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_get_events() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let (_, e1) = node_event(ns, "first", "x");
    let (_, e2) = node_event(ns, "second", "x");
    let eid1 = provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    let events = provider.get_events(0, Some(ns), 100).await.unwrap();
    assert!(events.len() >= 2);

    // After ID filter
    let events_after = provider.get_events(eid1, Some(ns), 100).await.unwrap();
    assert_eq!(events_after.len(), 1);
    assert_eq!(events_after[0].event_type, EventType::NodeCreated);
}

// ---------------------------------------------------------------------------
// GDPR: purge_namespace
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_purge_namespace() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let victim_ns = &format!("{ns}_victim");
    let safe_ns = &format!("{ns}_safe");

    // Create data in two namespaces
    let (n1, e1) = node_event(victim_ns, "data to purge", "fact");
    let (n2, e2) = node_event(safe_ns, "data to keep", "fact");
    provider.apply_event(&e1).await.unwrap();
    provider.apply_event(&e2).await.unwrap();

    // Purge victim namespace
    let result = provider.purge_namespace(victim_ns).await.unwrap();
    assert!(result.events_deleted >= 1);
    assert!(result.nodes_deleted >= 1);

    // Victim data gone
    let node = provider
        .get_node(Uuid::parse_str(&n1).unwrap())
        .await
        .unwrap();
    assert!(node.is_none());

    // Safe data intact
    let node = provider
        .get_node(Uuid::parse_str(&n2).unwrap())
        .await
        .unwrap();
    assert!(node.is_some());
}

// ---------------------------------------------------------------------------
// Session State
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_state_set_and_get() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    provider
        .state_set(ns, "session1", "plan", json!({"steps": [1, 2, 3]}), None)
        .await
        .unwrap();

    let value = provider.state_get(ns, "session1", "plan").await.unwrap();
    assert!(value.is_some());
    assert_eq!(value.unwrap()["steps"], json!([1, 2, 3]));
}

#[tokio::test]
async fn test_state_upsert() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    provider
        .state_set(ns, "s1", "key1", json!("v1"), None)
        .await
        .unwrap();
    provider
        .state_set(ns, "s1", "key1", json!("v2"), None)
        .await
        .unwrap();

    let value = provider.state_get(ns, "s1", "key1").await.unwrap();
    assert_eq!(value.unwrap(), json!("v2"));
}

#[tokio::test]
async fn test_state_get_nonexistent() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    let value = provider.state_get(ns, "s1", "nope").await.unwrap();
    assert!(value.is_none());
}

#[tokio::test]
async fn test_state_delete() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    provider
        .state_set(ns, "s1", "k1", json!(42), None)
        .await
        .unwrap();

    let existed = provider.state_delete(ns, "s1", "k1").await.unwrap();
    assert!(existed);

    let not_existed = provider.state_delete(ns, "s1", "k1").await.unwrap();
    assert!(!not_existed);

    let value = provider.state_get(ns, "s1", "k1").await.unwrap();
    assert!(value.is_none());
}

#[tokio::test]
async fn test_state_clear() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    provider
        .state_set(ns, "s1", "a", json!(1), None)
        .await
        .unwrap();
    provider
        .state_set(ns, "s1", "b", json!(2), None)
        .await
        .unwrap();
    provider
        .state_set(ns, "s1", "c", json!(3), None)
        .await
        .unwrap();

    let cleared = provider.state_clear(ns, "s1").await.unwrap();
    assert_eq!(cleared, 3);

    let list = provider.state_list(ns, "s1").await.unwrap();
    assert!(list.is_empty());
}

#[tokio::test]
async fn test_state_list() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    provider
        .state_set(ns, "s1", "beta", json!("b"), None)
        .await
        .unwrap();
    provider
        .state_set(ns, "s1", "alpha", json!("a"), None)
        .await
        .unwrap();
    provider
        .state_set(ns, "s1", "gamma", json!("g"), None)
        .await
        .unwrap();

    let list = provider.state_list(ns, "s1").await.unwrap();
    assert_eq!(list.len(), 3);
    // Ordered by key name
    assert_eq!(list[0].0, "alpha");
    assert_eq!(list[1].0, "beta");
    assert_eq!(list[2].0, "gamma");
}

#[tokio::test]
async fn test_state_namespace_isolation() {
    let provider = setup_provider().await;
    let ns = &unique_ns();
    let ns1 = &format!("{ns}_1");
    let ns2 = &format!("{ns}_2");

    provider
        .state_set(ns1, "s1", "secret", json!("private"), None)
        .await
        .unwrap();

    let value = provider.state_get(ns2, "s1", "secret").await.unwrap();
    assert!(value.is_none());
}

#[tokio::test]
async fn test_state_session_isolation() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    provider
        .state_set(ns, "session_a", "key", json!("a"), None)
        .await
        .unwrap();

    let value = provider.state_get(ns, "session_b", "key").await.unwrap();
    assert!(value.is_none());
}

#[tokio::test]
async fn test_state_ttl_expiry() {
    let provider = setup_provider().await;
    let ns = &unique_ns();

    // Set with 1 second TTL
    provider
        .state_set(ns, "s1", "ephemeral", json!("gone soon"), Some(1))
        .await
        .unwrap();

    // Should exist immediately
    let value = provider.state_get(ns, "s1", "ephemeral").await.unwrap();
    assert!(value.is_some());

    // Wait for expiry
    tokio::time::sleep(std::time::Duration::from_secs(2)).await;

    // Should be filtered out
    let value = provider.state_get(ns, "s1", "ephemeral").await.unwrap();
    assert!(value.is_none());
}
