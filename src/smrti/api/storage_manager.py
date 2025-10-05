"""Storage manager that coordinates all memory tier adapters."""

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from smrti.core.types import MemoryType
from smrti.core.exceptions import ValidationError, StorageError
from smrti.core.logging import get_logger
from smrti.storage.protocol import StorageAdapter
from smrti.embedding.protocol import EmbeddingProvider

logger = get_logger(__name__)


class StorageManager:
    """
    Coordinates storage operations across all memory tiers.
    
    Responsibilities:
    - Route operations to correct adapter based on memory_type
    - Generate embeddings when needed (LONG_TERM tier)
    - Enforce business logic and validation
    - Provide unified interface for API layer
    """
    
    def __init__(
        self,
        working_adapter: StorageAdapter,
        short_term_adapter: StorageAdapter,
        long_term_adapter: StorageAdapter,
        episodic_adapter: StorageAdapter,
        semantic_adapter: StorageAdapter,
        embedding_provider: EmbeddingProvider
    ):
        """
        Initialize storage manager with all adapters.
        
        Args:
            working_adapter: Adapter for WORKING tier
            short_term_adapter: Adapter for SHORT_TERM tier
            long_term_adapter: Adapter for LONG_TERM tier
            episodic_adapter: Adapter for EPISODIC tier
            semantic_adapter: Adapter for SEMANTIC tier
            embedding_provider: Provider for generating embeddings
        """
        self.adapters = {
            MemoryType.WORKING.value: working_adapter,
            MemoryType.SHORT_TERM.value: short_term_adapter,
            MemoryType.LONG_TERM.value: long_term_adapter,
            MemoryType.EPISODIC.value: episodic_adapter,
            MemoryType.SEMANTIC.value: semantic_adapter,
        }
        self.embedding_provider = embedding_provider
        
        logger.info(
            "storage_manager_initialized",
            tiers=list(self.adapters.keys())
        )
    
    def _get_adapter(self, memory_type: str) -> StorageAdapter:
        """Get adapter for memory type."""
        adapter = self.adapters.get(memory_type)
        if adapter is None:
            raise ValidationError(f"Invalid memory_type: {memory_type}")
        return adapter
    
    async def store(
        self,
        memory_type: str,
        namespace: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Store a memory in the appropriate tier.
        
        Args:
            memory_type: Memory tier (WORKING, SHORT_TERM, etc.)
            namespace: Namespace for isolation
            data: Memory data (must contain 'text' field)
            metadata: Optional metadata
            
        Returns:
            memory_id: UUID of stored memory
            
        Raises:
            ValidationError: If input is invalid
            StorageError: If storage fails
        """
        # Generate memory ID
        memory_id = uuid4()
        
        # Generate embedding if needed (LONG_TERM tier)
        embedding = None
        if memory_type == MemoryType.LONG_TERM.value:
            text = data.get("text", "")
            if not text:
                raise ValidationError("text field is required for LONG_TERM memories")
            
            try:
                embedding = await self.embedding_provider.embed_single(text)
                logger.debug(
                    "embedding_generated_for_storage",
                    memory_id=str(memory_id),
                    text_length=len(text),
                    embedding_dim=len(embedding)
                )
            except Exception as e:
                logger.error(
                    "embedding_generation_failed",
                    memory_id=str(memory_id),
                    error=str(e)
                )
                raise StorageError(f"Failed to generate embedding: {e}") from e
        
        # Get adapter and store
        adapter = self._get_adapter(memory_type)
        
        try:
            await adapter.store(
                memory_id=memory_id,
                namespace=namespace,
                data=data,
                embedding=embedding,
                metadata=metadata or {}
            )
            
            logger.info(
                "memory_stored",
                memory_id=str(memory_id),
                memory_type=memory_type,
                namespace=namespace
            )
            
            return memory_id
            
        except Exception as e:
            logger.error(
                "storage_failed",
                memory_id=str(memory_id),
                memory_type=memory_type,
                namespace=namespace,
                error=str(e)
            )
            raise
    
    async def retrieve(
        self,
        memory_type: str,
        namespace: str,
        query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories from a tier.
        
        Args:
            memory_type: Memory tier to retrieve from
            namespace: Namespace for isolation
            query: Optional search query
            filters: Optional metadata filters
            limit: Maximum results
            
        Returns:
            List of matching memories
            
        Raises:
            ValidationError: If input is invalid
            StorageError: If retrieval fails
        """
        # Generate query embedding if needed (LONG_TERM tier)
        query_embedding = None
        if memory_type == MemoryType.LONG_TERM.value and query:
            try:
                query_embedding = await self.embedding_provider.embed_single(query)
                logger.debug(
                    "query_embedding_generated",
                    memory_type=memory_type,
                    query_length=len(query),
                    embedding_dim=len(query_embedding)
                )
            except Exception as e:
                logger.error(
                    "query_embedding_failed",
                    memory_type=memory_type,
                    error=str(e)
                )
                raise StorageError(f"Failed to generate query embedding: {e}") from e
        
        # Get adapter and retrieve
        adapter = self._get_adapter(memory_type)
        
        try:
            # For LONG_TERM memories with embeddings, use semantic search
            # For other tiers, use simple retrieve
            results = await adapter.retrieve(
                namespace=namespace,
                query=query,
                filters={} if not query_embedding else {"_has_embedding": True},
                limit=limit
            )
            
            logger.info(
                "memories_retrieved",
                memory_type=memory_type,
                namespace=namespace,
                count=len(results)
            )
            
            return results
            
        except Exception as e:
            logger.error(
                "retrieval_failed",
                memory_type=memory_type,
                namespace=namespace,
                error=str(e)
            )
            raise
    
    async def get(
        self,
        memory_type: str,
        memory_id: UUID,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific memory by ID.
        
        Args:
            memory_type: Memory tier
            memory_id: Memory identifier
            namespace: Namespace for authorization
            
        Returns:
            Memory data or None if not found
            
        Raises:
            ValidationError: If input is invalid
            StorageError: If retrieval fails
        """
        adapter = self._get_adapter(memory_type)
        
        try:
            result = await adapter.get(memory_id, namespace)
            
            if result:
                logger.debug(
                    "memory_retrieved",
                    memory_id=str(memory_id),
                    memory_type=memory_type,
                    namespace=namespace
                )
            else:
                logger.debug(
                    "memory_not_found",
                    memory_id=str(memory_id),
                    memory_type=memory_type,
                    namespace=namespace
                )
            
            return result
            
        except Exception as e:
            logger.error(
                "get_failed",
                memory_id=str(memory_id),
                memory_type=memory_type,
                namespace=namespace,
                error=str(e)
            )
            raise
    
    async def delete(
        self,
        memory_type: str,
        memory_id: UUID,
        namespace: str
    ) -> bool:
        """
        Delete a specific memory.
        
        Args:
            memory_type: Memory tier
            memory_id: Memory identifier
            namespace: Namespace for authorization
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ValidationError: If input is invalid
            StorageError: If deletion fails
        """
        adapter = self._get_adapter(memory_type)
        
        try:
            deleted = await adapter.delete(memory_id, namespace)
            
            if deleted:
                logger.info(
                    "memory_deleted",
                    memory_id=str(memory_id),
                    memory_type=memory_type,
                    namespace=namespace
                )
            else:
                logger.debug(
                    "memory_not_found_for_deletion",
                    memory_id=str(memory_id),
                    memory_type=memory_type,
                    namespace=namespace
                )
            
            return deleted
            
        except Exception as e:
            logger.error(
                "deletion_failed",
                memory_id=str(memory_id),
                memory_type=memory_type,
                namespace=namespace,
                error=str(e)
            )
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of all storage backends and embedding service.
        
        Returns:
            Dictionary with health status of all components
        """
        health_status = {}
        
        # Check each adapter
        for memory_type, adapter in self.adapters.items():
            try:
                status = await adapter.health_check()
                health_status[memory_type] = status
            except Exception as e:
                logger.error(
                    "health_check_failed",
                    memory_type=memory_type,
                    error=str(e)
                )
                health_status[memory_type] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # Check embedding service
        try:
            embedding_status = await self.embedding_provider.health_check()
            health_status["embedding_service"] = embedding_status
        except Exception as e:
            logger.error(
                "embedding_health_check_failed",
                error=str(e)
            )
            health_status["embedding_service"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Determine overall status
        all_healthy = all(
            component.get("status") in ("connected", "healthy")
            for component in health_status.values()
        )
        
        return {
            "status": "healthy" if all_healthy else "degraded",
            "components": health_status
        }
