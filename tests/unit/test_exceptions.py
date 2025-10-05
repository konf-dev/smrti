"""Unit tests for exceptions."""

import pytest

from smrti.core.exceptions import (
    AuthenticationError,
    EmbeddingError,
    SmrtiError,
    StorageError,
    ValidationError,
)


@pytest.mark.unit
class TestExceptions:
    """Test exception hierarchy."""

    def test_smrti_error_is_base(self) -> None:
        """Test SmrtiError is base exception."""
        error = SmrtiError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_validation_error(self) -> None:
        """Test ValidationError inherits from SmrtiError."""
        error = ValidationError("Invalid input")
        assert isinstance(error, SmrtiError)
        assert isinstance(error, Exception)

    def test_storage_error(self) -> None:
        """Test StorageError inherits from SmrtiError."""
        error = StorageError("Database failed")
        assert isinstance(error, SmrtiError)

    def test_embedding_error(self) -> None:
        """Test EmbeddingError inherits from SmrtiError."""
        error = EmbeddingError("Embedding failed")
        assert isinstance(error, SmrtiError)

    def test_authentication_error(self) -> None:
        """Test AuthenticationError inherits from SmrtiError."""
        error = AuthenticationError("Invalid API key")
        assert isinstance(error, SmrtiError)

    def test_exception_with_chaining(self) -> None:
        """Test exception chaining."""
        original = ValueError("Original error")
        try:
            raise StorageError("Storage failed") from original
        except StorageError as e:
            assert e.__cause__ == original
            assert "Storage failed" in str(e)
