"""
smrti/core/exceptions.py - Custom exception hierarchy

Complete exception taxonomy for Smrti operations, following the PRD specification
for error handling and categorization.
"""

from typing import Any

from smrti.schemas.models import SmrtiContext


class SmrtiError(Exception):
    """
    Base exception for all Smrti errors.
    
    All Smrti-specific exceptions inherit from this base class to enable
    easy categorization and handling in client code.
    """
    
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(SmrtiError):
    """
    Input data failed validation.
    
    Raised when Pydantic validation fails or custom business logic
    validation rules are violated.
    """
    
    def __init__(self, message: str, field: str | None = None, value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value


class PartialDegradationError(SmrtiError):
    """
    Some tiers failed but partial result available.
    
    This exception indicates that some memory tiers or adapters failed
    but the system was able to produce a partial context that may still
    be useful to the consumer.
    """
    
    def __init__(
        self, 
        message: str, 
        partial_context: SmrtiContext, 
        failed_tiers: list[str],
        failed_operations: dict[str, Exception] | None = None
    ):
        super().__init__(message)
        self.partial_context = partial_context
        self.failed_tiers = failed_tiers
        self.failed_operations = failed_operations or {}

    def get_failure_summary(self) -> dict[str, Any]:
        """Get a summary of what failed and what succeeded."""
        return {
            "failed_tiers": self.failed_tiers,
            "successful_sections": [s.name for s in self.partial_context.sections],
            "total_items_retrieved": self.partial_context.total_items(),
            "estimated_tokens": self.partial_context.estimated_tokens,
            "failure_count": len(self.failed_operations)
        }


class RetryableError(SmrtiError):
    """
    Transient failure; safe to retry.
    
    Indicates errors that are likely to succeed on retry, such as
    network timeouts, temporary service unavailability, or rate limits.
    """
    
    def __init__(
        self, 
        message: str, 
        retry_after_seconds: int | None = None,
        max_retries: int = 3,
        attempt_count: int = 1
    ):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.max_retries = max_retries
        self.attempt_count = attempt_count

    def should_retry(self) -> bool:
        """Check if this error should be retried."""
        return self.attempt_count < self.max_retries


class CapacityExceededError(SmrtiError):
    """
    Batch size or rate limit exceeded.
    
    Raised when operations exceed configured limits such as maximum
    batch size, rate limits, or resource quotas.
    """
    
    def __init__(
        self, 
        message: str, 
        limit_type: str,
        current_value: int | float,
        limit_value: int | float
    ):
        super().__init__(message)
        self.limit_type = limit_type
        self.current_value = current_value
        self.limit_value = limit_value


class IntegrityError(SmrtiError):
    """
    Data corruption or lineage inconsistency detected.
    
    Raised when data integrity checks fail, such as checksum mismatches,
    broken lineage chains, or corrupted record envelopes.
    """
    
    def __init__(
        self, 
        message: str, 
        record_id: str | None = None,
        integrity_check: str | None = None,
        expected_value: Any = None,
        actual_value: Any = None
    ):
        super().__init__(message)
        self.record_id = record_id
        self.integrity_check = integrity_check
        self.expected_value = expected_value
        self.actual_value = actual_value


class EmbeddingError(SmrtiError):
    """
    Embedding provider failure.
    
    Raised when embedding generation fails due to model errors,
    API failures, or incompatible input formats.
    """
    
    def __init__(
        self, 
        message: str, 
        provider: str | None = None,
        model: str | None = None,
        input_text: str | None = None
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.input_text = input_text


class AdapterError(SmrtiError):
    """
    Generic adapter operational failure.
    
    Base class for adapter-specific errors. Concrete adapters should
    subclass this for their specific error types.
    """
    
    def __init__(
        self, 
        message: str, 
        adapter_name: str,
        operation: str | None = None,
        backend_error: Exception | None = None
    ):
        super().__init__(message)
        self.adapter_name = adapter_name
        self.operation = operation
        self.backend_error = backend_error


# Adapter-specific exceptions
class RedisAdapterError(AdapterError):
    """Redis adapter specific errors."""
    
    def __init__(
        self, 
        message: str, 
        operation: str | None = None,
        redis_error: Exception | None = None
    ):
        super().__init__(message, "redis", operation, redis_error)


class VectorStoreError(AdapterError):
    """Vector store adapter errors (ChromaDB, Pinecone, etc.)."""
    
    def __init__(
        self, 
        message: str, 
        store_type: str,
        operation: str | None = None,
        backend_error: Exception | None = None
    ):
        super().__init__(message, f"vector_store_{store_type}", operation, backend_error)


class GraphStoreError(AdapterError):
    """Graph store adapter errors (Neo4j, NetworkX, etc.)."""
    
    def __init__(
        self, 
        message: str, 
        store_type: str,
        operation: str | None = None,
        backend_error: Exception | None = None
    ):
        super().__init__(message, f"graph_store_{store_type}", operation, backend_error)


class LexicalIndexError(AdapterError):
    """Lexical index adapter errors (Whoosh, etc.)."""
    
    def __init__(
        self, 
        message: str, 
        index_type: str,
        operation: str | None = None,
        backend_error: Exception | None = None
    ):
        super().__init__(message, f"lexical_index_{index_type}", operation, backend_error)


# Configuration and setup errors
class ConfigurationError(SmrtiError):
    """Configuration validation or loading errors."""
    
    def __init__(
        self, 
        message: str, 
        config_key: str | None = None,
        config_value: Any = None
    ):
        super().__init__(message)
        self.config_key = config_key
        self.config_value = config_value


class AdapterNotFoundError(SmrtiError):
    """Requested adapter not found or not registered."""
    
    def __init__(self, adapter_name: str, adapter_type: str):
        message = f"Adapter '{adapter_name}' of type '{adapter_type}' not found"
        super().__init__(message)
        self.adapter_name = adapter_name
        self.adapter_type = adapter_type


class CapabilityNotSupportedError(SmrtiError):
    """Adapter does not support required capability."""
    
    def __init__(self, adapter_name: str, capability: str):
        message = f"Adapter '{adapter_name}' does not support capability '{capability}'"
        super().__init__(message)
        self.adapter_name = adapter_name
        self.capability = capability


# Context assembly errors
class ContextAssemblyError(SmrtiError):
    """Context building and assembly errors."""
    pass


class TokenBudgetExceededError(ContextAssemblyError):
    """Token budget exceeded even after all reduction strategies."""
    
    def __init__(
        self, 
        budget: int, 
        estimated_tokens: int,
        reduction_attempts: int = 0
    ):
        message = f"Token budget {budget} exceeded (estimated: {estimated_tokens}) after {reduction_attempts} reductions"
        super().__init__(message)
        self.budget = budget
        self.estimated_tokens = estimated_tokens
        self.reduction_attempts = reduction_attempts


class InsufficientMemoryError(ContextAssemblyError):
    """Not enough memory items found to build meaningful context."""
    
    def __init__(self, min_items_required: int, items_found: int):
        message = f"Insufficient memory items: required {min_items_required}, found {items_found}"
        super().__init__(message)
        self.min_items_required = min_items_required
        self.items_found = items_found


# Lifecycle management errors
class MemoryError(SmrtiError):
    """Base class for memory-related operations errors."""
    pass


class StorageError(MemoryError):
    """Error during memory storage operations."""
    
    def __init__(
        self, 
        message: str, 
        tier: str | None = None,
        record_id: str | None = None
    ):
        super().__init__(message)
        self.tier = tier
        self.record_id = record_id


class RetrievalError(MemoryError):
    """Error during memory retrieval operations."""
    
    def __init__(
        self, 
        message: str, 
        tier: str | None = None,
        query: str | None = None
    ):
        super().__init__(message)
        self.tier = tier
        self.query = query


class LifecycleError(SmrtiError):
    """Lifecycle management operation errors."""
    pass


class ConsolidationError(LifecycleError):
    """Error during memory consolidation process."""
    
    def __init__(
        self, 
        message: str, 
        session_id: str | None = None,
        source_tier: str | None = None,
        target_tier: str | None = None
    ):
        super().__init__(message)
        self.session_id = session_id
        self.source_tier = source_tier
        self.target_tier = target_tier


class SummarizationError(LifecycleError):
    """Error during summarization process."""
    
    def __init__(
        self, 
        message: str, 
        source_records: list[str] | None = None,
        summarizer_model: str | None = None
    ):
        super().__init__(message)
        self.source_records = source_records or []
        self.summarizer_model = summarizer_model


class DeduplicationError(LifecycleError):
    """Error during deduplication process."""
    
    def __init__(
        self, 
        message: str, 
        record_ids: list[str] | None = None,
        similarity_threshold: float | None = None
    ):
        super().__init__(message)
        self.record_ids = record_ids or []
        self.similarity_threshold = similarity_threshold


# Security and privacy errors
class SecurityError(SmrtiError):
    """Security violation or policy enforcement error."""
    pass


class NamespaceViolationError(SecurityError):
    """Cross-namespace access attempt detected."""
    
    def __init__(
        self, 
        attempted_tenant: str, 
        attempted_namespace: str,
        authorized_tenant: str | None = None,
        authorized_namespace: str | None = None
    ):
        message = f"Unauthorized access to {attempted_tenant}:{attempted_namespace}"
        super().__init__(message)
        self.attempted_tenant = attempted_tenant
        self.attempted_namespace = attempted_namespace
        self.authorized_tenant = authorized_tenant
        self.authorized_namespace = authorized_namespace


class PIIRedactionError(SecurityError):
    """PII redaction process failed."""
    
    def __init__(self, message: str, text_sample: str | None = None):
        super().__init__(message)
        self.text_sample = text_sample


class EncryptionError(SecurityError):
    """Encryption/decryption operation failed."""
    
    def __init__(
        self, 
        message: str, 
        operation: str,
        key_id: str | None = None
    ):
        super().__init__(message)
        self.operation = operation
        self.key_id = key_id


# Utility functions for error handling
def is_retryable_error(exception: Exception) -> bool:
    """Check if an exception should trigger a retry."""
    if isinstance(exception, RetryableError):
        return exception.should_retry()
    
    # Network and connection errors are typically retryable
    retryable_types = (
        ConnectionError,
        TimeoutError,
        # Add more as needed
    )
    
    return isinstance(exception, retryable_types)


def get_error_context(exception: Exception) -> dict[str, Any]:
    """Extract structured context from an exception."""
    context = {
        "type": type(exception).__name__,
        "message": str(exception),
    }
    
    if isinstance(exception, SmrtiError):
        context["smrti_error"] = True
        context.update(exception.details)
        
        # Add specific fields based on error type
        if isinstance(exception, PartialDegradationError):
            context["partial_context_available"] = True
            context["failed_tiers"] = exception.failed_tiers
            
        elif isinstance(exception, CapacityExceededError):
            context["limit_exceeded"] = {
                "type": exception.limit_type,
                "current": exception.current_value,
                "limit": exception.limit_value
            }
            
        elif isinstance(exception, IntegrityError):
            context["integrity_violation"] = {
                "record_id": exception.record_id,
                "check": exception.integrity_check
            }
    else:
        context["smrti_error"] = False
    
    return context