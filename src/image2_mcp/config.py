"""Configuration from environment variables."""

import os
import tempfile
from pathlib import Path

from .errors import AuthError

_DEFAULT_BASE_URL = "http://localhost:11636/api/v1/images/generations"
_DEFAULT_MODEL = "openai/gpt-image-2"


def get_api_key() -> str:
    """Read MAGENE_API_KEY from environment. Raises AuthError if not set."""
    key = os.environ.get("MAGENE_API_KEY", "").strip()
    if not key:
        raise AuthError("MAGENE_API_KEY environment variable is not set")
    return key


def get_base_url() -> str:
    """Read MAGENE_API_BASE_URL or return default."""
    return os.environ.get("MAGENE_API_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def get_model() -> str:
    """Read IMAGE2_MODEL or return default."""
    return os.environ.get("IMAGE2_MODEL", _DEFAULT_MODEL).strip()


def get_output_dir(path: str | None = None) -> Path:
    """Get the output directory for generated images.

    Precedence:
    1. Explicit path argument (from user/AI request)
    2. IMAGE2_OUTPUT_DIR env var
    3. IMAGE2_PROJECT_DIR env var → <project>/output/ (auto-set by MCP launcher)
    4. System temp dir / image2-output
    """
    if path:
        output_dir = Path(path)
    else:
        env_path = os.environ.get("IMAGE2_OUTPUT_DIR")
        if env_path:
            output_dir = Path(env_path)
        else:
            project_dir = os.environ.get("IMAGE2_PROJECT_DIR")
            if project_dir:
                output_dir = Path(project_dir) / "output"
            else:
                output_dir = Path(tempfile.gettempdir()) / "image2-output"

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
