"""Qdrant adapter for LONG_TERM memory tier (persistent vector storage)."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
)

from smrti.core.exceptions import StorageError
from smrti.core.logging import get_logger
from smrti.core.metrics import storage_operation_duration_seconds, storage_operations_total

logger = get_logger(__name__)


class QdrantLongTermAdapter:
    """
    Qdrant adapter for LONG_TERM memory storage.
    
    Features:
    - Persistent storage (no TTL)
    - Vector similarity search
    - Metadata filtering
    - One collection per namespace prefix
    - Semantic retrieval via embeddings
    
    Performance target: < 200ms for retrieval
    """
    
    def __init__(
        self,
        client: AsyncQdrantClient,
        vector_size: int = 384,  # Default for all-MiniLM-L6-v2
        distance_metric: Distance = Distance.COSINE,
        collection_prefix: str = "smrti_long_term"
    ):
        """
        Initialize Qdrant adapter.
        
        Args:
            client: Async Qdrant client
            vector_size: Dimension of embedding vectors
            distance_metric: Distance metric for similarity (COSINE, EUCLID, DOT)
            collection_prefix: Prefix for collection names
        """
        self.client = client
        self.vector_size = vector_size
        self.distance_metric = distance_metric
        self.collection_prefix = collection_prefix
        self.memory_type = "LONG_TERM"
        
    def _get_collection_name(self, namespace: str) -> str:
        """
        Generate collection name from namespace.
        
        Uses namespace prefix (first two parts) to group related tenants.
        Example: tenant:123:user:456 -> smrti_long_term_tenant_123
        
        Args:
            namespace: Hierarchical namespace string
            
        Returns:
            Collection name
        """
        parts = namespace.split(":")
        prefix_parts = parts[:2] if len(parts) >= 2 else parts
        safe_prefix = "_".join(prefix_parts)
        return f"{self.collection_prefix}_{safe_prefix}"
    
    async def _ensure_collection(self, collection_name: str) -> None:
        """
        Create collection if it doesn't exist.
        
        Args:
            collection_name: Name of collection
        """
        try:
            # Check if collection exists
            collections = await self.client.get_collections()
            exists = any(c.name == collection_name for c in collections.collections)
            
            if not exists:
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=self.distance_metric
                    )
                )
                logger.info(
                    "qdrant_collection_created",
                    collection_name=collection_name,
                    vector_size=self.vector_size,
                    distance=str(self.distance_metric)
                )
        except Exception as e:
            logger.error(
                "qdrant_collection_creation_failed",
                collection_name=collection_name,
                error=str(e)
            )
            raise StorageError(f"Failed to create collection: {e}") from e
    
    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Store a long-term memory with vector embedding.
        
        Args:
            memory_id: Unique identifier for memory
            namespace: Hierarchical namespace for isolation
            data: Memory data (must contain 'text' field)
            embedding: Vector embedding of the text
            metadata: Optional metadata
            
        Returns:
            The memory_id
            
        Raises:
            StorageError: If storage fails
        """
        start_time = time.time()
        
        try:
            # Validate required fields
            if "text" not in data:
                raise StorageError("Memory data must contain 'text' field")
            
            if embedding is None:
                raise StorageError("Embedding is required for LONG_TERM storage")
            
            if len(embedding) != self.vector_size:
                raise StorageError(
                    f"Embedding size {len(embedding)} doesn't match "
                    f"expected {self.vector_size}"
                )
            
            # Get or create collection
            collection_name = self._get_collection_name(namespace)
            await self._ensure_collection(collection_name)
            
            # Prepare payload
            payload = {
                "memory_id": str(memory_id),
                "memory_type": self.memory_type,
                "namespace": namespace,
                "data": data,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Store point
            await self.client.upsert(
                collection_name=collection_name,
                points=[
                    PointStruct(
                        id=str(memory_id),
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
            
            duration = time.time() - start_time
            logger.info(
                "long_term_memory_stored",
                memory_id=str(memory_id),
                namespace=namespace,
                collection=collection_name,
                duration_ms=round(duration * 1000, 2)
            )
            
            storage_operations_total.labels(
                operation="store",
                memory_type=self.memory_type,
                status="success"
            ).inc()
            
            storage_operation_duration_seconds.labels(
                operation="store",
                memory_type=self.memory_type
            ).observe(duration)
            
            return memory_id
            
        except StorageError:
            raise
        except Exception as e:
            logger.error(
                "long_term_memory_store_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to store long-term memory: {e}") from e
    
    async def retrieve(
        self,
        namespace: str,
        query_embedding: Optional[List[float]],
        text_query: Optional[str],
        limit: int = 10,
        score_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve long-term memories using vector similarity search.
        
        Args:
            namespace: Namespace to search in
            query_embedding: Query vector for similarity search
            text_query: Not used (vector search only), kept for protocol compatibility
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of matching memories with similarity scores
        """
        start_time = time.time()
        
        try:
            if query_embedding is None:
                raise StorageError("Query embedding is required for LONG_TERM retrieval")
            
            if len(query_embedding) != self.vector_size:
                raise StorageError(
                    f"Query embedding size {len(query_embedding)} doesn't match "
                    f"expected {self.vector_size}"
                )
            
            collection_name = self._get_collection_name(namespace)
            
            # Check if collection exists
            collections = await self.client.get_collections()
            if not any(c.name == collection_name for c in collections.collections):
                logger.debug(
                    "long_term_collection_not_found",
                    collection_name=collection_name,
                    namespace=namespace
                )
                return []
            
            # Search with namespace filter
            search_result = await self.client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="namespace",
                            match=MatchValue(value=namespace)
                        )
                    ]
                ),
                limit=limit,
                score_threshold=score_threshold
            )
            
            # Format results
            results = []
            for scored_point in search_result:
                memory = scored_point.payload.copy()
                memory["similarity_score"] = scored_point.score
                results.append(memory)
            
            duration = time.time() - start_time
            logger.info(
                "long_term_memories_retrieved",
                namespace=namespace,
                count=len(results),
                duration_ms=round(duration * 1000, 2)
            )
            
            storage_operations_total.labels(
                operation="retrieve",
                memory_type=self.memory_type,
                status="success"
            ).inc()
            
            storage_operation_duration_seconds.labels(
                operation="retrieve",
                memory_type=self.memory_type
            ).observe(duration)
            
            return results
            
        except StorageError:
            raise
        except Exception as e:
            logger.error(
                "long_term_memory_retrieve_failed",
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve long-term memories: {e}") from e
    
    async def get(
        self,
        memory_id: UUID,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific long-term memory by ID.
        
        Args:
            memory_id: Memory identifier
            namespace: Namespace for isolation
            
        Returns:
            Memory data or None if not found
        """
        start_time = time.time()
        
        try:
            collection_name = self._get_collection_name(namespace)
            
            # Check if collection exists
            collections = await self.client.get_collections()
            if not any(c.name == collection_name for c in collections.collections):
                return None
            
            # Retrieve point
            points = await self.client.retrieve(
                collection_name=collection_name,
                ids=[str(memory_id)]
            )
            
            if not points:
                return None
            
            point = points[0]
            
            # Verify namespace (security)
            if point.payload.get("namespace") != namespace:
                logger.warning(
                    "long_term_memory_namespace_mismatch",
                    memory_id=str(memory_id),
                    expected_namespace=namespace,
                    actual_namespace=point.payload.get("namespace")
                )
                return None
            
            duration = time.time() - start_time
            logger.debug(
                "long_term_memory_retrieved",
                memory_id=str(memory_id),
                namespace=namespace,
                duration_ms=round(duration * 1000, 2)
            )
            
            return point.payload
            
        except Exception as e:
            logger.error(
                "long_term_memory_get_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to get long-term memory: {e}") from e
    
    async def delete(
        self,
        memory_id: UUID,
        namespace: str
    ) -> bool:
        """
        Delete a specific long-term memory.
        
        Args:
            memory_id: Memory identifier
            namespace: Namespace for isolation
            
        Returns:
            True if deleted, False if not found
        """
        start_time = time.time()
        
        try:
            # First verify the memory exists and belongs to namespace
            existing = await self.get(memory_id, namespace)
            if existing is None:
                return False
            
            collection_name = self._get_collection_name(namespace)
            
            # Delete point
            await self.client.delete(
                collection_name=collection_name,
                points_selector=[str(memory_id)]
            )
            
            duration = time.time() - start_time
            logger.info(
                "long_term_memory_deleted",
                memory_id=str(memory_id),
                namespace=namespace,
                duration_ms=round(duration * 1000, 2)
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "long_term_memory_delete_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to delete long-term memory: {e}") from e
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check Qdrant connection health.
        
        Returns:
            Status dictionary with connection info
        """
        try:
            start_time = time.time()
            
            # Get collections to verify connection
            collections = await self.client.get_collections()
            latency = (time.time() - start_time) * 1000
            
            return {
                "status": "connected",
                "backend": "Qdrant",
                "memory_type": self.memory_type,
                "latency_ms": round(latency, 2),
                "collections_count": len(collections.collections),
                "vector_size": self.vector_size,
                "distance_metric": str(self.distance_metric)
            }
            
        except Exception as e:
            logger.error("long_term_memory_health_check_failed", error=str(e))
            return {
                "status": "error",
                "backend": "Qdrant",
                "memory_type": self.memory_type,
                "error": str(e)
            }
