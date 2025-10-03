"""
smrti/adapters/storage/redis_adapter.py - Redis Storage Adapter

Redis-based storage adapter optimized for Working Memory and Short-term Memory tiers
with TTL support, batch operations, and high-performance access patterns.
"""

from __future__ import annotations

import json
import time
import asyncio
from typing import Dict, List, Optional, Any, Union, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None

from ...models.base import MemoryItem
from ...config.base import BaseConfig


@dataclass
class RedisConfig(BaseConfig):
    """Configuration for Redis storage adapter."""
    
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    username: Optional[str] = None
    ssl: bool = False
    ssl_cert_reqs: Optional[str] = None
    
    # Connection pool settings
    max_connections: int = 20
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    socket_keepalive: bool = True
    
    # Redis-specific settings
    decode_responses: bool = True
    health_check_interval: int = 30
    
    # Smrti-specific settings
    key_prefix: str = "smrti"
    default_ttl: int = 3600  # 1 hour default
    batch_size: int = 100
    enable_compression: bool = False
    
    def get_redis_url(self) -> str:
        """Generate Redis connection URL."""
        scheme = "rediss" if self.ssl else "redis"
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        elif self.password:
            auth = f":{self.password}@"
        
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"


@dataclass
class RedisOperationResult:
    """Result of a Redis operation."""
    
    success: bool
    operation: str
    key_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None
    
    @classmethod
    def success_result(cls, operation: str, key_count: int = 0, 
                      execution_time_ms: float = 0.0) -> 'RedisOperationResult':
        """Create a successful operation result."""
        return cls(
            success=True,
            operation=operation,
            key_count=key_count,
            execution_time_ms=execution_time_ms
        )
    
    @classmethod
    def error_result(cls, operation: str, error_message: str,
                    execution_time_ms: float = 0.0) -> 'RedisOperationResult':
        """Create an error operation result."""
        return cls(
            success=False,
            operation=operation,
            error_message=error_message,
            execution_time_ms=execution_time_ms
        )


class RedisStorageAdapter:
    """Redis-based storage adapter for memory tiers."""
    
    def __init__(self, config: RedisConfig):
        """Initialize Redis storage adapter.
        
        Args:
            config: Redis configuration
            
        Raises:
            ImportError: If redis package not available
            ValueError: If configuration invalid
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package required for RedisStorageAdapter. "
                "Install with: pip install redis"
            )
        
        self.config = config
        self.redis_client: Optional[Any] = None  # Redis client instance
        self._connection_pool = None
        
        # Performance tracking
        self._operations_count = 0
        self._total_operation_time = 0.0
        self._error_count = 0
        
        # Key management
        self._active_keys: Set[str] = set()
        
    async def initialize(self) -> None:
        """Initialize Redis connection and verify connectivity."""
        try:
            # Create connection pool
            self._connection_pool = redis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                username=self.config.username,
                ssl=self.config.ssl,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                socket_keepalive=self.config.socket_keepalive,
                decode_responses=self.config.decode_responses,
                health_check_interval=self.config.health_check_interval
            )
            
            # Create Redis client
            self.redis_client = Redis(connection_pool=self._connection_pool)
            
            # Test connection
            await self.redis_client.ping()
            
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}") from e
    
    async def close(self) -> None:
        """Close Redis connection and clean up resources."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
        
        if self._connection_pool:
            await self._connection_pool.disconnect()
            self._connection_pool = None
    
    def _make_key(self, tenant: str, namespace: str, key_type: str, item_id: str) -> str:
        """Generate Redis key with proper namespacing.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace within tenant
            key_type: Type of key (item, metadata, etc.)
            item_id: Item identifier
            
        Returns:
            Formatted Redis key
        """
        return f"{self.config.key_prefix}:{tenant}:{namespace}:{key_type}:{item_id}"
    
    def _make_index_key(self, tenant: str, namespace: str, index_type: str) -> str:
        """Generate Redis key for indexes.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace within tenant
            index_type: Type of index
            
        Returns:
            Formatted Redis index key
        """
        return f"{self.config.key_prefix}:{tenant}:{namespace}:idx:{index_type}"
    
    async def store_item(self, item: MemoryItem, ttl: Optional[int] = None) -> RedisOperationResult:
        """Store a single memory item in Redis.
        
        Args:
            item: Memory item to store
            ttl: Time to live in seconds (uses default if None)
            
        Returns:
            Operation result
        """
        start_time = time.time()
        
        try:
            if not self.redis_client:
                raise RuntimeError("Redis client not initialized")
            
            # Use default TTL if not specified
            if ttl is None:
                ttl = self.config.default_ttl
            
            # Generate key
            key = self._make_key(
                item.tenant or "default",
                item.namespace or "default", 
                "item",
                item.id
            )
            
            # Serialize item data
            item_data = {
                'id': item.id,
                'tenant': item.tenant,
                'namespace': item.namespace,
                'content': item.content,
                'metadata': item.metadata,
                'timestamp': item.timestamp,
                'created_at': time.time(),
                'item_type': getattr(item, 'item_type', 'memory_item')
            }
            
            # Store with TTL
            await self.redis_client.setex(
                key, 
                ttl, 
                json.dumps(item_data, default=str)
            )
            
            # Track key
            self._active_keys.add(key)
            
            # Update index (optional - for fast listing)
            index_key = self._make_index_key(
                item.tenant or "default",
                item.namespace or "default",
                "items"
            )
            await self.redis_client.sadd(index_key, key)
            await self.redis_client.expire(index_key, ttl + 300)  # Index lives slightly longer
            
            execution_time = (time.time() - start_time) * 1000
            self._operations_count += 1
            self._total_operation_time += execution_time
            
            return RedisOperationResult.success_result(
                "store_item", 1, execution_time
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return RedisOperationResult.error_result(
                "store_item", str(e), execution_time
            )
    
    async def store_items_batch(self, items: List[MemoryItem], 
                               ttl: Optional[int] = None) -> RedisOperationResult:
        """Store multiple memory items in a single batch operation.
        
        Args:
            items: List of memory items to store
            ttl: Time to live in seconds (uses default if None)
            
        Returns:
            Operation result
        """
        start_time = time.time()
        
        try:
            if not self.redis_client:
                raise RuntimeError("Redis client not initialized")
            
            if not items:
                return RedisOperationResult.success_result("store_items_batch", 0, 0.0)
            
            # Use default TTL if not specified
            if ttl is None:
                ttl = self.config.default_ttl
            
            # Use pipeline for batch operations
            pipe = self.redis_client.pipeline()
            
            stored_keys = []
            index_keys_map = {}
            
            for item in items:
                # Generate key
                key = self._make_key(
                    item.tenant or "default",
                    item.namespace or "default",
                    "item", 
                    item.id
                )
                
                # Serialize item data
                item_data = {
                    'id': item.id,
                    'tenant': item.tenant,
                    'namespace': item.namespace,
                    'content': item.content,
                    'metadata': item.metadata,
                    'timestamp': item.timestamp,
                    'created_at': time.time(),
                    'item_type': getattr(item, 'item_type', 'memory_item')
                }
                
                # Add to pipeline
                pipe.setex(key, ttl, json.dumps(item_data, default=str))
                stored_keys.append(key)
                
                # Track index updates
                index_key = self._make_index_key(
                    item.tenant or "default",
                    item.namespace or "default",
                    "items"
                )
                if index_key not in index_keys_map:
                    index_keys_map[index_key] = []
                index_keys_map[index_key].append(key)
            
            # Add index updates to pipeline
            for index_key, keys in index_keys_map.items():
                pipe.sadd(index_key, *keys)
                pipe.expire(index_key, ttl + 300)
            
            # Execute pipeline
            await pipe.execute()
            
            # Track keys
            self._active_keys.update(stored_keys)
            
            execution_time = (time.time() - start_time) * 1000
            self._operations_count += 1
            self._total_operation_time += execution_time
            
            return RedisOperationResult.success_result(
                "store_items_batch", len(items), execution_time
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return RedisOperationResult.error_result(
                "store_items_batch", str(e), execution_time
            )
    
    async def retrieve_item(self, tenant: str, namespace: str, 
                           item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single memory item.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace within tenant
            item_id: Item identifier
            
        Returns:
            Item data dictionary or None if not found
        """
        try:
            if not self.redis_client:
                raise RuntimeError("Redis client not initialized")
            
            key = self._make_key(tenant, namespace, "item", item_id)
            
            data = await self.redis_client.get(key)
            if data is None:
                return None
            
            return json.loads(data)
            
        except Exception as e:
            # Log error but don't raise - retrieval failures should be graceful
            return None
    
    async def retrieve_items_batch(self, tenant: str, namespace: str, 
                                  item_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Retrieve multiple memory items in a single batch operation.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace within tenant
            item_ids: List of item identifiers
            
        Returns:
            Dictionary mapping item_id to item data (missing items omitted)
        """
        try:
            if not self.redis_client or not item_ids:
                return {}
            
            # Generate keys
            keys = [
                self._make_key(tenant, namespace, "item", item_id)
                for item_id in item_ids
            ]
            
            # Use pipeline for batch retrieval
            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            
            results = await pipe.execute()
            
            # Build result dictionary
            items = {}
            for item_id, data in zip(item_ids, results):
                if data is not None:
                    try:
                        items[item_id] = json.loads(data)
                    except json.JSONDecodeError:
                        # Skip corrupted items
                        continue
            
            return items
            
        except Exception as e:
            # Log error but return empty dict - retrieval failures should be graceful
            return {}
    
    async def delete_item(self, tenant: str, namespace: str, item_id: str) -> RedisOperationResult:
        """Delete a single memory item.
        
        Args:
            tenant: Tenant identifier  
            namespace: Namespace within tenant
            item_id: Item identifier
            
        Returns:
            Operation result
        """
        start_time = time.time()
        
        try:
            if not self.redis_client:
                raise RuntimeError("Redis client not initialized")
            
            key = self._make_key(tenant, namespace, "item", item_id)
            
            # Delete item and update index
            pipe = self.redis_client.pipeline()
            pipe.delete(key)
            
            index_key = self._make_index_key(tenant, namespace, "items")
            pipe.srem(index_key, key)
            
            results = await pipe.execute()
            
            # Check if item existed
            deleted_count = results[0]
            
            # Remove from tracked keys
            self._active_keys.discard(key)
            
            execution_time = (time.time() - start_time) * 1000
            self._operations_count += 1
            self._total_operation_time += execution_time
            
            return RedisOperationResult.success_result(
                "delete_item", deleted_count, execution_time
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return RedisOperationResult.error_result(
                "delete_item", str(e), execution_time
            )
    
    async def list_items(self, tenant: str, namespace: str, 
                        limit: Optional[int] = None) -> List[str]:
        """List all item IDs in a namespace.
        
        Args:
            tenant: Tenant identifier
            namespace: Namespace within tenant
            limit: Maximum number of items to return
            
        Returns:
            List of item IDs
        """
        try:
            if not self.redis_client:
                return []
            
            index_key = self._make_index_key(tenant, namespace, "items")
            
            # Get all keys from index
            keys = await self.redis_client.smembers(index_key)
            
            # Extract item IDs from keys
            item_ids = []
            prefix = f"{self.config.key_prefix}:{tenant}:{namespace}:item:"
            
            for key in keys:
                if key.startswith(prefix):
                    item_id = key[len(prefix):]
                    item_ids.append(item_id)
            
            # Apply limit if specified
            if limit is not None:
                item_ids = item_ids[:limit]
            
            return item_ids
            
        except Exception as e:
            # Return empty list on error
            return []
    
    async def cleanup_expired(self, tenant: Optional[str] = None, 
                             namespace: Optional[str] = None) -> RedisOperationResult:
        """Clean up expired items and update indexes.
        
        Args:
            tenant: Optional tenant filter
            namespace: Optional namespace filter
            
        Returns:
            Operation result
        """
        start_time = time.time()
        
        try:
            if not self.redis_client:
                raise RuntimeError("Redis client not initialized")
            
            # This is automatically handled by Redis TTL, but we can clean up our indexes
            cleaned_count = 0
            
            if tenant and namespace:
                # Clean specific namespace
                index_key = self._make_index_key(tenant, namespace, "items")
                
                # Get all keys in index
                keys = await self.redis_client.smembers(index_key)
                
                # Check which keys still exist
                if keys:
                    pipe = self.redis_client.pipeline()
                    for key in keys:
                        pipe.exists(key)
                    
                    results = await pipe.execute()
                    
                    # Remove non-existent keys from index
                    expired_keys = [
                        key for key, exists in zip(keys, results)
                        if not exists
                    ]
                    
                    if expired_keys:
                        await self.redis_client.srem(index_key, *expired_keys)
                        cleaned_count = len(expired_keys)
                        
                        # Remove from tracked keys
                        self._active_keys.difference_update(expired_keys)
            
            execution_time = (time.time() - start_time) * 1000
            self._operations_count += 1
            self._total_operation_time += execution_time
            
            return RedisOperationResult.success_result(
                "cleanup_expired", cleaned_count, execution_time
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._error_count += 1
            return RedisOperationResult.error_result(
                "cleanup_expired", str(e), execution_time
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get adapter performance statistics.
        
        Returns:
            Statistics dictionary
        """
        try:
            # Get Redis info if available
            redis_info = {}
            if self.redis_client:
                try:
                    info = await self.redis_client.info()
                    redis_info = {
                        'connected_clients': info.get('connected_clients', 0),
                        'used_memory': info.get('used_memory', 0),
                        'used_memory_human': info.get('used_memory_human', '0B'),
                        'keyspace_hits': info.get('keyspace_hits', 0),
                        'keyspace_misses': info.get('keyspace_misses', 0),
                        'total_commands_processed': info.get('total_commands_processed', 0)
                    }
                except Exception:
                    pass
            
            avg_operation_time = (
                self._total_operation_time / max(1, self._operations_count)
            )
            
            return {
                'operations_count': self._operations_count,
                'error_count': self._error_count,
                'total_operation_time_ms': self._total_operation_time,
                'average_operation_time_ms': avg_operation_time,
                'success_rate': (
                    (self._operations_count - self._error_count) / max(1, self._operations_count)
                ),
                'active_keys_tracked': len(self._active_keys),
                'redis_info': redis_info,
                'config': {
                    'host': self.config.host,
                    'port': self.config.port,
                    'db': self.config.db,
                    'default_ttl': self.config.default_ttl,
                    'batch_size': self.config.batch_size,
                    'max_connections': self.config.max_connections
                }
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'operations_count': self._operations_count,
                'error_count': self._error_count
            }
    
    async def health_check(self) -> bool:
        """Check if Redis connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self.redis_client:
                return False
            
            await self.redis_client.ping()
            return True
            
        except Exception:
            return False


# Convenience factory function
def create_redis_adapter(host: str = "localhost", port: int = 6379, 
                        db: int = 0, **kwargs) -> RedisStorageAdapter:
    """Create Redis storage adapter with simplified configuration.
    
    Args:
        host: Redis host
        port: Redis port
        db: Redis database number
        **kwargs: Additional configuration options
        
    Returns:
        Configured Redis storage adapter
    """
    config = RedisConfig(host=host, port=port, db=db, **kwargs)
    return RedisStorageAdapter(config)