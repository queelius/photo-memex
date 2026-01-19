"""Tests for the AI provider abstraction."""

import pytest
from pathlib import Path

from ptk.ai.provider import (
    VisionProvider,
    get_provider,
    list_providers,
    ProviderNotFoundError,
)
from ptk.ai.ollama import OllamaVisionService
from ptk.ai.openai_provider import OpenAIProvider
from ptk.ai.anthropic_provider import AnthropicProvider


class TestListProviders:
    """Tests for list_providers function."""

    def test_returns_all_providers(self):
        """Should return all available provider names."""
        providers = list_providers()
        assert "ollama" in providers
        assert "openai" in providers
        assert "anthropic" in providers

    def test_returns_list(self):
        """Should return a list."""
        providers = list_providers()
        assert isinstance(providers, list)


class TestGetProvider:
    """Tests for get_provider factory function."""

    def test_get_ollama_default(self):
        """Default provider should be ollama."""
        provider = get_provider()
        assert isinstance(provider, OllamaVisionService)
        assert provider.name == "ollama"

    def test_get_ollama_explicit(self):
        """Explicit ollama provider."""
        provider = get_provider("ollama")
        assert isinstance(provider, OllamaVisionService)
        assert provider.name == "ollama"

    def test_get_ollama_with_config(self):
        """Ollama provider with custom config."""
        provider = get_provider("ollama", {
            "host": "custom-host",
            "port": 12345,
            "model": "llava:latest",
        })
        assert provider.host == "custom-host"
        assert provider.port == 12345
        assert provider.model == "llava:latest"

    def test_get_openai(self):
        """OpenAI provider."""
        provider = get_provider("openai")
        assert isinstance(provider, OpenAIProvider)
        assert provider.name == "openai"

    def test_get_openai_with_config(self):
        """OpenAI provider with custom config."""
        provider = get_provider("openai", {
            "api_key": "test-key",
            "model": "gpt-4o-mini",
        })
        assert provider.api_key == "test-key"
        assert provider.model == "gpt-4o-mini"

    def test_get_anthropic(self):
        """Anthropic provider."""
        provider = get_provider("anthropic")
        assert isinstance(provider, AnthropicProvider)
        assert provider.name == "anthropic"

    def test_get_anthropic_with_config(self):
        """Anthropic provider with custom config."""
        provider = get_provider("anthropic", {
            "api_key": "test-key",
            "model": "claude-3-haiku-20240307",
        })
        assert provider.api_key == "test-key"
        assert provider.model == "claude-3-haiku-20240307"

    def test_unknown_provider_raises(self):
        """Unknown provider should raise ProviderNotFoundError."""
        with pytest.raises(ProviderNotFoundError):
            get_provider("unknown")


class TestOllamaProvider:
    """Tests for OllamaVisionService provider interface."""

    def test_name_property(self):
        """Should have correct name property."""
        provider = OllamaVisionService()
        assert provider.name == "ollama"

    def test_is_available_when_unavailable(self):
        """Should return False when server not running."""
        # Use a port that's unlikely to have Ollama
        provider = OllamaVisionService(port=59999)
        assert provider.is_available() is False

    def test_default_model(self):
        """Should have default model llava."""
        provider = OllamaVisionService()
        assert provider.model == "llava"


class TestOpenAIProvider:
    """Tests for OpenAIProvider interface."""

    def test_name_property(self):
        """Should have correct name property."""
        provider = OpenAIProvider()
        assert provider.name == "openai"

    def test_is_available_without_key(self):
        """Should return False without API key."""
        provider = OpenAIProvider({})
        assert provider.is_available() is False

    def test_is_available_with_key(self):
        """Should return True with API key."""
        provider = OpenAIProvider({"api_key": "test-key"})
        assert provider.is_available() is True

    def test_default_model(self):
        """Should have default model gpt-4o."""
        provider = OpenAIProvider()
        assert provider.model == "gpt-4o"


class TestAnthropicProvider:
    """Tests for AnthropicProvider interface."""

    def test_name_property(self):
        """Should have correct name property."""
        provider = AnthropicProvider()
        assert provider.name == "anthropic"

    def test_is_available_without_key(self):
        """Should return False without API key."""
        provider = AnthropicProvider({})
        assert provider.is_available() is False

    def test_is_available_with_key(self):
        """Should return True with API key."""
        provider = AnthropicProvider({"api_key": "test-key"})
        assert provider.is_available() is True

    def test_default_model(self):
        """Should have default model claude-sonnet."""
        provider = AnthropicProvider()
        assert "claude" in provider.model.lower()
