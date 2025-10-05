"""Authentication middleware for API key validation."""

import secrets
from typing import Callable, Optional
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from smrti.core.logging import get_logger
from smrti.core.exceptions import AuthenticationError

logger = get_logger(__name__)

security = HTTPBearer()


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate API keys and extract namespace.
    
    Expects:
    - Header: Authorization: Bearer <api_key>
    - Header: X-Namespace: <namespace>
    
    Sets:
    - request.state.namespace
    - request.state.api_key
    """
    
    def __init__(self, app, valid_api_keys: set):
        """
        Initialize middleware.
        
        Args:
            app: FastAPI application
            valid_api_keys: Set of valid API keys
        """
        super().__init__(app)
        self.valid_api_keys = valid_api_keys
        
        # Paths that don't require authentication
        self.public_paths = {"/health", "/docs", "/redoc", "/openapi.json", "/metrics"}
    
    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and validate authentication."""
        
        # Skip auth for public paths
        if request.url.path in self.public_paths:
            return await call_next(request)
        
        # Check for API key in Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            logger.warning(
                "missing_authorization_header",
                path=request.url.path,
                client=request.client.host if request.client else "unknown"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Extract API key
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format. Expected: Bearer <api_key>",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        api_key = auth_header[7:]  # Remove "Bearer " prefix
        
        # Validate API key (constant-time comparison)
        if not self._validate_api_key(api_key):
            logger.warning(
                "invalid_api_key",
                path=request.url.path,
                client=request.client.host if request.client else "unknown"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Extract namespace from header
        namespace = request.headers.get("X-Namespace")
        if not namespace:
            logger.warning(
                "missing_namespace_header",
                path=request.url.path,
                api_key_prefix=api_key[:8] if api_key else "none"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-Namespace header"
            )
        
        # Validate namespace format
        if not self._validate_namespace(namespace):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid namespace format. Expected: tenant:id:user:id"
            )
        
        # Store in request state
        request.state.api_key = api_key
        request.state.namespace = namespace
        
        logger.debug(
            "request_authenticated",
            path=request.url.path,
            namespace=namespace,
            api_key_prefix=api_key[:8]
        )
        
        # Continue to endpoint
        response = await call_next(request)
        return response
    
    def _validate_api_key(self, api_key: str) -> bool:
        """
        Validate API key using constant-time comparison.
        
        Args:
            api_key: API key to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not api_key:
            return False
        
        # Use constant-time comparison to prevent timing attacks
        for valid_key in self.valid_api_keys:
            if secrets.compare_digest(api_key, valid_key):
                return True
        
        return False
    
    def _validate_namespace(self, namespace: str) -> bool:
        """
        Validate namespace format.
        
        Args:
            namespace: Namespace string
            
        Returns:
            True if valid format, False otherwise
        """
        if not namespace:
            return False
        
        # Must be hierarchical (at least 2 parts)
        parts = namespace.split(":")
        if len(parts) < 2:
            return False
        
        # Each part must be non-empty
        if any(not part.strip() for part in parts):
            return False
        
        return True


def get_namespace(request: Request) -> str:
    """
    Extract namespace from request state.
    
    Args:
        request: FastAPI request
        
    Returns:
        Namespace string
        
    Raises:
        HTTPException: If namespace not found in state
    """
    if not hasattr(request.state, "namespace"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Namespace not found in request state"
        )
    
    return request.state.namespace


def get_api_key(request: Request) -> str:
    """
    Extract API key from request state.
    
    Args:
        request: FastAPI request
        
    Returns:
        API key string
        
    Raises:
        HTTPException: If API key not found in state
    """
    if not hasattr(request.state, "api_key"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not found in request state"
        )
    
    return request.state.api_key
