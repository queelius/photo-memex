"""Anthropic vision provider for image analysis.

Uses Anthropic's Claude models with vision capabilities for
image understanding and analysis.

Requires: ANTHROPIC_API_KEY environment variable or api_key in config.
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from ptk.ai.ollama import AnalysisResult


class AnthropicProvider:
    """Anthropic vision provider using Claude models.

    Implements the VisionProvider interface.
    """

    # Default prompts (similar to other providers)
    DESCRIBE_PROMPT = """Describe this image in 1-2 sentences. Be concise and factual.
Focus on: the main subject, setting, and any notable details."""

    FULL_ANALYSIS_PROMPT = """Analyze this image and provide:
1. DESCRIPTION: A brief 1-2 sentence description
2. TAGS: 5-10 relevant tags (comma-separated)
3. SCENE: The type of scene (e.g., indoor, outdoor, portrait, landscape, event)
4. OBJECTS: Main objects visible (comma-separated)
5. PEOPLE: Number of people visible (just the number)

Format your response exactly like this:
DESCRIPTION: [your description]
TAGS: [tag1, tag2, tag3, ...]
SCENE: [scene type]
OBJECTS: [object1, object2, ...]
PEOPLE: [number]"""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the Anthropic provider.

        Args:
            config: Configuration dict with optional keys:
                - api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
                - model: Model name (default: claude-sonnet-4-20250514)
                - max_tokens: Max response tokens (default: 1024)
                - timeout: Request timeout in seconds (default: 120)
        """
        config = config or {}
        self.api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self.model = config.get("model", "claude-sonnet-4-20250514")
        self.max_tokens = config.get("max_tokens", 1024)
        self.timeout = config.get("timeout", 120)
        self.base_url = "https://api.anthropic.com/v1"

    @property
    def name(self) -> str:
        """Provider name."""
        return "anthropic"

    def is_available(self) -> bool:
        """Check if Anthropic API is available (has API key)."""
        return bool(self.api_key)

    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _get_media_type(self, image_path: Path) -> str:
        """Get MIME type for image."""
        suffix = image_path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(suffix, "image/jpeg")

    def _generate(self, prompt: str, image_path: Path) -> str:
        """Send a vision request to Anthropic.

        Args:
            prompt: The prompt/question about the image
            image_path: Path to the image file

        Returns:
            The model's response text

        Raises:
            ConnectionError: If Anthropic API is not reachable
            RuntimeError: If the request fails
        """
        if not self.api_key:
            raise RuntimeError("Anthropic API key not configured")

        image_data = self._encode_image(image_path)
        media_type = self._get_media_type(image_path)

        # Anthropic's vision API format
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }

        try:
            req = Request(
                f"{self.base_url}/messages",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )

            with urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode())
                # Anthropic returns content as a list of blocks
                content = result.get("content", [])
                for block in content:
                    if block.get("type") == "text":
                        return block.get("text", "")
                return ""

        except URLError as e:
            raise ConnectionError(f"Cannot connect to Anthropic API: {e}")
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise RuntimeError(f"Anthropic request failed: {e.code} - {error_body}")
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Invalid response from Anthropic: {e}")

    def describe(self, image_path: Path) -> str:
        """Generate a description for an image.

        Args:
            image_path: Path to the image

        Returns:
            A text description of the image
        """
        return self._generate(self.DESCRIBE_PROMPT, image_path).strip()

    def analyze(self, image_path: Path) -> AnalysisResult:
        """Perform full analysis of an image.

        Args:
            image_path: Path to the image

        Returns:
            AnalysisResult with description, tags, objects, scene, and people count
        """
        response = self._generate(self.FULL_ANALYSIS_PROMPT, image_path)

        result = AnalysisResult(raw_response=response)

        # Parse structured response
        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()

            if line.upper().startswith("DESCRIPTION:"):
                result.description = line.split(":", 1)[1].strip()

            elif line.upper().startswith("TAGS:"):
                tags_str = line.split(":", 1)[1].strip()
                result.tags = [
                    t.strip().lower()
                    for t in tags_str.split(",")
                    if t.strip() and len(t.strip()) < 30
                ]

            elif line.upper().startswith("SCENE:"):
                result.scene = line.split(":", 1)[1].strip().lower()

            elif line.upper().startswith("OBJECTS:"):
                objects_str = line.split(":", 1)[1].strip()
                result.objects = [
                    o.strip().lower() for o in objects_str.split(",") if o.strip()
                ]

            elif line.upper().startswith("PEOPLE:"):
                people_str = line.split(":", 1)[1].strip()
                match = re.search(r"\d+", people_str)
                if match:
                    result.people_count = int(match.group())

        return result

    def annotate(
        self,
        image_path: Path,
        profile: "AnnotationProfile",
        fields: list[str] | None = None,
    ) -> "AnnotationResult":
        """Annotate an image using a structured profile.

        Args:
            image_path: Path to the image
            profile: The annotation profile to use
            fields: Optional list of specific field names to extract

        Returns:
            AnnotationResult with structured annotations
        """
        from datetime import datetime, timezone
        from ptk.ai.annotations import AnnotationResult

        result = AnnotationResult(
            profile_name=profile.name,
            model=self.model,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Determine which fields to process
        fields_to_process = profile.fields
        if fields:
            fields_to_process = [f for f in profile.fields if f.name in fields]

        for field in fields_to_process:
            try:
                prompt = field.build_prompt()
                response = self._generate(prompt, image_path)
                result.raw_responses[field.name] = response

                parsed = field.parse_response(response)
                result.annotations[field.name] = parsed

            except Exception as e:
                result.errors[field.name] = str(e)
                if field.default is not None:
                    result.annotations[field.name] = field.default

        return result

    def ask(self, image_path: Path, question: str) -> str:
        """Ask a question about an image.

        Args:
            image_path: Path to the image
            question: The question to ask

        Returns:
            The model's response to the question
        """
        return self._generate(question, image_path).strip()
