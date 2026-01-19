"""Vision provider abstraction for AI image analysis.

This module provides an abstract base class for vision AI providers
and a factory function to get the appropriate provider based on
configuration.

Supported providers:
- ollama: Local Ollama server with vision models (llava, etc.)
- openai: OpenAI API with gpt-4o vision
- anthropic: Anthropic API with Claude vision

Example:
    >>> from ptk.ai.provider import get_provider
    >>> provider = get_provider("ollama")
    >>> if provider.is_available():
    ...     description = provider.describe(Path("photo.jpg"))
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ptk.ai.annotations import AnnotationProfile, AnnotationResult
    from ptk.ai.ollama import AnalysisResult


class VisionProvider(ABC):
    """Abstract base class for vision AI providers.

    All vision providers must implement this interface to be usable
    with ptk's AI features.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'ollama', 'openai', 'anthropic')."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured.

        Returns:
            True if the provider can be used, False otherwise.
        """

    @abstractmethod
    def describe(self, image_path: Path) -> str:
        """Generate a natural language description of an image.

        Args:
            image_path: Path to the image file.

        Returns:
            A text description of the image content.

        Raises:
            ConnectionError: If the provider is not reachable.
            RuntimeError: If the request fails.
            FileNotFoundError: If the image file doesn't exist.
        """

    @abstractmethod
    def analyze(self, image_path: Path) -> "AnalysisResult":
        """Perform full structured analysis of an image.

        Returns description, tags, objects, scene type, and people count.

        Args:
            image_path: Path to the image file.

        Returns:
            AnalysisResult with structured analysis data.

        Raises:
            ConnectionError: If the provider is not reachable.
            RuntimeError: If the request fails.
        """

    @abstractmethod
    def annotate(
        self,
        image_path: Path,
        profile: "AnnotationProfile",
        fields: list[str] | None = None,
    ) -> "AnnotationResult":
        """Annotate an image using a structured profile.

        Args:
            image_path: Path to the image file.
            profile: The annotation profile defining fields to extract.
            fields: Optional list of specific field names to extract.
                   If None, extracts all fields in the profile.

        Returns:
            AnnotationResult with structured annotations.

        Raises:
            ConnectionError: If the provider is not reachable.
            RuntimeError: If the request fails.
        """

    @abstractmethod
    def ask(self, image_path: Path, question: str) -> str:
        """Ask a question about an image.

        Args:
            image_path: Path to the image file.
            question: The question to ask about the image.

        Returns:
            The provider's response to the question.

        Raises:
            ConnectionError: If the provider is not reachable.
            RuntimeError: If the request fails.
        """


class ProviderNotFoundError(Exception):
    """Raised when a requested provider is not found."""


class ProviderNotAvailableError(Exception):
    """Raised when a provider is found but not available (e.g., no API key)."""


def get_provider(
    name: str | None = None,
    config: dict[str, Any] | None = None,
) -> VisionProvider:
    """Factory function to get a vision provider instance.

    Args:
        name: Provider name ('ollama', 'openai', 'anthropic').
              If None, uses 'ollama' as default.
        config: Provider-specific configuration dict. Keys depend on provider:
            - ollama: host, port, model
            - openai: api_key, model
            - anthropic: api_key, model

    Returns:
        A VisionProvider instance.

    Raises:
        ProviderNotFoundError: If the provider name is not recognized.

    Example:
        >>> provider = get_provider("openai", {"api_key": "sk-..."})
        >>> if provider.is_available():
        ...     desc = provider.describe(Path("photo.jpg"))
    """
    name = name or "ollama"
    config = config or {}

    if name == "ollama":
        from ptk.ai.ollama import OllamaVisionService

        return OllamaVisionService(
            host=config.get("host", "localhost"),
            port=config.get("port", 11434),
            model=config.get("model", "llava"),
        )
    elif name == "openai":
        from ptk.ai.openai_provider import OpenAIProvider

        return OpenAIProvider(config)
    elif name == "anthropic":
        from ptk.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(config)
    else:
        raise ProviderNotFoundError(f"Unknown provider: {name}")


def list_providers() -> list[str]:
    """List all available provider names.

    Returns:
        List of provider names that can be used with get_provider().
    """
    return ["ollama", "openai", "anthropic"]
