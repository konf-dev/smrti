"""Integration test for the full API stack."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from httpx import AsyncClient
import redis.asyncio as redis
from qdrant_client import QdrantClient
import asyncpg

from smrti.api.main import app
from smrti.core.config import get_settings


pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    settings = get_settings()
    client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True
    )
    
    # Test connection
    await client.ping()
    
    yield client
    
    # Cleanup
    await client.flushdb()
    await client.close()


@pytest.fixture
async def qdrant_client():
    """Create Qdrant client for testing."""
    settings = get_settings()
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port
    )
    
    yield client
    
    # Cleanup - delete test collections
    collections = client.get_collections()
    for collection in collections.collections:
        if collection.name.startswith("smrti_test"):
            client.delete_collection(collection.name)


@pytest.fixture
async def postgres_pool():
    """Create PostgreSQL pool for testing."""
    settings = get_settings()
    pool = await asyncpg.create_pool(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_database,
        user=settings.postgres_user,
        password=settings.postgres_password,
        min_size=2,
        max_size=5
    )
    
    yield pool
    
    # Cleanup
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM episodic_memories WHERE namespace LIKE 'test:%'"
        )
        await conn.execute(
            "DELETE FROM semantic_memories WHERE namespace LIKE 'test:%'"
        )
    
    await pool.close()


@pytest.fixture
async def api_client(redis_client, qdrant_client, postgres_pool):
    """Create async HTTP client for API testing with proper lifespan handling."""
    from smrti.api.dependencies import set_storage_manager
    from smrti.api.storage_manager import StorageManager
    from smrti.storage.adapters import (
        RedisWorkingAdapter,
        RedisShortTermAdapter,
        QdrantLongTermAdapter,
        PostgresEpisodicAdapter,
        PostgresSemanticAdapter
    )
    from smrti.embedding.local import LocalEmbeddingProvider
    from smrti.core.config import get_settings
    
    settings = get_settings()
    
    # Initialize embedding provider
    embedding_provider = LocalEmbeddingProvider(
        model_name=settings.embedding_model,
        cache_size=settings.embedding_cache_size
    )
    
    # Initialize storage adapters
    working_adapter = RedisWorkingAdapter(redis_client)
    short_term_adapter = RedisShortTermAdapter(redis_client)
    long_term_adapter = QdrantLongTermAdapter(qdrant_client)
    episodic_adapter = PostgresEpisodicAdapter(postgres_pool)
    semantic_adapter = PostgresSemanticAdapter(postgres_pool)
    
    # Create storage manager
    storage_manager = StorageManager(
        working_adapter=working_adapter,
        short_term_adapter=short_term_adapter,
        long_term_adapter=long_term_adapter,
        episodic_adapter=episodic_adapter,
        semantic_adapter=semantic_adapter,
        embedding_provider=embedding_provider
    )
    
    # Set the global storage manager
    set_storage_manager(storage_manager)
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Clean up
    set_storage_manager(None)


class TestAPIHealthCheck:
    """Test API health check endpoint."""
    
    async def test_health_check_returns_200(self, api_client: AsyncClient):
        """Health check should return 200 OK."""
        response = await api_client.get("/health")
        assert response.status_code == 200
        
    async def test_health_check_includes_all_components(self, api_client: AsyncClient):
        """Health check should report status of all components."""
        response = await api_client.get("/health")
        data = response.json()
        
        assert "status" in data
        assert "components" in data
        assert "redis" in data["components"]
        assert "qdrant" in data["components"]
        assert "postgres" in data["components"]
        assert "embedding" in data["components"]


class TestAPIAuthentication:
    """Test API authentication."""
    
    async def test_store_without_auth_fails(self, api_client: AsyncClient):
        """Request without API key should fail."""
        response = await api_client.post(
            "/memory/store",
            json={
                "memory_type": "WORKING",
                "data": {"text": "test"}
            }
        )
        assert response.status_code == 401
        
    async def test_store_with_invalid_key_fails(self, api_client: AsyncClient):
        """Request with invalid API key should fail."""
        response = await api_client.post(
            "/memory/store",
            headers={"Authorization": "Bearer invalid-key"},
            json={
                "memory_type": "WORKING",
                "data": {"text": "test"}
            }
        )
        assert response.status_code == 401
        
    async def test_store_without_namespace_fails(self, api_client: AsyncClient):
        """Request without namespace header should fail."""
        response = await api_client.post(
            "/memory/store",
            headers={"Authorization": "Bearer dev-key-123"},
            json={
                "memory_type": "WORKING",
                "data": {"text": "test"}
            }
        )
        assert response.status_code == 400


class TestMemoryOperations:
    """Test memory CRUD operations."""
    
    @pytest.fixture
    def auth_headers(self):
        """Standard auth headers for testing."""
        return {
            "Authorization": "Bearer dev-key-123",
            "X-Namespace": "test:integration"
        }
    
    async def test_store_and_retrieve_working_memory(
        self,
        api_client: AsyncClient,
        auth_headers: dict
    ):
        """Store and retrieve a WORKING memory."""
        # Store memory
        store_response = await api_client.post(
            "/memory/store",
            headers=auth_headers,
            json={
                "memory_type": "WORKING",
                "data": {"text": "Test working memory"},
                "metadata": {"test": True}
            }
        )
        assert store_response.status_code == 201
        
        store_data = store_response.json()
        assert "memory_id" in store_data
        memory_id = store_data["memory_id"]
        
        # Retrieve memory
        retrieve_response = await api_client.post(
            "/memory/retrieve",
            headers=auth_headers,
            json={
                "memory_type": "WORKING",
                "query": "Test working memory",
                "limit": 10
            }
        )
        assert retrieve_response.status_code == 200
        
        retrieve_data = retrieve_response.json()
        assert retrieve_data["count"] > 0
        assert any(m["memory_id"] == memory_id for m in retrieve_data["memories"])
        
    async def test_delete_memory(
        self,
        api_client: AsyncClient,
        auth_headers: dict
    ):
        """Delete a memory."""
        # Store memory
        store_response = await api_client.post(
            "/memory/store",
            headers=auth_headers,
            json={
                "memory_type": "SHORT_TERM",
                "data": {"text": "Memory to delete"}
            }
        )
        memory_id = store_response.json()["memory_id"]
        
        # Delete memory
        delete_response = await api_client.delete(
            f"/memory/short_term/{memory_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        
        delete_data = delete_response.json()
        assert delete_data["deleted"] is True
        
    async def test_store_long_term_generates_embedding(
        self,
        api_client: AsyncClient,
        auth_headers: dict
    ):
        """Storing LONG_TERM memory should auto-generate embeddings."""
        response = await api_client.post(
            "/memory/store",
            headers=auth_headers,
            json={
                "memory_type": "LONG_TERM",
                "data": {"text": "Knowledge to be embedded"}
            }
        )
        assert response.status_code == 201
        
        # Should succeed without providing embedding
        data = response.json()
        assert "memory_id" in data
        
    async def test_retrieve_respects_limit(
        self,
        api_client: AsyncClient,
        auth_headers: dict
    ):
        """Retrieve should respect limit parameter."""
        # Store multiple memories
        for i in range(5):
            await api_client.post(
                "/memory/store",
                headers=auth_headers,
                json={
                    "memory_type": "WORKING",
                    "data": {"text": f"Memory {i}"}
                }
            )
        
        # Retrieve with limit
        response = await api_client.post(
            "/memory/retrieve",
            headers=auth_headers,
            json={
                "memory_type": "WORKING",
                "query": "Memory",
                "limit": 3
            }
        )
        
        data = response.json()
        assert len(data["memories"]) <= 3


class TestNamespaceIsolation:
    """Test namespace isolation."""
    
    async def test_different_namespaces_are_isolated(self, api_client: AsyncClient):
        """Memories in different namespaces should not be visible to each other."""
        # Store in namespace 1
        await api_client.post(
            "/memory/store",
            headers={
                "Authorization": "Bearer dev-key-123",
                "X-Namespace": "test:ns1"
            },
            json={
                "memory_type": "WORKING",
                "data": {"text": "Namespace 1 memory"}
            }
        )
        
        # Store in namespace 2
        await api_client.post(
            "/memory/store",
            headers={
                "Authorization": "Bearer dev-key-123",
                "X-Namespace": "test:ns2"
            },
            json={
                "memory_type": "WORKING",
                "data": {"text": "Namespace 2 memory"}
            }
        )
        
        # Retrieve from namespace 1
        response1 = await api_client.post(
            "/memory/retrieve",
            headers={
                "Authorization": "Bearer dev-key-123",
                "X-Namespace": "test:ns1"
            },
            json={
                "memory_type": "WORKING",
                "query": "memory",
                "limit": 10
            }
        )
        
        data1 = response1.json()
        memories1_text = [m["data"]["text"] for m in data1["memories"]]
        
        # Should only see namespace 1 memory
        assert "Namespace 1 memory" in memories1_text
        assert "Namespace 2 memory" not in memories1_text
