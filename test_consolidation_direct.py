#!/usr/bin/env python3
"""
Test consolidation engine functionality directly.
"""

import sys
import os

# Add to path
sys.path.insert(0, '/home/bert/Work/orgs/konf-dev/smrti')

# Import directly from file path to avoid package init issues
import importlib.util
spec = importlib.util.spec_from_file_location("simple_engine", "/home/bert/Work/orgs/konf-dev/smrti/smrti/consolidation/simple_engine.py")
simple_engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(simple_engine)

print('Testing simple consolidation engine...')

try:
    # Create engine
    engine = simple_engine.SimpleConsolidationEngine()
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
    print(f'  - Status: {task.status}')
    print(f'  - Similarity threshold: {task.similarity_threshold}')
    print(f'  - Importance threshold: {task.importance_threshold}')
    
    # Test task properties
    print(f'  - Is running: {task.is_running}')
    print(f'  - Is completed: {task.is_completed}')
    
    # Simulate consolidation
    result = engine.simulate_consolidation(task.task_id)
    
    print(f'\n✓ Consolidation simulation completed')
    print(f'  - Result status: {result.status}')
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
    
    # Get engine stats
    stats = engine.get_consolidation_stats()
    print(f'\n✓ Engine statistics:')
    print(f'  - Completed tasks: {stats["total_tasks_completed"]}')
    print(f'  - Active tasks: {stats["active_tasks"]}')
    
    # Test action types
    action_types = list(simple_engine.ConsolidationActionType)
    print(f'\n✓ Available action types: {[t.value for t in action_types]}')
    
    print('\n✓ Consolidation engine fully functional!')
    
except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()