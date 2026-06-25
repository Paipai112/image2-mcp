"""Async HTTP client for company image2 API."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from .errors import APIError, AuthError, NetworkError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 1  # 1 retry = 2 attempts total

# Timeout per-diemension tier: bigger images need more time.
# Worst case: 3840×2160 ("4K") at high quality ≈ 3–5 min.
_REQUEST_TIMEOUT_BY_PIXELS: dict[tuple[int, int], float] = {
    # (lower_bound, upper_bound): timeout_seconds
    (0, 1_048_576): 90.0,   # up to 1024x1024
    (1_048_577, 2_359_296): 180.0,  # up to 1536x1024 / 1024x1536
    (2_359_297, 4_194_304): 240.0,  # up to 2048x2048
    (4_194_305, 8_294_400): 360.0,  # up to 3840x2160 / 2160x3840
}
# Total fallback for anything that doesn't match
_REQUEST_TIMEOUT_FALLBACK = 420.0


def _timeout_for_size(size: str) -> float:
    """Return the appropriate HTTP timeout for the given image size.

    Larger images take more time to generate. Uses pixel-count tiers
    to ensure even 4K images at high quality won't hit a timeout.

    Timeouts:
        up to 1024x1024       → 90s
        up to 1536x1024       → 180s
        up to 2048x2048       → 240s
        4K (3840x2160)        → 360s
        auto / unknown        → 420s (generous fallback)
    """
    if size == "auto":
        return _REQUEST_TIMEOUT_FALLBACK

    import re

    m = re.match(r"^(\d+)x(\d+)$", size)
    if not m:
        return _REQUEST_TIMEOUT_FALLBACK

    pixels = int(m.group(1)) * int(m.group(2))
    for (lo, hi), t in _REQUEST_TIMEOUT_BY_PIXELS.items():
        if lo <= pixels <= hi:
            return t

    return _REQUEST_TIMEOUT_FALLBACK


class Image2Client:
    """Async HTTP client for the image2 generations API."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._base_url = base_url
        self._model = model
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _client_for(self, size: str) -> httpx.AsyncClient:
        """Create a client with a timeout tuned for the target size."""
        t = _timeout_for_size(size)
        return httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(t),
        )

    async def generate(
        self, prompt: str, size: str, quality: str
    ) -> tuple[bytes, dict[str, Any]]:
        """Call the image generations API and return (image_bytes, usage_dict).

        Raises:
            AuthError: on 401/403
            APIError: on other 4xx (no retry) or 5xx (after retry)
            NetworkError: on network connectivity failures (after retry)
        """
        payload = {
            "model": self._model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
        }

        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self._do_request(payload, size)
            except (AuthError, APIError):
                raise  # don't retry auth/client errors
            except (
                httpx.ConnectError,
                httpx.TimeoutException,
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.WriteError,
                httpx.PoolTimeout,
            ) as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying...",
                        attempt + 1, _MAX_RETRIES + 1, exc,
                    )

        raise NetworkError(
            f"Request failed after {_MAX_RETRIES + 1} attempts: {last_error}"
        )

    async def _do_request(self, payload: dict[str, Any], size: str) -> tuple[bytes, dict[str, Any]]:
        """Single HTTP request attempt. Returns (image_bytes, usage)."""
        async with self._client_for(size) as client:
            response = await client.post(self._base_url, json=payload)
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
