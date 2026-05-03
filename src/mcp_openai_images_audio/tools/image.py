"""
The single ``image`` tool — generate, edit, or compose with the
gpt-image family.

Design summary:

- ONE tool, three modes selected by ``references_paths``:
    - empty/None  -> /v1/images/generations
    - 1 file      -> /v1/images/edits, "modify this image"
    - 2..16 files -> /v1/images/edits, "compose / use as references"
- The model is chosen automatically by ``client.pick_model``:
  gpt-image-2 by default, gpt-image-1.5 when transparency is requested
  (gpt-image-2 currently rejects transparent backgrounds — confirmed
  regression in OpenAI's docs/community).
- ``size`` is REQUIRED with no default: Claude must consciously pick a
  resolution that fits the task.
- ``quality`` and ``input_fidelity`` are OPTIONAL and should usually
  be omitted.
- ``output_format`` is derived from the file extension on
  ``output_path``. The server never invents formats.
- The response intentionally does NOT include the image bytes. Claude
  reads the file via its ``Read`` tool only when visual verification
  is actually needed.
- After saving, we inspect the file: report ``has_alpha`` and, when
  transparency was requested, an ``alpha_appears_baked`` flag that
  catches the "model painted the editor checkerboard into RGB" trap.
"""

from __future__ import annotations

import base64
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_openai_images_audio.client import edit, generate
from mcp_openai_images_audio.image_inspect import inspect
from mcp_openai_images_audio.logger import log_event
from mcp_openai_images_audio.paths import (
    output_format_from_path,
    validate_output_path,
    validate_references,
)
from mcp_openai_images_audio.pricing import estimate_cost_usd

# The full enumeration of sizes gpt-image-2 accepts. ``Literal`` here is
# what the MCP SDK turns into a JSON Schema enum, so Claude only ever
# sees these eight strings as valid values.
Size = Literal[
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "2048x2048",
    "2048x1152",
    "1152x2048",
    "3840x2160",
    "2160x3840",
]
Quality = Literal["low", "medium", "high"]
Background = Literal["auto", "opaque", "transparent"]
Fidelity = Literal["low", "high"]


# Tool description shown to Claude on every call. Keep it short — the
# detailed prompting rules live in the `image-guide://full` resource.
_TOOL_DESCRIPTION = """\
Generate, edit, or compose images via OpenAI's gpt-image family.

BEFORE the FIRST call in a conversation, read the MCP resource
`image-guide://full` for the full prompting guide (structure,
realism rules, edit/compose modes, when to set quality/fidelity).
You only need to read it once per conversation.

Mode is selected by `references_paths`:
- omitted/empty  -> generate from text alone
- 1 path         -> edit that image
- 2..16 paths    -> generate using them as labeled references

Model routing is automatic and reported in the response:
- background='transparent'  -> gpt-image-1.5 (gpt-image-2 rejects alpha)
- everything else           -> gpt-image-2 (flagship)

Returns metadata only — the file is written to `output_path`.
Read the file with the Read tool only if you need to verify the result.
"""


def register(server: FastMCP) -> None:
    """Attach the ``image`` tool to ``server``.

    We register at runtime (rather than via a module-level decorator)
    so that the FastMCP instance is constructed in one place
    (``server.build_server``) and the tool functions stay importable
    without side effects.
    """

    @server.tool(name="image", description=_TOOL_DESCRIPTION)
    async def image(
        prompt: Annotated[
            str,
            Field(
                description=(
                    "Structured English description of the desired image. "
                    "When references_paths has more than one entry, label "
                    "each one explicitly in the prompt "
                    '(e.g. "Image 1: subject. Image 2: style reference."). '
                    "See image-guide://full for the full prompting guide."
                )
            ),
        ],
        output_path: Annotated[
            str,
            Field(
                description=(
                    "ABSOLUTE filesystem path where the result will be saved. "
                    "Extension determines format: .png / .jpg / .jpeg / .webp. "
                    "Parent directory MUST already exist (create it via Bash "
                    "mkdir -p before retrying). File MUST NOT already exist."
                )
            ),
        ],
        size: Annotated[
            Size,
            Field(
                description=(
                    "Output resolution. REQUIRED — pick deliberately based "
                    "on the use case:\n"
                    "- 1024x1024 — generic single subject, avatar, icon\n"
                    "- 1536x1024 / 1024x1536 — landscape / portrait composition\n"
                    "- 2048x2048 — high-res square (hero blocks, album art)\n"
                    "- 2048x1152 / 1152x2048 — 16:9 / 9:16 banners, video thumbs\n"
                    "- 3840x2160 / 2160x3840 — 4K, only when text/UI must be crisp"
                )
            ),
        ],
        references_paths: Annotated[
            list[str] | None,
            Field(
                default=None,
                description=(
                    "Optional. Up to 16 ABSOLUTE paths to existing PNG/JPG/WebP "
                    "files (each ≤50 MB) used as input images. "
                    "Omit for pure text-to-image generation."
                ),
            ),
        ] = None,
        quality: Annotated[
            Quality | None,
            Field(
                default=None,
                description=(
                    "Optional. OMIT in most cases — the default ('auto') already "
                    "produces excellent quality. Pass 'low' for cheap drafts. "
                    "Pass 'high' only when text legibility (UI mockups), "
                    "photorealism, or final-output quality is critical."
                ),
            ),
        ] = None,
        input_fidelity: Annotated[
            Fidelity | None,
            Field(
                default=None,
                description=(
                    "Optional. Only relevant when references_paths is set. "
                    "Pass 'high' when faces/identity must be preserved exactly "
                    "(portrait edits, virtual try-on, product placement). "
                    "Otherwise omit — defaults to 'low' on the OpenAI side, "
                    "which is cheaper and faster."
                ),
            ),
        ] = None,
        background: Annotated[
            Background,
            Field(
                default="auto",
                description=(
                    "Background handling. Use 'transparent' for logos, icons, "
                    "isolated products, or anything you'll composite later "
                    "(only valid with .png/.webp). 'opaque' forces a solid "
                    "background. 'auto' lets the model decide."
                ),
            ),
        ] = "auto",
    ) -> dict[str, Any]:
        # 1. Validate paths up front. These raise ValueError with
        #    actionable messages that Claude can read and react to —
        #    which is exactly what we want from a "dumb" server.
        out_path = validate_output_path(output_path)
        refs = validate_references(references_paths)

        if background == "transparent" and out_path.suffix.lower() in {".jpg", ".jpeg"}:
            # JPEG has no alpha channel; transparent + jpeg is a logical
            # contradiction we catch ourselves rather than letting the
            # API reject it with a less obvious message.
            raise ValueError(
                "background='transparent' is incompatible with JPEG output. "
                "Use a .png or .webp output_path, or pick a different background."
            )

        out_format = output_format_from_path(out_path)

        # 2. Dispatch to the right OpenAI endpoint. Each helper picks
        #    the actual model internally and returns it in the tuple
        #    so we can echo it back to the caller.
        try:
            if refs:
                response, model_used = await edit(
                    prompt=prompt,
                    references=refs,
                    size=size,
                    output_format=out_format,
                    quality=quality,
                    background=background,
                    input_fidelity=input_fidelity,
                )
                mode = "edit" if len(refs) == 1 else "compose"
            else:
                response, model_used = await generate(
                    prompt=prompt,
                    size=size,
                    output_format=out_format,
                    quality=quality,
                    background=background,
                )
                mode = "generate"
        except Exception as exc:
            # Log first (best-effort), then re-raise after optionally
            # rewriting the message into something more actionable.
            log_event(
                {
                    "event": "image.error",
                    "mode": "edit" if refs else "generate",
                    "error": repr(exc),
                    "prompt_preview": prompt[:200],
                    "size": size,
                    "output_path": str(out_path),
                    "references_count": len(refs),
                    "background": background,
                }
            )
            _reraise_with_hint(exc, background=background)

        # 3. Decode and write the file. The gpt-image family always
        #    returns base64; not configurable, so no branching on
        #    response_format.
        b64 = response.data[0].b64_json
        raw = base64.b64decode(b64)
        out_path.write_bytes(raw)

        # 4. Inspect the saved file. This catches two real-world traps:
        #    - "transparent was requested but the upstream silently
        #      demoted it" (alpha missing on PNG/WebP)
        #    - "the model painted the editor checkerboard into RGB
        #      to *look* transparent" (alpha_appears_baked)
        inspection = inspect(out_path, requested_transparent=(background == "transparent"))

        # 5. Pull usage. The ``usage`` field on SDK response objects
        #    is a Pydantic model in newer versions and a plain dict
        #    in older ones; ``model_dump`` covers both via duck-typing.
        usage_payload: dict[str, Any] | None
        usage_obj = getattr(response, "usage", None)
        if usage_obj is None:
            usage_payload = None
        elif hasattr(usage_obj, "model_dump"):
            usage_payload = usage_obj.model_dump()
        else:
            usage_payload = dict(usage_obj)

        cost = estimate_cost_usd(usage_payload)
        bytes_written = len(raw)

        # 6. Compose any warnings the inspection wants to surface.
        #    These go into the response so Claude sees them directly
        #    in the tool result, not just in our sidecar log.
        warnings: list[str] = []
        if background == "transparent":
            if inspection.has_alpha is False:
                warnings.append(
                    "Requested transparent background but the saved file has no alpha channel. "
                    "The image is opaque despite the request."
                )
            elif inspection.has_alpha and inspection.alpha_used is False:
                warnings.append(
                    "File has an alpha channel but every pixel is fully opaque. "
                    "Visually equivalent to no transparency."
                )
        if inspection.alpha_appears_baked:
            warnings.append(
                "The image appears to contain a painted gray checkerboard pattern in RGB "
                "instead of real transparency. The 'transparent' look is fake; do not use "
                "this output as if it had an alpha channel."
            )

        log_event(
            {
                "event": "image.ok",
                "mode": mode,
                "model": model_used,
                "size": size,
                "output_path": str(out_path),
                "bytes": bytes_written,
                "references_count": len(refs),
                "quality": quality,
                "input_fidelity": input_fidelity,
                "background": background,
                "has_alpha": inspection.has_alpha,
                "alpha_used": inspection.alpha_used,
                "alpha_appears_baked": inspection.alpha_appears_baked,
                "warnings": warnings,
                "usage": usage_payload,
                "estimated_cost_usd": cost,
                "prompt_preview": prompt[:200],
            }
        )

        result: dict[str, Any] = {
            "path": str(out_path),
            "bytes": bytes_written,
            "size": size,
            "model": model_used,
            "mode": mode,
            "has_alpha": inspection.has_alpha,
            "alpha_used": inspection.alpha_used,
            "tokens_used": (usage_payload or {}).get("total_tokens"),
            "estimated_cost_usd": cost,
        }
        if inspection.alpha_appears_baked is not None:
            result["alpha_appears_baked"] = inspection.alpha_appears_baked
        if warnings:
            result["warnings"] = warnings
        return result


def _reraise_with_hint(exc: BaseException, *, background: str) -> None:
    """Re-raise ``exc``, possibly with a friendlier message attached.

    For the one upstream error we know how to interpret — "transparent
    background not supported" — we explain that the server already
    routes transparency requests to gpt-image-1.5 and suggest the most
    likely real cause (e.g. an account that lost access to 1.5) so
    Claude has a useful next step instead of a raw 400.

    Anything we don't recognize is re-raised unchanged.
    """
    text = str(exc)
    if background == "transparent" and "Transparent background is not supported" in text:
        raise RuntimeError(
            "Upstream rejected transparent background even though the server "
            "routes such requests to gpt-image-1.5. This usually means the "
            "OpenAI account temporarily lost access to gpt-image-1.5 or the "
            "model is in maintenance. Workaround: rerun with "
            "background='auto' or 'opaque', then post-process the output to "
            "remove the background (e.g. cwebp / magick / a remove-bg tool). "
            f"Original error: {text}"
        ) from exc
    raise exc
