"""
smrti/adapters/storage/__init__.py - Storage tier adapters

Collection of storage adapters for different memory tiers and backends.
"""

from .redis import RedisAdapter
from .vector_adapter import VectorStorageAdapter, VectorConfig, VectorSearchQuery, VectorOperationResult

__all__ = [
    "RedisAdapter",
    "VectorStorageAdapter", 
    "VectorConfig",
    "VectorSearchQuery",
    "VectorOperationResult",
]