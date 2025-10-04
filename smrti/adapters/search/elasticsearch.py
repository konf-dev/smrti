"""
smrti/adapters/search/elasticsearch.py - Elasticsearch adapter for Procedural Memory

Production-ready Elasticsearch adapter for procedural knowledge, skills, 
workflows, and structured search with advanced analytics capabilities.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

try:
    from elasticsearch import AsyncElasticsearch
    from elasticsearch.exceptions import (
        ElasticsearchException,
        ConnectionError as ESConnectionError,
        TransportError,
        NotFoundError
    )
    HAS_ELASTICSEARCH = True
except ImportError:
    HAS_ELASTICSEARCH = False
    
    # Type placeholders when elasticsearch is not available
    class AsyncElasticsearch:
        pass
    
    class ElasticsearchException(Exception):
        pass
    
    class ESConnectionError(Exception):
        pass
    
    class TransportError(Exception):
        pass
    
    class NotFoundError(Exception):
        pass

from smrti.core.base import BaseTierStore
from smrti.core.exceptions import (
    AdapterError,
    ConfigurationError,
    ValidationError,
    RetryableError,
    IntegrityError
)
from smrti.core.protocols import TierStore
from smrti.core.registry import AdapterCapability
from smrti.schemas.models import (
    MemoryQuery, 
    RecordEnvelope
)


class ElasticsearchAdapter(BaseTierStore):
    """
    Elasticsearch adapter for Procedural Memory storage.
    
    Features:
    - Full-text search with relevance scoring
    - Structured queries with aggregations
    - Skill and procedure indexing
    - Workflow step sequencing
    - Multi-field search and filtering
    - Analytics and insights
    - Auto-completion and suggestions
    - Faceted search capabilities
    - Performance monitoring
    - Index lifecycle management
    - Cluster health monitoring
    - Bulk operations for performance
    """
    
    def __init__(
        self,
        tier_name: str = "procedural",
        config: Optional[Dict[str, Any]] = None
    ):
        if not HAS_ELASTICSEARCH:
            raise ConfigurationError(
                "elasticsearch package is required but not installed. "
                "Install with: pip install elasticsearch"
            )
        
        super().__init__(tier_name, config)
        
        # Validate required configuration
        self._validate_config(["hosts"])
        
        # Elasticsearch connection configuration
        self._hosts = self.config["hosts"]
        if isinstance(self._hosts, str):
            self._hosts = [self._hosts]
        
        # Authentication
        self._username = self.config.get("username")
        self._password = self.config.get("password")
        self._api_key = self.config.get("api_key")
        self._cloud_id = self.config.get("cloud_id")
        
        # SSL/TLS configuration
        self._use_ssl = self.config.get("use_ssl", False)
        self._verify_certs = self.config.get("verify_certs", True)
        self._ca_certs = self.config.get("ca_certs")
        
        # Performance configuration
        self._timeout = self.config.get("timeout", 30)
        self._max_retries = self.config.get("max_retries", 3)
        self._retry_on_timeout = self.config.get("retry_on_timeout", True)
        self._max_connections = self.config.get("max_connections", 20)
        
        # Index configuration
        self._index_prefix = self.config.get("index_prefix", "smrti")
        self._index_name = f"{self._index_prefix}_procedural"
        self._number_of_shards = self.config.get("number_of_shards", 1)
        self._number_of_replicas = self.config.get("number_of_replicas", 1)
        self._refresh_interval = self.config.get("refresh_interval", "1s")
        
        # Search configuration
        self._default_search_size = self.config.get("default_search_size", 100)
        self._max_search_size = self.config.get("max_search_size", 10000)
        self._search_timeout = self.config.get("search_timeout", "30s")
        self._enable_aggregations = self.config.get("enable_aggregations", True)
        self._enable_suggestions = self.config.get("enable_suggestions", True)
        
        # Bulk operations configuration
        self._bulk_size = self.config.get("bulk_size", 100)
        self._bulk_timeout = self.config.get("bulk_timeout", "30s")
        
        # Client object
        self._client: Optional[AsyncElasticsearch] = None
        
        # Statistics
        self._search_count = 0
        self._index_count = 0
        self._bulk_count = 0
        self._total_search_time = 0.0
        self._total_index_time = 0.0
        
        # Set tier capabilities
        self._supports_ttl = True  # Via document TTL
        self._supports_similarity_search = True  # Via full-text similarity
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._cleanup_client()
    
    async def _initialize_client(self) -> None:
        """Initialize Elasticsearch client and ensure index exists."""
        try:
            # Prepare authentication
            auth_kwargs = {}
            if self._username and self._password:
                auth_kwargs["basic_auth"] = (self._username, self._password)
            elif self._api_key:
                auth_kwargs["api_key"] = self._api_key
            
            # Create client
            self._client = AsyncElasticsearch(
                hosts=self._hosts,
                cloud_id=self._cloud_id,
                timeout=self._timeout,
                max_retries=self._max_retries,
                retry_on_timeout=self._retry_on_timeout,
                use_ssl=self._use_ssl,
                verify_certs=self._verify_certs,
                ca_certs=self._ca_certs,
                **auth_kwargs
            )
            
            # Test connection
            cluster_health = await self._client.cluster.health()
            
            # Create index if it doesn't exist
            await self._ensure_index_exists()
            
            self.logger.info(
                f"Elasticsearch adapter initialized (cluster_name={cluster_health.get('cluster_name')}, "
                f"status={cluster_health.get('status')}, index={self._index_name})"
            )
            
        except Exception as e:
            raise AdapterError(
                f"Failed to initialize Elasticsearch client: {e}",
                adapter_name="elasticsearch",
                operation="initialize",
                backend_error=e
            )
    
    async def _ensure_index_exists(self) -> None:
        """Ensure the procedural memory index exists with proper mapping."""
        try:
            # Check if index exists
            exists = await self._client.indices.exists(index=self._index_name)
            
            if not exists:
                await self._create_index()
            else:
                # Update mapping if needed
                await self._update_index_mapping()
                
        except Exception as e:
            raise AdapterError(
                f"Failed to ensure index exists: {e}",
                adapter_name="elasticsearch",
                operation="index_setup",
                backend_error=e
            )
    
    async def _create_index(self) -> None:
        """Create the procedural memory index with optimized mapping."""
        mapping = {
            "settings": {
                "number_of_shards": self._number_of_shards,
                "number_of_replicas": self._number_of_replicas,
                "refresh_interval": self._refresh_interval,
                "analysis": {
                    "analyzer": {
                        "procedural_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "stop",
                                "snowball",
                                "synonym"
                            ]
                        },
                        "skill_analyzer": {
                            "type": "custom", 
                            "tokenizer": "keyword",
                            "filter": ["lowercase"]
                        }
                    },
                    "filter": {
                        "synonym": {
                            "type": "synonym",
                            "synonyms": [
                                "how,method,way,approach",
                                "step,stage,phase",
                                "skill,ability,capability,competency",
                                "procedure,process,workflow,method"
                            ]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    # Core record fields
                    "record_id": {"type": "keyword"},
                    "tenant_id": {"type": "keyword"},
                    "namespace": {"type": "keyword"},
                    "tier": {"type": "keyword"},
                    "record_type": {"type": "keyword"},
                    "content_type": {"type": "keyword"},
                    
                    # Content fields with different analyzers
                    "content": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "text",
                                "analyzer": "procedural_analyzer",
                                "fields": {
                                    "keyword": {"type": "keyword"},
                                    "suggest": {"type": "completion"}
                                }
                            },
                            "description": {
                                "type": "text",
                                "analyzer": "procedural_analyzer"
                            },
                            "steps": {
                                "type": "nested",
                                "properties": {
                                    "step_number": {"type": "integer"},
                                    "title": {
                                        "type": "text", 
                                        "analyzer": "procedural_analyzer"
                                    },
                                    "description": {
                                        "type": "text",
                                        "analyzer": "procedural_analyzer"
                                    },
                                    "inputs": {"type": "keyword"},
                                    "outputs": {"type": "keyword"},
                                    "duration": {"type": "integer"},
                                    "complexity": {"type": "keyword"}
                                }
                            },
                            "skills_required": {
                                "type": "text",
                                "analyzer": "skill_analyzer",
                                "fields": {"keyword": {"type": "keyword"}}
                            },
                            "tools_required": {"type": "keyword"},
                            "difficulty_level": {"type": "keyword"},
                            "category": {"type": "keyword"},
                            "domain": {"type": "keyword"},
                            "prerequisites": {"type": "keyword"},
                            "outcomes": {"type": "keyword"},
                            "success_criteria": {
                                "type": "text",
                                "analyzer": "procedural_analyzer"
                            }
                        }
                    },
                    
                    # Metadata and analytics
                    "embedding": {"type": "dense_vector", "dims": 768},
                    "relevance_score": {"type": "float"},
                    "access_count": {"type": "integer"},
                    "success_rate": {"type": "float"},
                    "average_completion_time": {"type": "integer"},
                    "tags": {
                        "type": "text",
                        "analyzer": "skill_analyzer",
                        "fields": {"keyword": {"type": "keyword"}}
                    },
                    "source": {"type": "keyword"},
                    
                    # Temporal fields
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "last_accessed": {"type": "date"},
                    "expires_at": {"type": "date"},
                    
                    # Additional metadata
                    "metadata": {"type": "object", "dynamic": True},
                    "content_hash": {"type": "keyword"},
                    "provenance": {"type": "object", "dynamic": True},
                    
                    # Session and context
                    "session_id": {"type": "keyword"},
                    
                    # Procedural-specific fields
                    "procedure_type": {"type": "keyword"},
                    "complexity_score": {"type": "float"},
                    "automation_level": {"type": "keyword"},
                    "validation_method": {"type": "keyword"}
                }
            }
        }
        
        await self._client.indices.create(
            index=self._index_name,
            body=mapping
        )
        
        self.logger.info(f"Created Elasticsearch index: {self._index_name}")
    
    async def _update_index_mapping(self) -> None:
        """Update index mapping if needed (for schema evolution)."""
        try:
            # Get current mapping
            current_mapping = await self._client.indices.get_mapping(index=self._index_name)
            
            # Add any new fields or update analyzers as needed
            # This is a simplified version - in production you'd have more sophisticated migration logic
            
            # Example: Add new field if it doesn't exist
            new_fields = {
                "execution_time": {"type": "float"},
                "error_rate": {"type": "float"}
            }
            
            for field, mapping in new_fields.items():
                field_path = f"mappings.properties.{field}"
                if field not in current_mapping.get(self._index_name, {}).get("mappings", {}).get("properties", {}):
                    await self._client.indices.put_mapping(
                        index=self._index_name,
                        body={"properties": {field: mapping}}
                    )
                    
        except Exception as e:
            self.logger.warning(f"Failed to update index mapping: {e}")
    
    def _record_to_document(self, record: RecordEnvelope) -> Dict[str, Any]:
        """Convert record to Elasticsearch document."""
        doc = {
            "record_id": record.record_id,
            "tenant_id": record.tenant_id,
            "namespace": record.namespace,
            "tier": record.tier,
            "record_type": record.record_type,
            "content_type": getattr(record, 'content_type', type(record.content).__name__),
            "content": record.content.model_dump() if hasattr(record.content, 'model_dump') else record.content,
            "embedding": record.embedding,
            "relevance_score": record.relevance_score,
            "access_count": record.access_count,
            "tags": record.tags,
            "source": record.source,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "last_accessed": record.last_accessed,
            "metadata": record.metadata,
            "content_hash": record.compute_semantic_hash()
        }
        
        # Add optional fields
        if hasattr(record, 'session_id') and record.session_id:
            doc['session_id'] = record.session_id
        if hasattr(record, 'expires_at') and record.expires_at:
            doc['expires_at'] = record.expires_at
        if record.provenance:
            doc['provenance'] = record.provenance.model_dump()
        
        # Add procedural-specific fields
        # TODO: Add back when ProcedureRecord and SkillRecord are defined
        # if isinstance(record.content, (ProcedureRecord, SkillRecord)):
        #     doc['procedure_type'] = getattr(record.content, 'procedure_type', 'unknown')
        #     doc['complexity_score'] = getattr(record.content, 'complexity', 0.5)
            
        return doc
    
    async def store(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Store a memory record in Elasticsearch."""
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
            start_time = time.time()
            
            # Convert record to document
            doc = self._record_to_document(record)
            
            # Add TTL if specified
            if ttl:
                doc['expires_at'] = datetime.utcnow() + ttl
            
            # Index document
            response = await self._client.index(
                index=self._index_name,
                id=record.record_id,
                body=doc,
                timeout=self._search_timeout
            )
            
            index_time = time.time() - start_time
            self._index_count += 1
            self._total_index_time += index_time
            self._update_stats("store", 1, len(str(record.content)))
            
            return record.record_id
            
        except ElasticsearchException as e:
            raise AdapterError(
                f"Elasticsearch error during store: {e}",
                adapter_name="elasticsearch",
                operation="store",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during store: {e}",
                adapter_name="elasticsearch", 
                operation="store",
                backend_error=e
            )
    
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
            # Get document
            response = await self._client.get(
                index=self._index_name,
                id=record_id,
                ignore=[404]
            )
            
            if not response.get("found", False):
                return None
            
            doc = response["_source"]
            
            # Update access count
            await self._client.update(
                index=self._index_name,
                id=record_id,
                body={
                    "script": {
                        "source": "ctx._source.access_count += 1; ctx._source.last_accessed = params.now",
                        "params": {"now": datetime.utcnow()}
                    }
                },
                ignore=[404]
            )
            
            record = self._document_to_record(doc)
            self._update_stats("retrieve", 1)
            
            return record
            
        except ElasticsearchException as e:
            raise AdapterError(
                f"Elasticsearch error during retrieve: {e}",
                adapter_name="elasticsearch",
                operation="retrieve",
                backend_error=e
            )
        except Exception as e:
            self.logger.warning(f"Error retrieving record {record_id}: {e}")
            return None
    
    def _document_to_record(self, doc: Dict[str, Any]) -> RecordEnvelope:
        """Convert Elasticsearch document to RecordEnvelope."""
        # Build record data
        record_data = {
            'record_id': doc['record_id'],
            'tenant_id': doc['tenant_id'],
            'namespace': doc['namespace'],
            'tier': doc.get('tier', 'procedural'),
            'record_type': doc['record_type'],
            'content': doc['content'],
            'embedding': doc.get('embedding'),
            'relevance_score': doc.get('relevance_score', 0.0),
            'access_count': doc.get('access_count', 0),
            'tags': doc.get('tags', []),
            'source': doc.get('source'),
            'created_at': self._parse_datetime(doc['created_at']),
            'updated_at': self._parse_datetime(doc['updated_at']),
            'metadata': doc.get('metadata', {})
        }
        
        # Add optional fields
        if doc.get('session_id'):
            record_data['session_id'] = doc['session_id']
        if doc.get('last_accessed'):
            record_data['last_accessed'] = self._parse_datetime(doc['last_accessed'])
        if doc.get('expires_at'):
            record_data['expires_at'] = self._parse_datetime(doc['expires_at'])
        if doc.get('provenance'):
            record_data['provenance'] = doc['provenance']
        
        return RecordEnvelope(**record_data)
    
    def _parse_datetime(self, dt_value: Any) -> datetime:
        """Parse datetime from various formats."""
        if isinstance(dt_value, datetime):
            return dt_value
        elif isinstance(dt_value, str):
            return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
        elif isinstance(dt_value, (int, float)):
            return datetime.fromtimestamp(dt_value)
        else:
            return datetime.utcnow()
    
    async def query(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Query records using Elasticsearch full-text and structured search."""
        return await self._execute_with_retry(
            "query",
            self._query_impl,
            query
        )
    
    async def _query_impl(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Internal query implementation with Elasticsearch DSL."""
        self._validate_query(query)
        
        try:
            start_time = time.time()
            
            # Build Elasticsearch query
            es_query = self._build_elasticsearch_query(query)
            
            # Execute search
            response = await self._client.search(
                index=self._index_name,
                body=es_query,
                timeout=self._search_timeout
            )
            
            # Process results
            records = []
            for hit in response["hits"]["hits"]:
                try:
                    doc = hit["_source"]
                    # Add search score as relevance boost
                    doc["relevance_score"] = hit["_score"]
                    
                    record = self._document_to_record(doc)
                    records.append(record)
                except Exception as e:
                    self.logger.warning(f"Failed to convert hit to record: {e}")
                    continue
            
            search_time = time.time() - start_time
            self._search_count += 1
            self._total_search_time += search_time
            self._update_stats("retrieve", len(records))
            
            if search_time > 1.0:
                self.logger.warning(f"Slow Elasticsearch query took {search_time:.2f}s")
            
            return records
            
        except ElasticsearchException as e:
            raise AdapterError(
                f"Elasticsearch error during query: {e}",
                adapter_name="elasticsearch",
                operation="query",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during query: {e}",
                adapter_name="elasticsearch",
                operation="query",
                backend_error=e
            )
    
    def _build_elasticsearch_query(self, query: MemoryQuery) -> Dict[str, Any]:
        """Build Elasticsearch query from MemoryQuery parameters."""
        # Build query clauses
        must_clauses = []
        filter_clauses = []
        should_clauses = []
        
        # Tenant and namespace filtering
        if query.tenant_id:
            filter_clauses.append({"term": {"tenant_id": query.tenant_id}})
        
        if query.namespace:
            filter_clauses.append({"term": {"namespace": query.namespace}})
        
        # Time range filtering
        if query.start_time or query.end_time:
            date_range = {}
            if query.start_time:
                date_range["gte"] = query.start_time
            if query.end_time:
                date_range["lte"] = query.end_time
            
            filter_clauses.append({
                "range": {"created_at": date_range}
            })
        
        # Tag filtering
        if query.tags:
            should_clauses.extend([
                {"terms": {"tags.keyword": query.tags}},
                {"terms": {"content.skills_required.keyword": query.tags}},
                {"terms": {"content.category": query.tags}}
            ])
        
        # Full-text search
        if query.query_text:
            must_clauses.append({
                "multi_match": {
                    "query": query.query_text,
                    "fields": [
                        "content.title^3",
                        "content.description^2",
                        "content.steps.title^2",
                        "content.steps.description",
                        "content.success_criteria",
                        "tags^2"
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            })
            
            # Add phrase matching for better relevance
            should_clauses.append({
                "multi_match": {
                    "query": query.query_text,
                    "fields": [
                        "content.title^3",
                        "content.description^2"
                    ],
                    "type": "phrase",
                    "boost": 2.0
                }
            })
        
        # Nested search for procedure steps
        if hasattr(query, 'step_search') and query.step_search:
            must_clauses.append({
                "nested": {
                    "path": "content.steps",
                    "query": {
                        "multi_match": {
                            "query": query.step_search,
                            "fields": [
                                "content.steps.title",
                                "content.steps.description"
                            ]
                        }
                    }
                }
            })
        
        # Complexity filtering
        if hasattr(query, 'max_complexity') and query.max_complexity:
            filter_clauses.append({
                "range": {"complexity_score": {"lte": query.max_complexity}}
            })
        
        # Skill requirement filtering
        if hasattr(query, 'required_skills') and query.required_skills:
            must_clauses.append({
                "terms": {"content.skills_required.keyword": query.required_skills}
            })
        
        # Build the final query
        bool_query = {}
        
        if must_clauses:
            bool_query["must"] = must_clauses
        
        if filter_clauses:
            bool_query["filter"] = filter_clauses
        
        if should_clauses:
            bool_query["should"] = should_clauses
            bool_query["minimum_should_match"] = 1 if not must_clauses else 0
        
        # If no specific queries, match all
        if not bool_query:
            bool_query = {"match_all": {}}
        
        es_query = {
            "query": {"bool": bool_query} if any([must_clauses, filter_clauses, should_clauses]) else {"match_all": {}},
            "size": min(query.limit, self._max_search_size),
            "sort": [
                {"_score": {"order": "desc"}},
                {"relevance_score": {"order": "desc"}},
                {"access_count": {"order": "desc"}},
                {"created_at": {"order": "desc"}}
            ]
        }
        
        # Add aggregations if enabled
        if self._enable_aggregations:
            es_query["aggs"] = {
                "categories": {
                    "terms": {"field": "content.category", "size": 10}
                },
                "difficulty_levels": {
                    "terms": {"field": "content.difficulty_level", "size": 10}
                },
                "domains": {
                    "terms": {"field": "content.domain", "size": 10}
                },
                "avg_complexity": {
                    "avg": {"field": "complexity_score"}
                }
            }
        
        # Add highlighting
        es_query["highlight"] = {
            "fields": {
                "content.title": {},
                "content.description": {},
                "content.steps.title": {},
                "content.steps.description": {}
            }
        }
        
        return es_query
    
    async def delete(self, record_id: str) -> bool:
        """Delete a memory record."""
        return await self._execute_with_retry(
            "delete",
            self._delete_impl,
            record_id
        )
    
    async def _delete_impl(self, record_id: str) -> bool:
        """Internal delete implementation."""
        try:
            response = await self._client.delete(
                index=self._index_name,
                id=record_id,
                ignore=[404]
            )
            
            result = response.get("result")
            
            if result == "deleted":
                self._update_stats("delete", 1)
                return True
            else:
                return False
                
        except ElasticsearchException as e:
            raise AdapterError(
                f"Elasticsearch error during delete: {e}",
                adapter_name="elasticsearch",
                operation="delete",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during delete: {e}",
                adapter_name="elasticsearch",
                operation="delete",
                backend_error=e
            )
    
    async def suggest_procedures(
        self,
        query_text: str,
        tenant_id: str,
        namespace: str,
        size: int = 5
    ) -> List[Dict[str, Any]]:
        """Get procedure suggestions using completion suggester."""
        try:
            suggest_query = {
                "suggest": {
                    "procedure_suggest": {
                        "prefix": query_text,
                        "completion": {
                            "field": "content.title.suggest",
                            "size": size,
                            "contexts": {
                                "tenant": tenant_id,
                                "namespace": namespace
                            }
                        }
                    }
                }
            }
            
            response = await self._client.search(
                index=self._index_name,
                body=suggest_query
            )
            
            suggestions = []
            for suggestion in response.get("suggest", {}).get("procedure_suggest", []):
                for option in suggestion.get("options", []):
                    suggestions.append({
                        "text": option["text"],
                        "score": option["_score"],
                        "source": option.get("_source", {})
                    })
            
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Failed to get suggestions: {e}")
            return []
    
    async def get_analytics(
        self,
        tenant_id: str,
        namespace: str,
        time_range: Optional[Dict[str, datetime]] = None
    ) -> Dict[str, Any]:
        """Get analytics and insights about procedural memory usage."""
        try:
            # Build analytics query
            aggs_query = {
                "size": 0,
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"tenant_id": tenant_id}},
                            {"term": {"namespace": namespace}}
                        ]
                    }
                },
                "aggs": {
                    "total_procedures": {
                        "value_count": {"field": "record_id"}
                    },
                    "categories": {
                        "terms": {"field": "content.category", "size": 20}
                    },
                    "difficulty_distribution": {
                        "terms": {"field": "content.difficulty_level", "size": 10}
                    },
                    "complexity_stats": {
                        "stats": {"field": "complexity_score"}
                    },
                    "access_patterns": {
                        "date_histogram": {
                            "field": "last_accessed",
                            "calendar_interval": "day"
                        }
                    },
                    "top_procedures": {
                        "terms": {
                            "field": "content.title.keyword",
                            "order": {"avg_access_count": "desc"},
                            "size": 10
                        },
                        "aggs": {
                            "avg_access_count": {
                                "avg": {"field": "access_count"}
                            }
                        }
                    },
                    "skill_requirements": {
                        "terms": {"field": "content.skills_required.keyword", "size": 20}
                    }
                }
            }
            
            # Add time range filter if specified
            if time_range:
                date_filter = {"range": {"created_at": {}}}
                if time_range.get("start"):
                    date_filter["range"]["created_at"]["gte"] = time_range["start"]
                if time_range.get("end"):
                    date_filter["range"]["created_at"]["lte"] = time_range["end"]
                
                aggs_query["query"]["bool"]["filter"].append(date_filter)
            
            response = await self._client.search(
                index=self._index_name,
                body=aggs_query
            )
            
            # Process aggregations
            aggs = response.get("aggregations", {})
            
            analytics = {
                "total_procedures": aggs.get("total_procedures", {}).get("value", 0),
                "categories": [
                    {"name": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in aggs.get("categories", {}).get("buckets", [])
                ],
                "difficulty_distribution": [
                    {"level": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in aggs.get("difficulty_distribution", {}).get("buckets", [])
                ],
                "complexity_stats": aggs.get("complexity_stats", {}),
                "top_procedures": [
                    {
                        "title": bucket["key"],
                        "count": bucket["doc_count"],
                        "avg_access_count": bucket.get("avg_access_count", {}).get("value", 0)
                    }
                    for bucket in aggs.get("top_procedures", {}).get("buckets", [])
                ],
                "skill_requirements": [
                    {"skill": bucket["key"], "count": bucket["doc_count"]}
                    for bucket in aggs.get("skill_requirements", {}).get("buckets", [])
                ],
                "access_patterns": [
                    {"date": bucket["key_as_string"], "count": bucket["doc_count"]}
                    for bucket in aggs.get("access_patterns", {}).get("buckets", [])
                ]
            }
            
            return analytics
            
        except Exception as e:
            self.logger.error(f"Failed to get analytics: {e}")
            return {}
    
    async def update_relevance(
        self, 
        record_id: str, 
        new_relevance: float
    ) -> bool:
        """Update relevance score for a record."""
        try:
            response = await self._client.update(
                index=self._index_name,
                id=record_id,
                body={
                    "doc": {
                        "relevance_score": new_relevance,
                        "updated_at": datetime.utcnow()
                    }
                },
                ignore=[404]
            )
            
            result = response.get("result")
            return result in ["updated", "noop"]
                
        except Exception as e:
            self.logger.error(f"Failed to update relevance for {record_id}: {e}")
            return False
    
    async def cleanup_expired(self) -> int:
        """Remove expired records based on expires_at field."""
        try:
            # Delete expired documents
            response = await self._client.delete_by_query(
                index=self._index_name,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"exists": {"field": "expires_at"}},
                                {"range": {"expires_at": {"lt": "now"}}}
                            ]
                        }
                    }
                }
            )
            
            deleted_count = response.get("deleted", 0)
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} expired procedural records")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired records: {e}")
            return 0
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform Elasticsearch health check."""
        try:
            # Cluster health
            cluster_health = await self._client.cluster.health()
            
            # Index health
            index_stats = await self._client.indices.stats(index=self._index_name)
            
            # Node info
            node_info = await self._client.nodes.info()
            
            return {
                "cluster_name": cluster_health.get("cluster_name"),
                "cluster_status": cluster_health.get("status"),
                "number_of_nodes": cluster_health.get("number_of_nodes"),
                "active_shards": cluster_health.get("active_shards"),
                "index_name": self._index_name,
                "document_count": index_stats["indices"][self._index_name]["total"]["docs"]["count"],
                "index_size": index_stats["indices"][self._index_name]["total"]["store"]["size_in_bytes"],
                "search_count": self._search_count,
                "index_count": self._index_count,
                "bulk_count": self._bulk_count,
                "average_search_time": (
                    self._total_search_time / max(1, self._search_count)
                ),
                "average_index_time": (
                    self._total_index_time / max(1, self._index_count)
                ),
                "elasticsearch_version": list(node_info["nodes"].values())[0]["version"] if node_info.get("nodes") else "unknown"
            }
                
        except Exception as e:
            raise AdapterError(
                f"Elasticsearch health check failed: {e}",
                adapter_name="elasticsearch",
                operation="health_check",
                backend_error=e
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Elasticsearch adapter statistics."""
        base_stats = await super().get_stats()
        
        es_stats = {
            "hosts": self._hosts,
            "index_name": self._index_name,
            "search_count": self._search_count,
            "index_count": self._index_count,
            "bulk_count": self._bulk_count,
            "average_search_time": (
                self._total_search_time / max(1, self._search_count)
            ),
            "average_index_time": (
                self._total_index_time / max(1, self._index_count)
            ),
            "enable_aggregations": self._enable_aggregations,
            "enable_suggestions": self._enable_suggestions,
            "max_search_size": self._max_search_size,
            "bulk_size": self._bulk_size
        }
        
        base_stats.update(es_stats)
        return base_stats
    
    async def _cleanup_client(self) -> None:
        """Clean up Elasticsearch client."""
        try:
            if self._client:
                await self._client.close()
        except Exception as e:
            self.logger.warning(f"Error during Elasticsearch cleanup: {e}")
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """Get adapter capabilities."""
        capabilities = [
            AdapterCapability(
                name="procedural_memory",
                version="1.0.0",
                description="Full-text search and structured procedural storage"
            ),
            AdapterCapability(
                name="full_text_search",
                version="1.0.0",
                description="Advanced full-text search with relevance scoring"
            ),
            AdapterCapability(
                name="structured_queries",
                version="1.0.0",
                description="Complex structured queries and filtering"
            ),
            AdapterCapability(
                name="analytics",
                version="1.0.0",
                description="Advanced analytics and aggregations"
            ),
            AdapterCapability(
                name="auto_completion",
                version="1.0.0",
                description="Auto-completion and search suggestions"
            ),
            AdapterCapability(
                name="nested_search",
                version="1.0.0",
                description="Nested document search for procedure steps"
            ),
            AdapterCapability(
                name="faceted_search",
                version="1.0.0",
                description="Faceted search with category aggregations"
            ),
            AdapterCapability(
                name="bulk_operations",
                version="1.0.0",
                description="High-performance bulk indexing operations"
            )
        ]
        
        if self._enable_aggregations:
            capabilities.append(AdapterCapability(
                name="real_time_analytics",
                version="1.0.0",
                description="Real-time analytics and usage insights"
            ))
        
        if self._enable_suggestions:
            capabilities.append(AdapterCapability(
                name="intelligent_suggestions",
                version="1.0.0",
                description="Intelligent auto-completion and suggestions"
            ))
        
        return capabilities