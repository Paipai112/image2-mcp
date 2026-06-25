"""FastMCP server for image2 text-to-image generation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.server import Context
from pydantic import ValidationError as PydanticValidationError

from .client import Image2Client
from .config import get_api_key, get_base_url, get_model, get_output_dir
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

logger = logging.getLogger(__name__)


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


def _handle_background_result(task: asyncio.Task) -> None:
    """Callback for background tasks — logs result or error."""
    try:
        if task.cancelled():
            logger.warning("Background image task was cancelled")
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("Background image generation failed: %s", exc)
        else:
            _, file_path, _usage = task.result()
            logger.info("Background image generated: %s", file_path)
    except asyncio.CancelledError:
        logger.warning("Background image task was cancelled")
    except Exception:
        logger.warning("Background task result retrieval failed", exc_info=True)


async def _generate_and_save(
    client: Image2Client,
    validated: GenerateImageInput,
    ctx: Context | None = None,
) -> tuple[bytes, Path, dict[str, Any]]:
    """Core logic: call API, save image, return (bytes, path, usage). Shared by sync/async tools."""
    # --- API call ---
    image_bytes, usage = await client.generate(
        prompt=validated.prompt,
        size=validated.size,
        quality=validated.quality,
    )

    # --- Save ---
    out_dir = get_output_dir(validated.output_dir)
    out_filename = _generate_filename(validated.filename)
    file_path = out_dir / out_filename
    file_path.write_bytes(image_bytes)

    if ctx:
        try:
            await ctx.info(f"Image saved to {file_path}")
        except (ValueError, RuntimeError):
            pass

    return image_bytes, file_path, usage


def _build_response(image_bytes: bytes, file_path: Path, usage: dict[str, Any]) -> list[Any]:
    """Build the standard MCP tool response."""
    mcp_image = Image(data=image_bytes, format="png")
    output = ImageOutput(path=str(file_path), usage=usage)
    return [
        mcp_image.to_image_content().model_dump(exclude_none=True),
        {"type": "text", "text": output.model_dump_json()},
    ]


def create_server() -> FastMCP:
    """Create and configure the image2 MCP server."""
    api_key = get_api_key()
    base_url = get_base_url()
    model = get_model()

    client = Image2Client(base_url=base_url, api_key=api_key, model=model)
    mcp = FastMCP("Image2")

    @mcp.tool(
        description=(
            "Generate an image from a text prompt using the company image2 model. "
            "Use async_mode=true (default) for fire-and-forget — returns immediately, "
            "image saves to disk in the background. "
            "Use async_mode=false to wait for the image and see it in the response. "
            f"Size: {_format_size_help()}"
        ),
    )
    async def generate_image(
        prompt: str,
        size: str,
        quality: str = "auto",
        output_dir: str | None = None,
        filename: str | None = None,
        async_mode: bool = True,
        ctx: Context | None = None,
    ) -> list[Any]:
        """Generate an image via the image2 API.

        Args:
            prompt: Text description of the image to generate (max ~32000 chars).
            size: Output size. {_format_size_help()}
            quality: Image quality: low, medium, high, or auto (default).
            output_dir: Custom output directory. Uses configured default if omitted.
            filename: Custom filename without extension. Auto-generated if omitted.
            async_mode: If True (default), fire-and-forget — returns immediately
                while the image is generated and saved in the background.
                If False, waits for the image to complete and returns it.

        Returns:
            In sync mode: the generated image as PNG plus metadata.
            In async mode: a text confirmation that generation has started.
        """
        # --- Validation phase ---
        try:
            validated = GenerateImageInput(
                prompt=prompt,
                size=size,
                quality=quality,
                output_dir=output_dir,
                filename=filename,
            )
        except PydanticValidationError as e:
            size_help = _format_size_help()
            raise ValidationError(
                f"Invalid parameters: {e}\nSupported sizes: {size_help}"
            )

        if ctx:
            try:
                await ctx.info(f"Generating image: {validated.prompt[:100]}...")
            except (ValueError, RuntimeError):
                pass

        if async_mode:
            # Fire-and-forget: schedule the coroutine and let it run independently.
            # Use ensure_future (not create_task) and yield to the event loop
            # so the task gets a chance to start before we return.
            task = asyncio.ensure_future(_generate_and_save(client, validated, ctx))
            task.add_done_callback(_handle_background_result)
            # Keep a reference to prevent GC
            if not hasattr(mcp, "_bg_tasks"):
                mcp._bg_tasks = set()
            mcp._bg_tasks.add(task)
            task.add_done_callback(mcp._bg_tasks.discard)
            # Yield so the coroutine starts executing
            await asyncio.sleep(0)
            return [
                {
                    "type": "text",
                    "text": (
                        "🔥 Image generation started in background!\n"
                        f"Prompt: {validated.prompt[:80]}...\n"
                        f"Size: {validated.size} | Quality: {validated.quality}\n"
                        "The image will be saved to the output directory shortly. "
                        "You can continue chatting while it generates.\n"
                        "Run `list_images` to check what's been generated."
                    ),
                }
            ]

        # --- Sync mode: wait for result ---
        try:
            image_bytes, file_path, usage = await _generate_and_save(
                client, validated, ctx
            )
        except Image2Exception:
            raise
        except Exception as exc:
            if ctx:
                try:
                    await ctx.error(f"Unexpected error: {exc}")
                except (ValueError, RuntimeError):
                    pass
            raise

        return _build_response(image_bytes, file_path, usage)

    @mcp.tool(
        description=(
            "List recently generated images in the output directory. "
            "Useful after async/fire-and-forget generation to see what's been created."
        ),
    )
    async def list_images(
        output_dir: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List generated images in the output directory.

        Args:
            output_dir: Directory to scan. Uses configured default if omitted.
            limit: Maximum number of images to return (default 20, max 100).

        Returns:
            List of image file info sorted by newest first.
        """
        limit = max(1, min(limit, 100))
        out_dir = get_output_dir(output_dir)

        png_files = sorted(
            out_dir.glob("*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        result = []
        for fp in png_files:
            stat = fp.stat()
            result.append({
                "filename": fp.name,
                "path": str(fp),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })

        return [
            {
                "type": "text",
                "text": (
                    f"📁 {out_dir}\n"
                    f"Showing {len(result)} of {len(list(out_dir.glob('*.png')))} total\n\n"
                    + (
                        "\n".join(
                            f"{i+1}. {r['filename']} ({r['size_bytes']:,} bytes, {r['modified']})"
                            for i, r in enumerate(result)
                        )
                        if result
                        else "(no images found)"
                    )
                ),
            }
        ]

    return mcp
