"""PostgreSQL adapter for EPISODIC memory tier (time-series events)."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

from smrti.core.exceptions import StorageError
from smrti.core.logging import get_logger
from smrti.core.metrics import storage_operation_duration_seconds, storage_operations_total

logger = get_logger(__name__)


class PostgresEpisodicAdapter:
    """
    PostgreSQL adapter for EPISODIC memory storage.
    
    Features:
    - Persistent time-series storage
    - Time-range queries
    - Full-text search
    - Event type filtering
    - Automatic search vector indexing
    
    Performance target: < 100ms for retrieval
    """
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize PostgreSQL adapter.
        
        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool
        self.memory_type = "EPISODIC"
        
    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Store an episodic memory.
        
        Args:
            memory_id: Unique identifier for memory
            namespace: Hierarchical namespace for isolation
            data: Memory data (must contain 'text' field)
            embedding: Not used for episodic (kept for protocol compatibility)
            metadata: Optional metadata (can include 'event_type', 'event_time')
            
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
            
            metadata = metadata or {}
            
            # Extract event_type and event_time from metadata if present
            event_type = metadata.get("event_type")
            event_time = metadata.get("event_time")
            
            # Convert event_time string to datetime if needed
            if event_time and isinstance(event_time, str):
                event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
            
            # Insert memory
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO episodic_memories 
                        (memory_id, namespace, memory_type, text, data, metadata, 
                         event_type, event_time, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (memory_id) DO UPDATE SET
                        text = EXCLUDED.text,
                        data = EXCLUDED.data,
                        metadata = EXCLUDED.metadata,
                        event_type = EXCLUDED.event_type,
                        event_time = EXCLUDED.event_time
                    """,
                    str(memory_id),
                    namespace,
                    self.memory_type,
                    data["text"],
                    json.dumps(data),
                    json.dumps(metadata),
                    event_type,
                    event_time,
                    datetime.now(timezone.utc)
                )
            
            duration = time.time() - start_time
            logger.info(
                "episodic_memory_stored",
                memory_id=str(memory_id),
                namespace=namespace,
                event_type=event_type,
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
                "episodic_memory_store_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to store episodic memory: {e}") from e
    
    async def retrieve(
        self,
        namespace: str,
        query_embedding: Optional[List[float]],
        text_query: Optional[str],
        limit: int = 10,
        time_range: Optional[tuple] = None,
        event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve episodic memories.
        
        Args:
            namespace: Namespace to search in
            query_embedding: Not used (kept for protocol compatibility)
            text_query: Optional full-text search query
            limit: Maximum number of results
            time_range: Optional tuple of (start_time, end_time) datetimes
            event_type: Optional event type filter
            
        Returns:
            List of matching memories ordered by time (newest first)
        """
        start_time = time.time()
        
        try:
            # Build dynamic query
            conditions = ["namespace = $1"]
            params = [namespace]
            param_counter = 2
            
            # Time range filter
            if time_range:
                start_dt, end_dt = time_range
                conditions.append(f"created_at BETWEEN ${param_counter} AND ${param_counter + 1}")
                params.extend([start_dt, end_dt])
                param_counter += 2
            
            # Event type filter
            if event_type:
                conditions.append(f"event_type = ${param_counter}")
                params.append(event_type)
                param_counter += 1
            
            # Full-text search
            if text_query:
                conditions.append(f"search_vector @@ plainto_tsquery('english', ${param_counter})")
                params.append(text_query)
                param_counter += 1
            
            where_clause = " AND ".join(conditions)
            
            # Add limit
            params.append(limit)
            limit_clause = f"${param_counter}"
            
            query = f"""
                SELECT 
                    memory_id, namespace, memory_type, text, data, metadata,
                    created_at, event_time, event_type
                FROM episodic_memories
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit_clause}
            """
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
            
            # Format results
            results = []
            for row in rows:
                memory = {
                    "memory_id": str(row["memory_id"]),
                    "namespace": row["namespace"],
                    "memory_type": row["memory_type"],
                    "data": json.loads(row["data"]) if isinstance(row["data"], str) else row["data"],
                    "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
                    "created_at": row["created_at"].isoformat(),
                }
                
                if row["event_time"]:
                    memory["event_time"] = row["event_time"].isoformat()
                if row["event_type"]:
                    memory["event_type"] = row["event_type"]
                    
                results.append(memory)
            
            duration = time.time() - start_time
            logger.info(
                "episodic_memories_retrieved",
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
            
        except Exception as e:
            logger.error(
                "episodic_memory_retrieve_failed",
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve episodic memories: {e}") from e
    
    async def get(
        self,
        memory_id: UUID,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific episodic memory by ID.
        
        Args:
            memory_id: Memory identifier
            namespace: Namespace for isolation
            
        Returns:
            Memory data or None if not found
        """
        start_time = time.time()
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT 
                        memory_id, namespace, memory_type, text, data, metadata,
                        created_at, event_time, event_type
                    FROM episodic_memories
                    WHERE memory_id = $1 AND namespace = $2
                    """,
                    str(memory_id),
                    namespace
                )
            
            if not row:
                return None
            
            memory = {
                "memory_id": str(row["memory_id"]),
                "namespace": row["namespace"],
                "memory_type": row["memory_type"],
                "data": json.loads(row["data"]) if isinstance(row["data"], str) else row["data"],
                "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
                "created_at": row["created_at"].isoformat(),
            }
            
            if row["event_time"]:
                memory["event_time"] = row["event_time"].isoformat()
            if row["event_type"]:
                memory["event_type"] = row["event_type"]
            
            duration = time.time() - start_time
            logger.debug(
                "episodic_memory_retrieved",
                memory_id=str(memory_id),
                namespace=namespace,
                duration_ms=round(duration * 1000, 2)
            )
            
            return memory
            
        except Exception as e:
            logger.error(
                "episodic_memory_get_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to get episodic memory: {e}") from e
    
    async def delete(
        self,
        memory_id: UUID,
        namespace: str
    ) -> bool:
        """
        Delete a specific episodic memory.
        
        Args:
            memory_id: Memory identifier
            namespace: Namespace for isolation
            
        Returns:
            True if deleted, False if not found
        """
        start_time = time.time()
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM episodic_memories
                    WHERE memory_id = $1 AND namespace = $2
                    """,
                    str(memory_id),
                    namespace
                )
            
            # Parse result like "DELETE 1" to get count
            deleted_count = int(result.split()[-1]) if result else 0
            
            if deleted_count > 0:
                duration = time.time() - start_time
                logger.info(
                    "episodic_memory_deleted",
                    memory_id=str(memory_id),
                    namespace=namespace,
                    duration_ms=round(duration * 1000, 2)
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(
                "episodic_memory_delete_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to delete episodic memory: {e}") from e
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check PostgreSQL connection health.
        
        Returns:
            Status dictionary with connection info
        """
        try:
            start_time = time.time()
            
            async with self.pool.acquire() as conn:
                # Simple query to check connectivity
                version = await conn.fetchval("SELECT version()")
                
                # Get table stats
                stats = await conn.fetchrow(
                    """
                    SELECT 
                        COUNT(*) as total_memories,
                        COUNT(DISTINCT namespace) as unique_namespaces
                    FROM episodic_memories
                    """
                )
            
            latency = (time.time() - start_time) * 1000
            
            return {
                "status": "connected",
                "backend": "PostgreSQL",
                "memory_type": self.memory_type,
                "latency_ms": round(latency, 2),
                "total_memories": stats["total_memories"],
                "unique_namespaces": stats["unique_namespaces"],
                "pool_size": self.pool.get_size(),
                "pool_free": self.pool.get_size() - self.pool.get_size()  # Simplified
            }
            
        except Exception as e:
            logger.error("episodic_memory_health_check_failed", error=str(e))
            return {
                "status": "error",
                "backend": "PostgreSQL",
                "memory_type": self.memory_type,
                "error": str(e)
            }
