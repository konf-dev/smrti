"""Redis adapter for WORKING memory tier (5-minute TTL)."""

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


class RedisWorkingAdapter:
    """
    Storage adapter for WORKING memory using Redis.
    
    Characteristics:
    - Storage: In-memory Redis with TTL
    - TTL: 300 seconds (5 minutes)
    - Key pattern: working:{namespace}:{memory_id}
    - Retrieval: Scan by namespace pattern, sort by timestamp
    - Use case: Current context, immediate tasks
    
    Performance:
    - Store: < 10ms (p95)
    - Retrieve: < 5ms (p95)
    - Persistence: None (volatile, expires after TTL)
    """

    def __init__(self, redis_client: Redis, ttl: int = 300):
        """
        Initialize Redis Working adapter.
        
        Args:
            redis_client: Async Redis client
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)
        """
        self.redis = redis_client
        self.ttl = ttl
        self.memory_type = "WORKING"

    def _make_key(self, namespace: str, memory_id: UUID) -> str:
        """Generate Redis key for a memory."""
        return f"working:{namespace}:{memory_id}"

    def _make_pattern(self, namespace: str) -> str:
        """Generate Redis scan pattern for namespace."""
        return f"working:{namespace}:*"

    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Dict[str, Any],
    ) -> UUID:
        """
        Store a working memory in Redis with TTL.
        
        Args:
            memory_id: Unique identifier
            namespace: Isolation key
            data: Memory data (must contain 'text' field)
            embedding: Not used for working memory (ignored)
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
            memory_obj = {
                "memory_id": str(memory_id),
                "memory_type": self.memory_type,
                "namespace": namespace,
                "data": data,
                "metadata": metadata,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Store in Redis with TTL
            key = self._make_key(namespace, memory_id)
            await self.redis.setex(
                key,
                self.ttl,
                json.dumps(memory_obj)
            )

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
                "working_memory_stored",
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
                "working_memory_store_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e),
                exc_info=True
            )
            raise StorageError(f"Failed to store working memory: {e}") from e

    async def retrieve(
        self,
        namespace: str,
        query: Optional[str],
        filters: Optional[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve working memories for a namespace.
        
        Args:
            namespace: Isolation key
            query: Text search query (simple substring match)
            filters: Metadata filters (not implemented for working memory)
            limit: Maximum results to return
            
        Returns:
            List of memories, sorted by creation time (newest first)
        """
        start_time = time.time()
        
        try:
            # Scan for keys matching namespace pattern
            pattern = self._make_pattern(namespace)
            cursor = 0
            keys = []
            
            while True:
                cursor, batch = await self.redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )
                keys.extend(batch)
                if cursor == 0:
                    break

            # Retrieve all memories
            memories = []
            if keys:
                values = await self.redis.mget(keys)
                for value in values:
                    if value:
                        memory = json.loads(value)
                        
                        # Apply text search filter if provided
                        if query:
                            text = memory.get("data", {}).get("text", "")
                            if query.lower() not in text.lower():
                                continue
                        
                        memories.append(memory)

            # Sort by created_at (newest first)
            memories.sort(
                key=lambda m: m.get("created_at", ""),
                reverse=True
            )

            # Apply limit
            results = memories[:limit]

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
                "working_memories_retrieved",
                namespace=namespace,
                query=query,
                count=len(results),
                duration_ms=duration * 1000
            )

            return results

        except Exception as e:
            storage_operations_total.labels(
                operation="retrieve",
                memory_type=self.memory_type,
                status="error"
            ).inc()
            
            logger.error(
                "working_memory_retrieve_failed",
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve working memories: {e}") from e

    async def get(
        self,
        memory_id: UUID,
        namespace: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific working memory by ID.
        
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
                    "working_memory_not_found",
                    memory_id=str(memory_id),
                    namespace=namespace
                )
                return None

            memory = json.loads(value)
            
            # Verify namespace matches (security)
            if memory.get("namespace") != namespace:
                logger.warning(
                    "working_memory_namespace_mismatch",
                    memory_id=str(memory_id),
                    requested_namespace=namespace,
                    actual_namespace=memory.get("namespace")
                )
                return None

            return memory

        except Exception as e:
            logger.error(
                "working_memory_get_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to get working memory: {e}") from e

    async def delete(
        self,
        memory_id: UUID,
        namespace: str,
    ) -> bool:
        """
        Delete a working memory.
        
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

            key = self._make_key(namespace, memory_id)
            deleted_count = await self.redis.delete(key)
            
            if deleted_count > 0:
                logger.info(
                    "working_memory_deleted",
                    memory_id=str(memory_id),
                    namespace=namespace
                )
                return True
            
            return False

        except Exception as e:
            logger.error(
                "working_memory_delete_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to delete working memory: {e}") from e

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
            logger.error("working_memory_health_check_failed", error=str(e))
            return {
                "status": "error",
                "backend": "Redis",
                "memory_type": self.memory_type,
                "error": str(e)
            }
