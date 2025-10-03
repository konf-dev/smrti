"""
smrti/config/environment.py - Environment management and detection

Handles environment-specific configuration management, variable resolution,
and environment detection for different deployment contexts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Callable
from dataclasses import dataclass, field
from enum import Enum


class Environment(str, Enum):
    """Supported deployment environments."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class VariableSource(str, Enum):
    """Sources for configuration variables."""
    ENV_VAR = "environment_variable"
    CONFIG_FILE = "config_file"
    DEFAULT = "default"
    OVERRIDE = "override"


@dataclass
class EnvironmentVariable:
    """Represents a configuration environment variable."""
    
    key: str
    value: Any = None
    source: VariableSource = VariableSource.DEFAULT
    required: bool = False
    description: str = ""
    validator: Optional[Callable[[Any], bool]] = None
    transformer: Optional[Callable[[Any], Any]] = None
    
    def __post_init__(self):
        """Post-initialization processing."""
        if self.transformer and self.value is not None:
            try:
                self.value = self.transformer(self.value)
            except Exception as e:
                raise ValueError(f"Failed to transform value for {self.key}: {e}")
        
        if self.validator and self.value is not None:
            if not self.validator(self.value):
                raise ValueError(f"Validation failed for {self.key}: {self.value}")


@dataclass
class EnvironmentContext:
    """Context information about the current environment."""
    
    environment: Environment = Environment.DEVELOPMENT
    is_containerized: bool = False
    is_cloud_deployment: bool = False
    has_external_secrets: bool = False
    platform: str = ""
    hostname: str = ""
    python_version: str = ""
    workspace_root: Path = field(default_factory=lambda: Path.cwd())
    
    def __post_init__(self):
        """Detect environment characteristics."""
        self.platform = sys.platform
        self.hostname = os.environ.get('HOSTNAME', 'unknown')
        self.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        
        # Detect containerization
        self.is_containerized = self._detect_containerization()
        
        # Detect cloud deployment
        self.is_cloud_deployment = self._detect_cloud_deployment()
        
        # Detect external secrets management
        self.has_external_secrets = self._detect_external_secrets()
    
    def _detect_containerization(self) -> bool:
        """Detect if running in a container."""
        # Check for Docker
        if os.path.exists('/.dockerenv'):
            return True
        
        # Check for Kubernetes
        if os.environ.get('KUBERNETES_SERVICE_HOST'):
            return True
        
        # Check for container runtime
        if os.environ.get('container'):
            return True
        
        # Check cgroup (less reliable)
        try:
            with open('/proc/1/cgroup', 'r') as f:
                content = f.read()
                if 'docker' in content or 'kubepods' in content:
                    return True
        except (FileNotFoundError, PermissionError):
            pass
        
        return False
    
    def _detect_cloud_deployment(self) -> bool:
        """Detect if running in a cloud environment."""
        cloud_indicators = [
            'AWS_REGION', 'AWS_DEFAULT_REGION',  # AWS
            'GOOGLE_CLOUD_PROJECT', 'GCP_PROJECT',  # GCP
            'AZURE_CLIENT_ID', 'AZURE_SUBSCRIPTION_ID',  # Azure
            'HEROKU_APP_NAME',  # Heroku
            'VERCEL_ENV',  # Vercel
            'RAILWAY_ENVIRONMENT',  # Railway
        ]
        
        return any(os.environ.get(var) for var in cloud_indicators)
    
    def _detect_external_secrets(self) -> bool:
        """Detect external secrets management systems."""
        secrets_indicators = [
            'VAULT_ADDR',  # HashiCorp Vault
            'SECRET_MANAGER_PROJECT',  # Google Secret Manager
            'AWS_SECRETS_MANAGER_REGION',  # AWS Secrets Manager
            'AZURE_KEYVAULT_URL',  # Azure Key Vault
        ]
        
        return any(os.environ.get(var) for var in secrets_indicators)


class EnvironmentManager:
    """Manages environment variables and configuration resolution."""
    
    def __init__(self, env_prefix: str = "SMRTI_"):
        """Initialize the environment manager.
        
        Args:
            env_prefix: Prefix for environment variables
        """
        self.env_prefix = env_prefix
        self.variables: Dict[str, EnvironmentVariable] = {}
        self.context = EnvironmentContext()
        self._load_environment_detection()
    
    def _load_environment_detection(self):
        """Load and detect the current environment."""
        # Detect environment from ENV variable or context
        env_name = os.environ.get(f'{self.env_prefix}ENVIRONMENT', 
                                  os.environ.get('ENV', 
                                  os.environ.get('NODE_ENV', 'development')))
        
        try:
            self.context.environment = Environment(env_name.lower())
        except ValueError:
            # Default to development for unknown environments
            self.context.environment = Environment.DEVELOPMENT
    
    def register_variable(self, 
                         key: str, 
                         default: Any = None,
                         required: bool = False,
                         description: str = "",
                         validator: Optional[Callable[[Any], bool]] = None,
                         transformer: Optional[Callable[[Any], Any]] = None,
                         env_key: Optional[str] = None) -> EnvironmentVariable:
        """Register an environment variable.
        
        Args:
            key: Configuration key name
            default: Default value if not found
            required: Whether the variable is required
            description: Variable description
            validator: Function to validate the value
            transformer: Function to transform the value
            env_key: Override environment variable name
            
        Returns:
            EnvironmentVariable instance
        """
        # Determine environment variable name
        if env_key is None:
            env_key = f"{self.env_prefix}{key.upper()}"
        
        # Get value from environment
        env_value = os.environ.get(env_key)
        
        # Determine value and source
        if env_value is not None:
            value = env_value
            source = VariableSource.ENV_VAR
        elif default is not None:
            value = default
            source = VariableSource.DEFAULT
        else:
            value = None
            source = VariableSource.DEFAULT
        
        # Create and register variable
        var = EnvironmentVariable(
            key=key,
            value=value,
            source=source,
            required=required,
            description=description,
            validator=validator,
            transformer=transformer
        )
        
        self.variables[key] = var
        
        # Validate required variables
        if required and value is None:
            raise ValueError(f"Required environment variable not found: {env_key}")
        
        return var
    
    def get_variable(self, key: str) -> Optional[EnvironmentVariable]:
        """Get a registered environment variable.
        
        Args:
            key: Variable key
            
        Returns:
            EnvironmentVariable or None
        """
        return self.variables.get(key)
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """Get the value of an environment variable.
        
        Args:
            key: Variable key
            default: Default value if variable not found
            
        Returns:
            Variable value or default
        """
        var = self.variables.get(key)
        if var is not None:
            return var.value
        return default
    
    def set_override(self, key: str, value: Any):
        """Set an override value for a variable.
        
        Args:
            key: Variable key
            value: Override value
        """
        if key in self.variables:
            var = self.variables[key]
            var.value = value
            var.source = VariableSource.OVERRIDE
            
            # Apply transformer if available
            if var.transformer:
                var.value = var.transformer(var.value)
            
            # Validate if validator available
            if var.validator and not var.validator(var.value):
                raise ValueError(f"Override validation failed for {key}: {value}")
        else:
            # Create new override variable
            self.variables[key] = EnvironmentVariable(
                key=key,
                value=value,
                source=VariableSource.OVERRIDE
            )
    
    def load_env_file(self, env_file: Union[str, Path]):
        """Load environment variables from a .env file.
        
        Args:
            env_file: Path to .env file
        """
        env_file = Path(env_file)
        if not env_file.exists():
            return
        
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Parse key=value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Set in environment if not already set
                    if key not in os.environ:
                        os.environ[key] = value
    
    def validate_all(self) -> tuple[bool, List[str]]:
        """Validate all registered variables.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        for key, var in self.variables.items():
            # Check required variables
            if var.required and var.value is None:
                errors.append(f"Required variable {key} is not set")
            
            # Run validators
            if var.validator and var.value is not None:
                try:
                    if not var.validator(var.value):
                        errors.append(f"Validation failed for variable {key}")
                except Exception as e:
                    errors.append(f"Validator error for {key}: {e}")
        
        return len(errors) == 0, errors
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Get comprehensive environment information.
        
        Returns:
            Dictionary with environment details
        """
        return {
            'environment': self.context.environment.value,
            'is_containerized': self.context.is_containerized,
            'is_cloud_deployment': self.context.is_cloud_deployment,
            'has_external_secrets': self.context.has_external_secrets,
            'platform': self.context.platform,
            'hostname': self.context.hostname,
            'python_version': self.context.python_version,
            'workspace_root': str(self.context.workspace_root),
            'env_prefix': self.env_prefix,
            'registered_variables': len(self.variables),
            'required_variables': sum(1 for var in self.variables.values() if var.required),
        }
    
    def export_config(self) -> Dict[str, Any]:
        """Export current configuration as a dictionary.
        
        Returns:
            Configuration dictionary
        """
        config = {}
        for key, var in self.variables.items():
            config[key] = {
                'value': var.value,
                'source': var.source.value,
                'required': var.required,
                'description': var.description
            }
        
        return config


# Common transformers
def str_to_bool(value: Any) -> bool:
    """Transform string values to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
    return bool(value)


def str_to_int(value: Any) -> int:
    """Transform string values to integer."""
    if isinstance(value, int):
        return value
    return int(value)


def str_to_float(value: Any) -> float:
    """Transform string values to float."""
    if isinstance(value, float):
        return value
    return float(value)


def str_to_list(separator: str = ',') -> Callable[[Any], List[str]]:
    """Create a transformer to split strings into lists.
    
    Args:
        separator: String separator
        
    Returns:
        Transformer function
    """
    def transformer(value: Any) -> List[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [item.strip() for item in value.split(separator) if item.strip()]
        return [str(value)]
    
    return transformer


def path_expander(value: Any) -> Path:
    """Transform path strings to expanded Path objects."""
    if isinstance(value, Path):
        return value
    path_str = str(value)
    # Expand user home directory
    path_str = os.path.expanduser(path_str)
    # Expand environment variables
    path_str = os.path.expandvars(path_str)
    return Path(path_str)


# Common validators
def positive_number(value: Any) -> bool:
    """Validate that value is a positive number."""
    try:
        return float(value) > 0
    except (ValueError, TypeError):
        return False


def port_validator(value: Any) -> bool:
    """Validate port number (1-65535)."""
    try:
        port = int(value)
        return 1 <= port <= 65535
    except (ValueError, TypeError):
        return False


def url_validator(value: Any) -> bool:
    """Basic URL validation."""
    if not isinstance(value, str):
        return False
    return value.startswith(('http://', 'https://', 'ws://', 'wss://'))


def file_exists_validator(value: Any) -> bool:
    """Validate that file exists."""
    try:
        return Path(value).is_file()
    except (TypeError, OSError):
        return False


def directory_exists_validator(value: Any) -> bool:
    """Validate that directory exists."""
    try:
        return Path(value).is_dir()
    except (TypeError, OSError):
        return False


# Predefined environment managers for common use cases
def create_development_manager() -> EnvironmentManager:
    """Create an environment manager configured for development."""
    manager = EnvironmentManager()
    
    # Load .env file if it exists
    env_files = ['.env', '.env.local', '.env.development']
    for env_file in env_files:
        if Path(env_file).exists():
            manager.load_env_file(env_file)
    
    return manager


def create_production_manager() -> EnvironmentManager:
    """Create an environment manager configured for production."""
    manager = EnvironmentManager()
    
    # In production, we typically don't load .env files
    # and rely on properly set environment variables
    
    return manager


def create_testing_manager() -> EnvironmentManager:
    """Create an environment manager configured for testing."""
    manager = EnvironmentManager()
    
    # Load test-specific environment files
    env_files = ['.env.test', '.env.testing']
    for env_file in env_files:
        if Path(env_file).exists():
            manager.load_env_file(env_file)
    
    return manager


def auto_detect_environment_manager() -> EnvironmentManager:
    """Auto-detect and create appropriate environment manager."""
    env = os.environ.get('SMRTI_ENVIRONMENT', 
                         os.environ.get('ENV', 'development')).lower()
    
    if env == 'production':
        return create_production_manager()
    elif env in ['test', 'testing']:
        return create_testing_manager()
    else:
        return create_development_manager()