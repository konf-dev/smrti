"""Unit tests for Qdrant Long-Term memory adapter."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from qdrant_client.models import (
    Distance,
    CollectionsResponse,
    CollectionDescription,
    ScoredPoint,
    Record,
)

from smrti.storage.adapters.qdrant_long_term import QdrantLongTermAdapter
from smrti.core.exceptions import StorageError


@pytest.fixture
def mock_qdrant_client():
    """Create a mock Qdrant client."""
    client = AsyncMock()
    
    # Mock collections list (empty initially)
    client.get_collections.return_value = CollectionsResponse(
        collections=[]
    )
    
    return client


@pytest.fixture
def adapter(mock_qdrant_client):
    """Create a QdrantLongTermAdapter with mock client."""
    return QdrantLongTermAdapter(
        client=mock_qdrant_client,
        vector_size=384,
        distance_metric=Distance.COSINE
    )


@pytest.fixture
def sample_embedding() -> List[float]:
    """Generate a sample embedding vector."""
    return [0.1] * 384


@pytest.mark.unit
@pytest.mark.asyncio
class TestQdrantLongTermAdapter:
    """Test suite for Qdrant Long-Term memory adapter."""

    async def test_collection_name_generation(self, adapter):
        """Test collection name generation from namespace."""
        # Two-part namespace
        name1 = adapter._get_collection_name("tenant:123:user:456")
        assert name1 == "smrti_long_term_tenant_123"
        
        # Single-part namespace
        name2 = adapter._get_collection_name("demo")
        assert name2 == "smrti_long_term_demo"
        
        # Three-part namespace (uses first two)
        name3 = adapter._get_collection_name("org:acme:team:alpha")
        assert name3 == "smrti_long_term_org_acme"

    async def test_store_success(self, adapter, mock_qdrant_client, sample_embedding):
        """Test successful memory storage."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"text": "Important information to remember"}
        metadata = {"category": "work"}
        
        # Mock collection creation
        mock_qdrant_client.upsert.return_value = None
        
        # Store
        result = await adapter.store(memory_id, namespace, data, sample_embedding, metadata)
        
        assert result == memory_id
        
        # Verify collection was created
        mock_qdrant_client.create_collection.assert_called_once()
        
        # Verify upsert was called
        mock_qdrant_client.upsert.assert_called_once()
        call_args = mock_qdrant_client.upsert.call_args
        
        # Check collection name
        assert call_args.kwargs["collection_name"] == "smrti_long_term_test_user"
        
        # Check point structure
        points = call_args.kwargs["points"]
        assert len(points) == 1
        point = points[0]
        assert str(point.id) == str(memory_id)
        assert point.vector == sample_embedding
        assert point.payload["namespace"] == namespace
        assert point.payload["data"]["text"] == "Important information to remember"
        assert point.payload["metadata"]["category"] == "work"

    async def test_store_missing_text(self, adapter, sample_embedding):
        """Test that store requires 'text' field in data."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"content": "Missing text field"}
        
        with pytest.raises(StorageError, match="text"):
            await adapter.store(memory_id, namespace, data, sample_embedding, {})

    async def test_store_missing_embedding(self, adapter):
        """Test that store requires embedding."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"text": "Some text"}
        
        with pytest.raises(StorageError, match="Embedding is required"):
            await adapter.store(memory_id, namespace, data, None, {})

    async def test_store_wrong_embedding_size(self, adapter):
        """Test that store validates embedding size."""
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {"text": "Some text"}
        wrong_embedding = [0.1] * 128  # Wrong size
        
        with pytest.raises(StorageError, match="Embedding size"):
            await adapter.store(memory_id, namespace, data, wrong_embedding, {})

    async def test_store_creates_collection_once(self, adapter, mock_qdrant_client, sample_embedding):
        """Test that collection is only created once."""
        namespace = "test:user:123"
        
        # First store - collection doesn't exist
        await adapter.store(uuid4(), namespace, {"text": "First"}, sample_embedding, {})
        assert mock_qdrant_client.create_collection.call_count == 1
        
        # Simulate collection now exists
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        
        # Second store - collection exists
        await adapter.store(uuid4(), namespace, {"text": "Second"}, sample_embedding, {})
        # Should still be 1 (not created again)
        assert mock_qdrant_client.create_collection.call_count == 1

    async def test_retrieve_success(self, adapter, mock_qdrant_client, sample_embedding):
        """Test successful memory retrieval."""
        namespace = "test:user:123"
        query_embedding = sample_embedding
        
        # Mock collection exists
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        
        # Mock search results
        mock_qdrant_client.search.return_value = [
            ScoredPoint(
                id="mem1",
                version=1,
                score=0.95,
                payload={
                    "memory_id": "mem1",
                    "namespace": namespace,
                    "data": {"text": "Result 1"},
                    "metadata": {}
                },
                vector=None
            ),
            ScoredPoint(
                id="mem2",
                version=1,
                score=0.87,
                payload={
                    "memory_id": "mem2",
                    "namespace": namespace,
                    "data": {"text": "Result 2"},
                    "metadata": {}
                },
                vector=None
            )
        ]
        
        # Retrieve
        results = await adapter.retrieve(namespace, query_embedding, None, limit=10)
        
        assert len(results) == 2
        assert results[0]["similarity_score"] == 0.95
        assert results[1]["similarity_score"] == 0.87
        assert results[0]["data"]["text"] == "Result 1"
        
        # Verify search was called with correct parameters
        mock_qdrant_client.search.assert_called_once()
        call_args = mock_qdrant_client.search.call_args
        assert call_args.kwargs["collection_name"] == "smrti_long_term_test_user"
        assert call_args.kwargs["query_vector"] == query_embedding
        assert call_args.kwargs["limit"] == 10

    async def test_retrieve_empty_collection(self, adapter, mock_qdrant_client, sample_embedding):
        """Test retrieval from non-existent collection."""
        namespace = "test:user:empty"
        
        # Collection doesn't exist
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[]
        )
        
        results = await adapter.retrieve(namespace, sample_embedding, None, limit=10)
        
        assert results == []
        # Search should not be called
        mock_qdrant_client.search.assert_not_called()

    async def test_retrieve_missing_embedding(self, adapter):
        """Test that retrieve requires query embedding."""
        namespace = "test:user:123"
        
        with pytest.raises(StorageError, match="Query embedding is required"):
            await adapter.retrieve(namespace, None, None, limit=10)

    async def test_retrieve_wrong_embedding_size(self, adapter):
        """Test that retrieve validates query embedding size."""
        namespace = "test:user:123"
        wrong_embedding = [0.1] * 128
        
        with pytest.raises(StorageError, match="Query embedding size"):
            await adapter.retrieve(namespace, wrong_embedding, None, limit=10)

    async def test_retrieve_with_score_threshold(self, adapter, mock_qdrant_client, sample_embedding):
        """Test retrieval with score threshold."""
        namespace = "test:user:123"
        
        # Mock collection exists
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        
        mock_qdrant_client.search.return_value = []
        
        # Retrieve with threshold
        await adapter.retrieve(namespace, sample_embedding, None, limit=10, score_threshold=0.8)
        
        # Verify threshold was passed
        call_args = mock_qdrant_client.search.call_args
        assert call_args.kwargs["score_threshold"] == 0.8

    async def test_get_success(self, adapter, mock_qdrant_client):
        """Test getting a specific memory by ID."""
        memory_id = uuid4()
        namespace = "test:user:123"
        
        # Mock collection exists
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        
        # Mock retrieve
        mock_qdrant_client.retrieve.return_value = [
            Record(
                id=str(memory_id),
                payload={
                    "memory_id": str(memory_id),
                    "namespace": namespace,
                    "data": {"text": "Retrieved memory"},
                    "metadata": {}
                },
                vector=None
            )
        ]
        
        # Get
        result = await adapter.get(memory_id, namespace)
        
        assert result is not None
        assert result["memory_id"] == str(memory_id)
        assert result["data"]["text"] == "Retrieved memory"

    async def test_get_nonexistent(self, adapter, mock_qdrant_client):
        """Test getting a memory that doesn't exist."""
        memory_id = uuid4()
        namespace = "test:user:123"
        
        # Mock collection exists but point doesn't
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        mock_qdrant_client.retrieve.return_value = []
        
        result = await adapter.get(memory_id, namespace)
        
        assert result is None

    async def test_get_collection_not_exists(self, adapter, mock_qdrant_client):
        """Test getting from non-existent collection."""
        memory_id = uuid4()
        namespace = "test:user:empty"
        
        # Collection doesn't exist
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[]
        )
        
        result = await adapter.get(memory_id, namespace)
        
        assert result is None

    async def test_get_namespace_isolation(self, adapter, mock_qdrant_client):
        """Test that get respects namespace isolation."""
        memory_id = uuid4()
        namespace_a = "test:user:alice"
        namespace_b = "test:user:bob"
        
        # Mock collection exists
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        
        # Mock retrieve - memory belongs to Alice
        mock_qdrant_client.retrieve.return_value = [
            Record(
                id=str(memory_id),
                payload={
                    "memory_id": str(memory_id),
                    "namespace": namespace_a,  # Alice's namespace
                    "data": {"text": "Alice's memory"},
                    "metadata": {}
                },
                vector=None
            )
        ]
        
        # Try to get from Bob's namespace
        result = await adapter.get(memory_id, namespace_b)
        
        # Should return None due to namespace mismatch
        assert result is None

    async def test_delete_success(self, adapter, mock_qdrant_client):
        """Test successful memory deletion."""
        memory_id = uuid4()
        namespace = "test:user:123"
        
        # Mock collection exists
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        
        # Mock get (memory exists)
        mock_qdrant_client.retrieve.return_value = [
            Record(
                id=str(memory_id),
                payload={
                    "memory_id": str(memory_id),
                    "namespace": namespace,
                    "data": {"text": "To delete"},
                    "metadata": {}
                },
                vector=None
            )
        ]
        
        # Delete
        deleted = await adapter.delete(memory_id, namespace)
        
        assert deleted is True
        mock_qdrant_client.delete.assert_called_once()

    async def test_delete_nonexistent(self, adapter, mock_qdrant_client):
        """Test deleting a memory that doesn't exist."""
        memory_id = uuid4()
        namespace = "test:user:123"
        
        # Mock collection exists but memory doesn't
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        mock_qdrant_client.retrieve.return_value = []
        
        deleted = await adapter.delete(memory_id, namespace)
        
        assert deleted is False
        mock_qdrant_client.delete.assert_not_called()

    async def test_delete_wrong_namespace(self, adapter, mock_qdrant_client):
        """Test that delete respects namespace isolation."""
        memory_id = uuid4()
        namespace_a = "test:user:alice"
        namespace_b = "test:user:bob"
        
        # Mock collection exists
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="smrti_long_term_test_user")
            ]
        )
        
        # Memory belongs to Alice
        mock_qdrant_client.retrieve.return_value = [
            Record(
                id=str(memory_id),
                payload={
                    "memory_id": str(memory_id),
                    "namespace": namespace_a,
                    "data": {"text": "Alice's memory"},
                    "metadata": {}
                },
                vector=None
            )
        ]
        
        # Try to delete from Bob's namespace
        deleted = await adapter.delete(memory_id, namespace_b)
        
        assert deleted is False
        mock_qdrant_client.delete.assert_not_called()

    async def test_health_check_success(self, adapter, mock_qdrant_client):
        """Test health check when Qdrant is available."""
        mock_qdrant_client.get_collections.return_value = CollectionsResponse(
            collections=[
                CollectionDescription(name="collection1"),
                CollectionDescription(name="collection2")
            ]
        )
        
        health = await adapter.health_check()
        
        assert health["status"] == "connected"
        assert health["backend"] == "Qdrant"
        assert health["memory_type"] == "LONG_TERM"
        assert health["collections_count"] == 2
        assert health["vector_size"] == 384
        assert "latency_ms" in health

    async def test_health_check_failure(self, adapter, mock_qdrant_client):
        """Test health check when Qdrant is unavailable."""
        mock_qdrant_client.get_collections.side_effect = Exception("Connection failed")
        
        health = await adapter.health_check()
        
        assert health["status"] == "error"
        assert "error" in health

    async def test_namespace_isolation_comprehensive(self, adapter, mock_qdrant_client, sample_embedding):
        """Comprehensive test for multi-tenant isolation."""
        alice_id = uuid4()
        bob_id = uuid4()
        namespace_alice = "tenant:1:user:alice"
        namespace_bob = "tenant:1:user:bob"
        
        # Store for Alice
        await adapter.store(
            alice_id,
            namespace_alice,
            {"text": "Alice's secret"},
            sample_embedding,
            {}
        )
        
        # Store for Bob
        await adapter.store(
            bob_id,
            namespace_bob,
            {"text": "Bob's secret"},
            sample_embedding,
            {}
        )
        
        # Both should be in same collection (same tenant prefix)
        assert adapter._get_collection_name(namespace_alice) == adapter._get_collection_name(namespace_bob)
        
        # But namespace filtering in search prevents cross-access
        # This is enforced by Qdrant's filter in retrieve()
