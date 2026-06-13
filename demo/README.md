# Demo video

A narrated ~88s demo of whatfirst-small, generated from the **real Gradio UI**
(genuine pixels — only the model is stubbed with deterministic data) and
composed into a captioned, Ken-Burns video over a self-generated jazz bed, with
an **AI voiceover** baked in.

The structure mirrors the [what-first.com](https://what-first.com) demo: a
brand-tinted canvas, a bold narrator caption above the app, and a single clean
rounded video box with a slow push-in toward a per-scene focal point.

Output: `out/whatfirst-small-demo.mp4` (+ `-poster.jpg`), 720p H.264 + AAC.

## Voice & captions

The narration is synthesized by `vo.py` using **edge-tts** (Microsoft neural
TTS, no API key) — a warm, grounded female voice (`en-US-AvaMultilingualNeural`,
overridable via `DEMO_VOICE`). Each scene's spoken line sets that scene's
on-screen duration, so the captions, the push-in, and the voice stay in lockstep.

The music is `music.py` — a warm, mellow minor-key jazz trio (deep walking bass,
soft piano comping, brushed swing, a Rhodes-ish melody), ducked under the voice;
self-generated and royalty-free.

## Regenerate

```bash
pip install playwright imageio-ffmpeg edge-tts Pillow numpy "gradio>=5.8,<6"
python -m playwright install chromium

python capture.py     # launch the stubbed Gradio app, screenshot scenes -> shots/
python music.py       # -> audio/bed.wav
python compose.py     # synth VO, mix, render -> out/whatfirst-small-demo.mp4
```

- `seed.py` — the deterministic structured tasks a good parse of the app's own
  sample brain-dump would yield (every value invented).
- `stub_llm.py` — a drop-in `llm` so the genuine UI runs with no llama.cpp
  server; only the model is faked, every captured pixel is the real app.
- `capture.py` — serves the app, walks the flow (paste → prioritize → correct a
  score & watch it re-rank → open the formula), one PNG per scene.
- `vo.py` — neural voiceover + the audio decode/mix helpers.
- `compose.py` — owns the cut: scene list, captions, focal points, the music +
  voice mix, and the final encode.

`shots/`, `audio/`, `out/` and `_frames/` are regenerable and git-ignored.
