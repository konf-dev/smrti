"""
Database adapters for relational and structured storage.

This module provides database adapters for various relational and structured
storage systems used by different memory tiers in the Smrti system.
"""

from .postgresql import PostgreSQLAdapter

__all__ = [
    "PostgreSQLAdapter"
]