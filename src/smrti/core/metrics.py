"""Prometheus metrics for observability."""

from prometheus_client import Counter, Histogram, Info

# Application info
app_info = Info("smrti_app", "Application information")
app_info.info(
    {
        "version": "2.0.0",
        "name": "Smrti Memory Storage System",
    }
)

# HTTP request metrics
http_requests_total = Counter(
    "smrti_http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "smrti_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Storage operation metrics
storage_operations_total = Counter(
    "smrti_storage_operations_total",
    "Total storage operations",
    labelnames=["operation", "memory_type", "status"],
)

storage_operation_duration_seconds = Histogram(
    "smrti_storage_operation_duration_seconds",
    "Storage operation duration in seconds",
    labelnames=["operation", "memory_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# Embedding metrics
embedding_generations_total = Counter(
    "smrti_embedding_generations_total",
    "Total embedding generations",
    labelnames=["provider", "status"],
)

embedding_generation_duration_seconds = Histogram(
    "smrti_embedding_generation_duration_seconds",
    "Embedding generation duration in seconds",
    labelnames=["provider"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

embedding_cache_hits_total = Counter(
    "smrti_embedding_cache_hits_total",
    "Total embedding cache hits",
    labelnames=["provider"],
)

embedding_cache_misses_total = Counter(
    "smrti_embedding_cache_misses_total",
    "Total embedding cache misses",
    labelnames=["provider"],
)

# Database connection metrics
db_connections_active = Histogram(
    "smrti_db_connections_active",
    "Number of active database connections",
    labelnames=["db_type"],
    buckets=(1, 5, 10, 20, 50, 100),
)

# Error metrics
errors_total = Counter(
    "smrti_errors_total",
    "Total errors",
    labelnames=["error_type", "component"],
)
