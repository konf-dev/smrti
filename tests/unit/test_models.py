"""
tests/unit/test_models.py - Unit tests for data models

Tests the core Pydantic models used throughout the system.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any

from smrti.schemas.models import (
    MemoryRecord,
    RecordEnvelope, 
    MemoryQuery,
    TextContent
)


class TestTextContent:
    """Test TextContent model."""
    
    def test_create_text_content(self):
        """Test creating text content."""
        content = TextContent(text="Hello world")
        
        assert content.text == "Hello world"
        assert content.content_type == "text"
        assert content.get_text() == "Hello world"
    
    def test_empty_text_validation(self):
        """Test validation of empty text."""
        with pytest.raises(ValueError):
            TextContent(text="")
    
    def test_whitespace_text_validation(self):
        """Test validation of whitespace-only text."""
        with pytest.raises(ValueError):
            TextContent(text="   ")
    
    def test_text_content_serialization(self):
        """Test serialization/deserialization."""
        content = TextContent(text="Test content")
        
        # Test dict conversion
        data = content.model_dump()
        assert data["text"] == "Test content"
        assert data["content_type"] == "text"
        
        # Test reconstruction
        content2 = TextContent.model_validate(data)
        assert content2.text == content.text
        assert content2.content_type == content.content_type


class TestMemoryQuery:
    """Test MemoryQuery model."""
    
    def test_create_basic_query(self):
        """Test creating basic memory query."""
        query = MemoryQuery(
            query_text="test query",
            tenant_id="user123", 
            namespace="default"
        )
        
        assert query.query_text == "test query"
        assert query.tenant_id == "user123"
        assert query.namespace == "default"
        assert query.limit == 10  # Default value
        assert query.similarity_threshold == 0.1  # Default value
    
    def test_create_query_with_all_fields(self):
        """Test creating query with all optional fields."""
        now = datetime.utcnow()
        
        query = MemoryQuery(
            query_text="advanced query",
            tenant_id="user456",
            namespace="test_ns",
            limit=50,
            similarity_threshold=0.8,
            time_range_hours=24,
            created_after=now - timedelta(days=1),
            created_before=now,
            metadata_filters={"category": "important"},
            embedding=[0.1, 0.2, 0.3]
        )
        
        assert query.query_text == "advanced query"
        assert query.limit == 50
        assert query.similarity_threshold == 0.8
        assert query.time_range_hours == 24
        assert query.metadata_filters == {"category": "important"}
        assert query.embedding == [0.1, 0.2, 0.3]
    
    def test_query_validation(self):
        """Test query parameter validation."""
        # Test invalid similarity threshold
        with pytest.raises(ValueError):
            MemoryQuery(
                query_text="test",
                tenant_id="user",
                namespace="default",
                similarity_threshold=1.5  # Invalid: > 1.0
            )
        
        with pytest.raises(ValueError):
            MemoryQuery(
                query_text="test", 
                tenant_id="user",
                namespace="default",
                similarity_threshold=-0.1  # Invalid: < 0.0
            )
        
        # Test invalid limit
        with pytest.raises(ValueError):
            MemoryQuery(
                query_text="test",
                tenant_id="user", 
                namespace="default",
                limit=0  # Invalid: must be positive
            )
    
    def test_query_copy_with_changes(self):
        """Test copying query with modifications."""
        original = MemoryQuery(
            query_text="original",
            tenant_id="user1",
            namespace="ns1"
        )
        
        # Test model_copy functionality
        modified = original.model_copy(update={"query_text": "modified", "limit": 20})
        
        assert modified.query_text == "modified"
        assert modified.limit == 20
        assert modified.tenant_id == "user1"  # Unchanged
        assert modified.namespace == "ns1"    # Unchanged


class TestRecordEnvelope:
    """Test RecordEnvelope model."""
    
    def test_create_record_envelope(self):
        """Test creating record envelope."""
        content = TextContent(text="Test content")
        
        record = RecordEnvelope(
            record_id="rec123",
            tenant_id="user456", 
            namespace="test_ns",
            content=content
        )
        
        assert record.record_id == "rec123"
        assert record.tenant_id == "user456"
        assert record.namespace == "test_ns"
        assert record.content == content
        assert isinstance(record.metadata, dict)
        assert record.created_at is not None
        assert record.updated_at is not None
    
    def test_record_with_metadata_and_embedding(self):
        """Test record with metadata and embedding."""
        content = TextContent(text="Content with metadata")
        metadata = {"importance": 0.8, "category": "test"}
        embedding = [0.1, 0.2, 0.3, 0.4]
        
        record = RecordEnvelope(
            record_id="rec456",
            tenant_id="user789",
            namespace="advanced_ns", 
            content=content,
            metadata=metadata,
            embedding=embedding
        )
        
        assert record.metadata == metadata
        assert record.embedding == embedding
    
    def test_record_validation(self):
        """Test record validation rules."""
        content = TextContent(text="Valid content")
        
        # Test empty record_id
        with pytest.raises(ValueError):
            RecordEnvelope(
                record_id="",
                tenant_id="user",
                namespace="ns",
                content=content
            )
        
        # Test empty tenant_id
        with pytest.raises(ValueError):
            RecordEnvelope(
                record_id="rec123",
                tenant_id="",
                namespace="ns", 
                content=content
            )
        
        # Test empty namespace
        with pytest.raises(ValueError):
            RecordEnvelope(
                record_id="rec123",
                tenant_id="user",
                namespace="",
                content=content
            )
    
    def test_record_timestamps(self):
        """Test timestamp handling."""
        content = TextContent(text="Timestamp test")
        
        # Test auto-generated timestamps
        record1 = RecordEnvelope(
            record_id="rec1",
            tenant_id="user",
            namespace="ns",
            content=content
        )
        
        assert record1.created_at is not None
        assert record1.updated_at is not None
        
        # Test explicit timestamps
        now = datetime.utcnow()
        earlier = now - timedelta(hours=1)
        
        record2 = RecordEnvelope(
            record_id="rec2",
            tenant_id="user",
            namespace="ns",
            content=content,
            created_at=earlier,
            updated_at=now
        )
        
        assert record2.created_at == earlier
        assert record2.updated_at == now
    
    def test_record_serialization(self):
        """Test record serialization and deserialization."""
        content = TextContent(text="Serialization test")
        metadata = {"test": True, "value": 42}
        embedding = [0.1, 0.2, 0.3]
        
        original = RecordEnvelope(
            record_id="ser_test",
            tenant_id="user_ser",
            namespace="ser_ns",
            content=content,
            metadata=metadata,
            embedding=embedding
        )
        
        # Serialize to dict
        data = original.model_dump()
        
        # Verify serialized data
        assert data["record_id"] == "ser_test"
        assert data["tenant_id"] == "user_ser"
        assert data["namespace"] == "ser_ns"
        assert data["metadata"] == metadata
        assert data["embedding"] == embedding
        
        # Deserialize back
        restored = RecordEnvelope.model_validate(data)
        
        assert restored.record_id == original.record_id
        assert restored.tenant_id == original.tenant_id
        assert restored.namespace == original.namespace
        assert restored.content.text == original.content.text
        assert restored.metadata == original.metadata
        assert restored.embedding == original.embedding


class TestMemoryRecord:
    """Test MemoryRecord model."""
    
    def test_create_memory_record(self):
        """Test creating memory record."""
        content = TextContent(text="Memory record test")
        
        record = MemoryRecord(
            content=content,
            importance_score=0.7
        )
        
        assert record.content == content
        assert record.importance_score == 0.7
        assert isinstance(record.metadata, dict)
    
    def test_memory_record_validation(self):
        """Test memory record validation."""
        content = TextContent(text="Valid content")
        
        # Test invalid importance score
        with pytest.raises(ValueError):
            MemoryRecord(content=content, importance_score=1.5)
        
        with pytest.raises(ValueError):
            MemoryRecord(content=content, importance_score=-0.1)
    
    def test_memory_record_with_metadata(self):
        """Test memory record with metadata."""
        content = TextContent(text="Record with metadata")
        metadata = {
            "source": "test",
            "category": "unit_test",
            "tags": ["test", "memory"]
        }
        
        record = MemoryRecord(
            content=content,
            importance_score=0.5,
            metadata=metadata
        )
        
        assert record.metadata == metadata
    
    def test_memory_record_to_envelope(self):
        """Test converting memory record to envelope."""
        content = TextContent(text="Conversion test")
        metadata = {"test": True}
        
        record = MemoryRecord(
            content=content,
            importance_score=0.8,
            metadata=metadata
        )
        
        # Convert to envelope (would need implementation in actual model)
        # This tests the data structure compatibility
        envelope_data = {
            "record_id": "test_id",
            "tenant_id": "test_tenant",
            "namespace": "test_ns",
            "content": record.content,
            "metadata": record.metadata
        }
        
        envelope = RecordEnvelope.model_validate(envelope_data)
        
        assert envelope.content == record.content
        assert envelope.metadata == record.metadata


class TestModelInteractions:
    """Test interactions between different models."""
    
    def test_query_record_compatibility(self):
        """Test that queries can work with records."""
        # Create a record
        content = TextContent(text="Machine learning algorithms")
        record = RecordEnvelope(
            record_id="ml_record",
            tenant_id="data_scientist",
            namespace="ml_concepts",
            content=content,
            metadata={"category": "algorithms", "difficulty": "intermediate"}
        )
        
        # Create a query that should match
        query = MemoryQuery(
            query_text="machine learning",
            tenant_id="data_scientist",
            namespace="ml_concepts",
            metadata_filters={"category": "algorithms"}
        )
        
        # Basic compatibility checks
        assert query.tenant_id == record.tenant_id
        assert query.namespace == record.namespace
        
        # Check if metadata filter would match
        if query.metadata_filters:
            for key, value in query.metadata_filters.items():
                assert key in record.metadata
                assert record.metadata[key] == value
    
    def test_content_type_polymorphism(self):
        """Test that different content types can be used."""
        # TextContent
        text_content = TextContent(text="This is text content")
        
        record1 = RecordEnvelope(
            record_id="text_rec",
            tenant_id="user",
            namespace="test",
            content=text_content
        )
        
        assert record1.content.get_text() == "This is text content"
        
        # Could test other content types here when implemented
    
    def test_embedding_consistency(self):
        """Test embedding dimension consistency."""
        embedding_384 = [0.1] * 384  # 384-dimensional embedding
        embedding_512 = [0.2] * 512  # 512-dimensional embedding
        
        content = TextContent(text="Embedding test")
        
        # Records should accept embeddings of different dimensions
        record1 = RecordEnvelope(
            record_id="emb1",
            tenant_id="user", 
            namespace="test",
            content=content,
            embedding=embedding_384
        )
        
        record2 = RecordEnvelope(
            record_id="emb2",
            tenant_id="user",
            namespace="test", 
            content=content,
            embedding=embedding_512
        )
        
        assert len(record1.embedding) == 384
        assert len(record2.embedding) == 512
        
        # Queries should also accept embeddings
        query = MemoryQuery(
            query_text="test",
            tenant_id="user",
            namespace="test",
            embedding=embedding_384
        )
        
        assert len(query.embedding) == 384


@pytest.fixture
def sample_text_content():
    """Fixture providing sample text content."""
    return TextContent(text="This is sample text for testing")


@pytest.fixture  
def sample_record_envelope(sample_text_content):
    """Fixture providing sample record envelope."""
    return RecordEnvelope(
        record_id="sample_record",
        tenant_id="test_tenant",
        namespace="test_namespace", 
        content=sample_text_content,
        metadata={"test": True, "fixture": "sample"}
    )


@pytest.fixture
def sample_memory_query():
    """Fixture providing sample memory query."""
    return MemoryQuery(
        query_text="sample query",
        tenant_id="test_tenant",
        namespace="test_namespace",
        limit=5
    )


class TestFixtures:
    """Test that our fixtures work correctly."""
    
    def test_sample_content_fixture(self, sample_text_content):
        """Test sample text content fixture."""
        assert isinstance(sample_text_content, TextContent)
        assert sample_text_content.text == "This is sample text for testing"
    
    def test_sample_record_fixture(self, sample_record_envelope):
        """Test sample record envelope fixture.""" 
        assert isinstance(sample_record_envelope, RecordEnvelope)
        assert sample_record_envelope.record_id == "sample_record"
        assert sample_record_envelope.metadata["test"] is True
    
    def test_sample_query_fixture(self, sample_memory_query):
        """Test sample memory query fixture."""
        assert isinstance(sample_memory_query, MemoryQuery)
        assert sample_memory_query.query_text == "sample query"
        assert sample_memory_query.limit == 5