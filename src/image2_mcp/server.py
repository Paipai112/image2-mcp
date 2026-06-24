"""FastMCP server for image2 text-to-image generation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from .client import Image2Client
from .config import get_api_key, get_base_url, get_output_dir
from .errors import Image2Exception, ValidationError
from .schemas import (
    DIMENSION_MULTIPLE,
    MAX_ASPECT_RATIO,
    MAX_DIMENSION,
    MAX_TOTAL_PIXELS,
    MIN_TOTAL_PIXELS,
    VALID_SIZES,
    GenerateImageInput,
    ImageOutput,
)


def _generate_filename(custom: str | None) -> str:
    """Generate a filename for the output image."""
    if custom:
        return f"{custom}.png"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    return f"image2-{timestamp}-{short_id}.png"


def _format_size_help() -> str:
    return (
        "Presets: " + ", ".join(sorted(VALID_SIZES))
        + f". Custom: WxH (max {MAX_DIMENSION}px per side, multiples of {DIMENSION_MULTIPLE}, "
        + f"ratio ≤ {MAX_ASPECT_RATIO}:1, pixels {MIN_TOTAL_PIXELS:,}–{MAX_TOTAL_PIXELS:,})"
    )


def create_server() -> FastMCP:
    """Create and configure the image2 MCP server."""
    api_key = get_api_key()
    base_url = get_base_url()

    client = Image2Client(base_url=base_url, api_key=api_key)
    mcp = FastMCP("Image2")

    @mcp.tool(
        description=(
            "Generate an image from a text prompt using the company image2 model. "
            f"Returns the generated image and saves it to disk. Size: {_format_size_help()}"
        ),
    )
    async def generate_image(
        prompt: str,
        size: str,
        quality: str = "auto",
        output_dir: str | None = None,
        filename: str | None = None,
    ) -> list[dict]:
        """Generate an image via the image2 API.

        Args:
            prompt: Text description of the image to generate (max ~32000 chars).
            size: Output size. {_format_size_help()}
            quality: Image quality: low, medium, high, or auto (default).
            output_dir: Custom output directory. Uses configured default if omitted.
            filename: Custom filename without extension. Auto-generated if omitted.

        Returns:
            The generated image as PNG plus metadata (file path, usage stats).
        """
        try:
            validated = GenerateImageInput(
                prompt=prompt,
                size=size,
                quality=quality,
                output_dir=output_dir,
                filename=filename,
            )
        except Exception as e:
            size_help = _format_size_help()
            raise ValidationError(
                f"Invalid parameters: {e}\nSupported sizes: {size_help}"
            )

        image_bytes, usage = await client.generate(
            prompt=validated.prompt,
            size=validated.size,
            quality=validated.quality,
        )

        # Determine output directory and save
        out_dir = get_output_dir(validated.output_dir)
        out_filename = _generate_filename(validated.filename)
        file_path = out_dir / out_filename
        file_path.write_bytes(image_bytes)

        # Build response
        mcp_image = Image(data=image_bytes, format="png")
        output = ImageOutput(
            path=str(file_path),
            usage=usage,
        )

        return [
            mcp_image.to_image_content(),
            {
                "type": "text",
                "text": output.model_dump_json(),
            },
        ]

    return mcp
