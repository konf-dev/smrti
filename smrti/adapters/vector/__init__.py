"""
smrti/adapters/vector/__init__.py - Vector store adapters

Collection of vector database adapters for semantic similarity search
and high-dimensional vector operations.
"""

from .chromadb import ChromaDBAdapter

__all__ = [
    "ChromaDBAdapter",
]