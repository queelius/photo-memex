"""Ollama vision service for image analysis."""

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

if TYPE_CHECKING:
    from ptk.ai.provider import VisionProvider


@dataclass
class AnalysisResult:
    """Result of AI image analysis."""

    description: str = ""
    tags: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    scene: str = ""
    people_count: int = 0
    raw_response: str = ""


class OllamaVisionService:
    """Service for analyzing images using Ollama vision models.

    Supports models like llava, llama3.2-vision, bakllava, etc.

    Implements the VisionProvider interface for use with ptk's
    multi-provider AI system.
    """

    @property
    def name(self) -> str:
        """Provider name."""
        return "ollama"

    # Default prompts for different analysis types
    DESCRIBE_PROMPT = """Describe this image in 1-2 sentences. Be concise and factual.
Focus on: the main subject, setting, and any notable details."""

    TAG_PROMPT = """List 5-10 tags for this image. Return ONLY a comma-separated list of single-word or two-word tags.
Examples: landscape, family, beach, sunset, portrait, indoor, outdoor, nature, urban, celebration
Tags:"""

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

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11434,
        model: str = "llava",
        timeout: int = 120,
    ):
        """Initialize the Ollama vision service.

        Args:
            host: Ollama server hostname
            port: Ollama server port
            model: Vision model to use (llava, llama3.2-vision, bakllava, etc.)
            timeout: Request timeout in seconds
        """
        self.host = host
        self.port = port
        self.model = model
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"

    def is_available(self) -> bool:
        """Check if Ollama server is available."""
        try:
            req = Request(f"{self.base_url}/api/tags", method="GET")
            with urlopen(req, timeout=5) as response:
                return response.status == 200
        except (URLError, HTTPError, TimeoutError):
            return False

    def list_models(self) -> list[str]:
        """List available models on the Ollama server."""
        try:
            req = Request(f"{self.base_url}/api/tags", method="GET")
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return [m["name"] for m in data.get("models", [])]
        except (URLError, HTTPError, json.JSONDecodeError):
            return []

    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _generate(self, prompt: str, image_path: Path) -> str:
        """Send a generation request to Ollama with an image.

        Args:
            prompt: The prompt/question about the image
            image_path: Path to the image file

        Returns:
            The model's response text

        Raises:
            ConnectionError: If Ollama server is not reachable
            RuntimeError: If the request fails
        """
        image_data = self._encode_image(image_path)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_data],
            "stream": False,
        }

        try:
            req = Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode())
                return result.get("response", "")

        except URLError as e:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}: {e}")
        except HTTPError as e:
            raise RuntimeError(f"Ollama request failed: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid response from Ollama: {e}")

    def describe(self, image_path: Path) -> str:
        """Generate a description for an image.

        Args:
            image_path: Path to the image

        Returns:
            A text description of the image
        """
        return self._generate(self.DESCRIBE_PROMPT, image_path).strip()

    def generate_tags(self, image_path: Path) -> list[str]:
        """Generate tags for an image.

        Args:
            image_path: Path to the image

        Returns:
            List of tags
        """
        response = self._generate(self.TAG_PROMPT, image_path)

        # Parse comma-separated tags
        tags = []
        for tag in response.split(","):
            tag = tag.strip().lower()
            # Clean up common formatting issues
            tag = re.sub(r"^[\d\.\-\*]+\s*", "", tag)  # Remove leading numbers/bullets
            tag = re.sub(r"[^\w\s\-]", "", tag)  # Remove special chars except hyphen
            tag = tag.strip()
            if tag and len(tag) > 1 and len(tag) < 30:
                tags.append(tag)

        return tags[:15]  # Limit to 15 tags

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
                    o.strip().lower()
                    for o in objects_str.split(",")
                    if o.strip()
                ]

            elif line.upper().startswith("PEOPLE:"):
                people_str = line.split(":", 1)[1].strip()
                # Extract number
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
                   (if None, extracts all fields in profile)

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

    def ask_batch(
        self,
        image_path: Path,
        questions: dict[str, str],
    ) -> dict[str, str]:
        """Ask multiple questions about an image.

        Args:
            image_path: Path to the image
            questions: Dict of {name: question} pairs

        Returns:
            Dict of {name: response} pairs
        """
        responses = {}
        for name, question in questions.items():
            try:
                responses[name] = self._generate(question, image_path)
            except Exception as e:
                responses[name] = f"Error: {e}"
        return responses
