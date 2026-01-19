"""Tests for library configuration (ptk.yaml)."""

import pytest
from pathlib import Path
import tempfile
import os

from ptk.core.config import (
    load_library_config,
    get_provider_config,
    LibraryConfig,
    AIProviderConfig,
    OllamaProviderConfig,
    OpenAIProviderConfig,
    AnthropicProviderConfig,
    _expand_env_vars,
)


class TestDefaultConfig:
    """Tests for default configuration values."""

    def test_default_library_config(self):
        """Default config should have expected values."""
        config = LibraryConfig()
        assert config.ai.provider == "ollama"
        assert config.ai.default_profile == "quick"

    def test_default_ollama_config(self):
        """Default Ollama config should have expected values."""
        config = OllamaProviderConfig()
        assert config.host == "localhost"
        assert config.port == 11434
        assert config.model == "llava"
        assert config.timeout == 120

    def test_default_openai_config(self):
        """Default OpenAI config should have expected values."""
        config = OpenAIProviderConfig()
        assert config.api_key is None
        assert config.model == "gpt-4o"
        assert config.max_tokens == 1024

    def test_default_anthropic_config(self):
        """Default Anthropic config should have expected values."""
        config = AnthropicProviderConfig()
        assert config.api_key is None
        assert "claude" in config.model.lower()
        assert config.max_tokens == 1024


class TestLoadLibraryConfig:
    """Tests for load_library_config function."""

    def test_load_nonexistent_file_returns_defaults(self):
        """Loading from nonexistent file should return defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_library_config(Path(tmpdir))
            assert config.ai.provider == "ollama"

    def test_load_empty_file_returns_defaults(self):
        """Loading from empty file should return defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "ptk.yaml"
            config_path.write_text("")
            config = load_library_config(Path(tmpdir))
            assert config.ai.provider == "ollama"

    def test_load_valid_config(self):
        """Loading valid config file should parse values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "ptk.yaml"
            config_path.write_text("""
ai:
  provider: openai
  default_profile: family
  ollama:
    host: custom-host
    port: 9999
    model: llava:latest
  openai:
    model: gpt-4o-mini
    max_tokens: 2048
""")
            config = load_library_config(Path(tmpdir))
            assert config.ai.provider == "openai"
            assert config.ai.default_profile == "family"
            assert config.ai.ollama.host == "custom-host"
            assert config.ai.ollama.port == 9999
            assert config.ai.openai.model == "gpt-4o-mini"
            assert config.ai.openai.max_tokens == 2048


class TestExpandEnvVars:
    """Tests for environment variable expansion."""

    def test_expand_env_var(self):
        """Should expand ${VAR_NAME} syntax."""
        os.environ["TEST_VAR_XYZ"] = "test-value"
        try:
            result = _expand_env_vars("${TEST_VAR_XYZ}")
            assert result == "test-value"
        finally:
            del os.environ["TEST_VAR_XYZ"]

    def test_expand_missing_env_var(self):
        """Should return empty string for missing env var."""
        result = _expand_env_vars("${NONEXISTENT_VAR_XYZ}")
        assert result == ""

    def test_non_env_var_unchanged(self):
        """Non-env-var strings should be unchanged."""
        result = _expand_env_vars("regular-string")
        assert result == "regular-string"

    def test_non_string_unchanged(self):
        """Non-string values should be unchanged."""
        assert _expand_env_vars(123) == 123
        assert _expand_env_vars(True) is True
        assert _expand_env_vars(None) is None


class TestGetProviderConfig:
    """Tests for get_provider_config function."""

    def test_ollama_config(self):
        """Should return Ollama config when provider is ollama."""
        config = LibraryConfig()
        config.ai.provider = "ollama"
        config.ai.ollama.host = "my-host"
        config.ai.ollama.port = 5555

        provider_config = get_provider_config(config)
        assert provider_config["host"] == "my-host"
        assert provider_config["port"] == 5555
        assert provider_config["model"] == "llava"

    def test_openai_config(self):
        """Should return OpenAI config when provider is openai."""
        config = LibraryConfig()
        config.ai.provider = "openai"
        config.ai.openai.api_key = "test-key"
        config.ai.openai.model = "gpt-4o-mini"

        provider_config = get_provider_config(config)
        assert provider_config["api_key"] == "test-key"
        assert provider_config["model"] == "gpt-4o-mini"

    def test_anthropic_config(self):
        """Should return Anthropic config when provider is anthropic."""
        config = LibraryConfig()
        config.ai.provider = "anthropic"
        config.ai.anthropic.api_key = "test-key"

        provider_config = get_provider_config(config)
        assert provider_config["api_key"] == "test-key"
        assert "claude" in provider_config["model"].lower()

    def test_unknown_provider_returns_empty(self):
        """Unknown provider should return empty dict."""
        config = LibraryConfig()
        config.ai.provider = "unknown"

        provider_config = get_provider_config(config)
        assert provider_config == {}
