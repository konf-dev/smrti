"""
Smrti - Intelligent Multi-Tier Memory System for AI Applications

A production-ready memory system providing five tiers of memory storage
with automatic consolidation, semantic search, and context assembly.
"""

__version__ = "0.1.0"

# Core data models - Always available
from .schemas.models import (
    RecordEnvelope,
    MemoryQuery,
    TextContent,
    MemoryRecord
)

__all__ = [
    # Version
    "__version__",
    
    # Data models
    "RecordEnvelope",
    "MemoryQuery",
    "TextContent",
    "MemoryRecord"
]