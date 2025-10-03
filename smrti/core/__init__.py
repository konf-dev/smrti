"""
smrti.core - Core functionality and base classes

Contains the foundational components for the Smrti intelligent memory system,
including base adapters, protocols, and shared utilities.
"""

from .exceptions import (
    SmrtiError,
    ValidationError,
    PartialDegradationError,
    RetryableError,
    CapacityExceededError,
    IntegrityError,
    EmbeddingError,
    AdapterError,
    RedisAdapterError,
    VectorStoreError,
    GraphStoreError,
    LexicalIndexError,
    ConfigurationError,
    AdapterNotFoundError,
    CapabilityNotSupportedError,
    ContextAssemblyError,
    TokenBudgetExceededError,
    InsufficientMemoryError,
    LifecycleError,
    ConsolidationError,
    SummarizationError,
    DeduplicationError,
    SecurityError,
    NamespaceViolationError,
    PIIRedactionError,
    EncryptionError,
    is_retryable_error,
    get_error_context,
)

from .protocols import (
    EmbeddingProvider,
    TierStore,
    VectorStore,
    GraphStore,
    LexicalIndex,
    ContextAssembler,
    LifecycleManager,
    SmrtiProvider,
    AdapterRegistry,
)

from .registry import (
    AdapterCapability,
    AdapterInfo,
    SmrtiAdapterRegistry,
    get_global_registry,
    set_global_registry,
)

from .base import (
    BaseAdapter,
    BaseTierStore,
    BaseEmbeddingProvider,
)

__all__ = [
    # Exception hierarchy
    "SmrtiError",
    "ValidationError",
    "PartialDegradationError",
    "RetryableError",
    "CapacityExceededError",
    "IntegrityError",
    "EmbeddingError",
    "AdapterError",
    "RedisAdapterError",
    "VectorStoreError",
    "GraphStoreError",
    "LexicalIndexError",
    "ConfigurationError",
    "AdapterNotFoundError",
    "CapabilityNotSupportedError",
    "ContextAssemblyError",
    "TokenBudgetExceededError",
    "InsufficientMemoryError",
    "LifecycleError",
    "ConsolidationError",
    "SummarizationError",
    "DeduplicationError",
    "SecurityError",
    "NamespaceViolationError",
    "PIIRedactionError",
    "EncryptionError",
    "is_retryable_error",
    "get_error_context",
    
    # Protocol interfaces
    "EmbeddingProvider",
    "TierStore",
    "VectorStore",
    "GraphStore",
    "LexicalIndex",
    "ContextAssembler",
    "LifecycleManager",
    "SmrtiProvider",
    "AdapterRegistry",
    
    # Registry system
    "AdapterCapability",
    "AdapterInfo", 
    "SmrtiAdapterRegistry",
    "get_global_registry",
    "set_global_registry",
    
    # Base classes
    "BaseAdapter",
    "BaseTierStore",
    "BaseEmbeddingProvider",
]