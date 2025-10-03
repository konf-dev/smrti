"""
smrti/adapters/database/postgresql.py - PostgreSQL adapter for Episodic Memory

Production-ready PostgreSQL adapter for temporal event sequences, episodic memories,
and complex relational queries with full ACID compliance.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import asyncpg
    from asyncpg import Connection, Pool
    from asyncpg.exceptions import PostgresError, ConnectionFailureError
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    asyncpg = None
    
    # Type placeholders when asyncpg is not available
    class Connection:
        pass
    
    class Pool:
        pass
    
    PostgresError = Exception
    ConnectionFailureError = Exception

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
    RecordEnvelope, 
    EventRecord,
    ConversationTurn
)


class PostgreSQLAdapter(BaseTierStore):
    """
    PostgreSQL adapter for Episodic Memory storage.
    
    Features:
    - Temporal event sequence management
    - Complex relational queries and joins
    - Transaction support with ACID compliance
    - Connection pooling with auto-reconnection
    - Advanced indexing for temporal queries
    - Event timeline reconstruction
    - Session-based memory organization
    - JSON document storage with relational metadata
    - Full-text search integration
    - Automatic schema migration
    """
    
    # Database schema version for migrations
    SCHEMA_VERSION = 1
    
    def __init__(
        self,
        tier_name: str = "episodic",
        config: Optional[Dict[str, Any]] = None
    ):
        if not HAS_ASYNCPG:
            raise ConfigurationError(
                "asyncpg package is required but not installed. "
                "Install with: pip install asyncpg"
            )
        
        super().__init__(tier_name, config)
        
        # Validate required configuration
        self._validate_config(["host", "database", "user"])
        
        # Database connection configuration
        self._host = self.config["host"]
        self._port = self.config.get("port", 5432)
        self._database = self.config["database"]
        self._user = self.config["user"]
        self._password = self.config.get("password", "")
        self._ssl = self.config.get("ssl", "prefer")
        
        # Connection pool configuration
        self._min_size = self.config.get("min_pool_size", 5)
        self._max_size = self.config.get("max_pool_size", 20)
        self._max_queries = self.config.get("max_queries", 50000)
        self._max_inactive_time = self.config.get("max_inactive_time", 300.0)
        self._command_timeout = self.config.get("command_timeout", 30.0)
        
        # Table configuration
        self._table_prefix = self.config.get("table_prefix", "smrti")
        self._schema_name = self.config.get("schema", "public")
        self._use_partitioning = self.config.get("use_partitioning", True)
        self._partition_interval = self.config.get("partition_interval", "month")
        
        # Performance configuration
        self._batch_size = self.config.get("batch_size", 1000)
        self._enable_full_text_search = self.config.get("enable_full_text_search", True)
        self._vacuum_threshold = self.config.get("vacuum_threshold", 10000)
        
        # Connection objects
        self._pool: Optional[Pool] = None
        
        # Table names
        self._records_table = f"{self._table_prefix}_episodic_records"
        self._events_table = f"{self._table_prefix}_episodic_events"
        self._sessions_table = f"{self._table_prefix}_episodic_sessions"
        self._metadata_table = f"{self._table_prefix}_episodic_metadata"
        
        # Statistics
        self._connections_created = 0
        self._query_count = 0
        self._transaction_count = 0
        self._total_query_time = 0.0
        self._last_vacuum = None
        
        # Set tier capabilities
        self._supports_ttl = False  # Handled at application level
        self._supports_similarity_search = False  # No vector similarity
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_connection_pool()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._cleanup_connections()
    
    async def _initialize_connection_pool(self) -> None:
        """Initialize PostgreSQL connection pool and ensure schema exists."""
        try:
            # Create connection pool
            self._pool = await asyncpg.create_pool(
                host=self._host,
                port=self._port,
                database=self._database,
                user=self._user,
                password=self._password,
                ssl=self._ssl,
                min_size=self._min_size,
                max_size=self._max_size,
                max_queries=self._max_queries,
                max_inactive_connection_lifetime=self._max_inactive_time,
                command_timeout=self._command_timeout
            )
            
            # Test connection and initialize schema
            async with self._pool.acquire() as conn:
                await self._initialize_schema(conn)
            
            self.logger.info(
                f"PostgreSQL adapter initialized (host={self._host}, "
                f"db={self._database}, pool_size={self._min_size}-{self._max_size})"
            )
            
        except Exception as e:
            raise AdapterError(
                f"Failed to initialize PostgreSQL connection pool: {e}",
                adapter_name="postgresql",
                operation="initialize",
                backend_error=e
            )
    
    async def _initialize_schema(self, conn: Connection) -> None:
        """Initialize database schema and tables."""
        try:
            # Create schema if it doesn't exist
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self._schema_name}")
            
            # Create main records table
            await self._create_records_table(conn)
            
            # Create events table for detailed event tracking
            await self._create_events_table(conn)
            
            # Create sessions table for grouping related memories
            await self._create_sessions_table(conn)
            
            # Create metadata table for additional record properties
            await self._create_metadata_table(conn)
            
            # Create indexes for optimal query performance
            await self._create_indexes(conn)
            
            # Enable full-text search if configured
            if self._enable_full_text_search:
                await self._setup_full_text_search(conn)
            
            # Set up partitioning if enabled
            if self._use_partitioning:
                await self._setup_partitioning(conn)
            
            self.logger.info("PostgreSQL schema initialized successfully")
            
        except Exception as e:
            raise AdapterError(
                f"Failed to initialize database schema: {e}",
                adapter_name="postgresql",
                operation="schema_init",
                backend_error=e
            )
    
    async def _create_records_table(self, conn: Connection) -> None:
        """Create the main episodic records table."""
        table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self._schema_name}.{self._records_table} (
            record_id VARCHAR(255) PRIMARY KEY,
            tenant_id VARCHAR(100) NOT NULL,
            namespace VARCHAR(100) NOT NULL,
            session_id VARCHAR(255),
            tier VARCHAR(50) NOT NULL DEFAULT 'episodic',
            record_type VARCHAR(50) NOT NULL,
            content_type VARCHAR(100),
            content JSONB NOT NULL,
            embedding FLOAT8[],
            relevance_score FLOAT8 DEFAULT 0.0,
            access_count INTEGER DEFAULT 0,
            tags TEXT[],
            source VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE,
            metadata JSONB DEFAULT '{{}}',
            content_hash VARCHAR(64),
            provenance JSONB,
            -- Episodic-specific fields
            event_sequence INTEGER,
            event_timestamp TIMESTAMP WITH TIME ZONE,
            temporal_context JSONB,
            causal_links TEXT[],
            emotional_context JSONB,
            -- Full-text search
            content_tsvector TSVECTOR
        ) 
        """
        
        if self._use_partitioning:
            table_sql += f"PARTITION BY RANGE (created_at)"
        
        await conn.execute(table_sql)
        
        # Create trigger for updating updated_at timestamp
        trigger_sql = f"""
        CREATE OR REPLACE FUNCTION {self._schema_name}.update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        DROP TRIGGER IF EXISTS update_{self._records_table}_updated_at 
        ON {self._schema_name}.{self._records_table};
        
        CREATE TRIGGER update_{self._records_table}_updated_at 
        BEFORE UPDATE ON {self._schema_name}.{self._records_table}
        FOR EACH ROW EXECUTE FUNCTION {self._schema_name}.update_updated_at_column();
        """
        
        await conn.execute(trigger_sql)
    
    async def _create_events_table(self, conn: Connection) -> None:
        """Create events table for detailed event tracking."""
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self._schema_name}.{self._events_table} (
            event_id SERIAL PRIMARY KEY,
            record_id VARCHAR(255) REFERENCES {self._schema_name}.{self._records_table}(record_id) ON DELETE CASCADE,
            event_type VARCHAR(100) NOT NULL,
            event_data JSONB NOT NULL,
            event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            session_id VARCHAR(255),
            tenant_id VARCHAR(100) NOT NULL,
            namespace VARCHAR(100) NOT NULL,
            sequence_number INTEGER,
            parent_event_id INTEGER REFERENCES {self._schema_name}.{self._events_table}(event_id),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """)
    
    async def _create_sessions_table(self, conn: Connection) -> None:
        """Create sessions table for grouping related memories."""
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self._schema_name}.{self._sessions_table} (
            session_id VARCHAR(255) PRIMARY KEY,
            tenant_id VARCHAR(100) NOT NULL,
            namespace VARCHAR(100) NOT NULL,
            session_type VARCHAR(100),
            start_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            end_time TIMESTAMP WITH TIME ZONE,
            duration_seconds INTEGER,
            event_count INTEGER DEFAULT 0,
            summary TEXT,
            tags TEXT[],
            metadata JSONB DEFAULT '{{}}',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """)
    
    async def _create_metadata_table(self, conn: Connection) -> None:
        """Create metadata table for additional record properties."""
        await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self._schema_name}.{self._metadata_table} (
            record_id VARCHAR(255) REFERENCES {self._schema_name}.{self._records_table}(record_id) ON DELETE CASCADE,
            key VARCHAR(255) NOT NULL,
            value JSONB NOT NULL,
            data_type VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY (record_id, key)
        )
        """)
    
    async def _create_indexes(self, conn: Connection) -> None:
        """Create optimized indexes for query performance."""
        indexes = [
            # Primary access patterns
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_tenant_namespace ON {self._schema_name}.{self._records_table} (tenant_id, namespace)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_session ON {self._schema_name}.{self._records_table} (session_id) WHERE session_id IS NOT NULL",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_created_at ON {self._schema_name}.{self._records_table} (created_at)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_event_timestamp ON {self._schema_name}.{self._records_table} (event_timestamp) WHERE event_timestamp IS NOT NULL",
            
            # Temporal queries
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_temporal ON {self._schema_name}.{self._records_table} (tenant_id, namespace, event_timestamp, event_sequence)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_sequence ON {self._schema_name}.{self._records_table} (session_id, event_sequence) WHERE session_id IS NOT NULL",
            
            # Content and metadata
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_tags ON {self._schema_name}.{self._records_table} USING GIN (tags)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_content ON {self._schema_name}.{self._records_table} USING GIN (content)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_metadata ON {self._schema_name}.{self._records_table} USING GIN (metadata)",
            
            # Events table indexes
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._events_table}_record ON {self._schema_name}.{self._events_table} (record_id)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._events_table}_session ON {self._schema_name}.{self._events_table} (session_id, sequence_number)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._events_table}_temporal ON {self._schema_name}.{self._events_table} (event_timestamp)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._events_table}_type ON {self._schema_name}.{self._events_table} (event_type)",
            
            # Sessions table indexes
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._sessions_table}_tenant ON {self._schema_name}.{self._sessions_table} (tenant_id, namespace)",
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._sessions_table}_time ON {self._schema_name}.{self._sessions_table} (start_time, end_time)",
        ]
        
        for index_sql in indexes:
            try:
                await conn.execute(index_sql)
            except Exception as e:
                # Index creation can fail if index already exists, which is fine
                self.logger.debug(f"Index creation note: {e}")
    
    async def _setup_full_text_search(self, conn: Connection) -> None:
        """Set up full-text search capabilities."""
        try:
            # Create or update full-text search index
            await conn.execute(f"""
            CREATE OR REPLACE FUNCTION {self._schema_name}.update_content_tsvector() 
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.content_tsvector := to_tsvector('english', 
                    COALESCE(NEW.content::text, '') || ' ' ||
                    COALESCE(array_to_string(NEW.tags, ' '), '') || ' ' ||
                    COALESCE(NEW.source, '')
                );
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """)
            
            # Create trigger
            await conn.execute(f"""
            DROP TRIGGER IF EXISTS tsvector_update_trigger 
            ON {self._schema_name}.{self._records_table};
            
            CREATE TRIGGER tsvector_update_trigger 
            BEFORE INSERT OR UPDATE ON {self._schema_name}.{self._records_table}
            FOR EACH ROW EXECUTE FUNCTION {self._schema_name}.update_content_tsvector();
            """)
            
            # Create GIN index for full-text search
            await conn.execute(f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{self._records_table}_fts 
            ON {self._schema_name}.{self._records_table} USING GIN (content_tsvector)
            """)
            
        except Exception as e:
            self.logger.warning(f"Failed to set up full-text search: {e}")
    
    async def _setup_partitioning(self, conn: Connection) -> None:
        """Set up table partitioning for better performance."""
        try:
            # Create monthly partitions for the current and next few months
            current_date = datetime.now()
            
            for months_ahead in range(6):  # Create 6 months of partitions
                partition_date = current_date.replace(day=1) + timedelta(days=32 * months_ahead)
                partition_date = partition_date.replace(day=1)
                
                partition_name = f"{self._records_table}_{partition_date.strftime('%Y_%m')}"
                next_month = (partition_date.replace(day=28) + timedelta(days=4)).replace(day=1)
                
                partition_sql = f"""
                CREATE TABLE IF NOT EXISTS {self._schema_name}.{partition_name}
                PARTITION OF {self._schema_name}.{self._records_table}
                FOR VALUES FROM ('{partition_date.isoformat()}') TO ('{next_month.isoformat()}')
                """
                
                await conn.execute(partition_sql)
            
        except Exception as e:
            self.logger.warning(f"Failed to set up partitioning: {e}")
    
    def _record_to_sql_params(self, record: RecordEnvelope) -> Tuple[str, List[Any]]:
        """Convert record to SQL parameters for insertion."""
        # Handle EventRecord specific fields
        event_sequence = None
        event_timestamp = None
        temporal_context = None
        causal_links = None
        emotional_context = None
        
        if hasattr(record.content, 'sequence_number'):
            event_sequence = record.content.sequence_number
        if hasattr(record.content, 'timestamp'):
            event_timestamp = record.content.timestamp
        if hasattr(record.content, 'context'):
            temporal_context = record.content.context
        if hasattr(record.content, 'causal_links'):
            causal_links = record.content.causal_links
        if hasattr(record.content, 'emotional_context'):
            emotional_context = record.content.emotional_context
        
        sql = f"""
        INSERT INTO {self._schema_name}.{self._records_table} (
            record_id, tenant_id, namespace, session_id, tier, record_type,
            content_type, content, embedding, relevance_score, access_count,
            tags, source, created_at, updated_at, last_accessed, expires_at,
            metadata, content_hash, provenance, event_sequence, event_timestamp,
            temporal_context, causal_links, emotional_context
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
        )
        ON CONFLICT (record_id) DO UPDATE SET
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            relevance_score = EXCLUDED.relevance_score,
            access_count = EXCLUDED.access_count + 1,
            tags = EXCLUDED.tags,
            updated_at = NOW(),
            last_accessed = NOW(),
            metadata = EXCLUDED.metadata,
            event_sequence = EXCLUDED.event_sequence,
            event_timestamp = EXCLUDED.event_timestamp,
            temporal_context = EXCLUDED.temporal_context,
            causal_links = EXCLUDED.causal_links,
            emotional_context = EXCLUDED.emotional_context
        """
        
        params = [
            record.record_id,
            record.tenant_id,
            record.namespace,
            getattr(record, 'session_id', None),
            record.tier,
            record.record_type,
            getattr(record, 'content_type', type(record.content).__name__),
            json.dumps(record.content.model_dump() if hasattr(record.content, 'model_dump') else record.content),
            getattr(record, 'embedding', None),
            record.relevance_score,
            record.access_count,
            record.tags,
            record.source,
            record.created_at,
            record.updated_at,
            record.last_accessed,
            getattr(record, 'expires_at', None),
            record.metadata,
            record.compute_semantic_hash(),
            record.provenance.model_dump() if record.provenance else None,
            event_sequence,
            event_timestamp,
            temporal_context,
            causal_links,
            emotional_context
        ]
        
        return sql, params
    
    async def store(
        self, 
        record: RecordEnvelope,
        ttl: Optional[timedelta] = None
    ) -> str:
        """Store a memory record with episodic metadata."""
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
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    # Insert main record
                    sql, params = self._record_to_sql_params(record)
                    await conn.execute(sql, *params)
                    
                    # Insert event record if this is an EventRecord
                    if isinstance(record.content, EventRecord):
                        await self._store_event_record(conn, record)
                    
                    # Update session information
                    if hasattr(record, 'session_id') and record.session_id:
                        await self._update_session_info(conn, record)
            
            self._query_count += 1
            self._transaction_count += 1
            self._update_stats("store", 1, len(str(record.content)))
            
            return record.record_id
            
        except PostgresError as e:
            raise AdapterError(
                f"PostgreSQL error during store: {e}",
                adapter_name="postgresql",
                operation="store",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during store: {e}",
                adapter_name="postgresql", 
                operation="store",
                backend_error=e
            )
    
    async def _store_event_record(self, conn: Connection, record: RecordEnvelope) -> None:
        """Store additional event tracking information."""
        event_content = record.content
        
        event_sql = f"""
        INSERT INTO {self._schema_name}.{self._events_table} (
            record_id, event_type, event_data, event_timestamp, session_id,
            tenant_id, namespace, sequence_number
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        
        await conn.execute(
            event_sql,
            record.record_id,
            getattr(event_content, 'event_type', 'unknown'),
            event_content.model_dump(),
            getattr(event_content, 'timestamp', record.created_at),
            getattr(record, 'session_id', None),
            record.tenant_id,
            record.namespace,
            getattr(event_content, 'sequence_number', None)
        )
    
    async def _update_session_info(self, conn: Connection, record: RecordEnvelope) -> None:
        """Update session information with new event."""
        session_sql = f"""
        INSERT INTO {self._schema_name}.{self._sessions_table} (
            session_id, tenant_id, namespace, start_time, event_count
        ) VALUES ($1, $2, $3, $4, 1)
        ON CONFLICT (session_id) DO UPDATE SET
            end_time = $4,
            event_count = {self._sessions_table}.event_count + 1,
            updated_at = NOW()
        """
        
        await conn.execute(
            session_sql,
            record.session_id,
            record.tenant_id,
            record.namespace,
            record.created_at
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
            async with self._pool.acquire() as conn:
                # Update access count and timestamp
                update_sql = f"""
                UPDATE {self._schema_name}.{self._records_table} 
                SET access_count = access_count + 1, last_accessed = NOW()
                WHERE record_id = $1
                """
                
                await conn.execute(update_sql, record_id)
                
                # Retrieve record
                select_sql = f"""
                SELECT * FROM {self._schema_name}.{self._records_table}
                WHERE record_id = $1
                """
                
                row = await conn.fetchrow(select_sql, record_id)
                
                if row is None:
                    return None
                
                record = self._row_to_record(row)
                self._update_stats("retrieve", 1)
                
                return record
                
        except PostgresError as e:
            raise AdapterError(
                f"PostgreSQL error during retrieve: {e}",
                adapter_name="postgresql",
                operation="retrieve",
                backend_error=e
            )
        except Exception as e:
            self.logger.warning(f"Error retrieving record {record_id}: {e}")
            return None
    
    def _row_to_record(self, row: Dict[str, Any]) -> RecordEnvelope:
        """Convert database row to RecordEnvelope."""
        # Parse JSON content back to appropriate type
        content_data = row['content']
        
        # Reconstruct the record
        record_data = {
            'record_id': row['record_id'],
            'tenant_id': row['tenant_id'],
            'namespace': row['namespace'],
            'tier': row['tier'],
            'record_type': row['record_type'],
            'content': content_data,
            'embedding': row['embedding'],
            'relevance_score': row['relevance_score'] or 0.0,
            'access_count': row['access_count'] or 0,
            'tags': row['tags'] or [],
            'source': row['source'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'last_accessed': row['last_accessed'],
            'metadata': row['metadata'] or {}
        }
        
        # Add optional fields
        if row['session_id']:
            record_data['session_id'] = row['session_id']
        if row['expires_at']:
            record_data['expires_at'] = row['expires_at']
        if row['provenance']:
            record_data['provenance'] = row['provenance']
        
        return RecordEnvelope(**record_data)
    
    async def query(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Query records with temporal and episodic filtering."""
        return await self._execute_with_retry(
            "query",
            self._query_impl,
            query
        )
    
    async def _query_impl(self, query: MemoryQuery) -> List[RecordEnvelope]:
        """Internal query implementation with temporal support."""
        self._validate_query(query)
        
        try:
            start_time = time.time()
            
            # Build SQL query with temporal constraints
            where_conditions = []
            params = []
            param_count = 0
            
            # Basic filtering
            if query.tenant_id:
                param_count += 1
                where_conditions.append(f"tenant_id = ${param_count}")
                params.append(query.tenant_id)
            
            if query.namespace:
                param_count += 1
                where_conditions.append(f"namespace = ${param_count}")
                params.append(query.namespace)
            
            # Time range filtering
            if query.start_time:
                param_count += 1
                where_conditions.append(f"event_timestamp >= ${param_count}")
                params.append(query.start_time)
            
            if query.end_time:
                param_count += 1
                where_conditions.append(f"event_timestamp <= ${param_count}")
                params.append(query.end_time)
            
            # Tag filtering
            if query.tags:
                param_count += 1
                where_conditions.append(f"tags && ${param_count}")
                params.append(query.tags)
            
            # Full-text search
            if query.query_text and self._enable_full_text_search:
                param_count += 1
                where_conditions.append(f"content_tsvector @@ plainto_tsquery(${param_count})")
                params.append(query.query_text)
            
            # Build final SQL
            where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"
            
            # Order by temporal sequence or relevance
            order_clause = """
            ORDER BY 
                event_timestamp DESC NULLS LAST,
                event_sequence DESC NULLS LAST,
                created_at DESC
            """
            
            sql = f"""
            SELECT * FROM {self._schema_name}.{self._records_table}
            WHERE {where_clause}
            {order_clause}
            LIMIT {query.limit}
            """
            
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
                
                records = []
                for row in rows:
                    try:
                        record = self._row_to_record(dict(row))
                        records.append(record)
                    except Exception as e:
                        self.logger.warning(f"Failed to convert row to record: {e}")
                        continue
            
            query_time = time.time() - start_time
            self._query_count += 1
            self._total_query_time += query_time
            self._update_stats("retrieve", len(records))
            
            if query_time > 1.0:
                self.logger.warning(f"Slow PostgreSQL query took {query_time:.2f}s")
            
            return records
            
        except PostgresError as e:
            raise AdapterError(
                f"PostgreSQL error during query: {e}",
                adapter_name="postgresql",
                operation="query",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during query: {e}",
                adapter_name="postgresql",
                operation="query",
                backend_error=e
            )
    
    async def delete(self, record_id: str) -> bool:
        """Delete a memory record and related data."""
        return await self._execute_with_retry(
            "delete",
            self._delete_impl,
            record_id
        )
    
    async def _delete_impl(self, record_id: str) -> bool:
        """Internal delete implementation."""
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    # Delete from main table (cascades to events and metadata)
                    sql = f"DELETE FROM {self._schema_name}.{self._records_table} WHERE record_id = $1"
                    result = await conn.execute(sql, record_id)
                    
                    # Check if any rows were deleted
                    deleted_count = int(result.split()[-1])
                    
                    if deleted_count > 0:
                        self._update_stats("delete", 1)
                        return True
                    else:
                        return False
                        
        except PostgresError as e:
            raise AdapterError(
                f"PostgreSQL error during delete: {e}",
                adapter_name="postgresql",
                operation="delete",
                backend_error=e
            )
        except Exception as e:
            raise AdapterError(
                f"Unexpected error during delete: {e}",
                adapter_name="postgresql",
                operation="delete",
                backend_error=e
            )
    
    async def update_relevance(
        self, 
        record_id: str, 
        new_relevance: float
    ) -> bool:
        """Update relevance score for a record."""
        try:
            async with self._pool.acquire() as conn:
                sql = f"""
                UPDATE {self._schema_name}.{self._records_table} 
                SET relevance_score = $1, updated_at = NOW()
                WHERE record_id = $2
                """
                
                result = await conn.execute(sql, new_relevance, record_id)
                updated_count = int(result.split()[-1])
                
                return updated_count > 0
                
        except Exception as e:
            self.logger.error(f"Failed to update relevance for {record_id}: {e}")
            return False
    
    async def cleanup_expired(self) -> int:
        """Remove expired records based on expires_at timestamp."""
        try:
            async with self._pool.acquire() as conn:
                sql = f"""
                DELETE FROM {self._schema_name}.{self._records_table}
                WHERE expires_at IS NOT NULL AND expires_at < NOW()
                """
                
                result = await conn.execute(sql)
                deleted_count = int(result.split()[-1])
                
                if deleted_count > 0:
                    self.logger.info(f"Cleaned up {deleted_count} expired episodic records")
                
                return deleted_count
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired records: {e}")
            return 0
    
    async def get_timeline(
        self, 
        tenant_id: str,
        namespace: str,
        session_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[RecordEnvelope]:
        """Get chronological timeline of episodic events."""
        try:
            where_conditions = ["tenant_id = $1", "namespace = $2"]
            params = [tenant_id, namespace]
            param_count = 2
            
            if session_id:
                param_count += 1
                where_conditions.append(f"session_id = ${param_count}")
                params.append(session_id)
            
            if start_time:
                param_count += 1
                where_conditions.append(f"event_timestamp >= ${param_count}")
                params.append(start_time)
            
            if end_time:
                param_count += 1
                where_conditions.append(f"event_timestamp <= ${param_count}")
                params.append(end_time)
            
            where_clause = " AND ".join(where_conditions)
            
            sql = f"""
            SELECT * FROM {self._schema_name}.{self._records_table}
            WHERE {where_clause}
            ORDER BY 
                COALESCE(event_timestamp, created_at) ASC,
                event_sequence ASC NULLS LAST
            LIMIT {limit}
            """
            
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
                
                return [self._row_to_record(dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Failed to get timeline: {e}")
            return []
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform PostgreSQL health check."""
        try:
            async with self._pool.acquire() as conn:
                # Test basic connectivity
                start_time = time.time()
                version = await conn.fetchval("SELECT version()")
                health_time = time.time() - start_time
                
                # Get table statistics
                stats_sql = f"""
                SELECT 
                    (SELECT COUNT(*) FROM {self._schema_name}.{self._records_table}) as record_count,
                    (SELECT COUNT(*) FROM {self._schema_name}.{self._events_table}) as event_count,
                    (SELECT COUNT(*) FROM {self._schema_name}.{self._sessions_table}) as session_count
                """
                
                stats = await conn.fetchrow(stats_sql)
                
                return {
                    "postgresql_version": version,
                    "database": self._database,
                    "schema": self._schema_name,
                    "pool_size": f"{self._pool.get_size()}/{self._max_size}",
                    "record_count": stats["record_count"],
                    "event_count": stats["event_count"], 
                    "session_count": stats["session_count"],
                    "query_count": self._query_count,
                    "transaction_count": self._transaction_count,
                    "average_query_time": (
                        self._total_query_time / max(1, self._query_count)
                    ),
                    "health_check_time": health_time,
                    "partitioning_enabled": self._use_partitioning,
                    "full_text_search": self._enable_full_text_search
                }
                
        except Exception as e:
            raise AdapterError(
                f"PostgreSQL health check failed: {e}",
                adapter_name="postgresql",
                operation="health_check",
                backend_error=e
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get PostgreSQL adapter statistics."""
        base_stats = await super().get_stats()
        
        pg_stats = {
            "host": self._host,
            "port": self._port,
            "database": self._database,
            "schema": self._schema_name,
            "pool_size": f"{self._min_size}-{self._max_size}",
            "connections_created": self._connections_created,
            "query_count": self._query_count,
            "transaction_count": self._transaction_count,
            "average_query_time": (
                self._total_query_time / max(1, self._query_count)
            ),
            "partitioning_enabled": self._use_partitioning,
            "full_text_search": self._enable_full_text_search,
            "last_vacuum": self._last_vacuum.isoformat() if self._last_vacuum else None
        }
        
        base_stats.update(pg_stats)
        return base_stats
    
    async def _cleanup_connections(self) -> None:
        """Clean up PostgreSQL connections."""
        try:
            if self._pool:
                await self._pool.close()
        except Exception as e:
            self.logger.warning(f"Error during PostgreSQL cleanup: {e}")
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """Get adapter capabilities."""
        capabilities = [
            AdapterCapability(
                name="episodic_memory",
                version="1.0.0",
                description="Temporal event sequence storage and retrieval"
            ),
            AdapterCapability(
                name="relational_storage",
                version="1.0.0",
                description="ACID compliant relational database storage"
            ),
            AdapterCapability(
                name="temporal_queries",
                version="1.0.0",
                description="Complex temporal and chronological queries"
            ),
            AdapterCapability(
                name="session_management",
                version="1.0.0",
                description="Session-based memory organization"
            ),
            AdapterCapability(
                name="event_tracking",
                version="1.0.0",
                description="Detailed event sequence tracking"
            ),
            AdapterCapability(
                name="transaction_support",
                version="1.0.0",
                description="ACID transaction support"
            )
        ]
        
        if self._enable_full_text_search:
            capabilities.append(AdapterCapability(
                name="full_text_search",
                version="1.0.0",
                description="PostgreSQL full-text search capabilities"
            ))
        
        if self._use_partitioning:
            capabilities.append(AdapterCapability(
                name="table_partitioning",
                version="1.0.0",
                description="Automatic table partitioning for performance"
            ))
        
        return capabilities