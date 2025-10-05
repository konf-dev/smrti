"""Redis adapter for SHORT_TERM memory tier (1-hour TTL)."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from redis.asyncio import Redis

from smrti.core.exceptions import StorageError
from smrti.core.logging import get_logger
from smrti.core.metrics import storage_operation_duration_seconds, storage_operations_total

logger = get_logger(__name__)


class RedisShortTermAdapter:
    """
    Storage adapter for SHORT_TERM memory using Redis.
    
    Characteristics:
    - Storage: In-memory Redis with TTL
    - TTL: 3600 seconds (1 hour)
    - Key pattern: short_term:{namespace}:{memory_id}
    - Retrieval: Sorted set for time ordering
    - Use case: Session summary, recent history
    
    Performance:
    - Store: < 10ms (p95)
    - Retrieve: < 10ms (p95)
    - Persistence: None (volatile, expires after TTL)
    """

    def __init__(self, redis_client: Redis, ttl: int = 3600):
        """
        Initialize Redis Short-Term adapter.
        
        Args:
            redis_client: Async Redis client
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)
        """
        self.redis = redis_client
        self.ttl = ttl
        self.memory_type = "SHORT_TERM"

    def _make_key(self, namespace: str, memory_id: UUID) -> str:
        """Generate Redis key for a memory."""
        return f"short_term:{namespace}:{memory_id}"

    def _make_index_key(self, namespace: str) -> str:
        """Generate Redis sorted set key for time-ordered index."""
        return f"short_term_index:{namespace}"

    def _make_pattern(self, namespace: str) -> str:
        """Generate Redis scan pattern for namespace."""
        return f"short_term:{namespace}:*"

    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Dict[str, Any],
    ) -> UUID:
        """
        Store a short-term memory in Redis with TTL.
        
        Args:
            memory_id: Unique identifier
            namespace: Isolation key
            data: Memory data (must contain 'text' field)
            embedding: Not used for short-term memory (ignored)
            metadata: Additional metadata
            
        Returns:
            memory_id: Confirmation
            
        Raises:
            StorageError: If Redis operation fails
        """
        start_time = time.time()
        
        try:
            # Validate data
            if "text" not in data:
                raise ValueError("data must contain 'text' field")

            # Build memory object
            timestamp = time.time()
            memory_obj = {
                "memory_id": str(memory_id),
                "memory_type": self.memory_type,
                "namespace": namespace,
                "data": data,
                "metadata": metadata,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "timestamp": timestamp,
            }

            # Use pipeline for atomic operations
            async with self.redis.pipeline() as pipe:
                # Store memory with TTL
                key = self._make_key(namespace, memory_id)
                pipe.setex(key, self.ttl, json.dumps(memory_obj))
                
                # Add to sorted set index (score = timestamp)
                index_key = self._make_index_key(namespace)
                pipe.zadd(index_key, {str(memory_id): timestamp})
                pipe.expire(index_key, self.ttl)
                
                await pipe.execute()

            # Record metrics
            duration = time.time() - start_time
            storage_operation_duration_seconds.labels(
                operation="store",
                memory_type=self.memory_type
            ).observe(duration)
            storage_operations_total.labels(
                operation="store",
                memory_type=self.memory_type,
                status="success"
            ).inc()

            logger.info(
                "short_term_memory_stored",
                memory_id=str(memory_id),
                namespace=namespace,
                ttl=self.ttl,
                duration_ms=duration * 1000
            )

            return memory_id

        except Exception as e:
            storage_operations_total.labels(
                operation="store",
                memory_type=self.memory_type,
                status="error"
            ).inc()
            
            logger.error(
                "short_term_memory_store_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e),
                exc_info=True
            )
            raise StorageError(f"Failed to store short-term memory: {e}") from e

    async def retrieve(
        self,
        namespace: str,
        query: Optional[str],
        filters: Optional[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve short-term memories for a namespace.
        
        Uses sorted set index for efficient time-ordered retrieval.
        
        Args:
            namespace: Isolation key
            query: Text search query (simple substring match)
            filters: Metadata filters (not implemented for short-term memory)
            limit: Maximum results to return
            
        Returns:
            List of memories, sorted by creation time (newest first)
        """
        start_time = time.time()
        
        try:
            # Get memory IDs from sorted set (newest first)
            index_key = self._make_index_key(namespace)
            memory_ids = await self.redis.zrevrange(
                index_key,
                0,
                -1  # Get all, we'll filter and limit later
            )

            if not memory_ids:
                return []

            # Retrieve memories
            memories = []
            for memory_id_bytes in memory_ids:
                memory_id = memory_id_bytes.decode() if isinstance(memory_id_bytes, bytes) else memory_id_bytes
                key = self._make_key(namespace, UUID(memory_id))
                value = await self.redis.get(key)
                
                if value:
                    memory = json.loads(value)
                    
                    # Apply text search filter if provided
                    if query:
                        text = memory.get("data", {}).get("text", "")
                        if query.lower() not in text.lower():
                            continue
                    
                    memories.append(memory)
                    
                    # Stop if we have enough results
                    if len(memories) >= limit:
                        break

            # Record metrics
            duration = time.time() - start_time
            storage_operation_duration_seconds.labels(
                operation="retrieve",
                memory_type=self.memory_type
            ).observe(duration)
            storage_operations_total.labels(
                operation="retrieve",
                memory_type=self.memory_type,
                status="success"
            ).inc()

            logger.debug(
                "short_term_memories_retrieved",
                namespace=namespace,
                query=query,
                count=len(memories),
                duration_ms=duration * 1000
            )

            return memories

        except Exception as e:
            storage_operations_total.labels(
                operation="retrieve",
                memory_type=self.memory_type,
                status="error"
            ).inc()
            
            logger.error(
                "short_term_memory_retrieve_failed",
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve short-term memories: {e}") from e

    async def get(
        self,
        memory_id: UUID,
        namespace: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific short-term memory by ID.
        
        Args:
            memory_id: Memory identifier
            namespace: Isolation key (for authorization)
            
        Returns:
            Memory data or None if not found/expired
        """
        try:
            key = self._make_key(namespace, memory_id)
            value = await self.redis.get(key)
            
            if not value:
                logger.debug(
                    "short_term_memory_not_found",
                    memory_id=str(memory_id),
                    namespace=namespace
                )
                return None

            memory = json.loads(value)
            
            # Verify namespace matches (security)
            if memory.get("namespace") != namespace:
                logger.warning(
                    "short_term_memory_namespace_mismatch",
                    memory_id=str(memory_id),
                    requested_namespace=namespace,
                    actual_namespace=memory.get("namespace")
                )
                return None

            return memory

        except Exception as e:
            logger.error(
                "short_term_memory_get_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to get short-term memory: {e}") from e

    async def delete(
        self,
        memory_id: UUID,
        namespace: str,
    ) -> bool:
        """
        Delete a short-term memory.
        
        Args:
            memory_id: Memory identifier
            namespace: Isolation key
            
        Returns:
            True if deleted, False if not found
        """
        try:
            # Verify namespace matches before deleting
            existing = await self.get(memory_id, namespace)
            if not existing:
                return False

            # Delete from both key and sorted set index
            async with self.redis.pipeline() as pipe:
                key = self._make_key(namespace, memory_id)
                pipe.delete(key)
                
                index_key = self._make_index_key(namespace)
                pipe.zrem(index_key, str(memory_id))
                
                results = await pipe.execute()
            
            deleted = results[0] > 0
            
            if deleted:
                logger.info(
                    "short_term_memory_deleted",
                    memory_id=str(memory_id),
                    namespace=namespace
                )
            
            return deleted

        except Exception as e:
            logger.error(
                "short_term_memory_delete_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to delete short-term memory: {e}") from e

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Redis connection health.
        
        Returns:
            Status dictionary with connection info
        """
        try:
            start_time = time.time()
            pong = await self.redis.ping()
            latency = (time.time() - start_time) * 1000

            return {
                "status": "connected" if pong else "error",
                "backend": "Redis",
                "memory_type": self.memory_type,
                "latency_ms": round(latency, 2),
                "ttl_seconds": self.ttl
            }

        except Exception as e:
            logger.error("short_term_memory_health_check_failed", error=str(e))
            return {
                "status": "error",
                "backend": "Redis",
                "memory_type": self.memory_type,
                "error": str(e)
            }
