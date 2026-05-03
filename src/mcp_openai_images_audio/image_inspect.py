"""
Post-generation sanity checks on the saved image file.

Two specific failure modes we want to catch before the caller acts on
the result as if it succeeded:

1. ALPHA MISSING — the user requested a transparent background, but
   the saved file has no alpha channel. This can happen if the upstream
   model silently demoted the request, or if the file was written in a
   format that doesn't support alpha (although our format gate should
   prevent that path).

2. FAKE-CHECKERBOARD — when an LLM is told "make the background
   transparent" but the API only returns RGB, the model sometimes
   *paints* the universal "transparent" checkerboard pattern (gray
   squares) into the RGB pixels themselves, producing an image that
   *looks* transparent in a thumbnail viewer but is actually opaque
   pixels. We detect this with a small heuristic on a corner crop.

Both checks return ``None`` when they don't apply (e.g. JPEG output —
no alpha to ask about, no checkerboard to suspect). Both return
booleans when they do apply. Neither raises; failure to inspect just
means the inspection metadata is omitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# Sample window we read from each corner. Small to keep this fast and
# big enough to count alternating tiles reliably.
_CORNER_PX: int = 32

# Classic checkerboard cell size in image editors is 8 px; we sample
# coarser at 4 px and accept some tolerance so the heuristic isn't
# brittle against minor rendering differences.
_TILE_PX: int = 8

# Tolerance for "this pixel matches the alternating pattern". 0.6 means
# at least 60% of the sampled corner pixels must follow the expected
# light/dark alternation for us to flag it. Empirical — chosen high
# enough not to false-positive on natural gray gradients.
_FAKE_THRESHOLD: float = 0.6


@dataclass(frozen=True)
class ImageInspection:
    """Result of inspecting a freshly-written image.

    All fields are optional; ``None`` means "the question doesn't apply
    to this format / we couldn't determine it". The caller folds the
    populated fields into the tool's response payload.
    """

    has_alpha: bool | None = None
    """True if the image's pixel format includes an alpha channel."""

    alpha_used: bool | None = None
    """True if the alpha channel actually contains non-opaque pixels.

    A PNG can have an alpha channel that's fully 255 — technically
    transparent-capable but visually identical to opaque. This field
    distinguishes "alpha exists" from "alpha is doing something".
    """

    alpha_appears_baked: bool | None = None
    """True if the corners look like the editor 'transparent' checkerboard.

    A signal that the model drew the pattern instead of returning a
    transparent image. Only set when the request asked for transparency
    AND the file turned out to have no real alpha.
    """


def inspect(path: Path, *, requested_transparent: bool) -> ImageInspection:
    """Inspect a saved image; never raises.

    ``requested_transparent`` toggles the fake-checkerboard heuristic:
    we only run it when transparency was asked for and the result
    appears opaque. Otherwise a legitimate gray-tiled image (e.g. an
    actual checkerboard pattern in the subject) would false-positive.
    """
    try:
        with Image.open(path) as img:
            mode = img.mode
            has_alpha = _mode_has_alpha(mode)

            alpha_used: bool | None
            if has_alpha:
                # ``getchannel("A")`` works for any alpha-bearing mode
                # (RGBA, LA, PA). ``getextrema`` is O(pixels) but we
                # only do it once per generation, and it's fast enough
                # not to matter against a multi-second OpenAI call.
                lo, _hi = img.getchannel("A").getextrema()
                alpha_used = lo < 255
            else:
                alpha_used = None

            baked: bool | None
            if requested_transparent and not (has_alpha and alpha_used):
                baked = _looks_like_checkerboard(img)
            else:
                baked = None

            return ImageInspection(
                has_alpha=has_alpha,
                alpha_used=alpha_used,
                alpha_appears_baked=baked,
            )
    except Exception:
        # Inspection is sidecar info; never let a Pillow corner case
        # turn a successful generation into a tool failure.
        return ImageInspection()


def _mode_has_alpha(mode: str) -> bool:
    """Whether a PIL mode string includes an alpha channel.

    Hardcoded list rather than a substring check on "A" because the
    mode language is small, well-defined, and stable; a substring
    check would false-positive on, e.g., ``"LAB"``.
    """
    return mode in {"RGBA", "LA", "PA", "RGBa", "La"}


def _looks_like_checkerboard(img: Image.Image) -> bool:
    """Heuristic: does the upper-left corner alternate light/dark tiles?

    We grayscale a 32x32 corner crop and ask: when split into 8x8
    tiles, do mean luminances alternate light-dark-light-dark in a
    checker pattern? The classic editor checkerboard is white +
    light gray, so means around 255 and ~204; we use a midpoint
    cutoff at 230 and require >60% tile-agreement.

    This is intentionally specific to the "fake checkerboard" trap.
    Natural images very rarely tile in an alternating brightness
    pattern at this exact scale.
    """
    try:
        # Always sample top-left; sampling all four corners would be
        # more thorough but in practice the model paints the same
        # pattern across the whole background, so one corner suffices.
        crop = img.convert("L").crop((0, 0, _CORNER_PX, _CORNER_PX))
    except Exception:
        return False

    tiles_per_side = _CORNER_PX // _TILE_PX
    cutoff = 230  # see docstring

    matches = 0
    total = 0
    for ty in range(tiles_per_side):
        for tx in range(tiles_per_side):
            tile = crop.crop(
                (
                    tx * _TILE_PX,
                    ty * _TILE_PX,
                    (tx + 1) * _TILE_PX,
                    (ty + 1) * _TILE_PX,
                )
            )
            # ``Image.getextrema`` returns (min, max) for L mode; the
            # mean we want for tile classification is approximated
            # well by averaging the two — exact pixel mean would need
            # a numpy import we'd rather avoid for one heuristic.
            lo, hi = tile.getextrema()
            mean = (lo + hi) / 2

            # Expected pattern: tile (tx+ty) even -> light, odd -> dark.
            expected_light = (tx + ty) % 2 == 0
            actual_light = mean >= cutoff

            if expected_light == actual_light:
                matches += 1
            total += 1

    if total == 0:
        return False
    return (matches / total) >= _FAKE_THRESHOLD
