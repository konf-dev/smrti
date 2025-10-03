"""
smrti/api.py - Main API Interface

The unified Smrti class that provides a high-level interface to all memory
operations, tier coordination, and intelligent memory management.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from smrti.core.base import BaseAdapter
from smrti.core.consolidation import ConsolidationConfig, MemoryConsolidationEngine
from smrti.core.context_assembly import ContextAssemblyConfig, ContextAssemblyEngine, ScoredRecord
from smrti.core.exceptions import (
    ConfigurationError, 
    MemoryError, 
    RetrievalError, 
    StorageError, 
    ValidationError
)
from smrti.core.registry import AdapterRegistry
from smrti.core.retrieval_engine import (
    QueryStrategy, 
    ResultMergeStrategy, 
    RetrievalConfig, 
    UnifiedRetrievalEngine
)
from smrti.schemas.models import (
    ContentType, 
    MemoryQuery, 
    MemoryRecord, 
    RecordEnvelope, 
    TextContent
)

# Import all adapters for registration
from smrti.adapters.storage import (
    ChromaDBAdapter,
    ElasticsearchAdapter,
    Neo4jAdapter,
    PostgreSQLAdapter,
    RedisAdapter
)
from smrti.adapters.embedding import (
    OpenAIEmbeddingProvider,
    SentenceTransformersProvider
)
from smrti.memory.tiers import (
    EpisodicMemory,
    LongTermMemory,
    SemanticMemory,
    ShortTermMemory,
    WorkingMemory
)


class SmrtiConfig:
    """Configuration class for the main Smrti system."""
    
    def __init__(
        self,
        # Storage configurations
        redis_config: Optional[Dict[str, Any]] = None,
        chroma_config: Optional[Dict[str, Any]] = None,
        postgres_config: Optional[Dict[str, Any]] = None,
        neo4j_config: Optional[Dict[str, Any]] = None,
        elasticsearch_config: Optional[Dict[str, Any]] = None,
        
        # Embedding provider configurations
        openai_config: Optional[Dict[str, Any]] = None,
        sentence_transformers_config: Optional[Dict[str, Any]] = None,
        
        # Engine configurations
        retrieval_config: Optional[RetrievalConfig] = None,
        context_assembly_config: Optional[ContextAssemblyConfig] = None,
        consolidation_config: Optional[ConsolidationConfig] = None,
        
        # System settings
        default_tenant_id: str = "default",
        auto_start_consolidation: bool = True,
        enable_health_monitoring: bool = True,
        log_level: str = "INFO"
    ):
        # Storage configurations
        self.redis_config = redis_config or {"host": "localhost", "port": 6379}
        self.chroma_config = chroma_config or {"persist_directory": "./chroma_data"}
        self.postgres_config = postgres_config or {
            "host": "localhost", "port": 5432, "database": "smrti"
        }
        self.neo4j_config = neo4j_config or {
            "uri": "bolt://localhost:7687", "database": "smrti"
        }
        self.elasticsearch_config = elasticsearch_config or {
            "hosts": ["http://localhost:9200"]
        }
        
        # Embedding configurations
        self.openai_config = openai_config
        self.sentence_transformers_config = sentence_transformers_config or {
            "model_name": "all-MiniLM-L6-v2"
        }
        
        # Engine configurations
        self.retrieval_config = retrieval_config or RetrievalConfig()
        self.context_assembly_config = context_assembly_config or ContextAssemblyConfig()
        self.consolidation_config = consolidation_config or ConsolidationConfig()
        
        # System settings
        self.default_tenant_id = default_tenant_id
        self.auto_start_consolidation = auto_start_consolidation
        self.enable_health_monitoring = enable_health_monitoring
        self.log_level = log_level


class SmrtiSession:
    """Session context for memory operations with automatic lifecycle management."""
    
    def __init__(
        self, 
        smrti_instance: 'Smrti',
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        namespace: str = "default"
    ):
        self.smrti = smrti_instance
        self.session_id = session_id or str(uuid.uuid4())
        self.tenant_id = tenant_id or smrti_instance.config.default_tenant_id
        self.namespace = namespace
        self.created_at = datetime.utcnow()
        
        # Session-specific context
        self.context: Dict[str, Any] = {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat()
        }
        
        # Session statistics
        self.operations_count = 0
        self.last_activity = self.created_at
    
    async def store_memory(
        self,
        content: Union[str, ContentType],
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        tier: Optional[str] = None
    ) -> str:
        """Store a memory in this session context."""
        return await self.smrti.store_memory(
            content=content,
            tenant_id=self.tenant_id,
            namespace=self.namespace,
            metadata=metadata,
            importance=importance,
            tier=tier,
            session_context=self.context
        )
    
    async def retrieve_memories(
        self,
        query: Union[str, MemoryQuery],
        limit: int = 10,
        strategy: Optional[QueryStrategy] = None,
        merge_strategy: Optional[ResultMergeStrategy] = None
    ) -> List[ScoredRecord]:
        """Retrieve memories in this session context."""
        return await self.smrti.retrieve_memories(
            query=query,
            tenant_id=self.tenant_id,
            namespace=self.namespace,
            limit=limit,
            strategy=strategy,
            merge_strategy=merge_strategy,
            session_context=self.context
        )
    
    async def search_memories(
        self,
        query_text: str,
        limit: int = 10,
        similarity_threshold: float = 0.1,
        time_range_hours: Optional[int] = None
    ) -> List[ScoredRecord]:
        """Simple text-based memory search in this session."""
        query = MemoryQuery(
            query_text=query_text,
            tenant_id=self.tenant_id,
            namespace=self.namespace,
            limit=limit,
            similarity_threshold=similarity_threshold,
            time_range_hours=time_range_hours
        )
        
        return await self.retrieve_memories(query)
    
    def _update_activity(self):
        """Update session activity timestamp."""
        self.operations_count += 1
        self.last_activity = datetime.utcnow()
        self.context["last_activity"] = self.last_activity.isoformat()
        self.context["operations_count"] = self.operations_count


class Smrti(BaseAdapter):
    """
    Main Smrti intelligent memory system interface.
    
    Provides a unified, high-level API for all memory operations with
    intelligent routing, session management, and production-ready features.
    """
    
    def __init__(self, config: Optional[SmrtiConfig] = None):
        super().__init__("smrti_main")
        self.config = config or SmrtiConfig()
        
        # Setup logging
        logging.basicConfig(level=getattr(logging, self.config.log_level))
        
        # Core components
        self.registry = AdapterRegistry()
        self.context_assembly: Optional[ContextAssemblyEngine] = None
        self.retrieval_engine: Optional[UnifiedRetrievalEngine] = None
        self.consolidation_engine: Optional[MemoryConsolidationEngine] = None
        
        # Memory tiers
        self.working_memory: Optional[WorkingMemory] = None
        self.short_term_memory: Optional[ShortTermMemory] = None  
        self.long_term_memory: Optional[LongTermMemory] = None
        self.episodic_memory: Optional[EpisodicMemory] = None
        self.semantic_memory: Optional[SemanticMemory] = None
        
        # Session management
        self.active_sessions: Dict[str, SmrtiSession] = {}
        self._session_cleanup_task: Optional[asyncio.Task] = None
        
        # System state
        self._initialized = False
        self._running = False
        
        # Performance tracking
        self._total_operations = 0
        self._successful_operations = 0
        self._failed_operations = 0
        self._initialization_time: Optional[datetime] = None
    
    async def initialize(self) -> None:
        """
        Initialize the Smrti system with all components.
        
        Raises:
            ConfigurationError: If initialization fails due to configuration issues
        """
        if self._initialized:
            self.logger.warning("Smrti system is already initialized")
            return
        
        init_start = datetime.utcnow()
        self.logger.info("Initializing Smrti intelligent memory system...")
        
        try:
            # Initialize embedding providers
            await self._initialize_embedding_providers()
            
            # Initialize storage adapters  
            await self._initialize_storage_adapters()
            
            # Initialize memory tiers
            await self._initialize_memory_tiers()
            
            # Initialize engines
            await self._initialize_engines()
            
            # Start background services
            if self.config.auto_start_consolidation and self.consolidation_engine:
                await self.consolidation_engine.start_consolidation_service()
            
            # Start session cleanup
            self._session_cleanup_task = asyncio.create_task(self._session_cleanup_loop())
            
            self._initialized = True
            self._running = True
            self._initialization_time = init_start
            
            init_duration = (datetime.utcnow() - init_start).total_seconds()
            self.logger.info(f"Smrti system initialized successfully in {init_duration:.2f}s")
            
        except Exception as e:
            self._mark_error(e)
            raise ConfigurationError(f"Failed to initialize Smrti system: {e}") from e
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown the Smrti system.
        
        Stops all background services and closes connections.
        """
        if not self._initialized:
            return
        
        self.logger.info("Shutting down Smrti system...")
        self._running = False
        
        try:
            # Stop consolidation service
            if self.consolidation_engine:
                await self.consolidation_engine.stop_consolidation_service()
            
            # Stop session cleanup
            if self._session_cleanup_task:
                self._session_cleanup_task.cancel()
                try:
                    await self._session_cleanup_task
                except asyncio.CancelledError:
                    pass
            
            # Close storage connections
            for adapter in self.registry.tier_stores.values():
                if hasattr(adapter, 'close'):
                    try:
                        await adapter.close()
                    except Exception as e:
                        self.logger.warning(f"Error closing adapter: {e}")
            
            self._initialized = False
            self.logger.info("Smrti system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    async def _initialize_embedding_providers(self) -> None:
        """Initialize embedding providers."""
        self.logger.info("Initializing embedding providers...")
        
        # Sentence Transformers (always available)
        try:
            st_provider = SentenceTransformersProvider(
                **self.config.sentence_transformers_config
            )
            self.registry.register_embedding_provider("sentence_transformers", st_provider)
            self.logger.info("Registered SentenceTransformers embedding provider")
        except Exception as e:
            self.logger.warning(f"Failed to initialize SentenceTransformers: {e}")
        
        # OpenAI (if configured)
        if self.config.openai_config:
            try:
                openai_provider = OpenAIEmbeddingProvider(**self.config.openai_config)
                self.registry.register_embedding_provider("openai", openai_provider)
                self.logger.info("Registered OpenAI embedding provider")
            except Exception as e:
                self.logger.warning(f"Failed to initialize OpenAI provider: {e}")
    
    async def _initialize_storage_adapters(self) -> None:
        """Initialize storage adapters."""
        self.logger.info("Initializing storage adapters...")
        
        # Redis adapter (for working/short-term memory)
        try:
            redis_adapter = RedisAdapter(**self.config.redis_config)
            self.registry.register_tier_store("redis", redis_adapter)
            self.logger.info("Registered Redis adapter")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Redis adapter: {e}")
        
        # ChromaDB adapter (for long-term memory)
        try:
            chroma_adapter = ChromaDBAdapter(**self.config.chroma_config)
            self.registry.register_tier_store("chroma", chroma_adapter)
            self.logger.info("Registered ChromaDB adapter")
        except Exception as e:
            self.logger.warning(f"Failed to initialize ChromaDB adapter: {e}")
        
        # PostgreSQL adapter (for episodic memory)
        try:
            postgres_adapter = PostgreSQLAdapter(**self.config.postgres_config)
            self.registry.register_tier_store("postgres", postgres_adapter)
            self.logger.info("Registered PostgreSQL adapter")
        except Exception as e:
            self.logger.warning(f"Failed to initialize PostgreSQL adapter: {e}")
        
        # Neo4j adapter (for semantic memory)
        try:
            neo4j_adapter = Neo4jAdapter(**self.config.neo4j_config)
            self.registry.register_tier_store("neo4j", neo4j_adapter)
            self.logger.info("Registered Neo4j adapter")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Neo4j adapter: {e}")
        
        # Elasticsearch adapter (for procedural memory)
        try:
            es_adapter = ElasticsearchAdapter(**self.config.elasticsearch_config)
            self.registry.register_tier_store("elasticsearch", es_adapter)
            self.logger.info("Registered Elasticsearch adapter")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Elasticsearch adapter: {e}")
    
    async def _initialize_memory_tiers(self) -> None:
        """Initialize memory tier implementations."""
        self.logger.info("Initializing memory tiers...")
        
        # Working Memory (uses Redis)
        if "redis" in self.registry.tier_stores:
            try:
                self.working_memory = WorkingMemory(self.registry)
                self.registry.register_memory_tier("working", self.working_memory)
                self.logger.info("Initialized Working Memory tier")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Working Memory: {e}")
        
        # Short-term Memory (uses Redis)  
        if "redis" in self.registry.tier_stores:
            try:
                self.short_term_memory = ShortTermMemory(self.registry)
                self.registry.register_memory_tier("short_term", self.short_term_memory)
                self.logger.info("Initialized Short-term Memory tier")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Short-term Memory: {e}")
        
        # Long-term Memory (uses ChromaDB)
        if "chroma" in self.registry.tier_stores:
            try:
                self.long_term_memory = LongTermMemory(self.registry)
                self.registry.register_memory_tier("long_term", self.long_term_memory)
                self.logger.info("Initialized Long-term Memory tier")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Long-term Memory: {e}")
        
        # Episodic Memory (uses PostgreSQL)
        if "postgres" in self.registry.tier_stores:
            try:
                self.episodic_memory = EpisodicMemory(self.registry)
                self.registry.register_memory_tier("episodic", self.episodic_memory)
                self.logger.info("Initialized Episodic Memory tier")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Episodic Memory: {e}")
        
        # Semantic Memory (uses Neo4j)
        if "neo4j" in self.registry.tier_stores:
            try:
                self.semantic_memory = SemanticMemory(self.registry)
                self.registry.register_memory_tier("semantic", self.semantic_memory)
                self.logger.info("Initialized Semantic Memory tier")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Semantic Memory: {e}")
        
        # Set up tier relationships
        self._setup_tier_relationships()
    
    def _setup_tier_relationships(self) -> None:
        """Set up cross-tier relationships for consolidation."""
        # Working -> Short-term
        if self.working_memory and self.short_term_memory:
            self.working_memory.register_downstream_tier("short_term")
            self.short_term_memory.register_upstream_tier("working")
        
        # Short-term -> Long-term
        if self.short_term_memory and self.long_term_memory:
            self.short_term_memory.register_downstream_tier("long_term")
            self.long_term_memory.register_upstream_tier("short_term")
        
        # Cross-connections for specialized tiers
        if self.working_memory:
            if self.episodic_memory:
                self.working_memory.register_downstream_tier("episodic")
                self.episodic_memory.register_upstream_tier("working")
            
            if self.semantic_memory:
                self.working_memory.register_downstream_tier("semantic")
                self.semantic_memory.register_upstream_tier("working")
    
    async def _initialize_engines(self) -> None:
        """Initialize the core engines."""
        self.logger.info("Initializing core engines...")
        
        # Context Assembly Engine
        try:
            self.context_assembly = ContextAssemblyEngine(
                self.registry, 
                self.config.context_assembly_config
            )
            self.logger.info("Initialized Context Assembly Engine")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Context Assembly Engine: {e}")
        
        # Unified Retrieval Engine
        try:
            self.retrieval_engine = UnifiedRetrievalEngine(
                self.registry,
                self.context_assembly,
                self.config.retrieval_config
            )
            self.logger.info("Initialized Unified Retrieval Engine")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Retrieval Engine: {e}")
        
        # Memory Consolidation Engine
        try:
            self.consolidation_engine = MemoryConsolidationEngine(
                self.registry,
                self.config.consolidation_config
            )
            self.logger.info("Initialized Memory Consolidation Engine")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Consolidation Engine: {e}")
    
    async def store_memory(
        self,
        content: Union[str, ContentType],
        tenant_id: Optional[str] = None,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        tier: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a memory in the appropriate tier.
        
        Args:
            content: Memory content (text or structured content)
            tenant_id: Tenant identifier for isolation
            namespace: Namespace for organization
            metadata: Additional metadata
            importance: Importance score (0.0 to 1.0)
            tier: Specific tier to store in (optional, auto-selected if None)
            session_context: Session context for tracking
            
        Returns:
            Unique record ID
            
        Raises:
            StorageError: If storage fails
            ValidationError: If input is invalid
        """
        if not self._initialized:
            raise MemoryError("Smrti system not initialized")
        
        self._total_operations += 1
        
        try:
            # Validate inputs
            if not content:
                raise ValidationError("Content cannot be empty")
            
            if not 0.0 <= importance <= 1.0:
                raise ValidationError("Importance must be between 0.0 and 1.0")
            
            tenant_id = tenant_id or self.config.default_tenant_id
            
            # Create content object
            if isinstance(content, str):
                content_obj = TextContent(text=content)
            else:
                content_obj = content
            
            # Generate embedding
            embedding = None
            if self.registry.embedding_providers:
                try:
                    provider = next(iter(self.registry.embedding_providers.values()))
                    if hasattr(content_obj, 'get_text'):
                        text = content_obj.get_text()
                    else:
                        text = str(content_obj)
                    embedding = await provider.embed_text(text)
                except Exception as e:
                    self.logger.warning(f"Failed to generate embedding: {e}")
            
            # Create memory record
            record_id = str(uuid.uuid4())
            
            # Prepare metadata
            final_metadata = {
                "importance_score": importance,
                "access_count": 0,
                "created_by": "smrti_api",
                **(metadata or {}),
                **(session_context or {})
            }
            
            # Create record envelope
            record = RecordEnvelope(
                record_id=record_id,
                tenant_id=tenant_id,
                namespace=namespace,
                content=content_obj,
                embedding=embedding,
                metadata=final_metadata,
                created_at=datetime.utcnow()
            )
            
            # Select appropriate tier
            target_tier = tier or self._select_storage_tier(importance, content_obj)
            
            # Store in selected tier
            memory_tier = self.registry.memory_tiers.get(target_tier)
            if not memory_tier:
                raise StorageError(f"Memory tier '{target_tier}' not available")
            
            success = await memory_tier.store_memory(record)
            
            if not success:
                raise StorageError(f"Failed to store memory in tier '{target_tier}'")
            
            self._successful_operations += 1
            
            self.logger.debug(
                f"Stored memory {record_id} in tier '{target_tier}' "
                f"(importance: {importance})"
            )
            
            return record_id
        
        except Exception as e:
            self._failed_operations += 1
            self._mark_error(e)
            if isinstance(e, (StorageError, ValidationError, MemoryError)):
                raise
            else:
                raise StorageError(f"Memory storage failed: {e}") from e
    
    async def retrieve_memories(
        self,
        query: Union[str, MemoryQuery],
        tenant_id: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 10,
        strategy: Optional[QueryStrategy] = None,
        merge_strategy: Optional[ResultMergeStrategy] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> List[ScoredRecord]:
        """
        Retrieve memories using intelligent cross-tier querying.
        
        Args:
            query: Query string or structured query
            tenant_id: Tenant identifier
            namespace: Namespace filter
            limit: Maximum results to return
            strategy: Query execution strategy
            merge_strategy: Result merging strategy
            session_context: Session context
            
        Returns:
            List of scored memory records
            
        Raises:
            RetrievalError: If retrieval fails
        """
        if not self._initialized:
            raise MemoryError("Smrti system not initialized")
        
        if not self.retrieval_engine:
            raise RetrievalError("Retrieval engine not available")
        
        self._total_operations += 1
        
        try:
            # Create query object
            if isinstance(query, str):
                query_obj = MemoryQuery(
                    query_text=query,
                    tenant_id=tenant_id or self.config.default_tenant_id,
                    namespace=namespace or "default",
                    limit=limit
                )
            else:
                query_obj = query
                # Override parameters if provided
                if tenant_id:
                    query_obj.tenant_id = tenant_id
                if namespace:
                    query_obj.namespace = namespace
                if limit != 10:
                    query_obj.limit = limit
            
            # Execute retrieval
            results = await self.retrieval_engine.retrieve_memories(
                query_obj,
                session_context,
                strategy,
                merge_strategy
            )
            
            # Update access counts for retrieved memories
            await self._update_access_counts(results)
            
            self._successful_operations += 1
            
            self.logger.debug(
                f"Retrieved {len(results)} memories for query: {query_obj.query_text}"
            )
            
            return results
        
        except Exception as e:
            self._failed_operations += 1
            self._mark_error(e)
            if isinstance(e, (RetrievalError, MemoryError)):
                raise
            else:
                raise RetrievalError(f"Memory retrieval failed: {e}") from e
    
    async def search_memories(
        self,
        query_text: str,
        tenant_id: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.1,
        time_range_hours: Optional[int] = None
    ) -> List[ScoredRecord]:
        """
        Simple text-based memory search.
        
        Convenience method for basic search operations.
        """
        query = MemoryQuery(
            query_text=query_text,
            tenant_id=tenant_id or self.config.default_tenant_id,
            namespace=namespace or "default",
            limit=limit,
            similarity_threshold=similarity_threshold,
            time_range_hours=time_range_hours
        )
        
        return await self.retrieve_memories(query)
    
    async def delete_memory(
        self,
        record_id: str,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Delete a memory record from all tiers.
        
        Args:
            record_id: Record identifier
            tenant_id: Tenant identifier
            
        Returns:
            True if deleted successfully
        """
        if not self._initialized:
            raise MemoryError("Smrti system not initialized")
        
        tenant_id = tenant_id or self.config.default_tenant_id
        deleted = False
        
        # Try to delete from all memory tiers
        for tier_name, tier in self.registry.memory_tiers.items():
            try:
                if await tier.delete_memory(record_id, tenant_id):
                    deleted = True
                    self.logger.debug(f"Deleted memory {record_id} from tier {tier_name}")
            except Exception as e:
                self.logger.warning(f"Error deleting from tier {tier_name}: {e}")
        
        return deleted
    
    def create_session(
        self,
        tenant_id: Optional[str] = None,
        namespace: str = "default"
    ) -> SmrtiSession:
        """
        Create a new memory session.
        
        Args:
            tenant_id: Tenant identifier
            namespace: Session namespace
            
        Returns:
            New session instance
        """
        session = SmrtiSession(
            smrti_instance=self,
            tenant_id=tenant_id,
            namespace=namespace
        )
        
        self.active_sessions[session.session_id] = session
        self.logger.debug(f"Created session {session.session_id}")
        
        return session
    
    @asynccontextmanager
    async def session(
        self,
        tenant_id: Optional[str] = None,
        namespace: str = "default"
    ) -> AsyncGenerator[SmrtiSession, None]:
        """
        Context manager for automatic session lifecycle management.
        
        Usage:
            async with smrti.session() as session:
                await session.store_memory("Hello world")
                results = await session.search_memories("Hello")
        """
        session = self.create_session(tenant_id, namespace)
        
        try:
            yield session
        finally:
            await self._cleanup_session(session.session_id)
    
    async def force_consolidation(self, tier_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Force immediate memory consolidation.
        
        Args:
            tier_name: Specific tier to consolidate (optional)
            
        Returns:
            Consolidation results
        """
        if not self.consolidation_engine:
            raise MemoryError("Consolidation engine not available")
        
        return await self.consolidation_engine.force_consolidation(tier_name)
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        if not self._initialized:
            return {"status": "not_initialized"}
        
        stats = {
            "system": {
                "initialized": self._initialized,
                "running": self._running,
                "initialization_time": (
                    self._initialization_time.isoformat() 
                    if self._initialization_time else None
                ),
                "total_operations": self._total_operations,
                "successful_operations": self._successful_operations,
                "failed_operations": self._failed_operations,
                "success_rate": (
                    self._successful_operations / max(1, self._total_operations)
                ),
                "active_sessions": len(self.active_sessions)
            },
            "registry": {
                "tier_stores": len(self.registry.tier_stores),
                "memory_tiers": len(self.registry.memory_tiers),
                "embedding_providers": len(self.registry.embedding_providers),
                "available_tiers": list(self.registry.memory_tiers.keys()),
                "available_embedders": list(self.registry.embedding_providers.keys())
            }
        }
        
        # Add engine statistics
        if self.retrieval_engine:
            try:
                retrieval_stats = await self.retrieval_engine.get_retrieval_stats()
                stats["retrieval_engine"] = retrieval_stats
            except Exception as e:
                stats["retrieval_engine"] = {"error": str(e)}
        
        if self.context_assembly:
            try:
                assembly_stats = await self.context_assembly.get_assembly_stats()
                stats["context_assembly"] = assembly_stats
            except Exception as e:
                stats["context_assembly"] = {"error": str(e)}
        
        if self.consolidation_engine:
            try:
                consolidation_stats = await self.consolidation_engine.get_consolidation_stats()
                stats["consolidation"] = consolidation_stats
            except Exception as e:
                stats["consolidation"] = {"error": str(e)}
        
        return stats
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get system health status."""
        if not self._initialized:
            return {
                "status": "unhealthy",
                "reason": "not_initialized"
            }
        
        health_checks = {}
        overall_healthy = True
        
        # Check core components
        try:
            if self.retrieval_engine:
                health_checks["retrieval_engine"] = await self.retrieval_engine.health_check()
        except Exception as e:
            health_checks["retrieval_engine"] = {"status": "unhealthy", "error": str(e)}
            overall_healthy = False
        
        try:
            if self.context_assembly:
                health_checks["context_assembly"] = await self.context_assembly.health_check()
        except Exception as e:
            health_checks["context_assembly"] = {"status": "unhealthy", "error": str(e)}
            overall_healthy = False
        
        try:
            if self.consolidation_engine:
                health_checks["consolidation"] = await self.consolidation_engine.health_check()
        except Exception as e:
            health_checks["consolidation"] = {"status": "unhealthy", "error": str(e)}
            overall_healthy = False
        
        # Check memory tiers
        tier_health = {}
        for tier_name, tier in self.registry.memory_tiers.items():
            try:
                if hasattr(tier, 'health_check'):
                    tier_health[tier_name] = await tier.health_check()
                else:
                    tier_health[tier_name] = {"status": "healthy", "note": "no_health_check"}
            except Exception as e:
                tier_health[tier_name] = {"status": "unhealthy", "error": str(e)}
                overall_healthy = False
        
        return {
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "components": health_checks,
            "tiers": tier_health
        }
    
    def _select_storage_tier(self, importance: float, content: ContentType) -> str:
        """Select appropriate storage tier based on content and importance."""
        # Simple tier selection logic (can be enhanced with ML)
        
        # Very important or recent -> working memory first
        if importance >= 0.8:
            if self.working_memory:
                return "working"
        
        # Important content -> short-term memory
        if importance >= 0.6:
            if self.short_term_memory:
                return "short_term"
        
        # Check content type for specialized storage
        if hasattr(content, 'content_type'):
            if content.content_type in ["event", "experience"]:
                if self.episodic_memory:
                    return "episodic"
            
            elif content.content_type in ["concept", "relationship"]:
                if self.semantic_memory:
                    return "semantic"
            
            elif content.content_type in ["procedure", "skill"]:
                # Would use procedural memory if implemented
                pass
        
        # Default to long-term memory
        if self.long_term_memory:
            return "long_term"
        
        # Fallback to any available tier
        if self.registry.memory_tiers:
            return next(iter(self.registry.memory_tiers.keys()))
        
        raise StorageError("No memory tiers available")
    
    async def _update_access_counts(self, results: List[ScoredRecord]) -> None:
        """Update access counts for retrieved memories."""
        for scored_record in results:
            record = scored_record.record
            
            # Increment access count
            current_count = record.metadata.get("access_count", 0)
            record.metadata["access_count"] = current_count + 1
            record.metadata["last_accessed"] = datetime.utcnow().isoformat()
            
            # Try to update in the source tier
            tier_name = scored_record.tier_source
            if tier_name in self.registry.memory_tiers:
                try:
                    tier = self.registry.memory_tiers[tier_name]
                    await tier.store_memory(record)  # Update existing record
                except Exception as e:
                    self.logger.debug(f"Could not update access count in tier {tier_name}: {e}")
    
    async def _session_cleanup_loop(self) -> None:
        """Background loop to clean up inactive sessions."""
        while self._running:
            try:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)  # 24-hour timeout
                
                expired_sessions = [
                    session_id for session_id, session in self.active_sessions.items()
                    if session.last_activity < cutoff_time
                ]
                
                for session_id in expired_sessions:
                    await self._cleanup_session(session_id)
                
                # Wait 1 hour before next cleanup
                await asyncio.sleep(3600)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.warning(f"Error in session cleanup loop: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_session(self, session_id: str) -> None:
        """Clean up a specific session."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            self.logger.debug(f"Cleaned up session {session_id}")
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform main system health check."""
        if not self._initialized:
            return {
                "status": "unhealthy",
                "reason": "not_initialized"
            }
        
        # Basic functionality test
        try:
            # Test storage
            test_record_id = await self.store_memory(
                content="health_check_test",
                metadata={"test": True},
                importance=0.1
            )
            
            # Test retrieval
            results = await self.search_memories("health_check_test", limit=1)
            
            # Cleanup
            await self.delete_memory(test_record_id)
            
            test_success = len(results) > 0
        except Exception as e:
            test_success = False
            self.logger.debug(f"Health check test failed: {e}")
        
        return {
            "initialized": self._initialized,
            "running": self._running,
            "total_operations": self._total_operations,
            "success_rate": self._successful_operations / max(1, self._total_operations),
            "active_sessions": len(self.active_sessions),
            "available_tiers": len(self.registry.memory_tiers),
            "available_embedders": len(self.registry.embedding_providers),
            "basic_functionality_test": test_success
        }
    
    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()


# Convenience factory function
async def create_smrti_system(config: Optional[SmrtiConfig] = None) -> Smrti:
    """
    Create and initialize a Smrti system.
    
    Args:
        config: System configuration
        
    Returns:
        Initialized Smrti instance
    """
    smrti = Smrti(config)
    await smrti.initialize()
    return smrti


# Example usage patterns
if __name__ == "__main__":
    async def example_usage():
        """Example usage of the Smrti system."""
        
        # Basic usage with context manager
        async with Smrti() as smrti:
            # Store some memories
            memory_id = await smrti.store_memory(
                "Today I learned about neural networks",
                importance=0.8
            )
            
            # Search for memories
            results = await smrti.search_memories("neural networks")
            
            print(f"Found {len(results)} memories about neural networks")
        
        # Session-based usage
        smrti = await create_smrti_system()
        
        try:
            async with smrti.session(namespace="learning") as session:
                # Store memories in session context
                await session.store_memory("Machine learning is fascinating")
                await session.store_memory("I need to practice more coding")
                
                # Search within session
                results = await session.search_memories("learning")
                
                for result in results:
                    print(f"Memory: {result.record.content}")
        
        finally:
            await smrti.shutdown()
    
    # Run example
    asyncio.run(example_usage())