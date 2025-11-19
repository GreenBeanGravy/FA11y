"""
Centralized Configuration Manager for FA11y

Provides unified interface for all configuration and persistent data storage.
Supports dynamic registration - scripts register their own configs.

Usage:
    from lib.config.config_manager import config_manager

    # Register your config (first time or every startup - idempotent)
    config_manager.register('my_module', 'config/my_data.json',
                           format='json', default={})

    # Get data
    data = config_manager.get('my_module')
    token = config_manager.get('my_module', 'access_token')

    # Set data
    config_manager.set('my_module', 'access_token', 'abc123')
    config_manager.set('my_module', data={'key': 'value'})
"""

import os
import json
import configparser
import threading
import time
import logging
from typing import Any, Dict, Optional, Callable
from io import StringIO

logger = logging.getLogger(__name__)


class ConfigRegistry:
    """Holds metadata for a registered config"""
    def __init__(self, config_id: str, filename: str, format: str,
                 default: Any, cache_timeout: float, custom_loader: Callable = None,
                 custom_saver: Callable = None):
        self.config_id = config_id
        self.filename = filename
        self.format = format
        self.default = default
        self.cache_timeout = cache_timeout
        self.custom_loader = custom_loader
        self.custom_saver = custom_saver

        # Runtime state
        self.lock = threading.RLock()
        self.cache = None
        self.cache_time = 0


class ConfigManager:
    """
    Centralized configuration manager with dynamic registration.

    Thread-safe, cached, supports multiple formats (JSON, INI, custom).
    """

    def __init__(self):
        self._registries: Dict[str, ConfigRegistry] = {}
        self._global_lock = threading.RLock()

        # Ensure config directory exists
        os.makedirs('config', exist_ok=True)

    def register(self, config_id: str, filename: str,
                 format: str = 'json',
                 default: Any = None,
                 cache_timeout: float = 1.0,
                 custom_loader: Callable = None,
                 custom_saver: Callable = None) -> None:
        """
        Register a config file. Idempotent - safe to call multiple times.

        Args:
            config_id: Unique identifier for this config
            filename: Path to config file (relative to FA11y root)
            format: 'json', 'ini', or 'custom'
            default: Default value if file doesn't exist
            cache_timeout: How long to cache in memory (seconds)
            custom_loader: Custom function to load file (for format='custom')
            custom_saver: Custom function to save file (for format='custom')
        """
        with self._global_lock:
            if config_id in self._registries:
                # Already registered, just return
                return

            registry = ConfigRegistry(
                config_id=config_id,
                filename=filename,
                format=format,
                default=default,
                cache_timeout=cache_timeout,
                custom_loader=custom_loader,
                custom_saver=custom_saver
            )

            self._registries[config_id] = registry
            logger.debug(f"Registered config: {config_id} -> {filename} ({format})")

    def get(self, config_id: str, key: str = None, default: Any = None,
            use_cache: bool = True) -> Any:
        """
        Get config value(s).

        Args:
            config_id: Which config to read from
            key: Specific key to get (None = get entire config)
            default: Default value if key doesn't exist
            use_cache: Whether to use cached value

        Returns:
            Config value, entire config, or default

        Examples:
            # Get entire config
            auth = config_manager.get('epic_auth')

            # Get specific key
            token = config_manager.get('epic_auth', 'access_token')

            # Get with default
            volume = config_manager.get('app_config', 'StormVolume', default=0.5)
        """
        registry = self._get_registry(config_id)

        with registry.lock:
            # Check cache
            if use_cache and registry.cache is not None:
                current_time = time.time()
                if current_time - registry.cache_time < registry.cache_timeout:
                    config_data = registry.cache
                else:
                    config_data = self._load_config(registry)
            else:
                config_data = self._load_config(registry)

            # Return value
            if key is None:
                # Return entire config
                return config_data
            else:
                # Return specific key
                if isinstance(config_data, dict):
                    return config_data.get(key, default)
                elif isinstance(config_data, configparser.ConfigParser):
                    # For INI files, search all sections for the key
                    for section in config_data.sections():
                        if config_data.has_option(section, key):
                            return config_data.get(section, key)
                    return default
                else:
                    return default

    def set(self, config_id: str, key: str = None, value: Any = None,
            data: Any = None) -> bool:
        """
        Set config value(s). Auto-saves to disk.

        Args:
            config_id: Which config to write to
            key: Specific key to set (None if setting entire config)
            value: Value to set for key
            data: Entire config to set (alternative to key/value)

        Returns:
            True if saved successfully, False otherwise

        Examples:
            # Set specific key
            config_manager.set('epic_auth', 'access_token', 'abc123')

            # Set entire config
            config_manager.set('epic_auth', data={'access_token': 'abc123'})
        """
        registry = self._get_registry(config_id)

        with registry.lock:
            # Load current config
            current_config = self._load_config(registry)

            # Update config
            if data is not None:
                # Replace entire config
                new_config = data
            elif key is not None:
                # Update specific key
                if isinstance(current_config, dict):
                    current_config[key] = value
                    new_config = current_config
                elif isinstance(current_config, configparser.ConfigParser):
                    # For INI, find the section containing this key
                    found = False
                    for section in current_config.sections():
                        if current_config.has_option(section, key):
                            current_config.set(section, key, str(value))
                            found = True
                            break
                    if not found:
                        # Key doesn't exist, can't set it (INI requires section)
                        logger.warning(f"Key '{key}' not found in INI config '{config_id}'")
                        return False
                    new_config = current_config
                else:
                    logger.error(f"Cannot set key on non-dict/non-INI config '{config_id}'")
                    return False
            else:
                logger.error(f"Must provide either 'key'+'value' or 'data' to set()")
                return False

            # Save to disk
            success = self._save_config(registry, new_config)

            if success:
                # Update cache
                registry.cache = new_config
                registry.cache_time = time.time()

            return success

    def exists(self, config_id: str, key: str = None) -> bool:
        """
        Check if config or key exists.

        Args:
            config_id: Which config to check
            key: Specific key to check (None = check if config file exists)

        Returns:
            True if exists, False otherwise
        """
        try:
            registry = self._get_registry(config_id)
        except KeyError:
            return False

        if key is None:
            # Check if file exists
            return os.path.exists(registry.filename)
        else:
            # Check if key exists
            config_data = self.get(config_id)
            if isinstance(config_data, dict):
                return key in config_data
            elif isinstance(config_data, configparser.ConfigParser):
                for section in config_data.sections():
                    if config_data.has_option(section, key):
                        return True
                return False
            else:
                return False

    def reload(self, config_id: str) -> None:
        """Force reload config from disk (clears cache)."""
        registry = self._get_registry(config_id)
        with registry.lock:
            registry.cache = None
            registry.cache_time = 0

    def save(self, config_id: str) -> bool:
        """Force save cached config to disk."""
        registry = self._get_registry(config_id)
        with registry.lock:
            if registry.cache is not None:
                return self._save_config(registry, registry.cache)
            return True

    def _get_registry(self, config_id: str) -> ConfigRegistry:
        """Get registry for config_id or raise KeyError"""
        with self._global_lock:
            if config_id not in self._registries:
                raise KeyError(f"Config '{config_id}' not registered. Call register() first.")
            return self._registries[config_id]

    def _load_config(self, registry: ConfigRegistry) -> Any:
        """Load config from disk"""
        # Ensure directory exists
        directory = os.path.dirname(registry.filename)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # Load based on format
        if registry.format == 'json':
            return self._load_json(registry)
        elif registry.format == 'ini':
            return self._load_ini(registry)
        elif registry.format == 'custom':
            if registry.custom_loader:
                return registry.custom_loader(registry.filename)
            else:
                logger.error(f"Custom format requires custom_loader for '{registry.config_id}'")
                return registry.default
        else:
            logger.error(f"Unknown format '{registry.format}' for '{registry.config_id}'")
            return registry.default

    def _load_json(self, registry: ConfigRegistry) -> Dict:
        """Load JSON config file"""
        if not os.path.exists(registry.filename):
            # File doesn't exist, return default
            default = registry.default if registry.default is not None else {}
            # Create file with default
            self._save_json(registry, default)
            return default

        try:
            with open(registry.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Update cache
            registry.cache = data
            registry.cache_time = time.time()
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Error loading JSON config '{registry.config_id}': {e}")
            default = registry.default if registry.default is not None else {}
            return default

    def _load_ini(self, registry: ConfigRegistry) -> configparser.ConfigParser:
        """Load INI config file (special handling for config.txt)"""
        # This delegates to utilities.py for backward compatibility
        # utilities.py will use config_manager, but we provide the low-level loader
        config = self._create_config_parser()

        if not os.path.exists(registry.filename):
            # File doesn't exist, return default or empty
            if registry.default is not None:
                if isinstance(registry.default, str):
                    config.read_string(registry.default)
            return config

        try:
            with open(registry.filename, 'r', encoding='utf-8') as f:
                content = f.read()
            config.read_string(content)
            # Update cache
            registry.cache = config
            registry.cache_time = time.time()
            return config
        except (configparser.Error, OSError) as e:
            logger.error(f"Error loading INI config '{registry.config_id}': {e}")
            return config

    def _save_config(self, registry: ConfigRegistry, data: Any) -> bool:
        """Save config to disk"""
        # Ensure directory exists
        directory = os.path.dirname(registry.filename)
        if directory:
            os.makedirs(directory, exist_ok=True)

        # Save based on format
        if registry.format == 'json':
            return self._save_json(registry, data)
        elif registry.format == 'ini':
            return self._save_ini(registry, data)
        elif registry.format == 'custom':
            if registry.custom_saver:
                return registry.custom_saver(registry.filename, data)
            else:
                logger.error(f"Custom format requires custom_saver for '{registry.config_id}'")
                return False
        else:
            logger.error(f"Unknown format '{registry.format}' for '{registry.config_id}'")
            return False

    def _save_json(self, registry: ConfigRegistry, data: Dict) -> bool:
        """Save JSON config file"""
        try:
            with open(registry.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except OSError as e:
            logger.error(f"Error saving JSON config '{registry.config_id}': {e}")
            return False

    def _save_ini(self, registry: ConfigRegistry, config: configparser.ConfigParser) -> bool:
        """Save INI config file"""
        try:
            config_string = StringIO()
            config.write(config_string)
            content = config_string.getvalue()
            config_string.close()

            with open(registry.filename, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except (OSError, Exception) as e:
            logger.error(f"Error saving INI config '{registry.config_id}': {e}")
            return False

    def _create_config_parser(self) -> configparser.ConfigParser:
        """Create ConfigParser with case-preserved keys"""
        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case
        return config


# Global singleton instance
config_manager = ConfigManager()
