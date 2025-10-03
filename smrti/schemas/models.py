"""
smrti/schemas/models.py - Core data models with validation

This module contains all Pydantic models for Smrti's data structures,
implementing the complete specifications from PRD Appendix J.
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# Type aliases for clarity
TierType = Literal["working", "short_term", "long_term", "episodic", "semantic"]
ContentType = Literal["TEXT", "FACT", "EVENT", "SUMMARY", "EMBED_REF", "MULTIMODAL_PLACEHOLDER"]
RoleType = Literal["user", "assistant", "system", "tool"]
LogLevel = Literal["DEBUG", "INFO", "WARN", "ERROR"]


class RecordEnvelope(BaseModel):
    """
    Universal memory record wrapper. All tiers use this structure.
    
    This is the core data structure that unifies all memory records across
    tiers, providing consistent metadata, lifecycle tracking, and provenance.
    """
    
    id: UUID = Field(default_factory=uuid4, description="Unique record identifier")
    tenant: str = Field(
        ..., 
        min_length=1, 
        max_length=128, 
        description="Tenant namespace for isolation"
    )
    namespace: str = Field(
        ..., 
        min_length=1, 
        max_length=128, 
        description="Sub-namespace (e.g., 'support', 'sales')"
    )
    user_id: str | None = Field(
        None, 
        max_length=256, 
        description="User principal; None for system/global memory"
    )
    tier: TierType = Field(..., description="Memory tier classification")
    content_type: ContentType = Field(..., description="Payload semantic type")
    payload: dict[str, Any] | str = Field(
        ..., 
        description="Actual content (text string or structured dict)"
    )
    
    # Vector and similarity fields
    embedding: list[float] | None = Field(
        None, 
        description="Dense vector representation (if applicable)"
    )
    semantic_hash: str | None = Field(
        None, 
        max_length=64, 
        description="LSH/SimHash for deduplication"
    )
    
    # Temporal fields
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relevance and importance scoring
    relevance_score: float = Field(
        1.0, 
        ge=0.0, 
        le=1.0, 
        description="Dynamic decay-adjusted relevance"
    )
    importance_score: float = Field(
        0.0, 
        ge=0.0, 
        le=1.0, 
        description="Static priority weight"
    )
    
    # Access tracking (for reinforcement learning)
    access_count: int = Field(0, ge=0, description="Retrieval frequency (reinforcement signal)")
    last_accessed_at: datetime | None = None
    
    # Lifecycle management
    decay_params: dict[str, Any] = Field(
        default_factory=dict, 
        description="Tier-specific decay config override"
    )
    
    # Provenance and lineage
    lineage: list[str] = Field(
        default_factory=list, 
        description="Parent record IDs (for summaries/consolidations)"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, 
        description="Origin metadata (agent, tool, etc.)"
    )
    
    # Data integrity
    integrity: dict[str, Any] = Field(
        default_factory=dict, 
        description="Checksums, version, signatures"
    )
    
    # Extension metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict, 
        description="Arbitrary key-value extensions"
    )
    
    # Archival flag
    archived: bool = Field(False, description="Flagged for cold storage")

    @field_validator("tenant", "namespace")
    @classmethod
    def validate_namespace_chars(cls, v: str) -> str:
        """Enforce safe namespace characters (alphanumeric + underscore + hyphen)."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(f"Invalid namespace format: {v}")
        return v

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimensions(cls, v: list[float] | None) -> list[float] | None:
        """Ensure embedding vector has supported dimensions if present."""
        if v is not None:
            allowed_dims = [384, 512, 768, 1024, 1536, 3072]
            if len(v) not in allowed_dims:
                raise ValueError(
                    f"Unsupported embedding dimension: {len(v)}. "
                    f"Allowed: {allowed_dims}"
                )
        return v

    @field_validator("semantic_hash")
    @classmethod
    def validate_semantic_hash(cls, v: str | None) -> str | None:
        """Validate semantic hash format (hexadecimal)."""
        if v is not None and not re.match(r'^[a-f0-9]+$', v):
            raise ValueError("Semantic hash must be hexadecimal")
        return v

    def compute_semantic_hash(self) -> str:
        """
        Compute semantic hash for deduplication.
        
        Uses SHA-256 hash of normalized payload content.
        """
        if isinstance(self.payload, str):
            content = self.payload.strip().lower()
        else:
            # For dict payload, create normalized string representation
            import json
            content = json.dumps(self.payload, sort_keys=True)
        
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def update_relevance(self, decay_factor: float = 0.95) -> None:
        """Update relevance score with decay and access reinforcement."""
        age_penalty = decay_factor ** (
            (datetime.utcnow() - self.created_at).total_seconds() / 86400
        )
        access_boost = min(1.0, 1.0 + 0.1 * self.access_count)
        
        self.relevance_score = min(1.0, self.importance_score * age_penalty * access_boost)
        self.updated_at = datetime.utcnow()

    class Config:
        json_schema_extra = {
            "example": {
                "id": "01234567-89ab-cdef-0123-456789abcdef",
                "tenant": "acme_corp",
                "namespace": "customer_support", 
                "user_id": "user_12345",
                "tier": "long_term",
                "content_type": "SUMMARY",
                "payload": {
                    "text": "User prefers email notifications over SMS.",
                    "confidence": 0.92,
                    "extracted_facts": ["prefers_email", "dislikes_sms"]
                },
                "embedding": [0.1, 0.2, 0.3],  # truncated for example
                "semantic_hash": "a1b2c3d4e5f6789a",
                "relevance_score": 0.87,
                "importance_score": 0.8,
                "created_at": "2025-10-01T10:00:00Z"
            }
        }


class MemoryQuery(BaseModel):
    """Request specification for context retrieval."""
    
    user_id: str = Field(..., min_length=1, max_length=256)
    query: str = Field(
        ..., 
        min_length=1, 
        max_length=8000, 
        description="Natural language or structured query"
    )
    token_budget: int = Field(
        8000, 
        ge=100, 
        le=32000, 
        description="Maximum tokens in assembled context"
    )
    tenant: str = Field(..., min_length=1, max_length=128)
    namespace: str = Field(..., min_length=1, max_length=128)
    
    # Retrieval options
    include_archived: bool = Field(
        False, 
        description="Whether to search cold-stored records"
    )
    disable_sections: list[str] = Field(
        default_factory=list, 
        description="Section names to skip (e.g., ['patterns'])"
    )
    min_relevance: float = Field(
        0.1, 
        ge=0.0, 
        le=1.0, 
        description="Minimum relevance threshold"
    )
    force_sections: list[str] = Field(
        default_factory=list, 
        description="Sections to include regardless of budget"
    )
    
    # Advanced options
    retrieval_options: dict[str, Any] = Field(
        default_factory=dict, 
        description="Advanced tuning (e.g., rerank model, fusion weights)"
    )

    @field_validator("disable_sections", "force_sections") 
    @classmethod
    def validate_section_names(cls, v: list[str]) -> list[str]:
        """Validate section names against known sections."""
        valid_sections = {
            "working", "semantic_facts", "episodic_recent", 
            "summaries", "patterns", "user_profile"
        }
        invalid = set(v) - valid_sections
        if invalid:
            raise ValueError(f"Invalid section names: {invalid}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_12345",
                "query": "What are the user's notification preferences?",
                "token_budget": 4000,
                "tenant": "acme_corp",
                "namespace": "customer_support",
                "min_relevance": 0.2,
                "disable_sections": ["patterns"],
                "retrieval_options": {
                    "enable_rerank": True,
                    "rerank_model": "cross-encoder-mini"
                }
            }
        }


class ProvenanceRecord(BaseModel):
    """Provenance metadata for each context fragment."""
    
    record_id: str = Field(..., description="Source RecordEnvelope ID")
    tier: TierType
    source_type: ContentType
    original_tokens: int = Field(ge=0)
    current_tokens: int = Field(ge=0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    selection_reason: str = Field(
        ..., 
        description="Why included: top_k|explicit|high_importance|boosted"
    )
    transformations: list[dict[str, Any]] = Field(
        default_factory=list, 
        description="Reduction/summarization steps applied"
    )

    @field_validator("selection_reason")
    @classmethod
    def validate_selection_reason(cls, v: str) -> str:
        """Validate selection reason is from allowed set."""
        valid_reasons = {
            "top_k", "explicit", "high_importance", "boosted", 
            "forced_section", "semantic_match", "temporal_match"
        }
        if v not in valid_reasons:
            raise ValueError(f"Invalid selection reason: {v}")
        return v

    def add_transformation(
        self, 
        transformation_type: str, 
        details: dict[str, Any]
    ) -> None:
        """Add a transformation record to the provenance chain."""
        transformation = {
            "type": transformation_type,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details
        }
        self.transformations.append(transformation)


class ContextSection(BaseModel):
    """Logical section within assembled context."""
    
    name: str = Field(
        ..., 
        description="Section identifier (working|semantic_facts|episodic_recent|...)"
    )
    items: list[dict[str, Any]] = Field(
        default_factory=list, 
        description="Ordered memory items"
    )
    estimated_tokens: int = Field(0, ge=0, description="Token count estimate for this section")

    @field_validator("name")
    @classmethod  
    def validate_section_name(cls, v: str) -> str:
        """Validate section name against known sections."""
        valid_sections = {
            "working", "semantic_facts", "episodic_recent",
            "summaries", "patterns", "user_profile"
        }
        if v not in valid_sections:
            raise ValueError(f"Invalid section name: {v}")
        return v


class SmrtiContext(BaseModel):
    """Final assembled context returned to consumer."""
    
    user_id: str
    query: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    token_budget: int
    estimated_tokens: int = Field(ge=0)
    sections: list[ContextSection]
    provenance: list[ProvenanceRecord] 
    stats: dict[str, Any] = Field(
        default_factory=dict, 
        description="Assembly metrics (reductions, discards, etc.)"
    )

    def get_section(self, name: str) -> ContextSection | None:
        """Get section by name, or None if not found."""
        return next((s for s in self.sections if s.name == name), None)

    def total_items(self) -> int:
        """Count total items across all sections."""
        return sum(len(section.items) for section in self.sections)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_12345",
                "query": "notification preferences", 
                "generated_at": "2025-10-03T14:22:00Z",
                "token_budget": 4000,
                "estimated_tokens": 3200,
                "sections": [
                    {
                        "name": "working",
                        "items": [],
                        "estimated_tokens": 0
                    },
                    {
                        "name": "semantic_facts", 
                        "items": [
                            {
                                "fact_id": "fact_001",
                                "text": "User prefers email notifications",
                                "confidence": 0.95
                            }
                        ],
                        "estimated_tokens": 50
                    }
                ],
                "provenance": [
                    {
                        "record_id": "rec_001",
                        "tier": "semantic",
                        "source_type": "FACT",
                        "original_tokens": 50,
                        "current_tokens": 50,
                        "relevance_score": 0.95,
                        "selection_reason": "semantic_match",
                        "transformations": []
                    }
                ],
                "stats": {
                    "reductions_applied": 1,
                    "discarded_items": 3,
                    "total_candidates": 25
                }
            }
        }


class EventRecord(BaseModel):
    """Episodic event ingestion payload."""
    
    tenant: str
    namespace: str
    user_id: str | None
    event_type: str = Field(
        ..., 
        max_length=128, 
        description="Event classification (e.g., 'user_login', 'error')"
    )
    event_data: dict[str, Any] = Field(..., description="Event-specific payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Ensure event type has no whitespace and valid characters."""
        if not re.match(r'^[a-zA-Z0-9_.-]+$', v):
            raise ValueError("Event type must be alphanumeric with underscores, dots, hyphens only")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "tenant": "acme_corp",
                "namespace": "app_usage",
                "user_id": "user_12345", 
                "event_type": "page_view",
                "event_data": {
                    "page": "/dashboard",
                    "duration_seconds": 45.2,
                    "source": "direct"
                },
                "timestamp": "2025-10-03T14:30:00Z",
                "metadata": {
                    "session_id": "sess_abc123",
                    "ip_address": "192.168.1.100"  
                }
            }
        }


class FactRecord(BaseModel):
    """Semantic fact ingestion payload."""
    
    tenant: str
    namespace: str
    entity_id: str = Field(
        ..., 
        min_length=1, 
        max_length=256, 
        description="Entity identifier"
    )
    predicate: str = Field(
        ..., 
        min_length=1, 
        max_length=128, 
        description="Relationship/attribute type"
    )
    object: str | int | float | bool = Field(..., description="Fact value")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("predicate")
    @classmethod
    def validate_predicate(cls, v: str) -> str:
        """Ensure predicate follows naming conventions."""
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError("Predicate must start with letter, contain only alphanumeric and underscore")
        return v

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if fact is valid at given timestamp."""
        return (
            timestamp >= self.valid_from and 
            (self.valid_until is None or timestamp <= self.valid_until)
        )

    class Config:
        json_schema_extra = {
            "example": {
                "tenant": "acme_corp",
                "namespace": "user_profile",
                "entity_id": "user_12345",
                "predicate": "preferred_language", 
                "object": "python",
                "confidence": 0.95,
                "valid_from": "2025-10-01T00:00:00Z",
                "valid_until": None,
                "metadata": {
                    "source": "user_preference_form",
                    "extraction_method": "direct_input"
                }
            }
        }


class ConversationTurn(BaseModel):
    """Dialog turn ingestion for STM."""
    
    tenant: str
    namespace: str
    user_id: str
    session_id: str = Field(..., description="Conversation session identifier")
    role: RoleType = Field(...)
    content: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        """Ensure session ID format."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Session ID must be alphanumeric with underscores and hyphens only")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "tenant": "acme_corp",
                "namespace": "customer_support",
                "user_id": "user_12345",
                "session_id": "sess_abc123",
                "role": "user", 
                "content": "I need help with my notification settings",
                "timestamp": "2025-10-03T14:25:00Z",
                "metadata": {
                    "channel": "web_chat",
                    "lang": "en"
                }
            }
        }


# Configuration models
class TierConfig(BaseModel):
    """Per-tier storage and lifecycle configuration."""
    
    backend: str = Field(
        ..., 
        description="Adapter name (redis|chroma|postgres|neo4j|...)"
    )
    ttl_seconds: int | None = Field(
        None, 
        ge=60, 
        description="Time-to-live for ephemeral tiers"
    )
    half_life_days: float | None = Field(
        None, 
        ge=0.1, 
        description="Decay half-life duration"
    )
    archive_threshold: float | None = Field(
        None, 
        ge=0.0, 
        le=1.0, 
        description="Relevance below which to archive"
    )
    compress_threshold: float | None = Field(
        None, 
        ge=0.0, 
        le=1.0, 
        description="Threshold to trigger compression"
    )
    adapter_config: dict[str, Any] = Field(
        default_factory=dict, 
        description="Backend-specific settings (connection URI, etc.)"
    )

    @field_validator("backend") 
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Validate backend name format."""
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', v):
            raise ValueError("Backend name must start with letter")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "backend": "redis",
                "ttl_seconds": 3600,
                "adapter_config": {
                    "url": "redis://localhost:6379",
                    "db": 0,
                    "max_connections": 10
                }
            }
        }


class Settings(BaseModel):
    """Global Smrti configuration."""
    
    # Tier configurations (required)
    tiers: dict[TierType, TierConfig] = Field(
        ..., 
        description="Configuration per memory tier"
    )
    
    # Retrieval and fusion weights
    fusion_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "vector": 0.45,
            "lexical": 0.20, 
            "graph": 0.15,
            "temporal": 0.10,
            "recency": 0.10
        }
    )
    
    # Feature flags
    feature_flags: dict[str, bool] = Field(
        default_factory=lambda: {
            "enable_rerank": True,
            "enable_graph_traversal": False,
            "enable_fact_extraction": True,
            "enable_entity_resolution": True,
            "enable_conflict_resolution": True,
            "enable_adaptive_weights": True
        }
    )
    
    # Default values
    default_token_budget: int = Field(8000, ge=100, le=32000)
    
    # Context assembly allocation
    context_allocation: dict[str, float] = Field(
        default_factory=lambda: {
            "working": 0.10,
            "semantic": 0.25,
            "episodic": 0.25,
            "summaries": 0.20,
            "patterns": 0.10,
            "slack": 0.10
        }
    )
    
    # Model and provider settings
    embedding_model: str = Field(
        "sentence-transformers/all-MiniLM-L6-v2",
        description="Default embedding model"
    )
    
    # Logging
    log_level: LogLevel = Field("INFO")

    @model_validator(mode='after')
    def validate_allocation_sums_to_one(self):
        """Ensure context allocation fractions sum to ~1.0."""
        total = sum(self.context_allocation.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(f"context_allocation must sum to 1.0 (got {total})")
        return self

    @model_validator(mode='after')
    def validate_fusion_weights_sum(self):
        """Ensure fusion weights sum to ~1.0.""" 
        total = sum(self.fusion_weights.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(f"fusion_weights must sum to 1.0 (got {total})")
        return self

    @field_validator("tiers")
    @classmethod
    def validate_required_tiers(cls, v: dict[TierType, TierConfig]) -> dict[TierType, TierConfig]:
        """Ensure at least working and long_term tiers are configured."""
        required = {"working", "long_term"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"Missing required tiers: {missing}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "tiers": {
                    "working": {
                        "backend": "redis",
                        "ttl_seconds": 300,
                        "adapter_config": {"url": "redis://localhost:6379"}
                    },
                    "long_term": {
                        "backend": "chroma", 
                        "half_life_days": 60.0,
                        "adapter_config": {"persist_directory": "./chroma_data"}
                    }
                },
                "fusion_weights": {
                    "vector": 0.50,
                    "lexical": 0.30,
                    "graph": 0.20
                },
                "default_token_budget": 8000,
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                "log_level": "INFO"
            }
        }


# Additional classes needed by tests
class TextContent(BaseModel):
    """Simple text content model for testing compatibility."""
    
    text: str = Field(..., min_length=1, description="The text content")
    content_type: str = Field(default="text", description="Content type identifier")
    
    @field_validator('text')
    @classmethod
    def validate_text_not_empty(cls, v: str) -> str:
        """Ensure text is not empty or whitespace."""
        if not v.strip():
            raise ValueError("Text content cannot be empty or whitespace only")
        return v
    
    def get_text(self) -> str:
        """Get the text content."""
        return self.text


class MemoryRecord(BaseModel):
    """Enhanced memory record with importance scoring."""
    
    record_id: str = Field(..., description="Unique record identifier")
    content: TextContent = Field(..., description="Record content")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance score")
    created_at: Optional[float] = Field(default_factory=time.time, description="Creation timestamp")
    
    def get_importance(self) -> float:
        """Get the importance score of the record."""
        return self.importance


class ConversationTurn(BaseModel):
    """Represents a single turn in a conversation."""
    
    role: str = Field(..., description="Role of the speaker (user, assistant, system)")
    content: str = Field(..., description="Content of the turn")
    timestamp: Optional[float] = Field(default_factory=time.time, description="Timestamp of the turn")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ContextRecord(BaseModel):
    """Represents a contextual record with enhanced metadata."""
    
    record_id: str = Field(..., description="Unique record identifier")
    content: TextContent = Field(..., description="Record content")
    context_type: str = Field(default="general", description="Type of context")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Importance score")
    created_at: Optional[float] = Field(default_factory=time.time, description="Creation timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class WorkingMemoryConfig(BaseModel):
    """Configuration for working memory tier."""
    
    max_records: int = Field(default=1000, ge=1, description="Maximum number of records")
    ttl_seconds: int = Field(default=3600, ge=1, description="Time to live in seconds")
    consolidation_threshold: int = Field(default=800, ge=1, description="Consolidation trigger threshold")
    cleanup_interval: int = Field(default=300, ge=1, description="Cleanup interval in seconds")