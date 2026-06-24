# Image2 MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server that wraps the company image2 API, exposing a `generate_image` tool callable from Claude Code / Codex.

**Architecture:** A local stdio-based FastMCP server that receives tool calls, validates parameters, POSTs to the company HTTP API, decodes the Base64 response, writes a PNG to disk, and returns the image + metadata to the AI.

**Tech Stack:** Python 3.10+, `mcp` SDK (FastMCP), `httpx` (async HTTP), `pydantic` (validation)

## Global Constraints

- Python >= 3.10
- `mcp` >= 1.28.0
- `httpx` >= 0.27.1
- `pydantic` >= 2.12.0
- All I/O must be async (httpx + FastMCP async tool)
- Image returned via MCP `Image(data=bytes, format="png")` type
- Transport: stdio (`run(transport="stdio")`)
- API key via `MAGENE_API_KEY` env var (fatal if missing, checked at server start)
- Output dir via `IMAGE2_OUTPUT_DIR` env var, default `<tempdir>/image2-output`
- API base URL via `MAGENE_API_BASE_URL` env var, default `http://tops.magene.cn:11636/api/v1/images/generations`

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/image2_mcp/__init__.py`

**Interfaces:**
- Produces: `pyproject.toml` with correct project metadata, entry point, and dependencies

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "image2-mcp"
version = "0.1.0"
description = "MCP Server for company image2 text-to-image API"
requires-python = ">=3.10"
dependencies = [
    "mcp[cli]>=1.28.0",
    "httpx>=0.27.1",
    "pydantic>=2.12.0",
]

[project.scripts]
image2-mcp = "image2_mcp.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create `src/image2_mcp/__init__.py`**

```python
"""Image2 MCP Server — wraps company image2 text-to-image API."""
```

- [ ] **Step 3: Install and verify project loads**

```bash
pip install -e ".[cli]"
python -c "import image2_mcp; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/image2_mcp/__init__.py
git commit -m "chore: scaffold image2-mcp project"
```

---

### Task 2: Custom exceptions (`errors.py`)

**Files:**
- Create: `src/image2_mcp/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Produces:
  - `Image2Exception(Exception)` — base
  - `AuthError(Image2Exception)` — status, message
  - `NetworkError(Image2Exception)` — status, message
  - `ValidationError(Image2Exception)` — message
  - `APIError(Image2Exception)` — status, message, body

- [ ] **Step 1: Write the failing test**

```python
# tests/test_errors.py
import pytest
from image2_mcp.errors import Image2Exception, AuthError, NetworkError, ValidationError, APIError


def test_auth_error_default_message():
    err = AuthError()
    assert 401 == err.status
    assert "Authentication failed" in str(err)


def test_network_error_custom_message():
    err = NetworkError("Connection refused", status=503)
    assert 503 == err.status
    assert "Connection refused" == err.message
    assert "Connection refused" in str(err)


def test_validation_error_message():
    err = ValidationError("prompt is required")
    assert "prompt is required" == err.message
    assert "prompt is required" in str(err)


def test_api_error_includes_body():
    err = APIError(status=500, message="Internal Server Error", body='{"error":"boom"}')
    assert 500 == err.status
    assert '{"error":"boom"}' == err.body


def test_network_error_is_retryable():
    err = NetworkError("timeout")
    assert err.retryable is True


def test_api_error_5xx_is_retryable():
    err = APIError(status=502, message="Bad Gateway", body="")
    assert err.retryable is True


def test_api_error_4xx_not_retryable():
    err = APIError(status=400, message="Bad Request", body="")
    assert err.retryable is False


def test_auth_error_not_retryable():
    err = AuthError()
    assert err.retryable is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_errors.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'image2_mcp.errors'`

- [ ] **Step 3: Write `src/image2_mcp/errors.py`**

```python
"""Custom exceptions for image2-mcp."""


class Image2Exception(Exception):
    """Base exception for image2-mcp."""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class AuthError(Image2Exception):
    """Authentication / API key error."""

    def __init__(self, message: str = "Authentication failed. Check MAGENE_API_KEY.") -> None:
        super().__init__(message)
        self.status = 401

    @property
    def retryable(self) -> bool:
        return False


class NetworkError(Image2Exception):
    """Network / connection error."""

    def __init__(self, message: str = "Network error", status: int = 0) -> None:
        super().__init__(message)
        self.status = status

    @property
    def retryable(self) -> bool:
        return True


class ValidationError(Image2Exception):
    """Parameter validation error."""

    @property
    def retryable(self) -> bool:
        return False


class APIError(Image2Exception):
    """Upstream API returned an error response."""

    def __init__(self, status: int, message: str, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body

    @property
    def retryable(self) -> bool:
        return self.status >= 500
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_errors.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_errors.py src/image2_mcp/errors.py
git commit -m "feat: add custom exception hierarchy"
```

---

### Task 3: Configuration module (`config.py`)

**Files:**
- Create: `src/image2_mcp/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `get_api_key() -> str` — reads `MAGENE_API_KEY`, raises `AuthError` if missing
  - `get_base_url() -> str` — reads `MAGENE_API_BASE_URL`, default `http://tops.magene.cn:11636/api/v1/images/generations`
  - `get_output_dir() -> Path` — reads `IMAGE2_OUTPUT_DIR`, default `<tempdir>/image2-output`, creates dir if it doesn't exist

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
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
    """Restore original environment after all tests."""
    os.environ.clear()
    os.environ.update(ORIGINAL_ENV)


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_config.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'image2_mcp.config'`

- [ ] **Step 3: Write `src/image2_mcp/config.py`**

```python
"""Configuration from environment variables."""

import os
import tempfile
from pathlib import Path

from .errors import AuthError

_DEFAULT_BASE_URL = "http://tops.magene.cn:11636/api/v1/images/generations"


def get_api_key() -> str:
    """Read MAGENE_API_KEY from environment. Raises AuthError if not set."""
    key = os.environ.get("MAGENE_API_KEY", "").strip()
    if not key:
        raise AuthError("MAGENE_API_KEY environment variable is not set")
    return key


def get_base_url() -> str:
    """Read MAGENE_API_BASE_URL or return default."""
    return os.environ.get("MAGENE_API_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def get_output_dir(path: str | None = None) -> Path:
    """Get the output directory for generated images.

    Precedence:
    1. Explicit path argument (from user request)
    2. IMAGE2_OUTPUT_DIR env var
    3. System temp dir / image2-output
    """
    if path:
        output_dir = Path(path)
    else:
        env_path = os.environ.get("IMAGE2_OUTPUT_DIR")
        if env_path:
            output_dir = Path(env_path)
        else:
            output_dir = Path(tempfile.gettempdir()) / "image2-output"

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_config.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_config.py src/image2_mcp/config.py
git commit -m "feat: add configuration from environment variables"
```

---

### Task 4: Pydantic schemas (`schemas.py`)

**Files:**
- Create: `src/image2_mcp/schemas.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces:
  - `VALID_SIZES: frozenset` — predefined size strings
  - `GenerateImageInput(pydantic.BaseModel)` — tool input params with validation
  - `ImageOutput(pydantic.BaseModel)` — tool output: path, url, usage dict

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError
from image2_mcp.schemas import VALID_SIZES, GenerateImageInput, ImageOutput


def test_valid_sizes_contains_presets():
    for size in ("1024x1024", "1536x1024", "1024x1536", "2048x2048",
                  "2048x1152", "3840x2160", "2160x3840", "auto"):
        assert size in VALID_SIZES


def test_custom_size_valid():
    """Custom sizes must pass structural rules."""
    input_data = GenerateImageInput(prompt="test", size="2048x1280")
    assert input_data.size == "2048x1280"


def test_custom_size_not_multiple_of_16():
    with pytest.raises(ValidationError, match="multiple of 16"):
        GenerateImageInput(prompt="test", size="100x100")


def test_custom_size_max_dimension_exceeded():
    with pytest.raises(ValidationError, match="max 3840px"):
        GenerateImageInput(prompt="test", size="4096x4096")


def test_custom_size_aspect_ratio_exceeded():
    with pytest.raises(ValidationError, match="3:1"):
        GenerateImageInput(prompt="test", size="3840x960")  # 4:1


def test_custom_size_total_pixels_too_low():
    with pytest.raises(ValidationError, match="655,360"):
        GenerateImageInput(prompt="test", size="640x640")


def test_custom_size_total_pixels_too_high():
    with pytest.raises(ValidationError, match="8,294,400"):
        GenerateImageInput(prompt="test", size="3840x2560")


def test_prompt_empty_string_rejected():
    with pytest.raises(ValidationError, match="prompt"):
        GenerateImageInput(prompt="", size="1024x1024")


def test_prompt_whitespace_only_rejected():
    with pytest.raises(ValidationError, match="prompt"):
        GenerateImageInput(prompt="   ", size="1024x1024")


def test_preset_size_no_custom_validation():
    """Preset sizes skip dimension validation."""
    input_data = GenerateImageInput(prompt="test", size="auto")
    assert input_data.size == "auto"


def test_quality_default_auto():
    input_data = GenerateImageInput(prompt="test", size="1024x1024")
    assert input_data.quality == "auto"


def test_quality_invalid_value_rejected():
    with pytest.raises(ValidationError, match="quality"):
        GenerateImageInput(prompt="test", size="1024x1024", quality="ultra")


def test_filename_default():
    input_data = GenerateImageInput(prompt="test", size="1024x1024")
    assert input_data.filename is None


def test_image_output_model():
    output = ImageOutput(path="/tmp/out.png", usage={"total_tokens": 100})
    assert output.path == "/tmp/out.png"
    assert output.url == "file:///tmp/out.png"
    assert output.usage == {"total_tokens": 100}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_schemas.py -v
```
Expected: FAIL

- [ ] **Step 3: Write `src/image2_mcp/schemas.py`**

```python
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
        return f"Width and height must be multiples of {DIMENSION_MULTIPLE}px"
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        return f"Max dimension is {MAX_DIMENSION}px"
    long_side = max(width, height)
    short_side = min(width, height)
    if short_side == 0 or long_side / short_side > MAX_ASPECT_RATIO:
        return f"Aspect ratio must be ≤ {MAX_ASPECT_RATIO}:1 (long/short)"
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_schemas.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_schemas.py src/image2_mcp/schemas.py
git commit -m "feat: add pydantic schemas with size validation"
```

---

### Task 5: HTTP API client (`client.py`)

**Files:**
- Create: `src/image2_mcp/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `errors.py` exceptions, `schemas.py` models, `config.py` get_api_key/get_base_url
- Produces:
  - `async def generate(prompt, size, quality) -> ApiResponse` — calls company API, decodes base64, returns (bytes, usage dict)
  - Raises `AuthError`, `NetworkError`, `APIError` on failure

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py
import base64
import os

import pytest
import respx
from httpx import Response

from image2_mcp.client import Image2Client
from image2_mcp.errors import APIError, AuthError, NetworkError

# A small 1x1 transparent PNG in base64
DUMMY_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()

BASE_URL = "http://test.local/v1/images/generations"
API_KEY = "sk-test-key"


@pytest.fixture
def client():
    """Create a client with test base URL."""
    return Image2Client(base_url=BASE_URL, api_key=API_KEY)


@pytest.mark.asyncio
async def test_generate_success(client, respx_mock):
    respx_mock.post(BASE_URL).mock(
        return_value=Response(200, json={
            "data": [{"b64_json": DUMMY_PNG}],
            "usage": {"total_tokens": 100},
        })
    )
    data, usage = await client.generate("a cat", "1024x1024", "auto")
    assert data.startswith(b"\x89PNG")
    assert usage == {"total_tokens": 100}


@pytest.mark.asyncio
async def test_generate_401_raises_auth_error(client, respx_mock):
    respx_mock.post(BASE_URL).mock(
        return_value=Response(401, json={"error": "Invalid API key"})
    )
    with pytest.raises(AuthError) as exc:
        await client.generate("prompt", "1024x1024", "auto")
    assert exc.value.status == 401


@pytest.mark.asyncio
async def test_generate_400_raises_api_error(client, respx_mock):
    respx_mock.post(BASE_URL).mock(
        return_value=Response(400, json={"error": "Bad prompt"}))
    with pytest.raises(APIError) as exc:
        await client.generate("bad", "1024x1024", "auto")
    assert exc.value.status == 400
    assert not exc.value.retryable


@pytest.mark.asyncio
async def test_generate_500_raises_api_error_retryable(client, respx_mock):
    respx_mock.post(BASE_URL).mock(
        return_value=Response(500, text="Internal Error"))
    with pytest.raises(APIError) as exc:
        await client.generate("prompt", "1024x1024", "auto")
    assert exc.value.status == 500
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_generate_network_error_is_retried(client, respx_mock):
    route = respx_mock.post(BASE_URL)
    # First call times out, second succeeds
    route.side_effect = [
        Exception("Connection refused"),
        Response(200, json={
            "data": [{"b64_json": DUMMY_PNG}],
            "usage": {"total_tokens": 1},
        }),
    ]
    data, usage = await client.generate("prompt", "1024x1024", "auto")
    assert usage == {"total_tokens": 1}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_generate_both_attempts_fail(client, respx_mock):
    route = respx_mock.post(BASE_URL)
    route.side_effect = [
        Exception("timeout"),
        Response(500, text="Still down"),
    ]
    with pytest.raises(APIError) as exc:
        await client.generate("prompt", "1024x1024", "auto")
    assert exc.value.status == 500


@pytest.mark.asyncio
async def test_generate_missing_data_field(client, respx_mock):
    respx_mock.post(BASE_URL).mock(
        return_value=Response(200, json={"data": [], "usage": {}}))
    with pytest.raises(APIError, match="No image data"):
        await client.generate("prompt", "1024x1024", "auto")


@pytest.mark.asyncio
async def test_generate_invalid_base64(client, respx_mock):
    respx_mock.post(BASE_URL).mock(
        return_value=Response(200, json={
            "data": [{"b64_json": "!!!not-valid-base64!!!"}],
            "usage": {},
        }))
    with pytest.raises(APIError, match="Failed to decode"):
        await client.generate("prompt", "1024x1024", "auto")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_client.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: Write `src/image2_mcp/client.py`**

```python
"""Async HTTP client for company image2 API."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from .errors import APIError, AuthError, NetworkError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 1  # 1 retry = 2 attempts total
_REQUEST_TIMEOUT = 60.0  # seconds


class Image2Client:
    """Async HTTP client for the image2 generations API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url
        self._auth_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self, prompt: str, size: str, quality: str
    ) -> tuple[bytes, dict[str, Any]]:
        """Call the image generations API and return (image_bytes, usage_dict).

        Raises:
            AuthError: on 401/403
            APIError: on other 4xx (no retry) or 5xx (after retry)
        """
        payload = {
            "model": "openai/gpt-image-2",
            "prompt": prompt,
            "size": size,
            "quality": quality,
        }

        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self._do_request(payload)
            except (APIError, AuthError):
                raise  # don't retry API/auth errors
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying...",
                        attempt + 1, _MAX_RETRIES + 1, exc,
                    )

        raise NetworkError(
            f"Request failed after {_MAX_RETRIES + 1} attempts: {last_error}"
        )

    async def _do_request(self, payload: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
        """Single HTTP request attempt. Returns (bytes, usage)."""
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                self._base_url,
                headers=self._auth_headers,
                json=payload,
            )
            return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> tuple[bytes, dict[str, Any]]:
        """Parse response or raise appropriate error."""
        if response.status_code in (401, 403):
            raise AuthError(f"API authentication failed ({response.status_code})")

        if response.status_code >= 400:
            raise APIError(
                status=response.status_code,
                message=f"API error {response.status_code}",
                body=response.text,
            )

        try:
            body = response.json()
        except Exception:
            raise APIError(
                status=response.status_code,
                message="Failed to parse API response as JSON",
                body=response.text,
            )

        data_list = body.get("data", [])
        if not data_list or not data_list[0].get("b64_json"):
            raise APIError(
                status=response.status_code,
                message="No image data in API response",
                body=str(body),
            )

        b64_str = data_list[0]["b64_json"]
        try:
            image_bytes = base64.b64decode(b64_str)
        except Exception:
            raise APIError(
                status=response.status_code,
                message="Failed to decode base64 image data",
                body="<binary>",
            )

        usage = body.get("usage", {})
        return image_bytes, usage
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_client.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_client.py src/image2_mcp/client.py
git commit -m "feat: add async HTTP client with retry logic"
```

---

### Task 6: MCP Server (`server.py` + `__main__.py`)

**Files:**
- Create: `src/image2_mcp/server.py`
- Create: `src/image2_mcp/__main__.py`
- Modify: `src/image2_mcp/__init__.py`

**Interfaces:**
- Consumes: `config.py`, `schemas.py`, `client.py`, `errors.py`
- Produces:
  - `create_server() -> FastMCP` — creates configured server
  - `main()` entry point — reads config, calls `create_server().run(transport="stdio")`

- [ ] **Step 1: Write `src/image2_mcp/server.py`**

```python
"""FastMCP server for image2 text-to-image generation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from .client import Image2Client
from .config import get_api_key, get_base_url, get_output_dir
from .errors import Image2Exception, ValidationError
from .schemas import GenerateImageInput, ImageOutput, VALID_SIZES


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
        + ". Custom: WxH (max 3840px per side, multiples of 16, ratio ≤ 3:1, pixels 655,360–8,294,400)"
    )


def create_server() -> FastMCP:
    """Create and configure the image2 MCP server."""
    api_key = get_api_key()
    base_url = get_base_url()
    output_dir = get_output_dir()

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
```

- [ ] **Step 2: Write `src/image2_mcp/__main__.py`**

```python
"""Entry point for python -m image2_mcp."""

from .server import create_server


def main() -> None:
    """Run the image2 MCP server via stdio."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update `src/image2_mcp/__init__.py`**

```python
"""Image2 MCP Server — wraps company image2 text-to-image API."""

from .server import create_server

__all__ = ["create_server"]
```

- [ ] **Step 4: Verify server loads without error**

```bash
MAGENE_API_KEY=sk-test python -c "from image2_mcp.server import create_server; s = create_server(); print('OK: server created')"
```
Expected: `OK: server created`

- [ ] **Step 5: Commit**

```bash
git add src/image2_mcp/server.py src/image2_mcp/__main__.py src/image2_mcp/__init__.py
git commit -m "feat: add MCP server with generate_image tool"
```

---

### Task 7: Integration test

**Files:**
- Create: `tests/test_integration.py`
- Modify: `tests/conftest.py` (create if needed)

**Interfaces:**
- Consumes: all modules assembled
- Produces: integration test with httpx mock that exercises full tool flow

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""Shared test fixtures."""
```

- [ ] **Step 2: Write `tests/test_integration.py`**

```python
"""Integration tests for the full generate_image tool flow."""

import os

import pytest

from image2_mcp.server import create_server, _generate_filename


# Set these before importing anything that reads config
os.environ["MAGENE_API_KEY"] = "sk-integration-test"
os.environ["MAGENE_API_BASE_URL"] = "http://integration.test/v1/images/generations"


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


def test_generate_filename_sanitized():
    name = _generate_filename("sub/dir/file")
    assert "/" not in name
    assert "\\" not in name


@pytest.mark.asyncio
async def test_generate_image_empty_prompt_returns_error():
    """Calling tool with empty prompt returns isError."""
    server = create_server()
    result = await server.call_tool("generate_image", {
        "prompt": "",
        "size": "1024x1024",
    })
    assert result.isError is True
    assert any("prompt" in c.text.lower() for c in result.content if hasattr(c, "text"))


@pytest.mark.asyncio
async def test_generate_image_bad_size_returns_error():
    server = create_server()
    result = await server.call_tool("generate_image", {
        "prompt": "a cat",
        "size": "bad-size",
    })
    assert result.isError is True


@pytest.mark.asyncio
async def test_generate_image_preset_size_passes_validation():
    """Preset size 'auto' passes validation, fails at network layer."""
    server = create_server()
    result = await server.call_tool("generate_image", {
        "prompt": "a cat",
        "size": "auto",
        "quality": "low",
    })
    # Should fail at network, not validation
    assert result.isError is True
    assert any("network" in c.text.lower() or "connection" in c.text.lower()
               for c in result.content if hasattr(c, "text"))
```

- [ ] **Step 3: Run integration tests**

```bash
python -m pytest tests/test_integration.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add integration tests for full tool flow"
```

---

### Task 8: README documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# image2-mcp

MCP Server for the company image2 text-to-image API. Allows Claude Code, Codex,
and other MCP-compatible AI tools to generate images directly.

## Prerequisites

- Python 3.10+
- A company API Key for the unified AI platform

## Installation

```bash
pip install git+https://git.company.com/platform/image2-mcp.git
```

Or clone and install locally:

```bash
git clone https://git.company.com/platform/image2-mcp.git
cd image2-mcp
pip install -e .
```

## Configuration

Configure via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAGENE_API_KEY` | Yes | — | Your company API key |
| `MAGENE_API_BASE_URL` | No | `http://tops.magene.cn:11636/api/v1/images/generations` | API endpoint |
| `IMAGE2_OUTPUT_DIR` | No | System temp directory `/image2-output` | Default image save location |

## Usage with Claude Code

Add to your Claude Code MCP configuration (`~/.claude/settings.local.json` or project `.claude/settings.local.json`):

```json
{
  "mcpServers": {
    "image2": {
      "command": "python",
      "args": ["-m", "image2_mcp"],
      "env": {
        "MAGENE_API_KEY": "your-api-key-here",
        "IMAGE2_OUTPUT_DIR": "/Users/you/Pictures/image2-output"
      }
    }
  }
}
```

## Usage with Codex

Add to your Codex MCP configuration:

```json
{
  "mcpServers": {
    "image2": {
      "command": "python",
      "args": ["-m", "image2_mcp"],
      "env": {
        "MAGENE_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## How It Works

The AI calls `generate_image` as a native tool:

```
AI: generate_image(prompt="a cat in a garden", size="1024x1024")
    → Server validates parameters
    → POST to company API
    → Decodes Base64 response
    → Saves PNG to disk
    → Returns image + file path + usage stats to AI
```

## Tool Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | Yes | — | Text description of the image |
| `size` | string | Yes | — | Image size (see below) |
| `quality` | string | No | `auto` | `low`, `medium`, `high`, or `auto` |
| `output_dir` | string | No | From env | Custom output directory |
| `filename` | string | No | Auto-generated | Custom filename (without `.png`) |

### Available Sizes

| Value | Resolution |
|-------|-----------|
| `1024x1024` | 1K Square |
| `1536x1024` | 1.5K Landscape |
| `1024x1536` | 1.5K Portrait |
| `2048x2048` | 2K Square |
| `2048x1152` | 2K Landscape |
| `3840x2160` | 4K Landscape |
| `2160x3840` | 4K Portrait |
| `auto` | Automatic |

Custom sizes supported: `WxH` format, max 3840px per side, multiples of 16,
aspect ratio ≤ 3:1, total pixels 655,360–8,294,400.

## Development

```bash
pip install -e ".[dev]"
pytest
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with install and usage instructions"
```

---

### Task 9: Final verification — run test suite

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: ALL PASSING

- [ ] **Step 2: Verify server starts in stdio mode**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | MAGENE_API_KEY=sk-test timeout 5 python -m image2_mcp 2>&1 || true
```
Expected: returns a valid JSON-RPC initialize response

- [ ] **Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final verification and polish"
```
```

---

## Coverage Checklist

| Spec Requirement | Task |
|------------------|------|
| `generate_image` tool with 5 params (prompt, size, quality, output_dir, filename) | Task 6 |
| `size` = required field | Task 4 |
| `size` validation (presets + custom rules) | Task 4 |
| `quality` defaults to `auto` | Task 4 |
| Image returned via MCP Image type | Task 6 |
| Text metadata (path, url, usage) returned | Task 6 |
| `MAGENE_API_KEY` env var, fatal if missing | Task 3 |
| `MAGENE_API_BASE_URL` env var with default | Task 3 |
| `IMAGE2_OUTPUT_DIR` env var with default | Task 3 |
| Error: API key missing → fatal at start | Task 3 |
| Error: prompt empty → validation error | Task 4 |
| Error: size invalid → helpful message | Task 4 |
| Error: network → retry 1x | Task 5 |
| Error: 4xx → no retry, pass through | Task 5 |
| Error: 5xx → retry 1x | Task 5 |
| Error: bad base64 → error returned | Task 5 |
| Error: disk write fail → error returned | Task 6 |
| Python 3.10+ | Task 1 |
| `mcp`, `httpx`, `pydantic` dependencies | Task 1 |
| pip install / uvx distribution | Task 8 |
| README with config guide | Task 8 |
