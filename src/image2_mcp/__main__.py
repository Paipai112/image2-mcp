"""Entry point for python -m image2_mcp."""

from .server import create_server


def main() -> None:
    """Run the image2 MCP server via stdio."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
