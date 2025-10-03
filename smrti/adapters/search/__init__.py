"""
Search adapters for full-text search and structured queries.

This module provides search engine adapters for procedural memory storage
and advanced search capabilities used by the Smrti system.
"""

from .elasticsearch import ElasticsearchAdapter

__all__ = [
    "ElasticsearchAdapter"
]