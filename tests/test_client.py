"""Tests for image2_mcp.client module."""

import base64

import httpx
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
    return Image2Client(base_url=BASE_URL, api_key=API_KEY, model="openai/gpt-image-2")


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
    # First call throws a connection error, second succeeds
    route.side_effect = [
        httpx.ConnectError("Connection refused"),
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
        httpx.TimeoutException("timeout"),
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
