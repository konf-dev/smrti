"""
smrti/adapters/embedding/__init__.py - Embedding provider adapters

Collection of embedding providers for generating dense vector representations
of text content.
"""

from .sentence_transformers import SentenceTransformersProvider
from .openai import OpenAIEmbeddingProvider

__all__ = [
    "SentenceTransformersProvider",
    "OpenAIEmbeddingProvider",
]