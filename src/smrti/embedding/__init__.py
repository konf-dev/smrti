"""Embedding service for generating vector representations of text."""

from smrti.embedding.protocol import EmbeddingProvider
from smrti.embedding.local import LocalEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "LocalEmbeddingProvider",
]
