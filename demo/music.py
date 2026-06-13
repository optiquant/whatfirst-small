"""Synthesize a warm, mellow, *minor-key* jazz bed for the demo video — numpy
only, self-generated and royalty-free (adapted from the what-first.com demo
pipeline). Designed to medium-swing conventions so it grooves without getting
bright or repetitive:

  • Key of C minor with a brief lift to the relative major (Eb / Ab) — a 16-bar
    form, so the obvious short loop is gone.
  • Deep walking upright bass + soft piano comping, both low in the register.
  • A light brushed swing beat (feathered kick, brushed backbeat, soft ride).
  • A warm Rhodes-ish melody and a quiet background arpeggio riff.
  • ~124 BPM and a hard treble rolloff (~4.3 kHz) so nothing reads as tinny.

Renders one cut sized to cover the demo:
    demo/audio/bed.wav
"""

import os
import wave
import struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "audio")
os.makedirs(OUT, exist_ok=True)

SR = 44100
BPM = 124.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
SWING = 0.6

VOICING = {"m9": [3, 7, 10, 14], "maj9": [4, 7, 11, 14],
           "7b9": [4, 10, 13], "m7b5": [3, 6, 10]}
TONES = {"m9": [0, 3, 7, 10], "maj9": [0, 4, 7, 11],
         "7b9": [0, 4, 7, 10], "m7b5": [0, 3, 6, 10]}

FORM = [
    (0, "m9"), (0, "m9"), (5, "m9"), (5, "m9"),
    (2, "m7b5"), (7, "7b9"), (0, "m9"), (0, "m9"),
    (3, "maj9"), (3, "maj9"), (8, "maj9"), (8, "maj9"),
    (5, "m9"), (7, "7b9"), (0, "m9"), (7, "7b9"),
]
COMP_SLOTS = [0, 3, 6]

MELODY = {
    0: [(0, 67, 1.5), (3, 63, 1.0)],
    2: [(0, 68, 1.0), (2, 65, 1.2)],
    4: [(0, 62, 1.0)],
    5: [(2, 68, 0.8), (5, 67, 0.8)],
    6: [(0, 63, 2.0)],
    8: [(0, 70, 1.5), (3, 67, 1.0)],
    10: [(0, 68, 1.5), (3, 65, 1.0)],
    12: [(0, 68, 1.0), (2, 67, 1.0)],
    13: [(0, 67, 1.0), (2, 71, 1.0)],
    14: [(0, 63, 2.0)],
}


def hz(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def eighth_time(bar, slot):
    beat = slot // 2
    off = (slot % 2) * SWING
    return bar * BAR + (beat + off) * BEAT


def fft_lowpass(x, cutoff, width=0.5):
    n = len(x)
    if n < 16:
        return x
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    lo, hi = cutoff * (1 - width), cutoff * (1 + width)
    gain = np.ones_like(f)
    band = (f >= lo) & (f <= hi)
    gain[band] = 0.5 * (1 + np.cos(np.pi * (f[band] - lo) / (hi - lo)))
    gain[f > hi] = 0.0
    return np.fft.irfft(X * gain, n=n)


def voice(root_pc, quality):
    out = []
    for iv in VOICING[quality]:
        m = root_pc + iv
        while m < 50:
            m += 12
        while m >= 62:
            m -= 12
        out.append(m)
    return sorted(set(out))


def walk(root_pc, next_pc, quality):
    broot = 24 + (root_pc % 12)
    fifth = broot + 7
    octave = broot + 12
    approach = (24 + (next_pc % 12)) - 1
    if approach < 24:
        approach += 12
    return [broot, fifth, octave, approach]


def piano(freq, dur, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.zeros(n)
    for k in range(1, 6):
        fk = freq * k
        if fk > SR / 2:
            break
        tone += (0.6 ** (k - 1)) * np.sin(2 * np.pi * fk * t)
    env = np.exp(-t / (0.5 + 0.5 * np.exp(-freq / 200))) * np.minimum(1.0, t / 0.006)
    return tone * env * vel


def rhodes(freq, dur, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.26 * np.sin(2 * np.pi * 2 * freq * t)
    trem = 1 + 0.07 * np.sin(2 * np.pi * 5 * t)
    env = np.exp(-t / 0.95) * np.minimum(1.0, t / 0.01)
    return tone * env * trem * vel


def bass(freq, dur, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * freq * t)
            + 0.42 * np.sin(2 * np.pi * 2 * freq * t)
            + 0.16 * np.sin(2 * np.pi * 3 * freq * t))
    env = np.exp(-t / 0.62) * np.minimum(1.0, t / 0.008)
    return tone * env * vel


def kick(dur=0.22, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    pitch = 50 + 40 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(pitch) / SR) * np.exp(-t * 12) * vel


def brush(dur, vel=1.0, seed=1):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(seed).standard_normal(n)
    return fft_lowpass(noise, 2000) * np.exp(-t * 17) * vel


def ride(dur=0.18, vel=1.0, seed=1):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(seed).standard_normal(n)
    return fft_lowpass(noise, 3000) * np.exp(-t * 22) * vel


def render(n_bars, out_path):
    n = int(round(n_bars * BAR * SR)) + int(0.8 * SR)
    L = np.zeros(n)
    R = np.zeros(n)

    def add(buf, start_s, sig, gain=1.0):
        s = int(start_s * SR)
        e = min(len(buf), s + len(sig))
        if 0 <= s < len(buf) and e > s:
            buf[s:e] += sig[: e - s] * gain

    for bar in range(int(np.ceil(n_bars))):
        idx = bar % len(FORM)
        root_pc, qual = FORM[idx]
        nxt_pc = FORM[(idx + 1) % len(FORM)][0]
        vch = voice(root_pc, qual)

        for beat, m in enumerate(walk(root_pc, nxt_pc, qual)):
            b = bass(hz(m), BEAT * 0.95, vel=0.55)
            t0 = bar * BAR + beat * BEAT
            add(L, t0, b, 0.95); add(R, t0, b, 0.95)

        for slot in range(8):
            m = vch[slot % len(vch)]
            a = piano(hz(m), 0.32, vel=0.14)
            t0 = eighth_time(bar, slot)
            add(L, t0, a, 0.7 if slot % 2 else 0.5)
            add(R, t0, a, 0.5 if slot % 2 else 0.7)

        for slot in COMP_SLOTS:
            t0 = eighth_time(bar, slot)
            for j, m in enumerate(vch):
                p = piano(hz(m), 0.7, vel=0.32 - 0.03 * j)
                add(L, t0, p, 0.9); add(R, t0, p, 0.85)

        for slot, m, beats in MELODY.get(idx, []):
            r = rhodes(hz(m), beats * BEAT, vel=0.5)
            t0 = eighth_time(bar, slot)
            add(L, t0, r, 0.95); add(R, t0, r, 0.9)

        add(L, bar * BAR, kick(vel=0.5)); add(R, bar * BAR, kick(vel=0.5))
        add(L, bar * BAR + 2 * BEAT, kick(vel=0.3)); add(R, bar * BAR + 2 * BEAT, kick(vel=0.3))
        for beat in (1, 3):
            br = brush(0.3, vel=0.3, seed=bar * 7 + beat)
            t0 = bar * BAR + beat * BEAT
            add(L, t0, br, 0.85); add(R, t0, br, 0.95)
        for beat in range(4):
            rd = ride(vel=0.14, seed=bar * 13 + beat)
            add(L, bar * BAR + beat * BEAT, rd, 0.8); add(R, bar * BAR + beat * BEAT, rd, 1.0)
            if beat in (1, 3):
                rd2 = ride(vel=0.1, seed=bar * 13 + beat + 99)
                t0 = bar * BAR + (beat + SWING) * BEAT
                add(L, t0, rd2, 0.8); add(R, t0, rd2, 1.0)

    L = fft_lowpass(L, 4300)
    R = fft_lowpass(R, 4300)
    fade = int(1.6 * SR)
    ramp = np.linspace(0, 1, fade)
    for buf in (L, R):
        buf[:fade] *= ramp
        buf[-fade:] *= ramp[::-1]

    stereo = np.stack([L, R], axis=1)
    peak = np.max(np.abs(stereo)) or 1.0
    stereo = (stereo / peak) * 0.5
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(struct.pack("<%dh" % pcm.size, *pcm.flatten()))
    print(f"wrote {out_path}  ({n / SR:.1f}s)")


def main():
    # bar ≈ 1.935s. 48 bars ≈ 93s — comfortably covers the demo.
    render(48, os.path.join(OUT, "bed.wav"))


if __name__ == "__main__":
    main()
