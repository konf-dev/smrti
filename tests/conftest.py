"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio

# Configure asyncio for tests
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create an event loop for the test session.
    
    This ensures all tests use the same event loop.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test markers for categorizing tests
def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "unit: Unit tests (fast, isolated, no external dependencies)",
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration tests (require real databases)",
    )
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests (full stack with docker-compose)",
    )
