"""Pydantic models for request/response validation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# Predefined valid sizes per API docs
VALID_SIZES: frozenset[str] = frozenset({
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "2048x2048",
    "2048x1152",
    "3840x2160",
    "2160x3840",
    "auto",
})

_SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$")

# Custom size constraints per API docs
MIN_TOTAL_PIXELS = 655_360
MAX_TOTAL_PIXELS = 8_294_400
MAX_DIMENSION = 3840
DIMENSION_MULTIPLE = 16
MAX_ASPECT_RATIO = 3.0

VALID_QUALITIES: frozenset[str] = frozenset({"low", "medium", "high", "auto"})


def _validate_custom_size(width: int, height: int) -> str | None:
    """Validate a custom (non-preset) size against API rules.

    Returns an error message string if invalid, None if valid.
    """
    if width % DIMENSION_MULTIPLE != 0 or height % DIMENSION_MULTIPLE != 0:
        return f"Width and height must be a multiple of {DIMENSION_MULTIPLE}"
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        return f"Dimension must be max {MAX_DIMENSION}px"
    long_side = max(width, height)
    short_side = min(width, height)
    if short_side == 0 or long_side / short_side > MAX_ASPECT_RATIO:
        return f"Aspect ratio must be ≤ 3:1 (long/short)"
    total = width * height
    if total < MIN_TOTAL_PIXELS:
        return f"Total pixels must be ≥ {MIN_TOTAL_PIXELS:,}"
    if total > MAX_TOTAL_PIXELS:
        return f"Total pixels must be ≤ {MAX_TOTAL_PIXELS:,}"
    return None


class GenerateImageInput(BaseModel):
    """Input parameters for the generate_image tool."""

    prompt: str = Field(min_length=1, description="Text prompt for image generation (max ~32000 chars)")
    size: str = Field(description="Output size, e.g. '1024x1024' or 'auto'")
    quality: str = Field(default="auto", description="Quality: low, medium, high, or auto")
    output_dir: str | None = Field(default=None, description="Custom output directory path")
    filename: str | None = Field(default=None, description="Custom filename without extension")

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("prompt must not be empty or whitespace-only")
        return stripped

    @field_validator("quality")
    @classmethod
    def quality_valid(cls, v: str) -> str:
        if v not in VALID_QUALITIES:
            raise ValueError(f"quality must be one of: {', '.join(sorted(VALID_QUALITIES))}")
        return v

    @field_validator("filename")
    @classmethod
    def filename_safe(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                return None
            # replace path separators for safety
            return stripped.replace("/", "_").replace("\\", "_")
        return None

    @model_validator(mode="after")
    def validate_size(self) -> "GenerateImageInput":
        size = self.size

        # Preset sizes skip custom validation
        if size in VALID_SIZES:
            return self

        match = _SIZE_PATTERN.match(size)
        if not match:
            raise ValueError(
                f"Invalid size format '{size}'. "
                f"Use WxH (e.g. '1024x1024') or one of: {', '.join(sorted(VALID_SIZES))}"
            )

        width, height = int(match.group(1)), int(match.group(2))
        error = _validate_custom_size(width, height)
        if error:
            raise ValueError(error)
        return self


class ImageOutput(BaseModel):
    """Output from generate_image tool — sent to AI alongside the raw image."""

    path: str = Field(description="Absolute path to the saved image file")
    usage: dict[str, Any] = Field(default_factory=dict, description="Token usage from API response")

    @property
    def url(self) -> str:
        return f"file://{self.path}"
