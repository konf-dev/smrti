"""
tests/mocks/adapters.py - Mock adapters for testing

Provides mock implementations of storage and embedding adapters
for testing without requiring actual backend services.
"""

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from unittest.mock import Mock

from smrti.core.base import BaseAdapter, BaseEmbeddingProvider, BaseTierStore
from smrti.core.exceptions import AdapterError, StorageError
from smrti.schemas.models import MemoryQuery, RecordEnvelope


class MockTierStore(BaseTierStore):
    """Mock tier store for testing."""
    
    def __init__(self, tier_name: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(tier_name, config)
        
        # In-memory storage
        self._records: Dict[str, RecordEnvelope] = {}
        self._failure_mode = False
        self._slow_mode = False
        self._capacity_limit = config.get("capacity_limit", 1000) if config else 1000
    
    def set_failure_mode(self, enabled: bool) -> None:
        """Enable/disable failure mode for testing error handling."""
        self._failure_mode = enabled
    
    def set_slow_mode(self, enabled: bool) -> None:
        """Enable/disable slow mode for testing timeouts."""
        self._slow_mode = enabled
    
    async def store_record(self, record: RecordEnvelope) -> bool:
        """Store a record in the mock tier."""
        if self._failure_mode:
            raise StorageError("Mock failure mode enabled")
        
        if self._slow_mode:
            await asyncio.sleep(2.0)  # Simulate slow operation
        
        if len(self._records) >= self._capacity_limit:
            from smrti.core.exceptions import CapacityExceededError
            raise CapacityExceededError(
                "Mock tier capacity exceeded",
                limit_type="record_count",
                current_value=len(self._records),
                limit_value=self._capacity_limit
            )
        
        self._validate_record(record)
        
        # Simulate some processing time
        await asyncio.sleep(0.01)
        
        self._records[record.record_id] = record
        self._update_stats("store", 1, len(str(record)))
        
        return True
    
    async def retrieve_records(
        self, 
        query: MemoryQuery,
        context: Optional[Dict[str, Any]] = None
    ) -> List[RecordEnvelope]:
        """Retrieve records matching the query."""
        if self._failure_mode:
            raise StorageError("Mock failure mode enabled")
        
        if self._slow_mode:
            await asyncio.sleep(1.0)
        
        self._validate_query(query)
        
        # Simple mock filtering logic
        results = []
        
        for record in self._records.values():
            # Tenant isolation
            if record.tenant_id != query.tenant_id:
                continue
            
            # Namespace filtering
            if query.namespace != "*" and record.namespace != query.namespace:
                continue
            
            # Time range filtering
            if query.time_range_hours:
                cutoff_time = datetime.utcnow() - timedelta(hours=query.time_range_hours)
                if record.created_at and record.created_at < cutoff_time:
                    continue
            
            # Simple text matching (if query has text)
            if query.query_text:
                content_text = str(record.content).lower()
                query_text = query.query_text.lower()
                
                # Simple keyword matching
                query_words = set(query_text.split())
                content_words = set(content_text.split())
                
                if not (query_words & content_words):  # No intersection
                    continue
            
            results.append(record)
        
        # Apply limit
        results = results[:query.limit]
        
        self._update_stats("retrieve", len(results))
        
        # Simulate processing time proportional to results
        await asyncio.sleep(0.001 * len(results))
        
        return results
    
    async def delete_record(self, record_id: str, tenant_id: str) -> bool:
        """Delete a record by ID."""
        if self._failure_mode:
            raise StorageError("Mock failure mode enabled")
        
        if record_id in self._records:
            record = self._records[record_id]
            
            # Check tenant isolation
            if record.tenant_id != tenant_id:
                return False
            
            del self._records[record_id]
            self._update_stats("delete", 1, len(str(record)))
            return True
        
        return False
    
    async def get_record_count(self) -> int:
        """Get total number of records."""
        return len(self._records)
    
    async def clear_all(self) -> int:
        """Clear all records (for testing)."""
        count = len(self._records)
        self._records.clear()
        return count
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Mock health check."""
        return {
            "tier_name": self.tier_name,
            "record_count": len(self._records),
            "capacity_usage": len(self._records) / self._capacity_limit,
            "failure_mode": self._failure_mode,
            "slow_mode": self._slow_mode
        }


class MockRedisAdapter(MockTierStore):
    """Mock Redis adapter with TTL support."""
    
    def __init__(self, **config):
        super().__init__("redis", config)
        self._ttl_records: Dict[str, datetime] = {}
        self._supports_ttl = True
    
    async def store_record(self, record: RecordEnvelope, ttl: Optional[int] = None) -> bool:
        """Store record with optional TTL."""
        success = await super().store_record(record)
        
        if success and ttl:
            expiry_time = datetime.utcnow() + timedelta(seconds=ttl)
            self._ttl_records[record.record_id] = expiry_time
        
        return success
    
    async def _cleanup_expired(self):
        """Clean up expired records."""
        now = datetime.utcnow()
        expired_ids = [
            record_id for record_id, expiry in self._ttl_records.items()
            if expiry <= now
        ]
        
        for record_id in expired_ids:
            if record_id in self._records:
                del self._records[record_id]
            del self._ttl_records[record_id]
        
        return len(expired_ids)


class MockChromaDBAdapter(MockTierStore):
    """Mock ChromaDB adapter with vector similarity."""
    
    def __init__(self, **config):
        super().__init__("chroma", config)
        self._supports_similarity_search = True
    
    async def retrieve_records(
        self, 
        query: MemoryQuery,
        context: Optional[Dict[str, Any]] = None
    ) -> List[RecordEnvelope]:
        """Retrieve with mock similarity search."""
        # Get base results
        results = await super().retrieve_records(query, context)
        
        # If query has embedding, simulate similarity scoring
        if query.embedding and results:
            scored_results = []
            
            for record in results:
                if record.embedding:
                    # Mock similarity calculation (random for testing)
                    import random
                    similarity = random.uniform(0.1, 1.0)
                    
                    if similarity >= query.similarity_threshold:
                        scored_results.append((similarity, record))
            
            # Sort by similarity (descending)
            scored_results.sort(key=lambda x: x[0], reverse=True)
            results = [record for _, record in scored_results]
        
        return results


class MockPostgreSQLAdapter(MockTierStore):
    """Mock PostgreSQL adapter with temporal queries."""
    
    def __init__(self, **config):
        super().__init__("postgres", config)
        self._event_sequences: Dict[str, List[str]] = defaultdict(list)
    
    async def store_record(self, record: RecordEnvelope) -> bool:
        """Store with event sequence tracking."""
        success = await super().store_record(record)
        
        if success:
            # Track in event sequence
            session_id = record.metadata.get("session_id", "default")
            self._event_sequences[session_id].append(record.record_id)
        
        return success
    
    async def get_event_sequence(self, session_id: str) -> List[RecordEnvelope]:
        """Get records in temporal order for a session."""
        record_ids = self._event_sequences.get(session_id, [])
        return [self._records[rid] for rid in record_ids if rid in self._records]


class MockNeo4jAdapter(MockTierStore):
    """Mock Neo4j adapter with relationship tracking."""
    
    def __init__(self, **config):
        super().__init__("neo4j", config)
        self._relationships: Dict[str, Set[str]] = defaultdict(set)
    
    async def store_record(self, record: RecordEnvelope) -> bool:
        """Store with relationship tracking."""
        success = await super().store_record(record)
        
        if success:
            # Extract entities and create mock relationships
            content_text = str(record.content).lower()
            entities = set(word for word in content_text.split() if len(word) > 4)
            
            for entity in entities:
                self._relationships[record.record_id].add(entity)
        
        return success
    
    async def find_related_records(self, record_id: str) -> List[RecordEnvelope]:
        """Find records with shared entities."""
        if record_id not in self._relationships:
            return []
        
        target_entities = self._relationships[record_id]
        related_records = []
        
        for rid, entities in self._relationships.items():
            if rid != record_id and (target_entities & entities):
                if rid in self._records:
                    related_records.append(self._records[rid])
        
        return related_records


class MockElasticsearchAdapter(MockTierStore):
    """Mock Elasticsearch adapter with full-text search."""
    
    def __init__(self, **config):
        super().__init__("elasticsearch", config)
        self._text_index: Dict[str, Set[str]] = defaultdict(set)
    
    async def store_record(self, record: RecordEnvelope) -> bool:
        """Store with text indexing."""
        success = await super().store_record(record)
        
        if success:
            # Build text index
            content_text = str(record.content).lower()
            words = set(word.strip('.,!?;:') for word in content_text.split())
            
            for word in words:
                self._text_index[word].add(record.record_id)
        
        return success
    
    async def full_text_search(self, query_text: str, limit: int = 10) -> List[RecordEnvelope]:
        """Perform full-text search."""
        query_words = set(word.lower().strip('.,!?;:') for word in query_text.split())
        
        # Find records containing any query words
        matching_records = set()
        for word in query_words:
            if word in self._text_index:
                matching_records.update(self._text_index[word])
        
        # Return record objects
        results = []
        for record_id in list(matching_records)[:limit]:
            if record_id in self._records:
                results.append(self._records[record_id])
        
        return results


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Mock embedding provider for testing."""
    
    def __init__(
        self, 
        name: str = "mock_embedder",
        embedding_dim: int = 384,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(name, "mock-model", embedding_dim, 512, config)
        self._deterministic = config.get("deterministic", True) if config else True
    
    async def embed_text(self, text: str) -> List[float]:
        """Generate mock embeddings."""
        self._validate_text(text)
        
        # Check cache
        cached = self._check_cache(text)
        if cached:
            return cached
        
        # Simulate processing time
        await asyncio.sleep(0.01)
        
        if self._deterministic:
            # Generate deterministic embedding based on text hash
            import hashlib
            text_hash = int(hashlib.md5(text.encode()).hexdigest(), 16)
            
            # Use hash to generate consistent values
            import random
            random.seed(text_hash % (2**32))
            
            embedding = [random.uniform(-1, 1) for _ in range(self.embedding_dim)]
        else:
            # Random embedding
            import random
            embedding = [random.uniform(-1, 1) for _ in range(self.embedding_dim)]
        
        # Cache embedding
        self._cache_embedding(text, embedding)
        
        self._embeddings_generated += 1
        
        return embedding
    
    async def embed_texts_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        results = []
        for text in texts:
            embedding = await self.embed_text(text)
            results.append(embedding)
        
        self._batch_operations += 1
        return results
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Mock health check."""
        return {
            "provider_name": self.name,
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "embeddings_generated": self._embeddings_generated,
            "deterministic_mode": self._deterministic
        }


class MockFailingAdapter(BaseAdapter):
    """Mock adapter that always fails - for testing error handling."""
    
    def __init__(self, name: str = "failing_adapter"):
        super().__init__(name)
        self.failure_count = 0
    
    async def any_operation(self) -> None:
        """Always fails."""
        self.failure_count += 1
        raise AdapterError(f"Mock failure #{self.failure_count}")
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Health check that fails."""
        raise AdapterError("Health check failed")


class MockSlowAdapter(BaseAdapter):
    """Mock adapter that simulates slow operations."""
    
    def __init__(self, name: str = "slow_adapter", delay: float = 2.0):
        super().__init__(name)
        self.delay = delay
        self.operations = 0
    
    async def slow_operation(self) -> str:
        """Slow operation for testing timeouts."""
        self.operations += 1
        await asyncio.sleep(self.delay)
        return f"operation_{self.operations}_completed"
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Slow health check."""
        await asyncio.sleep(self.delay / 2)
        return {
            "adapter_name": self.name,
            "delay": self.delay,
            "operations": self.operations
        }


def create_mock_registry():
    """Create a registry with mock adapters for testing."""
    from smrti.core.registry import AdapterRegistry
    
    registry = AdapterRegistry()
    
    # Register mock storage adapters
    registry.register_tier_store("redis", MockRedisAdapter())
    registry.register_tier_store("chroma", MockChromaDBAdapter())
    registry.register_tier_store("postgres", MockPostgreSQLAdapter())
    registry.register_tier_store("neo4j", MockNeo4jAdapter())
    registry.register_tier_store("elasticsearch", MockElasticsearchAdapter())
    
    # Register mock embedding provider
    registry.register_embedding_provider("mock", MockEmbeddingProvider())
    
    return registry


def create_test_record(
    record_id: Optional[str] = None,
    tenant_id: str = "test_tenant",
    namespace: str = "test_namespace",
    content: str = "test content",
    metadata: Optional[Dict[str, Any]] = None
) -> RecordEnvelope:
    """Create a test record envelope."""
    from smrti.schemas.models import TextContent
    import uuid
    
    return RecordEnvelope(
        record_id=record_id or str(uuid.uuid4()),
        tenant_id=tenant_id,
        namespace=namespace,
        content=TextContent(text=content),
        metadata=metadata or {},
        created_at=datetime.utcnow()
    )