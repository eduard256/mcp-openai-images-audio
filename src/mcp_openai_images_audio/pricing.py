"""
Cost estimation for gpt-image-2 calls.

OpenAI bills image generation as token usage rather than per-image, so
we have to convert the ``usage`` block returned by the API into a USD
estimate. Prices below match OpenAI's published pricing as of the time
this file was written; if OpenAI changes them, the numbers here go
stale silently — that's why the tool's response calls the field
``estimated_cost_usd`` (emphasis on "estimated").

This module has zero runtime dependencies and is trivially testable.
"""

from __future__ import annotations

from typing import TypedDict

# All prices are per 1 million tokens, USD. These match the pricing page
# for gpt-image-2 (https://openai.com/api/pricing/) at version time.
PRICE_TEXT_INPUT_PER_1M: float = 5.00
PRICE_IMAGE_INPUT_PER_1M: float = 8.00
PRICE_IMAGE_INPUT_CACHED_PER_1M: float = 2.00
PRICE_IMAGE_OUTPUT_PER_1M: float = 30.00


class _UsageInputDetails(TypedDict, total=False):
    text_tokens: int
    image_tokens: int
    cached_tokens: int


class _UsageOutputDetails(TypedDict, total=False):
    text_tokens: int
    image_tokens: int


class Usage(TypedDict, total=False):
    """Shape of the ``usage`` field in an OpenAI image response.

    All fields are optional because OpenAI may omit ones that don't
    apply to a given call (e.g. no ``image_tokens`` on a pure
    text-to-image generation).
    """

    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_tokens_details: _UsageInputDetails
    output_tokens_details: _UsageOutputDetails


def estimate_cost_usd(usage: Usage | None) -> float:
    """Estimate the call cost in USD from a usage payload.

    Returns ``0.0`` when no usage was reported (some legacy responses
    omit it entirely). Otherwise breaks the input/output token counts
    into their text/image/cached buckets and applies the published
    per-million rates.

    The result is rounded to four decimal places — that's the precision
    OpenAI's own dashboard displays, and finer numbers are noise given
    the published prices already round to whole cents.
    """
    if not usage:
        return 0.0

    input_details = usage.get("input_tokens_details", {}) or {}
    output_details = usage.get("output_tokens_details", {}) or {}

    text_in = input_details.get("text_tokens", 0)
    image_in = input_details.get("image_tokens", 0)
    cached_in = input_details.get("cached_tokens", 0)
    image_out = output_details.get("image_tokens", 0)

    cost = (
        text_in * PRICE_TEXT_INPUT_PER_1M
        + image_in * PRICE_IMAGE_INPUT_PER_1M
        + cached_in * PRICE_IMAGE_INPUT_CACHED_PER_1M
        + image_out * PRICE_IMAGE_OUTPUT_PER_1M
    ) / 1_000_000.0

    return round(cost, 4)
