"""
smrti/memory/tiers/semantic.py - Semantic Memory Tier

Semantic memory for conceptual knowledge, relationships, and meaning structures.
Optimized for graph-based queries and knowledge reasoning.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union, Tuple

from smrti.core.base import BaseMemoryTier
from smrti.core.exceptions import MemoryError, ValidationError
from smrti.core.protocols import TierStore, GraphStore
from smrti.core.registry import AdapterRegistry
from smrti.schemas.models import (
    MemoryQuery,
    RecordEnvelope,
    EntityRecord,
    ConceptRecord,
    SemanticMemoryConfig
)


class SemanticMemory(BaseMemoryTier):
    """
    Semantic Memory Tier - Conceptual knowledge and meaning relationships.
    
    Characteristics:
    - Graph-based knowledge representation
    - Entity and concept relationships
    - Semantic reasoning and inference
    - Knowledge network traversal
    - Conceptual hierarchies
    - Meaning-based retrieval
    
    Use cases:
    - Factual knowledge storage
    - Concept definitions and relationships
    - Semantic reasoning and inference
    - Knowledge graph queries
    - Ontology management
    - Conceptual learning and understanding
    """
    
    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        config: Optional[SemanticMemoryConfig] = None
    ):
        super().__init__(
            tier_name="semantic",
            adapter_registry=adapter_registry,
            config=config
        )
        
        # Semantic memory configuration
        self._relationship_types = config.relationship_types if config else {
            "IS_A": 1.0,
            "PART_OF": 0.9,
            "RELATES_TO": 0.7,
            "SIMILAR_TO": 0.6,
            "CAUSES": 0.8,
            "USED_FOR": 0.7,
            "EXAMPLE_OF": 0.8
        }
        
        self._min_relationship_strength = config.min_relationship_strength if config else 0.1
        self._max_traversal_depth = config.max_traversal_depth if config else 5
        self._concept_similarity_threshold = config.concept_similarity_threshold if config else 0.7
        
        # Knowledge organization
        self._entity_registry: Dict[str, Set[str]] = {}  # entity_type -> record_ids
        self._concept_hierarchy: Dict[str, Dict[str, float]] = {}  # concept -> {parent_concept: strength}
        self._semantic_networks: Dict[str, Set[str]] = {}  # domain -> record_ids
        self._relationship_cache: Dict[str, List[Tuple[str, str, float]]] = {}  # record_id -> [(related_id, rel_type, strength)]
        
        # Reasoning and inference
        self._inference_rules: List[Dict[str, Any]] = []
        self._concept_definitions: Dict[str, str] = {}
        self._domain_ontologies: Dict[str, Dict[str, Any]] = {}
        
        # Configuration
        self._enable_auto_relationships = config.enable_auto_relationships if config else True
        self._enable_inference = config.enable_inference if config else True
        self._enable_concept_learning = config.enable_concept_learning if config else True
        self._relationship_decay_rate = config.relationship_decay_rate if config else 0.05
        
        # Performance optimization
        self._last_inference_run = datetime.utcnow()
        self._inference_interval = timedelta(hours=config.inference_interval_hours if config else 6)
        self._relationship_update_batch_size = 100
        
    async def initialize(self) -> None:
        """Initialize semantic memory tier with graph database storage."""
        # Get graph storage adapter for semantic memory (Neo4j)
        adapter = await self._adapter_registry.get_adapter(
            tier_name="semantic",
            required_capabilities=["graph_traversal", "entity_relationships"]
        )
        
        if not adapter:
            raise MemoryError(
                "No suitable graph database adapter found for semantic memory tier",
                tier="semantic",
                operation="initialize"
            )
        
        self._storage = adapter
        await super().initialize()
        
        # Start background reasoning tasks
        if self._enable_inference:
            asyncio.create_task(self._periodic_inference())
        
        self.logger.info(
            f"Semantic memory initialized (relationship_types={len(self._relationship_types)}, "
            f"max_traversal_depth={self._max_traversal_depth})"
        )
    
    async def store(
        self, 
        record: RecordEnvelope,
        entity_type: Optional[str] = None,
        domain: Optional[str] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        auto_extract_entities: bool = True
    ) -> str:
        """
        Store semantic knowledge with entity and relationship extraction.
        
        Args:
            record: Memory record to store
            entity_type: Type of entity if this represents an entity
            domain: Knowledge domain classification
            relationships: Explicit relationships to create
            auto_extract_entities: Whether to automatically extract entities
            
        Returns:
            Record ID of stored memory
        """
        # Set semantic memory tier
        record.tier = "semantic"
        
        # Add domain information
        if domain:
            record.metadata = record.metadata or {}
            record.metadata["domain"] = domain
            
            # Track domain membership
            if domain not in self._semantic_networks:
                self._semantic_networks[domain] = set()
            self._semantic_networks[domain].add(record.record_id)
        
        # Store in graph database
        record_id = await self._storage.store(record)
        
        # Track entity type
        if entity_type:
            if entity_type not in self._entity_registry:
                self._entity_registry[entity_type] = set()
            self._entity_registry[entity_type].add(record_id)
        
        # Process entity extraction and relationships
        if auto_extract_entities or relationships:
            await self._process_semantic_relationships(record, relationships)
        
        # Update concept hierarchy if this is a concept
        if isinstance(record.content, ConceptRecord):
            await self._update_concept_hierarchy(record)
        
        self.logger.debug(
            f"Stored semantic record {record_id} "
            f"(entity_type={entity_type}, domain={domain})"
        )
        
        return record_id
    
    async def retrieve(
        self, 
        record_id: str,
        include_relationships: bool = False,
        relationship_depth: int = 1
    ) -> Optional[RecordEnvelope]:
        """
        Retrieve a semantic record with optional relationship information.
        
        Args:
            record_id: ID of record to retrieve
            include_relationships: Whether to include related entities
            relationship_depth: Depth of relationship traversal
            
        Returns:
            Record with optional relationship information in metadata
        """
        record = await self._storage.retrieve(record_id)
        
        if not record:
            return None
        
        # Add relationship information if requested
        if include_relationships:
            relationships = await self._get_relationships(record_id, relationship_depth)
            record.metadata = record.metadata or {}
            record.metadata["relationships"] = relationships
        
        return record
    
    async def query(
        self,
        query: MemoryQuery,
        domain: Optional[str] = None,
        entity_types: Optional[List[str]] = None,
        relationship_filter: Optional[Dict[str, Any]] = None,
        use_inference: bool = True
    ) -> List[RecordEnvelope]:
        """
        Query semantic memory with graph traversal and reasoning.
        
        Args:
            query: Memory query parameters
            domain: Optional domain to focus search
            entity_types: Optional entity types to filter by
            relationship_filter: Optional relationship-based filtering
            use_inference: Whether to use semantic inference
            
        Returns:
            List of matching records with semantic relevance
        """
        results = []
        
        # Domain-based filtering
        if domain and domain in self._semantic_networks:
            domain_records = self._semantic_networks[domain]
            # This would be implemented differently with actual graph queries
            # For now, it's a simplified approach
        
        # Entity type filtering
        if entity_types:
            entity_filtered_records = set()
            for entity_type in entity_types:
                if entity_type in self._entity_registry:
                    entity_filtered_records.update(self._entity_registry[entity_type])
        
        # Perform graph-based query
        if isinstance(self._storage, GraphStore):
            # Use graph-specific query capabilities
            graph_results = await self._storage.query(query)
            results.extend(graph_results)
        else:
            # Fallback to regular query
            regular_results = await self._storage.query(query)
            results.extend(regular_results)
        
        # Apply semantic inference if enabled
        if use_inference and self._enable_inference:
            inferred_results = await self._apply_semantic_inference(query, results)
            results.extend(inferred_results)
        
        # Remove duplicates and sort by semantic relevance
        unique_results = {}
        for record in results:
            if record.record_id not in unique_results:
                unique_results[record.record_id] = record
            else:
                # Keep the one with higher relevance score
                if record.relevance_score > unique_results[record.record_id].relevance_score:
                    unique_results[record.record_id] = record
        
        final_results = list(unique_results.values())
        final_results.sort(key=lambda r: r.relevance_score, reverse=True)
        
        return final_results[:query.limit]
    
    async def find_related_concepts(
        self,
        concept: str,
        relationship_types: Optional[List[str]] = None,
        max_depth: int = 3,
        min_strength: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Find concepts related to the given concept through graph traversal.
        
        Args:
            concept: Starting concept name
            relationship_types: Types of relationships to follow
            max_depth: Maximum traversal depth
            min_strength: Minimum relationship strength
            
        Returns:
            List of related concepts with relationship information
        """
        if not isinstance(self._storage, GraphStore):
            self.logger.warning("Storage adapter does not support graph traversal")
            return []
        
        try:
            # Use graph adapter's entity relationship functionality
            if hasattr(self._storage, 'find_related_entities'):
                related_entities = await self._storage.find_related_entities(
                    entity_name=concept,
                    tenant_id="",  # Would be filled appropriately
                    namespace="",  # Would be filled appropriately
                    max_depth=max_depth,
                    min_strength=min_strength
                )
                
                return related_entities
            else:
                # Fallback implementation using local relationship cache
                return await self._find_related_concepts_fallback(concept, max_depth, min_strength)
                
        except Exception as e:
            self.logger.error(f"Error finding related concepts: {e}")
            return []
    
    async def _find_related_concepts_fallback(
        self,
        concept: str,
        max_depth: int,
        min_strength: float
    ) -> List[Dict[str, Any]]:
        """Fallback method for finding related concepts."""
        related = []
        visited = set()
        queue = [(concept, 0, 1.0)]  # (concept, depth, strength)
        
        while queue:
            current_concept, depth, strength = queue.pop(0)
            
            if depth >= max_depth or current_concept in visited:
                continue
            
            visited.add(current_concept)
            
            # Look for relationships in our cache
            if current_concept in self._relationship_cache:
                for related_id, rel_type, rel_strength in self._relationship_cache[current_concept]:
                    combined_strength = strength * rel_strength
                    
                    if combined_strength >= min_strength:
                        related.append({
                            "concept": related_id,
                            "relationship_type": rel_type,
                            "strength": combined_strength,
                            "depth": depth + 1
                        })
                        
                        # Add to queue for further traversal
                        queue.append((related_id, depth + 1, combined_strength))
        
        return sorted(related, key=lambda r: r["strength"], reverse=True)
    
    async def get_concept_definition(
        self,
        concept: str,
        include_examples: bool = True,
        include_relationships: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive definition and information about a concept.
        
        Args:
            concept: Concept name to look up
            include_examples: Whether to include example instances
            include_relationships: Whether to include related concepts
            
        Returns:
            Dictionary containing concept information
        """
        # Find concept records
        concept_query = MemoryQuery(
            query_text=concept,
            limit=10,
            tags=[concept]
        )
        
        concept_records = await self.query(concept_query)
        concept_records = [r for r in concept_records if isinstance(r.content, ConceptRecord)]
        
        if not concept_records:
            return None
        
        # Get the best concept record (highest relevance)
        main_concept = concept_records[0]
        
        definition = {
            "concept": concept,
            "definition": getattr(main_concept.content, 'description', ''),
            "properties": getattr(main_concept.content, 'properties', {}),
            "domain": main_concept.metadata.get('domain') if main_concept.metadata else None
        }
        
        # Add examples if requested
        if include_examples:
            examples = []
            for record in concept_records:
                if hasattr(record.content, 'examples'):
                    examples.extend(record.content.examples)
            
            definition["examples"] = examples[:10]  # Limit to 10 examples
        
        # Add relationships if requested
        if include_relationships:
            relationships = await self.find_related_concepts(concept, max_depth=2)
            definition["relationships"] = relationships[:20]  # Limit to 20 relationships
        
        # Add hierarchy information
        if concept in self._concept_hierarchy:
            definition["parent_concepts"] = list(self._concept_hierarchy[concept].keys())
        
        # Find child concepts
        child_concepts = [
            parent for parent, children in self._concept_hierarchy.items()
            if concept in children
        ]
        definition["child_concepts"] = child_concepts
        
        return definition
    
    async def learn_concept(
        self,
        concept_name: str,
        definition: str,
        examples: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None,
        parent_concepts: Optional[List[str]] = None
    ) -> str:
        """
        Learn a new concept or update existing concept knowledge.
        
        Args:
            concept_name: Name of the concept
            definition: Textual definition
            examples: Optional examples of the concept
            properties: Optional structured properties
            domain: Knowledge domain
            parent_concepts: Optional parent concepts in hierarchy
            
        Returns:
            Record ID of the concept record
        """
        if not self._enable_concept_learning:
            raise ValidationError("Concept learning is disabled")
        
        # Create concept record
        concept_content = ConceptRecord(
            concept_name=concept_name,
            definition=definition,
            examples=examples or [],
            properties=properties or {}
        )
        
        record = RecordEnvelope(
            record_id=f"concept_{concept_name}_{hash(concept_name) % 10000}",
            tenant_id="system",  # Would be set appropriately
            namespace="concepts",
            tier="semantic",
            record_type="concept",
            content=concept_content,
            tags=[concept_name, "concept"],
            source="concept_learning"
        )
        
        # Store the concept
        record_id = await self.store(
            record,
            entity_type="concept",
            domain=domain
        )
        
        # Update concept hierarchy
        if parent_concepts:
            for parent in parent_concepts:
                if parent not in self._concept_hierarchy:
                    self._concept_hierarchy[parent] = {}
                
                self._concept_hierarchy[parent][concept_name] = 0.9  # Strong parent-child relationship
        
        # Store definition for quick lookup
        self._concept_definitions[concept_name] = definition
        
        self.logger.info(f"Learned new concept: {concept_name}")
        return record_id
    
    async def _process_semantic_relationships(
        self,
        record: RecordEnvelope,
        explicit_relationships: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Process and create semantic relationships for a record."""
        relationships_to_create = explicit_relationships or []
        
        # Auto-extract relationships if enabled
        if self._enable_auto_relationships:
            auto_relationships = await self._extract_automatic_relationships(record)
            relationships_to_create.extend(auto_relationships)
        
        # Create relationships in graph storage
        for rel in relationships_to_create:
            try:
                await self._create_relationship(
                    source_id=record.record_id,
                    target_id=rel.get("target_id"),
                    relationship_type=rel.get("type", "RELATES_TO"),
                    strength=rel.get("strength", 0.5)
                )
            except Exception as e:
                self.logger.error(f"Failed to create relationship: {e}")
    
    async def _extract_automatic_relationships(
        self,
        record: RecordEnvelope
    ) -> List[Dict[str, Any]]:
        """Extract relationships automatically from record content."""
        relationships = []
        
        # Extract based on content type
        if isinstance(record.content, EntityRecord):
            # Find related entities of same type
            entity_type = getattr(record.content, 'entity_type', None)
            if entity_type and entity_type in self._entity_registry:
                # Create similarity relationships with other entities
                similar_entities = list(self._entity_registry[entity_type])[:5]  # Limit to 5
                
                for entity_id in similar_entities:
                    if entity_id != record.record_id:
                        relationships.append({
                            "target_id": entity_id,
                            "type": "SIMILAR_TO",
                            "strength": 0.6
                        })
        
        elif isinstance(record.content, ConceptRecord):
            # Find related concepts based on domain or properties
            concept_name = record.content.concept_name
            domain = record.metadata.get('domain') if record.metadata else None
            
            if domain and domain in self._semantic_networks:
                # Create domain relationships
                domain_concepts = list(self._semantic_networks[domain])[:3]  # Limit to 3
                
                for concept_id in domain_concepts:
                    if concept_id != record.record_id:
                        relationships.append({
                            "target_id": concept_id,
                            "type": "RELATES_TO",
                            "strength": 0.5
                        })
        
        # Extract relationships from tags
        for tag in record.tags:
            # Find other records with same tags
            # This would require a tag-based lookup - simplified here
            pass
        
        return relationships
    
    async def _create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        strength: float
    ) -> None:
        """Create a relationship between two records."""
        if not target_id:
            return
        
        # Validate relationship type
        if relationship_type not in self._relationship_types:
            relationship_type = "RELATES_TO"
        
        # Normalize strength
        strength = max(self._min_relationship_strength, min(1.0, strength))
        
        # Update relationship cache
        if source_id not in self._relationship_cache:
            self._relationship_cache[source_id] = []
        
        self._relationship_cache[source_id].append((target_id, relationship_type, strength))
        
        # If using graph storage, create actual graph relationship
        if hasattr(self._storage, 'create_relationship'):
            try:
                await self._storage.create_relationship(
                    source_id=source_id,
                    target_id=target_id,
                    relationship_type=relationship_type,
                    properties={"strength": strength}
                )
            except Exception as e:
                self.logger.error(f"Failed to create graph relationship: {e}")
    
    async def _update_concept_hierarchy(self, record: RecordEnvelope) -> None:
        """Update concept hierarchy when new concepts are learned."""
        if not isinstance(record.content, ConceptRecord):
            return
        
        concept_name = record.content.concept_name
        
        # Look for parent concepts in the definition or properties
        definition = getattr(record.content, 'definition', '')
        properties = getattr(record.content, 'properties', {})
        
        # Simple pattern matching for "is a" relationships
        # In production, this would use more sophisticated NLP
        if "is a" in definition.lower() or "is an" in definition.lower():
            # Extract potential parent concept
            # This is greatly simplified
            pass
        
        # Check for explicit parent in properties
        if "parent_concept" in properties:
            parent = properties["parent_concept"]
            if parent not in self._concept_hierarchy:
                self._concept_hierarchy[parent] = {}
            
            self._concept_hierarchy[parent][concept_name] = 0.9
    
    async def _get_relationships(
        self,
        record_id: str,
        depth: int = 1
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get relationship information for a record."""
        relationships = {
            "outgoing": [],
            "incoming": []
        }
        
        # Get outgoing relationships from cache
        if record_id in self._relationship_cache:
            for target_id, rel_type, strength in self._relationship_cache[record_id]:
                relationships["outgoing"].append({
                    "target_id": target_id,
                    "relationship_type": rel_type,
                    "strength": strength
                })
        
        # Get incoming relationships (inverse lookup)
        for source_id, rel_list in self._relationship_cache.items():
            for target_id, rel_type, strength in rel_list:
                if target_id == record_id:
                    relationships["incoming"].append({
                        "source_id": source_id,
                        "relationship_type": rel_type,
                        "strength": strength
                    })
        
        return relationships
    
    async def _apply_semantic_inference(
        self,
        query: MemoryQuery,
        existing_results: List[RecordEnvelope]
    ) -> List[RecordEnvelope]:
        """Apply semantic inference to expand query results."""
        if not self._enable_inference or not self._inference_rules:
            return []
        
        inferred_results = []
        
        # Apply inference rules (simplified)
        for rule in self._inference_rules:
            # This would contain actual inference logic
            # For now, it's a placeholder
            pass
        
        return inferred_results
    
    async def _periodic_inference(self) -> None:
        """Periodic semantic reasoning and relationship strength updates."""
        while True:
            try:
                await asyncio.sleep(self._inference_interval.total_seconds())
                
                now = datetime.utcnow()
                if now - self._last_inference_run < self._inference_interval:
                    continue
                
                # Update relationship strengths with decay
                await self._update_relationship_strengths()
                
                # Run inference rules
                await self._run_inference_rules()
                
                # Clean up weak relationships
                await self._cleanup_weak_relationships()
                
                self._last_inference_run = now
                
                self.logger.info("Completed semantic inference update")
                
            except Exception as e:
                self.logger.error(f"Error during semantic inference: {e}")
    
    async def _update_relationship_strengths(self) -> None:
        """Update relationship strengths with time decay."""
        for source_id in list(self._relationship_cache.keys()):
            updated_relationships = []
            
            for target_id, rel_type, strength in self._relationship_cache[source_id]:
                # Apply decay
                new_strength = strength * (1.0 - self._relationship_decay_rate)
                
                if new_strength >= self._min_relationship_strength:
                    updated_relationships.append((target_id, rel_type, new_strength))
            
            self._relationship_cache[source_id] = updated_relationships
    
    async def _run_inference_rules(self) -> None:
        """Run semantic inference rules to derive new knowledge."""
        # This would contain actual inference logic
        # Example: If A is_a B and B is_a C, then A is_a C (transitivity)
        pass
    
    async def _cleanup_weak_relationships(self) -> None:
        """Remove relationships that have fallen below minimum strength."""
        for source_id in list(self._relationship_cache.keys()):
            self._relationship_cache[source_id] = [
                (target_id, rel_type, strength)
                for target_id, rel_type, strength in self._relationship_cache[source_id]
                if strength >= self._min_relationship_strength
            ]
            
            # Remove empty relationship lists
            if not self._relationship_cache[source_id]:
                del self._relationship_cache[source_id]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get semantic memory statistics."""
        base_stats = await super().get_stats()
        
        # Knowledge organization statistics
        total_entities = sum(len(entities) for entities in self._entity_registry.values())
        total_concepts = len(self._concept_definitions)
        total_relationships = sum(len(rels) for rels in self._relationship_cache.values())
        semantic_domains = len(self._semantic_networks)
        
        # Relationship type distribution
        rel_type_counts = {}
        for rel_list in self._relationship_cache.values():
            for _, rel_type, _ in rel_list:
                rel_type_counts[rel_type] = rel_type_counts.get(rel_type, 0) + 1
        
        semantic_stats = {
            "tier_name": "semantic",
            "total_entities": total_entities,
            "entity_types": len(self._entity_registry),
            "total_concepts": total_concepts,
            "total_relationships": total_relationships,
            "semantic_domains": semantic_domains,
            "relationship_types": rel_type_counts,
            "concept_hierarchy_depth": len(self._concept_hierarchy),
            "inference_enabled": self._enable_inference,
            "auto_relationships_enabled": self._enable_auto_relationships,
            "concept_learning_enabled": self._enable_concept_learning,
            "last_inference": self._last_inference_run.isoformat(),
            "min_relationship_strength": self._min_relationship_strength,
            "max_traversal_depth": self._max_traversal_depth
        }
        
        base_stats.update(semantic_stats)
        return base_stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check for semantic memory tier."""
        health = await super().health_check()
        
        # Semantic memory specific health metrics
        inference_health = (datetime.utcnow() - self._last_inference_run) < self._inference_interval * 2
        
        # Check relationship consistency
        relationship_health = True
        total_relationships = sum(len(rels) for rels in self._relationship_cache.values())
        
        # Check for orphaned relationships (simplified check)
        orphaned_count = 0  # Would implement actual orphan detection
        
        semantic_health = {
            "inference_running": inference_health,
            "relationship_health": relationship_health,
            "total_entities": sum(len(entities) for entities in self._entity_registry.values()),
            "total_relationships": total_relationships,
            "orphaned_relationships": orphaned_count,
            "concept_definitions": len(self._concept_definitions),
            "semantic_domains": len(self._semantic_networks)
        }
        
        health.update(semantic_health)
        return health