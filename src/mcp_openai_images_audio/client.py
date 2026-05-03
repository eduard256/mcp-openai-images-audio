"""
Thin async wrapper around the OpenAI Python SDK.

This module centralizes:
- API key discovery (env var, with a clear error message)
- a single shared ``AsyncOpenAI`` instance per process
- the two endpoints we actually call (``images.generate`` and
  ``images.edit``)
- model selection: gpt-image-2 by default, with an automatic fallback
  to gpt-image-1.5 when transparency is requested (gpt-image-2 does
  not currently support transparent backgrounds — confirmed regression
  documented in OpenAI's API guide and community threads, with no
  announced timeline for restoration).

Both ``generate`` and ``edit`` return a ``(response, model_used)``
tuple so the caller can record the actually-invoked model in its
metadata payload, which matters because the model is not always the
flagship — see the transparency fallback above.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

# The two models we route between.
# ``FLAGSHIP`` is the default. ``ALPHA_CAPABLE`` is the only model in
# the gpt-image family that currently honors background='transparent'.
FLAGSHIP_MODEL: str = "gpt-image-2"
ALPHA_CAPABLE_MODEL: str = "gpt-image-1.5"


def pick_model(background: str) -> str:
    """Choose the OpenAI model based on the requested background.

    gpt-image-2 rejects ``background='transparent'`` with a 400 right
    now (regression vs. gpt-image-1.5). To keep transparency working
    end-to-end without exposing this rough edge to the caller, we
    silently fall back to gpt-image-1.5 in that case. Every other
    request uses the flagship.
    """
    if background == "transparent":
        return ALPHA_CAPABLE_MODEL
    return FLAGSHIP_MODEL


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    """Return the process-wide ``AsyncOpenAI`` client.

    Lazy + cached so that:
    - importing this module does not require ``OPENAI_API_KEY`` to
      be set (handy for tests and ``--help`` invocations);
    - the underlying httpx connection pool is reused across all
      concurrent tool calls.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Pass it via `claude mcp add ... -e OPENAI_API_KEY=sk-...` "
            "or export it in your shell."
        )
    return AsyncOpenAI(api_key=api_key)


async def generate(
    *,
    prompt: str,
    size: str,
    output_format: str,
    quality: str | None,
    background: str,
) -> tuple[Any, str]:
    """Call ``/v1/images/generations``.

    Returns ``(response, model_used)``. The model is not echoed in
    the OpenAI response payload itself, so the caller has to learn
    it from us.
    """
    model = pick_model(background)
    kwargs: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "output_format": output_format,
        "background": background,
        "moderation": "low",
        "n": 1,
    }
    # ``quality`` is "absent => let OpenAI decide (auto)". Sending
    # the string "auto" works too, but omitting matches the documented
    # default and stays robust if their default policy ever shifts.
    if quality is not None:
        kwargs["quality"] = quality

    response = await _client().images.generate(**kwargs)
    return response, model


async def edit(
    *,
    prompt: str,
    references: list[Path],
    size: str,
    output_format: str,
    quality: str | None,
    background: str,
    input_fidelity: str | None,
) -> tuple[Any, str]:
    """Call ``/v1/images/edits``.

    Returns ``(response, model_used)``. We always pass references as
    a list (even when there's just one) — the SDK accepts that shape
    in both cases, which keeps the call site uniform.
    """
    model = pick_model(background)
    open_files = [path.open("rb") for path in references]
    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "image": open_files,
            "size": size,
            "output_format": output_format,
            "background": background,
            "moderation": "low",
            "n": 1,
        }
        if quality is not None:
            kwargs["quality"] = quality
        if input_fidelity is not None:
            kwargs["input_fidelity"] = input_fidelity

        response = await _client().images.edit(**kwargs)
        return response, model
    finally:
        # The SDK reads file contents during the call, so by now every
        # handle has been consumed — but we still close defensively
        # to avoid leaking fds on an exception mid-flight.
        for f in open_files:
            try:
                f.close()
            except Exception:
                pass
