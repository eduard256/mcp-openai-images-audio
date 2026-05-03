"""
Smoke tests for the path validation module.

These are deliberately offline — they don't touch OpenAI, the
filesystem outside of pytest's tmp_path, or any network. If they pass,
the strict-path contract from the design discussion is intact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_openai_images_audio.paths import (
    output_format_from_path,
    validate_output_path,
    validate_references,
)


def test_relative_output_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        validate_output_path("relative/path.png")


def test_unsupported_extension_rejected(tmp_path: Path) -> None:
    target = tmp_path / "weird.gif"
    with pytest.raises(ValueError, match="Unsupported extension"):
        validate_output_path(str(target))


def test_missing_parent_directory_rejected(tmp_path: Path) -> None:
    target = tmp_path / "does-not-exist" / "img.png"
    with pytest.raises(ValueError, match="Parent directory does not exist"):
        validate_output_path(str(target))


def test_existing_file_rejected(tmp_path: Path) -> None:
    target = tmp_path / "img.png"
    target.write_bytes(b"")
    with pytest.raises(ValueError, match="already exists"):
        validate_output_path(str(target))


def test_happy_path_returns_resolved_path(tmp_path: Path) -> None:
    target = tmp_path / "ok.png"
    result = validate_output_path(str(target))
    assert result == target
    assert result.is_absolute()


def test_format_inferred_from_extension(tmp_path: Path) -> None:
    assert output_format_from_path(tmp_path / "x.png") == "png"
    assert output_format_from_path(tmp_path / "x.webp") == "webp"
    assert output_format_from_path(tmp_path / "x.jpg") == "jpeg"
    assert output_format_from_path(tmp_path / "x.JPEG") == "jpeg"


def test_empty_references_returns_empty_list() -> None:
    assert validate_references(None) == []
    assert validate_references([]) == []


def test_relative_reference_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        validate_references(["ref.png"])


def test_missing_reference_rejected(tmp_path: Path) -> None:
    target = tmp_path / "missing.png"
    with pytest.raises(ValueError, match="does not exist"):
        validate_references([str(target)])


def test_too_many_references_rejected(tmp_path: Path) -> None:
    paths = []
    for i in range(17):
        p = tmp_path / f"ref{i}.png"
        p.write_bytes(b"")
        paths.append(str(p))
    with pytest.raises(ValueError, match="Too many references"):
        validate_references(paths)


def test_unsupported_reference_extension_rejected(tmp_path: Path) -> None:
    target = tmp_path / "ref.bmp"
    target.write_bytes(b"")
    with pytest.raises(ValueError, match="Unsupported reference extension"):
        validate_references([str(target)])
