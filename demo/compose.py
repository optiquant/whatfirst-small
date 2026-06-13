"""Compose the captured whatfirst-small screenshots into a narrated demo video.

Pipeline, mirroring the what-first.com demo but with the voiceover baked in:
  1. synthesize each scene's narration (vo.py / edge-tts) and measure it,
  2. set each scene's on-screen duration from its narration length,
  3. lay the voice clips onto a track aligned to the cut and mix the jazz bed
     (music.py) under it,
  4. render a clean Ken-Burns push-in per scene with a bold caption above the
     app, crossfade the scenes, and mux the mixed audio.

Output: demo/out/whatfirst-small-demo.mp4  (+ -poster.jpg)
"""

import os
import subprocess
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

import vo

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
AUDIO = os.path.join(HERE, "audio")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

W, H = 1920, 1080
OUT_W, OUT_H = 1280, 720
FPS = 24
FADE = int(0.6 * FPS)
LOGO_FADE = int(0.9 * FPS)
SR = vo.SR
MUSIC_GAIN = 0.16
VO_LEAD = 0.45          # narration starts this long after the scene begins
VO_TAIL = 0.9           # breath held after narration before the next scene
MIN_SECS = {"title": 3.2, "app": 5.0, "card": 3.6, "end": 3.8}

# ── Type & colour ────────────────────────────────────────────────────────────
_ROBOTO = os.path.join(HERE, "fonts", "Roboto-VF.ttf")
_WGHT = {"r": 400, "m": 500, "sb": 600, "b": 700}


@lru_cache(maxsize=None)
def font(weight, size):
    f = ImageFont.truetype(_ROBOTO, size)
    try:
        f.set_variation_by_axes([_WGHT[weight], 100])
    except Exception:
        pass
    return f


INDIGO = (79, 70, 229); BLUE = (37, 99, 235); SLATE = (30, 41, 59)
INK = (17, 24, 39); INKSOFT = (55, 65, 81); MUTED = (90, 100, 115)
ACCENTS = {
    "indigo": (79, 70, 229), "blue": (37, 99, 235), "gold": (217, 119, 6),
    "green": (21, 128, 61), "violet": (109, 40, 217), "slate": (51, 65, 85),
    "teal": (13, 118, 110),
}

VW, VH = 1480, 832
VX, VY = (W - VW) // 2, 214
VBOX = (VX, VY, VX + VW, VY + VH)
VRAD = 22

_shot_cache = {}


def load_shot(name):
    if name not in _shot_cache:
        _shot_cache[name] = Image.open(os.path.join(SHOTS, f"{name}.png")).convert("RGB")
    return _shot_cache[name]


def make_bg():
    top = np.array([250, 251, 255], dtype=np.float32)
    bot = np.array([232, 235, 248], dtype=np.float32)
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    grad = np.repeat((top * (1 - ramp) + bot * ramp).astype(np.uint8), W, axis=1)
    img = Image.fromarray(grad, "RGB")
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([-560, -620, 1060, 560], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(240))
    layer = Image.new("RGB", (W, H), INDIGO)
    return Image.composite(layer, img, glow.point(lambda v: int(v * 0.13)))


BG = make_bg()
BG_ARR = np.asarray(BG.convert("RGB"))


def soft_shadow(box, radius, blur, alpha, dy):
    x0, y0, x1, y1 = box
    shp = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shp).rounded_rectangle([x0, y0 + dy, x1, y1 + dy], radius=radius, fill=alpha)
    return shp.filter(ImageFilter.GaussianBlur(blur))


def centered(draw, cx, y, text, f, fill, tracking=0.0):
    if not tracking:
        draw.text((cx - draw.textlength(text, font=f) / 2, y), text, font=f, fill=fill)
        return
    widths = [draw.textlength(ch, font=f) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, wd in zip(text, widths):
        draw.text((x, y), ch, font=f, fill=fill)
        x += wd + tracking


def wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_wordmark(draw, cx, cy, size):
    f = font("sb", size)
    parts = [("whatfirst", INDIGO), (" · small", SLATE)]
    widths = [draw.textlength(t, font=f) for t, _ in parts]
    x = cx - sum(widths) / 2
    for (t, col), wpx in zip(parts, widths):
        draw.text((x, cy), t, font=f, fill=col)
        x += wpx


def _box_mask():
    m = Image.new("L", (VW, VH), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, VW - 1, VH - 1], radius=VRAD, fill=255)
    return m


BOX_MASK = _box_mask()


def scene_static(chip_col, chip_label, title, body):
    frame = BG.copy()
    d = ImageDraw.Draw(frame)
    cx = W // 2
    y = 44
    if chip_label:
        fchip = font("b", 21)
        tw = d.textlength(chip_label.upper(), font=fchip)
        col = ACCENTS[chip_col]
        d.rounded_rectangle([cx - tw / 2 - 17, y, cx + tw / 2 + 17, y + 37], radius=9, fill=col)
        d.text((cx - tw / 2, y + 7), chip_label.upper(), font=fchip, fill=(255, 255, 255))
    centered(d, cx, 88, title, font("b", 52), INK, tracking=-1.0)
    fb = font("m", 30)
    for line in wrap(d, body, fb, 1560)[:1]:
        centered(d, cx, 158, line, fb, INKSOFT)
    frame.paste((0, 0, 0), (0, 0, W, H), soft_shadow(VBOX, VRAD, 40, 60, 24))
    d.rounded_rectangle(VBOX, radius=VRAD, fill=(255, 255, 255))
    d.rounded_rectangle(VBOX, radius=VRAD, outline=(228, 231, 237), width=2)
    return frame


def kenburns(shot_img, focal, z):
    iw, ih = shot_img.size
    base = max(VW / iw, VH / ih)
    scale = base * z
    rw, rh = VW / scale, VH / scale
    fx, fy = focal
    cxp = min(max(fx * iw, rw / 2), iw - rw / 2)
    cyp = min(max(fy * ih, rh / 2), ih - rh / 2)
    box = (cxp - rw / 2, cyp - rh / 2, cxp + rw / 2, cyp + rh / 2)
    return shot_img.resize((VW, VH), Image.LANCZOS, box=box)


def ease(p):
    return 0.5 - 0.5 * np.cos(np.pi * p)


def build_title(line, sub):
    frame = BG.copy()
    d = ImageDraw.Draw(frame)
    draw_wordmark(d, W // 2, H // 2 - 170, 132)
    if sub:
        centered(d, W // 2, H // 2 - 16, sub, font("m", 34), SLATE)
    fb = font("m", 37)
    for i, ln in enumerate(wrap(d, line, fb, 1420)[:3]):
        centered(d, W // 2, H // 2 + 64 + i * 50, ln, fb, INK, tracking=-0.6)
    return np.asarray(frame.convert("RGB"))


def build_card(chip_col, chip_label, title, subtitle):
    frame = BG.copy()
    d = ImageDraw.Draw(frame)
    cx = W // 2
    fchip = font("b", 25)
    tw = d.textlength(chip_label.upper(), font=fchip)
    col = ACCENTS[chip_col]
    d.rounded_rectangle([cx - tw / 2 - 23, H // 2 - 158, cx + tw / 2 + 23, H // 2 - 110], radius=11, fill=col)
    d.text((cx - tw / 2, H // 2 - 150), chip_label.upper(), font=fchip, fill=(255, 255, 255))
    centered(d, cx, H // 2 - 66, title, font("b", 76), INK, tracking=-1.6)
    centered(d, cx, H // 2 + 52, subtitle, font("m", 33), MUTED)
    return np.asarray(frame.convert("RGB"))


def build_end():
    frame = BG.copy()
    d = ImageDraw.Draw(frame)
    draw_wordmark(d, W // 2, H // 2 - 120, 120)
    centered(d, W // 2, H // 2 + 40, "Dump everything. Do the first thing.", font("m", 35), SLATE)
    centered(d, W // 2, H // 2 + 112, "hf.co/spaces/build-small-hackathon/whatfirst-small",
             font("sb", 28), INDIGO)
    return np.asarray(frame.convert("RGB"))


# ── The cut ──────────────────────────────────────────────────────────────────
def app(shot, chip_col, chip_label, title, body, vo_text, focal=(0.5, 0.42), z=(1.05, 1.18)):
    return dict(kind="app", shot=shot, chip_col=chip_col, chip_label=chip_label,
                title=title, body=body, vo=vo_text, focal=focal, z=z)


SCENES = [
    dict(kind="title", vo=(
        "Meet whatfirst, small. Dump everything on your mind — and it tells you "
        "the one thing to do first."),
        line="Dump your mind. Get back what to do first.", sub="the small, offline edition"),

    app("02_filled", "indigo", "Capture", "Catch it however it arrives",
        "Type a messy brain-dump — or snap a photo of your list.",
        "Start with the mess. Type a brain-dump, or photograph a pile of sticky notes. "
        "A small vision model — three billion parameters, running locally on llama-c-p-p — "
        "reads every line and turns it into a structured task.",
        focal=(0.17, 0.40), z=(1.05, 1.18)),

    app("03_ranked", "blue", "The answer", "What should I do first?",
        "One ranked list — and the single thing to start now.",
        "Then a transparent engine ranks them. Impact, urgency, how ready you are, a nudge "
        "for quick wins — and out comes one ranked list, with the single thing to do first, "
        "right at the top.",
        focal=(0.60, 0.30), z=(1.05, 1.19)),

    app("06_formula", "slate", "No black box", "The math is one plain page",
        "Two scores compete — and every number is shown.",
        "And it's no black box. Two scores compete — do it now, or de-risk it first — and "
        "the whole formula is right there, in plain English.",
        focal=(0.32, 0.86), z=(1.05, 1.18)),

    app("04_correct", "violet", "You decide", "The model proposes — you decide",
        "Disagree with a score? Grab a slider and correct it.",
        "The model proposes, but you decide. Think it got one wrong? Grab a slider and "
        "correct any score yourself.",
        focal=(0.30, 0.88), z=(1.05, 1.18)),

    app("05_reranked", "green", "Live", "The list re-ranks instantly",
        "Change a number and the whole order updates live.",
        "Change a number, and the whole list re-ranks the instant you let go — that task "
        "just climbed from the bottom of the pile.",
        focal=(0.56, 0.34), z=(1.05, 1.19)),

    dict(kind="card", vo=(
        "And all of it runs offline. A three-billion-parameter model on llama-c-p-p — no "
        "cloud, no API keys. Your to-do list never leaves the laptop."),
        chip_col="indigo", chip_label="Backyard AI",
        title="3B model · llama.cpp · offline", subtitle="No cloud. No API keys. Runs on a laptop."),

    dict(kind="end", vo=(
        "That's whatfirst, small. Dump everything — and just do the first thing.")),
]


# ── Audio: synth narration, time the scenes, mix voice under music ───────────
def build_audio():
    durs = []
    for i, s in enumerate(SCENES):
        path = os.path.join(AUDIO, f"vo_{i:02d}.mp3")
        d = vo.synth(s["vo"], path)
        s["_vo_path"] = path
        secs = max(MIN_SECS[s["kind"]], VO_LEAD + d + VO_TAIL)
        s["_secs"] = secs
        durs.append((i, d, secs))
        print(f"  scene {i} ({s['kind']}): vo {d:.2f}s -> scene {secs:.2f}s")

    total = sum(s["_secs"] for s in SCENES) + 2 * LOGO_FADE / FPS
    n = int(total * SR) + SR
    track = np.zeros((n, 2), np.float32)

    t = LOGO_FADE / FPS
    for s in SCENES:
        clip = vo.decode_stereo(s["_vo_path"])
        start = int((t + VO_LEAD) * SR)
        end = min(n, start + clip.shape[0])
        track[start:end] += clip[: end - start]
        t += s["_secs"]

    # Music bed: tile to length, duck under the voice.
    bed = vo.decode_stereo(os.path.join(AUDIO, "bed.wav"))
    if bed.shape[0] < n:
        reps = int(np.ceil(n / bed.shape[0]))
        bed = np.tile(bed, (reps, 1))
    bed = bed[:n] * MUSIC_GAIN

    mix = track + bed
    peak = float(np.max(np.abs(mix))) or 1.0
    if peak > 0.97:
        mix *= 0.97 / peak

    fin = int(1.2 * SR)
    fout = int(2.0 * SR)
    mix[:fin] *= np.linspace(0, 1, fin)[:, None]
    mix[-fout:] *= np.linspace(1, 0, fout)[:, None]

    import wave
    mix_path = os.path.join(AUDIO, "mix.wav")
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(mix_path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return mix_path, total


# ── Video: render frames, mux the mixed audio ────────────────────────────────
def frame_for(s):
    if s["kind"] == "app":
        return np.asarray(scene_static(s["chip_col"], s["chip_label"], s["title"], s["body"]).convert("RGB"))
    if s["kind"] == "title":
        return build_title(s["line"], s["sub"])
    if s["kind"] == "card":
        return build_card(s["chip_col"], s["chip_label"], s["title"], s["subtitle"])
    return build_end()


def render():
    mix_path, total = build_audio()
    statics = [frame_for(s) for s in SCENES]
    shots = [load_shot(s["shot"]) if s["kind"] == "app" else None for s in SCENES]

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_path = os.path.join(OUT, "whatfirst-small-demo.mp4")
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", mix_path,
        "-vf", f"scale={OUT_W}:{OUT_H}:flags=lanczos",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "medium",
        "-c:a", "aac", "-b:a", "160k",
        "-map", "0:v", "-map", "1:a", "-t", f"{total:.2f}",
        "-movflags", "+faststart", out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    write = proc.stdin.write

    def frame_at(idx, f, n):
        s = SCENES[idx]
        if s["kind"] != "app":
            return statics[idx]
        z = s["z"][0] + (s["z"][1] - s["z"][0]) * ease(f / max(1, n - 1))
        crop = kenburns(shots[idx], s["focal"], z)
        base = Image.fromarray(statics[idx])
        base.paste(crop, (VX, VY), BOX_MASK)
        return np.asarray(base)

    first = frame_at(0, 0, 1)
    for f in range(LOGO_FADE):
        a = (f + 1) / LOGO_FADE
        write((BG_ARR * (1 - a) + first * a).astype(np.uint8))

    prev_last = first
    for idx, s in enumerate(SCENES):
        n = int(s["_secs"] * FPS)
        frame = statics[idx]
        for f in range(n):
            frame = frame_at(idx, f, n)
            if f < FADE and idx > 0:
                a = f / FADE
                frame = (prev_last * (1 - a) + frame * a).astype(np.uint8)
            write(frame)
        prev_last = frame_at(idx, n - 1, n)

    for f in range(LOGO_FADE):
        a = (f + 1) / LOGO_FADE
        write((prev_last * (1 - a) + BG_ARR * a).astype(np.uint8))

    proc.stdin.close()
    proc.wait()

    # Poster: the ranked-list scene, mid push-in.
    pidx = next((i for i, s in enumerate(SCENES) if s.get("shot") == "03_ranked"), 1)
    pf = frame_at(pidx, int(SCENES[pidx]["_secs"] * FPS) // 2, int(SCENES[pidx]["_secs"] * FPS))
    poster = Image.fromarray(pf).resize((OUT_W, OUT_H), Image.LANCZOS)
    poster.convert("RGB").save(out_path.replace(".mp4", "-poster.jpg"), "JPEG", quality=86)
    print(f"done -> {out_path}  (~{total:.0f}s)")


if __name__ == "__main__":
    render()
