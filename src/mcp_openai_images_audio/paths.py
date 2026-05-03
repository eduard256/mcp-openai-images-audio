"""
Path validation helpers shared by the `image` tool.

The MCP server is intentionally strict about file paths: it does NOT
create parent directories, does NOT overwrite existing files, and does
NOT accept relative paths. This keeps the server "dumb" and pushes all
control over the filesystem back to the caller (Claude), who can
inspect, mkdir, and rename via its own tools.

Every public function in this module returns ``None`` on success or
raises ``ValueError`` with a message tailored to be actionable for
Claude (e.g. "directory does not exist: /foo — create it with mkdir
-p before retrying").
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

# OpenAI's images endpoint accepts only these container formats on
# input (for `image_edit`) and produces only these on output. We mirror
# that allow-list when validating the caller's `output_path` extension
# and the reference paths.
_ALLOWED_OUTPUT_EXTS: Final[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_ALLOWED_REFERENCE_EXTS: Final[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".webp"})

# OpenAI's documented hard limit for image inputs to /v1/images/edits.
_MAX_REFERENCE_BYTES: Final[int] = 50 * 1024 * 1024  # 50 MB
_MAX_REFERENCE_COUNT: Final[int] = 16


def validate_output_path(output_path: str) -> Path:
    """Return a resolved ``Path`` after enforcing all output-path rules.

    Rules:
    1. Path must be absolute. Relative paths are rejected because the
       server's CWD is not a stable contract — Claude must construct
       the absolute path itself from its own working directory.
    2. Extension must be one of .png/.jpg/.jpeg/.webp. The extension
       drives the OpenAI ``output_format`` parameter, so unsupported
       extensions cannot be silently coerced.
    3. The parent directory must already exist. We do not ``mkdir``
       on the caller's behalf — if Claude is targeting a project
       subfolder that does not exist, it should learn about it and
       create it explicitly.
    4. The file itself must NOT exist. Overwrite is dangerous and
       irreversible; Claude can ``rm`` the file first if that's truly
       intended.

    Returns the resolved ``Path`` so the caller can write to it.
    """
    path = Path(output_path)

    if not path.is_absolute():
        raise ValueError(
            f"output_path must be absolute, got: {output_path!r}. "
            "Pass a full absolute path like /home/user/project/img.png."
        )

    ext = path.suffix.lower()
    if ext not in _ALLOWED_OUTPUT_EXTS:
        raise ValueError(
            f"Unsupported extension {ext!r} in output_path. Use .png, .jpg/.jpeg, or .webp."
        )

    parent = path.parent
    if not parent.exists():
        raise ValueError(
            f"Parent directory does not exist: {parent}. "
            "Create it first (e.g. `mkdir -p` via the Bash tool) and retry."
        )
    if not parent.is_dir():
        raise ValueError(f"Parent path exists but is not a directory: {parent}.")

    if path.exists():
        raise ValueError(
            f"File already exists: {path}. "
            "Delete it first if you really want to overwrite, "
            "or pick a different output_path."
        )

    return path


def output_format_from_path(output_path: Path) -> str:
    """Map a validated output path's extension to the OpenAI value.

    ``validate_output_path`` must have been called first; we do not
    re-validate here because callers shouldn't pay for that twice.
    """
    ext = output_path.suffix.lower()
    if ext == ".png":
        return "png"
    if ext == ".webp":
        return "webp"
    # .jpg and .jpeg both mean JPEG to OpenAI.
    return "jpeg"


def validate_references(references_paths: list[str] | None) -> list[Path]:
    """Validate a list of reference image paths.

    An empty/None list means "generate from scratch", which is allowed
    and returns ``[]``. A non-empty list is checked against:

    - count limit (16, OpenAI's hard cap)
    - per-file existence and "is regular file"
    - extension allow-list
    - per-file size limit (50 MB, OpenAI's hard cap)

    Each reference must be an absolute path for the same reason
    output_path must be: the server has no stable CWD contract with
    its caller.
    """
    if not references_paths:
        return []

    if len(references_paths) > _MAX_REFERENCE_COUNT:
        raise ValueError(
            f"Too many references: {len(references_paths)}. "
            f"OpenAI accepts at most {_MAX_REFERENCE_COUNT} input images."
        )

    resolved: list[Path] = []
    for raw in references_paths:
        path = Path(raw)

        if not path.is_absolute():
            raise ValueError(
                f"reference path must be absolute, got: {raw!r}. Pass a full absolute path."
            )
        if not path.exists():
            raise ValueError(f"reference file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"reference path is not a regular file: {path}")

        ext = path.suffix.lower()
        if ext not in _ALLOWED_REFERENCE_EXTS:
            raise ValueError(
                f"Unsupported reference extension {ext!r} for {path}. "
                "Use .png, .jpg/.jpeg, or .webp."
            )

        size = path.stat().st_size
        if size > _MAX_REFERENCE_BYTES:
            raise ValueError(
                f"reference file too large: {path} is {size} bytes, "
                f"OpenAI accepts up to {_MAX_REFERENCE_BYTES} bytes (50 MB)."
            )

        resolved.append(path)

    return resolved
