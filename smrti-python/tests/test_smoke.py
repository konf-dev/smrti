"""Smoke tests for smrti Python bindings.

Tests the full stack: Python → PyO3 → Rust → PostgreSQL.
Requires Docker running (testcontainers spins up pgvector).

Run with: pytest smrti-python/tests/ -v
"""

import subprocess
import time

import pytest

# Skip all tests if Docker is not available
try:
    subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=5)
    HAS_DOCKER = True
except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
    HAS_DOCKER = False

pytestmark = pytest.mark.skipif(not HAS_DOCKER, reason="Docker not available")


@pytest.fixture(scope="module")
def pg_dsn():
    """Start a pgvector container and return the DSN."""
    container_name = "smrti_python_test"

    # Clean up any existing container
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
    )

    # Start pgvector container
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-e",
            "POSTGRES_USER=test",
            "-e",
            "POSTGRES_PASSWORD=test",
            "-e",
            "POSTGRES_DB=smrti_test",
            "-p",
            "15432:5432",
            "pgvector/pgvector:pg17",
        ],
        check=True,
        capture_output=True,
    )

    # Wait for Postgres to be ready
    for _ in range(30):
        result = subprocess.run(
            ["docker", "exec", container_name, "pg_isready", "-U", "test"],
            capture_output=True,
        )
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        pytest.fail("PostgreSQL container did not start in time")

    dsn = "postgresql://test:test@127.0.0.1:15432/smrti_test"

    yield dsn

    # Cleanup
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)


@pytest.fixture
def memory(pg_dsn):
    """Connect a Memory instance."""
    from smrti import Memory

    mem = Memory.connect(pg_dsn)
    yield mem
    mem.close()


class TestImport:
    """Test that the module imports correctly."""

    def test_import_memory(self):
        from smrti import Memory

        assert Memory is not None

    def test_memory_has_methods(self):
        from smrti import Memory

        methods = [m for m in dir(Memory) if not m.startswith("_")]
        assert "connect" in methods
        assert "add_nodes" in methods
        assert "search" in methods
        assert "traverse" in methods
        assert "state_set" in methods


class TestNodeCRUD:
    """Test basic node operations through Python."""

    def test_add_nodes(self, memory):
        result = memory.add_nodes(
            [
                {"node_type": "person", "content": "Alice is an engineer"},
            ]
        )
        assert "node_ids" in result
        assert len(result["node_ids"]) == 1
        assert "_meta" in result
        assert result["_meta"]["count"] == 1

    def test_add_nodes_with_embedding(self, memory):
        result = memory.add_nodes(
            [
                {
                    "node_type": "person",
                    "content": "Bob works at Acme",
                    "embedding": [1.0, 0.0, 0.0],
                    "model_name": "test-model",
                },
            ]
        )
        assert len(result["node_ids"]) == 1

    def test_get_or_create(self, memory):
        result1 = memory.get_or_create("Charlie", "person")
        assert result1["created"] is True
        assert "node_id" in result1

        result2 = memory.get_or_create("Charlie", "person")
        assert result2["created"] is False
        assert result1["node_id"] == result2["node_id"]


class TestEdges:
    """Test edge operations."""

    def test_add_edges(self, memory):
        nodes = memory.add_nodes(
            [
                {"node_type": "person", "content": "Dave"},
                {"node_type": "person", "content": "Eve"},
            ]
        )
        n1, n2 = nodes["node_ids"]

        result = memory.add_edges(
            [
                {
                    "source_node_id": n1,
                    "target_node_id": n2,
                    "edge_type": "KNOWS",
                }
            ]
        )
        assert len(result["edge_ids"]) == 1
        assert "_meta" in result

    def test_get_edges(self, memory):
        nodes = memory.add_nodes(
            [
                {"node_type": "x", "content": "F"},
                {"node_type": "x", "content": "G"},
            ]
        )
        n1, n2 = nodes["node_ids"]

        memory.add_edges(
            [
                {
                    "source_node_id": n1,
                    "target_node_id": n2,
                    "edge_type": "NEXT",
                }
            ]
        )

        result = memory.get_edges(n1, direction="outgoing")
        assert len(result["edges"]) >= 1


class TestSearch:
    """Test search operations."""

    def test_vector_search(self, memory):
        memory.add_nodes(
            [
                {
                    "node_type": "fact",
                    "content": "cats are fluffy",
                    "embedding": [1.0, 0.0, 0.0],
                    "model_name": "m",
                },
                {
                    "node_type": "fact",
                    "content": "dogs are loyal",
                    "embedding": [0.0, 1.0, 0.0],
                    "model_name": "m",
                },
            ]
        )

        result = memory.search(
            query_vector=[0.9, 0.1, 0.0],
            mode="vector",
        )
        assert "results" in result
        assert "_meta" in result
        assert result["_meta"]["search_mode"] == "vector"

    def test_text_search(self, memory):
        memory.add_nodes(
            [
                {"node_type": "fact", "content": "the quick brown fox"},
            ]
        )

        result = memory.search(text_query="quick brown", mode="text")
        assert "results" in result
        assert result["_meta"]["search_mode"] == "text"


class TestTraversal:
    """Test graph traversal."""

    def test_traverse(self, memory):
        nodes = memory.add_nodes(
            [
                {"node_type": "x", "content": "H"},
                {"node_type": "x", "content": "I"},
            ]
        )
        n1, n2 = nodes["node_ids"]

        memory.add_edges(
            [
                {
                    "source_node_id": n1,
                    "target_node_id": n2,
                    "edge_type": "NEXT",
                }
            ]
        )

        result = memory.traverse(n1, depth=1)
        assert "nodes" in result
        assert "edges" in result
        assert result["_meta"]["nodes_found"] >= 2


class TestSessionState:
    """Test session state (working memory)."""

    def test_state_crud(self, memory):
        memory.state_set("plan", {"steps": [1, 2, 3]}, session_id="s1")

        result = memory.state_get("plan", session_id="s1")
        assert result["_meta"]["found"] is True
        assert result["value"]["steps"] == [1, 2, 3]

        memory.state_delete("plan", session_id="s1")

        result = memory.state_get("plan", session_id="s1")
        assert result["_meta"]["found"] is False

    def test_state_list(self, memory):
        memory.state_set("a", 1, session_id="s2")
        memory.state_set("b", 2, session_id="s2")

        result = memory.state_list(session_id="s2")
        assert result["_meta"]["count"] >= 2


class TestMeta:
    """Test that _meta is present on all returns."""

    def test_all_returns_have_meta(self, memory):
        """Every method should return a dict with _meta."""
        result = memory.add_nodes(
            [
                {"node_type": "x", "content": "meta test"},
            ]
        )
        assert "_meta" in result
        assert "duration_ms" in result["_meta"]

        node_id = result["node_ids"][0]

        result = memory.get_or_create("meta test 2", "x")
        assert "_meta" in result

        result = memory.search(text_query="meta", mode="text")
        assert "_meta" in result

        result = memory.traverse(node_id)
        assert "_meta" in result

        result = memory.state_set("k", "v", session_id="s")
        assert "_meta" in result

        result = memory.export_events()
        assert "_meta" in result


class TestErrorHandling:
    """Test that errors are properly raised as Python exceptions."""

    def test_validation_error(self, memory):
        with pytest.raises(ValueError, match="node_type is required"):
            memory.add_nodes([{"content": "missing type"}])

    def test_invalid_uuid(self, memory):
        with pytest.raises(ValueError, match="Invalid node_id"):
            memory.retract_node("not-a-uuid")

    def test_empty_nodes(self, memory):
        with pytest.raises(ValueError, match="empty"):
            memory.add_nodes([])
