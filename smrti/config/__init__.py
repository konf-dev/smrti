"""
smrti/config/__init__.py - Configuration system exports

Provides configuration management with validation, environment variable support,
and dynamic reloading capabilities.
"""

from .settings import (
    SmrtiConfig,
    TierConfiguration,
    AdapterConfiguration,
    EmbeddingConfiguration,
    ConsolidationConfiguration,
    ObservabilityConfiguration,
    SecurityConfiguration,
    load_config_from_env,
    load_config_from_file,
    validate_config
)

from .environment import (
    Environment,
    EnvironmentManager,
    EnvironmentContext,
    auto_detect_environment_manager
)

from .loader import (
    ConfigLoader,
    ConfigSource,
    ConfigChangeEvent,
    load_default_config,
    load_config_from_file as load_config_file_loader
)

__all__ = [
    # Main configuration classes
    "SmrtiConfig",
    "TierConfiguration", 
    "AdapterConfiguration",
    "EmbeddingConfiguration",
    "ConsolidationConfiguration",
    "ObservabilityConfiguration",
    "SecurityConfiguration",
    
    # Configuration loading
    "load_config_from_env",
    "load_config_from_file",
    "validate_config",
    
    # Environment management
    "Environment",
    "EnvironmentManager",
    "EnvironmentContext", 
    "auto_detect_environment_manager",
    
    # Dynamic loading and hot reload
    "ConfigLoader",
    "ConfigSource",
    "ConfigChangeEvent",
    "load_default_config",
    "load_config_file_loader"
]