"""Configuration management for ptk using XDG paths and library config.

Supports:
- Global config from XDG_CONFIG_HOME (~/.config/ptk/)
- Library config from ptk.yaml in the library directory
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import os

from ptk.core.constants import (
    APP_NAME,
    CONFIG_FILENAME,
    DEFAULT_DATABASE_NAME,
    DEFAULT_THUMBNAIL_SIZE,
    DEFAULT_THUMBNAIL_FORMAT,
    DEFAULT_THUMBNAIL_QUALITY,
)

# Try to import yaml, fall back to basic parsing if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _get_xdg_config_home() -> Path:
    """Get XDG_CONFIG_HOME or default."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _get_xdg_data_home() -> Path:
    """Get XDG_DATA_HOME or default."""
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _get_xdg_cache_home() -> Path:
    """Get XDG_CACHE_HOME or default."""
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


@dataclass
class AIConfig:
    """AI feature configuration."""

    faces_enabled: bool = True
    embeddings_enabled: bool = True
    caption_enabled: bool = False  # Opt-in (requires Ollama or API)

    face_model: str = "hog"  # "hog" (faster) or "cnn" (more accurate)
    embedding_model: str = "clip-ViT-B-32"
    caption_model: str = "llava"

    ollama_url: str = "http://localhost:11434"
    openai_api_key: Optional[str] = None

    face_clustering_threshold: float = 0.6


@dataclass
class PtkConfig:
    """Main configuration for ptk."""

    # Library location (where database and thumbnails are stored)
    library_path: Optional[Path] = None

    # Database settings
    database_name: str = DEFAULT_DATABASE_NAME

    # Thumbnail settings
    thumbnail_size: int = DEFAULT_THUMBNAIL_SIZE
    thumbnail_format: str = DEFAULT_THUMBNAIL_FORMAT
    thumbnail_quality: int = DEFAULT_THUMBNAIL_QUALITY

    # Import settings
    skip_hidden: bool = True
    recursive: bool = True

    # AI settings
    ai: AIConfig = field(default_factory=AIConfig)

    @property
    def database_path(self) -> Path:
        """Get the full path to the database file."""
        if self.library_path is None:
            raise ValueError("library_path not set")
        return self.library_path / self.database_name

    @property
    def thumbnails_path(self) -> Path:
        """Get the path to thumbnails directory."""
        if self.library_path is None:
            raise ValueError("library_path not set")
        return self.library_path / "thumbnails"

    @classmethod
    def config_dir(cls) -> Path:
        """Get the config directory path."""
        return _get_xdg_config_home() / APP_NAME

    @classmethod
    def config_file(cls) -> Path:
        """Get the config file path."""
        return cls.config_dir() / CONFIG_FILENAME

    @classmethod
    def default_library_path(cls) -> Path:
        """Get the default library path."""
        return _get_xdg_data_home() / APP_NAME

    @classmethod
    def cache_dir(cls) -> Path:
        """Get the cache directory path."""
        return _get_xdg_cache_home() / APP_NAME


# Global config instance
_config: Optional[PtkConfig] = None


def get_config() -> PtkConfig:
    """Get the global config instance, creating if needed."""
    global _config
    if _config is None:
        _config = PtkConfig()
    return _config


def set_config(config: PtkConfig) -> None:
    """Set the global config instance."""
    global _config
    _config = config


def find_library(start_path: Optional[Path] = None) -> Optional[Path]:
    """Find a ptk library by looking for ptk.db in current or parent directories.

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to library directory if found, None otherwise
    """
    start = start_path or Path.cwd()
    current = start.resolve()

    while current != current.parent:
        db_path = current / DEFAULT_DATABASE_NAME
        if db_path.exists():
            return current
        current = current.parent

    # Check home last
    db_path = current / DEFAULT_DATABASE_NAME
    if db_path.exists():
        return current

    return None


# =============================================================================
# Library Configuration (ptk.yaml)
# =============================================================================


@dataclass
class OllamaProviderConfig:
    """Ollama provider configuration."""

    host: str = "localhost"
    port: int = 11434
    model: str = "llava"
    timeout: int = 120


@dataclass
class OpenAIProviderConfig:
    """OpenAI provider configuration."""

    api_key: Optional[str] = None
    model: str = "gpt-4o"
    max_tokens: int = 1024
    timeout: int = 120


@dataclass
class AnthropicProviderConfig:
    """Anthropic provider configuration."""

    api_key: Optional[str] = None
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    timeout: int = 120


@dataclass
class AIProviderConfig:
    """AI provider configuration for ptk.yaml."""

    # Provider to use: 'ollama' | 'openai' | 'anthropic'
    provider: str = "ollama"
    ollama: OllamaProviderConfig = field(default_factory=OllamaProviderConfig)
    openai: OpenAIProviderConfig = field(default_factory=OpenAIProviderConfig)
    anthropic: AnthropicProviderConfig = field(default_factory=AnthropicProviderConfig)
    default_profile: str = "quick"


@dataclass
class LibraryConfig:
    """Library-level configuration from ptk.yaml."""

    ai: AIProviderConfig = field(default_factory=AIProviderConfig)


def _expand_env_vars(value: Any) -> Any:
    """Expand environment variables in string values.

    Supports ${VAR_NAME} syntax.
    """
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.environ.get(var_name, "")
    return value


def _parse_library_config_dict(data: dict[str, Any]) -> LibraryConfig:
    """Parse configuration dictionary into LibraryConfig."""
    ai_data = data.get("ai", {})

    # Parse Ollama config
    ollama_data = ai_data.get("ollama", {})
    ollama_config = OllamaProviderConfig(
        host=ollama_data.get("host", "localhost"),
        port=int(ollama_data.get("port", 11434)),
        model=ollama_data.get("model", "llava"),
        timeout=int(ollama_data.get("timeout", 120)),
    )

    # Parse OpenAI config
    openai_data = ai_data.get("openai", {})
    openai_api_key = _expand_env_vars(openai_data.get("api_key", ""))
    openai_config = OpenAIProviderConfig(
        api_key=openai_api_key or None,
        model=openai_data.get("model", "gpt-4o"),
        max_tokens=int(openai_data.get("max_tokens", 1024)),
        timeout=int(openai_data.get("timeout", 120)),
    )

    # Parse Anthropic config
    anthropic_data = ai_data.get("anthropic", {})
    anthropic_api_key = _expand_env_vars(anthropic_data.get("api_key", ""))
    anthropic_config = AnthropicProviderConfig(
        api_key=anthropic_api_key or None,
        model=anthropic_data.get("model", "claude-sonnet-4-20250514"),
        max_tokens=int(anthropic_data.get("max_tokens", 1024)),
        timeout=int(anthropic_data.get("timeout", 120)),
    )

    # Parse AI config
    ai_config = AIProviderConfig(
        provider=ai_data.get("provider", "ollama"),
        ollama=ollama_config,
        openai=openai_config,
        anthropic=anthropic_config,
        default_profile=ai_data.get("default_profile", "quick"),
    )

    return LibraryConfig(ai=ai_config)


def load_library_config(library_path: Optional[Path] = None) -> LibraryConfig:
    """Load configuration from ptk.yaml in the library directory.

    Args:
        library_path: Path to the library directory. If None, uses current directory.

    Returns:
        LibraryConfig with settings from file, or defaults if file not found.
    """
    if library_path is None:
        library_path = Path.cwd()

    config_file = library_path / "ptk.yaml"

    if not config_file.exists():
        return LibraryConfig()

    if not HAS_YAML:
        # Fall back to returning defaults if yaml is not available
        return LibraryConfig()

    try:
        with open(config_file, "r") as f:
            data = yaml.safe_load(f) or {}
        return _parse_library_config_dict(data)
    except Exception:
        # On any error, return defaults
        return LibraryConfig()


def get_provider_config(config: LibraryConfig) -> dict[str, Any]:
    """Get configuration dict for the active provider.

    Args:
        config: The library configuration.

    Returns:
        Configuration dict suitable for passing to get_provider().
    """
    provider = config.ai.provider

    if provider == "ollama":
        return {
            "host": config.ai.ollama.host,
            "port": config.ai.ollama.port,
            "model": config.ai.ollama.model,
            "timeout": config.ai.ollama.timeout,
        }
    elif provider == "openai":
        return {
            "api_key": config.ai.openai.api_key,
            "model": config.ai.openai.model,
            "max_tokens": config.ai.openai.max_tokens,
            "timeout": config.ai.openai.timeout,
        }
    elif provider == "anthropic":
        return {
            "api_key": config.ai.anthropic.api_key,
            "model": config.ai.anthropic.model,
            "max_tokens": config.ai.anthropic.max_tokens,
            "timeout": config.ai.anthropic.timeout,
        }
    else:
        return {}
