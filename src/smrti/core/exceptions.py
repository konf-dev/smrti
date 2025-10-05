"""Exception hierarchy for Smrti."""


class SmrtiError(Exception):
    """Base exception for all Smrti errors."""

    pass


class ValidationError(SmrtiError):
    """Invalid input data."""

    pass


class StorageError(SmrtiError):
    """Database operation failed."""

    pass


class EmbeddingError(SmrtiError):
    """Embedding generation failed."""

    pass


class AuthenticationError(SmrtiError):
    """Invalid/missing API key."""

    pass
