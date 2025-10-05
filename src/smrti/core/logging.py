"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from smrti.core.config import get_settings


def add_log_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add log level to event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def censor_sensitive_data(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Remove sensitive data from logs."""
    # List of field names to censor
    sensitive_fields = {
        "api_key",
        "password",
        "secret",
        "token",
        "authorization",
        "embedding",  # Too large
    }

    for field in sensitive_fields:
        if field in event_dict:
            event_dict[field] = "***REDACTED***"

    return event_dict


def configure_logging() -> None:
    """
    Configure structured logging for the application.
    
    Sets up structlog with JSON formatting for production
    and human-readable formatting for development.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Configure structlog processors
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_log_level,
        censor_sensitive_data,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    # Add appropriate final processor based on environment
    if settings.log_level.upper() == "DEBUG":
        # Human-readable for development
        processors.extend(
            [
                structlog.dev.ConsoleRenderer(
                    colors=True,
                    exception_formatter=structlog.dev.plain_traceback,
                )
            ]
        )
    else:
        # JSON for production (structured, machine-readable)
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ]
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured structlog logger
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("operation_completed", memory_id="123", duration_ms=45.2)
    """
    return structlog.get_logger(name)
