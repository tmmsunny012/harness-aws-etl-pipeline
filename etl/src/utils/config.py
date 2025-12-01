"""
Configuration Module
====================
Centralized configuration management.
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class Config:
    """
    Configuration manager that loads from YAML files and environment variables.

    Priority (highest to lowest):
    1. Environment variables
    2. Environment-specific config
    3. Base config file
    4. Default values
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config file. If None, auto-discovers.
        """
        self.environment = os.environ.get("ENVIRONMENT", "dev")
        self._config = {}

        # Load config file
        if config_path:
            self._load_config(config_path)
        else:
            self._auto_discover_config()

    def _auto_discover_config(self):
        """Auto-discover config file in common locations."""
        possible_paths = [
            Path("config/config.yaml"),
            Path("../config/config.yaml"),
            Path("/app/config/config.yaml"),
            Path.home() / ".etl" / "config.yaml"
        ]

        for path in possible_paths:
            if path.exists():
                self._load_config(str(path))
                return

    def _load_config(self, path: str):
        """Load configuration from YAML file."""
        try:
            with open(path, "r") as f:
                self._config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config from {path}: {e}")
            self._config = {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Supports dot notation for nested keys (e.g., "s3.raw_bucket_prefix")

        Args:
            key: Configuration key (dot notation supported)
            default: Default value if key not found

        Returns:
            Configuration value
        """
        # Check environment variable first (converted key)
        env_key = key.upper().replace(".", "_")
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return self._parse_env_value(env_value)

        # Navigate nested config
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        # Check for environment-specific override
        if isinstance(value, dict) and self.environment in value:
            return value[self.environment]

        return value

    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Integer
        try:
            return int(value)
        except ValueError:
            pass

        # Float
        try:
            return float(value)
        except ValueError:
            pass

        return value

    def get_all(self) -> dict:
        """Get all configuration as dictionary."""
        return self._config.copy()

    def get_environment_config(self) -> dict:
        """Get configuration for current environment."""
        envs = self._config.get("environments", {})
        return envs.get(self.environment, {})

    @property
    def is_local(self) -> bool:
        """Check if running in local environment."""
        return self.environment == "local"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "prod"
