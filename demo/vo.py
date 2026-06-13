"""AI voiceover for the demo — Microsoft Edge neural TTS (edge-tts), no API key.

A warm, grounded female narrator (see the voice note below). Each script line
is synthesized to its own mp3; compose.py reads the durations to time the
scenes, then lays the clips onto a single track aligned to the cut.

Pure-Python audio helpers (decode / resample via the bundled ffmpeg) live here
too so compose.py can mix music + voice into one wav without a filtergraph.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import wave

import numpy as np
import imageio_ffmpeg

import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")
os.makedirs(AUDIO, exist_ok=True)

# Warm, natural, grounded female voice — a calm expert, lightly wry. Ava is one
# of the newer high-quality multilingual neural voices. Slightly slower than
# default for gravitas.
VOICE = os.environ.get("DEMO_VOICE", "en-US-AvaMultilingualNeural")
RATE = os.environ.get("DEMO_RATE", "-6%")
SR = 44100

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


async def _synth_async(text: str, out_path: str):
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(out_path)


def synth(text: str, out_path: str) -> float:
    """Synthesize one line to mp3; return its duration in seconds."""
    asyncio.run(_synth_async(text, out_path))
    return decode_stereo(out_path).shape[0] / SR


def decode_stereo(path: str) -> np.ndarray:
    """Decode any audio file to float32 stereo at SR via ffmpeg → [n, 2]."""
    cmd = [
        FFMPEG, "-v", "error", "-i", path,
        "-ac", "2", "-ar", str(SR), "-f", "wav", "-",
    ]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout
    # Parse the WAV bytes ffmpeg streamed back.
    import io
    with wave.open(io.BytesIO(raw), "rb") as w:
        n = w.getnframes()
        frames = w.readframes(n)
    a = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if a.size == 0:
        return np.zeros((0, 2), np.float32)
    return a.reshape(-1, 2)


if __name__ == "__main__":
    # Smoke test: synth one line and report its length.
    d = synth("This is whatfirst, small — your to-do list, ranked.", os.path.join(AUDIO, "_smoke.mp3"))
    print(f"voice={VOICE} rate={RATE}  sample line = {d:.2f}s")
