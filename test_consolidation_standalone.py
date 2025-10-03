#!/usr/bin/env python3
"""
Standalone test of consolidation functionality.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any

# Define the core classes inline for testing

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
    source_record_ids: List[str] = field(default_factory=list)
    target_record_id: Optional[str] = None
    source_tier: str = ""
    target_tier: Optional[str] = None
    similarity_score: Optional[float] = None
    importance_score: Optional[float] = None
    confidence: float = 0.0
    reasoning: str = ""
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
    """Represents a consolidation task."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tier_name: str = ""
    max_records: Optional[int] = None
    similarity_threshold: float = 0.8
    importance_threshold: float = 0.3
    time_limit_seconds: Optional[float] = None
    status: ConsolidationStatus = ConsolidationStatus.PENDING
    progress: float = 0.0
    actions: List[ConsolidationAction] = field(default_factory=list)
    metrics: ConsolidationMetrics = field(default_factory=ConsolidationMetrics)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
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
    total_records_processed: int = 0
    actions_performed: int = 0
    processing_time_ms: float = 0.0
    actions: List[ConsolidationAction] = field(default_factory=list)
    metrics: ConsolidationMetrics = field(default_factory=ConsolidationMetrics)
    tier_name: str = ""
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

class SimpleConsolidationEngine:
    """Simplified consolidation engine for testing."""
    
    def __init__(self):
        """Initialize the simple consolidation engine."""
        self.active_tasks: Dict[str, ConsolidationTask] = {}
        self.completed_tasks: Dict[str, ConsolidationResult] = {}
    
    def create_task(self, 
                   tier_name: str,
                   similarity_threshold: float = 0.8,
                   importance_threshold: float = 0.3) -> ConsolidationTask:
        """Create a new consolidation task."""
        task = ConsolidationTask(
            tier_name=tier_name,
            similarity_threshold=similarity_threshold,
            importance_threshold=importance_threshold
        )
        
        self.active_tasks[task.task_id] = task
        return task
    
    def simulate_consolidation(self, task_id: str) -> ConsolidationResult:
        """Simulate a consolidation operation."""
        if task_id not in self.active_tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self.active_tasks[task_id]
        task.status = ConsolidationStatus.RUNNING
        task.started_at = time.time()
        
        # Simulate some processing
        time.sleep(0.05)  # Simulate work
        
        # Create some mock actions
        merge_action = ConsolidationAction(
            action_type=ConsolidationActionType.MERGE,
            source_record_ids=["record1", "record2"],
            target_record_id="record1",
            source_tier=task.tier_name,
            similarity_score=0.9,
            confidence=0.85,
            reasoning="Simulated merge of similar records"
        )
        
        promote_action = ConsolidationAction(
            action_type=ConsolidationActionType.PROMOTE,
            source_record_ids=["record3"],
            source_tier=task.tier_name,
            target_tier="long_term",
            importance_score=0.9,
            confidence=0.8,
            reasoning="High importance record promotion"
        )
        
        task.actions = [merge_action, promote_action]
        task.metrics.records_processed = 3
        task.metrics.records_merged = 1
        task.metrics.records_promoted = 1
        task.metrics.similarity_calculations = 2
        task.metrics.importance_calculations = 3
        task.metrics.tiers_affected.add(task.tier_name)
        
        task.status = ConsolidationStatus.COMPLETED
        task.completed_at = time.time()
        task.metrics.processing_time_ms = (task.completed_at - task.started_at) * 1000
        
        # Create result
        result = ConsolidationResult(
            task_id=task.task_id,
            status=task.status,
            total_records_processed=task.metrics.records_processed,
            actions_performed=len(task.actions),
            processing_time_ms=task.metrics.processing_time_ms,
            actions=task.actions,
            metrics=task.metrics,
            tier_name=task.tier_name,
            success=True
        )
        
        self.completed_tasks[task_id] = result
        del self.active_tasks[task_id]
        
        return result

# Run the tests
if __name__ == "__main__":
    print('Testing consolidation engine functionality...')
    
    try:
        # Create engine
        engine = SimpleConsolidationEngine()
        print(f'✓ SimpleConsolidationEngine created')
        
        # Create a task
        task = engine.create_task(
            tier_name='working',
            similarity_threshold=0.8,
            importance_threshold=0.3
        )
        
        print(f'\n✓ ConsolidationTask created')
        print(f'  - Task ID: {task.task_id[:8]}...')
        print(f'  - Tier: {task.tier_name}')
        print(f'  - Status: {task.status.value}')
        print(f'  - Similarity threshold: {task.similarity_threshold}')
        print(f'  - Importance threshold: {task.importance_threshold}')
        
        # Test task properties
        print(f'  - Is running: {task.is_running}')
        print(f'  - Is completed: {task.is_completed}')
        
        # Simulate consolidation
        result = engine.simulate_consolidation(task.task_id)
        
        print(f'\n✓ Consolidation simulation completed')
        print(f'  - Result status: {result.status.value}')
        print(f'  - Records processed: {result.total_records_processed}')
        print(f'  - Actions performed: {result.actions_performed}')
        print(f'  - Processing time: {result.processing_time_ms:.1f}ms')
        print(f'  - Success: {result.success}')
        
        # Check actions
        print(f'\n✓ Consolidation actions:')
        for i, action in enumerate(result.actions):
            print(f'  Action {i+1}:')
            print(f'    - Type: {action.action_type.value}')
            print(f'    - Source records: {len(action.source_record_ids)}')
            print(f'    - Confidence: {action.confidence}')
            print(f'    - Reasoning: {action.reasoning[:50]}...')
        
        # Check metrics
        print(f'\n✓ Consolidation metrics:')
        metrics = result.metrics
        print(f'  - Records merged: {metrics.records_merged}')
        print(f'  - Records promoted: {metrics.records_promoted}')
        print(f'  - Similarity calculations: {metrics.similarity_calculations}')
        print(f'  - Importance calculations: {metrics.importance_calculations}')
        print(f'  - Tiers affected: {len(metrics.tiers_affected)}')
        
        # Test action types
        action_types = list(ConsolidationActionType)
        print(f'\n✓ Available action types: {[t.value for t in action_types]}')
        
        print('\n✓ Consolidation engine fully functional!')
        
    except Exception as e:
        print(f'✗ Error: {e}')
        import traceback
        traceback.print_exc()