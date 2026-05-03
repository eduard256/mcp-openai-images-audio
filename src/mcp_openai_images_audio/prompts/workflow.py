"""
The single MCP prompt this server exposes.

MCP prompts behave like "always-on system instructions": when an MCP
client (Claude Code) connects to this server, the prompt is included
in the conversation context automatically. We use ours to point Claude
at the detailed resource (``image-guide://full``) rather than dumping
the whole guide into context, because the guide is ~5 KB and only
relevant when the user actually wants images.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

_WORKFLOW_TEXT = """\
This server exposes a single tool, `image`, backed by OpenAI's
gpt-image-2 model. It can generate, edit, or compose images.

Workflow:

1. If, and only if, the user's request actually needs an image, read
   the MCP resource `image-guide://full` BEFORE the first call to
   `image` in this conversation. The guide explains:
   - the prompt structure that gpt-image-2 responds well to,
   - photorealism rules (camera language, anti-words),
   - how to use references (single edit vs multi-image compose),
   - how to pick `size` for the use case,
   - when to set `quality` and `input_fidelity`,
   - common anti-patterns.

2. Construct the prompt according to the guide and call `image` with
   the absolute `output_path` (parent directory must exist; file must
   not). The tool returns metadata only — no image bytes.

3. If you need to verify the output visually (text legibility, layout,
   identity preservation), read the saved file with the Read tool.
   Otherwise, do not read it.

4. If the user does not need an image, do nothing here.
"""


def register(server: FastMCP) -> None:
    """Attach the workflow prompt to ``server``."""

    @server.prompt(
        name="image_workflow",
        description=(
            "Workflow rules for the `image` tool. Read once, follow whenever "
            "the user wants an image generated, edited, or composed."
        ),
    )
    def image_workflow() -> str:
        return _WORKFLOW_TEXT
