"""Dependency injection functions for FastAPI."""

from smrti.api.storage_manager import StorageManager


# Global storage manager instance
_storage_manager: StorageManager | None = None


def set_storage_manager(manager: StorageManager) -> None:
    """Set the global storage manager instance."""
    global _storage_manager
    _storage_manager = manager


async def get_storage_manager() -> StorageManager:
    """Dependency injection for storage manager."""
    if _storage_manager is None:
        raise RuntimeError("Storage manager not initialized")
    return _storage_manager
