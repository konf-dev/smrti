"""
smrti/query/parser.py - Natural Language Query Parser

Advanced query parsing with support for natural language expressions,
boolean logic, filters, and structured query construction.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import ast

from .filters import (
    FilterCondition, FilterOperator, ComparisonOperator,
    ImportanceFilter, ComplexityFilter, AccessFrequencyFilter,
    TierFilter, LabelFilter, CompositeFilter, ConditionFilter
)
from .temporal import TemporalFilter
from .ranking import RankingMethod


class QueryType(Enum):
    """Types of supported queries."""
    
    SEMANTIC = "semantic"          # Semantic similarity search
    KEYWORD = "keyword"            # Keyword/text matching
    TEMPORAL = "temporal"          # Time-based queries
    FILTERED = "filtered"          # Filtered queries
    RANKED = "ranked"              # Ranked queries
    COMPOSITE = "composite"        # Complex multi-part queries


@dataclass
class QueryAST:
    """Abstract Syntax Tree for parsed queries."""
    
    query_type: QueryType
    semantic_terms: List[str] = field(default_factory=list)
    keyword_terms: List[str] = field(default_factory=list)
    temporal_expressions: List[str] = field(default_factory=list)
    filters: List[Any] = field(default_factory=list)
    ranking_method: Optional[str] = None
    sort_order: Optional[str] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
    boolean_logic: str = "AND"  # AND, OR, NOT
    
    # Raw query components
    original_query: str = ""
    processed_query: str = ""
    
    # Confidence and metadata
    parse_confidence: float = 1.0
    parsing_errors: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class QueryPattern:
    """Represents a query pattern with regex and handler."""
    
    def __init__(self, name: str, pattern: str, handler: callable,
                 priority: int = 1, query_type: QueryType = QueryType.SEMANTIC):
        """Initialize query pattern.
        
        Args:
            name: Pattern name
            pattern: Regex pattern to match
            handler: Function to handle matched pattern
            priority: Pattern matching priority (higher = checked first)
            query_type: Default query type for this pattern
        """
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.handler = handler
        self.priority = priority
        self.query_type = query_type
    
    def matches(self, query: str) -> Optional[re.Match]:
        """Check if pattern matches query."""
        return self.pattern.search(query)


class NaturalLanguageParser:
    """Natural language query parser with pattern matching."""
    
    def __init__(self):
        """Initialize natural language parser."""
        self.patterns: List[QueryPattern] = []
        self._register_default_patterns()
        
        # Sort patterns by priority (higher priority first)
        self.patterns.sort(key=lambda p: p.priority, reverse=True)
    
    def _register_default_patterns(self) -> None:
        """Register default query patterns."""
        
        # Temporal patterns (high priority)
        self.patterns.extend([
            QueryPattern(
                "temporal_recent",
                r"\b(recent|latest|new|fresh)\s+(.+)",
                self._handle_recent_pattern,
                priority=8,
                query_type=QueryType.TEMPORAL
            ),
            QueryPattern(
                "temporal_since",
                r"\b(since|after|from)\s+(.+?)(?:\s+(?:find|show|get|search)|$)",
                self._handle_since_pattern,
                priority=8,
                query_type=QueryType.TEMPORAL
            ),
            QueryPattern(
                "temporal_before",
                r"\b(before|until|up\s+to)\s+(.+?)(?:\s+(?:find|show|get|search)|$)",
                self._handle_before_pattern,
                priority=8,
                query_type=QueryType.TEMPORAL
            ),
            QueryPattern(
                "temporal_between",
                r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:\s+(?:find|show|get|search)|$)",
                self._handle_between_pattern,
                priority=8,
                query_type=QueryType.TEMPORAL
            ),
        ])
        
        # Importance and ranking patterns
        self.patterns.extend([
            QueryPattern(
                "importance_high",
                r"\b(important|critical|urgent|high\s+priority)\s+(.+)",
                self._handle_high_importance_pattern,
                priority=7,
                query_type=QueryType.FILTERED
            ),
            QueryPattern(
                "most_relevant",
                r"\b(most\s+relevant|best\s+match|top\s+results?)\s+(.+)",
                self._handle_most_relevant_pattern,
                priority=7,
                query_type=QueryType.RANKED
            ),
            QueryPattern(
                "sort_by",
                r"\bsort\s+by\s+(importance|date|relevance|frequency)\s+(.+)",
                self._handle_sort_by_pattern,
                priority=6,
                query_type=QueryType.RANKED
            ),
        ])
        
        # Filter patterns
        self.patterns.extend([
            QueryPattern(
                "with_label",
                r"\bwith\s+(?:label|tag)\s+['\"]?([^'\"]+?)['\"]?\s+(.+)",
                self._handle_with_label_pattern,
                priority=6,
                query_type=QueryType.FILTERED
            ),
            QueryPattern(
                "in_tier",
                r"\bin\s+(hot|warm|cold|archived?)\s+(?:tier|memory)\s+(.+)",
                self._handle_in_tier_pattern,
                priority=6,
                query_type=QueryType.FILTERED
            ),
            QueryPattern(
                "longer_than",
                r"\blonger\s+than\s+(\d+)\s+(words?|characters?)\s+(.+)",
                self._handle_longer_than_pattern,
                priority=5,
                query_type=QueryType.FILTERED
            ),
        ])
        
        # Boolean logic patterns
        self.patterns.extend([
            QueryPattern(
                "and_query",
                r"\b(.+?)\s+and\s+(.+)",
                self._handle_and_pattern,
                priority=4,
                query_type=QueryType.COMPOSITE
            ),
            QueryPattern(
                "or_query",
                r"\b(.+?)\s+or\s+(.+)",
                self._handle_or_pattern,
                priority=4,
                query_type=QueryType.COMPOSITE
            ),
            QueryPattern(
                "not_query",
                r"\bnot\s+(.+)",
                self._handle_not_pattern,
                priority=4,
                query_type=QueryType.COMPOSITE
            ),
        ])
        
        # Limit and pagination patterns
        self.patterns.extend([
            QueryPattern(
                "limit_results",
                r"\b(?:(?:first|top|limit)\s+)?(\d+)\s+(.+?)(?:\s+(?:results?|items?|entries?))?$",
                self._handle_limit_pattern,
                priority=3,
                query_type=QueryType.SEMANTIC
            ),
            QueryPattern(
                "show_first",
                r"\bshow\s+(?:first\s+)?(\d+)\s+(.+)",
                self._handle_show_first_pattern,
                priority=3,
                query_type=QueryType.SEMANTIC
            ),
        ])
        
        # Question patterns
        self.patterns.extend([
            QueryPattern(
                "what_is",
                r"\bwhat\s+is\s+(.+?)\??",
                self._handle_what_is_pattern,
                priority=2,
                query_type=QueryType.SEMANTIC
            ),
            QueryPattern(
                "how_to",
                r"\bhow\s+to\s+(.+?)\??",
                self._handle_how_to_pattern,
                priority=2,
                query_type=QueryType.SEMANTIC
            ),
            QueryPattern(
                "where_is",
                r"\bwhere\s+(?:is|are|can\s+I\s+find)\s+(.+?)\??",
                self._handle_where_is_pattern,
                priority=2,
                query_type=QueryType.SEMANTIC
            ),
        ])
        
        # Default semantic pattern (lowest priority)
        self.patterns.append(
            QueryPattern(
                "semantic_search",
                r"(.+)",
                self._handle_semantic_pattern,
                priority=1,
                query_type=QueryType.SEMANTIC
            )
        )
    
    def parse(self, query: str) -> QueryAST:
        """Parse a natural language query into AST.
        
        Args:
            query: Natural language query string
            
        Returns:
            Parsed query AST
        """
        if not query or not query.strip():
            return QueryAST(
                query_type=QueryType.SEMANTIC,
                original_query=query,
                parse_confidence=0.0,
                parsing_errors=["Empty query"]
            )
        
        query = query.strip()
        ast_result = QueryAST(
            query_type=QueryType.SEMANTIC,
            original_query=query,
            processed_query=query
        )
        
        # Try to match patterns in priority order
        for pattern in self.patterns:
            match = pattern.matches(query)
            if match:
                try:
                    # Let the pattern handler modify the AST
                    pattern.handler(match, ast_result)
                    ast_result.query_type = pattern.query_type
                    break
                except Exception as e:
                    ast_result.parsing_errors.append(f"Pattern {pattern.name}: {str(e)}")
        
        # Set parse confidence based on errors and pattern matches
        if ast_result.parsing_errors:
            ast_result.parse_confidence = max(0.3, 1.0 - len(ast_result.parsing_errors) * 0.2)
        elif ast_result.query_type != QueryType.SEMANTIC or ast_result.filters or ast_result.temporal_expressions:
            ast_result.parse_confidence = 0.9
        else:
            ast_result.parse_confidence = 0.7  # Basic semantic search
        
        # Extract basic terms if none were found
        if not ast_result.semantic_terms and not ast_result.keyword_terms:
            ast_result.semantic_terms = self._extract_terms(query)
        
        return ast_result
    
    def _extract_terms(self, text: str) -> List[str]:
        """Extract meaningful terms from text."""
        # Remove common stop words and extract meaningful terms
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'among', 'throughout',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may',
            'might', 'must', 'shall', 'this', 'that', 'these', 'those'
        }
        
        # Extract words using regex
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filter meaningful terms
        terms = [word for word in words if len(word) > 2 and word not in stop_words]
        
        return terms
    
    # Pattern handlers
    
    def _handle_recent_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'recent/latest/new' patterns."""
        time_indicator = match.group(1).lower()
        search_terms = match.group(2)
        
        # Add temporal filter for recent items
        if time_indicator in ['recent', 'latest', 'new', 'fresh']:
            ast.temporal_expressions.append("last 7 days")  # Default to last week
        
        ast.semantic_terms = self._extract_terms(search_terms)
        ast.ranking_method = "recency"
    
    def _handle_since_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'since/after/from' temporal patterns."""
        time_expression = match.group(2)
        ast.temporal_expressions.append(f"since {time_expression}")
        ast.ranking_method = "recency"
    
    def _handle_before_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'before/until' temporal patterns."""
        time_expression = match.group(2)
        ast.temporal_expressions.append(f"before {time_expression}")
        ast.ranking_method = "recency"
    
    def _handle_between_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'between X and Y' temporal patterns."""
        start_time = match.group(1)
        end_time = match.group(2)
        ast.temporal_expressions.append(f"between {start_time} and {end_time}")
        ast.ranking_method = "recency"
    
    def _handle_high_importance_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle importance-based patterns."""
        search_terms = match.group(2)
        
        # Add importance filter
        importance_filter = ImportanceFilter(min_importance=0.7)
        ast.filters.append(importance_filter)
        
        ast.semantic_terms = self._extract_terms(search_terms)
        ast.ranking_method = "importance"
    
    def _handle_most_relevant_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'most relevant' patterns."""
        search_terms = match.group(2)
        ast.semantic_terms = self._extract_terms(search_terms)
        ast.ranking_method = "relevance"
        ast.limit = 10  # Default to top 10 for "best match"
    
    def _handle_sort_by_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'sort by' patterns."""
        sort_field = match.group(1).lower()
        search_terms = match.group(2)
        
        # Map sort fields to ranking methods
        sort_mapping = {
            'importance': 'importance',
            'date': 'recency',
            'relevance': 'relevance',
            'frequency': 'frequency'
        }
        
        ast.ranking_method = sort_mapping.get(sort_field, 'composite')
        ast.semantic_terms = self._extract_terms(search_terms)
    
    def _handle_with_label_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'with label' patterns."""
        label = match.group(1).strip()
        search_terms = match.group(2)
        
        # Add label filter
        label_filter = LabelFilter(required_labels=[label])
        ast.filters.append(label_filter)
        
        ast.semantic_terms = self._extract_terms(search_terms)
    
    def _handle_in_tier_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'in tier' patterns."""
        tier = match.group(1).lower()
        search_terms = match.group(2)
        
        # Add tier filter
        tier_filter = TierFilter(allowed_tiers=[tier])
        ast.filters.append(tier_filter)
        
        ast.semantic_terms = self._extract_terms(search_terms)
    
    def _handle_longer_than_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'longer than' patterns."""
        length = int(match.group(1))
        unit = match.group(2).lower()
        search_terms = match.group(3)
        
        # Add complexity filter based on unit
        metric = "words" if "word" in unit else "length"
        complexity_filter = ComplexityFilter(
            min_complexity=length,
            complexity_metric=metric
        )
        ast.filters.append(complexity_filter)
        
        ast.semantic_terms = self._extract_terms(search_terms)
    
    def _handle_and_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'AND' boolean logic."""
        term1 = match.group(1)
        term2 = match.group(2)
        
        ast.semantic_terms.extend(self._extract_terms(term1))
        ast.semantic_terms.extend(self._extract_terms(term2))
        ast.boolean_logic = "AND"
    
    def _handle_or_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'OR' boolean logic."""
        term1 = match.group(1)
        term2 = match.group(2)
        
        ast.semantic_terms.extend(self._extract_terms(term1))
        ast.semantic_terms.extend(self._extract_terms(term2))
        ast.boolean_logic = "OR"
    
    def _handle_not_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'NOT' boolean logic."""
        terms = match.group(1)
        ast.semantic_terms = self._extract_terms(terms)
        ast.boolean_logic = "NOT"
    
    def _handle_limit_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle result limit patterns."""
        limit = int(match.group(1))
        search_terms = match.group(2)
        
        ast.limit = limit
        ast.semantic_terms = self._extract_terms(search_terms)
    
    def _handle_show_first_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'show first N' patterns."""
        limit = int(match.group(1))
        search_terms = match.group(2)
        
        ast.limit = limit
        ast.semantic_terms = self._extract_terms(search_terms)
    
    def _handle_what_is_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'what is' question patterns."""
        subject = match.group(1)
        ast.semantic_terms = self._extract_terms(subject)
        ast.ranking_method = "relevance"
    
    def _handle_how_to_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'how to' question patterns."""
        action = match.group(1)
        ast.semantic_terms = ["how", "to"] + self._extract_terms(action)
        ast.ranking_method = "relevance"
    
    def _handle_where_is_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle 'where is' question patterns."""
        subject = match.group(1)
        ast.semantic_terms = ["where", "location"] + self._extract_terms(subject)
        ast.ranking_method = "relevance"
    
    def _handle_semantic_pattern(self, match: re.Match, ast: QueryAST) -> None:
        """Handle default semantic search pattern."""
        query_text = match.group(1)
        ast.semantic_terms = self._extract_terms(query_text)
        ast.processed_query = query_text


class StructuredQueryParser:
    """Parser for structured query syntax (SQL-like, JSON, etc.)."""
    
    def __init__(self):
        """Initialize structured query parser."""
        self.supported_formats = ['json', 'dict', 'sql-like']
    
    def parse(self, query: str) -> Optional[QueryAST]:
        """Parse a structured query string.
        
        Args:
            query: Structured query string
            
        Returns:
            Parsed query AST or None if not structured
        """
        query = query.strip()
        
        # Try JSON format
        if query.startswith('{') and query.endswith('}'):
            return self._parse_json_query(query)
        
        # Try Python dict format
        if query.startswith('{"') or query.startswith("{'"):
            return self._parse_dict_query(query)
        
        # Try SQL-like format
        if any(keyword in query.upper() for keyword in ['SELECT', 'FROM', 'WHERE', 'ORDER BY']):
            return self._parse_sql_like_query(query)
        
        return None
    
    def _parse_json_query(self, query: str) -> Optional[QueryAST]:
        """Parse JSON-formatted query."""
        try:
            import json
            query_dict = json.loads(query)
            return self._dict_to_ast(query_dict, query)
        except (json.JSONDecodeError, Exception):
            return None
    
    def _parse_dict_query(self, query: str) -> Optional[QueryAST]:
        """Parse Python dict-formatted query."""
        try:
            # Safely evaluate dict literal
            query_dict = ast.literal_eval(query)
            return self._dict_to_ast(query_dict, query)
        except (ValueError, SyntaxError, Exception):
            return None
    
    def _dict_to_ast(self, query_dict: dict, original: str) -> QueryAST:
        """Convert dictionary to QueryAST."""
        ast_result = QueryAST(
            query_type=QueryType.COMPOSITE,
            original_query=original
        )
        
        # Extract semantic terms
        if 'terms' in query_dict:
            ast_result.semantic_terms = query_dict['terms']
        elif 'semantic' in query_dict:
            ast_result.semantic_terms = query_dict['semantic']
        elif 'search' in query_dict:
            ast_result.semantic_terms = [query_dict['search']]
        
        # Extract filters
        if 'filters' in query_dict:
            ast_result.filters = self._parse_filter_dict(query_dict['filters'])
        
        # Extract temporal expressions
        if 'temporal' in query_dict:
            ast_result.temporal_expressions = [query_dict['temporal']]
        elif 'time' in query_dict:
            ast_result.temporal_expressions = [query_dict['time']]
        
        # Extract ranking method
        if 'ranking' in query_dict:
            ast_result.ranking_method = query_dict['ranking']
        elif 'sort' in query_dict:
            ast_result.ranking_method = query_dict['sort']
        
        # Extract limit and offset
        if 'limit' in query_dict:
            ast_result.limit = int(query_dict['limit'])
        if 'offset' in query_dict:
            ast_result.offset = int(query_dict['offset'])
        
        # Extract boolean logic
        if 'logic' in query_dict:
            ast_result.boolean_logic = query_dict['logic'].upper()
        
        return ast_result
    
    def _parse_filter_dict(self, filters_dict: dict) -> List[Any]:
        """Parse filters from dictionary format."""
        filters = []
        
        # Importance filter
        if 'importance' in filters_dict:
            imp_config = filters_dict['importance']
            if isinstance(imp_config, dict):
                filters.append(ImportanceFilter(
                    min_importance=imp_config.get('min'),
                    max_importance=imp_config.get('max')
                ))
            else:
                filters.append(ImportanceFilter(min_importance=float(imp_config)))
        
        # Label filter
        if 'labels' in filters_dict:
            label_config = filters_dict['labels']
            if isinstance(label_config, list):
                filters.append(LabelFilter(required_labels=label_config))
            else:
                filters.append(LabelFilter(required_labels=[label_config]))
        
        # Tier filter
        if 'tier' in filters_dict:
            tier_config = filters_dict['tier']
            if isinstance(tier_config, list):
                filters.append(TierFilter(allowed_tiers=tier_config))
            else:
                filters.append(TierFilter(allowed_tiers=[tier_config]))
        
        return filters
    
    def _parse_sql_like_query(self, query: str) -> Optional[QueryAST]:
        """Parse SQL-like query syntax."""
        # This is a simplified SQL-like parser
        # In a real implementation, you'd use a proper SQL parser
        
        ast_result = QueryAST(
            query_type=QueryType.COMPOSITE,
            original_query=query
        )
        
        # Extract WHERE conditions (very basic)
        where_match = re.search(r'\bWHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+LIMIT|$)', query, re.IGNORECASE)
        if where_match:
            where_clause = where_match.group(1)
            # Parse simple conditions
            ast_result.semantic_terms = self._extract_terms_from_where(where_clause)
        
        # Extract ORDER BY
        order_match = re.search(r'\bORDER\s+BY\s+(\w+)', query, re.IGNORECASE)
        if order_match:
            sort_field = order_match.group(1).lower()
            if sort_field in ['importance', 'recency', 'relevance']:
                ast_result.ranking_method = sort_field
        
        # Extract LIMIT
        limit_match = re.search(r'\bLIMIT\s+(\d+)', query, re.IGNORECASE)
        if limit_match:
            ast_result.limit = int(limit_match.group(1))
        
        return ast_result
    
    def _extract_terms_from_where(self, where_clause: str) -> List[str]:
        """Extract search terms from WHERE clause."""
        # Remove SQL operators and extract quoted strings
        terms = []
        
        # Find quoted strings
        quoted_strings = re.findall(r"['\"]([^'\"]+)['\"]", where_clause)
        terms.extend(quoted_strings)
        
        # Find unquoted words (excluding SQL keywords)
        sql_keywords = {'AND', 'OR', 'NOT', 'LIKE', 'IN', 'IS', 'NULL', 'TRUE', 'FALSE'}
        words = re.findall(r'\b\w+\b', where_clause)
        for word in words:
            if word.upper() not in sql_keywords and len(word) > 2:
                terms.append(word.lower())
        
        return terms


class QueryParser:
    """Main query parser that combines natural language and structured parsing."""
    
    def __init__(self):
        """Initialize main query parser."""
        self.natural_parser = NaturalLanguageParser()
        self.structured_parser = StructuredQueryParser()
        
        # Parser statistics
        self.parse_stats = {
            'total_queries': 0,
            'natural_language': 0,
            'structured': 0,
            'parse_errors': 0
        }
    
    def parse_query(self, query: str) -> QueryAST:
        """Parse any type of query (natural language or structured).
        
        Args:
            query: Query string to parse
            
        Returns:
            Parsed query AST
        """
        self.parse_stats['total_queries'] += 1
        
        if not query or not query.strip():
            self.parse_stats['parse_errors'] += 1
            return QueryAST(
                query_type=QueryType.SEMANTIC,
                original_query=query,
                parse_confidence=0.0,
                parsing_errors=["Empty query"]
            )
        
        # Try structured parsing first
        structured_result = self.structured_parser.parse(query)
        if structured_result:
            self.parse_stats['structured'] += 1
            structured_result.parse_confidence = 0.95  # High confidence for structured
            return structured_result
        
        # Fall back to natural language parsing
        self.parse_stats['natural_language'] += 1
        return self.natural_parser.parse(query)
    
    def get_parse_stats(self) -> Dict[str, Any]:
        """Get parsing statistics."""
        return self.parse_stats.copy()
    
    def add_custom_pattern(self, pattern: QueryPattern) -> None:
        """Add a custom query pattern.
        
        Args:
            pattern: Custom query pattern to add
        """
        self.natural_parser.patterns.append(pattern)
        
        # Re-sort patterns by priority
        self.natural_parser.patterns.sort(key=lambda p: p.priority, reverse=True)
    
    def suggest_query_improvements(self, query: str, ast: QueryAST) -> List[str]:
        """Suggest improvements for a query.
        
        Args:
            query: Original query string
            ast: Parsed query AST
            
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        # Low confidence suggestions
        if ast.parse_confidence < 0.5:
            suggestions.append("Try using more specific terms or structured query syntax")
        
        # No filters or ranking suggestions
        if not ast.filters and not ast.ranking_method and len(ast.semantic_terms) > 3:
            suggestions.append("Consider adding filters to narrow your search (e.g., 'important', 'recent')")
        
        # Temporal suggestions
        if not ast.temporal_expressions and any(word in query.lower() for word in ['when', 'time', 'date']):
            suggestions.append("Add specific time expressions (e.g., 'since yesterday', 'last week')")
        
        # Ranking suggestions
        if not ast.ranking_method and len(ast.semantic_terms) > 1:
            suggestions.append("Specify sorting preference (e.g., 'most relevant', 'sort by importance')")
        
        return suggestions