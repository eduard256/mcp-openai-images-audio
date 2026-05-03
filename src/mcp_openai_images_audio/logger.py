"""
JSONL request log with simple size-based rotation.

Every successful or failed image call is appended as a single JSON
object on its own line to ``~/.cache/mcp-openai-images-audio/log.jsonl``.
This is a debugging and accounting aid — Claude Code does not see this
file, and the server does not expose it through MCP.

Rotation policy: when the active log exceeds 10 MB on the next write,
it is renamed to ``log.jsonl.1`` (replacing any previous backup), and a
fresh ``log.jsonl`` is started. Two files maximum, no compression. This
keeps disk usage bounded at ~20 MB regardless of how long the server
runs without crashing.

We intentionally do not use the stdlib ``logging`` module here. The
output we want is structured JSONL, not a human-friendly log line; the
``logging`` module's strengths (handlers, formatters, levels) bring
configuration surface area we don't need.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 10 MB rotation threshold. Chosen to keep the file readable in a text
# editor while still capturing many days of normal usage.
_MAX_BYTES: int = 10 * 1024 * 1024


def _log_dir() -> Path:
    """Resolve the cache directory, honoring the XDG cache spec.

    Falls back to ``~/.cache`` if ``XDG_CACHE_HOME`` is not set, which is
    the spec-defined default and matches Linux defaults.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "mcp-openai-images-audio"


def _log_path() -> Path:
    return _log_dir() / "log.jsonl"


def _backup_path() -> Path:
    return _log_dir() / "log.jsonl.1"


def _rotate_if_needed(path: Path) -> None:
    """Rename ``path`` to ``log.jsonl.1`` when it grows past the limit.

    The rename is atomic on POSIX filesystems (replaces any existing
    backup), so we never end up with a half-rotated state.
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return
    if size < _MAX_BYTES:
        return
    backup = _backup_path()
    # On POSIX, ``Path.replace`` is atomic and overwrites if the target
    # exists, which is exactly what we want for rotation.
    path.replace(backup)


def log_event(event: dict[str, Any]) -> None:
    """Append one JSON event to the log, rotating the file if needed.

    All errors are swallowed: logging is a best-effort sidecar, never
    a reason to fail the user's request. If the disk is full or the
    cache directory is unwritable, the image generation should still
    succeed.
    """
    try:
        directory = _log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = _log_path()
        _rotate_if_needed(path)
        with path.open("a", encoding="utf-8") as f:
            # ``ensure_ascii=False`` keeps non-Latin prompts (e.g.
            # Russian) readable without \uXXXX escapes.
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # Intentionally silent — see docstring.
        pass
