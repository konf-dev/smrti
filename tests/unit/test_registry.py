"""
tests/unit/test_registry.py - Unit tests for registry components

Tests the registry system used for component discovery and management.
"""

import pytest
from typing import Dict, Any, Optional, List

from smrti.core.registry import (
    AdapterRegistry,
    MemoryTierRegistry,
    EngineRegistry
)
from smrti.core.exceptions import (
    SmrtiError,
    ConfigurationError,
    AdapterError
)


class MockAdapter:
    """Mock adapter for testing registry functionality."""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.is_initialized = False
    
    async def initialize(self):
        """Mock initialization."""
        self.is_initialized = True
    
    async def cleanup(self):
        """Mock cleanup."""
        self.is_initialized = False


class MockMemoryTier:
    """Mock memory tier for testing registry functionality."""
    
    def __init__(self, tier_name: str, config: Optional[Dict[str, Any]] = None):
        self.tier_name = tier_name
        self.config = config or {}
        self.is_active = False
    
    async def activate(self):
        """Mock activation."""
        self.is_active = True
    
    async def deactivate(self):
        """Mock deactivation."""
        self.is_active = False


class MockEngine:
    """Mock engine for testing registry functionality."""
    
    def __init__(self, engine_type: str, dependencies: Optional[List[str]] = None):
        self.engine_type = engine_type
        self.dependencies = dependencies or []
        self.is_running = False
    
    async def start(self):
        """Mock start."""
        self.is_running = True
    
    async def stop(self):
        """Mock stop."""
        self.is_running = False


class TestAdapterRegistry:
    """Test AdapterRegistry functionality."""
    
    def test_create_empty_registry(self):
        """Test creating empty adapter registry."""
        registry = AdapterRegistry()
        
        assert len(registry.list_adapters()) == 0
        assert not registry.has_adapter("nonexistent")
    
    def test_register_adapter(self):
        """Test registering an adapter."""
        registry = AdapterRegistry()
        adapter = MockAdapter("test_adapter")
        
        registry.register_adapter("test_adapter", adapter)
        
        assert registry.has_adapter("test_adapter")
        assert len(registry.list_adapters()) == 1
        assert "test_adapter" in registry.list_adapters()
    
    def test_get_adapter(self):
        """Test retrieving registered adapter."""
        registry = AdapterRegistry()
        adapter = MockAdapter("retrieve_test")
        
        registry.register_adapter("retrieve_test", adapter)
        retrieved = registry.get_adapter("retrieve_test")
        
        assert retrieved is adapter
        assert retrieved.name == "retrieve_test"
    
    def test_get_nonexistent_adapter(self):
        """Test retrieving non-existent adapter raises error."""
        registry = AdapterRegistry()
        
        with pytest.raises(AdapterError) as exc_info:
            registry.get_adapter("nonexistent")
        
        assert "not found" in str(exc_info.value).lower()
        assert "nonexistent" in str(exc_info.value)
    
    def test_duplicate_registration_error(self):
        """Test that duplicate registration raises error."""
        registry = AdapterRegistry()
        adapter1 = MockAdapter("duplicate")
        adapter2 = MockAdapter("duplicate")
        
        registry.register_adapter("duplicate", adapter1)
        
        with pytest.raises(ConfigurationError) as exc_info:
            registry.register_adapter("duplicate", adapter2)
        
        assert "already registered" in str(exc_info.value).lower()
    
    def test_unregister_adapter(self):
        """Test unregistering an adapter."""
        registry = AdapterRegistry()
        adapter = MockAdapter("to_unregister")
        
        registry.register_adapter("to_unregister", adapter)
        assert registry.has_adapter("to_unregister")
        
        registry.unregister_adapter("to_unregister")
        assert not registry.has_adapter("to_unregister")
        assert len(registry.list_adapters()) == 0
    
    def test_unregister_nonexistent_adapter(self):
        """Test unregistering non-existent adapter raises error."""
        registry = AdapterRegistry()
        
        with pytest.raises(AdapterError) as exc_info:
            registry.unregister_adapter("nonexistent")
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_list_adapters_types(self):
        """Test listing adapters with type filtering."""
        registry = AdapterRegistry()
        
        # Register different adapter types
        redis_adapter = MockAdapter("redis")
        chroma_adapter = MockAdapter("chroma")
        postgres_adapter = MockAdapter("postgres")
        
        registry.register_adapter("redis", redis_adapter, adapter_type="storage")
        registry.register_adapter("chroma", chroma_adapter, adapter_type="vector")
        registry.register_adapter("postgres", postgres_adapter, adapter_type="storage")
        
        # Test listing all
        all_adapters = registry.list_adapters()
        assert len(all_adapters) == 3
        
        # Test listing by type
        storage_adapters = registry.list_adapters(adapter_type="storage")
        assert len(storage_adapters) == 2
        assert "redis" in storage_adapters
        assert "postgres" in storage_adapters
        
        vector_adapters = registry.list_adapters(adapter_type="vector")
        assert len(vector_adapters) == 1
        assert "chroma" in vector_adapters
    
    @pytest.mark.asyncio
    async def test_initialize_all_adapters(self):
        """Test initializing all registered adapters."""
        registry = AdapterRegistry()
        
        adapter1 = MockAdapter("adapter1")
        adapter2 = MockAdapter("adapter2")
        
        registry.register_adapter("adapter1", adapter1)
        registry.register_adapter("adapter2", adapter2)
        
        assert not adapter1.is_initialized
        assert not adapter2.is_initialized
        
        await registry.initialize_all()
        
        assert adapter1.is_initialized
        assert adapter2.is_initialized
    
    @pytest.mark.asyncio
    async def test_cleanup_all_adapters(self):
        """Test cleaning up all registered adapters."""
        registry = AdapterRegistry()
        
        adapter1 = MockAdapter("cleanup1")
        adapter2 = MockAdapter("cleanup2")
        
        registry.register_adapter("cleanup1", adapter1)
        registry.register_adapter("cleanup2", adapter2)
        
        # Initialize first
        await registry.initialize_all()
        assert adapter1.is_initialized
        assert adapter2.is_initialized
        
        # Then cleanup
        await registry.cleanup_all()
        assert not adapter1.is_initialized
        assert not adapter2.is_initialized


class TestMemoryTierRegistry:
    """Test MemoryTierRegistry functionality."""
    
    def test_create_tier_registry(self):
        """Test creating tier registry."""
        registry = MemoryTierRegistry()
        
        assert len(registry.list_tiers()) == 0
        assert not registry.has_tier("nonexistent")
    
    def test_register_memory_tier(self):
        """Test registering a memory tier."""
        registry = MemoryTierRegistry()
        tier = MockMemoryTier("working_memory")
        
        registry.register_tier("working", tier)
        
        assert registry.has_tier("working")
        assert "working" in registry.list_tiers()
    
    def test_get_memory_tier(self):
        """Test retrieving memory tier."""
        registry = MemoryTierRegistry()
        tier = MockMemoryTier("short_term")
        
        registry.register_tier("short_term", tier)
        retrieved = registry.get_tier("short_term")
        
        assert retrieved is tier
        assert retrieved.tier_name == "short_term"
    
    def test_tier_ordering(self):
        """Test tier ordering functionality."""
        registry = MemoryTierRegistry()
        
        working = MockMemoryTier("working")
        short_term = MockMemoryTier("short_term")
        long_term = MockMemoryTier("long_term")
        
        registry.register_tier("working", working, priority=1)
        registry.register_tier("short_term", short_term, priority=2)
        registry.register_tier("long_term", long_term, priority=3)
        
        # Test ordered retrieval
        ordered_tiers = registry.get_tiers_by_priority()
        tier_names = [name for name, _ in ordered_tiers]
        
        assert tier_names == ["working", "short_term", "long_term"]
    
    def test_tier_hierarchy_validation(self):
        """Test validation of tier hierarchy."""
        registry = MemoryTierRegistry()
        
        # Test that duplicate priorities are handled
        tier1 = MockMemoryTier("tier1")
        tier2 = MockMemoryTier("tier2")
        
        registry.register_tier("tier1", tier1, priority=1)
        
        with pytest.raises(ConfigurationError):
            registry.register_tier("tier2", tier2, priority=1)  # Duplicate priority
    
    @pytest.mark.asyncio
    async def test_activate_tier_cascade(self):
        """Test activating tiers in cascade."""
        registry = MemoryTierRegistry()
        
        working = MockMemoryTier("working")
        short_term = MockMemoryTier("short_term") 
        
        registry.register_tier("working", working, priority=1)
        registry.register_tier("short_term", short_term, priority=2)
        
        await registry.activate_tier_cascade("short_term")
        
        # Both tiers should be active (cascade activation)
        assert working.is_active
        assert short_term.is_active


class TestEngineRegistry:
    """Test EngineRegistry functionality."""
    
    def test_create_engine_registry(self):
        """Test creating engine registry."""
        registry = EngineRegistry()
        
        assert len(registry.list_engines()) == 0
        assert not registry.has_engine("nonexistent")
    
    def test_register_engine(self):
        """Test registering an engine."""
        registry = EngineRegistry()
        engine = MockEngine("retrieval")
        
        registry.register_engine("retrieval", engine)
        
        assert registry.has_engine("retrieval")
        assert "retrieval" in registry.list_engines()
    
    def test_engine_dependencies(self):
        """Test engine dependency management."""
        registry = EngineRegistry()
        
        # Create engines with dependencies
        base_engine = MockEngine("base")
        dependent_engine = MockEngine("dependent", dependencies=["base"])
        
        registry.register_engine("base", base_engine)
        registry.register_engine("dependent", dependent_engine)
        
        # Test dependency resolution
        deps = registry.get_dependencies("dependent")
        assert "base" in deps
    
    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies."""
        registry = EngineRegistry()
        
        engine_a = MockEngine("engine_a", dependencies=["engine_b"])
        engine_b = MockEngine("engine_b", dependencies=["engine_a"])
        
        registry.register_engine("engine_a", engine_a)
        
        with pytest.raises(ConfigurationError) as exc_info:
            registry.register_engine("engine_b", engine_b)
        
        assert "circular dependency" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_start_engines_ordered(self):
        """Test starting engines in dependency order."""
        registry = EngineRegistry()
        
        base = MockEngine("base")
        middle = MockEngine("middle", dependencies=["base"])
        top = MockEngine("top", dependencies=["middle"])
        
        registry.register_engine("base", base)
        registry.register_engine("middle", middle)  
        registry.register_engine("top", top)
        
        # Start all engines
        start_order = await registry.start_all_engines()
        
        # Verify all engines are running
        assert base.is_running
        assert middle.is_running
        assert top.is_running
        
        # Verify start order respects dependencies
        assert start_order.index("base") < start_order.index("middle")
        assert start_order.index("middle") < start_order.index("top")
    
    @pytest.mark.asyncio
    async def test_stop_engines_reverse_order(self):
        """Test stopping engines in reverse dependency order."""
        registry = EngineRegistry()
        
        base = MockEngine("base")
        dependent = MockEngine("dependent", dependencies=["base"])
        
        registry.register_engine("base", base)
        registry.register_engine("dependent", dependent)
        
        # Start then stop
        await registry.start_all_engines()
        assert base.is_running
        assert dependent.is_running
        
        stop_order = await registry.stop_all_engines()
        
        # Verify all engines are stopped
        assert not base.is_running
        assert not dependent.is_running
        
        # Verify stop order is reverse of start order
        assert stop_order.index("dependent") < stop_order.index("base")


class TestRegistryIntegration:
    """Test integration between different registry types."""
    
    def test_registry_composition(self):
        """Test using multiple registries together."""
        adapter_registry = AdapterRegistry()
        tier_registry = MemoryTierRegistry()
        engine_registry = EngineRegistry()
        
        # Register components
        adapter = MockAdapter("redis")
        tier = MockMemoryTier("working")
        engine = MockEngine("retrieval")
        
        adapter_registry.register_adapter("redis", adapter)
        tier_registry.register_tier("working", tier)
        engine_registry.register_engine("retrieval", engine)
        
        # Verify independent operation
        assert adapter_registry.has_adapter("redis")
        assert tier_registry.has_tier("working")
        assert engine_registry.has_engine("retrieval")
    
    @pytest.mark.asyncio
    async def test_coordinated_initialization(self):
        """Test coordinated initialization across registries."""
        adapter_registry = AdapterRegistry()
        tier_registry = MemoryTierRegistry()
        engine_registry = EngineRegistry()
        
        # Create components
        adapter = MockAdapter("test_adapter")
        tier = MockMemoryTier("test_tier")
        engine = MockEngine("test_engine")
        
        # Register components
        adapter_registry.register_adapter("test_adapter", adapter)
        tier_registry.register_tier("test_tier", tier)
        engine_registry.register_engine("test_engine", engine)
        
        # Initialize in order: adapters -> tiers -> engines
        await adapter_registry.initialize_all()
        await tier_registry.activate_all_tiers()
        await engine_registry.start_all_engines()
        
        # Verify all are active
        assert adapter.is_initialized
        assert tier.is_active
        assert engine.is_running
        
        # Cleanup in reverse order
        await engine_registry.stop_all_engines()
        await tier_registry.deactivate_all_tiers()
        await adapter_registry.cleanup_all()
        
        # Verify all are inactive
        assert not adapter.is_initialized
        assert not tier.is_active
        assert not engine.is_running


@pytest.fixture
def sample_adapter():
    """Fixture providing sample adapter."""
    return MockAdapter("sample_adapter", {"test_config": True})


@pytest.fixture
def sample_tier():
    """Fixture providing sample memory tier."""
    return MockMemoryTier("sample_tier", {"capacity": 1000})


@pytest.fixture
def sample_engine():
    """Fixture providing sample engine."""
    return MockEngine("sample_engine", dependencies=[])


class TestRegistryFixtures:
    """Test registry fixtures work correctly."""
    
    def test_adapter_fixture(self, sample_adapter):
        """Test sample adapter fixture."""
        assert isinstance(sample_adapter, MockAdapter)
        assert sample_adapter.name == "sample_adapter"
        assert sample_adapter.config["test_config"] is True
    
    def test_tier_fixture(self, sample_tier):
        """Test sample tier fixture."""
        assert isinstance(sample_tier, MockMemoryTier)
        assert sample_tier.tier_name == "sample_tier"
        assert sample_tier.config["capacity"] == 1000
    
    def test_engine_fixture(self, sample_engine):
        """Test sample engine fixture."""
        assert isinstance(sample_engine, MockEngine)
        assert sample_engine.engine_type == "sample_engine"
        assert len(sample_engine.dependencies) == 0