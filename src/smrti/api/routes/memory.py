"""Memory operations endpoints."""

from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, Request, HTTPException, status

from smrti.api.models import (
    StoreMemoryRequest,
    StoreMemoryResponse,
    RetrieveMemoryRequest,
    RetrieveMemoryResponse,
    DeleteMemoryResponse,
    MemoryItem,
    ErrorResponse
)
from smrti.api.storage_manager import StorageManager
from smrti.api.dependencies import get_storage_manager
from smrti.api.auth import get_namespace
from smrti.core.exceptions import ValidationError, StorageError, EmbeddingError
from smrti.core.logging import get_logger
from smrti.core.metrics import http_requests_total, http_request_duration_seconds

import time

logger = get_logger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


@router.post(
    "/store",
    response_model=StoreMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store a memory",
    description="Store a memory in the specified tier",
    responses={
        201: {"description": "Memory stored successfully"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Storage error"}
    }
)
async def store_memory(
    request: Request,
    body: StoreMemoryRequest,
    namespace: str = Depends(get_namespace),
    storage_manager: StorageManager = Depends(get_storage_manager)
) -> StoreMemoryResponse:
    """
    Store a new memory.
    
    Headers required:
    - Authorization: Bearer <api_key>
    - X-Namespace: <namespace>
    
    Memory will be stored in the specified tier with automatic:
    - ID generation
    - Embedding generation (for LONG_TERM)
    - Timestamp addition
    - TTL handling (for WORKING, SHORT_TERM)
    """
    start_time = time.time()
    
    try:
        memory_id = await storage_manager.store(
            memory_type=body.memory_type,
            namespace=namespace,
            data=body.data,
            metadata=body.metadata
        )
        
        duration = time.time() - start_time
        
        # Update metrics
        http_requests_total.labels(
            method="POST",
            endpoint="/memory/store",
            status="2xx"
        ).inc()
        
        http_request_duration_seconds.labels(
            method="POST",
            endpoint="/memory/store"
        ).observe(duration)
        
        logger.info(
            "memory_stored_via_api",
            memory_id=str(memory_id),
            memory_type=body.memory_type,
            namespace=namespace,
            duration_ms=round(duration * 1000, 2)
        )
        
        return StoreMemoryResponse(
            memory_id=memory_id,
            memory_type=body.memory_type,
            namespace=namespace,
            created_at=datetime.now(timezone.utc)
        )
        
    except ValidationError as e:
        http_requests_total.labels(
            method="POST",
            endpoint="/memory/store",
            status="4xx"
        ).inc()
        
        logger.warning(
            "store_validation_error",
            memory_type=body.memory_type,
            namespace=namespace,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
        
    except (StorageError, EmbeddingError) as e:
        http_requests_total.labels(
            method="POST",
            endpoint="/memory/store",
            status="5xx"
        ).inc()
        
        logger.error(
            "store_error",
            memory_type=body.memory_type,
            namespace=namespace,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store memory: {str(e)}"
        )


@router.post(
    "/retrieve",
    response_model=RetrieveMemoryResponse,
    summary="Retrieve memories",
    description="Retrieve memories from the specified tier",
    responses={
        200: {"description": "Memories retrieved successfully"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Retrieval error"}
    }
)
async def retrieve_memories(
    request: Request,
    body: RetrieveMemoryRequest,
    namespace: str = Depends(get_namespace),
    storage_manager: StorageManager = Depends(get_storage_manager)
) -> RetrieveMemoryResponse:
    """
    Retrieve memories matching query and filters.
    
    Headers required:
    - Authorization: Bearer <api_key>
    - X-Namespace: <namespace>
    
    Search behavior varies by tier:
    - WORKING/SHORT_TERM: Text search + time ordering
    - LONG_TERM: Vector similarity search
    - EPISODIC: Time-range queries + full-text search
    - SEMANTIC: Entity/relationship queries
    """
    start_time = time.time()
    
    try:
        memories = await storage_manager.retrieve(
            memory_type=body.memory_type,
            namespace=namespace,
            query=body.query,
            filters=body.filters,
            limit=body.limit
        )
        
        duration = time.time() - start_time
        
        # Update metrics
        http_requests_total.labels(
            method="POST",
            endpoint="/memory/retrieve",
            status="2xx"
        ).inc()
        
        http_request_duration_seconds.labels(
            method="POST",
            endpoint="/memory/retrieve"
        ).observe(duration)
        
        logger.info(
            "memories_retrieved_via_api",
            memory_type=body.memory_type,
            namespace=namespace,
            count=len(memories),
            duration_ms=round(duration * 1000, 2)
        )
        
        # Convert to response model
        memory_items = [
            MemoryItem(
                memory_id=m["memory_id"],
                memory_type=m["memory_type"],
                namespace=m["namespace"],
                data=m["data"],
                metadata=m.get("metadata", {}),
                created_at=m["created_at"],
                relevance_score=m.get("similarity_score") or m.get("relevance_score")
            )
            for m in memories
        ]
        
        return RetrieveMemoryResponse(
            memories=memory_items,
            count=len(memory_items),
            memory_type=body.memory_type
        )
        
    except ValidationError as e:
        http_requests_total.labels(
            method="POST",
            endpoint="/memory/retrieve",
            status="4xx"
        ).inc()
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
        
    except (StorageError, EmbeddingError) as e:
        http_requests_total.labels(
            method="POST",
            endpoint="/memory/retrieve",
            status="5xx"
        ).inc()
        
        logger.error(
            "retrieve_error",
            memory_type=body.memory_type,
            namespace=namespace,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve memories: {str(e)}"
        )


@router.delete(
    "/{memory_type}/{memory_id}",
    response_model=DeleteMemoryResponse,
    summary="Delete a memory",
    description="Delete a specific memory by ID",
    responses={
        200: {"description": "Memory deleted successfully"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Memory not found"},
        500: {"model": ErrorResponse, "description": "Deletion error"}
    }
)
async def delete_memory(
    request: Request,
    memory_type: str,
    memory_id: UUID,
    namespace: str = Depends(get_namespace),
    storage_manager: StorageManager = Depends(get_storage_manager)
) -> DeleteMemoryResponse:
    """
    Delete a specific memory.
    
    Headers required:
    - Authorization: Bearer <api_key>
    - X-Namespace: <namespace>
    
    Only memories in the specified namespace can be deleted (enforced by adapters).
    """
    start_time = time.time()
    
    try:
        deleted = await storage_manager.delete(
            memory_type=memory_type.upper(),
            memory_id=memory_id,
            namespace=namespace
        )
        
        duration = time.time() - start_time
        
        # Update metrics
        http_requests_total.labels(
            method="DELETE",
            endpoint="/memory/{memory_type}/{memory_id}",
            status="2xx" if deleted else "4xx"
        ).inc()
        
        http_request_duration_seconds.labels(
            method="DELETE",
            endpoint="/memory/{memory_type}/{memory_id}"
        ).observe(duration)
        
        if not deleted:
            logger.warning(
                "memory_not_found_for_deletion_via_api",
                memory_id=str(memory_id),
                memory_type=memory_type,
                namespace=namespace
            )
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {memory_id} not found in {memory_type} tier"
            )
        
        logger.info(
            "memory_deleted_via_api",
            memory_id=str(memory_id),
            memory_type=memory_type,
            namespace=namespace,
            duration_ms=round(duration * 1000, 2)
        )
        
        return DeleteMemoryResponse(
            memory_id=memory_id,
            deleted=True,
            memory_type=memory_type.upper()
        )
        
    except HTTPException:
        raise
        
    except ValidationError as e:
        http_requests_total.labels(
            method="DELETE",
            endpoint="/memory/{memory_type}/{memory_id}",
            status="4xx"
        ).inc()
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
        
    except StorageError as e:
        http_requests_total.labels(
            method="DELETE",
            endpoint="/memory/{memory_type}/{memory_id}",
            status="5xx"
        ).inc()
        
        logger.error(
            "delete_error",
            memory_id=str(memory_id),
            memory_type=memory_type,
            namespace=namespace,
            error=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memory: {str(e)}"
        )
