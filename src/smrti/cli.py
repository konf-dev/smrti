"""Command-line interface for Smrti."""

import sys
from typing import Optional

import uvicorn

from smrti.core.config import get_settings
from smrti.core.logging import get_logger

logger = get_logger(__name__)


def main(args: Optional[list[str]] = None) -> int:
    """
    Main entry point for the CLI.
    
    Usage:
        smrti                  # Start API server with default settings
        smrti --help           # Show help message
    """
    if args is None:
        args = sys.argv[1:]
    
    settings = get_settings()
    
    if "--help" in args or "-h" in args:
        print("""
Smrti - Multi-tier Memory Storage System

Usage:
    smrti                  Start API server with default settings
    smrti --help           Show this help message

Environment Variables:
    HOST                   Server bind address (default: 0.0.0.0)
    PORT                   Server port (default: 8000)
    WORKERS                Number of worker processes (default: 4)
    LOG_LEVEL              Logging level (default: INFO)
    
    API_VERSION            API version (default: 2.0.0)
    API_KEYS               Comma-separated API keys (default: dev-key-123)
    CORS_ORIGINS           Comma-separated CORS origins (default: *)
    
    REDIS_URL              Redis connection URL
    QDRANT_HOST            Qdrant server host
    QDRANT_PORT            Qdrant server port
    POSTGRES_HOST          PostgreSQL server host
    POSTGRES_PORT          PostgreSQL server port
    POSTGRES_DATABASE      PostgreSQL database name
    POSTGRES_USER          PostgreSQL username
    POSTGRES_PASSWORD      PostgreSQL password
    
    EMBEDDING_MODEL        Embedding model name
    EMBEDDING_CACHE_SIZE   LRU cache size for embeddings

API Endpoints:
    GET  /                 Root information
    GET  /health           Health check
    POST /memory/store     Store a memory
    POST /memory/retrieve  Retrieve memories
    DELETE /memory/{type}/{id}  Delete a memory
    GET  /metrics          Prometheus metrics
    GET  /docs             OpenAPI documentation

See documentation: https://github.com/konf-dev/smrti
        """)
        return 0
    
    logger.info(
        "starting_smrti_server",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        version=settings.api_version
    )
    
    try:
        uvicorn.run(
            "smrti.api.main:app",
            host=settings.host,
            port=settings.port,
            workers=settings.workers if settings.workers > 1 else None,
            log_level=settings.log_level.lower(),
            reload=False,
            access_log=True
        )
        return 0
        
    except KeyboardInterrupt:
        logger.info("server_stopped_by_user")
        return 0
        
    except Exception as e:
        logger.error("server_failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
