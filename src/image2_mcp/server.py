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


def _log_done(task: asyncio.Task) -> None:
    """Fallback callback when MCP session is not available (e.g. tests)."""
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


async def _background_generate_and_notify(
    task: asyncio.Task,
    session: Any,
    request_id: str | None,
    validated: GenerateImageInput,
    mcp: FastMCP,
) -> None:
    """Await a background generation task, then push a log notification to the MCP client.

    This is the event-driven alternative to polling list_images:
    when the image finishes (or fails), the client gets a notification immediately.
    """
    try:
        image_bytes, file_path, usage = await task
        await session.send_log_message(
            level="notice",
            data={
                "event": "image_ready",
                "path": str(file_path),
                "filename": file_path.name,
                "prompt": validated.prompt[:100],
                "size": validated.size,
                "usage": usage,
            },
            logger="image2",
            related_request_id=request_id,
        )
        logger.info("Background image completed, notification sent: %s", file_path)
    except asyncio.CancelledError:
        logger.warning("Background image task was cancelled")
    except Exception as exc:
        logger.warning("Background image generation failed: %s", exc)
        try:
            await session.send_log_message(
                level="error",
                data={
                    "event": "image_failed",
                    "error": str(exc),
                    "prompt": validated.prompt[:100],
                },
                logger="image2",
                related_request_id=request_id,
            )
        except Exception:
            logger.warning("Failed to send error notification", exc_info=True)


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
    mcp = FastMCP(
        "Image2",
        instructions=(
            "## Image Generation Behavior\n"
            "1. Do NOT pass `output_dir` — images save to the project's `output/` folder automatically.\n"
            "2. Always use `async_mode=true` (the default) — generation will NOT block the conversation.\n"
            "3. After calling generate_image, do NOT poll list_images. "
            "You will receive a log notification when the image is ready (or failed). "
            "Just tell the user \"generating...\" and move on.\n"
            "4. When you receive the notification that an image is ready, tell the user.\n"
            "5. For multiple images, fire all generate_image calls in parallel — each sends its own notification.\n"
            "6. Always try to enrich and optimize the user's prompt for the best image results."
        ),
    )

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
            # Fire-and-forget: create the generation task, then schedule
            # a notifier that pushes a log message to the client when done.
            gen_task = asyncio.ensure_future(
                _generate_and_save(client, validated, ctx)
            )

            # Keep a reference to prevent GC
            if not hasattr(mcp, "_bg_tasks"):
                mcp._bg_tasks = set()
            mcp._bg_tasks.add(gen_task)
            gen_task.add_done_callback(mcp._bg_tasks.discard)

            # Schedule the event-driven notification
            try:
                session = ctx.session
                notify_coro = _background_generate_and_notify(
                    gen_task,
                    session,
                    ctx.request_id,
                    validated,
                    mcp,
                )
                notifier = asyncio.ensure_future(notify_coro)
                mcp._bg_tasks.add(notifier)
                notifier.add_done_callback(mcp._bg_tasks.discard)
            except (ValueError, RuntimeError):
                # ctx.session not available (e.g. in tests) — fallback to plain log
                _log_done(gen_task)

            # Yield so the coroutine starts executing
            await asyncio.sleep(0)
            return [
                {
                    "type": "text",
                    "text": (
                        "🔥 Image generation started in background!\n"
                        f"Prompt: {validated.prompt[:80]}...\n"
                        f"Size: {validated.size} | Quality: {validated.quality}\n"
                        "You'll be notified when it's ready — no need to poll."
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
