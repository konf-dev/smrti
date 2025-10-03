"""
smrti/query/__init__.py - Advanced Query Interface

Comprehensive query system with semantic search, temporal filtering,
importance ranking, and natural language processing capabilities.
"""

from .engine import (
    QueryEngine,
    QueryResult,
    QueryContext,
    QueryStats
)

from .semantic import (
    SemanticSearchEngine,
    SemanticResult,
    EmbeddingProvider,
    TFIDFEmbeddingProvider
)

from .temporal import (
    TemporalFilter,
    TemporalQueryParser,
    TimeRange,
    TemporalOperator
)

from .filters import (
    BaseFilter,
    ImportanceFilter,
    ComplexityFilter,
    AccessFrequencyFilter,
    TierFilter,
    LabelFilter,
    CompositeFilter,
    ConditionFilter,
    FilterRegistry,
    FilterCondition,
    FilterOperator,
    ComparisonOperator
)

from .ranking import (
    BaseRanker,
    RelevanceRanker,
    ImportanceRanker,
    RecencyRanker,
    AccessFrequencyRanker,
    CompositeRanker,
    RankingEngine,
    RankingScore,
    RankedItem,
    RankingMethod,
    SortOrder
)

from .parser import (
    QueryParser,
    NaturalLanguageParser,
    StructuredQueryParser,
    QueryAST,
    QueryType,
    QueryPattern
)

__all__ = [
    # Core engine
    'QueryEngine',
    'QueryResult', 
    'QueryContext',
    'QueryStats',
    
    # Semantic search
    'SemanticSearchEngine',
    'SemanticResult',
    'EmbeddingProvider',
    'TFIDFEmbeddingProvider',
    
    # Temporal filtering
    'TemporalFilter',
    'TemporalQueryParser',
    'TimeRange',
    'TemporalOperator',
    
    # Filtering system
    'BaseFilter',
    'ImportanceFilter',
    'ComplexityFilter',
    'AccessFrequencyFilter',
    'TierFilter',
    'LabelFilter',
    'CompositeFilter',
    'ConditionFilter',
    'FilterRegistry',
    'FilterCondition',
    'FilterOperator',
    'ComparisonOperator',
    
    # Ranking system
    'BaseRanker',
    'RelevanceRanker',
    'ImportanceRanker',
    'RecencyRanker',
    'AccessFrequencyRanker',
    'CompositeRanker',
    'RankingEngine',
    'RankingScore',
    'RankedItem',
    'RankingMethod',
    'SortOrder',
    
    # Query parsing
    'QueryParser',
    'NaturalLanguageParser', 
    'StructuredQueryParser',
    'QueryAST',
    'QueryType',
    'QueryPattern',
]

from .engine import (
    QueryEngine,
    QueryResult,
    QueryContext,
    QueryStats
)

from .semantic import (
    SemanticSearchEngine,
    SemanticQuery,
    SemanticResult,
    EmbeddingModel,
    SimilarityMetric
)

from .temporal import (
    TemporalFilter,
    TemporalQuery,
    TimeRange,
    TemporalOperator,
    RelativeTime
)

from .filters import (
    ImportanceFilter,
    ComplexityFilter,
    AccessFrequencyFilter,
    TierFilter,
    LabelFilter,
    CompositeFilter,
    FilterOperator
)

from .ranking import (
    RankingEngine,
    RankingStrategy,
    ImportanceRanker,
    RelevanceRanker,
    RecencyRanker,
    CompositeRanker,
    RankingWeight
)

from .parser import (
    QueryParser,
    QueryAST,
    QueryExpression,
    BooleanOperator,
    ComparisonOperator,
    ParseError
)

__all__ = [
    # Core Engine
    'QueryEngine',
    'QueryResult',
    'QueryContext',
    'QueryStats',
    
    # Semantic Search
    'SemanticSearchEngine',
    'SemanticQuery',
    'SemanticResult',
    'EmbeddingModel',
    'SimilarityMetric',
    
    # Temporal Filtering
    'TemporalFilter',
    'TemporalQuery',
    'TimeRange',
    'TemporalOperator',
    'RelativeTime',
    
    # Filtering System
    'ImportanceFilter',
    'ComplexityFilter',
    'AccessFrequencyFilter',
    'TierFilter',
    'LabelFilter',
    'CompositeFilter',
    'FilterOperator',
    
    # Ranking System
    'RankingEngine',
    'RankingStrategy',
    'ImportanceRanker',
    'RelevanceRanker',
    'RecencyRanker',
    'CompositeRanker',
    'RankingWeight',
    
    # Query Parser
    'QueryParser',
    'QueryAST',
    'QueryExpression',
    'BooleanOperator',
    'ComparisonOperator',
    'ParseError'
]