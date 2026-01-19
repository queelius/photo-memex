"""AI features for ptk (vision analysis, faces, embeddings)."""

from ptk.ai.ollama import OllamaVisionService, AnalysisResult
from ptk.ai.annotations import (
    AnnotationField,
    AnnotationProfile,
    AnnotationResult,
    FieldType,
    BUILTIN_PROFILES,
    get_profile,
    list_profiles,
    load_profile_from_yaml,
)
from ptk.ai.provider import (
    VisionProvider,
    get_provider,
    list_providers,
    ProviderNotFoundError,
    ProviderNotAvailableError,
)

__all__ = [
    # Providers
    "VisionProvider",
    "get_provider",
    "list_providers",
    "ProviderNotFoundError",
    "ProviderNotAvailableError",
    # Ollama
    "OllamaVisionService",
    "AnalysisResult",
    # Annotations
    "AnnotationField",
    "AnnotationProfile",
    "AnnotationResult",
    "FieldType",
    "BUILTIN_PROFILES",
    "get_profile",
    "list_profiles",
    "load_profile_from_yaml",
]
