"""
Test consolidation engine in isolation without full system dependencies.
"""

import sys
sys.path.insert(0, '/home/bert/Work/orgs/konf-dev/smrti')

# Test just the core components without full imports
from smrti.consolidation.engine import ConsolidationTask, ConsolidationActionType, ConsolidationMetrics, ConsolidationAction

print('Testing consolidation engine components in isolation...')

try:
    # Test task creation
    task = ConsolidationTask(
        tier_name='working',
        similarity_threshold=0.8,
        importance_threshold=0.3
    )
    
    print(f'✓ ConsolidationTask created')
    print(f'  - Task ID: {task.task_id}')
    print(f'  - Tier: {task.tier_name}')
    print(f'  - Status: {task.status}')
    print(f'  - Is running: {task.is_running}')
    print(f'  - Is completed: {task.is_completed}')
    
    # Test metrics
    metrics = ConsolidationMetrics()
    print(f'\n✓ ConsolidationMetrics created')
    print(f'  - Records processed: {metrics.records_processed}')
    print(f'  - Processing time: {metrics.processing_time_ms}ms')
    print(f'  - Tiers affected: {len(metrics.tiers_affected)}')
    
    # Test action creation
    action = ConsolidationAction(
        action_type=ConsolidationActionType.MERGE,
        source_record_ids=['record1', 'record2'],
        target_record_id='record1',
        source_tier='working',
        similarity_score=0.9,
        confidence=0.85,
        reasoning="High similarity merge test"
    )
    
    print(f'\n✓ ConsolidationAction created')
    print(f'  - Action ID: {action.action_id}')
    print(f'  - Action type: {action.action_type}')
    print(f'  - Source records: {len(action.source_record_ids)}')
    print(f'  - Confidence: {action.confidence}')
    
    # Test action types
    action_types = list(ConsolidationActionType)
    print(f'\n✓ Available action types: {[t.value for t in action_types]}')
    
    print('\n✓ Consolidation engine components working correctly!')
    
except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()