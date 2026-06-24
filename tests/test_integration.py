"""Integration tests for the full generate_image tool flow."""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from image2_mcp.server import create_server, _generate_filename


@pytest.mark.asyncio
async def test_create_server_success():
    server = create_server()
    assert server is not None
    assert server.name == "Image2"


def test_generate_filename_custom():
    name = _generate_filename("my-drawing")
    assert name == "my-drawing.png"


def test_generate_filename_auto():
    name = _generate_filename(None)
    assert name.startswith("image2-")
    assert name.endswith(".png")
    # Should have a timestamp + uuid segment
    parts = name.replace(".png", "").split("-")
    assert len(parts) >= 4  # image2-YYYYmmdd-HHMMSS-xxxxxxxx


def test_generate_filename_path_separators_removed():
    """_generate_filename itself does not sanitize; Pydantic validator does.
    Test that the validator removes path separators when present."""
    from image2_mcp.schemas import GenerateImageInput

    validated = GenerateImageInput(
        prompt="a cat",
        size="1024x1024",
        filename="sub/dir/file",
    )
    # The validator replaces / and \ with _
    assert validated.filename == "sub_dir_file"
    # When passed to _generate_filename, no path separators remain
    name = _generate_filename(validated.filename)
    assert "/" not in name
    assert "\\" not in name


@pytest.mark.asyncio
async def test_generate_image_empty_prompt_returns_error():
    """Calling tool with empty prompt raises ToolError due to validation."""
    server = create_server()
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("generate_image", {
            "prompt": "",
            "size": "1024x1024",
        })
    assert "prompt" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_generate_image_bad_size_returns_error():
    """Calling tool with invalid size raises ToolError due to validation."""
    server = create_server()
    with pytest.raises(ToolError):
        await server.call_tool("generate_image", {
            "prompt": "a cat",
            "size": "bad-size",
        })


@pytest.mark.asyncio
async def test_generate_image_preset_size_passes_validation():
    """Preset size 'auto' passes validation, fails at network layer."""
    server = create_server()
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("generate_image", {
            "prompt": "a cat",
            "size": "auto",
            "quality": "low",
        })
    # Should fail at network, not validation
    msg = str(exc_info.value).lower()
    assert any(kw in msg for kw in ("network", "connection", "nodename", "resolve", "refused"))
