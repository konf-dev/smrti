"""
smrti/consolidation/__init__.py - Memory consolidation system exports

Provides memory consolidation capabilities including similarity-based merging,
importance scoring, tier promotion, and automated cleanup.
"""

from .engine import (
    ConsolidationEngine,
    ConsolidationResult,
    ConsolidationTask
)

from .strategies import (
    ConsolidationStrategy,
    SimilarityMergeStrategy,
    ImportancePromotionStrategy,
    TemporalCleanupStrategy,
    HybridConsolidationStrategy
)

from .scheduler import (
    ConsolidationScheduler,
    ScheduleConfig,
    ConsolidationJob
)

__all__ = [
    # Core consolidation engine
    "ConsolidationEngine",
    "ConsolidationResult",
    "ConsolidationTask",
    
    # Consolidation strategies
    "ConsolidationStrategy",
    "SimilarityMergeStrategy", 
    "ImportancePromotionStrategy",
    "TemporalCleanupStrategy",
    "HybridConsolidationStrategy",
    
    # Scheduling and automation
    "ConsolidationScheduler",
    "ScheduleConfig",
    "ConsolidationJob"
]