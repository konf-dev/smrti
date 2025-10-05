"""Unit tests for core configuration."""

import pytest

from smrti.core.config import Settings
from smrti.core.types import MemoryType


@pytest.mark.unit
class TestMemoryType:
    """Test MemoryType enum."""

    def test_all_memory_types_defined(self) -> None:
        """Verify all 5 memory types are defined."""
        assert len(MemoryType) == 5
        assert MemoryType.WORKING.value == "WORKING"
        assert MemoryType.SHORT_TERM.value == "SHORT_TERM"
        assert MemoryType.LONG_TERM.value == "LONG_TERM"
        assert MemoryType.EPISODIC.value == "EPISODIC"
        assert MemoryType.SEMANTIC.value == "SEMANTIC"

    def test_memory_type_from_string(self) -> None:
        """Test creating MemoryType from string."""
        assert MemoryType("WORKING") == MemoryType.WORKING
        assert MemoryType("LONG_TERM") == MemoryType.LONG_TERM

    def test_invalid_memory_type(self) -> None:
        """Test invalid memory type raises ValueError."""
        with pytest.raises(ValueError):
            MemoryType("INVALID")


@pytest.mark.unit
class TestSettings:
    """Test configuration settings."""

    def test_default_settings(self) -> None:
        """Test default settings are valid."""
        settings = Settings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.redis_working_ttl == 300
        assert settings.redis_short_term_ttl == 3600

    def test_redis_url_validation(self) -> None:
        """Test Redis URL validation."""
        with pytest.raises(ValueError, match="redis_url must start with 'redis://'"):
            Settings(redis_url="http://localhost:6379")

    def test_qdrant_url_validation(self) -> None:
        """Test Qdrant URL validation."""
        with pytest.raises(ValueError, match="qdrant_url must start with"):
            Settings(qdrant_url="redis://localhost:6333")

    def test_postgres_url_validation(self) -> None:
        """Test PostgreSQL URL validation."""
        with pytest.raises(ValueError, match="postgres_url must start with 'postgresql://'"):
            Settings(postgres_url="mysql://localhost:5432")

    def test_api_keys_parsing(self) -> None:
        """Test API key parsing."""
        settings = Settings(api_keys="key1,key2,key3")
        keys = settings.get_api_keys()
        assert len(keys) == 3
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" in keys

    def test_cors_origins_parsing(self) -> None:
        """Test CORS origins parsing."""
        settings = Settings(cors_origins="http://localhost:3000,https://app.example.com")
        origins = settings.get_cors_origins()
        assert len(origins) == 2
        assert "http://localhost:3000" in origins
        assert "https://app.example.com" in origins

    def test_cors_wildcard(self) -> None:
        """Test CORS wildcard origin."""
        settings = Settings(cors_origins="*")
        origins = settings.get_cors_origins()
        assert origins == ["*"]
