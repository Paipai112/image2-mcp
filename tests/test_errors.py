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


def test_validation_error_not_retryable():
    err = ValidationError("prompt is required")
    assert err.retryable is False


def test_auth_error_not_retryable():
    err = AuthError()
    assert err.retryable is False
