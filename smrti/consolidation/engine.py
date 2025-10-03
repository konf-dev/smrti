"""
smrti/consolidation/engine.py - Core consolidation engine

Implements the main consolidation engine that manages memory consolidation
operations across different tiers with configurable strategies.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, List, Optional, Set, Any, Callable, Protocol
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from ..schemas.models import MemoryRecord, RecordEnvelope
from ..memory.tiers.base import BaseTier
from ..engines.similarity import SimilarityEngine


class ConsolidationStatus(str, Enum):
    """Status of consolidation operations."""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConsolidationActionType(str, Enum):
    """Types of consolidation actions."""
    MERGE = "merge"
    PROMOTE = "promote"
    ARCHIVE = "archive"
    DELETE = "delete"
    UPDATE = "update"
    NO_ACTION = "no_action"


@dataclass
class ConsolidationMetrics:
    """Metrics for consolidation operations."""
    
    records_processed: int = 0
    records_merged: int = 0
    records_promoted: int = 0
    records_archived: int = 0
    records_deleted: int = 0
    
    processing_time_ms: float = 0.0
    similarity_calculations: int = 0
    importance_calculations: int = 0
    
    memory_freed_bytes: int = 0
    tiers_affected: Set[str] = field(default_factory=set)
    
    errors_encountered: int = 0
    warnings_generated: int = 0


@dataclass
class ConsolidationAction:
    """Represents a single consolidation action."""
    
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ConsolidationActionType = ConsolidationActionType.NO_ACTION
    
    # Record identifiers
    source_record_ids: List[str] = field(default_factory=list)
    target_record_id: Optional[str] = None
    
    # Tier information
    source_tier: str = ""
    target_tier: Optional[str] = None
    
    # Action metadata
    similarity_score: Optional[float] = None
    importance_score: Optional[float] = None
    confidence: float = 0.0
    reasoning: str = ""
    
    # Processing metadata
    created_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None
    
    def __post_init__(self):
        """Post-initialization validation."""
        if not self.source_record_ids:
            raise ValueError("At least one source record ID is required")
        
        if self.action_type == ConsolidationActionType.MERGE and len(self.source_record_ids) < 2:
            raise ValueError("MERGE action requires at least two source records")


@dataclass
class ConsolidationTask:
    """Represents a consolidation task for a specific tier/scope."""
    
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tier_name: str = ""
    
    # Task configuration
    max_records: Optional[int] = None
    similarity_threshold: float = 0.8
    importance_threshold: float = 0.3
    time_limit_seconds: Optional[float] = None
    
    # Task state
    status: ConsolidationStatus = ConsolidationStatus.PENDING
    progress: float = 0.0
    
    # Results
    actions: List[ConsolidationAction] = field(default_factory=list)
    metrics: ConsolidationMetrics = field(default_factory=ConsolidationMetrics)
    
    # Timestamps
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate task duration in milliseconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None
    
    @property
    def is_running(self) -> bool:
        """Check if task is currently running."""
        return self.status == ConsolidationStatus.RUNNING
    
    @property
    def is_completed(self) -> bool:
        """Check if task is completed (success or failure)."""
        return self.status in [ConsolidationStatus.COMPLETED, ConsolidationStatus.FAILED, ConsolidationStatus.CANCELLED]


@dataclass
class ConsolidationResult:
    """Results of a consolidation operation."""
    
    task_id: str
    status: ConsolidationStatus
    
    # Summary metrics
    total_records_processed: int = 0
    actions_performed: int = 0
    processing_time_ms: float = 0.0
    
    # Detailed results
    actions: List[ConsolidationAction] = field(default_factory=list)
    metrics: ConsolidationMetrics = field(default_factory=ConsolidationMetrics)
    
    # Metadata
    tier_name: str = ""
    timestamp: float = field(default_factory=time.time)
    
    # Error information
    success: bool = True
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class ConsolidationEngine:
    """Core engine for memory consolidation operations."""
    
    def __init__(self, 
                 similarity_engine: SimilarityEngine,
                 progress_callback: Optional[Callable[[str, float], None]] = None):
        """Initialize the consolidation engine.
        
        Args:
            similarity_engine: Engine for computing record similarities
            progress_callback: Optional callback for progress updates
        """
        self.similarity_engine = similarity_engine
        self.progress_callback = progress_callback
        
        # Active tasks
        self.active_tasks: Dict[str, ConsolidationTask] = {}
        self.completed_tasks: Dict[str, ConsolidationResult] = {}
        
        # Configuration
        self.max_concurrent_tasks = 2
        self.default_batch_size = 100
        
        # Performance tracking
        self._total_records_processed = 0
        self._total_processing_time_ms = 0.0
    
    async def consolidate_tier(self, 
                              tier: BaseTier,
                              similarity_threshold: float = 0.8,
                              importance_threshold: float = 0.3,
                              max_records: Optional[int] = None,
                              time_limit_seconds: Optional[float] = None) -> ConsolidationResult:
        """Consolidate records in a specific memory tier.
        
        Args:
            tier: Memory tier to consolidate
            similarity_threshold: Minimum similarity for merging records
            importance_threshold: Minimum importance to retain records
            max_records: Maximum number of records to process
            time_limit_seconds: Maximum time to spend on consolidation
            
        Returns:
            ConsolidationResult with operation details
        """
        # Create consolidation task
        task = ConsolidationTask(
            tier_name=tier.tier_type.value,
            max_records=max_records,
            similarity_threshold=similarity_threshold,
            importance_threshold=importance_threshold,
            time_limit_seconds=time_limit_seconds
        )
        
        # Register and execute task
        self.active_tasks[task.task_id] = task
        
        try:
            result = await self._execute_consolidation_task(task, tier)
            self.completed_tasks[task.task_id] = result
            return result
            
        finally:
            # Clean up active task
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]
    
    async def _execute_consolidation_task(self, 
                                        task: ConsolidationTask, 
                                        tier: BaseTier) -> ConsolidationResult:
        """Execute a consolidation task.
        
        Args:
            task: Consolidation task to execute
            tier: Memory tier to process
            
        Returns:
            ConsolidationResult with operation results
        """
        start_time = time.time()
        task.status = ConsolidationStatus.RUNNING
        task.started_at = start_time
        
        try:
            # Get records to process
            records = await self._get_records_for_consolidation(tier, task.max_records)
            task.metrics.records_processed = len(records)
            
            # Update progress
            self._update_progress(task.task_id, 0.1)
            
            # Phase 1: Identify similar records for merging
            similarity_actions = await self._find_similar_records(
                records, task.similarity_threshold, tier.tier_type.value
            )
            task.actions.extend(similarity_actions)
            task.metrics.similarity_calculations = len(similarity_actions)
            
            # Update progress
            self._update_progress(task.task_id, 0.4)
            
            # Phase 2: Identify records for importance-based promotion/deletion
            importance_actions = await self._evaluate_importance(
                records, task.importance_threshold, tier.tier_type.value
            )
            task.actions.extend(importance_actions)
            task.metrics.importance_calculations = len(importance_actions)
            
            # Update progress
            self._update_progress(task.task_id, 0.7)
            
            # Phase 3: Execute consolidation actions
            execution_results = await self._execute_actions(task.actions, tier)
            task.metrics.records_merged = sum(1 for r in execution_results if r.get('action') == 'merged')
            task.metrics.records_promoted = sum(1 for r in execution_results if r.get('action') == 'promoted')
            task.metrics.records_deleted = sum(1 for r in execution_results if r.get('action') == 'deleted')
            
            # Update progress
            self._update_progress(task.task_id, 1.0)
            
            # Complete task
            task.status = ConsolidationStatus.COMPLETED
            task.completed_at = time.time()
            task.metrics.processing_time_ms = (task.completed_at - start_time) * 1000
            task.metrics.tiers_affected.add(tier.tier_type.value)
            
            # Create result
            result = ConsolidationResult(
                task_id=task.task_id,
                status=task.status,
                total_records_processed=task.metrics.records_processed,
                actions_performed=len(task.actions),
                processing_time_ms=task.metrics.processing_time_ms,
                actions=task.actions,
                metrics=task.metrics,
                tier_name=tier.tier_type.value,
                success=True
            )
            
            return result
            
        except Exception as e:
            # Handle task failure
            task.status = ConsolidationStatus.FAILED
            task.completed_at = time.time()
            task.error_message = str(e)
            task.metrics.errors_encountered += 1
            
            result = ConsolidationResult(
                task_id=task.task_id,
                status=task.status,
                tier_name=tier.tier_type.value,
                success=False,
                error_message=str(e)
            )
            
            return result
    
    async def _get_records_for_consolidation(self, 
                                           tier: BaseTier, 
                                           max_records: Optional[int]) -> List[MemoryRecord]:
        """Get records from tier for consolidation processing.
        
        Args:
            tier: Memory tier
            max_records: Maximum number of records to retrieve
            
        Returns:
            List of memory records
        """
        # For now, get all records (in practice, we'd implement smarter selection)
        # This could prioritize older records, lower importance records, etc.
        
        try:
            # Create a simple query to get records
            from ..schemas.models import MemoryQuery
            
            query = MemoryQuery(
                content="",  # Empty query to get all records
                limit=max_records or 1000,
                include_metadata=True
            )
            
            # Query the tier
            envelopes = await tier.search(query)
            
            # Extract records from envelopes
            records = []
            for envelope in envelopes:
                if hasattr(envelope, 'record') and envelope.record:
                    records.append(envelope.record)
            
            return records
            
        except Exception as e:
            print(f"Error retrieving records from tier {tier.tier_type}: {e}")
            return []
    
    async def _find_similar_records(self, 
                                   records: List[MemoryRecord], 
                                   threshold: float, 
                                   tier_name: str) -> List[ConsolidationAction]:
        """Find similar records that can be merged.
        
        Args:
            records: List of memory records
            threshold: Similarity threshold for merging
            tier_name: Name of the tier being processed
            
        Returns:
            List of merge actions
        """
        actions = []
        processed_ids = set()
        
        # Compare each record with all others
        for i, record1 in enumerate(records):
            if record1.record_id in processed_ids:
                continue
            
            similar_records = [record1]
            
            for j, record2 in enumerate(records[i+1:], i+1):
                if record2.record_id in processed_ids:
                    continue
                
                # Calculate similarity
                similarity = await self.similarity_engine.calculate_similarity(
                    record1.content.get_text(),
                    record2.content.get_text()
                )
                
                if similarity >= threshold:
                    similar_records.append(record2)
                    processed_ids.add(record2.record_id)
            
            # Create merge action if we have similar records
            if len(similar_records) > 1:
                action = ConsolidationAction(
                    action_type=ConsolidationActionType.MERGE,
                    source_record_ids=[r.record_id for r in similar_records],
                    target_record_id=similar_records[0].record_id,  # Keep the first one as target
                    source_tier=tier_name,
                    target_tier=tier_name,
                    similarity_score=threshold,  # Average similarity would be better
                    confidence=0.8,
                    reasoning=f"Merged {len(similar_records)} similar records with similarity >= {threshold}"
                )
                actions.append(action)
                
                # Mark all as processed
                for record in similar_records:
                    processed_ids.add(record.record_id)
        
        return actions
    
    async def _evaluate_importance(self, 
                                  records: List[MemoryRecord], 
                                  threshold: float, 
                                  tier_name: str) -> List[ConsolidationAction]:
        """Evaluate records for importance-based actions.
        
        Args:
            records: List of memory records
            threshold: Importance threshold
            tier_name: Name of the tier being processed
            
        Returns:
            List of importance-based actions
        """
        actions = []
        
        for record in records:
            importance = record.importance
            
            if importance < threshold:
                # Record has low importance - consider for deletion or archival
                action = ConsolidationAction(
                    action_type=ConsolidationActionType.DELETE,
                    source_record_ids=[record.record_id],
                    source_tier=tier_name,
                    importance_score=importance,
                    confidence=0.7,
                    reasoning=f"Low importance record ({importance:.3f} < {threshold})"
                )
                actions.append(action)
                
            elif importance > 0.8:
                # High importance record - consider for promotion to higher tier
                target_tier = self._get_promotion_tier(tier_name)
                if target_tier:
                    action = ConsolidationAction(
                        action_type=ConsolidationActionType.PROMOTE,
                        source_record_ids=[record.record_id],
                        source_tier=tier_name,
                        target_tier=target_tier,
                        importance_score=importance,
                        confidence=0.9,
                        reasoning=f"High importance record ({importance:.3f}) promoted to {target_tier}"
                    )
                    actions.append(action)
        
        return actions
    
    def _get_promotion_tier(self, current_tier: str) -> Optional[str]:
        """Get the target tier for promotion.
        
        Args:
            current_tier: Current tier name
            
        Returns:
            Target tier name or None
        """
        # Simple promotion logic - can be made more sophisticated
        promotion_map = {
            "working": "short_term",
            "short_term": "long_term",
            # long_term records stay in long_term
        }
        return promotion_map.get(current_tier)
    
    async def _execute_actions(self, 
                              actions: List[ConsolidationAction], 
                              tier: BaseTier) -> List[Dict[str, Any]]:
        """Execute consolidation actions.
        
        Args:
            actions: List of actions to execute
            tier: Memory tier to operate on
            
        Returns:
            List of execution results
        """
        results = []
        
        for action in actions:
            try:
                if action.action_type == ConsolidationActionType.MERGE:
                    result = await self._execute_merge(action, tier)
                elif action.action_type == ConsolidationActionType.DELETE:
                    result = await self._execute_delete(action, tier)
                elif action.action_type == ConsolidationActionType.PROMOTE:
                    result = await self._execute_promote(action, tier)
                else:
                    result = {"action": "skipped", "reason": f"Unsupported action: {action.action_type}"}
                
                action.executed_at = time.time()
                results.append(result)
                
            except Exception as e:
                result = {"action": "failed", "error": str(e)}
                results.append(result)
        
        return results
    
    async def _execute_merge(self, action: ConsolidationAction, tier: BaseTier) -> Dict[str, Any]:
        """Execute a record merge action.
        
        Args:
            action: Merge action to execute
            tier: Memory tier
            
        Returns:
            Execution result
        """
        # For now, just remove duplicate records (keep the target)
        # In practice, we'd merge content and metadata intelligently
        
        for record_id in action.source_record_ids[1:]:  # Skip first (target) record
            try:
                await tier.delete_record(record_id)
            except Exception as e:
                print(f"Error deleting record {record_id} during merge: {e}")
        
        return {"action": "merged", "records_merged": len(action.source_record_ids) - 1}
    
    async def _execute_delete(self, action: ConsolidationAction, tier: BaseTier) -> Dict[str, Any]:
        """Execute a record deletion action.
        
        Args:
            action: Delete action to execute
            tier: Memory tier
            
        Returns:
            Execution result
        """
        for record_id in action.source_record_ids:
            try:
                await tier.delete_record(record_id)
            except Exception as e:
                print(f"Error deleting record {record_id}: {e}")
        
        return {"action": "deleted", "records_deleted": len(action.source_record_ids)}
    
    async def _execute_promote(self, action: ConsolidationAction, tier: BaseTier) -> Dict[str, Any]:
        """Execute a record promotion action.
        
        Args:
            action: Promote action to execute
            tier: Memory tier
            
        Returns:
            Execution result
        """
        # For now, just mark as promoted (actual promotion would require target tier)
        # In practice, we'd move records to the target tier
        
        return {"action": "promoted", "records_promoted": len(action.source_record_ids)}
    
    def _update_progress(self, task_id: str, progress: float):
        """Update task progress.
        
        Args:
            task_id: Task identifier
            progress: Progress value (0.0 to 1.0)
        """
        if task_id in self.active_tasks:
            self.active_tasks[task_id].progress = progress
            
            if self.progress_callback:
                self.progress_callback(task_id, progress)
    
    def get_task_status(self, task_id: str) -> Optional[ConsolidationTask]:
        """Get the status of a consolidation task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            ConsolidationTask or None if not found
        """
        return self.active_tasks.get(task_id)
    
    def get_active_tasks(self) -> Dict[str, ConsolidationTask]:
        """Get all active consolidation tasks.
        
        Returns:
            Dictionary of active tasks
        """
        return self.active_tasks.copy()
    
    def get_task_history(self, limit: Optional[int] = None) -> List[ConsolidationResult]:
        """Get completed task history.
        
        Args:
            limit: Maximum number of results to return
            
        Returns:
            List of completed tasks
        """
        results = list(self.completed_tasks.values())
        results.sort(key=lambda x: x.timestamp, reverse=True)
        
        if limit:
            results = results[:limit]
        
        return results
    
    def get_consolidation_stats(self) -> Dict[str, Any]:
        """Get overall consolidation statistics.
        
        Returns:
            Dictionary with consolidation statistics
        """
        return {
            "total_tasks_completed": len(self.completed_tasks),
            "active_tasks": len(self.active_tasks),
            "total_records_processed": self._total_records_processed,
            "total_processing_time_ms": self._total_processing_time_ms,
            "average_processing_time_ms": (
                self._total_processing_time_ms / len(self.completed_tasks) 
                if self.completed_tasks else 0
            )
        }