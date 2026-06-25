"""Integration tests for the full generate_image tool flow."""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from image2_mcp.server import create_server, _generate_filename


@pytest.mark.asyncio
async def test_create_server_success():
    server = create_server()
    assert server is not None
    assert server.name == "Image2"


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
    """Preset size 'auto' passes validation and async mode returns immediately."""
    server = create_server()
    result, meta = await server.call_tool("generate_image", {
        "prompt": "a cat",
        "size": "auto",
        "quality": "low",
    })
    # Async mode — should return text confirmation without error
    text = result[0].text
    assert "started" in text.lower()


@pytest.mark.asyncio
async def test_generate_image_sync_mode_fails_on_network():
    """Sync mode with unreachable API raises network error."""
    server = create_server()
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("generate_image", {
            "prompt": "a cat",
            "size": "auto",
            "quality": "low",
            "async_mode": False,
        })
    msg = str(exc_info.value).lower()
    assert any(kw in msg for kw in ("network", "connection", "nodename", "resolve", "refused", "api error"))


@pytest.mark.asyncio
async def test_list_images_returns_files():
    """list_images should return the generated images."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a couple of dummy PNG files
        (Path(tmpdir) / "test_a.png").write_bytes(b"\x89PNG\x00\x00")
        (Path(tmpdir) / "test_b.png").write_bytes(b"\x89PNG\x00\x00")

        server = create_server()
        result, meta = await server.call_tool("list_images", {
            "output_dir": tmpdir,
            "limit": 5,
        })
        text = result[0].text
        assert "test_a.png" in text
        assert "test_b.png" in text
