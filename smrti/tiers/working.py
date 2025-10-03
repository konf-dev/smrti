"""
smrti/tiers/working.py - Working Memory Tier Implementation

Working Memory tier provides immediate access to actively used memory items.
Features fast access patterns, automatic eviction, and promotion to short-term memory.
"""

from __future__ import annotations

import time
import asyncio
from typing import Dict, List, Optional, Any, Set, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import logging

try:
    from ..models.base import MemoryItem, SimpleMemoryItem, MemoryTier
    from ..config.base import BaseConfig
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    MemoryItem = None
    SimpleMemoryItem = object
    MemoryTier = None
    BaseConfig = object

# Try to import storage adapters
try:
    from ..adapters.storage.redis_adapter import RedisStorageAdapter, RedisConfig
    from ..adapters.storage.memory_adapter import MemoryStorageAdapter, MemoryConfig
    STORAGE_ADAPTERS_AVAILABLE = True
except ImportError:
    STORAGE_ADAPTERS_AVAILABLE = False
    RedisStorageAdapter = None
    MemoryStorageAdapter = None


class AccessPattern(Enum):
    """Memory access patterns."""
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class AccessRecord:
    """Record of memory access."""
    item_id: str
    pattern: AccessPattern
    timestamp: float
    tenant: str
    namespace: str
    metadata: Optional[Dict[str, Any]] = None
    
    def age_seconds(self) -> float:
        """Get age of access record in seconds."""
        return time.time() - self.timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'item_id': self.item_id,
            'pattern': self.pattern.value,
            'timestamp': self.timestamp,
            'tenant': self.tenant,
            'namespace': self.namespace,
            'metadata': self.metadata or {}
        }


@dataclass
class WorkingMemoryConfig:
    """Configuration for Working Memory tier."""
    
    # Capacity settings
    max_items: int = 1000  # Maximum items in working memory
    max_memory_mb: int = 100  # Maximum memory usage in MB
    
    # Eviction settings
    eviction_policy: str = "lru"  # LRU, LFU, or custom
    eviction_threshold: float = 0.8  # Start evicting when 80% full
    batch_eviction_size: int = 10  # How many items to evict at once
    
    # Access tracking
    track_access_patterns: bool = True
    access_history_size: int = 1000
    
    # Promotion settings
    promotion_threshold: int = 3  # Promote after 3 accesses
    promotion_time_window: int = 300  # Within 5 minutes
    auto_promote_to_short_term: bool = True
    
    # TTL settings
    default_ttl: int = 3600  # 1 hour default TTL
    min_ttl: int = 60  # Minimum 1 minute
    max_ttl: int = 86400  # Maximum 24 hours
    
    # Performance settings
    enable_compression: bool = False
    enable_stats: bool = True
    cleanup_interval: int = 60  # Cleanup every minute
    
    # Storage settings
    storage_type: str = "memory"  # "redis" or "memory"
    namespace: str = "working_memory"


@dataclass
class WorkingMemoryStats:
    """Statistics for Working Memory tier."""
    
    total_items: int = 0
    memory_usage_bytes: int = 0
    memory_usage_mb: float = 0.0
    
    # Operations
    read_count: int = 0
    write_count: int = 0
    update_count: int = 0
    delete_count: int = 0
    eviction_count: int = 0
    promotion_count: int = 0
    
    # Performance
    avg_access_time_ms: float = 0.0
    hit_rate: float = 0.0
    eviction_rate: float = 0.0
    
    # Capacity
    capacity_utilization: float = 0.0
    items_near_eviction: int = 0
    
    # Access patterns
    most_accessed_items: List[str] = None
    recent_access_patterns: List[str] = None
    
    def __post_init__(self):
        if self.most_accessed_items is None:
            self.most_accessed_items = []
        if self.recent_access_patterns is None:
            self.recent_access_patterns = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class WorkingMemoryTier:
    """
    Working Memory tier for immediate access to actively used items.
    
    Features:
    - Fast access patterns with configurable eviction policies
    - Access pattern tracking and analytics
    - Automatic promotion to short-term memory
    - Capacity management with overflow handling
    - Performance monitoring and statistics
    """
    
    def __init__(self, config: WorkingMemoryConfig, 
                 storage_adapter: Optional[Any] = None):
        """Initialize Working Memory tier."""
        self.config = config
        
        # Storage adapter
        if storage_adapter:
            self.storage = storage_adapter
        else:
            # Create default storage adapter based on config
            self.storage = self._create_default_storage()
        
        # Access tracking
        self.access_records: List[AccessRecord] = []
        self.access_counts: Dict[str, int] = {}
        self.last_access: Dict[str, float] = {}
        
        # Statistics
        self.stats = WorkingMemoryStats()
        self._operation_times: List[float] = []
        self._start_time = time.time()
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        # Logger
        self.logger = logging.getLogger(f"smrti.working_memory")
    
    def _create_default_storage(self) -> Any:
        """Create default storage adapter."""
        if not STORAGE_ADAPTERS_AVAILABLE:
            return None
        
        if self.config.storage_type == "redis":
            redis_config = RedisConfig(
                default_ttl=self.config.default_ttl,
                key_prefix=f"smrti_{self.config.namespace}"
            )
            return RedisStorageAdapter(redis_config)
        else:
            memory_config = MemoryConfig(
                default_ttl=self.config.default_ttl,
                max_items_per_namespace=self.config.max_items,
                key_prefix=f"smrti_{self.config.namespace}"
            )
            return MemoryStorageAdapter(memory_config)
    
    async def initialize(self) -> bool:
        """Initialize Working Memory tier."""
        try:
            # Initialize storage adapter
            if self.storage:
                success = await self.storage.initialize()
                if not success:
                    self.logger.error("Failed to initialize storage adapter")
                    return False
            
            # Start cleanup task
            if self.config.cleanup_interval > 0:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            self.logger.info("Working Memory tier initialized successfully")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to initialize Working Memory tier: {e}")
            return False
    
    async def close(self):
        """Close Working Memory tier."""
        self._shutdown = True
        
        # Cancel cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close storage adapter
        if self.storage:
            await self.storage.close()
        
        self.logger.info("Working Memory tier closed")
    
    async def _cleanup_loop(self):
        """Periodic cleanup and maintenance."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                
                if not self._shutdown:
                    await self._perform_maintenance()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")
    
    async def _perform_maintenance(self):
        """Perform maintenance tasks."""
        try:
            # Check capacity and evict if necessary
            await self._check_capacity_and_evict()
            
            # Update statistics
            await self._update_statistics()
            
            # Clean up old access records
            self._cleanup_access_records()
            
            # Promote eligible items
            if self.config.auto_promote_to_short_term:
                await self._promote_eligible_items()
            
        except Exception as e:
            self.logger.error(f"Maintenance error: {e}")
    
    async def store_item(self, item: Any, ttl: Optional[int] = None) -> bool:
        """Store item in working memory."""
        start_time = time.time()
        
        try:
            if not self.storage:
                return False
            
            # Extract item data
            if hasattr(item, 'to_dict'):
                item_data = item.to_dict()
                item_id = item.get_id()
                tenant = item.get_tenant() or "default"
                namespace = item.get_namespace() or "default"
            elif isinstance(item, dict):
                item_data = item
                item_id = item.get('id')
                tenant = item.get('tenant', 'default')
                namespace = item.get('namespace', 'default')
            else:
                return False
            
            if not item_id:
                return False
            
            # Check if we need to evict items first
            await self._check_capacity_and_evict()
            
            # Store item with TTL
            ttl = ttl or self.config.default_ttl
            ttl = max(self.config.min_ttl, min(ttl, self.config.max_ttl))
            
            result = await self.storage.store_item(item_data, ttl)
            
            if result.success:
                # Record access
                if self.config.track_access_patterns:
                    self._record_access(item_id, AccessPattern.WRITE, tenant, namespace)
                
                # Update statistics
                self.stats.write_count += 1
                
                execution_time = (time.time() - start_time) * 1000
                self._operation_times.append(execution_time)
                
                return True
            
            return False
        
        except Exception as e:
            self.logger.error(f"Store error: {e}")
            return False
    
    async def retrieve_item(self, tenant: str, namespace: str, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve item from working memory."""
        start_time = time.time()
        
        try:
            if not self.storage:
                return None
            
            # Retrieve item
            item_data = await self.storage.retrieve_item(tenant, namespace, item_id)
            
            if item_data:
                # Record access
                if self.config.track_access_patterns:
                    self._record_access(item_id, AccessPattern.READ, tenant, namespace)
                
                # Update statistics
                self.stats.read_count += 1
                
                execution_time = (time.time() - start_time) * 1000
                self._operation_times.append(execution_time)
            
            return item_data
        
        except Exception as e:
            self.logger.error(f"Retrieve error: {e}")
            return None
    
    async def update_item(self, item: Any, ttl: Optional[int] = None) -> bool:
        """Update item in working memory."""
        start_time = time.time()
        
        try:
            # Store with update access pattern
            result = await self.store_item(item, ttl)
            
            if result:
                # Extract item info for access recording
                if hasattr(item, 'get_id'):
                    item_id = item.get_id()
                    tenant = item.get_tenant() or "default"
                    namespace = item.get_namespace() or "default"
                elif isinstance(item, dict):
                    item_id = item.get('id')
                    tenant = item.get('tenant', 'default')
                    namespace = item.get('namespace', 'default')
                else:
                    return False
                
                # Record as update instead of write
                if self.config.track_access_patterns and item_id:
                    self._record_access(item_id, AccessPattern.UPDATE, tenant, namespace)
                
                # Update statistics
                self.stats.update_count += 1
                self.stats.write_count -= 1  # Correct the write count
                
                execution_time = (time.time() - start_time) * 1000
                self._operation_times.append(execution_time)
            
            return result
        
        except Exception as e:
            self.logger.error(f"Update error: {e}")
            return False
    
    async def delete_item(self, tenant: str, namespace: str, item_id: str) -> bool:
        """Delete item from working memory."""
        start_time = time.time()
        
        try:
            if not self.storage:
                return False
            
            result = await self.storage.delete_item(tenant, namespace, item_id)
            
            if result.success:
                # Record access
                if self.config.track_access_patterns:
                    self._record_access(item_id, AccessPattern.DELETE, tenant, namespace)
                
                # Clean up tracking data
                self.access_counts.pop(item_id, None)
                self.last_access.pop(item_id, None)
                
                # Update statistics
                self.stats.delete_count += 1
                
                execution_time = (time.time() - start_time) * 1000
                self._operation_times.append(execution_time)
                
                return True
            
            return False
        
        except Exception as e:
            self.logger.error(f"Delete error: {e}")
            return False
    
    async def list_items(self, tenant: str, namespace: str, limit: Optional[int] = None) -> List[str]:
        """List items in working memory."""
        try:
            if not self.storage:
                return []
            
            return await self.storage.list_items(tenant, namespace, limit)
        
        except Exception as e:
            self.logger.error(f"List error: {e}")
            return []
    
    def _record_access(self, item_id: str, pattern: AccessPattern, 
                      tenant: str, namespace: str, metadata: Optional[Dict[str, Any]] = None):
        """Record access pattern."""
        current_time = time.time()
        
        # Create access record
        record = AccessRecord(
            item_id=item_id,
            pattern=pattern,
            timestamp=current_time,
            tenant=tenant,
            namespace=namespace,
            metadata=metadata
        )
        
        # Add to records list
        self.access_records.append(record)
        
        # Update counters
        self.access_counts[item_id] = self.access_counts.get(item_id, 0) + 1
        self.last_access[item_id] = current_time
        
        # Limit access records size
        if len(self.access_records) > self.config.access_history_size:
            # Remove oldest records
            excess = len(self.access_records) - self.config.access_history_size
            self.access_records = self.access_records[excess:]
    
    def _cleanup_access_records(self):
        """Clean up old access records."""
        if not self.config.track_access_patterns:
            return
        
        current_time = time.time()
        cutoff_time = current_time - (self.config.promotion_time_window * 2)  # Keep 2x window
        
        # Filter out old records
        self.access_records = [
            record for record in self.access_records
            if record.timestamp > cutoff_time
        ]
    
    async def _check_capacity_and_evict(self):
        """Check capacity and evict items if necessary."""
        try:
            if not self.storage:
                return
            
            # Get current statistics
            stats = await self.storage.get_stats()
            current_items = stats.get('total_items', 0)
            
            # Check if we need to evict
            items_threshold = self.config.max_items * self.config.eviction_threshold
            
            if current_items > items_threshold:
                # Calculate how many items to evict
                items_to_evict = max(
                    self.config.batch_eviction_size,
                    int(current_items - items_threshold)
                )
                
                await self._evict_items(items_to_evict)
        
        except Exception as e:
            self.logger.error(f"Capacity check error: {e}")
    
    async def _evict_items(self, count: int):
        """Evict items based on eviction policy."""
        try:
            if self.config.eviction_policy == "lru":
                await self._evict_lru_items(count)
            elif self.config.eviction_policy == "lfu":
                await self._evict_lfu_items(count)
            else:
                await self._evict_lru_items(count)  # Default to LRU
        
        except Exception as e:
            self.logger.error(f"Eviction error: {e}")
    
    async def _evict_lru_items(self, count: int):
        """Evict least recently used items."""
        # Sort items by last access time
        sorted_items = sorted(
            self.last_access.items(),
            key=lambda x: x[1]  # Sort by timestamp
        )
        
        # Take the oldest items
        items_to_evict = sorted_items[:count]
        
        for item_id, _ in items_to_evict:
            # Need tenant/namespace info to delete
            # For now, we'll need to enhance this with better tracking
            # This is a simplified version
            success = False
            
            # Try common tenant/namespace combinations
            for tenant in ["default"]:
                for namespace in ["default", self.config.namespace]:
                    result = await self.storage.delete_item(tenant, namespace, item_id)
                    if result.success:
                        success = True
                        break
                if success:
                    break
            
            if success:
                # Clean up tracking
                self.access_counts.pop(item_id, None)
                self.last_access.pop(item_id, None)
                self.stats.eviction_count += 1
    
    async def _evict_lfu_items(self, count: int):
        """Evict least frequently used items."""
        # Sort items by access count
        sorted_items = sorted(
            self.access_counts.items(),
            key=lambda x: x[1]  # Sort by access count
        )
        
        # Take the least accessed items
        items_to_evict = sorted_items[:count]
        
        for item_id, _ in items_to_evict:
            # Similar to LRU eviction
            success = False
            
            for tenant in ["default"]:
                for namespace in ["default", self.config.namespace]:
                    result = await self.storage.delete_item(tenant, namespace, item_id)
                    if result.success:
                        success = True
                        break
                if success:
                    break
            
            if success:
                self.access_counts.pop(item_id, None)
                self.last_access.pop(item_id, None)
                self.stats.eviction_count += 1
    
    async def _promote_eligible_items(self):
        """Promote items that meet promotion criteria."""
        current_time = time.time()
        time_window = self.config.promotion_time_window
        
        # Find items with sufficient access count in time window
        eligible_items = []
        
        for item_id, access_count in self.access_counts.items():
            if access_count >= self.config.promotion_threshold:
                # Check if accesses are within time window
                last_access_time = self.last_access.get(item_id, 0)
                if current_time - last_access_time <= time_window:
                    eligible_items.append(item_id)
        
        # For now, just log promotion candidates
        # In full implementation, this would interact with short-term memory tier
        if eligible_items:
            self.logger.info(f"Items eligible for promotion: {eligible_items}")
            self.stats.promotion_count += len(eligible_items)
    
    async def _update_statistics(self):
        """Update tier statistics."""
        try:
            if not self.storage:
                return
            
            # Get storage statistics
            storage_stats = await self.storage.get_stats()
            
            # Update basic stats
            self.stats.total_items = storage_stats.get('total_items', 0)
            self.stats.memory_usage_bytes = storage_stats.get('memory_usage_bytes', 0)
            self.stats.memory_usage_mb = self.stats.memory_usage_bytes / (1024 * 1024)
            
            # Calculate capacity utilization
            self.stats.capacity_utilization = self.stats.total_items / max(self.config.max_items, 1)
            
            # Calculate performance metrics
            if self._operation_times:
                self.stats.avg_access_time_ms = sum(self._operation_times) / len(self._operation_times)
                # Keep only recent operation times
                if len(self._operation_times) > 100:
                    self._operation_times = self._operation_times[-100:]
            
            # Calculate hit rate (simplified)
            total_operations = (self.stats.read_count + self.stats.write_count + 
                              self.stats.update_count + self.stats.delete_count)
            if total_operations > 0:
                self.stats.hit_rate = self.stats.read_count / total_operations
            
            # Calculate eviction rate
            if self.stats.write_count > 0:
                self.stats.eviction_rate = self.stats.eviction_count / self.stats.write_count
            
            # Update most accessed items
            sorted_access = sorted(
                self.access_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
            self.stats.most_accessed_items = [item_id for item_id, _ in sorted_access[:10]]
            
            # Update recent access patterns
            recent_patterns = []
            for record in self.access_records[-20:]:  # Last 20 accesses
                recent_patterns.append(f"{record.item_id}:{record.pattern.value}")
            self.stats.recent_access_patterns = recent_patterns
        
        except Exception as e:
            self.logger.error(f"Statistics update error: {e}")
    
    async def get_stats(self) -> WorkingMemoryStats:
        """Get current statistics."""
        await self._update_statistics()
        return self.stats
    
    async def health_check(self) -> bool:
        """Check tier health."""
        try:
            if not self.storage:
                return False
            
            return await self.storage.health_check()
        
        except Exception:
            return False
    
    def get_access_patterns(self, item_id: Optional[str] = None) -> List[AccessRecord]:
        """Get access patterns for item or all items."""
        if item_id:
            return [
                record for record in self.access_records
                if record.item_id == item_id
            ]
        else:
            return self.access_records.copy()


def create_working_memory_tier(**kwargs) -> WorkingMemoryTier:
    """
    Convenience function to create Working Memory tier.
    
    Args:
        **kwargs: Configuration parameters for WorkingMemoryConfig
        
    Returns:
        WorkingMemoryTier instance
    """
    config = WorkingMemoryConfig(**kwargs)
    return WorkingMemoryTier(config)