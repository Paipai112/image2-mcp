import os
import tempfile
from pathlib import Path

import pytest
from image2_mcp.config import get_api_key, get_base_url, get_output_dir
from image2_mcp.errors import AuthError


ORIGINAL_ENV = dict(os.environ)


def setup_function():
    """Clear env vars that affect config before each test."""
    for key in ("MAGENE_API_KEY", "MAGENE_API_BASE_URL", "IMAGE2_OUTPUT_DIR"):
        os.environ.pop(key, None)


def teardown_module():
    """Restore config env vars to their original values."""
    for key in ("MAGENE_API_KEY", "MAGENE_API_BASE_URL", "IMAGE2_OUTPUT_DIR"):
        if key in ORIGINAL_ENV:
            os.environ[key] = ORIGINAL_ENV[key]
        else:
            os.environ.pop(key, None)


def test_get_api_key_from_env():
    os.environ["MAGENE_API_KEY"] = "sk-test-123"
    assert get_api_key() == "sk-test-123"


def test_get_api_key_missing_raises_auth_error():
    with pytest.raises(AuthError, match="MAGENE_API_KEY"):
        get_api_key()


def test_get_base_url_default():
    assert get_base_url() == "http://tops.magene.cn:11636/api/v1/images/generations"


def test_get_base_url_custom():
    os.environ["MAGENE_API_BASE_URL"] = "https://custom.company.com/v2/images"
    assert get_base_url() == "https://custom.company.com/v2/images"


def test_get_output_dir_default_creates_dir():
    output_dir = get_output_dir()
    assert output_dir.exists()
    assert output_dir.is_dir()
    # Should end with image2-output relative to temp dir
    assert output_dir.name == "image2-output"


def test_get_output_dir_custom():
    with tempfile.TemporaryDirectory() as tmpdir:
        custom = Path(tmpdir) / "my-images"
        os.environ["IMAGE2_OUTPUT_DIR"] = str(custom)
        result = get_output_dir()
        assert result == custom
        assert result.exists()


def test_get_output_dir_returns_same_path_on_second_call():
    """Directory creation is idempotent."""
    first = get_output_dir()
    second = get_output_dir()
    assert first == second
