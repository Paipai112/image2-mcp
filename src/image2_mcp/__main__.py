"""Entry point for python -m image2_mcp."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx


def _green(msg: str) -> str:
    return f"\033[32m✓ {msg}\033[0m"


def _red(msg: str) -> str:
    return f"\033[31m✗ {msg}\033[0m"


def _dim(msg: str) -> str:
    return f"\033[2m{msg}\033[0m"


def _check_env() -> bool:
    """Check required environment variables."""
    api_key = os.environ.get("MAGENE_API_KEY", "").strip()
    if api_key:
        print(_green(f"MAGENE_API_KEY is set ({api_key[:8]}...)"))
        return True
    else:
        print(_red("MAGENE_API_KEY is not set"))
        return False


async def _check_api_connectivity(base_url: str) -> bool:
    """Send a HEAD request to the API endpoint to verify connectivity."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Send OPTIONS request — lightweight, doesn't consume credits
            resp = await client.options(base_url)
            status = resp.status_code
            if status < 500:
                print(_green(f"API endpoint reachable (HTTP {status}): {base_url}"))
                return True
            else:
                print(_red(f"API returned HTTP {status}: {base_url}"))
                return False
    except httpx.ConnectError:
        print(_red(f"Cannot connect to API: {base_url}"))
        print(_dim("  Check your network/VPN and MAGENE_API_BASE_URL"))
        return False
    except httpx.TimeoutException:
        print(_red(f"API connection timed out: {base_url}"))
        return False
    except Exception as exc:
        print(_red(f"API connectivity check failed: {exc}"))
        return False


def _check_uv() -> bool:
    """Check if uv is available."""
    import shutil

    if shutil.which("uv"):
        print(_green("uv is installed"))
        return True
    else:
        print(_red("uv is not installed. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"))
        return False


def _check_output_dir() -> bool:
    """Check output directory is writable."""
    from .config import get_output_dir

    try:
        out_dir = get_output_dir()
        test_file = out_dir / ".image2_write_test"
        test_file.touch()
        test_file.unlink()
        print(_green(f"Output directory writable: {out_dir}"))
        return True
    except Exception as exc:
        print(_red(f"Output directory not writable: {exc}"))
        return False


async def health_check() -> int:
    """Run all health checks. Returns exit code (0 = all good)."""
    print("=" * 50)
    print("  Image2 MCP — Health Check")
    print("=" * 50)
    print()

    checks = [
        ("Environment", _check_env()),
        ("uv / Python", _check_uv()),
    ]

    # API connectivity check — needs env vars first
    api_key = os.environ.get("MAGENE_API_KEY", "").strip()
    base_url = os.environ.get(
        "MAGENE_API_BASE_URL",
        "http://tops.magene.cn:11636/api/v1/images/generations",
    ).rstrip("/")

    if api_key:
        checks.append(("API Connectivity", await _check_api_connectivity(base_url)))

    checks.append(("Output Directory", _check_output_dir()))

    print()
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)

    if passed == total:
        print(_green(f"All {total} checks passed!"))
        print()
        print("Your image2 MCP should be ready to use.")
        print("Run the server with: uv run python -m image2_mcp")
        return 0
    else:
        failed = total - passed
        print(_red(f"{failed}/{total} check(s) failed. See details above."))
        return 1


def main() -> None:
    """Run the image2 MCP server via stdio, or health check."""
    if "--health-check" in sys.argv or "--health" in sys.argv:
        import asyncio

        code = asyncio.run(health_check())
        sys.exit(code)

    from .server import create_server

    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
