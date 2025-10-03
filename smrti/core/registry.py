"""
smrti/core/registry.py - Adapter registry and capability management

Provides centralized registry for all adapter types with capability negotiation,
discovery, and lifecycle management.
"""

import asyncio
from collections import defaultdict
from typing import Any, Dict, List, Optional, Type, TypeVar, cast

from smrti.core.exceptions import (
    AdapterNotFoundError,
    CapabilityNotSupportedError,
    ConfigurationError,
    SmrtiError
)
from smrti.core.protocols import (
    AdapterRegistry,
    ContextAssembler,
    EmbeddingProvider,
    GraphStore,
    LexicalIndex,
    LifecycleManager,
    SmrtiProvider,
    TierStore,
    VectorStore
)

T = TypeVar('T')


class AdapterCapability:
    """
    Represents a capability that an adapter can provide.
    
    Used for adapter discovery and compatibility checking.
    """
    
    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        requirements: Dict[str, Any] | None = None
    ):
        self.name = name
        self.version = version
        self.description = description
        self.requirements = requirements or {}
    
    def is_compatible_with(self, required_version: str) -> bool:
        """
        Check if this capability version is compatible with required version.
        
        Uses semantic versioning compatibility rules.
        """
        try:
            current_parts = [int(x) for x in self.version.split('.')]
            required_parts = [int(x) for x in required_version.split('.')]
            
            # Pad shorter version with zeros
            max_len = max(len(current_parts), len(required_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            required_parts.extend([0] * (max_len - len(required_parts)))
            
            # Major version must match, minor/patch can be >= required
            if current_parts[0] != required_parts[0]:
                return False
                
            # Check if current version >= required version
            for i in range(1, max_len):
                if current_parts[i] > required_parts[i]:
                    return True
                elif current_parts[i] < required_parts[i]:
                    return False
            
            return True  # Versions are equal
            
        except (ValueError, IndexError):
            return False
    
    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class AdapterInfo:
    """
    Metadata about a registered adapter.
    
    Includes capability information, health status, and configuration.
    """
    
    def __init__(
        self,
        name: str,
        adapter_type: str,
        instance: Any,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ):
        self.name = name
        self.adapter_type = adapter_type
        self.instance = instance
        self.capabilities = capabilities or []
        self.config = config or {}
        self.is_healthy = True
        self.last_health_check: Optional[str] = None
        self.error_count = 0
        self.last_error: Optional[Exception] = None
    
    def add_capability(self, capability: AdapterCapability) -> None:
        """Add a capability to this adapter."""
        self.capabilities.append(capability)
    
    def has_capability(self, capability_name: str, version: str | None = None) -> bool:
        """Check if adapter has a specific capability."""
        for cap in self.capabilities:
            if cap.name == capability_name:
                if version is None or cap.is_compatible_with(version):
                    return True
        return False
    
    def get_capability(self, capability_name: str) -> AdapterCapability | None:
        """Get specific capability by name."""
        for cap in self.capabilities:
            if cap.name == capability_name:
                return cap
        return None
    
    def mark_error(self, error: Exception) -> None:
        """Record an error for this adapter."""
        self.error_count += 1
        self.last_error = error
        self.is_healthy = False
    
    def mark_healthy(self) -> None:
        """Mark adapter as healthy."""
        self.is_healthy = True
        self.last_error = None


class SmrtiAdapterRegistry(AdapterRegistry):
    """
    Central registry for all Smrti adapters.
    
    Manages adapter lifecycle, capability negotiation, and health monitoring.
    """
    
    def __init__(self):
        # Core registries by adapter type
        self._embedding_providers: Dict[str, AdapterInfo] = {}
        self._tier_stores: Dict[str, AdapterInfo] = {}
        self._vector_stores: Dict[str, AdapterInfo] = {}
        self._graph_stores: Dict[str, AdapterInfo] = {}
        self._lexical_indices: Dict[str, AdapterInfo] = {}
        self._context_assemblers: Dict[str, AdapterInfo] = {}
        self._lifecycle_managers: Dict[str, AdapterInfo] = {}
        self._smrti_providers: Dict[str, AdapterInfo] = {}
        
        # Global capability index
        self._capabilities: Dict[str, List[AdapterInfo]] = defaultdict(list)
        
        # Configuration
        self._default_providers: Dict[str, str] = {}
        self._health_check_interval = 300  # 5 minutes
        self._auto_discovery_enabled = True
    
    def register_embedding_provider(
        self, 
        name: str, 
        provider: EmbeddingProvider,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register an embedding provider with capability metadata."""
        info = AdapterInfo(
            name=name,
            adapter_type="embedding_provider",
            instance=provider,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        # Add standard embedding capabilities
        if not info.has_capability("text_embedding"):
            info.add_capability(AdapterCapability(
                name="text_embedding",
                version="1.0.0",
                description="Generate dense embeddings from text"
            ))
        
        if hasattr(provider, 'embed_batch'):
            info.add_capability(AdapterCapability(
                name="batch_embedding",
                version="1.0.0",
                description="Generate embeddings in batches"
            ))
        
        self._embedding_providers[name] = info
        self._update_capability_index(info)
    
    def register_tier_store(
        self, 
        tier_name: str, 
        store: TierStore,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register a tier storage adapter."""
        info = AdapterInfo(
            name=tier_name,
            adapter_type="tier_store", 
            instance=store,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        # Add standard tier store capabilities
        info.add_capability(AdapterCapability(
            name="memory_storage",
            version="1.0.0",
            description="Store and retrieve memory records"
        ))
        
        if store.supports_ttl:
            info.add_capability(AdapterCapability(
                name="ttl_expiration",
                version="1.0.0",
                description="Automatic record expiration"
            ))
        
        if store.supports_similarity_search:
            info.add_capability(AdapterCapability(
                name="similarity_search",
                version="1.0.0", 
                description="Vector similarity search"
            ))
        
        self._tier_stores[tier_name] = info
        self._update_capability_index(info)
    
    def register_vector_store(
        self, 
        name: str, 
        store: VectorStore,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register a vector storage adapter."""
        info = AdapterInfo(
            name=name,
            adapter_type="vector_store",
            instance=store,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        # Add standard vector store capabilities  
        info.add_capability(AdapterCapability(
            name="vector_storage",
            version="1.0.0",
            description="Store and search high-dimensional vectors"
        ))
        
        info.add_capability(AdapterCapability(
            name="similarity_search",
            version="1.0.0",
            description="K-nearest neighbor vector search"
        ))
        
        self._vector_stores[name] = info
        self._update_capability_index(info)
    
    def register_graph_store(
        self, 
        name: str, 
        store: GraphStore,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register a graph storage adapter."""
        info = AdapterInfo(
            name=name,
            adapter_type="graph_store",
            instance=store,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        # Add standard graph store capabilities
        info.add_capability(AdapterCapability(
            name="graph_storage",
            version="1.0.0",
            description="Store entities and relationships"
        ))
        
        info.add_capability(AdapterCapability(
            name="graph_traversal",
            version="1.0.0",
            description="Navigate entity relationships"
        ))
        
        self._graph_stores[name] = info
        self._update_capability_index(info)
    
    def register_lexical_index(
        self, 
        name: str, 
        index: LexicalIndex,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register a lexical index adapter."""
        info = AdapterInfo(
            name=name,
            adapter_type="lexical_index",
            instance=index,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        # Add standard lexical index capabilities
        info.add_capability(AdapterCapability(
            name="text_search",
            version="1.0.0",
            description="Full-text search and indexing"
        ))
        
        if hasattr(index, 'phrase_search'):
            info.add_capability(AdapterCapability(
                name="phrase_search", 
                version="1.0.0",
                description="Exact phrase matching"
            ))
        
        self._lexical_indices[name] = info
        self._update_capability_index(info)
    
    def register_context_assembler(
        self,
        name: str,
        assembler: ContextAssembler,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register a context assembler."""
        info = AdapterInfo(
            name=name,
            adapter_type="context_assembler",
            instance=assembler,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        info.add_capability(AdapterCapability(
            name="context_assembly",
            version="1.0.0",
            description="Assemble unified context from memory tiers"
        ))
        
        self._context_assemblers[name] = info
        self._update_capability_index(info)
    
    def register_lifecycle_manager(
        self,
        name: str,
        manager: LifecycleManager,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register a lifecycle manager."""
        info = AdapterInfo(
            name=name,
            adapter_type="lifecycle_manager",
            instance=manager,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        info.add_capability(AdapterCapability(
            name="memory_lifecycle",
            version="1.0.0",
            description="Memory consolidation and cleanup"
        ))
        
        self._lifecycle_managers[name] = info
        self._update_capability_index(info)
    
    def register_smrti_provider(
        self,
        name: str,
        provider: SmrtiProvider,
        capabilities: List[AdapterCapability] | None = None,
        config: Dict[str, Any] | None = None
    ) -> None:
        """Register a complete Smrti provider."""
        info = AdapterInfo(
            name=name,
            adapter_type="smrti_provider",
            instance=provider,
            capabilities=capabilities or [],
            config=config or {}
        )
        
        info.add_capability(AdapterCapability(
            name="memory_system",
            version="1.0.0",
            description="Complete multi-tier memory system"
        ))
        
        self._smrti_providers[name] = info
        self._update_capability_index(info)
    
    def get_embedding_provider(self, name: str | None = None) -> EmbeddingProvider:
        """Get registered embedding provider."""
        if name is None:
            name = self._default_providers.get("embedding_provider")
        
        if not name:
            # Try to find any available provider
            if self._embedding_providers:
                name = next(iter(self._embedding_providers.keys()))
            else:
                raise AdapterNotFoundError("", "embedding_provider")
        
        if name not in self._embedding_providers:
            raise AdapterNotFoundError(name, "embedding_provider")
        
        return cast(EmbeddingProvider, self._embedding_providers[name].instance)
    
    def get_tier_store(self, tier_name: str) -> TierStore:
        """Get registered tier store."""
        if tier_name not in self._tier_stores:
            raise AdapterNotFoundError(tier_name, "tier_store")
        
        return cast(TierStore, self._tier_stores[tier_name].instance)
    
    def get_vector_store(self, name: str | None = None) -> VectorStore:
        """Get registered vector store."""
        if name is None:
            name = self._default_providers.get("vector_store")
        
        if not name:
            if self._vector_stores:
                name = next(iter(self._vector_stores.keys()))
            else:
                raise AdapterNotFoundError("", "vector_store")
        
        if name not in self._vector_stores:
            raise AdapterNotFoundError(name, "vector_store")
        
        return cast(VectorStore, self._vector_stores[name].instance)
    
    def get_graph_store(self, name: str | None = None) -> GraphStore:
        """Get registered graph store."""
        if name is None:
            name = self._default_providers.get("graph_store")
        
        if not name:
            if self._graph_stores:
                name = next(iter(self._graph_stores.keys()))
            else:
                raise AdapterNotFoundError("", "graph_store")
        
        if name not in self._graph_stores:
            raise AdapterNotFoundError(name, "graph_store")
        
        return cast(GraphStore, self._graph_stores[name].instance)
    
    def get_lexical_index(self, name: str | None = None) -> LexicalIndex:
        """Get registered lexical index."""
        if name is None:
            name = self._default_providers.get("lexical_index")
        
        if not name:
            if self._lexical_indices:
                name = next(iter(self._lexical_indices.keys()))
            else:
                raise AdapterNotFoundError("", "lexical_index")
        
        if name not in self._lexical_indices:
            raise AdapterNotFoundError(name, "lexical_index")
        
        return cast(LexicalIndex, self._lexical_indices[name].instance)
    
    def get_context_assembler(self, name: str | None = None) -> ContextAssembler:
        """Get registered context assembler."""
        if name is None:
            name = self._default_providers.get("context_assembler")
        
        if not name:
            if self._context_assemblers:
                name = next(iter(self._context_assemblers.keys()))
            else:
                raise AdapterNotFoundError("", "context_assembler")
        
        if name not in self._context_assemblers:
            raise AdapterNotFoundError(name, "context_assembler")
        
        return cast(ContextAssembler, self._context_assemblers[name].instance)
    
    def get_lifecycle_manager(self, name: str | None = None) -> LifecycleManager:
        """Get registered lifecycle manager.""" 
        if name is None:
            name = self._default_providers.get("lifecycle_manager")
        
        if not name:
            if self._lifecycle_managers:
                name = next(iter(self._lifecycle_managers.keys()))
            else:
                raise AdapterNotFoundError("", "lifecycle_manager")
        
        if name not in self._lifecycle_managers:
            raise AdapterNotFoundError(name, "lifecycle_manager")
        
        return cast(LifecycleManager, self._lifecycle_managers[name].instance)
    
    def get_smrti_provider(self, name: str | None = None) -> SmrtiProvider:
        """Get registered Smrti provider."""
        if name is None:
            name = self._default_providers.get("smrti_provider")
        
        if not name:
            if self._smrti_providers:
                name = next(iter(self._smrti_providers.keys()))
            else:
                raise AdapterNotFoundError("", "smrti_provider")
        
        if name not in self._smrti_providers:
            raise AdapterNotFoundError(name, "smrti_provider")
        
        return cast(SmrtiProvider, self._smrti_providers[name].instance)
    
    def list_capabilities(self) -> Dict[str, List[str]]:
        """List available adapters by capability type."""
        result = defaultdict(list)
        
        for capability_name, adapters in self._capabilities.items():
            result[capability_name] = [
                f"{adapter.adapter_type}:{adapter.name}" 
                for adapter in adapters 
                if adapter.is_healthy
            ]
        
        return dict(result)
    
    def check_requirements(
        self, 
        requirements: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Check if system meets capability requirements."""
        results = {}
        
        for requirement, spec in requirements.items():
            if isinstance(spec, str):
                # Simple capability name check
                results[requirement] = requirement in self._capabilities
            elif isinstance(spec, dict):
                # Complex requirement with version/config
                capability_name = spec.get("capability")
                required_version = spec.get("version")
                
                if capability_name not in self._capabilities:
                    results[requirement] = False
                    continue
                
                # Check if any adapter meets the requirement
                met = False
                for adapter in self._capabilities[capability_name]:
                    if adapter.has_capability(capability_name, required_version):
                        met = True
                        break
                
                results[requirement] = met
            else:
                results[requirement] = False
        
        return results
    
    def set_default_provider(self, adapter_type: str, name: str) -> None:
        """Set default provider for an adapter type."""
        self._default_providers[adapter_type] = name
    
    def get_adapter_info(self, name: str, adapter_type: str | None = None) -> AdapterInfo | None:
        """Get detailed information about a registered adapter."""
        registries = [
            self._embedding_providers,
            self._tier_stores,
            self._vector_stores,
            self._graph_stores,
            self._lexical_indices,
            self._context_assemblers,
            self._lifecycle_managers,
            self._smrti_providers
        ]
        
        if adapter_type:
            # Search specific registry
            registry_map = {
                "embedding_provider": self._embedding_providers,
                "tier_store": self._tier_stores,
                "vector_store": self._vector_stores,
                "graph_store": self._graph_stores,
                "lexical_index": self._lexical_indices,
                "context_assembler": self._context_assemblers,
                "lifecycle_manager": self._lifecycle_managers,
                "smrti_provider": self._smrti_providers
            }
            
            if adapter_type in registry_map:
                return registry_map[adapter_type].get(name)
        else:
            # Search all registries
            for registry in registries:
                if name in registry:
                    return registry[name]
        
        return None
    
    def list_adapters(self, adapter_type: str | None = None) -> Dict[str, AdapterInfo]:
        """List all registered adapters, optionally filtered by type."""
        if adapter_type is None:
            # Return all adapters
            result = {}
            for registry in [
                self._embedding_providers,
                self._tier_stores,
                self._vector_stores,
                self._graph_stores,
                self._lexical_indices,
                self._context_assemblers,
                self._lifecycle_managers,
                self._smrti_providers
            ]:
                result.update(registry)
            return result
        
        # Return adapters of specific type
        registry_map = {
            "embedding_provider": self._embedding_providers,
            "tier_store": self._tier_stores,
            "vector_store": self._vector_stores,
            "graph_store": self._graph_stores,
            "lexical_index": self._lexical_indices,
            "context_assembler": self._context_assemblers,
            "lifecycle_manager": self._lifecycle_managers,
            "smrti_provider": self._smrti_providers
        }
        
        return dict(registry_map.get(adapter_type, {}))
    
    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Perform health check on all registered adapters."""
        results = {}
        
        all_adapters = self.list_adapters()
        
        for name, adapter_info in all_adapters.items():
            try:
                # Try to call health_check method if available
                if hasattr(adapter_info.instance, 'health_check'):
                    health_data = await adapter_info.instance.health_check()
                    adapter_info.mark_healthy()
                    results[name] = {
                        "status": "healthy",
                        "type": adapter_info.adapter_type,
                        "capabilities": [str(cap) for cap in adapter_info.capabilities],
                        "details": health_data
                    }
                else:
                    # Assume healthy if no health check method
                    adapter_info.mark_healthy()
                    results[name] = {
                        "status": "healthy",
                        "type": adapter_info.adapter_type,
                        "capabilities": [str(cap) for cap in adapter_info.capabilities],
                        "details": {"message": "No health check available"}
                    }
            
            except Exception as e:
                adapter_info.mark_error(e)
                results[name] = {
                    "status": "unhealthy",
                    "type": adapter_info.adapter_type,
                    "error": str(e),
                    "error_count": adapter_info.error_count
                }
        
        return results
    
    def _update_capability_index(self, adapter_info: AdapterInfo) -> None:
        """Update the global capability index with adapter capabilities."""
        for capability in adapter_info.capabilities:
            self._capabilities[capability.name].append(adapter_info)


# Global registry instance
_global_registry: Optional[SmrtiAdapterRegistry] = None


def get_global_registry() -> SmrtiAdapterRegistry:
    """Get the global adapter registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SmrtiAdapterRegistry()
    return _global_registry


def set_global_registry(registry: SmrtiAdapterRegistry) -> None:
    """Set a custom global registry instance."""
    global _global_registry
    _global_registry = registry