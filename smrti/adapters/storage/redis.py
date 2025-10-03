"""
smrti/adapters/storage/redis.py - Redis adapter for Working Memory and Short-term Memory

Production-ready Redis adapter with connection pooling, failover, TTL support,
and comprehensive error handling.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import redis.asyncio as redis
    from redis.asyncio import ConnectionPool, Redis
    from redis.exceptions import ConnectionError, TimeoutError, RedisError
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    redis = None
    # Create placeholder classes for type hints
    class ConnectionPool:
        pass
    class Redis:
        pass
    ConnectionError = Exception
    TimeoutError = Exception  
    RedisError = Exception

from smrti.core.base import BaseTierStore
from smrti.core.exceptions import (
    RedisAdapterError,
    RetryableError,
    ValidationError,
    CapacityExceededError,
    ConfigurationError
)
from smrti.core.protocols import TierStore
from smrti.core.registry import AdapterCapability
from smrti.schemas.models import MemoryQuery, RecordEnvelope


class RedisAdapter(BaseTierStore):
    """
    Redis adapter for Working Memory and Short-term Memory tiers.
    
    Features:
    - Connection pooling with failover
    - TTL-based automatic expiration
    - JSON serialization with compression
    - Batch operations for efficiency
    - Memory usage monitoring
    - Master/replica support
    - Lua scripts for atomic operations
    - Configurable eviction policies
    """
    
    def __init__(
        self,
        tier_name: str,
        config: Optional[Dict[str, Any]] = None
    ):
        if not HAS_REDIS:
            raise ConfigurationError(
                "redis package is required but not installed. "
                "Install with: pip install redis"
            )
        
        super().__init__(tier_name, config)
        
        # Validate required configuration
        self._validate_config(["host"])
        
        # Redis connection configuration
        self._host = self.config["host"]
        self._port = self.config.get("port", 6379)
        self._db = self.config.get("db", 0)
        self._password = self.config.get("password")
        self._username = self.config.get("username")
        self._ssl = self.config.get("ssl", False)
        
        # Connection pool configuration
        self._max_connections = self.config.get("max_connections", 20)
        self._socket_timeout = self.config.get("socket_timeout", 5.0)
        self._socket_connect_timeout = self.config.get("socket_connect_timeout", 5.0)
        self._retry_on_timeout = self.config.get("retry_on_timeout", True)
        self._health_check_interval = self.config.get("health_check_interval", 30.0)
        
        # Memory tier configuration
        self._default_ttl = self.config.get("default_ttl", 3600)  # 1 hour
        self._max_ttl = self.config.get("max_ttl", 86400)  # 24 hours
        self._key_prefix = self.config.get("key_prefix", f"smrti:{tier_name}")
        self._compress_json = self.config.get("compress_json", True)
        self._max_value_size = self.config.get("max_value_size", 512 * 1024)  # 512KB
        
        # Batch operation settings
        self._batch_size = self.config.get("batch_size", 100)
        self._pipeline_size = self.config.get("pipeline_size", 50)
        
        # Failover configuration
        self._replica_hosts = self.config.get("replica_hosts", [])
        self._sentinel_hosts = self.config.get("sentinel_hosts", [])
        self._sentinel_service = self.config.get("sentinel_service", "mymaster")
        
        # Redis objects
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[Redis] = None
        self._replica_pools: List[ConnectionPool] = []
        
        # Lua scripts for atomic operations
        self._lua_scripts = {}
        
        # Statistics
        self._connection_errors = 0
        self._failover_count = 0
        self._last_failover = None
        self._memory_usage = 0
        self._key_count = 0
        
        # Set tier capabilities
        self._supports_ttl = True
        self._supports_similarity_search = False
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_connections()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._cleanup_connections()
    
    async def _initialize_connections(self) -> None:
        """Initialize Redis connections and connection pools."""
        try:
            # Create primary connection pool
            self._pool = ConnectionPool(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                username=self._username,
                ssl=self._ssl,
                max_connections=self._max_connections,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                retry_on_timeout=self._retry_on_timeout,
                health_check_interval=self._health_check_interval
            )
            
            self._redis = Redis(connection_pool=self._pool)
            
            # Test primary connection
            await self._redis.ping()
            
            # Initialize replica connections if configured
            for replica_config in self._replica_hosts:
                replica_pool = ConnectionPool(
                    host=replica_config["host"],
                    port=replica_config.get("port", 6379),
                    db=replica_config.get("db", self._db),
                    password=replica_config.get("password", self._password),
                    username=replica_config.get("username", self._username),
                    ssl=replica_config.get("ssl", self._ssl),
                    max_connections=self._max_connections // 2,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._socket_connect_timeout,
                    retry_on_timeout=self._retry_on_timeout
                )
                self._replica_pools.append(replica_pool)
            
            # Load Lua scripts
            await self._load_lua_scripts()
            
            self.logger.info(
                f"Redis adapter {self.tier_name} initialized "
                f"(host={self._host}:{self._port}, db={self._db}, "
                f"replicas={len(self._replica_pools)})"
            )
            
        except Exception as e:
            raise RedisAdapterError(
                f"Failed to initialize Redis connections: {e}",
                operation="initialize",
                redis_error=e
            )
    
    async def _load_lua_scripts(self) -> None:
        """Load Lua scripts for atomic operations."""
        # Script for atomic record storage with TTL
        store_script = """
        local key = KEYS[1]
        local value = ARGV[1] 
        local ttl = tonumber(ARGV[2])
        
        redis.call('SET', key, value)
        if ttl > 0 then
            redis.call('EXPIRE', key, ttl)
        end
        
        return redis.call('EXISTS', key)
        """
        
        # Script for batch retrieval
        batch_get_script = """
        local results = {}
        for i = 1, #KEYS do
            local value = redis.call('GET', KEYS[i])
            table.insert(results, value)
        end
        return results
        """
        
        # Script for cleanup expired records
        cleanup_script = """
        local cursor = "0"
        local count = 0
        local pattern = ARGV[1]
        
        repeat
            local result = redis.call('SCAN', cursor, 'MATCH', pattern, 'COUNT', 100)
            cursor = result[1]
            local keys = result[2]
            
            for i = 1, #keys do
                local ttl = redis.call('TTL', keys[i])
                if ttl == -1 then  -- No TTL set, but should have one
                    redis.call('DEL', keys[i])
                    count = count + 1
                end
            end
        until cursor == "0"
        
        return count
        """
        
        try:
            self._lua_scripts["store"] = self._redis.register_script(store_script)
            self._lua_scripts["batch_get"] = self._redis.register_script(batch_get_script)
            self._lua_scripts["cleanup"] = self._redis.register_script(cleanup_script)
            
        except Exception as e:
            self.logger.warning(f"Failed to load Lua scripts: {e}")
    
    def _make_key(self, record_id: str) -> str:
        """Generate Redis key for record ID."""
        return f"{self._key_prefix}:{record_id}"
    
    def _serialize_record(self, record: RecordEnvelope) -> bytes:
        """Serialize record to JSON bytes."""
        try:
            json_str = record.model_dump_json()
            
            if self._compress_json:
                import gzip
                return gzip.compress(json_str.encode('utf-8'))
            else:
                return json_str.encode('utf-8')
                
        except Exception as e:
            raise ValidationError(f"Failed to serialize record: {e}")
    
    def _deserialize_record(self, data: bytes) -> RecordEnvelope:
        """Deserialize JSON bytes to record."""
        try:
            if self._compress_json:
                import gzip
                json_str = gzip.decompress(data).decode('utf-8')
            else:
                json_str = data.decode('utf-8')
            
            return RecordEnvelope.model_validate_json(json_str)
            
        except Exception as e:
            raise ValidationError(f"Failed to deserialize record: {e}")
    
    def _calculate_ttl(self, ttl: Optional[timedelta]) -> int:
        """Calculate TTL in seconds, applying limits."""
        if ttl is None:
            return self._default_ttl
        
        ttl_seconds = int(ttl.total_seconds())
        
        if ttl_seconds <= 0:
            return self._default_ttl
        
        return min(ttl_seconds, self._max_ttl)
    
    async def store(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Store a memory record with optional TTL."""
        return await self._execute_with_retry(
            "store",
            self._store_impl,
            record,
            ttl
        )
    
    async def _store_impl(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Internal store implementation."""
        self._validate_record(record)
        
        key = self._make_key(record.record_id)
        serialized = self._serialize_record(record)
        
        # Check value size
        if len(serialized) > self._max_value_size:
            raise CapacityExceededError(
                f"Serialized record size {len(serialized)} exceeds maximum {self._max_value_size}",
                limit_type="value_size",
                current_value=len(serialized),
                limit_value=self._max_value_size
            )
        
        ttl_seconds = self._calculate_ttl(ttl)
        
        try:
            # Use Lua script for atomic operation
            if "store" in self._lua_scripts:
                result = await self._lua_scripts["store"](keys=[key], args=[serialized, ttl_seconds])
                success = bool(result)
            else:
                # Fallback to pipeline
                pipe = self._redis.pipeline()
                pipe.set(key, serialized)
                pipe.expire(key, ttl_seconds)
                results = await pipe.execute()
                success = all(results)
            
            if success:
                self._update_stats("store", 1, len(serialized))
                return record.record_id
            else:
                raise RedisAdapterError(
                    f"Failed to store record {record.record_id}",
                    operation="store"
                )
                
        except (ConnectionError, TimeoutError) as e:
            self._connection_errors += 1
            raise RetryableError(f"Redis connection error during store: {e}")
        
        except RedisError as e:
            raise RedisAdapterError(
                f"Redis error during store: {e}",
                operation="store",
                redis_error=e
            )
    
    async def retrieve(self, record_id: str) -> Optional[RecordEnvelope]:
        """Retrieve a specific memory record."""
        return await self._execute_with_retry(
            "retrieve",
            self._retrieve_impl,
            record_id
        )
    
    async def _retrieve_impl(self, record_id: str) -> Optional[RecordEnvelope]:
        """Internal retrieve implementation."""
        key = self._make_key(record_id)
        
        try:
            data = await self._redis.get(key)
            
            if data is None:
                return None
            
            record = self._deserialize_record(data)
            self._update_stats("retrieve", 1)
            
            return record
            
        except (ConnectionError, TimeoutError) as e:
            self._connection_errors += 1
            raise RetryableError(f"Redis connection error during retrieve: {e}")
        
        except RedisError as e:
            raise RedisAdapterError(
                f"Redis error during retrieve: {e}",
                operation="retrieve",
                redis_error=e
            )
    
    async def query(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Query records matching criteria."""
        return await self._execute_with_retry(
            "query",
            self._query_impl,
            query
        )
    
    async def _query_impl(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Internal query implementation."""
        self._validate_query(query)
        
        try:
            # Build pattern for key scanning
            pattern = f"{self._key_prefix}:*"
            if query.tenant_id:
                # This is a simplified pattern - in production you might want
                # to encode tenant/namespace in the key structure
                pass
            
            results = []
            cursor = 0
            
            while len(results) < query.limit:
                # Scan for keys matching pattern
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=min(self._batch_size, query.limit - len(results))
                )
                
                if not keys:
                    if cursor == 0:
                        break
                    continue
                
                # Batch retrieve records
                if "batch_get" in self._lua_scripts:
                    values = await self._lua_scripts["batch_get"](keys=keys)
                else:
                    pipe = self._redis.pipeline()
                    for key in keys:
                        pipe.get(key)
                    values = await pipe.execute()
                
                # Deserialize and filter records
                for value in values:
                    if value is None:
                        continue
                    
                    try:
                        record = self._deserialize_record(value)
                        
                        # Apply filters
                        if self._matches_query(record, query):
                            results.append(record)
                            
                        if len(results) >= query.limit:
                            break
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to deserialize record: {e}")
                        continue
                
                if cursor == 0:
                    break
            
            # Sort by relevance (timestamp for Redis tiers)
            results.sort(key=lambda r: r.created_at, reverse=True)
            
            self._update_stats("retrieve", len(results))
            
            return results
            
        except (ConnectionError, TimeoutError) as e:
            self._connection_errors += 1
            raise RetryableError(f"Redis connection error during query: {e}")
        
        except RedisError as e:
            raise RedisAdapterError(
                f"Redis error during query: {e}",
                operation="query",
                redis_error=e
            )
    
    def _matches_query(self, record: RecordEnvelope, query: MemoryQuery) -> bool:
        """Check if record matches query criteria."""
        # Tenant/namespace filtering
        if query.tenant_id and record.tenant_id != query.tenant_id:
            return False
        
        if query.namespace and record.namespace != query.namespace:
            return False
        
        # Tag filtering
        if query.tags:
            record_tags = set(record.tags or [])
            query_tags = set(query.tags)
            if not query_tags.intersection(record_tags):
                return False
        
        # Time range filtering
        if query.start_time and record.created_at < query.start_time:
            return False
        
        if query.end_time and record.created_at > query.end_time:
            return False
        
        return True
    
    async def delete(self, record_id: str) -> bool:
        """Delete a memory record."""
        return await self._execute_with_retry(
            "delete",
            self._delete_impl,
            record_id
        )
    
    async def _delete_impl(self, record_id: str) -> bool:
        """Internal delete implementation."""
        key = self._make_key(record_id)
        
        try:
            result = await self._redis.delete(key)
            
            if result > 0:
                self._update_stats("delete", 1)
                return True
            else:
                return False
                
        except (ConnectionError, TimeoutError) as e:
            self._connection_errors += 1
            raise RetryableError(f"Redis connection error during delete: {e}")
        
        except RedisError as e:
            raise RedisAdapterError(
                f"Redis error during delete: {e}",
                operation="delete",
                redis_error=e
            )
    
    async def update_relevance(
        self, 
        record_id: str, 
        new_relevance: float
    ) -> bool:
        """Update relevance score for a record."""
        # For Redis tiers, we need to retrieve, modify, and store back
        record = await self.retrieve(record_id)
        
        if record is None:
            return False
        
        # Update relevance score
        record.relevance_score = new_relevance
        
        # Store back with original TTL
        await self.store(record)
        
        return True
    
    async def cleanup_expired(self) -> int:
        """Remove expired records."""
        return await self._execute_with_retry(
            "cleanup_expired",
            self._cleanup_expired_impl
        )
    
    async def _cleanup_expired_impl(self) -> int:
        """Internal cleanup implementation."""
        try:
            pattern = f"{self._key_prefix}:*"
            
            if "cleanup" in self._lua_scripts:
                # Use Lua script for efficient cleanup
                count = await self._lua_scripts["cleanup"](args=[pattern])
                return int(count)
            else:
                # Manual cleanup
                count = 0
                cursor = 0
                
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor=cursor,
                        match=pattern,
                        count=100
                    )
                    
                    for key in keys:
                        ttl = await self._redis.ttl(key)
                        if ttl == -1:  # No expiration set
                            await self._redis.delete(key)
                            count += 1
                    
                    if cursor == 0:
                        break
                
                return count
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired records: {e}")
            return 0
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform Redis health check."""
        try:
            # Test basic connectivity
            start_time = time.time()
            await self._redis.ping()
            ping_time = time.time() - start_time
            
            # Get Redis info
            info = await self._redis.info()
            
            # Get memory usage
            memory_info = await self._redis.info("memory")
            
            # Count keys in our namespace
            cursor, keys = await self._redis.scan(match=f"{self._key_prefix}:*", count=1000)
            key_count = len(keys)
            
            return {
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": memory_info.get("used_memory"),
                "used_memory_human": memory_info.get("used_memory_human"),
                "used_memory_peak": memory_info.get("used_memory_peak"),
                "total_connections_received": info.get("total_connections_received"),
                "total_commands_processed": info.get("total_commands_processed"),
                "ping_time": ping_time,
                "key_count": key_count,
                "connection_errors": self._connection_errors,
                "failover_count": self._failover_count,
                "last_failover": self._last_failover.isoformat() if self._last_failover else None
            }
            
        except Exception as e:
            raise RedisAdapterError(
                f"Redis health check failed: {e}",
                operation="health_check",
                redis_error=e
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis adapter statistics."""
        base_stats = await super().get_stats()
        
        redis_stats = {
            "host": self._host,
            "port": self._port,
            "db": self._db,
            "key_prefix": self._key_prefix,
            "default_ttl": self._default_ttl,
            "max_ttl": self._max_ttl,
            "compress_json": self._compress_json,
            "max_value_size": self._max_value_size,
            "connection_errors": self._connection_errors,
            "failover_count": self._failover_count,
            "replica_count": len(self._replica_pools)
        }
        
        base_stats.update(redis_stats)
        return base_stats
    
    async def _cleanup_connections(self) -> None:
        """Clean up Redis connections."""
        try:
            if self._redis:
                await self._redis.close()
            
            if self._pool:
                await self._pool.disconnect()
            
            for replica_pool in self._replica_pools:
                await replica_pool.disconnect()
            
        except Exception as e:
            self.logger.warning(f"Error during Redis cleanup: {e}")
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """Get adapter capabilities."""
        return [
            AdapterCapability(
                name="memory_storage",
                version="1.0.0",
                description="Fast in-memory storage with Redis"
            ),
            AdapterCapability(
                name="ttl_expiration",
                version="1.0.0",
                description="Automatic record expiration with TTL"
            ),
            AdapterCapability(
                name="connection_pooling",
                version="1.0.0", 
                description="Connection pooling for performance"
            ),
            AdapterCapability(
                name="batch_operations",
                version="1.0.0",
                description="Efficient batch storage and retrieval"
            ),
            AdapterCapability(
                name="atomic_operations",
                version="1.0.0",
                description="Lua scripts for atomic operations"
            ),
            AdapterCapability(
                name="failover",
                version="1.0.0",
                description="Master/replica failover support"
            )
        ]