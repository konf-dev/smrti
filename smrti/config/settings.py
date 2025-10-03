"""
smrti/config/settings.py - Configuration settings and validation

Implements comprehensive configuration management with Pydantic validation,
environment variable support, and type safety.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


# Configuration enums for type safety
class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AdapterType(str, Enum):
    """Supported adapter types."""
    REDIS = "redis"
    CHROMA = "chroma"
    POSTGRESQL = "postgresql"
    NEO4J = "neo4j"
    ELASTICSEARCH = "elasticsearch"


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"
    COHERE = "cohere"


class TierType(str, Enum):
    """Memory tier types."""
    WORKING = "working"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


# Configuration models
class AdapterConfiguration(BaseModel):
    """Configuration for storage adapters."""
    
    model_config = ConfigDict(
        extra="allow",  # Allow adapter-specific settings
        validate_assignment=True
    )
    
    type: AdapterType = Field(..., description="Type of adapter")
    connection_string: Optional[str] = Field(None, description="Connection string or URL")
    host: Optional[str] = Field(None, description="Host address")
    port: Optional[int] = Field(None, description="Port number")
    database: Optional[str] = Field(None, description="Database name")
    username: Optional[str] = Field(None, description="Username for authentication")
    password: Optional[str] = Field(None, description="Password for authentication")
    
    # Connection pool settings
    max_connections: int = Field(default=10, ge=1, le=100, description="Maximum connections in pool")
    min_connections: int = Field(default=1, ge=1, description="Minimum connections in pool")
    connection_timeout: float = Field(default=30.0, ge=1.0, description="Connection timeout in seconds")
    
    # Retry settings
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, ge=0.1, description="Delay between retries in seconds")
    
    # Cache settings
    enable_cache: bool = Field(default=True, description="Enable query result caching")
    cache_ttl: int = Field(default=300, ge=0, description="Cache TTL in seconds")
    
    # Additional adapter-specific settings
    adapter_settings: Dict[str, Any] = Field(default_factory=dict, description="Adapter-specific configuration")
    
    @field_validator('port')
    @classmethod
    def validate_port(cls, v: Optional[int]) -> Optional[int]:
        """Validate port number range."""
        if v is not None and (v < 1 or v > 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @field_validator('min_connections')
    @classmethod
    def validate_min_connections(cls, v: int, info) -> int:
        """Ensure min_connections <= max_connections."""
        if hasattr(info.data, 'max_connections') and v > info.data['max_connections']:
            raise ValueError("min_connections cannot exceed max_connections")
        return v


class TierConfiguration(BaseModel):
    """Configuration for individual memory tiers."""
    
    model_config = ConfigDict(validate_assignment=True)
    
    tier_type: TierType = Field(..., description="Type of memory tier")
    adapter: AdapterConfiguration = Field(..., description="Storage adapter configuration")
    
    # Capacity settings
    max_records: Optional[int] = Field(None, ge=1, description="Maximum number of records")
    max_size_mb: Optional[float] = Field(None, ge=0.1, description="Maximum size in MB")
    
    # Retention settings
    ttl_seconds: Optional[int] = Field(None, ge=1, description="Time to live in seconds")
    max_age_days: Optional[float] = Field(None, ge=0.1, description="Maximum age in days")
    
    # Tier-specific settings
    importance_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance threshold for tier")
    consolidation_enabled: bool = Field(default=True, description="Enable consolidation for this tier")
    
    # Performance settings
    batch_size: int = Field(default=100, ge=1, le=1000, description="Batch size for operations")
    prefetch_size: int = Field(default=50, ge=1, description="Number of records to prefetch")
    
    # Tier-specific metadata
    tier_settings: Dict[str, Any] = Field(default_factory=dict, description="Tier-specific configuration")


class EmbeddingConfiguration(BaseModel):
    """Configuration for embedding providers."""
    
    model_config = ConfigDict(validate_assignment=True)
    
    provider: EmbeddingProvider = Field(..., description="Embedding provider type")
    model_name: str = Field(..., description="Model name or identifier")
    
    # Model settings
    embedding_dimension: Optional[int] = Field(None, ge=1, le=4096, description="Embedding dimension")
    max_sequence_length: Optional[int] = Field(None, ge=1, description="Maximum sequence length")
    
    # Performance settings
    batch_size: int = Field(default=32, ge=1, le=256, description="Batch size for embedding generation")
    max_concurrent: int = Field(default=4, ge=1, le=32, description="Maximum concurrent requests")
    
    # Cache settings
    cache_embeddings: bool = Field(default=True, description="Enable embedding caching")
    cache_size: int = Field(default=10000, ge=100, description="Number of embeddings to cache")
    
    # API settings (for cloud providers)
    api_key: Optional[str] = Field(None, description="API key for cloud providers")
    api_base_url: Optional[str] = Field(None, description="Custom API base URL")
    request_timeout: float = Field(default=30.0, ge=1.0, description="Request timeout in seconds")
    
    # Provider-specific settings
    provider_settings: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific configuration")


class ConsolidationConfiguration(BaseModel):
    """Configuration for memory consolidation."""
    
    model_config = ConfigDict(validate_assignment=True)
    
    # Consolidation scheduling
    enabled: bool = Field(default=True, description="Enable automatic consolidation")
    interval_seconds: int = Field(default=3600, ge=60, description="Consolidation interval in seconds")
    max_duration_seconds: int = Field(default=1800, ge=60, description="Maximum consolidation duration")
    
    # Consolidation thresholds
    similarity_threshold: float = Field(default=0.8, ge=0.0, le=1.0, description="Similarity threshold for merging")
    importance_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum importance to retain")
    age_threshold_days: float = Field(default=30.0, ge=0.1, description="Age threshold for consolidation")
    
    # Performance settings
    batch_size: int = Field(default=500, ge=10, le=5000, description="Records to process per batch")
    max_concurrent: int = Field(default=2, ge=1, le=8, description="Maximum concurrent consolidation tasks")
    
    # Strategy settings
    merge_similar_records: bool = Field(default=True, description="Enable similar record merging")
    promote_important_records: bool = Field(default=True, description="Enable tier promotion based on importance")
    archive_old_records: bool = Field(default=True, description="Enable archiving of old records")
    
    # Advanced settings
    consolidation_rules: Dict[str, Any] = Field(default_factory=dict, description="Custom consolidation rules")


class ObservabilityConfiguration(BaseModel):
    """Configuration for observability and monitoring."""
    
    model_config = ConfigDict(validate_assignment=True)
    
    # Metrics collection
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")
    metrics_port: int = Field(default=8080, ge=1024, le=65535, description="Port for metrics endpoint")
    metrics_path: str = Field(default="/metrics", description="Path for metrics endpoint")
    
    # Tracing
    enable_tracing: bool = Field(default=True, description="Enable distributed tracing")
    trace_sampler: float = Field(default=0.1, ge=0.0, le=1.0, description="Trace sampling rate")
    jaeger_endpoint: Optional[str] = Field(None, description="Jaeger collector endpoint")
    
    # Logging configuration
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    log_format: str = Field(default="json", description="Log format (json or text)")
    log_file: Optional[Path] = Field(None, description="Log file path")
    
    # Health checks
    enable_health_checks: bool = Field(default=True, description="Enable health check endpoints")
    health_check_interval: int = Field(default=30, ge=5, description="Health check interval in seconds")
    
    # Performance monitoring
    enable_profiling: bool = Field(default=False, description="Enable performance profiling")
    profile_duration: int = Field(default=60, ge=10, description="Profiling duration in seconds")


class SecurityConfiguration(BaseModel):
    """Configuration for security settings."""
    
    model_config = ConfigDict(validate_assignment=True)
    
    # Authentication
    enable_auth: bool = Field(default=True, description="Enable authentication")
    auth_provider: str = Field(default="internal", description="Authentication provider")
    jwt_secret: Optional[str] = Field(None, description="JWT signing secret")
    token_expiry_hours: int = Field(default=24, ge=1, description="Token expiry in hours")
    
    # Authorization
    enable_rbac: bool = Field(default=True, description="Enable role-based access control")
    admin_users: List[str] = Field(default_factory=list, description="List of admin users")
    
    # Encryption
    encrypt_at_rest: bool = Field(default=True, description="Enable encryption at rest")
    encryption_key: Optional[str] = Field(None, description="Encryption key")
    
    # Network security
    allowed_origins: List[str] = Field(default_factory=lambda: ["*"], description="Allowed CORS origins")
    rate_limit_per_hour: int = Field(default=1000, ge=1, description="Rate limit per hour per user")
    
    # Audit logging
    enable_audit_log: bool = Field(default=True, description="Enable audit logging")
    audit_log_retention_days: int = Field(default=90, ge=1, description="Audit log retention in days")


class SmrtiConfig(BaseSettings):
    """Main Smrti system configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SMRTI_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        validate_assignment=True,
        extra="ignore"
    )
    
    # System settings
    system_name: str = Field(default="smrti", description="System name")
    version: str = Field(default="0.1.0", description="System version")
    environment: str = Field(default="development", description="Environment (development/testing/production)")
    
    # Memory tier configurations
    tiers: Dict[TierType, TierConfiguration] = Field(
        default_factory=dict,
        description="Memory tier configurations"
    )
    
    # Embedding configuration
    embedding: EmbeddingConfiguration = Field(
        ...,
        description="Embedding provider configuration"
    )
    
    # Consolidation configuration
    consolidation: ConsolidationConfiguration = Field(
        default_factory=ConsolidationConfiguration,
        description="Memory consolidation configuration"
    )
    
    # Observability configuration
    observability: ObservabilityConfiguration = Field(
        default_factory=ObservabilityConfiguration,
        description="Observability and monitoring configuration"
    )
    
    # Security configuration
    security: SecurityConfiguration = Field(
        default_factory=SecurityConfiguration,
        description="Security configuration"
    )
    
    # Global system settings
    max_memory_mb: Optional[float] = Field(None, ge=100.0, description="Maximum system memory in MB")
    max_concurrent_operations: int = Field(default=10, ge=1, le=100, description="Maximum concurrent operations")
    graceful_shutdown_timeout: int = Field(default=30, ge=5, description="Graceful shutdown timeout in seconds")
    
    # Feature flags
    enable_hot_reload: bool = Field(default=True, description="Enable hot configuration reloading")
    enable_experimental_features: bool = Field(default=False, description="Enable experimental features")
    
    @model_validator(mode='after')
    def validate_config(self) -> 'SmrtiConfig':
        """Validate the complete configuration."""
        
        # Ensure at least one tier is configured
        if not self.tiers:
            raise ValueError("At least one memory tier must be configured")
        
        # Validate tier adapter types
        tier_adapters = {tier_type.value: tier_config.adapter.type for tier_type, tier_config in self.tiers.items()}
        
        # Working memory should use fast storage (Redis recommended)
        if TierType.WORKING in self.tiers:
            working_adapter = self.tiers[TierType.WORKING].adapter.type
            if working_adapter not in [AdapterType.REDIS]:
                print(f"Warning: {working_adapter} may not be optimal for working memory (Redis recommended)")
        
        # Long-term memory should use vector storage
        if TierType.LONG_TERM in self.tiers:
            long_term_adapter = self.tiers[TierType.LONG_TERM].adapter.type
            if long_term_adapter not in [AdapterType.CHROMA]:
                print(f"Warning: {long_term_adapter} may not be optimal for long-term memory (ChromaDB recommended)")
        
        return self
    
    @classmethod
    def create_default_config(cls) -> 'SmrtiConfig':
        """Create a default configuration for development."""
        
        # Default embedding configuration
        embedding_config = EmbeddingConfiguration(
            provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # Default tier configurations
        tiers = {
            TierType.WORKING: TierConfiguration(
                tier_type=TierType.WORKING,
                adapter=AdapterConfiguration(
                    type=AdapterType.REDIS,
                    host="localhost",
                    port=6379,
                    database="0"
                ),
                ttl_seconds=3600,  # 1 hour
                max_records=1000
            ),
            TierType.LONG_TERM: TierConfiguration(
                tier_type=TierType.LONG_TERM,
                adapter=AdapterConfiguration(
                    type=AdapterType.CHROMA,
                    adapter_settings={
                        "persist_directory": "./chroma_data",
                        "collection_name": "smrti_longterm"
                    }
                ),
                max_records=100000
            )
        }
        
        return cls(
            embedding=embedding_config,
            tiers=tiers
        )


# Configuration loading functions
def load_config_from_env() -> SmrtiConfig:
    """Load configuration from environment variables."""
    return SmrtiConfig()


def load_config_from_file(config_path: Union[str, Path]) -> SmrtiConfig:
    """Load configuration from a file (JSON/YAML)."""
    import json
    
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        if config_path.suffix.lower() == '.json':
            config_data = json.load(f)
        elif config_path.suffix.lower() in ['.yaml', '.yml']:
            try:
                import yaml
                config_data = yaml.safe_load(f)
            except ImportError:
                raise ImportError("PyYAML is required for YAML configuration files")
        else:
            raise ValueError(f"Unsupported configuration file format: {config_path.suffix}")
    
    return SmrtiConfig.model_validate(config_data)


def validate_config(config: SmrtiConfig) -> tuple[bool, List[str]]:
    """Validate configuration and return validation results.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    try:
        # Pydantic validation
        config.model_validate(config.model_dump())
        
        # Additional custom validations
        
        # Check for required environment-specific settings
        if config.environment == "production":
            if not config.security.jwt_secret:
                errors.append("JWT secret is required in production")
            
            if not config.security.encryption_key:
                errors.append("Encryption key is required in production")
            
            if config.observability.log_level == LogLevel.DEBUG:
                errors.append("DEBUG log level is not recommended in production")
        
        # Check tier compatibility
        for tier_type, tier_config in config.tiers.items():
            adapter_type = tier_config.adapter.type
            
            # Semantic memory should use graph databases
            if tier_type == TierType.SEMANTIC and adapter_type != AdapterType.NEO4J:
                errors.append(f"Semantic memory tier should use Neo4j, not {adapter_type}")
            
            # Episodic memory should use relational databases
            if tier_type == TierType.EPISODIC and adapter_type != AdapterType.POSTGRESQL:
                errors.append(f"Episodic memory tier should use PostgreSQL, not {adapter_type}")
        
        return len(errors) == 0, errors
        
    except Exception as e:
        errors.append(f"Configuration validation error: {str(e)}")
        return False, errors