"""
Construct and configure the FastMCP server.

This module's only public API is ``build_server``. ``__main__`` calls
it once at process start, ``server.run()`` on the result, and that's
the whole lifecycle.

Splitting registration across submodules (``tools/image.py``,
``prompts/workflow.py``) keeps each file focused on a single
responsibility while ``build_server`` is the one place that knows the
server's name, version, and which capabilities it exposes.
"""

from __future__ import annotations

from importlib.resources import files

from mcp.server.fastmcp import FastMCP

from mcp_openai_images_audio.prompts import workflow as workflow_prompt
from mcp_openai_images_audio.tools import image as image_tool

# The single static resource we expose. Bundled inside the package so
# it's always available regardless of where the user installed from.
_GUIDE_URI = "image-guide://full"
_GUIDE_PACKAGE = "mcp_openai_images_audio.resources"
_GUIDE_FILENAME = "image_guide.md"


def build_server() -> FastMCP:
    """Build and return a fully wired ``FastMCP`` instance.

    The construction order — server -> resources -> tools -> prompts —
    is arbitrary; we keep it lexical-ish for readability.
    """
    server = FastMCP(
        name="mcp-openai-images-audio",
        instructions=(
            "OpenAI gpt-image-2 access via MCP. "
            "Read the resource image-guide://full before the first call "
            "to the `image` tool in a conversation."
        ),
    )

    @server.resource(
        uri=_GUIDE_URI,
        name="image_guide",
        description=(
            "Full prompting guide for the gpt-image-2 model exposed by "
            "the `image` tool: structure, photorealism, edit/compose "
            "modes, sizing, and anti-patterns."
        ),
        mime_type="text/markdown",
    )
    def image_guide() -> str:
        """Return the bundled prompting guide as Markdown text.

        ``importlib.resources`` reads from inside the installed wheel,
        so this works whether the package is installed via `pip
        install`, `uvx`, or imported from a source checkout.
        """
        return files(_GUIDE_PACKAGE).joinpath(_GUIDE_FILENAME).read_text(encoding="utf-8")

    image_tool.register(server)
    workflow_prompt.register(server)

    return server
