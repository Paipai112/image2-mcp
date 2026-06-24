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
