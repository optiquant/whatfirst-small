---
title: whatfirst small
emoji: 🗂️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
models:
  - ggml-org/Qwen2.5-VL-3B-Instruct-GGUF
tags:
  - track:backyard
  - achievement:offgrid
  - achievement:llama
  - achievement:fieldnotes
---

# whatfirst · small

**Dump everything on your mind — get back what to do *first*, with the math shown.**

[**▶ Live demo**](https://huggingface.co/spaces/build-small-hackathon/whatfirst-small) &nbsp;·&nbsp; [📣 Launch post](https://x.com/tbd_ntbd/status/2066222870657692128) &nbsp;·&nbsp; [what-first.com](https://what-first.com) &nbsp;·&nbsp; Apache-2.0

🤏 **3B params** (≤ 4B) &nbsp;·&nbsp; 🔌 **runs 100% offline** — no internet required &nbsp;·&nbsp; 🦙 llama.cpp

A small **local** vision-language model (Qwen2.5-VL-3B, ~2 GB, running on
llama.cpp) reads a messy brain-dump or a photo of a to-do list and turns each
line into a structured task — impact, readiness, effort, deadline. A
**deterministic, transparent scoring engine** then ranks them and tells you the
one thing to start now, showing every number behind the call. No cloud, no API
keys, runs on a laptop.

Built for the [Hugging Face Build Small hackathon](https://huggingface.co/build-small-hackathon)
(Backyard AI track).

📓 **Field notes:** [an honest write-up of what worked and what didn't](submission/whatfirst-small-writeup.md) —
the small-model story, including where a 3B model wobbles and how the design absorbs it.

## Demo

[![Watch the whatfirst-small demo](https://huggingface.co/spaces/build-small-hackathon/whatfirst-small/resolve/main/demo/out/whatfirst-small-demo-poster.jpg)](https://huggingface.co/spaces/build-small-hackathon/whatfirst-small/resolve/main/demo/out/whatfirst-small-demo-loud.mp4)

▶ **[Watch the demo video](https://huggingface.co/spaces/build-small-hackathon/whatfirst-small/resolve/main/demo/out/whatfirst-small-demo-loud.mp4)** &nbsp;·&nbsp; **[Try the live Space](https://huggingface.co/spaces/build-small-hackathon/whatfirst-small)**

<!-- Rendered as a clickable poster + links so the demo works on GitHub (which strips raw <video>)
     and on Hugging Face alike. -->


## Why this exists

Deciding *what to do first* is a real, daily problem — and most "AI to-do" apps
answer it with a black box. This one keeps the AI where it earns its keep (turning
vague human language into structured fields) and makes the prioritization itself
**legible**: two competing scores (do-it-now vs. de-risk-first), an urgency curve
that explodes as a deadline nears, a quick-win boost for short, high-impact tasks, and
deadlines treated as a hard constraint rather than a number folded into a blob.

The problem — and the prioritization approach — come from
**[what-first.com](https://what-first.com)**, a full web app the same team built
in June 2026. There, a frontier cloud model (Claude) does the language work —
reading your tasks and proposing their impact, readiness, and effort — and a
deterministic engine ranks them. This entry asks a smaller question: can a **3B
model running offline on a laptop** do that same language work? The ranking
engine here is a clean-room Python reimplementation with its own tests, not a
copy of the original.

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
  extract, single-task re-score). Each call is grammar-constrained to a JSON
  object; every model output is re-clamped before scoring.
- `prompts.py` — the system prompts that ask for strict-JSON output and define
  the scoring scales.
- `app.py` — the Gradio UI: capture, ranked table, and sliders to correct any
  score and re-rank live.

## Run it locally

```bash
docker build -t whatfirst-small .
docker run -p 7860:7860 whatfirst-small   # first boot downloads ~3.3 GB (model + vision projector)
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
