"""
Persistent Settings Manager

Description: Manages persistent settings for download_tools nodes across reloads
Author: Eric Hiss (GitHub: EricRollei)
Contact: eric@historic.camera, eric@rollei.us
License: Dual License (Non-Commercial and Commercial Use)
Copyright (c) 2025 Eric Hiss. All rights reserved.
"""

import os
import json
from pathlib import Path
from typing import Optional, Any, Dict


class PersistentSettings:
    """
    Manages persistent settings for download_tools nodes.
    Settings are stored in a JSON file and persist across node/workflow reloads.
    """
    
    _instance = None
    _settings: Dict[str, Any] = {}
    _settings_file: Path = None
    
    def __new__(cls):
        """Singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the settings manager."""
        if self._initialized:
            return
        
        # Determine settings file path
        self._settings_file = Path(__file__).parent.parent / "configs" / "node_settings.json"
        self._settings = self._load_settings()
        self._initialized = True
        print(f"PersistentSettings initialized from: {self._settings_file}")
    
    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from the JSON file."""
        default_settings = {
            "web_scraper": {
                "auth_config_path": ""
            },
            "gallery_dl": {
                "config_path": "",
                "cookie_file": ""
            },
            "yt_dlp": {
                "config_path": ""
            }
        }
        
        try:
            if self._settings_file.exists():
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    for key in default_settings:
                        if key not in loaded:
                            loaded[key] = default_settings[key]
                        elif isinstance(default_settings[key], dict):
                            for subkey in default_settings[key]:
                                if subkey not in loaded[key]:
                                    loaded[key][subkey] = default_settings[key][subkey]
                    return loaded
            else:
                # Create the file with defaults
                self._settings_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._settings_file, 'w', encoding='utf-8') as f:
                    json.dump(default_settings, f, indent=4)
                return default_settings
        except Exception as e:
            print(f"Error loading persistent settings: {e}")
            return default_settings
    
    def _save_settings(self) -> bool:
        """Save current settings to the JSON file."""
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._settings_file, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving persistent settings: {e}")
            return False
    
    def get(self, node_type: str, key: str, default: Any = "") -> Any:
        """
        Get a setting value for a specific node type.
        
        Args:
            node_type: The type of node ('web_scraper', 'gallery_dl', 'yt_dlp')
            key: The setting key to retrieve
            default: Default value if setting not found
            
        Returns:
            The setting value or default
        """
        try:
            if node_type in self._settings and key in self._settings[node_type]:
                value = self._settings[node_type][key]
                return value if value else default
            return default
        except Exception:
            return default
    
    def set(self, node_type: str, key: str, value: Any) -> bool:
        """
        Set a setting value for a specific node type.
        
        Args:
            node_type: The type of node ('web_scraper', 'gallery_dl', 'yt_dlp')
            key: The setting key to set
            value: The value to store
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if node_type not in self._settings:
                self._settings[node_type] = {}
            
            # Only update if value is non-empty (don't overwrite with empty values)
            if value and str(value).strip():
                self._settings[node_type][key] = str(value).strip()
                return self._save_settings()
            return True
        except Exception as e:
            print(f"Error setting persistent setting: {e}")
            return False
    
    def get_all(self, node_type: str) -> Dict[str, Any]:
        """Get all settings for a specific node type."""
        return self._settings.get(node_type, {})
    
    def reload(self) -> None:
        """Reload settings from file (useful if file was edited externally)."""
        self._settings = self._load_settings()


# Global instance for easy access
_settings_manager: Optional[PersistentSettings] = None


def get_settings_manager() -> PersistentSettings:
    """Get the global settings manager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = PersistentSettings()
    return _settings_manager


def get_persistent_setting(node_type: str, key: str, default: Any = "") -> Any:
    """Convenience function to get a persistent setting."""
    return get_settings_manager().get(node_type, key, default)


def set_persistent_setting(node_type: str, key: str, value: Any) -> bool:
    """Convenience function to set a persistent setting."""
    return get_settings_manager().set(node_type, key, value)
