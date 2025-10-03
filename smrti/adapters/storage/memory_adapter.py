"""
smrti/adapters/storage/memory_adapter.py - In-Memory Storage Adapter

In-memory storage adapter for development, testing, and fallback scenarios.
Provides same interface as Redis adapter but uses local memory with TTL simulation.
"""

from __future__ import annotations

import json
import time
import asyncio
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import threading
import weakref

try:
    from ...models.base import MemoryItem
    from ...config.base import BaseConfig
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    MemoryItem = None
    BaseConfig = object


@dataclass
class MemoryConfig:
    """Configuration for in-memory storage adapter."""
    
    # Storage settings
    default_ttl: int = 3600  # Default TTL in seconds
    max_items_per_namespace: int = 10000  # Memory limit per namespace
    cleanup_interval: int = 300  # Cleanup interval in seconds (5 minutes)
    
    # Performance settings
    enable_compression: bool = False  # JSON compression for large items
    enable_stats: bool = True  # Track operation statistics
    
    # Key settings
    key_prefix: str = "smrti_memory"
    
    def get_storage_id(self) -> str:
        """Get unique storage identifier."""
        return f"memory://{self.key_prefix}"


@dataclass
class MemoryOperationResult:
    """Result of memory storage operation."""
    
    success: bool
    operation: str
    key_count: int
    execution_time_ms: float
    error_message: Optional[str] = None
    memory_usage_bytes: Optional[int] = None
    
    @classmethod
    def success_result(cls, operation: str, key_count: int, execution_time: float,
                      memory_usage: Optional[int] = None) -> 'MemoryOperationResult':
        """Create success result."""
        return cls(True, operation, key_count, execution_time, None, memory_usage)
    
    @classmethod
    def error_result(cls, operation: str, error: str, execution_time: float) -> 'MemoryOperationResult':
        """Create error result."""
        return cls(False, operation, 0, execution_time, error)


class TTLDict:
    """Dictionary with TTL support."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.expires: Dict[str, float] = {}
        self.lock = threading.RLock()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value with optional TTL."""
        with self.lock:
            self.data[key] = value
            if ttl is not None:
                self.expires[key] = time.time() + ttl
            elif key in self.expires:
                del self.expires[key]
    
    def get(self, key: str) -> Optional[Any]:
        """Get value, checking TTL."""
        with self.lock:
            if key not in self.data:
                return None
            
            # Check if expired
            if key in self.expires:
                if time.time() > self.expires[key]:
                    del self.data[key]
                    del self.expires[key]
                    return None
            
            return self.data[key]
    
    def delete(self, key: str) -> bool:
        """Delete key."""
        with self.lock:
            deleted = key in self.data
            self.data.pop(key, None)
            self.expires.pop(key, None)
            return deleted
    
    def keys(self) -> List[str]:
        """Get all non-expired keys."""
        with self.lock:
            current_time = time.time()
            valid_keys = []
            
            expired_keys = []
            for key in self.data.keys():
                if key in self.expires and current_time > self.expires[key]:
                    expired_keys.append(key)
                else:
                    valid_keys.append(key)
            
            # Clean up expired keys
            for key in expired_keys:
                del self.data[key]
                del self.expires[key]
            
            return valid_keys
    
    def cleanup_expired(self) -> int:
        """Clean up expired items."""
        with self.lock:
            current_time = time.time()
            expired_keys = []
            
            for key, expire_time in self.expires.items():
                if current_time > expire_time:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.data[key]
                del self.expires[key]
            
            return len(expired_keys)
    
    def size(self) -> int:
        """Get number of items."""
        with self.lock:
            # Trigger cleanup to get accurate count
            self.cleanup_expired()
            return len(self.data)
    
    def memory_usage(self) -> int:
        """Estimate memory usage in bytes."""
        with self.lock:
            # Simple estimation based on JSON serialization
            total_size = 0
            for key, value in self.data.items():
                try:
                    key_size = len(key.encode('utf-8'))
                    value_size = len(json.dumps(value).encode('utf-8'))
                    total_size += key_size + value_size
                except:
                    # Fallback estimation
                    total_size += len(str(key)) + len(str(value))
            
            return total_size


class TTLSet:
    """Set with TTL support."""
    
    def __init__(self):
        self.data: Dict[str, Set[str]] = {}
        self.lock = threading.RLock()
    
    def add(self, key: str, *members: str):
        """Add members to set."""
        with self.lock:
            if key not in self.data:
                self.data[key] = set()
            for member in members:
                self.data[key].add(member)
    
    def remove(self, key: str, *members: str) -> int:
        """Remove members from set."""
        with self.lock:
            if key not in self.data:
                return 0
            
            removed = 0
            for member in members:
                if member in self.data[key]:
                    self.data[key].remove(member)
                    removed += 1
            
            # Clean up empty sets
            if not self.data[key]:
                del self.data[key]
            
            return removed
    
    def members(self, key: str) -> List[str]:
        """Get set members."""
        with self.lock:
            return list(self.data.get(key, set()))
    
    def delete(self, key: str) -> bool:
        """Delete entire set."""
        with self.lock:
            return self.data.pop(key, None) is not None


class MemoryStorageAdapter:
    """
    In-memory storage adapter for Smrti system.
    
    Provides Redis-compatible interface using local memory with TTL simulation.
    Ideal for development, testing, and scenarios without Redis availability.
    """
    
    def __init__(self, config: MemoryConfig):
        """Initialize memory storage adapter."""
        self.config = config
        
        # Storage backends
        self._data_store = TTLDict()
        self._index_store = TTLSet()
        
        # Statistics
        self._operations_count = 0
        self._error_count = 0
        self._total_time_ms = 0.0
        self._start_time = time.time()
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        # Thread safety
        self.lock = threading.RLock()
    
    def _make_key(self, tenant: str, namespace: str, key_type: str, item_id: str) -> str:
        """Generate storage key."""
        return f"{self.config.key_prefix}:{tenant}:{namespace}:{key_type}:{item_id}"
    
    def _make_index_key(self, tenant: str, namespace: str, index_name: str) -> str:
        """Generate index key."""
        return f"{self.config.key_prefix}:{tenant}:{namespace}:idx:{index_name}"
    
    async def initialize(self) -> bool:
        """Initialize storage adapter."""
        try:
            # Start cleanup task
            if self.config.cleanup_interval > 0:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            return True
        except Exception as e:
            print(f"Memory adapter initialization failed: {e}")
            return False
    
    async def close(self):
        """Close storage adapter."""
        self._shutdown = True
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clear all data
        with self.lock:
            self._data_store.data.clear()
            self._data_store.expires.clear()
            self._index_store.data.clear()
    
    async def _cleanup_loop(self):
        """Periodic cleanup of expired items."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                
                if not self._shutdown:
                    # Clean up expired items
                    expired_data = self._data_store.cleanup_expired()
                    
                    if expired_data > 0:
                        print(f"Cleaned up {expired_data} expired items")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Cleanup error: {e}")
    
    async def store_item(self, item: Any, ttl: Optional[int] = None) -> MemoryOperationResult:
        """Store single memory item."""
        start_time = time.time()
        
        try:
            with self.lock:
                # Extract item data
                if hasattr(item, 'to_dict'):
                    item_data = item.to_dict()
                elif isinstance(item, dict):
                    item_data = item
                else:
                    return MemoryOperationResult.error_result("store_item", "Invalid item format", 0.0)
                
                tenant = item_data.get('tenant', 'default')
                namespace = item_data.get('namespace', 'default')
                item_id = item_data.get('id')
                
                if not item_id:
                    return MemoryOperationResult.error_result("store_item", "Missing item ID", 0.0)
                
                # Check namespace limits
                namespace_items = self._get_namespace_item_count(tenant, namespace)
                if namespace_items >= self.config.max_items_per_namespace:
                    return MemoryOperationResult.error_result(
                        "store_item", 
                        f"Namespace limit exceeded: {namespace_items}/{self.config.max_items_per_namespace}",
                        0.0
                    )
                
                # Store item
                key = self._make_key(tenant, namespace, "item", item_id)
                index_key = self._make_index_key(tenant, namespace, "items")
                
                ttl = ttl or self.config.default_ttl
                
                # Store data and update index
                self._data_store.set(key, item_data, ttl)
                self._index_store.add(index_key, item_id)
                
                # Update statistics
                execution_time = (time.time() - start_time) * 1000
                self._operations_count += 1
                self._total_time_ms += execution_time
                
                memory_usage = self._data_store.memory_usage()
                
                return MemoryOperationResult.success_result("store_item", 1, execution_time, memory_usage)
        
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return MemoryOperationResult.error_result("store_item", str(e), execution_time)
    
    async def store_items_batch(self, items: List[Any], ttl: Optional[int] = None) -> MemoryOperationResult:
        """Store multiple items in batch."""
        start_time = time.time()
        
        try:
            with self.lock:
                stored_count = 0
                
                for item in items:
                    result = await self.store_item(item, ttl)
                    if result.success:
                        stored_count += 1
                    else:
                        # Log individual failures but continue
                        print(f"Failed to store item: {result.error_message}")
                
                execution_time = (time.time() - start_time) * 1000
                memory_usage = self._data_store.memory_usage()
                
                return MemoryOperationResult.success_result("store_items_batch", stored_count, execution_time, memory_usage)
        
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return MemoryOperationResult.error_result("store_items_batch", str(e), execution_time)
    
    async def retrieve_item(self, tenant: str, namespace: str, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single item."""
        try:
            key = self._make_key(tenant, namespace, "item", item_id)
            return self._data_store.get(key)
        except Exception as e:
            print(f"Retrieve error: {e}")
            return None
    
    async def retrieve_items_batch(self, tenant: str, namespace: str, 
                                 item_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Retrieve multiple items."""
        results = {}
        
        try:
            for item_id in item_ids:
                item_data = await self.retrieve_item(tenant, namespace, item_id)
                if item_data:
                    results[item_id] = item_data
        except Exception as e:
            print(f"Batch retrieve error: {e}")
        
        return results
    
    async def delete_item(self, tenant: str, namespace: str, item_id: str) -> MemoryOperationResult:
        """Delete single item."""
        start_time = time.time()
        
        try:
            with self.lock:
                key = self._make_key(tenant, namespace, "item", item_id)
                index_key = self._make_index_key(tenant, namespace, "items")
                
                # Delete item and remove from index
                deleted = self._data_store.delete(key)
                self._index_store.remove(index_key, item_id)
                
                execution_time = (time.time() - start_time) * 1000
                self._operations_count += 1
                self._total_time_ms += execution_time
                
                key_count = 1 if deleted else 0
                return MemoryOperationResult.success_result("delete_item", key_count, execution_time)
        
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return MemoryOperationResult.error_result("delete_item", str(e), execution_time)
    
    async def list_items(self, tenant: str, namespace: str, limit: Optional[int] = None) -> List[str]:
        """List item IDs in namespace."""
        try:
            index_key = self._make_index_key(tenant, namespace, "items")
            item_ids = self._index_store.members(index_key)
            
            # Remove IDs for items that no longer exist (cleanup)
            valid_ids = []
            for item_id in item_ids:
                key = self._make_key(tenant, namespace, "item", item_id)
                if self._data_store.get(key) is not None:
                    valid_ids.append(item_id)
            
            # Update index with valid IDs
            if len(valid_ids) != len(item_ids):
                self._index_store.delete(index_key)
                if valid_ids:
                    self._index_store.add(index_key, *valid_ids)
            
            # Apply limit
            if limit is not None and len(valid_ids) > limit:
                valid_ids = valid_ids[:limit]
            
            return valid_ids
        
        except Exception as e:
            print(f"List error: {e}")
            return []
    
    async def cleanup_expired(self, tenant: str, namespace: str) -> MemoryOperationResult:
        """Clean up expired items in namespace."""
        start_time = time.time()
        
        try:
            with self.lock:
                # Get all items in namespace
                index_key = self._make_index_key(tenant, namespace, "items")
                item_ids = self._index_store.members(index_key)
                
                expired_count = 0
                valid_ids = []
                
                for item_id in item_ids:
                    key = self._make_key(tenant, namespace, "item", item_id)
                    if self._data_store.get(key) is None:
                        # Item expired or missing
                        expired_count += 1
                    else:
                        valid_ids.append(item_id)
                
                # Update index
                if expired_count > 0:
                    self._index_store.delete(index_key)
                    if valid_ids:
                        self._index_store.add(index_key, *valid_ids)
                
                # Also run global cleanup
                global_expired = self._data_store.cleanup_expired()
                
                execution_time = (time.time() - start_time) * 1000
                total_cleaned = expired_count + global_expired
                
                return MemoryOperationResult.success_result("cleanup_expired", total_cleaned, execution_time)
        
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return MemoryOperationResult.error_result("cleanup_expired", str(e), execution_time)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        with self.lock:
            uptime = time.time() - self._start_time
            avg_time = self._total_time_ms / max(self._operations_count, 1)
            success_rate = 1.0 - (self._error_count / max(self._operations_count, 1))
            
            # Memory usage
            total_items = self._data_store.size()
            memory_usage = self._data_store.memory_usage()
            
            # Namespace breakdown
            namespace_stats = {}
            for key in self._index_store.data.keys():
                if ":idx:items" in key:
                    parts = key.split(":")
                    if len(parts) >= 4:
                        tenant = parts[1]
                        namespace = parts[2]
                        ns_key = f"{tenant}:{namespace}"
                        namespace_stats[ns_key] = len(self._index_store.members(key))
            
            return {
                'operations_count': self._operations_count,
                'error_count': self._error_count,
                'average_operation_time_ms': avg_time,
                'success_rate': success_rate,
                'uptime_seconds': uptime,
                'memory_usage_bytes': memory_usage,
                'total_items': total_items,
                'namespace_stats': namespace_stats,
                'config': {
                    'max_items_per_namespace': self.config.max_items_per_namespace,
                    'default_ttl': self.config.default_ttl,
                    'cleanup_interval': self.config.cleanup_interval,
                    'key_prefix': self.config.key_prefix
                }
            }
    
    async def health_check(self) -> bool:
        """Check adapter health."""
        try:
            # Simple test operation
            test_key = f"{self.config.key_prefix}:health_check"
            self._data_store.set(test_key, {"status": "ok"}, 1)
            result = self._data_store.get(test_key)
            self._data_store.delete(test_key)
            
            return result is not None
        except Exception:
            return False
    
    def _get_namespace_item_count(self, tenant: str, namespace: str) -> int:
        """Get item count for namespace."""
        try:
            index_key = self._make_index_key(tenant, namespace, "items")
            return len(self._index_store.members(index_key))
        except:
            return 0


def create_memory_adapter(**kwargs) -> MemoryStorageAdapter:
    """
    Convenience function to create memory storage adapter.
    
    Args:
        **kwargs: Configuration parameters for MemoryConfig
        
    Returns:
        MemoryStorageAdapter instance
    """
    config = MemoryConfig(**kwargs)
    return MemoryStorageAdapter(config)