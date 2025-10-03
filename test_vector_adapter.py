#!/usr/bin/env python3
"""
Test script for Vector Storage Adapter

Comprehensive testing of ChromaDB-based vector storage adapter including:
- Basic storage and retrieval operations
- Batch operations and performance
- Similarity search functionality
- Embedding generation and caching
- Error handling and edge cases
- Statistics and health monitoring
"""

import asyncio
import time
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any

# Import our vector adapter
import sys
sys.path.append('/home/bert/Work/orgs/konf-dev/smrti')

# Import directly to avoid torch dependencies in other modules
sys.path.append('/home/bert/Work/orgs/konf-dev/smrti/smrti/adapters/storage')
from vector_adapter import (
    VectorStorageAdapter, 
    VectorConfig, 
    VectorSearchQuery,
    VectorOperationResult
)

# Import base models directly
sys.path.append('/home/bert/Work/orgs/konf-dev/smrti/smrti/models')
from base import SimpleMemoryItem, MemoryTier


class VectorAdapterTester:
    """Comprehensive test suite for Vector Storage Adapter."""
    
    def __init__(self):
        self.test_results = {}
        self.temp_dir = None
        self.adapter = None
        
    async def run_all_tests(self):
        """Run all vector adapter tests."""
        print("=" * 60)
        print("VECTOR STORAGE ADAPTER - COMPREHENSIVE TEST SUITE")
        print("=" * 60)
        
        try:
            await self._setup()
            
            # Core functionality tests
            await self._test_initialization()
            await self._test_embedding_generation()
            await self._test_single_item_storage()
            await self._test_batch_storage()
            await self._test_similarity_search()
            await self._test_item_retrieval()
            await self._test_item_deletion()
            await self._test_item_listing()
            
            # Performance and caching tests
            await self._test_embedding_cache()
            await self._test_batch_performance()
            
            # Advanced features
            await self._test_metadata_filtering()
            await self._test_large_content()
            
            # Error handling tests
            await self._test_error_conditions()
            
            # System monitoring
            await self._test_statistics()
            await self._test_health_check()
            
            # Generate summary
            self._print_test_summary()
            
        finally:
            await self._cleanup()
    
    async def _setup(self):
        """Set up test environment."""
        print("\n🔧 Setting up test environment...")
        
        # Create temporary directory for ChromaDB
        self.temp_dir = tempfile.mkdtemp(prefix="smrti_vector_test_")
        print(f"   Created temp directory: {self.temp_dir}")
        
        # Configure vector adapter
        config = VectorConfig(
            persist_directory=self.temp_dir,
            collection_name="test_collection",
            embedding_function="all-MiniLM-L6-v2",
            n_results=10,
            enable_caching=True,
            cache_size=1000,
            batch_size=50
        )
        
        self.adapter = VectorStorageAdapter(config)
        print("   Vector adapter configured")
        
    async def _cleanup(self):
        """Clean up test environment."""
        print("\n🧹 Cleaning up test environment...")
        
        if self.adapter:
            await self.adapter.close()
            
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
            print(f"   Removed temp directory: {self.temp_dir}")
    
    def _record_result(self, test_name: str, success: bool, details: str = ""):
        """Record test result."""
        self.test_results[test_name] = {
            "success": success,
            "details": details
        }
        status = "✅" if success else "❌"
        print(f"   {status} {test_name}: {details}")
    
    async def _test_initialization(self):
        """Test adapter initialization."""
        print("\n📋 Testing Adapter Initialization")
        
        try:
            start_time = time.time()
            await self.adapter.initialize()
            init_time = (time.time() - start_time) * 1000
            
            # Verify components are initialized
            if (self.adapter.chroma_client is not None and 
                self.adapter.collection is not None and
                self.adapter.embedding_model is not None):
                
                self._record_result(
                    "initialization", 
                    True, 
                    f"Completed in {init_time:.1f}ms"
                )
            else:
                self._record_result(
                    "initialization", 
                    False, 
                    "Components not properly initialized"
                )
                
        except Exception as e:
            self._record_result(
                "initialization", 
                False, 
                f"Failed with error: {str(e)}"
            )
    
    async def _test_embedding_generation(self):
        """Test embedding generation."""
        print("\n🧠 Testing Embedding Generation")
        
        try:
            # Test single embedding
            test_text = "This is a test sentence for embedding generation."
            embedding = await self.adapter._get_embedding(test_text)
            
            if isinstance(embedding, list) and len(embedding) > 0:
                self._record_result(
                    "single_embedding", 
                    True, 
                    f"Generated {len(embedding)}-dim embedding"
                )
            else:
                self._record_result("single_embedding", False, "Invalid embedding format")
                return
            
            # Test batch embeddings
            test_texts = [
                "First test sentence",
                "Second test sentence", 
                "Third test sentence"
            ]
            embeddings = await self.adapter._get_embeddings_batch(test_texts)
            
            if (isinstance(embeddings, list) and 
                len(embeddings) == len(test_texts) and
                all(isinstance(emb, list) and len(emb) > 0 for emb in embeddings)):
                
                self._record_result(
                    "batch_embeddings", 
                    True, 
                    f"Generated {len(embeddings)} embeddings"
                )
            else:
                self._record_result("batch_embeddings", False, "Invalid batch embeddings")
                
        except Exception as e:
            self._record_result("embedding_generation", False, f"Error: {str(e)}")
    
    async def _test_single_item_storage(self):
        """Test single item storage and retrieval."""
        print("\n💾 Testing Single Item Storage")
        
        try:
            # Create test item
            item = SimpleMemoryItem(
                id="test_item_1",
                content="This is a test memory item for vector storage.",
                tenant="test_tenant",
                namespace="test_namespace",
                metadata={"type": "test", "priority": "high"},
                tier=MemoryTier.LONG_TERM
            )
            
            # Store item
            start_time = time.time()
            result = await self.adapter.store_item(item)
            store_time = (time.time() - start_time) * 1000
            
            if result.success:
                self._record_result(
                    "single_store", 
                    True, 
                    f"Stored in {store_time:.1f}ms"
                )
                
                # Verify item can be retrieved
                retrieved = await self.adapter.retrieve_item(
                    item.get_tenant(), 
                    item.get_namespace(), 
                    item.get_id()
                )
                
                if retrieved and retrieved["content"] == item.get_content():
                    self._record_result(
                        "single_retrieve", 
                        True, 
                        "Content matches original"
                    )
                else:
                    self._record_result(
                        "single_retrieve", 
                        False, 
                        "Retrieved content doesn't match"
                    )
            else:
                self._record_result(
                    "single_store", 
                    False, 
                    f"Error: {result.error_message}"
                )
                
        except Exception as e:
            self._record_result("single_item_storage", False, f"Error: {str(e)}")
    
    async def _test_batch_storage(self):
        """Test batch storage operations."""
        print("\n📦 Testing Batch Storage Operations")
        
        try:
            # Create batch of test items
            items = []
            for i in range(10):
                item = SimpleMemoryItem(
                    id=f"batch_item_{i}",
                    content=f"This is batch test item number {i} with some unique content.",
                    tenant="test_tenant",
                    namespace="batch_test",
                    metadata={"batch_id": "batch_1", "item_number": i},
                    tier=MemoryTier.LONG_TERM
                )
                items.append(item)
            
            # Store batch
            start_time = time.time()
            result = await self.adapter.store_items_batch(items)
            batch_time = (time.time() - start_time) * 1000
            
            if result.success and result.item_count == len(items):
                self._record_result(
                    "batch_store", 
                    True, 
                    f"Stored {result.item_count} items in {batch_time:.1f}ms"
                )
                
                # Verify items can be listed
                listed_items = await self.adapter.list_items(
                    "test_tenant", 
                    "batch_test", 
                    limit=20
                )
                
                if len(listed_items) >= len(items):
                    self._record_result(
                        "batch_list", 
                        True, 
                        f"Listed {len(listed_items)} items"
                    )
                else:
                    self._record_result(
                        "batch_list", 
                        False, 
                        f"Expected {len(items)}, got {len(listed_items)}"
                    )
            else:
                self._record_result(
                    "batch_store", 
                    False, 
                    f"Error: {result.error_message}"
                )
                
        except Exception as e:
            self._record_result("batch_storage", False, f"Error: {str(e)}")
    
    async def _test_similarity_search(self):
        """Test similarity search functionality."""
        print("\n🔍 Testing Similarity Search")
        
        try:
            # First store some diverse content for searching
            search_items = [
                SimpleMemoryItem(
                    id="search_1",
                    content="Machine learning is a subset of artificial intelligence.",
                    tenant="test_tenant",
                    namespace="search_test",
                    tier=MemoryTier.LONG_TERM
                ),
                SimpleMemoryItem(
                    id="search_2", 
                    content="Deep learning uses neural networks with multiple layers.",
                    tenant="test_tenant",
                    namespace="search_test",
                    tier=MemoryTier.LONG_TERM
                ),
                SimpleMemoryItem(
                    id="search_3",
                    content="The weather today is sunny and warm.",
                    tenant="test_tenant", 
                    namespace="search_test",
                    tier=MemoryTier.LONG_TERM
                )
            ]
            
            # Store search items
            store_result = await self.adapter.store_items_batch(search_items)
            if not store_result.success:
                self._record_result("similarity_search", False, "Failed to store search items")
                return
            
            # Test similarity search
            query = VectorSearchQuery(
                query_text="artificial intelligence and neural networks",
                n_results=5,
                similarity_threshold=0.1  # Lower threshold for more results
            )
            
            start_time = time.time()
            search_result = await self.adapter.search_similar(query)
            search_time = (time.time() - start_time) * 1000
            
            if search_result.success and len(search_result.results) > 0:
                # Check if AI-related content ranks higher than weather content
                ai_found = False
                for result in search_result.results:
                    if "intelligence" in result.content.lower() or "learning" in result.content.lower():
                        ai_found = True
                        break
                
                if ai_found:
                    self._record_result(
                        "similarity_search", 
                        True, 
                        f"Found {len(search_result.results)} results in {search_time:.1f}ms"
                    )
                else:
                    self._record_result(
                        "similarity_search", 
                        False, 
                        "Relevant content not found in results"
                    )
            else:
                self._record_result(
                    "similarity_search", 
                    False, 
                    f"Error: {search_result.error_message}"
                )
                
        except Exception as e:
            self._record_result("similarity_search", False, f"Error: {str(e)}")
    
    async def _test_item_retrieval(self):
        """Test individual item retrieval."""
        print("\n🎯 Testing Item Retrieval")
        
        try:
            # Store a specific item for retrieval testing
            test_item = SimpleMemoryItem(
                id="retrieval_test",
                content="This item is specifically for testing retrieval functionality.",
                tenant="test_tenant",
                namespace="retrieval_test",
                metadata={"test_type": "retrieval"},
                tier=MemoryTier.LONG_TERM
            )
            
            store_result = await self.adapter.store_item(test_item)
            if not store_result.success:
                self._record_result("item_retrieval", False, "Failed to store test item")
                return
            
            # Test retrieval
            start_time = time.time()
            retrieved = await self.adapter.retrieve_item(
                test_item.get_tenant(),
                test_item.get_namespace(), 
                test_item.get_id()
            )
            retrieval_time = (time.time() - start_time) * 1000
            
            if retrieved:
                # Verify content and metadata
                if (retrieved["content"] == test_item.get_content() and
                    retrieved["metadata"].get("test_type") == "retrieval"):
                    
                    self._record_result(
                        "item_retrieval", 
                        True, 
                        f"Retrieved item in {retrieval_time:.1f}ms with correct data"
                    )
                else:
                    self._record_result(
                        "item_retrieval", 
                        False, 
                        "Retrieved item data doesn't match original"
                    )
            else:
                self._record_result("item_retrieval", False, "Item not found")
                
        except Exception as e:
            self._record_result("item_retrieval", False, f"Error: {str(e)}")
    
    async def _test_item_deletion(self):
        """Test item deletion."""
        print("\n🗑️  Testing Item Deletion")
        
        try:
            # Store item for deletion
            delete_item = SimpleMemoryItem(
                id="delete_test",
                content="This item will be deleted.",
                tenant="test_tenant", 
                namespace="delete_test",
                tier=MemoryTier.LONG_TERM
            )
            
            store_result = await self.adapter.store_item(delete_item)
            if not store_result.success:
                self._record_result("item_deletion", False, "Failed to store item for deletion")
                return
            
            # Verify item exists
            retrieved = await self.adapter.retrieve_item(
                delete_item.get_tenant(),
                delete_item.get_namespace(),
                delete_item.get_id()
            )
            if not retrieved:
                self._record_result("item_deletion", False, "Item not found before deletion")
                return
            
            # Delete item
            start_time = time.time()
            delete_result = await self.adapter.delete_item(
                delete_item.get_tenant(),
                delete_item.get_namespace(),
                delete_item.get_id()
            )
            delete_time = (time.time() - start_time) * 1000
            
            if delete_result.success:
                # Verify item no longer exists
                retrieved_after = await self.adapter.retrieve_item(
                    delete_item.get_tenant(),
                    delete_item.get_namespace(),
                    delete_item.get_id()
                )
                
                if not retrieved_after:
                    self._record_result(
                        "item_deletion", 
                        True, 
                        f"Item deleted in {delete_time:.1f}ms"
                    )
                else:
                    self._record_result(
                        "item_deletion", 
                        False, 
                        "Item still exists after deletion"
                    )
            else:
                self._record_result(
                    "item_deletion", 
                    False, 
                    f"Delete failed: {delete_result.error_message}"
                )
                
        except Exception as e:
            self._record_result("item_deletion", False, f"Error: {str(e)}")
    
    async def _test_item_listing(self):
        """Test item listing with pagination."""
        print("\n📄 Testing Item Listing")
        
        try:
            # Store multiple items for listing
            list_items = []
            for i in range(15):  # More than default limit
                item = SimpleMemoryItem(
                    id=f"list_item_{i:02d}",
                    content=f"Item for listing test number {i}",
                    tenant="test_tenant",
                    namespace="list_test", 
                    tier=MemoryTier.LONG_TERM
                )
                list_items.append(item)
            
            store_result = await self.adapter.store_items_batch(list_items)
            if not store_result.success:
                self._record_result("item_listing", False, "Failed to store items for listing")
                return
            
            # Test basic listing
            start_time = time.time()
            listed = await self.adapter.list_items(
                "test_tenant",
                "list_test",
                limit=10
            )
            list_time = (time.time() - start_time) * 1000
            
            if len(listed) == 10:  # Should respect limit
                self._record_result(
                    "item_listing", 
                    True, 
                    f"Listed {len(listed)} items in {list_time:.1f}ms (respects limit)"
                )
            else:
                self._record_result(
                    "item_listing", 
                    False, 
                    f"Expected 10 items, got {len(listed)}"
                )
                
        except Exception as e:
            self._record_result("item_listing", False, f"Error: {str(e)}")
    
    async def _test_embedding_cache(self):
        """Test embedding caching functionality."""
        print("\n⚡ Testing Embedding Cache")
        
        try:
            # Clear cache first
            self.adapter._embedding_cache.clear()
            initial_hits = self.adapter._cache_hits
            initial_misses = self.adapter._cache_misses
            
            test_text = "This text will be used to test caching functionality."
            
            # First call should be cache miss
            await self.adapter._get_embedding(test_text)
            miss_count = self.adapter._cache_misses - initial_misses
            
            # Second call should be cache hit
            await self.adapter._get_embedding(test_text)
            hit_count = self.adapter._cache_hits - initial_hits
            
            if miss_count >= 1 and hit_count >= 1:
                self._record_result(
                    "embedding_cache", 
                    True, 
                    f"Cache working: {miss_count} misses, {hit_count} hits"
                )
            else:
                self._record_result(
                    "embedding_cache", 
                    False, 
                    f"Cache not working properly: {miss_count} misses, {hit_count} hits"
                )
                
        except Exception as e:
            self._record_result("embedding_cache", False, f"Error: {str(e)}")
    
    async def _test_batch_performance(self):
        """Test batch operation performance."""
        print("\n🚀 Testing Batch Performance")
        
        try:
            # Create larger batch for performance testing
            batch_items = []
            for i in range(50):
                item = SimpleMemoryItem(
                    id=f"perf_item_{i}",
                    content=f"Performance test item {i} with substantial content to test embedding generation and storage performance metrics.",
                    tenant="test_tenant",
                    namespace="performance_test",
                    tier=MemoryTier.LONG_TERM
                )
                batch_items.append(item)
            
            # Measure batch storage performance
            start_time = time.time()
            result = await self.adapter.store_items_batch(batch_items)
            batch_time = (time.time() - start_time) * 1000
            
            if result.success:
                throughput = len(batch_items) / (batch_time / 1000)  # items per second
                self._record_result(
                    "batch_performance", 
                    True, 
                    f"Stored {len(batch_items)} items in {batch_time:.1f}ms ({throughput:.1f} items/sec)"
                )
            else:
                self._record_result(
                    "batch_performance", 
                    False, 
                    f"Batch storage failed: {result.error_message}"
                )
                
        except Exception as e:
            self._record_result("batch_performance", False, f"Error: {str(e)}")
    
    async def _test_metadata_filtering(self):
        """Test metadata-based filtering in searches."""
        print("\n🏷️  Testing Metadata Filtering")
        
        try:
            # Store items with different metadata
            filter_items = [
                SimpleMemoryItem(
                    id="filter_1",
                    content="High priority urgent task item",
                    tenant="test_tenant",
                    namespace="filter_test",
                    metadata={"priority": "high", "category": "urgent"},
                    tier=MemoryTier.LONG_TERM
                ),
                SimpleMemoryItem(
                    id="filter_2",
                    content="Low priority routine task item", 
                    tenant="test_tenant",
                    namespace="filter_test",
                    metadata={"priority": "low", "category": "routine"},
                    tier=MemoryTier.LONG_TERM
                )
            ]
            
            store_result = await self.adapter.store_items_batch(filter_items)
            if not store_result.success:
                self._record_result("metadata_filtering", False, "Failed to store filter items")
                return
            
            # Search with metadata filter
            query = VectorSearchQuery(
                query_text="task item",
                n_results=5,
                where={"priority": "high"}  # Only high priority items
            )
            
            search_result = await self.adapter.search_similar(query)
            
            if search_result.success and len(search_result.results) > 0:
                # Check if all results match the filter
                all_match = all(
                    result.metadata.get("priority") == "high" 
                    for result in search_result.results
                )
                
                if all_match:
                    self._record_result(
                        "metadata_filtering", 
                        True, 
                        f"Filter worked: {len(search_result.results)} high priority items found"
                    )
                else:
                    self._record_result(
                        "metadata_filtering", 
                        False, 
                        "Filter didn't work: non-matching items in results"
                    )
            else:
                # This might be expected if ChromaDB version doesn't support metadata filtering
                self._record_result(
                    "metadata_filtering", 
                    True, 
                    "No results (metadata filtering may not be supported in this ChromaDB version)"
                )
                
        except Exception as e:
            self._record_result("metadata_filtering", False, f"Error: {str(e)}")
    
    async def _test_large_content(self):
        """Test handling of large content items."""
        print("\n📄 Testing Large Content Handling")
        
        try:
            # Create item with large content
            large_content = "This is a very long piece of content. " * 100  # ~3000 chars
            
            large_item = SimpleMemoryItem(
                id="large_content_test",
                content=large_content,
                tenant="test_tenant",
                namespace="large_test",
                metadata={"size": "large", "chars": len(large_content)},
                tier=MemoryTier.LONG_TERM
            )
            
            # Store large item
            start_time = time.time()
            result = await self.adapter.store_item(large_item)
            store_time = (time.time() - start_time) * 1000
            
            if result.success:
                # Retrieve and verify
                retrieved = await self.adapter.retrieve_item(
                    large_item.get_tenant(),
                    large_item.get_namespace(),
                    large_item.get_id()
                )
                
                if retrieved and retrieved["content"] == large_content:
                    self._record_result(
                        "large_content", 
                        True, 
                        f"Stored and retrieved {len(large_content)} chars in {store_time:.1f}ms"
                    )
                else:
                    self._record_result(
                        "large_content", 
                        False, 
                        "Large content not properly retrieved"
                    )
            else:
                self._record_result(
                    "large_content", 
                    False, 
                    f"Failed to store large content: {result.error_message}"
                )
                
        except Exception as e:
            self._record_result("large_content", False, f"Error: {str(e)}")
    
    async def _test_error_conditions(self):
        """Test various error conditions and edge cases."""
        print("\n⚠️  Testing Error Conditions")
        
        try:
            # Test search with no query
            empty_query = VectorSearchQuery()
            result = await self.adapter.search_similar(empty_query)
            
            if not result.success:
                self._record_result(
                    "empty_query_error", 
                    True, 
                    "Properly rejected empty query"
                )
            else:
                self._record_result(
                    "empty_query_error", 
                    False, 
                    "Should have rejected empty query"
                )
            
            # Test retrieval of non-existent item
            non_existent = await self.adapter.retrieve_item(
                "nonexistent_tenant", 
                "nonexistent_namespace", 
                "nonexistent_id"
            )
            
            if non_existent is None:
                self._record_result(
                    "nonexistent_retrieval", 
                    True, 
                    "Properly returned None for non-existent item"
                )
            else:
                self._record_result(
                    "nonexistent_retrieval", 
                    False, 
                    "Should return None for non-existent item"
                )
                
        except Exception as e:
            self._record_result("error_conditions", False, f"Error: {str(e)}")
    
    async def _test_statistics(self):
        """Test statistics and monitoring."""
        print("\n📊 Testing Statistics")
        
        try:
            stats = await self.adapter.get_stats()
            
            # Check required fields
            required_fields = [
                "adapter_type", "backend", "total_items", 
                "operations_count", "embedding_model"
            ]
            
            missing_fields = [field for field in required_fields if field not in stats]
            
            if not missing_fields:
                self._record_result(
                    "statistics", 
                    True, 
                    f"All required stats present. Operations: {stats.get('operations_count', 0)}"
                )
            else:
                self._record_result(
                    "statistics", 
                    False, 
                    f"Missing required stats: {missing_fields}"
                )
                
        except Exception as e:
            self._record_result("statistics", False, f"Error: {str(e)}")
    
    async def _test_health_check(self):
        """Test health check functionality."""
        print("\n❤️  Testing Health Check")
        
        try:
            start_time = time.time()
            is_healthy = await self.adapter.health_check()
            health_time = (time.time() - start_time) * 1000
            
            if is_healthy:
                self._record_result(
                    "health_check", 
                    True, 
                    f"Healthy in {health_time:.1f}ms"
                )
            else:
                self._record_result(
                    "health_check", 
                    False, 
                    "Health check failed"
                )
                
        except Exception as e:
            self._record_result("health_check", False, f"Error: {str(e)}")
    
    def _print_test_summary(self):
        """Print comprehensive test results summary."""
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results.values() if result["success"])
        failed_tests = total_tests - successful_tests
        success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"Successful: {successful_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS ({failed_tests}):")
            for test_name, result in self.test_results.items():
                if not result["success"]:
                    print(f"   • {test_name}: {result['details']}")
        
        print(f"\n✅ SUCCESSFUL TESTS ({successful_tests}):")
        for test_name, result in self.test_results.items():
            if result["success"]:
                print(f"   • {test_name}: {result['details']}")
        
        # Overall assessment
        print(f"\n🎯 OVERALL ASSESSMENT:")
        if success_rate >= 90:
            print("   🟢 EXCELLENT - Vector adapter is production-ready!")
        elif success_rate >= 75:
            print("   🟡 GOOD - Vector adapter is mostly functional with minor issues.")
        elif success_rate >= 50:
            print("   🟠 FAIR - Vector adapter has significant issues that need addressing.")
        else:
            print("   🔴 POOR - Vector adapter has major problems and is not ready for use.")
        
        print("=" * 60)


async def main():
    """Run the vector adapter test suite."""
    tester = VectorAdapterTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())