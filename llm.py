"""Local model client.

Talks to a llama.cpp `llama-server` running on localhost (OpenAI-compatible
`/v1/chat/completions`, with multimodal support for the Qwen2.5-VL GGUF). One
model serves all three flows. No network leaves the box — this is the
"off the grid" path.

Every model response is treated as untrusted: parsed tolerantly, then every
field is re-clamped to its domain before it reaches score.py.
"""

from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime

import requests

LLAMA_BASE_URL = os.environ.get("LLAMA_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
CHAT_URL = f"{LLAMA_BASE_URL}/v1/chat/completions"
REQUEST_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "240"))  # CPU inference is slow

from prompts import (
    PARSE_SYSTEM_PROMPT, build_parse_user,
    EXTRACT_SYSTEM_PROMPT, EXTRACT_USER_PROMPT,
    SCORE_SYSTEM_PROMPT, build_score_user,
)


# -- server plumbing ----------------------------------------------------------

def is_ready() -> bool:
    """Has the model server come up and loaded weights?"""
    try:
        r = requests.get(f"{LLAMA_BASE_URL}/health", timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _chat(system: str, user_content, max_tokens: int) -> str:
    """One chat completion that is constrained to return a single JSON object.
    `user_content` is a string or an OpenAI content-parts list (for images).

    Note on JSON coercion: the cloud app (what-first.com) prefills the assistant
    turn with '{' and lets Claude continue it. llama.cpp's chat endpoint does NOT
    continue a trailing assistant turn — it generates a fresh, complete object —
    so that prefill produced a doubled leading brace and every parse failed.
    Instead we use llama.cpp's `response_format: json_object`, which applies a
    grammar at sampling time: the model literally cannot emit prose, markdown
    fences, or an unbalanced object."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "top_p": 0.9,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(CHAT_URL, json=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _read_balanced(text: str, start: int) -> tuple[str | None, int]:
    """Read one string-aware balanced {...} starting at text[start] == '{'.
    Returns (substring, end_index_exclusive), or (None, len) if it never closes
    (the object was truncated, e.g. the model hit max_tokens mid-write)."""
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1], i + 1
    return None, len(text)


def _recover_items(text: str) -> list:
    """Salvage every complete object inside an `"items": [ ... ]` array when the
    whole response can't be parsed (truncated final item, stray trailing token).
    A single cut-off task shouldn't void an otherwise-good batch."""
    key = text.find('"items"')
    if key == -1:
        return []
    i = text.find("[", key)
    if i == -1:
        return []
    items: list = []
    n = len(text)
    while i < n:
        if text[i] == "]":
            break
        if text[i] == "{":
            obj, end = _read_balanced(text, i)
            if obj is None:
                break  # truncated final object — stop, keep what we have
            try:
                items.append(json.loads(obj))
            except json.JSONDecodeError:
                pass
            i = end
        else:
            i += 1
    return items


def _extract_json(text: str) -> dict:
    """Parse the model's JSON object. Output is grammar-constrained to a clean
    object, so the fast path almost always wins; the fallbacks only matter if a
    response is truncated at max_tokens."""
    text = text.strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start != -1:
        obj_str, _ = _read_balanced(text, start)
        if obj_str is not None:
            try:
                parsed = json.loads(obj_str)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    # Truncated mid-array: recover whatever complete items survived.
    return {"items": _recover_items(text)}


# -- validation ---------------------------------------------------------------

def _clamp_int(v, lo, hi):
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def _clamp_num(v, lo, hi):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return max(lo, min(hi, n))


def _str_or_none(v, n):
    if not isinstance(v, str):
        return None
    s = v.strip()[:n]
    return s or None


def _due_iso(date_v, time_v):
    """Combine a model-proposed YYYY-MM-DD (+ optional HH:MM) into the ISO form
    score.py expects, or None. Garbage shapes are dropped, not guessed."""
    import re
    if not isinstance(date_v, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_v.strip()):
        return None
    date = date_v.strip()
    if isinstance(time_v, str) and re.match(r"^([01]\d|2[0-3]):[0-5]\d$", time_v.strip()):
        return f"{date}T{time_v.strip()}:00"
    return date  # score.py normalizes a bare date to 17:00


def _sanitize_scored(raw: dict, idx: int) -> dict | None:
    """A fully-scored item from PARSE: title + scores + optional due."""
    title = _str_or_none(raw.get("title"), 90)
    if not title:
        return None
    impact = _clamp_int(raw.get("impact"), 1, 10)
    readiness = _clamp_int(raw.get("readiness"), 1, 10)
    effort = _clamp_num(raw.get("effort_hours"), 0.05, 200)
    return {
        "id": f"t{idx}",
        "title": title,
        "category": _str_or_none(raw.get("category"), 80),
        "notes": _str_or_none(raw.get("notes"), 400),
        "due_date": _due_iso(raw.get("due_date"), raw.get("due_time")),
        "impact": impact if impact is not None else 5,
        "readiness": readiness if readiness is not None else 8,
        "effort_hours": effort if effort is not None else 1.0,
        "reason": _str_or_none(raw.get("reason"), 200) or "",
        "completed": False,
    }


def _sanitize_titleonly(raw: dict) -> dict | None:
    """An unscored item from EXTRACT: title + context only."""
    title = _str_or_none(raw.get("title"), 90)
    if not title:
        return None
    return {
        "title": title,
        "category": _str_or_none(raw.get("category"), 80),
        "notes": _str_or_none(raw.get("notes"), 400),
    }


# -- flows --------------------------------------------------------------------

def parse_braindump(text: str) -> list[dict]:
    """Free-text brain-dump -> fully scored, ready-to-rank task dicts."""
    if not text or not text.strip():
        return []
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday = now.strftime("%A")
    out = _chat(PARSE_SYSTEM_PROMPT, build_parse_user(text, today, weekday), max_tokens=1800)
    items = _extract_json(out).get("items", [])
    if not isinstance(items, list):
        return []
    scored = [_sanitize_scored(it, i) for i, it in enumerate(items[:25])]
    return [s for s in scored if s]


def score_task(title: str, notes: str = "", category: str = "") -> dict | None:
    """Re-score a single task (used by the slider 'suggest' button)."""
    out = _chat(SCORE_SYSTEM_PROMPT, build_score_user(title, notes, category), max_tokens=200)
    raw = _extract_json(out)
    impact = _clamp_int(raw.get("impact"), 1, 10)
    readiness = _clamp_int(raw.get("readiness"), 1, 10)
    effort = _clamp_num(raw.get("effort_hours"), 0.05, 200)
    if impact is None or readiness is None or effort is None:
        return None
    return {
        "impact": impact,
        "readiness": readiness,
        "effort_hours": effort,
        "reason": _str_or_none(raw.get("reason"), 200) or "",
    }


def extract_from_image(image) -> list[dict]:
    """Photo of a list -> scored task dicts. Two calls: a vision pass pulls the
    titles, then the text scorer scores them in one batch (keeps it to one
    model, and the scorer is more reliable on text than the VLM head is)."""
    if image is None:
        return []
    b64 = _png_b64(image)
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        {"type": "text", "text": EXTRACT_USER_PROMPT},
    ]
    out = _chat(EXTRACT_SYSTEM_PROMPT, content, max_tokens=1024)
    raw_items = _extract_json(out).get("items", [])
    if not isinstance(raw_items, list):
        return []
    titles = [_sanitize_titleonly(it) for it in raw_items[:20]]
    titles = [t for t in titles if t]
    if not titles:
        return []
    # Score the extracted titles in one pass by feeding them as a brain-dump.
    dump = "\n".join(
        f"{t['title']}" + (f" — {t['notes']}" if t.get("notes") else "")
        for t in titles
    )
    return parse_braindump(dump)


# Cap the longest image edge before sending to the vision encoder. Qwen2.5-VL
# uses dynamic resolution, so a full-size screenshot becomes thousands of vision
# tokens — murder on a CPU-only box. ~1280px keeps a task list readable while
# cutting vision tokens (and prefill time) several-fold. Tunable via env.
MAX_IMAGE_EDGE = int(os.environ.get("MAX_IMAGE_EDGE", "1280"))


def _png_b64(image) -> str:
    image = image.convert("RGB")
    longest = max(image.size)
    if longest > MAX_IMAGE_EDGE:
        scale = MAX_IMAGE_EDGE / longest
        new_size = (round(image.width * scale), round(image.height * scale))
        from PIL import Image  # local import: only the image flow needs it
        image = image.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
