---
title: "whatfirst · small — what to do first, on a 3B model, fully offline"
thumbnail: /blog/assets/whatfirst-small/thumbnail.jpg
authors:
- user: optiquant
date: June 13, 2026
tags:
- hackathon
- build-small-hackathon
- local-first
- llama-cpp
- gradio
---

# whatfirst · small — what to do first, on a 3B model, fully offline

**Dump everything on your mind — get back what to do _first_, with the math shown.** No cloud, no API keys, runs on a laptop.

<!-- Build Small hackathon · Backyard AI track -->

<gradio-app src="https://build-small-hackathon-whatfirst-small.hf.space"></gradio-app>

> Live Space: [build-small-hackathon/whatfirst-small](https://huggingface.co/spaces/build-small-hackathon/whatfirst-small)

## The problem

Deciding _what to do first_ is a real, daily problem — and most "AI to-do" apps answer it with a black box. You get a reordered list and no idea why. The whole category bet on opaque intelligence and lost the one axis that actually builds trust: _I understand why this is at the top._

whatfirst keeps the AI where it earns its keep — turning vague human language into structured fields — and makes the **prioritization itself legible**: two competing scores, an urgency curve that explodes as a deadline nears, a quick-win boost for short ready tasks, and deadlines treated as a hard constraint rather than a number folded into a blob.

## The small question

The problem — and the approach — come from **[what-first.com](https://what-first.com)**, a full web app the same team built in June 2026. There, a frontier cloud model (Claude) does the language work — reading your tasks and proposing their impact, readiness, and effort — and a deterministic engine ranks them.

This entry asks a smaller question:

> **Can a 3B model running offline on a laptop do that same language work?**

The ranking engine here is a clean-room Python reimplementation with its own tests — not a copy of the original — so the only variable being tested is the model.

## How it works

```
brain-dump / photo  ──▶  Qwen2.5-VL-3B (llama.cpp, localhost)  ──▶  structured tasks
                                                                          │
                                                              score.py (deterministic)
                                                                          │
                                                          ranked list + "do this first"
```

- **`llm.py`** — client for the local llama.cpp server (brain-dump parse, image extract, single-task re-score). Every model output is treated as untrusted: parsed tolerantly, then **re-clamped to its domain** before it reaches the scorer.
- **`score.py`** — the scoring + deadline-ranking engine. Pure standard-library math, fully deterministic.
- **`prompts.py`** — the system prompts that pin the model to strict JSON.
- **`app.py`** — the Gradio UI: capture, ranked table, and sliders to correct any score and re-rank live.

## The model

[`ggml-org/Qwen2.5-VL-3B-Instruct-GGUF`](https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF) (Q4_K_M weights + f16 mmproj) — ≤ 32B and laptop-runnable. One model serves all three flows over an OpenAI-compatible llama.cpp `llama-server`, including the vision path: snap a photo of a sticky-note pile and the same model reads it.

## The part that isn't AI: a scoring engine you can read

The model's job ends at structured fields. The ranking is deterministic, and **every number is shown on screen**. Two scores compete and the higher one displays:

- **do** = `(Impact · Urgency · Readiness_eff · QuickWin) / 10` — the case for doing it now.
- **prep** = `(Impact · Urgency · (10 − Readiness)) / 10 · 0.7 · QuickWin` — the case for de-risking it first (wins only when a task is valuable but not ready).

**Urgency** climbs as a deadline nears and _explodes_ once it's within a day, so a looming deadline can't be buried by a shiny far-off task. **QuickWin** rewards short, high-impact tasks. And deadlines act as a **constraint**, not just a term: anything overdue, or that genuinely won't finish in time given everything ahead of it, is lifted above the value pack.

Disagree with a score? Drag a slider and the list **re-ranks live** — the model proposes, you decide.

## Demo

<video
  controls
  width="100%"
  poster="https://huggingface.co/spaces/build-small-hackathon/whatfirst-small/resolve/main/demo/out/whatfirst-small-demo-poster.jpg"
  src="https://huggingface.co/spaces/build-small-hackathon/whatfirst-small/resolve/main/demo/out/whatfirst-small-demo-loud.mp4">
</video>

## Merit badges

**🔌 Off the Grid.** All inference is local llama.cpp over localhost. Nothing leaves the box at runtime — no cloud, no API keys. Your to-do list, including a photo of it, never travels.

**🦙 Llama Champion.** The whole language stack is a llama.cpp `llama-server`, built from source in the container, serving a Qwen2.5-VL GGUF (text **and** vision) behind an OpenAI-compatible API.

**📓 Field Notes.** This write-up — including the honest part below.

## What worked, and what didn't

**Worked:** The deterministic engine is the easy hero — it's instant, transparent, and identical to the production logic it reimplements; `test_score.py` keeps it honest. Treating every model output as untrusted and **re-clamping before scoring** turned out to be the load-bearing design decision: even when the 3B model returns a wobbly number or a malformed date, the score can never go NaN or out of range.

**Didn't, or only just:** A 3B model is not Claude. It mis-reads the occasional relative date ("next Wednesday") and gets jittery on effort estimates — the re-clamp and the editable sliders exist partly to absorb that. And **CPU inference is slow**: on a free CPU Space, expect a few seconds per task, and the vision path is heavier still (Qwen2.5-VL's dynamic resolution turns a screenshot into thousands of vision tokens, so the longest image edge is capped before encoding). That's the honest cost of staying fully on the grid-less side — and it's exactly the tradeoff the "small" question was meant to surface.

## Try it

- **Space:** [build-small-hackathon/whatfirst-small](https://huggingface.co/spaces/build-small-hackathon/whatfirst-small)
- **Model:** [ggml-org/Qwen2.5-VL-3B-Instruct-GGUF](https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF)
- **The full app this comes from:** [what-first.com](https://what-first.com)

Stop deciding. Start doing.
