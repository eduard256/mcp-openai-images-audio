"""
CLI entry point.

`mcp-openai-images-audio` (the script) and `python -m
mcp_openai_images_audio` both land here. The single responsibility of this
module is to start the FastMCP server over stdio so that an MCP client
(Claude Code, Inspector, ...) can talk to it via the standard protocol.
"""

from __future__ import annotations

from mcp_openai_images_audio.server import build_server


def main() -> None:
    """Run the MCP server over stdio.

    FastMCP's `.run()` blocks until the parent process closes stdin, which
    is exactly the lifecycle Claude Code expects for a stdio-transport MCP
    server.
    """
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
