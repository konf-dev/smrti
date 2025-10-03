"""
smrti/core/consolidation.py - Memory Consolidation System

Background processes for intelligent memory consolidation between tiers
based on access patterns, importance scoring, and lifecycle management.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from smrti.core.base import BaseAdapter
from smrti.core.exceptions import ConsolidationError, ValidationError
from smrti.core.registry import AdapterRegistry
from smrti.schemas.models import MemoryQuery, MemoryRecord, RecordEnvelope


class ConsolidationAction(Enum):
    """Types of consolidation actions."""
    
    PROMOTE = "promote"      # Move to higher priority tier
    DEMOTE = "demote"        # Move to lower priority tier
    REPLICATE = "replicate"  # Copy to another tier
    ARCHIVE = "archive"      # Move to long-term storage
    DELETE = "delete"        # Remove from system
    MERGE = "merge"          # Combine similar memories


class ConsolidationTrigger(Enum):
    """Triggers for consolidation actions."""
    
    ACCESS_FREQUENCY = "access_frequency"    # Based on how often accessed
    TIME_DECAY = "time_decay"               # Based on age
    CAPACITY_PRESSURE = "capacity_pressure" # Based on tier capacity
    SEMANTIC_SIMILARITY = "semantic_similarity" # Based on content similarity
    EXPLICIT_IMPORTANCE = "explicit_importance" # Based on explicit scoring
    SCHEDULED = "scheduled"                 # Based on time schedule


@dataclass
class ConsolidationRule:
    """Rule definition for memory consolidation."""
    
    name: str
    trigger: ConsolidationTrigger
    action: ConsolidationAction
    
    # Source and target tiers
    source_tier: str
    target_tier: Optional[str] = None
    
    # Conditions
    min_age_hours: Optional[int] = None
    max_age_hours: Optional[int] = None
    min_access_count: Optional[int] = None
    max_access_count: Optional[int] = None
    min_importance_score: Optional[float] = None
    max_importance_score: Optional[float] = None
    capacity_threshold: Optional[float] = None  # 0.0 to 1.0
    
    # Execution parameters
    batch_size: int = 100
    enabled: bool = True
    priority: int = 1  # Higher number = higher priority
    
    def matches_record(self, record: RecordEnvelope, tier_capacity: float) -> bool:
        """Check if this rule applies to a record."""
        if not self.enabled:
            return False
        
        # Check age constraints
        if record.created_at:
            age_hours = (datetime.utcnow() - record.created_at).total_seconds() / 3600
            
            if self.min_age_hours is not None and age_hours < self.min_age_hours:
                return False
            
            if self.max_age_hours is not None and age_hours > self.max_age_hours:
                return False
        
        # Check access count constraints
        access_count = record.metadata.get("access_count", 0)
        
        if self.min_access_count is not None and access_count < self.min_access_count:
            return False
        
        if self.max_access_count is not None and access_count > self.max_access_count:
            return False
        
        # Check importance score constraints
        importance = record.metadata.get("importance_score", 0.5)
        
        if self.min_importance_score is not None and importance < self.min_importance_score:
            return False
        
        if self.max_importance_score is not None and importance > self.max_importance_score:
            return False
        
        # Check capacity constraints
        if self.capacity_threshold is not None and tier_capacity < self.capacity_threshold:
            return False
        
        return True


@dataclass
class ConsolidationPlan:
    """Plan for executing consolidation actions."""
    
    plan_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Actions to execute
    actions: List[Tuple[ConsolidationRule, List[RecordEnvelope]]] = field(default_factory=list)
    
    # Execution parameters
    estimated_duration: float = 0.0
    estimated_records_moved: int = 0
    priority: int = 1
    
    # Status tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def is_completed(self) -> bool:
        """Check if plan is completed."""
        return self.completed_at is not None
    
    @property
    def is_failed(self) -> bool:
        """Check if plan has failed."""
        return self.failed_at is not None
    
    @property
    def duration(self) -> Optional[float]:
        """Get execution duration if completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class ConsolidationConfig:
    """Configuration for memory consolidation system."""
    
    # Scheduling configuration
    consolidation_interval_minutes: int = 60  # Run every hour
    cleanup_interval_minutes: int = 1440      # Daily cleanup
    max_concurrent_plans: int = 3
    
    # Performance configuration
    max_batch_size: int = 1000
    max_consolidation_time: float = 300.0  # 5 minutes max per plan
    records_per_second_limit: int = 100
    
    # Default consolidation rules
    enable_default_rules: bool = True
    
    # Working memory rules
    working_to_short_term_hours: int = 1      # Promote after 1 hour if accessed
    working_cleanup_hours: int = 24           # Delete after 24 hours if not accessed
    
    # Short-term memory rules  
    short_term_to_long_term_hours: int = 72   # Promote after 3 days if important
    short_term_cleanup_hours: int = 168       # Delete after 1 week if not important
    
    # Long-term memory rules
    long_term_importance_threshold: float = 0.7  # Keep if importance >= 0.7
    long_term_cleanup_days: int = 365            # Review after 1 year
    
    # Capacity-based rules
    capacity_warning_threshold: float = 0.8   # Start aggressive consolidation at 80%
    capacity_critical_threshold: float = 0.95 # Emergency consolidation at 95%
    
    # Quality control
    similarity_merge_threshold: float = 0.9   # Merge very similar memories
    min_importance_to_keep: float = 0.1      # Delete memories below this importance
    
    # Monitoring
    enable_consolidation_metrics: bool = True
    log_consolidation_actions: bool = True


class MemoryConsolidationEngine(BaseAdapter):
    """
    Intelligent memory consolidation engine.
    
    Manages memory lifecycle across tiers with configurable rules,
    background processing, and intelligent decision making.
    """
    
    def __init__(
        self,
        registry: AdapterRegistry,
        config: Optional[ConsolidationConfig] = None
    ):
        super().__init__("memory_consolidation")
        self.registry = registry
        self.config = config or ConsolidationConfig()
        
        # Consolidation rules
        self.rules: List[ConsolidationRule] = []
        self._setup_default_rules()
        
        # Execution state
        self._running = False
        self._consolidation_task: Optional[asyncio.Task] = None
        self._active_plans: Dict[str, ConsolidationPlan] = {}
        self._plan_queue: deque = deque()
        
        # Performance tracking
        self._consolidations_performed = 0
        self._records_consolidated = 0
        self._total_consolidation_time = 0.0
        self._last_consolidation: Optional[datetime] = None
        
        # Rule performance tracking
        self._rule_performance: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "executions": 0,
            "records_processed": 0,
            "total_time": 0.0,
            "success_rate": 1.0,
            "failures": 0
        })
        
        # Rate limiting
        self._consolidation_rate_limiter = asyncio.Semaphore(
            self.config.records_per_second_limit
        )
    
    def _setup_default_rules(self) -> None:
        """Set up default consolidation rules."""
        if not self.config.enable_default_rules:
            return
        
        # Working Memory Rules
        self.rules.extend([
            # Promote frequently accessed working memories to short-term
            ConsolidationRule(
                name="working_to_short_term_accessed",
                trigger=ConsolidationTrigger.ACCESS_FREQUENCY,
                action=ConsolidationAction.PROMOTE,
                source_tier="working",
                target_tier="short_term",
                min_age_hours=self.config.working_to_short_term_hours,
                min_access_count=3,
                priority=9
            ),
            
            # Clean up old working memories
            ConsolidationRule(
                name="working_memory_cleanup",
                trigger=ConsolidationTrigger.TIME_DECAY,
                action=ConsolidationAction.DELETE,
                source_tier="working",
                min_age_hours=self.config.working_cleanup_hours,
                max_access_count=1,
                priority=3
            ),
            
            # Emergency cleanup when working memory is full
            ConsolidationRule(
                name="working_capacity_emergency",
                trigger=ConsolidationTrigger.CAPACITY_PRESSURE,
                action=ConsolidationAction.DELETE,
                source_tier="working",
                capacity_threshold=self.config.capacity_critical_threshold,
                max_importance_score=0.3,
                priority=10
            )
        ])
        
        # Short-Term Memory Rules
        self.rules.extend([
            # Promote important short-term memories to long-term
            ConsolidationRule(
                name="short_term_to_long_term",
                trigger=ConsolidationTrigger.EXPLICIT_IMPORTANCE,
                action=ConsolidationAction.PROMOTE,
                source_tier="short_term",
                target_tier="long_term",
                min_age_hours=self.config.short_term_to_long_term_hours,
                min_importance_score=0.6,
                min_access_count=2,
                priority=8
            ),
            
            # Clean up unimportant short-term memories
            ConsolidationRule(
                name="short_term_cleanup",
                trigger=ConsolidationTrigger.TIME_DECAY,
                action=ConsolidationAction.DELETE,
                source_tier="short_term",
                min_age_hours=self.config.short_term_cleanup_hours,
                max_importance_score=0.4,
                max_access_count=1,
                priority=4
            ),
            
            # Capacity-based cleanup
            ConsolidationRule(
                name="short_term_capacity_pressure",
                trigger=ConsolidationTrigger.CAPACITY_PRESSURE,
                action=ConsolidationAction.DEMOTE,
                source_tier="short_term",
                target_tier="long_term",
                capacity_threshold=self.config.capacity_warning_threshold,
                min_importance_score=0.5,
                priority=6
            )
        ])
        
        # Long-Term Memory Rules
        self.rules.extend([
            # Archive very old but important memories
            ConsolidationRule(
                name="long_term_archival",
                trigger=ConsolidationTrigger.TIME_DECAY,
                action=ConsolidationAction.ARCHIVE,
                source_tier="long_term",
                min_age_hours=self.config.long_term_cleanup_days * 24,
                min_importance_score=self.config.long_term_importance_threshold,
                priority=2
            ),
            
            # Clean up low-importance long-term memories
            ConsolidationRule(
                name="long_term_cleanup",
                trigger=ConsolidationTrigger.EXPLICIT_IMPORTANCE,
                action=ConsolidationAction.DELETE,
                source_tier="long_term",
                max_importance_score=self.config.min_importance_to_keep,
                min_age_hours=720,  # 30 days
                priority=1
            )
        ])
        
        # Cross-tier similarity merging
        self.rules.extend([
            ConsolidationRule(
                name="similarity_merge_working",
                trigger=ConsolidationTrigger.SEMANTIC_SIMILARITY,
                action=ConsolidationAction.MERGE,
                source_tier="working",
                priority=5
            ),
            
            ConsolidationRule(
                name="similarity_merge_short_term",
                trigger=ConsolidationTrigger.SEMANTIC_SIMILARITY,
                action=ConsolidationAction.MERGE,
                source_tier="short_term",
                priority=5
            )
        ])
    
    async def start_consolidation_service(self) -> None:
        """Start the background consolidation service."""
        if self._running:
            self.logger.warning("Consolidation service is already running")
            return
        
        self._running = True
        self._consolidation_task = asyncio.create_task(self._consolidation_loop())
        self.logger.info("Memory consolidation service started")
    
    async def stop_consolidation_service(self) -> None:
        """Stop the background consolidation service."""
        self._running = False
        
        if self._consolidation_task:
            self._consolidation_task.cancel()
            try:
                await self._consolidation_task
            except asyncio.CancelledError:
                pass
        
        # Complete any active plans
        for plan in list(self._active_plans.values()):
            if not plan.is_completed and not plan.is_failed:
                plan.failed_at = datetime.utcnow()
                plan.error_message = "Service shutdown"
        
        self.logger.info("Memory consolidation service stopped")
    
    async def _consolidation_loop(self) -> None:
        """Main consolidation loop."""
        self.logger.info("Starting consolidation loop")
        
        while self._running:
            try:
                # Generate consolidation plans
                plans = await self._generate_consolidation_plans()
                
                # Execute plans
                if plans:
                    await self._execute_consolidation_plans(plans)
                else:
                    self.logger.debug("No consolidation needed")
                
                # Cleanup completed plans
                await self._cleanup_completed_plans()
                
                # Update performance metrics
                self._last_consolidation = datetime.utcnow()
                
                # Wait for next interval
                interval_seconds = self.config.consolidation_interval_minutes * 60
                await asyncio.sleep(interval_seconds)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in consolidation loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
        
        self.logger.info("Consolidation loop stopped")
    
    async def _generate_consolidation_plans(self) -> List[ConsolidationPlan]:
        """Generate consolidation plans based on current state."""
        plans = []
        
        # Analyze each tier
        for tier_name in self.registry.tier_stores:
            try:
                tier_plan = await self._analyze_tier(tier_name)
                if tier_plan and tier_plan.actions:
                    plans.append(tier_plan)
            except Exception as e:
                self.logger.warning(f"Failed to analyze tier {tier_name}: {e}")
        
        # Sort plans by priority
        plans.sort(key=lambda p: p.priority, reverse=True)
        
        return plans
    
    async def _analyze_tier(self, tier_name: str) -> Optional[ConsolidationPlan]:
        """Analyze a specific tier and generate consolidation plan."""
        tier_adapter = self.registry.tier_stores[tier_name]
        
        # Get tier capacity information
        try:
            if hasattr(tier_adapter, 'get_capacity_info'):
                capacity_info = await tier_adapter.get_capacity_info()
                usage_ratio = capacity_info.get('usage_ratio', 0.0)
            else:
                usage_ratio = 0.5  # Default assumption
        except Exception as e:
            self.logger.warning(f"Could not get capacity info for {tier_name}: {e}")
            usage_ratio = 0.5
        
        # Query tier for consolidation candidates
        query = MemoryQuery(
            namespace="*",  # All namespaces
            limit=self.config.max_batch_size,
            similarity_threshold=0.0  # Get all records
        )
        
        try:
            candidates = await tier_adapter.retrieve_memories(query)
        except Exception as e:
            self.logger.warning(f"Could not retrieve memories from {tier_name}: {e}")
            return None
        
        if not candidates:
            return None
        
        # Apply consolidation rules
        plan_actions = []
        rules_for_tier = [r for r in self.rules if r.source_tier == tier_name]
        
        for rule in sorted(rules_for_tier, key=lambda r: r.priority, reverse=True):
            matching_records = []
            
            for record in candidates:
                if rule.matches_record(record, usage_ratio):
                    matching_records.append(record)
            
            if matching_records:
                # Limit batch size
                matching_records = matching_records[:rule.batch_size]
                plan_actions.append((rule, matching_records))
        
        if not plan_actions:
            return None
        
        # Create consolidation plan
        plan = ConsolidationPlan(
            plan_id=f"{tier_name}_{int(time.time())}",
            actions=plan_actions,
            estimated_records_moved=sum(len(records) for _, records in plan_actions),
            priority=max(rule.priority for rule, _ in plan_actions)
        )
        
        # Estimate duration
        plan.estimated_duration = plan.estimated_records_moved / self.config.records_per_second_limit
        
        return plan
    
    async def _execute_consolidation_plans(self, plans: List[ConsolidationPlan]) -> None:
        """Execute consolidation plans."""
        # Limit concurrent executions
        available_slots = self.config.max_concurrent_plans - len(self._active_plans)
        plans_to_execute = plans[:available_slots]
        
        # Queue remaining plans
        for plan in plans[available_slots:]:
            self._plan_queue.append(plan)
        
        # Execute plans
        tasks = []
        for plan in plans_to_execute:
            self._active_plans[plan.plan_id] = plan
            task = asyncio.create_task(self._execute_consolidation_plan(plan))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_consolidation_plan(self, plan: ConsolidationPlan) -> None:
        """Execute a single consolidation plan."""
        plan.started_at = datetime.utcnow()
        
        try:
            self.logger.info(
                f"Executing consolidation plan {plan.plan_id} "
                f"with {len(plan.actions)} actions"
            )
            
            for rule, records in plan.actions:
                await self._execute_consolidation_action(rule, records)
                
                # Track rule performance
                perf = self._rule_performance[rule.name]
                perf["executions"] += 1
                perf["records_processed"] += len(records)
            
            plan.completed_at = datetime.utcnow()
            
            self._consolidations_performed += 1
            self._records_consolidated += plan.estimated_records_moved
            
            if plan.duration:
                self._total_consolidation_time += plan.duration
            
            self.logger.info(
                f"Completed consolidation plan {plan.plan_id} "
                f"in {plan.duration:.2f}s"
            )
        
        except Exception as e:
            plan.failed_at = datetime.utcnow()
            plan.error_message = str(e)
            
            # Update rule failure counts
            for rule, _ in plan.actions:
                perf = self._rule_performance[rule.name]
                perf["failures"] += 1
                perf["success_rate"] = (perf["executions"] - perf["failures"]) / perf["executions"]
            
            self.logger.error(f"Consolidation plan {plan.plan_id} failed: {e}")
        
        finally:
            # Remove from active plans
            if plan.plan_id in self._active_plans:
                del self._active_plans[plan.plan_id]
    
    async def _execute_consolidation_action(
        self, 
        rule: ConsolidationRule, 
        records: List[RecordEnvelope]
    ) -> None:
        """Execute a specific consolidation action."""
        action_start = time.time()
        
        try:
            if rule.action == ConsolidationAction.PROMOTE:
                await self._promote_records(rule.source_tier, rule.target_tier, records)
            
            elif rule.action == ConsolidationAction.DEMOTE:
                await self._demote_records(rule.source_tier, rule.target_tier, records)
            
            elif rule.action == ConsolidationAction.REPLICATE:
                await self._replicate_records(rule.source_tier, rule.target_tier, records)
            
            elif rule.action == ConsolidationAction.ARCHIVE:
                await self._archive_records(rule.source_tier, records)
            
            elif rule.action == ConsolidationAction.DELETE:
                await self._delete_records(rule.source_tier, records)
            
            elif rule.action == ConsolidationAction.MERGE:
                await self._merge_similar_records(rule.source_tier, records)
            
            # Update performance tracking
            action_duration = time.time() - action_start
            perf = self._rule_performance[rule.name]
            perf["total_time"] += action_duration
            
            if self.config.log_consolidation_actions:
                self.logger.info(
                    f"Executed {rule.action.value} action for rule {rule.name}: "
                    f"{len(records)} records in {action_duration:.2f}s"
                )
        
        except Exception as e:
            self._mark_error(e)
            raise ConsolidationError(
                f"Failed to execute {rule.action.value} action: {e}",
                rule_name=rule.name,
                record_count=len(records),
                backend_error=e
            )
    
    async def _promote_records(
        self, 
        source_tier: str, 
        target_tier: Optional[str], 
        records: List[RecordEnvelope]
    ) -> None:
        """Promote records to a higher-priority tier."""
        if not target_tier:
            raise ConsolidationError("Target tier required for promotion")
        
        source_adapter = self.registry.tier_stores.get(source_tier)
        target_adapter = self.registry.tier_stores.get(target_tier)
        
        if not source_adapter or not target_adapter:
            raise ConsolidationError(f"Tier adapters not found: {source_tier} -> {target_tier}")
        
        # Rate limiting
        await self._consolidation_rate_limiter.acquire()
        
        try:
            for record in records:
                # Update metadata to indicate promotion
                record.metadata["promoted_from"] = source_tier
                record.metadata["promoted_at"] = datetime.utcnow().isoformat()
                
                # Store in target tier
                await target_adapter.store_memory(record)
                
                # Remove from source tier
                await source_adapter.delete_memory(record.record_id, record.tenant_id)
        
        finally:
            self._consolidation_rate_limiter.release()
    
    async def _demote_records(
        self, 
        source_tier: str, 
        target_tier: Optional[str], 
        records: List[RecordEnvelope]
    ) -> None:
        """Demote records to a lower-priority tier."""
        if not target_tier:
            raise ConsolidationError("Target tier required for demotion")
        
        source_adapter = self.registry.tier_stores.get(source_tier)
        target_adapter = self.registry.tier_stores.get(target_tier)
        
        if not source_adapter or not target_adapter:
            raise ConsolidationError(f"Tier adapters not found: {source_tier} -> {target_tier}")
        
        await self._consolidation_rate_limiter.acquire()
        
        try:
            for record in records:
                # Update metadata to indicate demotion
                record.metadata["demoted_from"] = source_tier
                record.metadata["demoted_at"] = datetime.utcnow().isoformat()
                
                # Reduce importance score for demoted records
                current_importance = record.metadata.get("importance_score", 0.5)
                record.metadata["importance_score"] = max(0.1, current_importance * 0.8)
                
                # Store in target tier
                await target_adapter.store_memory(record)
                
                # Remove from source tier
                await source_adapter.delete_memory(record.record_id, record.tenant_id)
        
        finally:
            self._consolidation_rate_limiter.release()
    
    async def _replicate_records(
        self, 
        source_tier: str, 
        target_tier: Optional[str], 
        records: List[RecordEnvelope]
    ) -> None:
        """Replicate records to another tier (copy, don't move)."""
        if not target_tier:
            raise ConsolidationError("Target tier required for replication")
        
        target_adapter = self.registry.tier_stores.get(target_tier)
        
        if not target_adapter:
            raise ConsolidationError(f"Target tier adapter not found: {target_tier}")
        
        await self._consolidation_rate_limiter.acquire()
        
        try:
            for record in records:
                # Update metadata to indicate replication
                record.metadata["replicated_from"] = source_tier
                record.metadata["replicated_at"] = datetime.utcnow().isoformat()
                
                # Store copy in target tier
                await target_adapter.store_memory(record)
        
        finally:
            self._consolidation_rate_limiter.release()
    
    async def _archive_records(self, source_tier: str, records: List[RecordEnvelope]) -> None:
        """Archive records (move to long-term storage)."""
        # For now, archiving means moving to long_term tier
        # In a production system, this might involve external storage
        target_tier = "long_term"
        
        if target_tier == source_tier:
            # Already in long-term, just mark as archived
            source_adapter = self.registry.tier_stores.get(source_tier)
            if source_adapter:
                for record in records:
                    record.metadata["archived"] = True
                    record.metadata["archived_at"] = datetime.utcnow().isoformat()
                    await source_adapter.store_memory(record)  # Update in place
        else:
            await self._promote_records(source_tier, target_tier, records)
    
    async def _delete_records(self, source_tier: str, records: List[RecordEnvelope]) -> None:
        """Delete records from the system."""
        source_adapter = self.registry.tier_stores.get(source_tier)
        
        if not source_adapter:
            raise ConsolidationError(f"Source tier adapter not found: {source_tier}")
        
        await self._consolidation_rate_limiter.acquire()
        
        try:
            for record in records:
                await source_adapter.delete_memory(record.record_id, record.tenant_id)
        
        finally:
            self._consolidation_rate_limiter.release()
    
    async def _merge_similar_records(self, source_tier: str, records: List[RecordEnvelope]) -> None:
        """Merge similar records within a tier."""
        if len(records) < 2:
            return
        
        source_adapter = self.registry.tier_stores.get(source_tier)
        if not source_adapter:
            return
        
        # Group records by similarity
        similarity_groups = self._group_by_similarity(records)
        
        await self._consolidation_rate_limiter.acquire()
        
        try:
            for group in similarity_groups:
                if len(group) >= 2:
                    # Merge group into a single record
                    merged_record = await self._merge_record_group(group)
                    
                    # Store merged record
                    await source_adapter.store_memory(merged_record)
                    
                    # Delete original records (except the first one which becomes the merged record)
                    for record in group[1:]:
                        await source_adapter.delete_memory(record.record_id, record.tenant_id)
        
        finally:
            self._consolidation_rate_limiter.release()
    
    def _group_by_similarity(
        self, 
        records: List[RecordEnvelope]
    ) -> List[List[RecordEnvelope]]:
        """Group records by similarity."""
        if not records:
            return []
        
        # Simple grouping by content similarity (can be enhanced)
        groups = []
        unprocessed = records.copy()
        
        while unprocessed:
            # Start new group with first unprocessed record
            current_group = [unprocessed.pop(0)]
            
            # Find similar records
            to_remove = []
            for i, record in enumerate(unprocessed):
                if self._are_records_similar(current_group[0], record):
                    current_group.append(record)
                    to_remove.append(i)
            
            # Remove processed records
            for i in reversed(to_remove):
                unprocessed.pop(i)
            
            groups.append(current_group)
        
        return groups
    
    def _are_records_similar(self, record1: RecordEnvelope, record2: RecordEnvelope) -> bool:
        """Check if two records are similar enough to merge."""
        # Check namespace and type
        if record1.namespace != record2.namespace:
            return False
        
        # Check content similarity (simple text comparison for now)
        content1 = str(record1.content).lower()
        content2 = str(record2.content).lower()
        
        # Simple Jaccard similarity
        words1 = set(content1.split())
        words2 = set(content2.split())
        
        if not words1 or not words2:
            return False
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        jaccard_similarity = intersection / union if union > 0 else 0
        
        return jaccard_similarity >= self.config.similarity_merge_threshold
    
    async def _merge_record_group(self, group: List[RecordEnvelope]) -> RecordEnvelope:
        """Merge a group of similar records into one."""
        if not group:
            raise ConsolidationError("Cannot merge empty group")
        
        # Use the record with highest importance as base
        base_record = max(
            group, 
            key=lambda r: r.metadata.get("importance_score", 0.5)
        )
        
        # Merge content (combine unique information)
        merged_content = base_record.content
        
        # Merge metadata
        merged_metadata = base_record.metadata.copy()
        
        # Combine access counts
        total_access_count = sum(
            r.metadata.get("access_count", 0) for r in group
        )
        merged_metadata["access_count"] = total_access_count
        
        # Take highest importance score
        max_importance = max(
            r.metadata.get("importance_score", 0.5) for r in group
        )
        merged_metadata["importance_score"] = max_importance
        
        # Track merge history
        merged_metadata["merged_from"] = [r.record_id for r in group[1:]]
        merged_metadata["merged_at"] = datetime.utcnow().isoformat()
        merged_metadata["merge_count"] = len(group)
        
        # Create merged record
        merged_record = RecordEnvelope(
            record_id=base_record.record_id,
            tenant_id=base_record.tenant_id,
            namespace=base_record.namespace,
            content=merged_content,
            embedding=base_record.embedding,
            metadata=merged_metadata,
            created_at=min(r.created_at for r in group if r.created_at),
            updated_at=datetime.utcnow()
        )
        
        return merged_record
    
    async def _cleanup_completed_plans(self) -> None:
        """Clean up completed and failed plans."""
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        to_remove = []
        for plan_id, plan in self._active_plans.items():
            if ((plan.is_completed or plan.is_failed) and 
                plan.completed_at and plan.completed_at < cutoff_time):
                to_remove.append(plan_id)
        
        for plan_id in to_remove:
            del self._active_plans[plan_id]
    
    def add_consolidation_rule(self, rule: ConsolidationRule) -> None:
        """Add a custom consolidation rule."""
        self.rules.append(rule)
        self.logger.info(f"Added consolidation rule: {rule.name}")
    
    def remove_consolidation_rule(self, rule_name: str) -> bool:
        """Remove a consolidation rule by name."""
        original_count = len(self.rules)
        self.rules = [r for r in self.rules if r.name != rule_name]
        removed = len(self.rules) < original_count
        
        if removed:
            self.logger.info(f"Removed consolidation rule: {rule_name}")
        
        return removed
    
    def get_consolidation_rules(self) -> List[ConsolidationRule]:
        """Get all consolidation rules."""
        return self.rules.copy()
    
    async def force_consolidation(self, tier_name: Optional[str] = None) -> Dict[str, Any]:
        """Force immediate consolidation for a specific tier or all tiers."""
        self.logger.info(f"Forcing consolidation for tier: {tier_name or 'all'}")
        
        start_time = time.time()
        
        if tier_name:
            # Consolidate specific tier
            plans = []
            if tier_name in self.registry.tier_stores:
                plan = await self._analyze_tier(tier_name)
                if plan:
                    plans.append(plan)
        else:
            # Consolidate all tiers
            plans = await self._generate_consolidation_plans()
        
        if plans:
            await self._execute_consolidation_plans(plans)
        
        duration = time.time() - start_time
        
        return {
            "plans_executed": len(plans),
            "records_processed": sum(p.estimated_records_moved for p in plans),
            "duration": duration,
            "tier": tier_name or "all"
        }
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform consolidation engine health check."""
        return {
            "service_running": self._running,
            "active_plans": len(self._active_plans),
            "queued_plans": len(self._plan_queue),
            "consolidation_rules": len(self.rules),
            "consolidations_performed": self._consolidations_performed,
            "records_consolidated": self._records_consolidated,
            "average_consolidation_time": (
                self._total_consolidation_time / max(1, self._consolidations_performed)
            ),
            "last_consolidation": (
                self._last_consolidation.isoformat() if self._last_consolidation else None
            )
        }
    
    async def get_consolidation_stats(self) -> Dict[str, Any]:
        """Get detailed consolidation statistics."""
        base_stats = await self.get_stats()
        
        # Rule performance statistics
        rule_stats = {}
        for rule_name, perf in self._rule_performance.items():
            rule_stats[rule_name] = {
                "executions": perf["executions"],
                "records_processed": perf["records_processed"],
                "average_time": (
                    perf["total_time"] / max(1, perf["executions"])
                ),
                "success_rate": perf["success_rate"],
                "failures": perf["failures"]
            }
        
        consolidation_stats = {
            "service_running": self._running,
            "consolidations_performed": self._consolidations_performed,
            "records_consolidated": self._records_consolidated,
            "total_consolidation_time": self._total_consolidation_time,
            "average_consolidation_time": (
                self._total_consolidation_time / max(1, self._consolidations_performed)
            ),
            "active_plans": len(self._active_plans),
            "queued_plans": len(self._plan_queue),
            "consolidation_rules": len(self.rules),
            "rule_performance": rule_stats,
            "last_consolidation": (
                self._last_consolidation.isoformat() if self._last_consolidation else None
            ),
            "config": {
                "consolidation_interval_minutes": self.config.consolidation_interval_minutes,
                "max_concurrent_plans": self.config.max_concurrent_plans,
                "records_per_second_limit": self.config.records_per_second_limit,
                "enable_default_rules": self.config.enable_default_rules
            }
        }
        
        base_stats.update(consolidation_stats)
        return base_stats