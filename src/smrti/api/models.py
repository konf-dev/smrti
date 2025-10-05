"""Pydantic models for API requests and responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class StoreMemoryRequest(BaseModel):
    """Request model for storing a memory."""
    
    memory_type: str = Field(
        ...,
        description="Memory tier: WORKING, SHORT_TERM, LONG_TERM, EPISODIC, or SEMANTIC"
    )
    data: Dict[str, Any] = Field(
        ...,
        description="Memory data (must contain 'text' field)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional metadata"
    )
    
    @field_validator("memory_type")
    @classmethod
    def validate_memory_type(cls, v: str) -> str:
        """Validate memory type is valid."""
        valid_types = {"WORKING", "SHORT_TERM", "LONG_TERM", "EPISODIC", "SEMANTIC"}
        if v.upper() not in valid_types:
            raise ValueError(f"Invalid memory_type. Must be one of: {valid_types}")
        return v.upper()
    
    @field_validator("data")
    @classmethod
    def validate_data_has_text(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data contains 'text' field."""
        if "text" not in v:
            raise ValueError("data must contain 'text' field")
        if not v["text"] or not str(v["text"]).strip():
            raise ValueError("data.text cannot be empty")
        return v


class StoreMemoryResponse(BaseModel):
    """Response model for storing a memory."""
    
    memory_id: UUID = Field(
        ...,
        description="Unique identifier for the stored memory"
    )
    memory_type: str = Field(
        ...,
        description="Memory tier where it was stored"
    )
    namespace: str = Field(
        ...,
        description="Namespace of the stored memory"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when memory was created"
    )


class RetrieveMemoryRequest(BaseModel):
    """Request model for retrieving memories."""
    
    memory_type: str = Field(
        ...,
        description="Memory tier to retrieve from"
    )
    query: Optional[str] = Field(
        default=None,
        description="Search query (text or semantic)"
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Metadata filters"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results"
    )
    
    @field_validator("memory_type")
    @classmethod
    def validate_memory_type(cls, v: str) -> str:
        """Validate memory type is valid."""
        valid_types = {"WORKING", "SHORT_TERM", "LONG_TERM", "EPISODIC", "SEMANTIC"}
        if v.upper() not in valid_types:
            raise ValueError(f"Invalid memory_type. Must be one of: {valid_types}")
        return v.upper()


class MemoryItem(BaseModel):
    """Individual memory item in response."""
    
    memory_id: str = Field(
        ...,
        description="Unique identifier"
    )
    memory_type: str = Field(
        ...,
        description="Memory tier"
    )
    namespace: str = Field(
        ...,
        description="Memory namespace"
    )
    data: Dict[str, Any] = Field(
        ...,
        description="Memory data"
    )
    metadata: Dict[str, Any] = Field(
        ...,
        description="Memory metadata"
    )
    created_at: str = Field(
        ...,
        description="Creation timestamp (ISO format)"
    )
    relevance_score: Optional[float] = Field(
        default=None,
        description="Relevance score (for similarity searches)"
    )


class RetrieveMemoryResponse(BaseModel):
    """Response model for retrieving memories."""
    
    memories: List[MemoryItem] = Field(
        ...,
        description="List of matching memories"
    )
    count: int = Field(
        ...,
        description="Number of memories returned"
    )
    memory_type: str = Field(
        ...,
        description="Memory tier searched"
    )


class DeleteMemoryResponse(BaseModel):
    """Response model for deleting a memory."""
    
    memory_id: UUID = Field(
        ...,
        description="Identifier of deleted memory"
    )
    deleted: bool = Field(
        ...,
        description="Whether memory was successfully deleted"
    )
    memory_type: str = Field(
        ...,
        description="Memory tier"
    )


class HealthCheckResponse(BaseModel):
    """Response model for health check."""
    
    status: str = Field(
        ...,
        description="Overall system status"
    )
    version: str = Field(
        ...,
        description="API version"
    )
    services: Dict[str, Any] = Field(
        ...,
        description="Status of each service component"
    )


class ErrorResponse(BaseModel):
    """Response model for errors."""
    
    error: str = Field(
        ...,
        description="Error type"
    )
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    detail: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error details"
    )
