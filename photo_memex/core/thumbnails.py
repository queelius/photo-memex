"""Thumbnail generation for photos."""

from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from photo_memex.core.constants import (
    DEFAULT_THUMBNAIL_SIZE,
    DEFAULT_THUMBNAIL_FORMAT,
    DEFAULT_THUMBNAIL_QUALITY,
)
from photo_memex.core.exceptions import ThumbnailError


def generate_thumbnail(
    image_path: Path,
    size: int = DEFAULT_THUMBNAIL_SIZE,
    format: str = DEFAULT_THUMBNAIL_FORMAT,
    quality: int = DEFAULT_THUMBNAIL_QUALITY,
) -> Tuple[bytes, str]:
    """Generate a thumbnail from an image file.

    Args:
        image_path: Path to the source image
        size: Maximum dimension (width or height)
        format: Output format (webp, jpeg, png)
        quality: Compression quality (1-100)

    Returns:
        Tuple of (thumbnail bytes, mime type)

    Raises:
        ThumbnailError: If thumbnail generation fails
    """
    try:
        with Image.open(image_path) as img:
            # Handle EXIF orientation
            img = _apply_exif_orientation(img)

            # Convert to RGB if necessary (for RGBA, palette, etc.)
            if img.mode in ("RGBA", "P", "LA"):
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Create thumbnail (maintains aspect ratio)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)

            # Save to bytes
            buffer = BytesIO()
            save_format = format.upper()
            if save_format == "WEBP":
                img.save(buffer, format="WEBP", quality=quality)
                mime_type = "image/webp"
            elif save_format in ("JPEG", "JPG"):
                img.save(buffer, format="JPEG", quality=quality)
                mime_type = "image/jpeg"
            else:
                img.save(buffer, format="PNG")
                mime_type = "image/png"

            return buffer.getvalue(), mime_type

    except Exception as e:
        raise ThumbnailError(f"Failed to generate thumbnail for {image_path}: {e}") from e


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation to an image.

    Args:
        img: PIL Image to orient

    Returns:
        Correctly oriented image
    """
    try:
        exif = img.getexif()
        if exif is None:
            return img

        orientation = exif.get(274)  # 274 is the EXIF orientation tag
        if orientation is None:
            return img

        # Apply transformations based on orientation
        if orientation == 2:
            return img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif orientation == 3:
            return img.rotate(180)
        elif orientation == 4:
            return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif orientation == 5:
            return img.rotate(-90, expand=True).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif orientation == 6:
            return img.rotate(-90, expand=True)
        elif orientation == 7:
            return img.rotate(90, expand=True).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif orientation == 8:
            return img.rotate(90, expand=True)

    except Exception:
        pass  # If we can't read orientation, just return the original

    return img


def get_image_dimensions(image_path: Path) -> Optional[Tuple[int, int]]:
    """Get the dimensions of an image without loading the full file.

    Args:
        image_path: Path to the image

    Returns:
        Tuple of (width, height) or None if unable to determine
    """
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return None
