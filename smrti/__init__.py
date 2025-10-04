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

# Main API classes
from .api import (
    Smrti,
    SmrtiConfig,
    SmrtiSession,
    create_smrti_system
)

# Retrieval engine components
from .core.retrieval_engine import (
    QueryStrategy,
    ResultMergeStrategy,
    RetrievalConfig
)

# Context assembly components
from .core.context_assembly import (
    ContextAssemblyConfig,
    ScoredRecord
)

# Consolidation components
from .core.consolidation import (
    ConsolidationConfig
)

__all__ = [
    # Version
    "__version__",
    
    # Data models
    "RecordEnvelope",
    "MemoryQuery",
    "TextContent",
    "MemoryRecord",
    
    # Main API
    "Smrti",
    "SmrtiConfig",
    "SmrtiSession",
    "create_smrti_system",
    
    # Retrieval
    "QueryStrategy",
    "ResultMergeStrategy",
    "RetrievalConfig",
    
    # Context Assembly
    "ContextAssemblyConfig",
    "ScoredRecord",
    
    # Consolidation
    "ConsolidationConfig"
]