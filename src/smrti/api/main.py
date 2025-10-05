"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
import redis.asyncio as redis
from qdrant_client import QdrantClient
import asyncpg

from smrti.api.routes import health, memory
from smrti.api.auth import APIKeyMiddleware
from smrti.api.storage_manager import StorageManager
from smrti.api.dependencies import set_storage_manager
from smrti.storage.adapters import (
    RedisWorkingAdapter,
    RedisShortTermAdapter,
    QdrantLongTermAdapter,
    PostgresEpisodicAdapter,
    PostgresSemanticAdapter
)
from smrti.embedding.local import LocalEmbeddingProvider
from smrti.core.config import get_settings
from smrti.core.logging import get_logger
from smrti.core.exceptions import SmrtiError

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    
    logger.info("startup_initiated", version=settings.api_version)
    
    # Initialize connections
    redis_client = None
    qdrant_client = None
    pg_pool = None
    
    try:
        # Redis connection
        logger.info("connecting_to_redis", url=settings.redis_url)
        redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50
        )
        await redis_client.ping()
        logger.info("redis_connected")
        
        # Qdrant connection
        logger.info("connecting_to_qdrant", host=settings.qdrant_host)
        qdrant_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=30.0
        )
        logger.info("qdrant_connected")
        
        # PostgreSQL connection pool
        logger.info("connecting_to_postgres", host=settings.postgres_host)
        pg_pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_database,
            user=settings.postgres_user,
            password=settings.postgres_password,
            min_size=5,
            max_size=20,
            timeout=30.0
        )
        logger.info("postgres_connected")
        
        # Initialize embedding provider
        logger.info("loading_embedding_model", model=settings.embedding_model)
        embedding_provider = LocalEmbeddingProvider(
            model_name=settings.embedding_model,
            cache_size=settings.embedding_cache_size
        )
        await embedding_provider.health_check()
        logger.info("embedding_model_loaded")
        
        # Initialize storage adapters
        working_adapter = RedisWorkingAdapter(redis_client)
        short_term_adapter = RedisShortTermAdapter(redis_client)
        long_term_adapter = QdrantLongTermAdapter(qdrant_client)
        episodic_adapter = PostgresEpisodicAdapter(pg_pool)
        semantic_adapter = PostgresSemanticAdapter(pg_pool)
        
        # Create storage manager
        storage_manager = StorageManager(
            working_adapter=working_adapter,
            short_term_adapter=short_term_adapter,
            long_term_adapter=long_term_adapter,
            episodic_adapter=episodic_adapter,
            semantic_adapter=semantic_adapter,
            embedding_provider=embedding_provider
        )
        
        # Set global storage manager for dependency injection
        set_storage_manager(storage_manager)
        
        logger.info("startup_complete", version=settings.api_version)
        
        yield
        
    except Exception as e:
        logger.error("startup_failed", error=str(e))
        raise SmrtiError(f"Failed to initialize application: {e}") from e
        
    finally:
        # Cleanup
        logger.info("shutdown_initiated")
        
        if redis_client:
            await redis_client.close()
            logger.info("redis_disconnected")
            
        if pg_pool:
            await pg_pool.close()
            logger.info("postgres_disconnected")
            
        # Qdrant client doesn't need explicit cleanup
        
        # Clear the storage manager
        set_storage_manager(None)
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title="Smrti Memory System",
        description="Multi-tier memory storage and retrieval system with semantic search",
        version=settings.api_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Authentication middleware
    app.add_middleware(APIKeyMiddleware, valid_api_keys=set(settings.get_api_keys()))
    
    # Include routers
    app.include_router(health.router)
    app.include_router(memory.router)
    
    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    logger.info("app_configured", version=settings.api_version)
    
    return app


# Application instance
app = create_app()


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect."""
    return {
        "message": "Smrti Memory System API",
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }
