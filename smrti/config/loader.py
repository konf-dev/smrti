"""
smrti/config/loader.py - Configuration loading and hot-reload management

Implements configuration loading from multiple sources, hot-reload capabilities,
and configuration change detection for dynamic system reconfiguration.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Callable, Type
from dataclasses import dataclass
from enum import Enum
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

from .settings import SmrtiConfig
from .environment import EnvironmentManager, auto_detect_environment_manager


class ConfigSource(str, Enum):
    """Configuration source types."""
    ENV_VARS = "environment_variables"
    CONFIG_FILE = "config_file"
    DEFAULTS = "defaults"
    RUNTIME_OVERRIDE = "runtime_override"


@dataclass
class ConfigChangeEvent:
    """Represents a configuration change event."""
    
    source: ConfigSource
    path: Optional[str] = None
    old_value: Any = None
    new_value: Any = None
    timestamp: float = 0.0
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class ConfigFileWatcher(FileSystemEventHandler):
    """File system watcher for configuration files."""
    
    def __init__(self, callback: Callable[[str], None]):
        """Initialize the file watcher.
        
        Args:
            callback: Function to call when file changes detected
        """
        super().__init__()
        self.callback = callback
        self.last_modified = {}
        self.debounce_delay = 1.0  # 1 second debounce
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not isinstance(event, (FileModifiedEvent, FileCreatedEvent)):
            return
        
        if event.is_directory:
            return
        
        file_path = event.src_path
        
        # Debounce rapid file changes
        current_time = time.time()
        last_mod_time = self.last_modified.get(file_path, 0)
        
        if current_time - last_mod_time < self.debounce_delay:
            return
        
        self.last_modified[file_path] = current_time
        
        # Only watch configuration files
        if self._is_config_file(file_path):
            self.callback(file_path)
    
    def _is_config_file(self, file_path: str) -> bool:
        """Check if file is a configuration file."""
        config_extensions = ['.json', '.yaml', '.yml', '.toml', '.env']
        return any(file_path.endswith(ext) for ext in config_extensions)


class ConfigLoader:
    """Loads and manages Smrti configuration from multiple sources."""
    
    def __init__(self, 
                 config_class: Type[SmrtiConfig] = SmrtiConfig,
                 env_manager: Optional[EnvironmentManager] = None):
        """Initialize the configuration loader.
        
        Args:
            config_class: Configuration class to use
            env_manager: Environment manager instance
        """
        self.config_class = config_class
        self.env_manager = env_manager or auto_detect_environment_manager()
        
        self.current_config: Optional[SmrtiConfig] = None
        self.config_sources: Dict[ConfigSource, Any] = {}
        self.change_callbacks: List[Callable[[ConfigChangeEvent], None]] = []
        
        # Hot reload support
        self.hot_reload_enabled = False
        self.file_observer: Optional[Observer] = None
        self.watched_files: set[str] = set()
        
        # Change detection
        self.config_hash: Optional[str] = None
        self._setup_change_detection()
    
    def _setup_change_detection(self):
        """Setup configuration change detection."""
        self.register_change_callback(self._log_config_change)
    
    def _log_config_change(self, event: ConfigChangeEvent):
        """Log configuration changes."""
        print(f"Configuration changed: {event.source} - {event.path}")
    
    def load_config(self, 
                   config_file: Optional[Union[str, Path]] = None,
                   env_file: Optional[Union[str, Path]] = None,
                   enable_hot_reload: bool = True) -> SmrtiConfig:
        """Load configuration from all sources.
        
        Args:
            config_file: Optional configuration file path
            env_file: Optional environment file path
            enable_hot_reload: Enable hot-reload functionality
            
        Returns:
            Loaded configuration
        """
        # Load environment variables
        if env_file:
            self.env_manager.load_env_file(env_file)
        
        # Start with defaults
        config_data = {}
        self.config_sources[ConfigSource.DEFAULTS] = True
        
        # Load from configuration file
        if config_file:
            file_config = self._load_config_file(config_file)
            config_data.update(file_config)
            self.config_sources[ConfigSource.CONFIG_FILE] = str(config_file)
            
            # Add to watched files
            self.watched_files.add(str(Path(config_file).resolve()))
        
        # Apply environment variables
        env_config = self._load_env_config()
        config_data.update(env_config)
        self.config_sources[ConfigSource.ENV_VARS] = True
        
        # Create configuration instance
        if config_data and self._has_complete_config(config_data):
            self.current_config = self.config_class.model_validate(config_data)
        else:
            # Use default config and overlay with any provided data
            self.current_config = self.config_class.create_default_config()
            if config_data:
                # Apply any overrides from environment variables
                self._apply_config_overrides(self.current_config, config_data)
        
        # Calculate configuration hash
        self.config_hash = self._calculate_config_hash(self.current_config)
        
        # Enable hot reload if requested
        if enable_hot_reload:
            self.enable_hot_reload()
        
        return self.current_config
    
    def _load_config_file(self, config_file: Union[str, Path]) -> Dict[str, Any]:
        """Load configuration from a file.
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.suffix.lower() == '.json':
                return json.load(f)
            elif config_path.suffix.lower() in ['.yaml', '.yml']:
                try:
                    import yaml
                    return yaml.safe_load(f) or {}
                except ImportError:
                    raise ImportError("PyYAML is required for YAML configuration files")
            elif config_path.suffix.lower() == '.toml':
                try:
                    import toml
                    return toml.load(f)
                except ImportError:
                    raise ImportError("toml is required for TOML configuration files")
            else:
                raise ValueError(f"Unsupported configuration file format: {config_path.suffix}")
    
    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables.
        
        Returns:
            Configuration dictionary from environment
        """
        # Register common environment variables
        self._register_common_env_vars()
        
        # Build configuration from registered variables
        config = {}
        for key, var in self.env_manager.variables.items():
            if var.value is not None:
                # Convert flat keys to nested structure
                self._set_nested_value(config, key, var.value)
        
        return config
    
    def _register_common_env_vars(self):
        """Register common environment variables for Smrti."""
        from .environment import str_to_bool, str_to_int, str_to_float, str_to_list, port_validator
        
        # System settings
        self.env_manager.register_variable(
            "system_name", 
            default="smrti", 
            description="System name"
        )
        
        self.env_manager.register_variable(
            "environment", 
            default="development", 
            description="Deployment environment"
        )
        
        # Redis configuration
        self.env_manager.register_variable(
            "redis_host", 
            default="localhost", 
            description="Redis host address"
        )
        
        self.env_manager.register_variable(
            "redis_port", 
            default=6379, 
            transformer=str_to_int,
            validator=port_validator,
            description="Redis port number"
        )
        
        # Database configuration
        self.env_manager.register_variable(
            "database_url", 
            description="Database connection URL"
        )
        
        # Security settings (required in production only)
        is_production = self.env_manager.context.environment.value == "production"
        self.env_manager.register_variable(
            "jwt_secret", 
            default="dev-secret-key" if not is_production else None,
            required=is_production,
            description="JWT signing secret"
        )
        
        self.env_manager.register_variable(
            "enable_auth", 
            default=True,
            transformer=str_to_bool,
            description="Enable authentication"
        )
        
        # Observability settings
        self.env_manager.register_variable(
            "log_level", 
            default="INFO", 
            description="Logging level"
        )
        
        self.env_manager.register_variable(
            "enable_metrics", 
            default=True,
            transformer=str_to_bool,
            description="Enable metrics collection"
        )
        
        # Performance settings
        self.env_manager.register_variable(
            "max_concurrent_operations", 
            default=10,
            transformer=str_to_int,
            description="Maximum concurrent operations"
        )
        
        # Embedding settings
        self.env_manager.register_variable(
            "embedding_provider", 
            default="sentence_transformers",
            description="Embedding provider type"
        )
        
        self.env_manager.register_variable(
            "embedding_model", 
            default="sentence-transformers/all-MiniLM-L6-v2",
            description="Embedding model name"
        )
        
        # Feature flags
        self.env_manager.register_variable(
            "enable_hot_reload", 
            default=True,
            transformer=str_to_bool,
            description="Enable hot configuration reloading"
        )
    
    def _set_nested_value(self, config: Dict[str, Any], key: str, value: Any):
        """Set a nested value in configuration dictionary.
        
        Args:
            config: Configuration dictionary
            key: Dot-separated key path
            value: Value to set
        """
        parts = key.split('.')
        current = config
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    def _has_complete_config(self, config_data: Dict[str, Any]) -> bool:
        """Check if config data has all required fields.
        
        Args:
            config_data: Configuration dictionary
            
        Returns:
            True if configuration is complete
        """
        # Check for essential fields that indicate a complete config
        required_fields = ['embedding', 'tiers']
        return all(field in config_data for field in required_fields)
    
    def _apply_config_overrides(self, config: SmrtiConfig, overrides: Dict[str, Any]):
        """Apply configuration overrides to existing config.
        
        Args:
            config: Base configuration
            overrides: Override values
        """
        # Convert config to dict, apply overrides, and recreate
        config_dict = config.model_dump()
        
        for key, value in overrides.items():
            self._set_nested_value(config_dict, key, value)
        
        # Recreate config with overrides
        new_config = self.config_class.model_validate(config_dict)
        
        # Update fields
        for field_name, field_value in new_config.model_dump().items():
            setattr(config, field_name, field_value)
    
    def _calculate_config_hash(self, config: SmrtiConfig) -> str:
        """Calculate hash of configuration for change detection.
        
        Args:
            config: Configuration instance
            
        Returns:
            Configuration hash
        """
        import hashlib
        
        config_dict = config.model_dump()
        config_str = json.dumps(config_dict, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()
    
    def enable_hot_reload(self):
        """Enable hot-reload functionality."""
        if self.hot_reload_enabled:
            return
        
        self.hot_reload_enabled = True
        
        # Start file watcher
        if self.watched_files:
            self.file_observer = Observer()
            file_watcher = ConfigFileWatcher(self._on_file_changed)
            
            # Watch directories containing config files
            watched_dirs = set()
            for file_path in self.watched_files:
                directory = Path(file_path).parent
                if directory not in watched_dirs:
                    self.file_observer.schedule(file_watcher, str(directory), recursive=False)
                    watched_dirs.add(directory)
            
            self.file_observer.start()
    
    def disable_hot_reload(self):
        """Disable hot-reload functionality."""
        if not self.hot_reload_enabled:
            return
        
        self.hot_reload_enabled = False
        
        if self.file_observer:
            self.file_observer.stop()
            self.file_observer.join()
            self.file_observer = None
    
    def _on_file_changed(self, file_path: str):
        """Handle configuration file changes.
        
        Args:
            file_path: Path to changed file
        """
        if not self.hot_reload_enabled:
            return
        
        try:
            # Reload configuration
            old_config = self.current_config
            
            # Determine source file from watched files
            config_file = None
            for watched_file in self.watched_files:
                if Path(watched_file).samefile(Path(file_path)):
                    config_file = watched_file
                    break
            
            if config_file:
                self.reload_config(config_file)
                
                # Notify change callbacks
                event = ConfigChangeEvent(
                    source=ConfigSource.CONFIG_FILE,
                    path=file_path,
                    old_value=old_config,
                    new_value=self.current_config
                )
                self._notify_change_callbacks(event)
        
        except Exception as e:
            print(f"Error reloading configuration from {file_path}: {e}")
    
    def reload_config(self, config_file: Optional[str] = None) -> SmrtiConfig:
        """Reload configuration from sources.
        
        Args:
            config_file: Optional specific config file to reload
            
        Returns:
            Reloaded configuration
        """
        # Use the same config file if not specified
        if config_file is None and ConfigSource.CONFIG_FILE in self.config_sources:
            config_file = self.config_sources[ConfigSource.CONFIG_FILE]
        
        return self.load_config(
            config_file=config_file,
            enable_hot_reload=self.hot_reload_enabled
        )
    
    def register_change_callback(self, callback: Callable[[ConfigChangeEvent], None]):
        """Register a callback for configuration changes.
        
        Args:
            callback: Function to call on configuration changes
        """
        self.change_callbacks.append(callback)
    
    def unregister_change_callback(self, callback: Callable[[ConfigChangeEvent], None]):
        """Unregister a configuration change callback.
        
        Args:
            callback: Callback function to remove
        """
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
    def _notify_change_callbacks(self, event: ConfigChangeEvent):
        """Notify all registered change callbacks.
        
        Args:
            event: Configuration change event
        """
        for callback in self.change_callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"Error in configuration change callback: {e}")
    
    def override_config(self, key: str, value: Any):
        """Override a configuration value at runtime.
        
        Args:
            key: Configuration key (dot-separated path)
            value: New value
        """
        if not self.current_config:
            raise RuntimeError("No configuration loaded")
        
        old_value = self._get_nested_value(self.current_config.model_dump(), key)
        
        # Apply override to current config
        config_dict = self.current_config.model_dump()
        self._set_nested_value(config_dict, key, value)
        
        # Create new config instance
        self.current_config = self.config_class.model_validate(config_dict)
        
        # Update sources
        if ConfigSource.RUNTIME_OVERRIDE not in self.config_sources:
            self.config_sources[ConfigSource.RUNTIME_OVERRIDE] = {}
        self.config_sources[ConfigSource.RUNTIME_OVERRIDE][key] = value
        
        # Update hash
        self.config_hash = self._calculate_config_hash(self.current_config)
        
        # Notify callbacks
        event = ConfigChangeEvent(
            source=ConfigSource.RUNTIME_OVERRIDE,
            path=key,
            old_value=old_value,
            new_value=value
        )
        self._notify_change_callbacks(event)
    
    def _get_nested_value(self, config: Dict[str, Any], key: str) -> Any:
        """Get a nested value from configuration dictionary.
        
        Args:
            config: Configuration dictionary
            key: Dot-separated key path
            
        Returns:
            Value at key path
        """
        parts = key.split('.')
        current = config
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        
        return current
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get information about the loaded configuration.
        
        Returns:
            Configuration information
        """
        return {
            'config_class': self.config_class.__name__,
            'config_hash': self.config_hash,
            'sources': list(self.config_sources.keys()),
            'hot_reload_enabled': self.hot_reload_enabled,
            'watched_files': list(self.watched_files),
            'change_callbacks': len(self.change_callbacks),
            'environment_info': self.env_manager.get_environment_info()
        }
    
    def export_config(self) -> Dict[str, Any]:
        """Export current configuration as dictionary.
        
        Returns:
            Configuration dictionary
        """
        if not self.current_config:
            return {}
        
        return self.current_config.model_dump()
    
    def cleanup(self):
        """Cleanup resources used by the loader."""
        self.disable_hot_reload()
        self.change_callbacks.clear()


# Convenience functions for common loading scenarios
def load_default_config() -> SmrtiConfig:
    """Load configuration with default settings."""
    loader = ConfigLoader()
    return loader.load_config()


def load_config_from_file(config_file: Union[str, Path]) -> SmrtiConfig:
    """Load configuration from a specific file.
    
    Args:
        config_file: Path to configuration file
        
    Returns:
        Loaded configuration
    """
    loader = ConfigLoader()
    return loader.load_config(config_file=config_file)


def load_config_with_env(env_file: Union[str, Path]) -> SmrtiConfig:
    """Load configuration with specific environment file.
    
    Args:
        env_file: Path to environment file
        
    Returns:
        Loaded configuration
    """
    loader = ConfigLoader()
    return loader.load_config(env_file=env_file)


async def async_config_loader(config_file: Optional[str] = None,
                             env_file: Optional[str] = None,
                             enable_hot_reload: bool = True) -> tuple[SmrtiConfig, ConfigLoader]:
    """Asynchronously load configuration with hot-reload support.
    
    Args:
        config_file: Optional configuration file path
        env_file: Optional environment file path
        enable_hot_reload: Enable hot-reload functionality
        
    Returns:
        Tuple of (configuration, loader)
    """
    loop = asyncio.get_event_loop()
    
    loader = ConfigLoader()
    config = await loop.run_in_executor(
        None, 
        loader.load_config, 
        config_file, 
        env_file, 
        enable_hot_reload
    )
    
    return config, loader