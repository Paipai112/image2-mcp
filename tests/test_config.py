import os
import tempfile
from pathlib import Path

import pytest
from image2_mcp.config import get_api_key, get_base_url, get_model, get_output_dir
from image2_mcp.errors import AuthError


ORIGINAL_ENV = dict(os.environ)


def setup_function():
    """Clear env vars that affect config before each test."""
    for key in ("MAGENE_API_KEY", "MAGENE_API_BASE_URL", "IMAGE2_OUTPUT_DIR", "IMAGE2_MODEL", "IMAGE2_PROJECT_DIR", "CLAUDE_PROJECT_DIR"):
        os.environ.pop(key, None)


def teardown_module():
    """Restore config env vars to their original values."""
    for key in ("MAGENE_API_KEY", "MAGENE_API_BASE_URL", "IMAGE2_OUTPUT_DIR", "IMAGE2_MODEL", "IMAGE2_PROJECT_DIR", "CLAUDE_PROJECT_DIR"):
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
    # Falls back to CWD/output when no env vars are set
    assert output_dir.name == "output"


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


def test_get_output_dir_from_project_dir_env():
    """IMAGE2_PROJECT_DIR env var → <project>/output/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["IMAGE2_PROJECT_DIR"] = tmpdir
        result = get_output_dir()
        assert result == Path(tmpdir) / "output"
        assert result.exists()


def test_get_output_dir_explicit_wins_over_project_dir():
    """Explicit path takes precedence over IMAGE2_PROJECT_DIR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        custom = Path(tmpdir) / "explicit-dir"
        os.environ["IMAGE2_PROJECT_DIR"] = "/some/project"
        result = get_output_dir(str(custom))
        assert result == custom
        assert result.exists()


def test_get_output_dir_env_wins_over_project_dir():
    """IMAGE2_OUTPUT_DIR takes precedence over IMAGE2_PROJECT_DIR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_custom = Path(tmpdir) / "env-dir"
        os.environ["IMAGE2_OUTPUT_DIR"] = str(env_custom)
        os.environ["IMAGE2_PROJECT_DIR"] = "/some/project"
        result = get_output_dir()
        assert result == env_custom
        assert result.exists()


def test_get_model_default():
    assert get_model() == "openai/gpt-image-2"


def test_get_model_custom():
    os.environ["IMAGE2_MODEL"] = "custom/model-name"
    assert get_model() == "custom/model-name"
