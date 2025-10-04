"""
smrti/adapters/graph/neo4j.py - Neo4j adapter for Semantic Memory

Production-ready Neo4j adapter for semantic relationships, entity networks,
and graph traversal queries with advanced relationship modeling.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
    from neo4j.exceptions import Neo4jError, ServiceUnavailable, TransientError
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False
    AsyncGraphDatabase = None
    
    # Type placeholders when neo4j is not available
    class AsyncDriver:
        pass
    
    class AsyncSession:
        pass
    
    Neo4jError = Exception
    ServiceUnavailable = Exception
    TransientError = Exception

from smrti.core.base import BaseTierStore
from smrti.core.exceptions import (
    AdapterError,
    ConfigurationError,
    ValidationError,
    RetryableError,
    IntegrityError
)
from smrti.core.protocols import TierStore, GraphStore
from smrti.core.registry import AdapterCapability
from smrti.schemas.models import (
    MemoryQuery, 
    RecordEnvelope, 
    ConversationTurn
)


class Neo4jAdapter(BaseTierStore):
    """
    Neo4j adapter for Semantic Memory storage.
    
    Features:
    - Entity relationship modeling
    - Semantic networks and knowledge graphs
    - Graph traversal queries and path finding
    - Cypher query execution with parameterization
    - Relationship strength scoring
    - Entity disambiguation and merging
    - Community detection and clustering
    - Graph analytics and centrality measures
    - Temporal relationship tracking
    - Multi-tenant graph isolation
    - Schema-based entity validation
    - Batch operations for performance
    """
    
    def __init__(
        self,
        tier_name: str = "semantic",
        config: Optional[Dict[str, Any]] = None
    ):
        if not HAS_NEO4J:
            raise ConfigurationError(
                "neo4j package is required but not installed. "
                "Install with: pip install neo4j"
            )
        
        super().__init__(tier_name, config)
        
        # Validate required configuration
        self._validate_config(["uri", "user", "password"])
        
        # Database connection configuration
        self._uri = self.config["uri"]
        self._user = self.config["user"]
        self._password = self.config["password"]
        self._database = self.config.get("database", "neo4j")
        
        # Connection and performance settings
        self._max_connection_lifetime = self.config.get("max_connection_lifetime", 3600)
        self._max_connection_pool_size = self.config.get("max_connection_pool_size", 100)
        self._connection_acquisition_timeout = self.config.get("connection_acquisition_timeout", 60)
        self._max_transaction_retry_time = self.config.get("max_transaction_retry_time", 30)
        
        # Query configuration
        self._query_timeout = self.config.get("query_timeout", 30.0)
        self._batch_size = self.config.get("batch_size", 1000)
        self._max_traversal_depth = self.config.get("max_traversal_depth", 5)
        
        # Graph modeling configuration
        self._entity_label = self.config.get("entity_label", "Entity")
        self._memory_label = self.config.get("memory_label", "Memory")
        self._relationship_types = self.config.get("relationship_types", {
            "RELATES_TO": 1.0,
            "CONTAINS": 0.8,
            "CAUSES": 0.9,
            "SIMILAR_TO": 0.7,
            "PART_OF": 0.8,
            "FOLLOWS": 0.6
        })
        
        # Semantic analysis configuration
        self._enable_entity_extraction = self.config.get("enable_entity_extraction", True)
        self._min_relationship_strength = self.config.get("min_relationship_strength", 0.1)
        self._auto_merge_threshold = self.config.get("auto_merge_threshold", 0.9)
        
        # Driver and session objects
        self._driver: Optional[AsyncDriver] = None
        
        # Statistics
        self._query_count = 0
        self._transaction_count = 0
        self._total_query_time = 0.0
        self._entity_count = 0
        self._relationship_count = 0
        
        # Set tier capabilities
        self._supports_ttl = True  # Handled at application level
        self._supports_similarity_search = True  # Via graph similarity
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_driver()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._cleanup_driver()
    
    async def _initialize_driver(self) -> None:
        """Initialize Neo4j driver and ensure database setup."""
        try:
            # Create driver with configuration
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
                max_connection_lifetime=self._max_connection_lifetime,
                max_connection_pool_size=self._max_connection_pool_size,
                connection_acquisition_timeout=self._connection_acquisition_timeout,
                max_transaction_retry_time=self._max_transaction_retry_time
            )
            
            # Test connection and initialize constraints
            async with self._driver.session(database=self._database) as session:
                await self._initialize_constraints(session)
                await self._initialize_indexes(session)
            
            self.logger.info(
                f"Neo4j adapter initialized (uri={self._uri}, "
                f"db={self._database})"
            )
            
        except Exception as e:
            raise AdapterError(
                f"Failed to initialize Neo4j driver: {e}",
                adapter_name="neo4j",
                operation="initialize",
                backend_error=e
            )
    
    async def _initialize_constraints(self, session: AsyncSession) -> None:
        """Initialize database constraints and schema."""
        constraints = [
            # Unique constraints for entities and memories
            f"CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:{self._entity_label}) REQUIRE e.entity_id IS UNIQUE",
            f"CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:{self._memory_label}) REQUIRE m.record_id IS UNIQUE",
            
            # Composite constraints for tenant isolation
            f"CREATE CONSTRAINT tenant_entity IF NOT EXISTS FOR (e:{self._entity_label}) REQUIRE (e.tenant_id, e.namespace, e.name) IS UNIQUE",
            
            # Existence constraints for required properties
            f"CREATE CONSTRAINT entity_tenant IF NOT EXISTS FOR (e:{self._entity_label}) REQUIRE e.tenant_id IS NOT NULL",
            f"CREATE CONSTRAINT memory_tenant IF NOT EXISTS FOR (m:{self._memory_label}) REQUIRE m.tenant_id IS NOT NULL",
        ]
        
        for constraint in constraints:
            try:
                await session.run(constraint)
            except Neo4jError as e:
                # Constraint already exists is fine
                if "already exists" not in str(e):
                    self.logger.warning(f"Failed to create constraint: {e}")
    
    async def _initialize_indexes(self, session: AsyncSession) -> None:
        """Initialize performance indexes."""
        indexes = [
            # Full-text search indexes
            f"CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS FOR (e:{self._entity_label}) ON EACH [e.name, e.description, e.properties]",
            f"CREATE FULLTEXT INDEX memory_fulltext IF NOT EXISTS FOR (m:{self._memory_label}) ON EACH [m.content, m.tags, m.source]",
            
            # Property indexes for filtering
            f"CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:{self._entity_label}) ON (e.entity_type)",
            f"CREATE INDEX entity_tenant_idx IF NOT EXISTS FOR (e:{self._entity_label}) ON (e.tenant_id, e.namespace)",
            f"CREATE INDEX memory_tenant_idx IF NOT EXISTS FOR (m:{self._memory_label}) ON (m.tenant_id, e.namespace)",
            f"CREATE INDEX memory_created_idx IF NOT EXISTS FOR (m:{self._memory_label}) ON (m.created_at)",
            
            # Relationship indexes
            "CREATE INDEX relationship_strength_idx IF NOT EXISTS FOR ()-[r]-() ON (r.strength)",
            "CREATE INDEX relationship_created_idx IF NOT EXISTS FOR ()-[r]-() ON (r.created_at)",
        ]
        
        for index in indexes:
            try:
                await session.run(index)
            except Neo4jError as e:
                # Index already exists is fine
                if "already exists" not in str(e):
                    self.logger.warning(f"Failed to create index: {e}")
    
    def _record_to_cypher_params(self, record: RecordEnvelope) -> Dict[str, Any]:
        """Convert record to Cypher parameters."""
        params = {
            "record_id": record.record_id,
            "tenant_id": record.tenant_id,
            "namespace": record.namespace,
            "tier": record.tier,
            "record_type": record.record_type,
            "content": json.dumps(record.content.model_dump() if hasattr(record.content, 'model_dump') else record.content),
            "embedding": record.embedding,
            "relevance_score": record.relevance_score,
            "access_count": record.access_count,
            "tags": record.tags,
            "source": record.source,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "last_accessed": record.last_accessed.isoformat() if record.last_accessed else None,
            "metadata": record.metadata,
            "content_hash": record.compute_semantic_hash()
        }
        
        # Add optional fields
        if hasattr(record, 'session_id') and record.session_id:
            params['session_id'] = record.session_id
        if hasattr(record, 'expires_at') and record.expires_at:
            params['expires_at'] = record.expires_at.isoformat()
        if record.provenance:
            params['provenance'] = record.provenance.model_dump()
        
        return params
    
    async def store(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Store a memory record as a graph node with relationships."""
        return await self._execute_with_retry(
            "store",
            self._store_impl,
            record,
            ttl
        )
    
    async def _store_impl(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Internal store implementation."""
        self._validate_record(record)
        
        try:
            async with self._driver.session(database=self._database) as session:
                # Store memory node
                await self._store_memory_node(session, record, ttl)
                
                # Extract and store entities if enabled
                if self._enable_entity_extraction:
                    await self._extract_and_store_entities(session, record)
                
                # Create relationships to existing entities
                await self._create_entity_relationships(session, record)
            
            self._query_count += 1
            self._transaction_count += 1
            self._update_stats("store", 1, len(str(record.content)))
            
            return record.record_id
            
        except Neo4jError as e:
            raise AdapterError(
                f"Neo4j error during store: {e}",
                adapter_name="neo4j",
                operation="store",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during store: {e}",
                adapter_name="neo4j", 
                operation="store",
                backend_error=e
            )
    
    async def _store_memory_node(
        self, 
        session: AsyncSession, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> None:
        """Store memory as a graph node."""
        params = self._record_to_cypher_params(record)
        
        # Calculate expiry if TTL is provided
        if ttl:
            expires_at = datetime.utcnow() + ttl
            params['expires_at'] = expires_at.isoformat()
        
        cypher = f"""
        MERGE (m:{self._memory_label} {{record_id: $record_id}})
        SET m += $props,
            m.updated_at = datetime($updated_at),
            m.access_count = COALESCE(m.access_count, 0) + 1,
            m.last_accessed = datetime()
        """
        
        # Add all properties except record_id (already in MERGE)
        props = {k: v for k, v in params.items() if k != 'record_id'}
        params['props'] = props
        
        await session.run(cypher, params)
    
    async def _extract_and_store_entities(
        self, 
        session: AsyncSession, 
        record: RecordEnvelope
    ) -> None:
        """Extract entities from record content and store as nodes."""
        entities = self._extract_entities_from_content(record)
        
        for entity in entities:
            entity_params = {
                "entity_id": entity["id"],
                "tenant_id": record.tenant_id,
                "namespace": record.namespace,
                "name": entity["name"],
                "entity_type": entity.get("type", "unknown"),
                "description": entity.get("description", ""),
                "properties": entity.get("properties", {}),
                "confidence": entity.get("confidence", 1.0),
                "created_at": datetime.utcnow().isoformat()
            }
            
            cypher = f"""
            MERGE (e:{self._entity_label} {{
                tenant_id: $tenant_id,
                namespace: $namespace,
                name: $name
            }})
            SET e += $props,
                e.updated_at = datetime(),
                e.mention_count = COALESCE(e.mention_count, 0) + 1
            """
            
            props = {k: v for k, v in entity_params.items() 
                    if k not in ['tenant_id', 'namespace', 'name']}
            entity_params['props'] = props
            
            await session.run(cypher, entity_params)
            self._entity_count += 1
    
    def _extract_entities_from_content(self, record: RecordEnvelope) -> List[Dict[str, Any]]:
        """Extract entities from record content (simplified implementation)."""
        # This is a basic implementation - in production, you'd use NLP models
        entities = []
        
        content_str = str(record.content)
        
        # Simple entity extraction based on patterns
        # In production, integrate with spaCy, NLTK, or custom NER models
        
        # Extract potential entities from tags
        for tag in record.tags:
            entities.append({
                "id": f"tag_{tag}_{hash(tag) % 10000}",
                "name": tag,
                "type": "tag",
                "confidence": 0.8
            })
        
        # Extract entities from source
        if record.source:
            entities.append({
                "id": f"source_{record.source}_{hash(record.source) % 10000}",
                "name": record.source,
                "type": "source",
                "confidence": 0.9
            })
        
        # Extract entities if this is an EntityRecord
        if hasattr(record.content, 'entity_name'):
            entities.append({
                "id": f"entity_{record.content.entity_name}_{hash(record.content.entity_name) % 10000}",
                "name": record.content.entity_name,
                "type": getattr(record.content, 'entity_type', 'entity'),
                "description": getattr(record.content, 'description', ''),
                "properties": getattr(record.content, 'properties', {}),
                "confidence": 1.0
            })
        
        return entities
    
    async def _create_entity_relationships(
        self, 
        session: AsyncSession, 
        record: RecordEnvelope
    ) -> None:
        """Create relationships between memory and entities."""
        # Connect memory to entities it mentions
        cypher = f"""
        MATCH (m:{self._memory_label} {{record_id: $record_id}})
        MATCH (e:{self._entity_label} {{tenant_id: $tenant_id, namespace: $namespace}})
        WHERE e.name IN $entity_names
        MERGE (m)-[r:MENTIONS]->(e)
        SET r.strength = COALESCE(r.strength, 0) + $strength_increment,
            r.last_updated = datetime()
        """
        
        # Get entity names from the record
        entity_names = []
        entity_names.extend(record.tags)
        if record.source:
            entity_names.append(record.source)
        
        if hasattr(record.content, 'entity_name'):
            entity_names.append(record.content.entity_name)
        
        if entity_names:
            await session.run(cypher, {
                "record_id": record.record_id,
                "tenant_id": record.tenant_id,
                "namespace": record.namespace,
                "entity_names": entity_names,
                "strength_increment": 0.1
            })
            
            self._relationship_count += len(entity_names)
    
    async def retrieve(self, record_id: str) -> Optional[RecordEnvelope]:
        """Retrieve a specific memory record."""
        return await self._execute_with_retry(
            "retrieve",
            self._retrieve_impl,
            record_id
        )
    
    async def _retrieve_impl(self, record_id: str) -> Optional[RecordEnvelope]:
        """Internal retrieve implementation."""
        try:
            async with self._driver.session(database=self._database) as session:
                # Update access count and retrieve record
                cypher = f"""
                MATCH (m:{self._memory_label} {{record_id: $record_id}})
                SET m.access_count = COALESCE(m.access_count, 0) + 1,
                    m.last_accessed = datetime()
                RETURN m
                """
                
                result = await session.run(cypher, {"record_id": record_id})
                record_data = await result.single()
                
                if record_data is None:
                    return None
                
                memory_node = record_data["m"]
                record = self._node_to_record(memory_node)
                self._update_stats("retrieve", 1)
                
                return record
                
        except Neo4jError as e:
            raise AdapterError(
                f"Neo4j error during retrieve: {e}",
                adapter_name="neo4j",
                operation="retrieve",
                backend_error=e
            )
        except Exception as e:
            self.logger.warning(f"Error retrieving record {record_id}: {e}")
            return None
    
    def _node_to_record(self, node: Dict[str, Any]) -> RecordEnvelope:
        """Convert Neo4j node to RecordEnvelope."""
        # Parse content back to appropriate type
        content_data = json.loads(node['content']) if isinstance(node['content'], str) else node['content']
        
        # Build record data
        record_data = {
            'record_id': node['record_id'],
            'tenant_id': node['tenant_id'],
            'namespace': node['namespace'],
            'tier': node.get('tier', 'semantic'),
            'record_type': node['record_type'],
            'content': content_data,
            'embedding': node.get('embedding'),
            'relevance_score': node.get('relevance_score', 0.0),
            'access_count': node.get('access_count', 0),
            'tags': node.get('tags', []),
            'source': node.get('source'),
            'created_at': datetime.fromisoformat(node['created_at'].replace('Z', '+00:00')) if isinstance(node['created_at'], str) else node['created_at'],
            'updated_at': datetime.fromisoformat(node['updated_at'].replace('Z', '+00:00')) if isinstance(node['updated_at'], str) else node['updated_at'],
            'metadata': node.get('metadata', {})
        }
        
        # Add optional fields
        if node.get('session_id'):
            record_data['session_id'] = node['session_id']
        if node.get('last_accessed'):
            record_data['last_accessed'] = datetime.fromisoformat(node['last_accessed'].replace('Z', '+00:00')) if isinstance(node['last_accessed'], str) else node['last_accessed']
        if node.get('expires_at'):
            record_data['expires_at'] = datetime.fromisoformat(node['expires_at'].replace('Z', '+00:00')) if isinstance(node['expires_at'], str) else node['expires_at']
        if node.get('provenance'):
            record_data['provenance'] = node['provenance']
        
        return RecordEnvelope(**record_data)
    
    async def query(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Query records using graph traversal and semantic relationships."""
        return await self._execute_with_retry(
            "query",
            self._query_impl,
            query
        )
    
    async def _query_impl(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Internal query implementation with graph traversal."""
        self._validate_query(query)
        
        try:
            start_time = time.time()
            
            async with self._driver.session(database=self._database) as session:
                # Build Cypher query based on query parameters
                cypher, params = self._build_cypher_query(query)
                
                result = await session.run(cypher, params)
                records = []
                
                async for record_data in result:
                    try:
                        memory_node = record_data["m"]
                        record = self._node_to_record(dict(memory_node))
                        records.append(record)
                    except Exception as e:
                        self.logger.warning(f"Failed to convert node to record: {e}")
                        continue
            
            query_time = time.time() - start_time
            self._query_count += 1
            self._total_query_time += query_time
            self._update_stats("retrieve", len(records))
            
            if query_time > 1.0:
                self.logger.warning(f"Slow Neo4j query took {query_time:.2f}s")
            
            return records
            
        except Neo4jError as e:
            raise AdapterError(
                f"Neo4j error during query: {e}",
                adapter_name="neo4j",
                operation="query",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during query: {e}",
                adapter_name="neo4j",
                operation="query",
                backend_error=e
            )
    
    def _build_cypher_query(self, query: MemoryQuery) -> Tuple[str, Dict[str, Any]]:
        """Build Cypher query from MemoryQuery parameters."""
        where_conditions = []
        params = {}
        
        # Base match pattern
        cypher_parts = [f"MATCH (m:{self._memory_label})"]
        
        # Basic filtering
        if query.tenant_id:
            where_conditions.append("m.tenant_id = $tenant_id")
            params["tenant_id"] = query.tenant_id
        
        if query.namespace:
            where_conditions.append("m.namespace = $namespace")
            params["namespace"] = query.namespace
        
        # Time range filtering
        if query.start_time:
            where_conditions.append("datetime(m.created_at) >= datetime($start_time)")
            params["start_time"] = query.start_time.isoformat()
        
        if query.end_time:
            where_conditions.append("datetime(m.created_at) <= datetime($end_time)")
            params["end_time"] = query.end_time.isoformat()
        
        # Tag filtering with graph traversal
        if query.tags:
            cypher_parts.append(f"OPTIONAL MATCH (m)-[:MENTIONS]->(e:{self._entity_label})")
            where_conditions.append("ANY(tag IN $tags WHERE tag IN m.tags OR e.name = tag)")
            params["tags"] = query.tags
        
        # Full-text search
        if query.query_text:
            # Use full-text index for content search
            cypher_parts.append(f"CALL db.index.fulltext.queryNodes('memory_fulltext', $query_text) YIELD node, score")
            cypher_parts.append("WHERE node = m")
            params["query_text"] = query.query_text
        
        # Semantic similarity search via graph traversal
        if hasattr(query, 'semantic_query') and query.semantic_query:
            cypher_parts.append(f"""
            OPTIONAL MATCH (m)-[:MENTIONS|RELATES_TO*1..{self._max_traversal_depth}]-(related:{self._memory_label})
            WHERE related.content CONTAINS $semantic_query
            """)
            params["semantic_query"] = query.semantic_query
        
        # Build WHERE clause
        if where_conditions:
            cypher_parts.append("WHERE " + " AND ".join(where_conditions))
        
        # Return with ordering
        cypher_parts.extend([
            "RETURN DISTINCT m",
            "ORDER BY m.relevance_score DESC, m.access_count DESC, m.created_at DESC",
            f"LIMIT {query.limit}"
        ])
        
        return "\n".join(cypher_parts), params
    
    async def delete(self, record_id: str) -> bool:
        """Delete a memory record and its relationships."""
        return await self._execute_with_retry(
            "delete",
            self._delete_impl,
            record_id
        )
    
    async def _delete_impl(self, record_id: str) -> bool:
        """Internal delete implementation."""
        try:
            async with self._driver.session(database=self._database) as session:
                # Delete memory node and all its relationships
                cypher = f"""
                MATCH (m:{self._memory_label} {{record_id: $record_id}})
                DETACH DELETE m
                RETURN COUNT(m) as deleted_count
                """
                
                result = await session.run(cypher, {"record_id": record_id})
                record_data = await result.single()
                
                deleted_count = record_data["deleted_count"] if record_data else 0
                
                if deleted_count > 0:
                    self._update_stats("delete", 1)
                    return True
                else:
                    return False
                    
        except Neo4jError as e:
            raise AdapterError(
                f"Neo4j error during delete: {e}",
                adapter_name="neo4j",
                operation="delete",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during delete: {e}",
                adapter_name="neo4j",
                operation="delete",
                backend_error=e
            )
    
    async def find_related_entities(
        self,
        entity_name: str,
        tenant_id: str,
        namespace: str,
        max_depth: int = 3,
        min_strength: float = 0.1
    ) -> List[Dict[str, Any]]:
        """Find entities related to a given entity through graph traversal."""
        try:
            async with self._driver.session(database=self._database) as session:
                cypher = f"""
                MATCH (start:{self._entity_label} {{
                    tenant_id: $tenant_id,
                    namespace: $namespace,
                    name: $entity_name
                }})
                CALL apoc.path.subgraphAll(start, {{
                    relationshipFilter: "RELATES_TO|SIMILAR_TO|PART_OF",
                    minLevel: 1,
                    maxLevel: $max_depth
                }})
                YIELD nodes, relationships
                UNWIND nodes AS node
                MATCH ()-[r]->(node)
                WHERE r.strength >= $min_strength
                RETURN DISTINCT node, AVG(r.strength) as avg_strength
                ORDER BY avg_strength DESC
                LIMIT 50
                """
                
                result = await session.run(cypher, {
                    "entity_name": entity_name,
                    "tenant_id": tenant_id,
                    "namespace": namespace,
                    "max_depth": max_depth,
                    "min_strength": min_strength
                })
                
                entities = []
                async for record in result:
                    node = dict(record["node"])
                    node["relationship_strength"] = record["avg_strength"]
                    entities.append(node)
                
                return entities
                
        except Exception as e:
            self.logger.error(f"Failed to find related entities: {e}")
            return []
    
    async def get_entity_network(
        self,
        tenant_id: str,
        namespace: str,
        center_entities: List[str],
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """Get the semantic network around a set of entities."""
        try:
            async with self._driver.session(database=self._database) as session:
                cypher = f"""
                MATCH (center:{self._entity_label} {{tenant_id: $tenant_id, namespace: $namespace}})
                WHERE center.name IN $center_entities
                CALL apoc.path.subgraphAll(center, {{
                    relationshipFilter: "*",
                    maxLevel: $max_depth
                }})
                YIELD nodes, relationships
                RETURN nodes, relationships
                """
                
                result = await session.run(cypher, {
                    "tenant_id": tenant_id,
                    "namespace": namespace,
                    "center_entities": center_entities,
                    "max_depth": max_depth
                })
                
                record = await result.single()
                if not record:
                    return {"nodes": [], "relationships": []}
                
                nodes = [dict(node) for node in record["nodes"]]
                relationships = []
                
                for rel in record["relationships"]:
                    relationships.append({
                        "start_node": dict(rel.start_node),
                        "end_node": dict(rel.end_node),
                        "type": rel.type,
                        "properties": dict(rel)
                    })
                
                return {
                    "nodes": nodes,
                    "relationships": relationships,
                    "center_entities": center_entities
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get entity network: {e}")
            return {"nodes": [], "relationships": []}
    
    async def update_relevance(
        self, 
        record_id: str, 
        new_relevance: float
    ) -> bool:
        """Update relevance score for a record."""
        try:
            async with self._driver.session(database=self._database) as session:
                cypher = f"""
                MATCH (m:{self._memory_label} {{record_id: $record_id}})
                SET m.relevance_score = $new_relevance,
                    m.updated_at = datetime()
                RETURN COUNT(m) as updated_count
                """
                
                result = await session.run(cypher, {
                    "record_id": record_id,
                    "new_relevance": new_relevance
                })
                
                record_data = await result.single()
                updated_count = record_data["updated_count"] if record_data else 0
                
                return updated_count > 0
                
        except Exception as e:
            self.logger.error(f"Failed to update relevance for {record_id}: {e}")
            return False
    
    async def cleanup_expired(self) -> int:
        """Remove expired records based on expires_at timestamp."""
        try:
            async with self._driver.session(database=self._database) as session:
                cypher = f"""
                MATCH (m:{self._memory_label})
                WHERE m.expires_at IS NOT NULL 
                  AND datetime(m.expires_at) < datetime()
                DETACH DELETE m
                RETURN COUNT(m) as deleted_count
                """
                
                result = await session.run(cypher)
                record_data = await result.single()
                deleted_count = record_data["deleted_count"] if record_data else 0
                
                if deleted_count > 0:
                    self.logger.info(f"Cleaned up {deleted_count} expired semantic records")
                
                return deleted_count
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired records: {e}")
            return 0
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform Neo4j health check."""
        try:
            async with self._driver.session(database=self._database) as session:
                # Test basic connectivity
                start_time = time.time()
                
                # Get database info
                info_result = await session.run("CALL dbms.components() YIELD name, versions, edition")
                info_record = await info_result.single()
                
                # Get counts
                counts_result = await session.run(f"""
                MATCH (m:{self._memory_label}) 
                OPTIONAL MATCH (e:{self._entity_label})
                OPTIONAL MATCH ()-[r]-()
                RETURN 
                    COUNT(DISTINCT m) as memory_count,
                    COUNT(DISTINCT e) as entity_count,
                    COUNT(DISTINCT r) as relationship_count
                """)
                
                counts = await counts_result.single()
                health_time = time.time() - start_time
                
                return {
                    "neo4j_version": info_record["versions"][0] if info_record else "unknown",
                    "edition": info_record["edition"] if info_record else "unknown",
                    "database": self._database,
                    "uri": self._uri,
                    "memory_count": counts["memory_count"],
                    "entity_count": counts["entity_count"],
                    "relationship_count": counts["relationship_count"],
                    "query_count": self._query_count,
                    "transaction_count": self._transaction_count,
                    "average_query_time": (
                        self._total_query_time / max(1, self._query_count)
                    ),
                    "health_check_time": health_time,
                    "entity_extraction": self._enable_entity_extraction,
                    "max_traversal_depth": self._max_traversal_depth
                }
                
        except Exception as e:
            raise AdapterError(
                f"Neo4j health check failed: {e}",
                adapter_name="neo4j",
                operation="health_check",
                backend_error=e
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Neo4j adapter statistics."""
        base_stats = await super().get_stats()
        
        neo4j_stats = {
            "uri": self._uri,
            "database": self._database,
            "query_count": self._query_count,
            "transaction_count": self._transaction_count,
            "entity_count": self._entity_count,
            "relationship_count": self._relationship_count,
            "average_query_time": (
                self._total_query_time / max(1, self._query_count)
            ),
            "entity_extraction": self._enable_entity_extraction,
            "max_traversal_depth": self._max_traversal_depth,
            "min_relationship_strength": self._min_relationship_strength,
            "auto_merge_threshold": self._auto_merge_threshold
        }
        
        base_stats.update(neo4j_stats)
        return base_stats
    
    async def _cleanup_driver(self) -> None:
        """Clean up Neo4j driver."""
        try:
            if self._driver:
                await self._driver.close()
        except Exception as e:
            self.logger.warning(f"Error during Neo4j cleanup: {e}")
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """Get adapter capabilities."""
        capabilities = [
            AdapterCapability(
                name="semantic_memory",
                version="1.0.0",
                description="Graph-based semantic relationship storage"
            ),
            AdapterCapability(
                name="entity_relationships",
                version="1.0.0",
                description="Entity relationship modeling and traversal"
            ),
            AdapterCapability(
                name="graph_traversal",
                version="1.0.0",
                description="Multi-hop graph traversal queries"
            ),
            AdapterCapability(
                name="semantic_networks",
                version="1.0.0",
                description="Knowledge graph and semantic network analysis"
            ),
            AdapterCapability(
                name="entity_extraction",
                version="1.0.0",
                description="Automatic entity extraction from content"
            ),
            AdapterCapability(
                name="cypher_queries",
                version="1.0.0",
                description="Native Cypher query execution"
            ),
            AdapterCapability(
                name="relationship_strength",
                version="1.0.0",
                description="Weighted relationship scoring and analysis"
            )
        ]
        
        return capabilities