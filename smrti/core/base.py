"""
smrti/core/base.py - Base adapter classes and common functionality

Provides base implementations and shared utilities for all adapter types.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from smrti.core.exceptions import (
    AdapterError,
    CapacityExceededError,
    ConfigurationError,
    RetryableError,
    ValidationError
)
from smrti.schemas.models import MemoryQuery, RecordEnvelope


class BaseAdapter(ABC):
    """
    Base class for all Smrti adapters.
    
    Provides common functionality like configuration management,
    health tracking, retry logic, and telemetry integration.
    """
    
    def __init__(
        self,
        name: str,
        config: Dict[str, Any] | None = None
    ):
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"smrti.adapters.{name}")
        
        # Health tracking
        self._is_healthy = True
        self._last_health_check = datetime.utcnow()
        self._error_count = 0
        self._last_error: Optional[Exception] = None
        
        # Performance tracking
        self._operation_count = 0
        self._total_latency = 0.0
        self._last_operation_time = 0.0
        
        # Rate limiting
        self._rate_limit = self.config.get("rate_limit", 1000)  # ops per second
        self._rate_window = 1.0
        self._operation_times: List[float] = []
        
        # Retry configuration
        self._max_retries = self.config.get("max_retries", 3)
        self._retry_delay = self.config.get("retry_delay", 1.0)
        self._retry_backoff = self.config.get("retry_backoff", 2.0)
    
    @property
    def is_healthy(self) -> bool:
        """Check if adapter is currently healthy."""
        return self._is_healthy
    
    @property
    def error_count(self) -> int:
        """Get total error count."""
        return self._error_count
    
    @property
    def last_error(self) -> Optional[Exception]:
        """Get the last error encountered."""
        return self._last_error
    
    @property
    def average_latency(self) -> float:
        """Get average operation latency in seconds."""
        if self._operation_count == 0:
            return 0.0
        return self._total_latency / self._operation_count
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check and return status information.
        
        Subclasses should override _perform_health_check() to add
        adapter-specific health checks.
        """
        try:
            start_time = time.time()
            
            # Perform adapter-specific health check
            adapter_health = await self._perform_health_check()
            
            check_duration = time.time() - start_time
            self._last_health_check = datetime.utcnow()
            
            # If we got here without exception, adapter is healthy
            if self._is_healthy is False:
                self.logger.info(f"Adapter {self.name} recovered from unhealthy state")
                self._is_healthy = True
            
            return {
                "status": "healthy",
                "adapter_name": self.name,
                "last_check": self._last_health_check.isoformat(),
                "check_duration": check_duration,
                "error_count": self._error_count,
                "operation_count": self._operation_count,
                "average_latency": self.average_latency,
                "details": adapter_health
            }
        
        except Exception as e:
            self._mark_error(e)
            raise AdapterError(
                f"Health check failed for adapter {self.name}: {e}",
                adapter_name=self.name,
                operation="health_check",
                backend_error=e
            )
    
    @abstractmethod
    async def _perform_health_check(self) -> Dict[str, Any]:
        """
        Perform adapter-specific health check.
        
        Subclasses must implement this method to check their
        underlying storage/service health.
        
        Returns:
            Dictionary with adapter-specific health information
            
        Raises:
            Exception if health check fails
        """
        ...
    
    async def _execute_with_retry(
        self, 
        operation_name: str,
        operation_func,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute an operation with retry logic and error handling.
        
        Args:
            operation_name: Name of operation for logging
            operation_func: Async function to execute
            *args: Arguments for operation_func
            **kwargs: Keyword arguments for operation_func
            
        Returns:
            Result of operation_func
            
        Raises:
            AdapterError: If operation fails after all retries
        """
        await self._check_rate_limit()
        
        start_time = time.time()
        last_error = None
        
        for attempt in range(self._max_retries + 1):
            try:
                result = await operation_func(*args, **kwargs)
                
                # Track successful operation
                duration = time.time() - start_time
                self._operation_count += 1
                self._total_latency += duration
                self._last_operation_time = duration
                
                # Log slow operations
                if duration > 1.0:
                    self.logger.warning(
                        f"Slow operation {operation_name} took {duration:.2f}s"
                    )
                
                return result
            
            except Exception as e:
                last_error = e
                
                # Check if this is a retryable error
                if attempt < self._max_retries and self._is_retryable(e):
                    retry_delay = self._retry_delay * (self._retry_backoff ** attempt)
                    
                    self.logger.warning(
                        f"Operation {operation_name} failed (attempt {attempt + 1}), "
                        f"retrying in {retry_delay}s: {e}"
                    )
                    
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    # Not retryable or out of retries
                    break
        
        # All retries exhausted
        self._mark_error(last_error)
        
        if isinstance(last_error, (AdapterError, ValidationError)):
            raise last_error
        else:
            raise AdapterError(
                f"Operation {operation_name} failed after {self._max_retries + 1} attempts: {last_error}",
                adapter_name=self.name,
                operation=operation_name,
                backend_error=last_error
            )
    
    def _is_retryable(self, error: Exception) -> bool:
        """
        Check if an error should trigger a retry.
        
        Subclasses can override this to customize retry logic.
        """
        if isinstance(error, RetryableError):
            return error.should_retry()
        
        # Common retryable error types
        retryable_types = (
            ConnectionError,
            TimeoutError,
            OSError,  # Network errors
        )
        
        return isinstance(error, retryable_types)
    
    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        now = time.time()
        
        # Remove operations outside the rate window
        cutoff_time = now - self._rate_window
        self._operation_times = [t for t in self._operation_times if t > cutoff_time]
        
        # Check if we're at the rate limit
        if len(self._operation_times) >= self._rate_limit:
            oldest_time = min(self._operation_times)
            sleep_time = self._rate_window - (now - oldest_time)
            
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
        
        # Record this operation
        self._operation_times.append(now)
    
    def _mark_error(self, error: Exception) -> None:
        """Mark an error for health tracking."""
        self._error_count += 1
        self._last_error = error
        self._is_healthy = False
        
        self.logger.error(f"Adapter {self.name} error: {error}")
    
    def _validate_config(self, required_keys: List[str]) -> None:
        """
        Validate that required configuration keys are present.
        
        Args:
            required_keys: List of required configuration keys
            
        Raises:
            ConfigurationError: If any required keys are missing
        """
        missing_keys = [key for key in required_keys if key not in self.config]
        
        if missing_keys:
            raise ConfigurationError(
                f"Missing required configuration for adapter {self.name}: {missing_keys}",
                config_key=", ".join(missing_keys)
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics and performance metrics."""
        return {
            "adapter_name": self.name,
            "adapter_type": self.__class__.__name__,
            "is_healthy": self._is_healthy,
            "error_count": self._error_count,
            "operation_count": self._operation_count,
            "average_latency": self.average_latency,
            "last_operation_time": self._last_operation_time,
            "last_health_check": self._last_health_check.isoformat(),
            "config": {k: v for k, v in self.config.items() if "password" not in k.lower()}
        }


class BaseTierStore(BaseAdapter):
    """
    Base implementation for memory tier storage adapters.
    
    Provides common tier store functionality and validation.
    """
    
    def __init__(
        self,
        tier_name: str,
        config: Dict[str, Any] | None = None
    ):
        super().__init__(tier_name, config)
        self.tier_name = tier_name
        
        # Tier-specific configuration
        self._supports_ttl = self.config.get("supports_ttl", False)
        self._supports_similarity_search = self.config.get("supports_similarity_search", False)
        self._max_record_size = self.config.get("max_record_size", 1024 * 1024)  # 1MB
        self._cleanup_interval = self.config.get("cleanup_interval", 3600)  # 1 hour
        
        # Statistics tracking
        self._records_stored = 0
        self._records_retrieved = 0
        self._records_deleted = 0
        self._storage_size = 0
    
    @property
    def supports_ttl(self) -> bool:
        """Whether this tier supports time-to-live expiration."""
        return self._supports_ttl
    
    @property
    def supports_similarity_search(self) -> bool:
        """Whether this tier supports vector similarity search."""
        return self._supports_similarity_search
    
    def _validate_record(self, record: RecordEnvelope) -> None:
        """
        Validate a record before storage.
        
        Args:
            record: Record to validate
            
        Raises:
            ValidationError: If record is invalid
            CapacityExceededError: If record exceeds size limits
        """
        if not record.record_id:
            raise ValidationError("Record ID is required")
        
        if not record.tenant_id:
            raise ValidationError("Tenant ID is required")
        
        if not record.namespace:
            raise ValidationError("Namespace is required")
        
        # Check record size
        estimated_size = len(str(record))
        if estimated_size > self._max_record_size:
            raise CapacityExceededError(
                f"Record size {estimated_size} exceeds maximum {self._max_record_size}",
                limit_type="record_size",
                current_value=estimated_size,
                limit_value=self._max_record_size
            )
    
    def _validate_query(self, query: MemoryQuery) -> None:
        """
        Validate a memory query.
        
        Args:
            query: Query to validate
            
        Raises:
            ValidationError: If query is invalid
        """
        if query.limit <= 0:
            raise ValidationError("Query limit must be positive")
        
        if query.limit > 1000:
            raise ValidationError("Query limit cannot exceed 1000")
        
        if query.similarity_threshold < 0.0 or query.similarity_threshold > 1.0:
            raise ValidationError("Similarity threshold must be between 0.0 and 1.0")
    
    def _update_stats(self, operation: str, count: int = 1, size: int = 0) -> None:
        """Update tier statistics."""
        if operation == "store":
            self._records_stored += count
            self._storage_size += size
        elif operation == "retrieve":
            self._records_retrieved += count
        elif operation == "delete":
            self._records_deleted += count
            self._storage_size = max(0, self._storage_size - size)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get tier statistics and health information."""
        base_stats = super().get_stats()
        
        tier_stats = {
            "tier_name": self.tier_name,
            "supports_ttl": self._supports_ttl,
            "supports_similarity_search": self._supports_similarity_search,
            "records_stored": self._records_stored,
            "records_retrieved": self._records_retrieved,
            "records_deleted": self._records_deleted,
            "estimated_storage_size": self._storage_size,
            "max_record_size": self._max_record_size
        }
        
        base_stats.update(tier_stats)
        return base_stats


class BaseEmbeddingProvider(BaseAdapter):
    """
    Base implementation for embedding providers.
    
    Provides common functionality for text embedding generation.
    """
    
    def __init__(
        self,
        name: str,
        model_name: str,
        embedding_dim: int,
        max_tokens: int,
        config: Dict[str, Any] | None = None
    ):
        super().__init__(name, config)
        self._model_name = model_name
        self._embedding_dim = embedding_dim
        self._max_tokens = max_tokens
        
        # Embedding-specific configuration
        self._batch_size = self.config.get("batch_size", 32)
        self._cache_embeddings = self.config.get("cache_embeddings", True)
        self._embedding_cache: Dict[str, List[float]] = {}
        
        # Statistics
        self._embeddings_generated = 0
        self._cache_hits = 0
        self._batch_operations = 0
    
    @property
    def model_name(self) -> str:
        """Name of the embedding model being used."""
        return self._model_name
    
    @property
    def embedding_dim(self) -> int:
        """Dimensionality of generated embeddings."""
        return self._embedding_dim
    
    @property
    def max_tokens(self) -> int:
        """Maximum token length for input text."""
        return self._max_tokens
    
    def _validate_text(self, text: str) -> None:
        """
        Validate input text for embedding generation.
        
        Args:
            text: Input text to validate
            
        Raises:
            ValidationError: If text is invalid
        """
        if not text or not text.strip():
            raise ValidationError("Text cannot be empty")
        
        # Rough token count estimation (assuming ~4 chars per token)
        estimated_tokens = len(text) // 4
        if estimated_tokens > self._max_tokens:
            raise ValidationError(
                f"Text length {estimated_tokens} tokens exceeds maximum {self._max_tokens}"
            )
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()
    
    def _check_cache(self, text: str) -> Optional[List[float]]:
        """Check if embedding is cached."""
        if not self._cache_embeddings:
            return None
        
        cache_key = self._get_cache_key(text)
        if cache_key in self._embedding_cache:
            self._cache_hits += 1
            return self._embedding_cache[cache_key]
        
        return None
    
    def _cache_embedding(self, text: str, embedding: List[float]) -> None:
        """Cache an embedding."""
        if not self._cache_embeddings:
            return
        
        cache_key = self._get_cache_key(text)
        self._embedding_cache[cache_key] = embedding
        
        # Limit cache size
        max_cache_size = self.config.get("max_cache_size", 10000)
        if len(self._embedding_cache) > max_cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self._embedding_cache))
            del self._embedding_cache[oldest_key]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get embedding provider statistics."""
        base_stats = super().get_stats()
        
        embedding_stats = {
            "model_name": self._model_name,
            "embedding_dim": self._embedding_dim,
            "max_tokens": self._max_tokens,
            "embeddings_generated": self._embeddings_generated,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": self._cache_hits / max(1, self._embeddings_generated),
            "batch_operations": self._batch_operations,
            "cache_size": len(self._embedding_cache)
        }
        
        base_stats.update(embedding_stats)
        return base_stats


class BaseMemoryTier(BaseAdapter):
    """
    Base class for all memory tier implementations.
    
    Provides common memory tier functionality including consolidation,
    cross-tier coordination, and memory management.
    """
    
    def __init__(
        self,
        tier_name: str,
        config: Dict[str, Any] | None = None
    ):
        super().__init__(tier_name, config)
        self.tier_name = tier_name
        
        # Memory tier configuration
        self._capacity = self.config.get("capacity", 1000)
        self._default_ttl = self.config.get("default_ttl")
        self._consolidation_threshold = self.config.get("consolidation_threshold", 0.8)
        self._consolidation_enabled = self.config.get("consolidation_enabled", True)
        
        # Cross-tier coordination
        self._upstream_tiers: List[str] = []
        self._downstream_tiers: List[str] = []
        
        # Statistics
        self._records_count = 0
        self._consolidations_performed = 0
        self._last_consolidation: Optional[datetime] = None
    
    @property
    def capacity(self) -> int:
        """Maximum capacity of this memory tier."""
        return self._capacity
    
    @property
    def usage_ratio(self) -> float:
        """Current usage as ratio of capacity (0.0 to 1.0)."""
        return min(1.0, self._records_count / max(1, self._capacity))
    
    @property
    def needs_consolidation(self) -> bool:
        """Whether this tier needs consolidation."""
        return (
            self._consolidation_enabled and 
            self.usage_ratio >= self._consolidation_threshold
        )
    
    def register_upstream_tier(self, tier_name: str) -> None:
        """Register an upstream tier (feeds into this tier)."""
        if tier_name not in self._upstream_tiers:
            self._upstream_tiers.append(tier_name)
    
    def register_downstream_tier(self, tier_name: str) -> None:
        """Register a downstream tier (receives from this tier)."""
        if tier_name not in self._downstream_tiers:
            self._downstream_tiers.append(tier_name)
    
    @abstractmethod
    async def store_memory(
        self, 
        record: RecordEnvelope,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store a memory record in this tier.
        
        Args:
            record: Memory record to store
            ttl: Time-to-live in seconds (optional)
            
        Returns:
            True if stored successfully
            
        Raises:
            AdapterError: If storage fails
            CapacityExceededError: If tier is at capacity
        """
        ...
    
    @abstractmethod
    async def retrieve_memories(
        self,
        query: MemoryQuery,
        context: Optional[Dict[str, Any]] = None
    ) -> List[RecordEnvelope]:
        """
        Retrieve memories matching the query.
        
        Args:
            query: Memory query parameters
            context: Additional context for retrieval
            
        Returns:
            List of matching memory records
        """
        ...
    
    @abstractmethod
    async def delete_memory(self, record_id: str, tenant_id: str) -> bool:
        """
        Delete a memory record by ID.
        
        Args:
            record_id: ID of record to delete
            tenant_id: Tenant ID for isolation
            
        Returns:
            True if deleted successfully
        """
        ...
    
    @abstractmethod
    async def consolidate_memories(
        self,
        target_tier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Consolidate memories to downstream tiers.
        
        Args:
            target_tier: Specific tier to consolidate to (optional)
            
        Returns:
            Dictionary with consolidation statistics
        """
        ...
    
    async def cleanup_expired(self) -> int:
        """
        Clean up expired memories.
        
        Returns:
            Number of records cleaned up
        """
        # Base implementation - subclasses should override if they support TTL
        return 0
    
    async def get_capacity_info(self) -> Dict[str, Any]:
        """Get tier capacity and usage information."""
        return {
            "tier_name": self.tier_name,
            "capacity": self._capacity,
            "current_count": self._records_count,
            "usage_ratio": self.usage_ratio,
            "needs_consolidation": self.needs_consolidation,
            "consolidation_threshold": self._consolidation_threshold,
            "consolidations_performed": self._consolidations_performed,
            "last_consolidation": self._last_consolidation.isoformat() if self._last_consolidation else None
        }
    
    def _update_record_count(self, delta: int) -> None:
        """Update the record count for capacity tracking."""
        self._records_count = max(0, self._records_count + delta)
    
    def _mark_consolidation(self) -> None:
        """Mark that a consolidation was performed."""
        self._consolidations_performed += 1
        self._last_consolidation = datetime.utcnow()
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory tier statistics."""
        base_stats = super().get_stats()
        capacity_info = await self.get_capacity_info()
        
        tier_stats = {
            "upstream_tiers": self._upstream_tiers,
            "downstream_tiers": self._downstream_tiers,
            "default_ttl": self._default_ttl,
            "consolidation_enabled": self._consolidation_enabled
        }
        
        base_stats.update(capacity_info)
        base_stats.update(tier_stats)
        return base_stats