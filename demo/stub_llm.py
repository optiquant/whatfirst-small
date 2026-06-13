"""A drop-in stand-in for the real ``llm`` module.

``capture.py`` registers this under the name ``llm`` *before* importing ``app``,
so the genuine Gradio UI runs with no llama.cpp server: ``is_ready`` is always
true and the parse/score flows return the deterministic ``seed`` data instantly.
Only the backend is faked — every pixel captured is the real app.
"""

from __future__ import annotations

import copy

import seed


def is_ready() -> bool:
    return True


def parse_braindump(text: str) -> list[dict]:
    # The on-screen brain-dump text is ignored; we return the canned parse of it.
    return copy.deepcopy(seed.build_tasks())


def extract_from_image(image) -> list[dict]:
    return copy.deepcopy(seed.build_tasks())


def score_task(title: str, notes: str = "", category: str = "") -> dict | None:
    return dict(seed.SCORE_SUGGEST)
