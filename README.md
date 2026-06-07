---
title: whatfirst small
emoji: 🗂️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# whatfirst · small

**Dump everything on your mind — get back what to do *first*, with the math shown.**

A small **local** vision-language model (Qwen2.5-VL-3B, ~2 GB, running on
llama.cpp) reads a messy brain-dump or a photo of a to-do list and turns each
line into a structured task — impact, readiness, effort, deadline. A
**deterministic, transparent scoring engine** then ranks them and tells you the
one thing to start now, showing every number behind the call. No cloud, no API
keys, runs on a laptop.

Built for the [Hugging Face Build Small hackathon](https://huggingface.co/build-small-hackathon)
(Backyard AI track).

## Why this exists

Deciding *what to do first* is a real, daily problem — and most "AI to-do" apps
answer it with a black box. This one keeps the AI where it earns its keep (turning
vague human language into structured fields) and makes the prioritization itself
**legible**: two competing scores (do-it-now vs. de-risk-first), an urgency curve
that explodes as a deadline nears, a quick-win boost for short ready tasks, and
deadlines treated as a hard constraint rather than a number folded into a blob.

The problem, and the scoring model, come from
**[what-first.com](https://what-first.com)** — a full web app the same team built
in June 2026, where the scoring runs server-side against Claude. This entry is a
fresh, **offline, small-model** take built for the hackathon: can a 3B model on a
laptop do the load-bearing language work that a frontier cloud model does in the
product? The ranking engine here is a clean-room reimplementation in Python with
its own tests — no dependency on the original.

## How it works

```
brain-dump / photo  ──▶  Qwen2.5-VL-3B (llama.cpp, localhost)  ──▶  structured tasks
                                                                          │
                                                              score.py (deterministic)
                                                                          │
                                                          ranked list + "do this first"
```

- `score.py` — the scoring + deadline-ranking engine (pure standard-library math).
- `llm.py` — client for the local llama.cpp server (brain-dump parse, image
  extract, single-task re-score). Every model output is re-clamped before scoring.
- `prompts.py` — the system prompts that pin the model to strict JSON.
- `app.py` — the Gradio UI: capture, ranked table, and sliders to correct any
  score and re-rank live.

## Run it locally

```bash
docker build -t whatfirst-small .
docker run -p 7860:7860 whatfirst-small   # first boot downloads ~2.3 GB of weights
```

Then open http://localhost:7860. On a CPU-only box, expect a few seconds per task
— that's the cost of staying fully on the grid-less side. Tests:

```bash
python -m pytest test_score.py    # or: python test_score.py
```

## Notes

- **Model:** [`ggml-org/Qwen2.5-VL-3B-Instruct-GGUF`](https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF)
  (Q4_K_M + f16 mmproj), ≤ 32B and laptop-runnable.
- **Off the grid:** all inference is local llama.cpp over localhost; nothing
  leaves the box at runtime.
