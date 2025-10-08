"""Configuration management using Pydantic Settings."""

from typing import Literal
import os
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables.
    For production, set required values explicitly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=4, description="Number of worker processes")
    log_level: str = Field(default="INFO", description="Logging level")

    # API Configuration
    api_version: str = Field(
        default="2.0.0",
        description="API version",
    )
    api_keys: str = Field(
        default="dev-key-123",
        description="Comma-separated list of valid API keys",
    )
    cors_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins",
    )

    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_working_ttl: int = Field(
        default=300,
        description="TTL for WORKING memory in seconds (5 minutes)",
    )
    redis_short_term_ttl: int = Field(
        default=3600,
        description="TTL for SHORT_TERM memory in seconds (1 hour)",
    )
    redis_max_connections: int = Field(
        default=50,
        description="Maximum Redis connection pool size",
    )

    # Qdrant Configuration
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL",
    )
    qdrant_host: str = Field(
        default="localhost",
        description="Qdrant server host",
    )
    qdrant_port: int = Field(
        default=6333,
        description="Qdrant server port",
    )
    qdrant_collection_prefix: str = Field(
        default="smrti_",
        description="Prefix for Qdrant collection names",
    )
    qdrant_vector_size: int = Field(
        default=384,
        description="Embedding vector dimension (must match embedding model)",
    )

    # PostgreSQL Configuration
    postgres_url: str = Field(
        default="postgresql://smrti:smrti@localhost:5432/smrti",
        description="PostgreSQL connection URL (asyncpg format)",
    )
    postgres_host: str = Field(
        default="localhost",
        description="PostgreSQL server host",
    )
    postgres_port: int = Field(
        default=5432,
        description="PostgreSQL server port",
    )
    postgres_database: str = Field(
        default="smrti",
        description="PostgreSQL database name",
    )
    postgres_user: str = Field(
        default="smrti",
        description="PostgreSQL username",
    )
    postgres_password: str = Field(
        default="smrti",
        description="PostgreSQL password",
    )
    postgres_min_pool_size: int = Field(
        default=5,
        description="Minimum PostgreSQL connection pool size",
    )
    postgres_max_pool_size: int = Field(
        default=20,
        description="Maximum PostgreSQL connection pool size",
    )

    # Embedding Configuration
    embedding_provider: Literal["local", "api"] = Field(
        default="local",
        description="Embedding provider type",
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Embedding model name or path",
    )
    embedding_api_url: str = Field(
        default="",
        description="API URL for external embedding service",
    )
    embedding_api_key: str = Field(
        default="",
        description="API key for external embedding service",
    )
    embedding_cache_size: int = Field(
        default=1000,
        description="LRU cache size for embeddings",
    )
    embedding_batch_size: int = Field(
        default=32,
        description="Batch size for embedding generation",
    )

    # Validation Configuration
    max_text_length: int = Field(
        default=50000,
        description="Maximum text length in characters",
    )
    max_metadata_size: int = Field(
        default=10240,
        description="Maximum metadata JSON size in bytes",
    )

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Validate Redis URL format."""
        if not v.startswith("redis://"):
            raise ValueError("redis_url must start with 'redis://'")
        return v

    @field_validator("qdrant_url")
    @classmethod
    def validate_qdrant_url(cls, v: str) -> str:
        """Validate Qdrant URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("qdrant_url must start with 'http://' or 'https://'")
        return v

    @field_validator("postgres_url")
    @classmethod
    def validate_postgres_url(cls, v: str) -> str:
        """Validate PostgreSQL URL format."""
        if not v.startswith("postgresql://"):
            raise ValueError("postgres_url must start with 'postgresql://'")
        return v

    def get_api_keys(self) -> list[str]:
        """Parse comma-separated API keys into a list."""
        return [key.strip() for key in self.api_keys.split(",") if key.strip()]

    def get_cors_origins(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get global settings instance (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings()
        # Prefer central SMRTI_* variables if present (shared infra)
        redis_url_env = os.environ.get("SMRTI_REDIS_URL")
        if redis_url_env:
            _settings.redis_url = redis_url_env

        pg_dsn_env = os.environ.get("SMRTI_DATABASE_URL")
        if pg_dsn_env:
            _settings.postgres_url = pg_dsn_env
            # Attempt to parse discrete parts (optional)
            try:
                parsed = urlparse(pg_dsn_env)
                if parsed.hostname:
                    _settings.postgres_host = parsed.hostname
                if parsed.port:
                    _settings.postgres_port = parsed.port  # type: ignore[assignment]
                if parsed.path and len(parsed.path) > 1:
                    _settings.postgres_database = parsed.path.lstrip("/")
                if parsed.username:
                    _settings.postgres_user = parsed.username
                if parsed.password:
                    _settings.postgres_password = parsed.password
            except Exception:
                # Non-fatal; pool creation will use DSN directly
                pass

        qdrant_url_env = os.environ.get("SMRTI_QDRANT_URL")
        if qdrant_url_env:
            _settings.qdrant_url = qdrant_url_env
            # Optionally parse host/port for compatibility
            try:
                q = urlparse(qdrant_url_env)
                if q.hostname:
                    _settings.qdrant_host = q.hostname
                if q.port:
                    _settings.qdrant_port = q.port  # type: ignore[assignment]
            except Exception:
                pass
    return _settings
