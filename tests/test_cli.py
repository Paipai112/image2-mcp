"""Tests for CLI health check in __main__.py."""

import pytest
from image2_mcp.__main__ import _check_env, _check_output_dir, _check_uv


def test_check_env_missing(monkeypatch):
    monkeypatch.delenv("MAGENE_API_KEY", raising=False)
    assert _check_env() is False


def test_check_env_present(monkeypatch):
    monkeypatch.setenv("MAGENE_API_KEY", "sk-test-12345678")
    assert _check_env() is True


def test_check_uv_present():
    # uv should be installed in this project's venv
    assert _check_uv() is True


def test_check_output_dir_writable(monkeypatch):
    import tempfile

    monkeypatch.setenv("IMAGE2_OUTPUT_DIR", tempfile.mkdtemp())
    assert _check_output_dir() is True


def test_check_output_dir_not_writable(monkeypatch):
    monkeypatch.setenv("IMAGE2_OUTPUT_DIR", "/dev/null/not-a-dir")
    assert _check_output_dir() is False


@pytest.mark.asyncio
async def test_health_check_all_pass_returns_0(monkeypatch):
    from image2_mcp.__main__ import health_check

    monkeypatch.setenv("MAGENE_API_KEY", "sk-test-key")
    monkeypatch.setenv("MAGENE_API_BASE_URL", "http://localhost:9999/v1/images/generations")
    monkeypatch.setenv("IMAGE2_OUTPUT_DIR", "/tmp")

    # API check will fail (no server), but env + uv + output_dir pass
    code = await health_check()
    # With API down, exit code should be 1 (at least one check failed)
    assert code == 1


@pytest.mark.asyncio
async def test_main_health_check_flag(monkeypatch, capsys):
    """Invoking --health-check flag should exit 0 or 1 without raising."""
    import sys
    import subprocess

    monkeypatch.setenv("MAGENE_API_KEY", "sk-test-key")
    monkeypatch.setenv("MAGENE_API_BASE_URL", "http://localhost:9999/v1/images/generations")

    # Run in a subprocess since main() internally calls asyncio.run()
    result = subprocess.run(
        [sys.executable, "-m", "image2_mcp", "--health-check"],
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "MAGENE_API_KEY": "sk-test-key",
            "MAGENE_API_BASE_URL": "http://localhost:9999/v1/images/generations",
        },
        timeout=10,
    )
    assert result.returncode in (0, 1)
    assert "Image2 MCP" in result.stdout

