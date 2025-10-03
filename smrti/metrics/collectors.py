"""
smrti/metrics/collectors.py - Core metrics collection components

Implements comprehensive metrics collection for memory operations, tier performance,
consolidation activities, and system health monitoring.
"""

from __future__ import annotations

import time
import threading
from typing import Dict, List, Optional, Any, Callable, Set, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import asyncio
import psutil
import os


class MetricType(str, Enum):
    """Types of metrics collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class MetricLevel(str, Enum):
    """Metric collection levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DEBUG = "debug"


@dataclass
class MetricPoint:
    """Single metric data point."""
    
    name: str
    value: Union[int, float]
    metric_type: MetricType
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)
    level: MetricLevel = MetricLevel.MEDIUM
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metric point to dictionary."""
        return {
            'name': self.name,
            'value': self.value,
            'type': self.metric_type.value,
            'timestamp': self.timestamp,
            'labels': self.labels,
            'level': self.level.value
        }


@dataclass
class MemoryTierMetrics:
    """Metrics for individual memory tiers."""
    
    tier_name: str
    
    # Record statistics
    total_records: int = 0
    active_records: int = 0
    deleted_records: int = 0
    
    # Storage statistics
    total_size_bytes: int = 0
    avg_record_size: float = 0.0
    compression_ratio: float = 1.0
    
    # Operation counts
    read_operations: int = 0
    write_operations: int = 0
    delete_operations: int = 0
    search_operations: int = 0
    
    # Performance metrics
    avg_read_latency_ms: float = 0.0
    avg_write_latency_ms: float = 0.0
    avg_search_latency_ms: float = 0.0
    
    # Cache statistics
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_ratio: float = 0.0
    
    # Error tracking
    read_errors: int = 0
    write_errors: int = 0
    connection_errors: int = 0
    
    # Timestamps
    last_updated: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    
    def calculate_hit_ratio(self) -> float:
        """Calculate cache hit ratio."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total
    
    def calculate_error_rate(self) -> float:
        """Calculate overall error rate."""
        total_ops = self.read_operations + self.write_operations + self.delete_operations
        total_errors = self.read_errors + self.write_errors + self.connection_errors
        if total_ops == 0:
            return 0.0
        return total_errors / total_ops
    
    def to_metric_points(self) -> List[MetricPoint]:
        """Convert to list of metric points."""
        labels = {'tier': self.tier_name}
        
        points = [
            MetricPoint('memory_tier_total_records', self.total_records, MetricType.GAUGE, labels=labels),
            MetricPoint('memory_tier_active_records', self.active_records, MetricType.GAUGE, labels=labels),
            MetricPoint('memory_tier_size_bytes', self.total_size_bytes, MetricType.GAUGE, labels=labels),
            MetricPoint('memory_tier_avg_record_size', self.avg_record_size, MetricType.GAUGE, labels=labels),
            
            MetricPoint('memory_tier_read_ops_total', self.read_operations, MetricType.COUNTER, labels=labels),
            MetricPoint('memory_tier_write_ops_total', self.write_operations, MetricType.COUNTER, labels=labels),
            MetricPoint('memory_tier_search_ops_total', self.search_operations, MetricType.COUNTER, labels=labels),
            
            MetricPoint('memory_tier_read_latency_ms', self.avg_read_latency_ms, MetricType.GAUGE, labels=labels),
            MetricPoint('memory_tier_write_latency_ms', self.avg_write_latency_ms, MetricType.GAUGE, labels=labels),
            MetricPoint('memory_tier_search_latency_ms', self.avg_search_latency_ms, MetricType.GAUGE, labels=labels),
            
            MetricPoint('memory_tier_cache_hit_ratio', self.calculate_hit_ratio(), MetricType.GAUGE, labels=labels),
            MetricPoint('memory_tier_error_rate', self.calculate_error_rate(), MetricType.GAUGE, labels=labels),
        ]
        
        return points


@dataclass
class ConsolidationMetrics:
    """Metrics for consolidation operations."""
    
    # Task statistics
    total_tasks: int = 0
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    
    # Record processing
    records_processed: int = 0
    records_merged: int = 0
    records_promoted: int = 0
    records_archived: int = 0
    records_deleted: int = 0
    
    # Performance metrics
    avg_task_duration_ms: float = 0.0
    avg_processing_rate_rps: float = 0.0
    
    # Efficiency metrics
    merge_efficiency: float = 0.0  # Percentage of records successfully merged
    promotion_accuracy: float = 0.0  # Accuracy of tier promotions
    
    # Resource usage
    peak_memory_usage_mb: float = 0.0
    avg_cpu_usage_percent: float = 0.0
    
    # Error tracking
    task_failures: int = 0
    merge_failures: int = 0
    promotion_failures: int = 0
    
    # Timestamps
    last_consolidation: float = 0.0
    last_updated: float = field(default_factory=time.time)
    
    def calculate_merge_efficiency(self) -> float:
        """Calculate merge operation efficiency."""
        if self.records_processed == 0:
            return 0.0
        return self.records_merged / self.records_processed
    
    def calculate_success_rate(self) -> float:
        """Calculate overall task success rate."""
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks
    
    def to_metric_points(self) -> List[MetricPoint]:
        """Convert to list of metric points."""
        points = [
            MetricPoint('consolidation_tasks_total', self.total_tasks, MetricType.COUNTER),
            MetricPoint('consolidation_tasks_active', self.active_tasks, MetricType.GAUGE),
            MetricPoint('consolidation_tasks_completed', self.completed_tasks, MetricType.COUNTER),
            MetricPoint('consolidation_tasks_failed', self.failed_tasks, MetricType.COUNTER),
            
            MetricPoint('consolidation_records_processed', self.records_processed, MetricType.COUNTER),
            MetricPoint('consolidation_records_merged', self.records_merged, MetricType.COUNTER),
            MetricPoint('consolidation_records_promoted', self.records_promoted, MetricType.COUNTER),
            MetricPoint('consolidation_records_deleted', self.records_deleted, MetricType.COUNTER),
            
            MetricPoint('consolidation_avg_task_duration_ms', self.avg_task_duration_ms, MetricType.GAUGE),
            MetricPoint('consolidation_processing_rate_rps', self.avg_processing_rate_rps, MetricType.GAUGE),
            MetricPoint('consolidation_merge_efficiency', self.calculate_merge_efficiency(), MetricType.GAUGE),
            MetricPoint('consolidation_success_rate', self.calculate_success_rate(), MetricType.GAUGE),
            
            MetricPoint('consolidation_peak_memory_mb', self.peak_memory_usage_mb, MetricType.GAUGE),
            MetricPoint('consolidation_avg_cpu_percent', self.avg_cpu_usage_percent, MetricType.GAUGE),
        ]
        
        return points


@dataclass
class QueryMetrics:
    """Metrics for query operations."""
    
    # Query statistics
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    cached_queries: int = 0
    
    # Query types
    semantic_queries: int = 0
    keyword_queries: int = 0
    temporal_queries: int = 0
    hybrid_queries: int = 0
    
    # Performance metrics
    avg_query_latency_ms: float = 0.0
    avg_result_count: float = 0.0
    avg_relevance_score: float = 0.0
    
    # Resource usage
    avg_memory_per_query_mb: float = 0.0
    avg_cpu_per_query_percent: float = 0.0
    
    # Cache metrics
    cache_hit_ratio: float = 0.0
    cache_size_mb: float = 0.0
    
    # Error tracking
    timeout_errors: int = 0
    validation_errors: int = 0
    system_errors: int = 0
    
    # Timestamps
    last_query: float = 0.0
    last_updated: float = field(default_factory=time.time)
    
    def calculate_success_rate(self) -> float:
        """Calculate query success rate."""
        if self.total_queries == 0:
            return 0.0
        return self.successful_queries / self.total_queries
    
    def calculate_cache_efficiency(self) -> float:
        """Calculate cache utilization efficiency."""
        if self.total_queries == 0:
            return 0.0
        return self.cached_queries / self.total_queries
    
    def to_metric_points(self) -> List[MetricPoint]:
        """Convert to list of metric points."""
        points = [
            MetricPoint('query_total', self.total_queries, MetricType.COUNTER),
            MetricPoint('query_successful', self.successful_queries, MetricType.COUNTER),
            MetricPoint('query_failed', self.failed_queries, MetricType.COUNTER),
            MetricPoint('query_cached', self.cached_queries, MetricType.COUNTER),
            
            MetricPoint('query_semantic_total', self.semantic_queries, MetricType.COUNTER),
            MetricPoint('query_keyword_total', self.keyword_queries, MetricType.COUNTER),
            MetricPoint('query_temporal_total', self.temporal_queries, MetricType.COUNTER),
            MetricPoint('query_hybrid_total', self.hybrid_queries, MetricType.COUNTER),
            
            MetricPoint('query_avg_latency_ms', self.avg_query_latency_ms, MetricType.GAUGE),
            MetricPoint('query_avg_result_count', self.avg_result_count, MetricType.GAUGE),
            MetricPoint('query_avg_relevance_score', self.avg_relevance_score, MetricType.GAUGE),
            
            MetricPoint('query_success_rate', self.calculate_success_rate(), MetricType.GAUGE),
            MetricPoint('query_cache_hit_ratio', self.cache_hit_ratio, MetricType.GAUGE),
            MetricPoint('query_cache_efficiency', self.calculate_cache_efficiency(), MetricType.GAUGE),
        ]
        
        return points


@dataclass
class SystemMetrics:
    """System-wide health and performance metrics."""
    
    # System resource usage
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_usage_percent: float = 0.0
    disk_usage_mb: float = 0.0
    disk_usage_percent: float = 0.0
    
    # Network metrics
    network_bytes_sent: int = 0
    network_bytes_received: int = 0
    active_connections: int = 0
    
    # Process metrics
    active_threads: int = 0
    open_file_descriptors: int = 0
    uptime_seconds: float = 0.0
    
    # Performance metrics
    requests_per_second: float = 0.0
    avg_response_time_ms: float = 0.0
    error_rate_percent: float = 0.0
    
    # Health indicators
    is_healthy: bool = True
    last_health_check: float = 0.0
    health_score: float = 1.0
    
    # Timestamps
    last_updated: float = field(default_factory=time.time)
    
    @classmethod
    def collect_system_metrics(cls) -> 'SystemMetrics':
        """Collect current system metrics."""
        try:
            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Network
            net_io = psutil.net_io_counters()
            
            # Process info
            process = psutil.Process()
            
            return cls(
                cpu_usage_percent=cpu_percent,
                memory_usage_mb=memory.used / 1024 / 1024,
                memory_usage_percent=memory.percent,
                disk_usage_mb=disk.used / 1024 / 1024,
                disk_usage_percent=(disk.used / disk.total) * 100,
                
                network_bytes_sent=net_io.bytes_sent,
                network_bytes_received=net_io.bytes_recv,
                active_connections=len(psutil.net_connections()),
                
                active_threads=process.num_threads(),
                open_file_descriptors=process.num_fds() if hasattr(process, 'num_fds') else 0,
                uptime_seconds=time.time() - process.create_time(),
                
                is_healthy=True,  # Would be calculated based on thresholds
                last_health_check=time.time(),
                health_score=1.0,  # Would be calculated based on various factors
            )
            
        except Exception as e:
            # Return default metrics on error
            return cls(
                is_healthy=False,
                health_score=0.0,
                last_health_check=time.time()
            )
    
    def calculate_health_score(self) -> float:
        """Calculate overall system health score."""
        score = 1.0
        
        # Penalize high resource usage
        if self.cpu_usage_percent > 80:
            score -= 0.2
        if self.memory_usage_percent > 85:
            score -= 0.3
        if self.disk_usage_percent > 90:
            score -= 0.2
        
        # Penalize high error rate
        if self.error_rate_percent > 5:
            score -= 0.3
        
        return max(0.0, score)
    
    def to_metric_points(self) -> List[MetricPoint]:
        """Convert to list of metric points."""
        points = [
            MetricPoint('system_cpu_usage_percent', self.cpu_usage_percent, MetricType.GAUGE, level=MetricLevel.HIGH),
            MetricPoint('system_memory_usage_mb', self.memory_usage_mb, MetricType.GAUGE, level=MetricLevel.HIGH),
            MetricPoint('system_memory_usage_percent', self.memory_usage_percent, MetricType.GAUGE, level=MetricLevel.HIGH),
            MetricPoint('system_disk_usage_mb', self.disk_usage_mb, MetricType.GAUGE, level=MetricLevel.MEDIUM),
            MetricPoint('system_disk_usage_percent', self.disk_usage_percent, MetricType.GAUGE, level=MetricLevel.MEDIUM),
            
            MetricPoint('system_network_bytes_sent', self.network_bytes_sent, MetricType.COUNTER, level=MetricLevel.LOW),
            MetricPoint('system_network_bytes_received', self.network_bytes_received, MetricType.COUNTER, level=MetricLevel.LOW),
            MetricPoint('system_active_connections', self.active_connections, MetricType.GAUGE, level=MetricLevel.MEDIUM),
            
            MetricPoint('system_active_threads', self.active_threads, MetricType.GAUGE, level=MetricLevel.LOW),
            MetricPoint('system_open_fds', self.open_file_descriptors, MetricType.GAUGE, level=MetricLevel.LOW),
            MetricPoint('system_uptime_seconds', self.uptime_seconds, MetricType.GAUGE, level=MetricLevel.LOW),
            
            MetricPoint('system_requests_per_second', self.requests_per_second, MetricType.GAUGE, level=MetricLevel.HIGH),
            MetricPoint('system_avg_response_time_ms', self.avg_response_time_ms, MetricType.GAUGE, level=MetricLevel.HIGH),
            MetricPoint('system_error_rate_percent', self.error_rate_percent, MetricType.GAUGE, level=MetricLevel.CRITICAL),
            
            MetricPoint('system_health_score', self.calculate_health_score(), MetricType.GAUGE, level=MetricLevel.CRITICAL),
            MetricPoint('system_is_healthy', 1.0 if self.is_healthy else 0.0, MetricType.GAUGE, level=MetricLevel.CRITICAL),
        ]
        
        return points


class MetricsCollector:
    """Central metrics collection coordinator."""
    
    def __init__(self, collection_interval: float = 60.0):
        """Initialize the metrics collector.
        
        Args:
            collection_interval: Interval between automatic collections in seconds
        """
        self.collection_interval = collection_interval
        self.is_collecting = False
        
        # Metrics storage
        self.tier_metrics: Dict[str, MemoryTierMetrics] = {}
        self.consolidation_metrics = ConsolidationMetrics()
        self.query_metrics = QueryMetrics()
        self.system_metrics = SystemMetrics()
        
        # Historical data (last 1000 points)
        self.metric_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.metric_points: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))  # Store full MetricPoint objects
        
        # Collection control
        self._collection_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Callbacks for real-time updates
        self._metric_callbacks: List[Callable[[List[MetricPoint]], None]] = []
        
        # Performance tracking
        self._last_collection_time = 0.0
        self._collection_count = 0
    
    def register_tier(self, tier_name: str) -> None:
        """Register a memory tier for metrics collection.
        
        Args:
            tier_name: Name of the memory tier
        """
        if tier_name not in self.tier_metrics:
            self.tier_metrics[tier_name] = MemoryTierMetrics(tier_name=tier_name)
    
    def update_tier_metrics(self, tier_name: str, **kwargs) -> None:
        """Update metrics for a specific tier.
        
        Args:
            tier_name: Name of the tier
            **kwargs: Metric values to update
        """
        if tier_name not in self.tier_metrics:
            self.register_tier(tier_name)
        
        tier_metrics = self.tier_metrics[tier_name]
        
        for key, value in kwargs.items():
            if hasattr(tier_metrics, key):
                setattr(tier_metrics, key, value)
        
        tier_metrics.last_updated = time.time()
    
    def record_operation(self, tier_name: str, operation: str, 
                        latency_ms: Optional[float] = None,
                        success: bool = True) -> None:
        """Record an operation for a tier.
        
        Args:
            tier_name: Name of the tier
            operation: Type of operation (read, write, delete, search)
            latency_ms: Operation latency in milliseconds
            success: Whether the operation succeeded
        """
        if tier_name not in self.tier_metrics:
            self.register_tier(tier_name)
        
        tier_metrics = self.tier_metrics[tier_name]
        
        # Update operation counts
        if operation == 'read':
            tier_metrics.read_operations += 1
            if not success:
                tier_metrics.read_errors += 1
            if latency_ms is not None:
                # Simple moving average (would use proper averaging in production)
                tier_metrics.avg_read_latency_ms = (
                    (tier_metrics.avg_read_latency_ms + latency_ms) / 2
                )
        
        elif operation == 'write':
            tier_metrics.write_operations += 1
            if not success:
                tier_metrics.write_errors += 1
            if latency_ms is not None:
                tier_metrics.avg_write_latency_ms = (
                    (tier_metrics.avg_write_latency_ms + latency_ms) / 2
                )
        
        elif operation == 'search':
            tier_metrics.search_operations += 1
            if latency_ms is not None:
                tier_metrics.avg_search_latency_ms = (
                    (tier_metrics.avg_search_latency_ms + latency_ms) / 2
                )
        
        elif operation == 'delete':
            tier_metrics.delete_operations += 1
        
        tier_metrics.last_updated = time.time()
    
    def record_consolidation_event(self, event_type: str, **kwargs) -> None:
        """Record a consolidation event.
        
        Args:
            event_type: Type of consolidation event
            **kwargs: Additional event data
        """
        if event_type == 'task_started':
            self.consolidation_metrics.active_tasks += 1
            self.consolidation_metrics.total_tasks += 1
        
        elif event_type == 'task_completed':
            self.consolidation_metrics.active_tasks = max(0, self.consolidation_metrics.active_tasks - 1)
            self.consolidation_metrics.completed_tasks += 1
            self.consolidation_metrics.last_consolidation = time.time()
            
            # Update duration if provided
            duration_ms = kwargs.get('duration_ms')
            if duration_ms is not None:
                self.consolidation_metrics.avg_task_duration_ms = (
                    (self.consolidation_metrics.avg_task_duration_ms + duration_ms) / 2
                )
        
        elif event_type == 'task_failed':
            self.consolidation_metrics.active_tasks = max(0, self.consolidation_metrics.active_tasks - 1)
            self.consolidation_metrics.failed_tasks += 1
            self.consolidation_metrics.task_failures += 1
        
        elif event_type == 'records_processed':
            count = kwargs.get('count', 0)
            self.consolidation_metrics.records_processed += count
        
        elif event_type == 'records_merged':
            count = kwargs.get('count', 0)
            self.consolidation_metrics.records_merged += count
        
        elif event_type == 'records_promoted':
            count = kwargs.get('count', 0)
            self.consolidation_metrics.records_promoted += count
        
        self.consolidation_metrics.last_updated = time.time()
    
    def record_query_event(self, query_type: str, success: bool = True,
                          latency_ms: Optional[float] = None,
                          result_count: Optional[int] = None,
                          relevance_score: Optional[float] = None,
                          from_cache: bool = False) -> None:
        """Record a query event.
        
        Args:
            query_type: Type of query (semantic, keyword, temporal, hybrid)
            success: Whether the query succeeded
            latency_ms: Query latency in milliseconds
            result_count: Number of results returned
            relevance_score: Average relevance score of results
            from_cache: Whether results came from cache
        """
        self.query_metrics.total_queries += 1
        
        if success:
            self.query_metrics.successful_queries += 1
        else:
            self.query_metrics.failed_queries += 1
        
        if from_cache:
            self.query_metrics.cached_queries += 1
        
        # Update query type counters
        if query_type == 'semantic':
            self.query_metrics.semantic_queries += 1
        elif query_type == 'keyword':
            self.query_metrics.keyword_queries += 1
        elif query_type == 'temporal':
            self.query_metrics.temporal_queries += 1
        elif query_type == 'hybrid':
            self.query_metrics.hybrid_queries += 1
        
        # Update averages (simple approach for demo)
        if latency_ms is not None:
            self.query_metrics.avg_query_latency_ms = (
                (self.query_metrics.avg_query_latency_ms + latency_ms) / 2
            )
        
        if result_count is not None:
            self.query_metrics.avg_result_count = (
                (self.query_metrics.avg_result_count + result_count) / 2
            )
        
        if relevance_score is not None:
            self.query_metrics.avg_relevance_score = (
                (self.query_metrics.avg_relevance_score + relevance_score) / 2
            )
        
        self.query_metrics.last_query = time.time()
        self.query_metrics.last_updated = time.time()
    
    def collect_all_metrics(self) -> List[MetricPoint]:
        """Collect all current metrics.
        
        Returns:
            List of all metric points
        """
        all_points = []
        
        # Collect tier metrics
        for tier_metrics in self.tier_metrics.values():
            all_points.extend(tier_metrics.to_metric_points())
        
        # Collect consolidation metrics
        all_points.extend(self.consolidation_metrics.to_metric_points())
        
        # Collect query metrics
        all_points.extend(self.query_metrics.to_metric_points())
        
        # Collect system metrics
        self.system_metrics = SystemMetrics.collect_system_metrics()
        all_points.extend(self.system_metrics.to_metric_points())
        
        # Store in history
        timestamp = time.time()
        for point in all_points:
            self.metric_history[point.name].append((timestamp, point.value))
        
        # Update collection stats
        self._last_collection_time = timestamp
        self._collection_count += 1
        
        # Notify callbacks
        for callback in self._metric_callbacks:
            try:
                callback(all_points)
            except Exception as e:
                print(f"Error in metric callback: {e}")
        
        return all_points
    
    def start_collection(self) -> None:
        """Start automatic metrics collection."""
        if self.is_collecting:
            return
        
        self.is_collecting = True
        self._stop_event.clear()
        
        self._collection_thread = threading.Thread(
            target=self._collection_loop,
            daemon=True
        )
        self._collection_thread.start()
    
    def stop_collection(self) -> None:
        """Stop automatic metrics collection."""
        if not self.is_collecting:
            return
        
        self.is_collecting = False
        self._stop_event.set()
        
        if self._collection_thread:
            self._collection_thread.join(timeout=5.0)
            self._collection_thread = None
    
    def _collection_loop(self) -> None:
        """Main collection loop running in background thread."""
        while not self._stop_event.is_set():
            try:
                self.collect_all_metrics()
            except Exception as e:
                print(f"Error during metrics collection: {e}")
            
            # Wait for next collection interval
            self._stop_event.wait(self.collection_interval)
    
    def add_metric_callback(self, callback: Callable[[List[MetricPoint]], None]) -> None:
        """Add a callback for real-time metric updates.
        
        Args:
            callback: Function to call with new metrics
        """
        self._metric_callbacks.append(callback)
    
    def remove_metric_callback(self, callback: Callable[[List[MetricPoint]], None]) -> None:
        """Remove a metric callback.
        
        Args:
            callback: Callback function to remove
        """
        if callback in self._metric_callbacks:
            self._metric_callbacks.remove(callback)
    
    def record_metric(self, name: str, value: Union[int, float], 
                     metric_type: MetricType, level: MetricLevel, 
                     labels: Optional[Dict[str, str]] = None) -> None:
        """Record a custom metric point.
        
        Args:
            name: Metric name
            value: Metric value
            metric_type: Type of metric
            level: Severity level
            labels: Optional labels for the metric
        """
        if labels is None:
            labels = {}
        
        # Create MetricPoint
        metric_point = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            metric_type=metric_type,
            level=level,
            labels=labels
        )
        
        # Store in both formats for compatibility
        self.metric_history[name].append((metric_point.timestamp, metric_point.value))
        self.metric_points[name].append(metric_point)
        
        # Trigger callbacks
        for callback in self._metric_callbacks:
            try:
                callback(metric_point)
            except Exception as e:
                print(f"Callback error: {e}")
    
    def get_metric_history(self, metric_name: str, 
                          limit: Optional[int] = None) -> List[tuple[float, float]]:
        """Get historical data for a specific metric.
        
        Args:
            metric_name: Name of the metric
            limit: Maximum number of data points to return
            
        Returns:
            List of (timestamp, value) tuples
        """
        history = list(self.metric_history.get(metric_name, []))
        
        if limit and len(history) > limit:
            history = history[-limit:]
        
        return history
    
    def get_all_metrics(self) -> List[MetricPoint]:
        """Get all current metric points.
        
        Returns:
            List of all metric points collected
        """
        all_metrics = []
        
        # Get metrics from stored MetricPoint objects
        for metric_name, points in self.metric_points.items():
            if points:
                # Get all points, not just the latest
                all_metrics.extend(list(points))
        
        # If no MetricPoint objects, fall back to history
        if not all_metrics:
            for metric_name, history in self.metric_history.items():
                if history:
                    timestamp, value = history[-1]
                    metric_point = MetricPoint(
                        name=metric_name,
                        value=value,
                        timestamp=timestamp,
                        metric_type=MetricType.GAUGE,
                        level=MetricLevel.MEDIUM,
                        labels={}
                    )
                    all_metrics.append(metric_point)
        
        return all_metrics
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about metrics collection.
        
        Returns:
            Dictionary with collection statistics
        """
        return {
            'is_collecting': self.is_collecting,
            'collection_interval': self.collection_interval,
            'collection_count': self._collection_count,
            'last_collection_time': self._last_collection_time,
            'registered_tiers': len(self.tier_metrics),
            'metric_callbacks': len(self._metric_callbacks),
            'total_metric_types': len(self.metric_history),
            'uptime_seconds': time.time() - (self._last_collection_time - self.collection_interval * self._collection_count) if self._collection_count > 0 else 0
        }