"""Build the synthetic assets for the video-use launch demo.

There is no real footage and no ElevenLabs key in this sample, so this script
*generates* three short source clips (the stand-in "raw takes"), one eased
alpha overlay (the signature PIL animation technique), an EDL, and an
output-timeline SRT. Then `render.py` cuts, grades, composites the overlay
PTS-shifted, burns the subtitles LAST, and loudness-normalizes — exercising
every Hard Rule in the pipeline on assets that cost nothing to regenerate.

Run:
    uv run python samples/launch-demo/build.py
    uv run python helpers/render.py samples/launch-demo/edit/edl.json \
        -o samples/launch-demo/edit/final.mp4

Everything here is deterministic — delete sources/ and edit/*.mp4 and rebuild.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- canvas + palette (the terminal aesthetic from SKILL.md) ---------------
W, H, FPS = 1080, 1920, 30
BG = (10, 10, 10)
ORANGE = (255, 90, 0)
GRAY = (110, 110, 110)
WHITE = (235, 235, 235)
DIM = (55, 55, 55)
GREEN = (90, 200, 120)

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sources"
EDIT = ROOT / "edit"
SLOT = EDIT / "animations" / "slot_1"
for d in (SRC, SLOT):
    d.mkdir(parents=True, exist_ok=True)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def font(sz: int) -> ImageFont.FreeTypeFont:
    if sz not in _font_cache:
        _font_cache[sz] = ImageFont.truetype(FONT_PATH, sz)
    return _font_cache[sz]


# ---- easing (never linear — Hard Rule of animation craft) -------------------
def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


# ---- one precomputed vignette so the near-black bg isn't flat ----------------
def _vignette_base() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H / 2
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    falloff = np.clip(1.0 - 0.45 * (r ** 1.8), 0.45, 1.0)[..., None]
    base = (np.array(BG, np.float32) * falloff).astype(np.uint8)
    return Image.fromarray(base, "RGB")


VIGNETTE = _vignette_base()


def blend(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def ctext(d, cx, y, s, fnt, fill, anchor="mm"):
    d.text((cx, y), s, font=fnt, fill=fill, anchor=anchor)


# ============================================================================
# SCENE 1 — terminal: drop footage, chat, done
# ============================================================================
S1_L1 = "$ cd ~/footage && claude"
S1_L2 = "> edit these into a launch video"


def scene1(t: float) -> Image.Image:
    img = VIGNETTE.copy()
    d = ImageDraw.Draw(img)
    fade = ease_out_cubic(t / 0.4)

    # minimal window chrome — one orange dot is the only accent.
    # (the HUD overlay owns the top-right corner, so no label there.)
    for i, col in enumerate((ORANGE, DIM, DIM)):
        d.ellipse([80 + i * 46 - 13, 230 - 13, 80 + i * 46 + 13, 230 + 13],
                  fill=blend(BG, col, fade))

    fmono = font(46)
    x, y1, y2 = 80, int(H * 0.30), int(H * 0.30) + 86

    # line 1 typewriter: 0.6 -> 2.0s
    n1 = int(max(0, min(len(S1_L1), (t - 0.6) / 1.4 * len(S1_L1))))
    d.text((x, y1), S1_L1[:n1], font=fmono, fill=WHITE)
    # line 2 typewriter: 2.3 -> 4.2s
    n2 = int(max(0, min(len(S1_L2), (t - 2.3) / 1.9 * len(S1_L2))))
    if t >= 2.2:
        d.text((x, y2), S1_L2[:n2], font=fmono, fill=blend(WHITE, ORANGE, 0.85))

    # block cursor blinks on the active line
    if int(t * 2) % 2 == 0:
        if t < 2.2:
            cx = x + fmono.getlength(S1_L1[:n1])
            cy = y1
        else:
            cx = x + fmono.getlength(S1_L2[:n2])
            cy = y2
        d.rectangle([cx + 4, cy + 4, cx + 28, cy + 52], fill=ORANGE)

    return img


# ============================================================================
# SCENE 2 — it reads the video, it doesn't watch it (the pipeline)
# ============================================================================
PIPE = ["TRANSCRIBE", "PACK", "REASON", "EDL", "RENDER", "SELF-EVAL"]


def scene2(t: float) -> Image.Image:
    img = VIGNETTE.copy()
    d = ImageDraw.Draw(img)

    ctext(d, W / 2, int(H * 0.11), "IT READS THE VIDEO.",
          font(54), blend(BG, WHITE, ease_out_cubic(t / 0.5)))
    ctext(d, W / 2, int(H * 0.11) + 74, "IT DOESN'T WATCH IT.",
          font(54), blend(BG, ORANGE, ease_out_cubic((t - 0.5) / 0.5)))

    # pipeline nodes revealed one at a time (never two new things at once).
    # Kept entirely above the subtitle safe zone (~y1100+).
    fnode = font(42)
    x = int(W * 0.32)
    top = int(H * 0.255)
    step = 102
    for i, name in enumerate(PIPE):
        appear = 0.9 + i * 0.45
        a = ease_out_cubic((t - appear) / 0.45)
        if a <= 0:
            continue
        cy = top + i * step
        # connector drawn from previous node down into this one
        if i > 0:
            ln = ease_in_out_cubic((t - appear + 0.2) / 0.4)
            d.line([x, cy - step + 22, x, cy - step + 22 + int((step - 44) * ln)],
                   fill=blend(BG, DIM, 1.0), width=4)
        d.ellipse([x - 14, cy - 14, x + 14, cy + 14], fill=blend(BG, ORANGE, a))
        d.text((x + 52, cy), name, font=fnode, fill=blend(BG, WHITE, a), anchor="lm")
    return img


# ============================================================================
# SCENE 3 — get final.mp4 back
# ============================================================================
def scene3(t: float) -> Image.Image:
    img = VIGNETTE.copy()
    d = ImageDraw.Draw(img)

    ctext(d, W / 2, int(H * 0.20), "edit/", font(46), blend(BG, GRAY, ease_out_cubic(t / 0.5)), anchor="mm")

    name = "final.mp4"
    n = int(max(0, min(len(name), (t - 0.5) / 1.0 * len(name))))
    ctext(d, W / 2, int(H * 0.20) + 86, name[:n], font(92), ORANGE)

    # check pops in after the name finishes (ease_out scale)
    ca = ease_out_cubic((t - 1.8) / 0.5)
    if ca > 0:
        cx, cy, r = W / 2, int(H * 0.40), int(44 * ca)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GREEN, width=max(2, int(8 * ca)))
        if ca > 0.6:
            d.line([cx - 21, cy + 2, cx - 6, cy + 19], fill=GREEN, width=9)
            d.line([cx - 6, cy + 19, cx + 23, cy - 17], fill=GREEN, width=9)

    # taglines grouped in the upper-middle, clear of the subtitle safe zone
    ctext(d, W / 2, int(H * 0.51), "EDIT VIDEOS WITH CLAUDE CODE",
          font(44), blend(BG, WHITE, ease_out_cubic((t - 2.4) / 0.6)))
    ctext(d, W / 2, int(H * 0.51) + 66, "100% OPEN SOURCE",
          font(38), blend(BG, ORANGE, ease_out_cubic((t - 3.2) / 0.6)))
    return img


# ============================================================================
# OVERLAY — full-frame alpha HUD: blinking REC, running timecode, progress bar
# Runs on the OUTPUT timeline (15s), composited PTS-shifted at start_in_output=0.
# ============================================================================
OUT_DUR = 15.0


def overlay(t: float) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # blinking REC dot + label, top-left
    if int(t * 2) % 2 == 0:
        d.ellipse([84, 96, 116, 128], fill=(255, 60, 40, 255))
    d.text((132, 112), "REC", font=font(40), fill=(235, 235, 235, 230), anchor="lm")

    # timecode top-right
    tc = f"00:{int(t):02d}"
    d.text((W - 84, 112), tc, font=font(40), fill=(235, 235, 235, 210), anchor="rm")

    # progress bar along the very bottom (below the subtitle safe zone)
    y = H - 26
    d.rectangle([80, y, W - 80, y + 6], fill=(70, 70, 70, 180))
    frac = max(0.0, min(1.0, t / OUT_DUR))
    d.rectangle([80, y, 80 + int((W - 160) * frac), y + 6], fill=(255, 90, 0, 255))
    return img


# ============================================================================
# encoding
# ============================================================================
def encode_source(name: str, draw_fn, dur: float, audio: str) -> Path:
    """Pipe RGB frames to ffmpeg, mux a synthesized audio bed (so the 30ms
    fades, lossless concat, and loudnorm all operate on real audio)."""
    out = SRC / f"{name}.mp4"
    n = int(round(dur * FPS))
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-f", "lavfi", "-i", audio,
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", str(out),
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(draw_fn(i / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {name}")
    print(f"  source: {out.name}  ({dur:.1f}s)")
    return out


def encode_overlay() -> Path:
    # QuickTime Animation (qtrle/argb): lossless RGBA alpha that ffmpeg's
    # overlay filter honors reliably. (libvpx-vp9 dropped the alpha plane here.)
    out = SLOT / "render.mov"
    n = int(round(OUT_DUR * FPS))
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "qtrle", "-pix_fmt", "argb",
        str(out),
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(overlay(i / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed for overlay")
    print(f"  overlay: {out.name}  ({OUT_DUR:.1f}s, alpha)")
    return out


# soft sine-chord beds, distinct per scene so the cuts are audible
AUDIO = {
    "scene1": "sine=frequency=110:sample_rate=48000,volume=0.12",
    "scene2": "sine=frequency=147:sample_rate=48000,volume=0.12",
    "scene3": "sine=frequency=196:sample_rate=48000,volume=0.14",
}

SCENE_DUR = 6.0  # each source is 6s; the EDL trims to a 5s window


def write_edl(sources: dict[str, Path]) -> None:
    # paths relative to the edit dir (edl.parent) so the committed EDL is portable
    edl = {
        "version": 1,
        "sources": {k: f"../sources/{v.name}" for k, v in sources.items()},
        "ranges": [
            {"source": "scene1", "start": 0.40, "end": 5.40, "beat": "HOOK",
             "quote": "drop footage, chat, done", "reason": "trim lead-in and tail hold"},
            {"source": "scene2", "start": 0.40, "end": 5.40, "beat": "HOW",
             "quote": "it reads the video", "reason": "pipeline reveal lands inside the window"},
            {"source": "scene3", "start": 0.40, "end": 5.40, "beat": "PAYOFF",
             "quote": "get final.mp4 back", "reason": "hold on the open-source line"},
        ],
        "grade": "warm_cinematic",
        "overlays": [
            {"file": "animations/slot_1/render.mov", "start_in_output": 0.0, "duration": 15.0}
        ],
        "subtitles": "master.srt",
        "total_duration_s": 15.0,
    }
    (EDIT / "edl.json").write_text(json.dumps(edl, indent=2))
    print("  edl: edl.json")


# 2-word UPPERCASE chunks on the OUTPUT timeline (bold-overlay style)
SRT_CUES = [
    (0.5, 1.5, "DROP FOOTAGE"),
    (1.6, 2.6, "CHAT WITH"),
    (2.6, 3.7, "CLAUDE CODE"),
    (3.8, 4.9, "GET FINAL.MP4"),
    (5.4, 6.4, "IT READS"),
    (6.4, 7.4, "THE VIDEO"),
    (7.5, 8.6, "NEVER WATCHES"),
    (8.7, 9.8, "JUST READS"),
    (10.4, 11.4, "CUTS FILLER"),
    (11.5, 12.5, "COLOR GRADES"),
    (12.6, 13.6, "BURNS SUBTITLES"),
    (13.7, 14.8, "100% OPEN"),
]


def _ts(s: float) -> str:
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def write_srt() -> None:
    lines = []
    for i, (a, b, txt) in enumerate(SRT_CUES, 1):
        lines += [str(i), f"{_ts(a)} --> {_ts(b)}", txt, ""]
    (EDIT / "master.srt").write_text("\n".join(lines))
    print("  subtitles: master.srt")


def main() -> None:
    print("building sources …")
    sources = {
        "scene1": encode_source("scene1", scene1, SCENE_DUR, AUDIO["scene1"]),
        "scene2": encode_source("scene2", scene2, SCENE_DUR, AUDIO["scene2"]),
        "scene3": encode_source("scene3", scene3, SCENE_DUR, AUDIO["scene3"]),
    }
    print("building overlay …")
    encode_overlay()
    print("writing edit artifacts …")
    write_edl(sources)
    write_srt()
    print("\ndone. render with:")
    print("  uv run python helpers/render.py samples/launch-demo/edit/edl.json "
          "-o samples/launch-demo/edit/final.mp4")


if __name__ == "__main__":
    main()
