import json
import os
from typing import Dict, Any, Optional

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".mbook_settings.json")

class ConfigManager:
    """Manages application configuration and settings persistence."""

    def __init__(self, settings_path: str = SETTINGS_PATH):
        self.settings_path = settings_path
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load settings from disk."""
        if not os.path.exists(self.settings_path):
            self._config = {}
            return

        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._config = {}

    def save_config(self) -> None:
        """Save current settings to disk."""
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
        except OSError as e:
            print(f"Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value and save immediately."""
        self._config[key] = value
        self.save_config()

    def update(self, data: Dict[str, Any]) -> None:
        """Update multiple configuration values and save."""
        self._config.update(data)
        self.save_config()

    def get_default_engine(self) -> str:
        """Get the default TTS engine (maya1 or chatterbox)."""
        return self._config.get("default_engine", "maya1")

    def set_default_engine(self, engine: str) -> None:
        """Set the default TTS engine."""
        if engine not in ["maya1", "chatterbox"]:
            raise ValueError(f"Invalid engine: {engine}")
        self.set("default_engine", engine)

    def get_hf_token(self) -> Optional[str]:
        """Get the HuggingFace token."""
        return self._config.get("hf_token")

    def set_hf_token(self, token: str) -> None:
        """Set the HuggingFace token."""
        self.set("hf_token", token)
