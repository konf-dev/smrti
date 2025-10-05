"""Core type definitions for Smrti."""

from enum import Enum


class MemoryType(str, Enum):
    """
    Types of memory storage tiers.
    
    Each type has different storage characteristics:
    - WORKING: Ultra-short term (5 min), in-memory, current context
    - SHORT_TERM: Short term (1 hour), in-memory, session summary
    - LONG_TERM: Persistent, vector-indexed, semantic facts
    - EPISODIC: Persistent, time-series, event timeline
    - SEMANTIC: Persistent, graph-structured, knowledge facts
    """

    WORKING = "WORKING"
    SHORT_TERM = "SHORT_TERM"
    LONG_TERM = "LONG_TERM"
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
