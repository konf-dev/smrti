"""PostgreSQL adapter for SEMANTIC memory tier (structured knowledge)."""

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


class PostgresSemanticAdapter:
    """
    PostgreSQL adapter for SEMANTIC memory storage.
    
    Features:
    - Persistent knowledge storage
    - Entity and relationship queries
    - JSONB graph traversal
    - Knowledge type filtering
    - Confidence scoring
    
    Performance target: < 100ms for retrieval
    """
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize PostgreSQL adapter.
        
        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool
        self.memory_type = "SEMANTIC"
        
    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Store a semantic memory.
        
        Args:
            memory_id: Unique identifier for memory
            namespace: Hierarchical namespace for isolation
            data: Memory data (must contain 'text' field, can include 'entities', 'relationships')
            embedding: Not used for semantic (kept for protocol compatibility)
            metadata: Optional metadata (can include 'knowledge_type', 'confidence')
            
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
            
            # Extract semantic fields
            entities = data.get("entities", [])
            relationships = data.get("relationships", [])
            knowledge_type = metadata.get("knowledge_type")
            confidence = metadata.get("confidence", 1.0)
            
            # Validate confidence
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                confidence = 1.0
            
            # Insert memory
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO semantic_memories 
                        (memory_id, namespace, memory_type, text, data, metadata, 
                         entities, relationships, knowledge_type, confidence, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11)
                    ON CONFLICT (memory_id) DO UPDATE SET
                        text = EXCLUDED.text,
                        data = EXCLUDED.data,
                        metadata = EXCLUDED.metadata,
                        entities = EXCLUDED.entities,
                        relationships = EXCLUDED.relationships,
                        knowledge_type = EXCLUDED.knowledge_type,
                        confidence = EXCLUDED.confidence,
                        updated_at = EXCLUDED.updated_at
                    """,
                    str(memory_id),
                    namespace,
                    self.memory_type,
                    data["text"],
                    json.dumps(data),
                    json.dumps(metadata),
                    json.dumps(entities),
                    json.dumps(relationships),
                    knowledge_type,
                    confidence,
                    datetime.now(timezone.utc)
                )
            
            duration = time.time() - start_time
            logger.info(
                "semantic_memory_stored",
                memory_id=str(memory_id),
                namespace=namespace,
                knowledge_type=knowledge_type,
                entity_count=len(entities),
                relationship_count=len(relationships),
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
                "semantic_memory_store_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to store semantic memory: {e}") from e
    
    async def retrieve(
        self,
        namespace: str,
        query_embedding: Optional[List[float]],
        text_query: Optional[str],
        limit: int = 10,
        entity_filter: Optional[str] = None,
        knowledge_type: Optional[str] = None,
        min_confidence: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve semantic memories.
        
        Args:
            namespace: Namespace to search in
            query_embedding: Not used (kept for protocol compatibility)
            text_query: Optional full-text search query
            limit: Maximum number of results
            entity_filter: Optional entity name to filter by
            knowledge_type: Optional knowledge type filter
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of matching memories ordered by confidence (highest first)
        """
        start_time = time.time()
        
        try:
            # Build dynamic query
            conditions = ["namespace = $1"]
            params = [namespace]
            param_counter = 2
            
            # Confidence filter
            if min_confidence > 0.0:
                conditions.append(f"confidence >= ${param_counter}")
                params.append(min_confidence)
                param_counter += 1
            
            # Knowledge type filter
            if knowledge_type:
                conditions.append(f"knowledge_type = ${param_counter}")
                params.append(knowledge_type)
                param_counter += 1
            
            # Entity filter (search in JSONB array)
            if entity_filter:
                conditions.append(f"entities @> ${param_counter}::jsonb")
                # Search for entity by name
                params.append(json.dumps([{"name": entity_filter}]))
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
                    entities, relationships, knowledge_type, confidence,
                    created_at, updated_at
                FROM semantic_memories
                WHERE {where_clause}
                ORDER BY confidence DESC, created_at DESC
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
                    "entities": json.loads(row["entities"]) if isinstance(row["entities"], str) else row["entities"],
                    "relationships": json.loads(row["relationships"]) if isinstance(row["relationships"], str) else row["relationships"],
                    "confidence": float(row["confidence"]),
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                }
                
                if row["knowledge_type"]:
                    memory["knowledge_type"] = row["knowledge_type"]
                    
                results.append(memory)
            
            duration = time.time() - start_time
            logger.info(
                "semantic_memories_retrieved",
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
                "semantic_memory_retrieve_failed",
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve semantic memories: {e}") from e
    
    async def get(
        self,
        memory_id: UUID,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific semantic memory by ID.
        
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
                        entities, relationships, knowledge_type, confidence,
                        created_at, updated_at
                    FROM semantic_memories
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
                "entities": json.loads(row["entities"]) if isinstance(row["entities"], str) else row["entities"],
                "relationships": json.loads(row["relationships"]) if isinstance(row["relationships"], str) else row["relationships"],
                "confidence": float(row["confidence"]),
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            }
            
            if row["knowledge_type"]:
                memory["knowledge_type"] = row["knowledge_type"]
            
            duration = time.time() - start_time
            logger.debug(
                "semantic_memory_retrieved",
                memory_id=str(memory_id),
                namespace=namespace,
                duration_ms=round(duration * 1000, 2)
            )
            
            return memory
            
        except Exception as e:
            logger.error(
                "semantic_memory_get_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to get semantic memory: {e}") from e
    
    async def delete(
        self,
        memory_id: UUID,
        namespace: str
    ) -> bool:
        """
        Delete a specific semantic memory.
        
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
                    DELETE FROM semantic_memories
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
                    "semantic_memory_deleted",
                    memory_id=str(memory_id),
                    namespace=namespace,
                    duration_ms=round(duration * 1000, 2)
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(
                "semantic_memory_delete_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to delete semantic memory: {e}") from e
    
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
                        COUNT(DISTINCT namespace) as unique_namespaces,
                        AVG(confidence) as avg_confidence
                    FROM semantic_memories
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
                "avg_confidence": round(float(stats["avg_confidence"] or 0.0), 2),
                "pool_size": self.pool.get_size(),
                "pool_free": self.pool.get_size() - self.pool.get_size()  # Simplified
            }
            
        except Exception as e:
            logger.error("semantic_memory_health_check_failed", error=str(e))
            return {
                "status": "error",
                "backend": "PostgreSQL",
                "memory_type": self.memory_type,
                "error": str(e)
            }
