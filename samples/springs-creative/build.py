"""Springs Creative Marketing — Google Business Profile promo (1920×1080, ~30s).

A from-scratch kinetic-typography promo generated from the client caption,
skinned with the real Springs Creative design system (hero gradient, brand
colors, Space Grotesk / DM Sans, inverted logo). No footage, no ElevenLabs —
the caption is the content. PIL renders frames → ffmpeg encodes → a subtle
synth pad is mixed and loudness-normalized.

Run:
    uv run python samples/springs-creative/build.py
Output: samples/springs-creative/final.mp4
"""

from __future__ import annotations

import subprocess
from math import sin, cos, pi
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, DUR = 1920, 1080, 30, 30.0
ROOT = Path(__file__).resolve().parent
FONTS = ROOT / "fonts"
ASSETS = ROOT / "assets"

# ---- brand tokens (resolved from the design system) ------------------------
NAVY = (14, 36, 88)        # brand-blue-deep
BLUE = (0, 90, 163)        # brand-blue (primary)
TEAL = (0, 163, 168)       # brand-teal
ORANGE = (255, 110, 66)    # brand-orange (accent)
ORANGE_LT = (255, 153, 102)
WHITE = (255, 255, 255)
SLATE200 = (224, 229, 235)
SLATE400 = (150, 165, 188)

SG = str(FONTS / "SpaceGrotesk-var.ttf")   # display
DM = str(FONTS / "DMSans-var.ttf")         # body

_fc: dict = {}


def font(path: str, size: int, inst: str) -> ImageFont.FreeTypeFont:
    key = (path, size, inst)
    if key not in _fc:
        f = ImageFont.truetype(path, size)
        try:
            f.set_variation_by_name(inst)
        except Exception:
            pass
        _fc[key] = f
    return _fc[key]


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_io(t):
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


# ---- background: hero gradient (135° navy → blue → teal) -------------------
def _gradient_base() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (xx + yy) / (W + H)                       # 0 top-left → 1 bottom-right
    stops = [(0.0, NAVY), (0.55, BLUE), (1.0, TEAL)]
    out = np.zeros((H, W, 3), np.float32)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[..., None]
        out = np.where(m[..., None], np.array(c0) + (np.array(c1) - np.array(c0)) * f, out)
    # gentle edge darkening to focus the center
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vig = np.clip(1.0 - 0.16 * (r ** 2), 0.7, 1.0)[..., None]
    out = out * vig
    rgba = np.dstack([out.astype(np.uint8), np.full((H, W), 255, np.uint8)])
    return Image.fromarray(rgba, "RGBA")


def _highlight_sprite() -> Image.Image:
    s = 1000
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.sqrt(((xx - s / 2) / (s / 2)) ** 2 + ((yy - s / 2) / (s / 2)) ** 2)
    a = np.clip(1.0 - r, 0.0, 1.0) ** 2 * 42
    col = np.array([120, 220, 220], np.float32)  # soft teal-white glow
    rgba = np.dstack([np.broadcast_to(col, (s, s, 3)).astype(np.uint8), a.astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA")


BASE = _gradient_base()
GLOW = _highlight_sprite()

# floating dots (deterministic; no RNG so the build is reproducible)
DOTS = []
for i in range(54):
    DOTS.append({
        "x": (i * 137.5) % W,
        "y": (i * 263.1) % H,
        "r": 2 + (i % 4),
        "sp": 9 + (i * 7) % 16,
        "ph": (i * 0.7) % (2 * pi),
        "a": 16 + (i * 11) % 30,
        "teal": i % 3 == 0,
    })


def background(t: float) -> Image.Image:
    img = BASE.copy()
    fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # drifting glow on a slow ellipse
    gx = int(W * 0.5 + cos(t * 0.18) * W * 0.32) - GLOW.width // 2
    gy = int(H * 0.42 + sin(t * 0.13) * H * 0.30) - GLOW.height // 2
    fx.alpha_composite(GLOW, (gx, gy))
    d = ImageDraw.Draw(fx)
    for dt in DOTS:
        y = (dt["y"] - dt["sp"] * t) % (H + 40) - 20
        x = (dt["x"] + sin(t * 0.4 + dt["ph"]) * 18) % W
        tw = 0.6 + 0.4 * sin(t * 1.3 + dt["ph"])
        a = int(dt["a"] * tw)
        col = TEAL if dt["teal"] else WHITE
        d.ellipse([x - dt["r"], y - dt["r"], x + dt["r"], y + dt["r"]], fill=col + (a,))
    return Image.alpha_composite(img, fx)


# ---- prescaled logo --------------------------------------------------------
def load_scaled(path: Path, w: int) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    h = round(im.height * w / im.width)
    return im.resize((w, h), Image.LANCZOS)


LOGO_BRAND = load_scaled(ASSETS / "logo-inverted.png", 820)
LOGO_CTA = load_scaled(ASSETS / "logo-inverted.png", 560)


def put_logo(layer: Image.Image, logo: Image.Image, cx: int, cy: int, alpha: float, dy: int = 0):
    if alpha <= 0:
        return
    im = logo
    if alpha < 1:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    layer.alpha_composite(im, (cx - im.width // 2, cy - im.height // 2 + dy))


# ---- text helpers ----------------------------------------------------------
def text_c(d, cx, y, s, fnt, rgb, alpha, dy=0):
    if alpha <= 0:
        return
    d.text((cx, y + dy), s, font=fnt, fill=rgb + (int(alpha),), anchor="mm")


def tracked_c(d, cx, y, s, fnt, rgb, alpha, track, dy=0):
    """Center a letter-spaced (tracked) uppercase string."""
    if alpha <= 0:
        return
    widths = [d.textlength(ch, font=fnt) for ch in s]
    total = sum(widths) + track * (len(s) - 1)
    x = cx - total / 2
    fill = rgb + (int(alpha),)
    for ch, w in zip(s, widths):
        d.text((x, y + dy), ch, font=fnt, fill=fill, anchor="lm")
        x += w + track


def reveal(lt, delay, dur=0.55):
    return ease_out((lt - delay) / dur)


# ---- icons (simple, on-brand line motifs) ----------------------------------
def icon_browser(d, cx, cy, s, a):
    col = WHITE + (a,)
    ac = ORANGE + (a,)
    w, h = int(s * 1.25), s
    x0, y0 = cx - w // 2, cy - h // 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=14, outline=col, width=5)
    d.line([x0, y0 + 28, x0 + w, y0 + 28], fill=col, width=5)
    for i in range(3):
        d.ellipse([x0 + 16 + i * 20, y0 + 9, x0 + 26 + i * 20, y0 + 19], fill=ac)
    d.line([x0 + 24, y0 + 58, x0 + w - 24, y0 + 58], fill=ac, width=6)
    d.line([x0 + 24, y0 + 80, x0 + w - 70, y0 + 80], fill=col, width=5)


def icon_pin(d, cx, cy, s, a):
    col = WHITE + (a,)
    ac = ORANGE + (a,)
    r = s // 2
    d.ellipse([cx - r, cy - r - 8, cx + r, cy + r - 8], outline=col, width=6)
    d.ellipse([cx - 12, cy - 20, cx + 12, cy + 4], fill=ac)
    d.polygon([(cx - 16, cy + r - 18), (cx + 16, cy + r - 18), (cx, cy + r + 16)], fill=col)


def icon_chat(d, cx, cy, s, a):
    col = WHITE + (a,)
    ac = ORANGE + (a,)
    w, h = int(s * 1.2), int(s * 0.85)
    x0, y0 = cx - w // 2, cy - h // 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=18, outline=col, width=5)
    d.polygon([(x0 + 30, y0 + h - 2), (x0 + 30, y0 + h + 22), (x0 + 60, y0 + h - 2)], fill=col)
    for i in range(3):
        d.ellipse([x0 + 26 + i * 34, cy - 6, x0 + 38 + i * 34, cy + 6], fill=ac)


def icon_spark(d, cx, cy, s, a):
    col = WHITE + (a,)
    ac = ORANGE + (a,)
    def star(ccx, ccy, rr, fill):
        pts = []
        for k in range(8):
            ang = k * pi / 4
            rad = rr if k % 2 == 0 else rr * 0.4
            pts.append((ccx + cos(ang - pi / 2) * rad, ccy + sin(ang - pi / 2) * rad))
        d.polygon(pts, fill=fill)
    star(cx, cy, s // 2, ac)
    star(cx + s // 2 + 6, cy + s // 2 - 4, s // 5, col)


# ============================================================================
# beats
# ============================================================================
CX = W // 2


def b_hook(layer, lt, dur, env):
    d = ImageDraw.Draw(layer)
    a1 = int(255 * env * reveal(lt, 0.1))
    tracked_c(d, CX, 360, "HOLLY SPRINGS · CARY · APEX · RALEIGH · FUQUAY-VARINA",
              font(DM, 30, "SemiBold"), ORANGE, a1, 6, dy=int((1 - reveal(lt, 0.1)) * 24))
    r2 = reveal(lt, 0.5)
    text_c(d, CX, 520, "Your next customer", font(SG, 92, "Bold"), WHITE,
           255 * env * r2, dy=int((1 - r2) * 40))
    r3 = reveal(lt, 0.9)
    # two-tone line: white + orange emphasis, centered as a unit
    f = font(SG, 92, "Bold")
    s1, s2 = "is already ", "scrolling."
    w1 = d.textlength(s1, font=f)
    w2 = d.textlength(s2, font=f)
    x0 = CX - (w1 + w2) / 2
    dy = int((1 - r3) * 40)
    aa = int(255 * env * r3)
    if aa > 0:
        d.text((x0, 632 + dy), s1, font=f, fill=WHITE + (aa,), anchor="lm")
        d.text((x0 + w1, 632 + dy), s2, font=f, fill=ORANGE + (aa,), anchor="lm")


def b_brand(layer, lt, dur, env):
    d = ImageDraw.Draw(layer)
    rl = reveal(lt, 0.1, 0.7)
    put_logo(layer, LOGO_BRAND, CX, 470, env * rl, dy=int((1 - rl) * 30))
    r2 = reveal(lt, 0.7)
    text_c(d, CX, 660, "Where creativity springs growth.",
           font(DM, 42, "Medium"), SLATE200, 255 * env * r2, dy=int((1 - r2) * 26))
    r3 = reveal(lt, 1.05)
    tracked_c(d, CX, 730, "STRATEGY, NOT GUESSWORK", font(DM, 26, "Bold"),
              ORANGE, int(255 * env * r3), 5, dy=int((1 - r3) * 20))


def _service(layer, lt, env, icon, eyebrow, line1, line2):
    d = ImageDraw.Draw(layer)
    ri = reveal(lt, 0.05, 0.6)
    if ri > 0:
        icon(d, CX, 360, 130, int(255 * env * ri))
    re = reveal(lt, 0.35)
    tracked_c(d, CX, 500, eyebrow, font(DM, 30, "Bold"), ORANGE,
              int(255 * env * re), 7, dy=int((1 - re) * 20))
    # animated underline under the eyebrow
    uw = int(140 * ease_io((lt - 0.45) / 0.5))
    if uw > 0 and env > 0:
        d.rounded_rectangle([CX - uw // 2, 530, CX + uw // 2, 535], radius=3,
                            fill=ORANGE + (int(255 * env),))
    r1 = reveal(lt, 0.6)
    text_c(d, CX, 612, line1, font(SG, 78, "Bold"), WHITE, 255 * env * r1, dy=int((1 - r1) * 36))
    r2 = reveal(lt, 0.85)
    text_c(d, CX, 700, line2, font(SG, 78, "Bold"), WHITE, 255 * env * r2, dy=int((1 - r2) * 36))


def b_web(layer, lt, dur, env):
    _service(layer, lt, env, icon_browser, "WEBSITES", "Modern. Fast.", "Built to convert.")


def b_seo(layer, lt, dur, env):
    _service(layer, lt, env, icon_pin, "LOCAL SEO", "Get found locally.", "Clean SEO + smart content.")


def b_social(layer, lt, dur, env):
    _service(layer, lt, env, icon_chat, "SOCIAL", "Sounds like you.", "Brings in real leads.")


def b_ai(layer, lt, dur, env):
    _service(layer, lt, env, icon_spark, "THE EDGE", "Practical AI consulting.", "Spot opportunities. Save time.")


def b_cta(layer, lt, dur, env):
    d = ImageDraw.Draw(layer)
    r1 = reveal(lt, 0.1)
    text_c(d, CX, 300, "Clear. Measured. Built to grow.",
           font(SG, 60, "Bold"), WHITE, 255 * env * r1, dy=int((1 - r1) * 30))
    rl = reveal(lt, 0.5, 0.6)
    put_logo(layer, LOGO_CTA, CX, 470, env * rl, dy=int((1 - rl) * 24))
    # CTA pill
    rp = reveal(lt, 0.9, 0.5)
    if rp > 0 and env > 0:
        a = int(255 * env)
        pw, ph = 360, 84
        x0, y0 = CX - pw // 2, 600
        sc = 0.9 + 0.1 * rp
        pw2, ph2 = int(pw * sc), int(ph * sc)
        x0, y0 = CX - pw2 // 2, 600 + (ph - ph2) // 2
        d.rounded_rectangle([x0, y0, x0 + pw2, y0 + ph2], radius=ph2 // 2, fill=ORANGE + (a,))
        text_c(d, CX, y0 + ph2 // 2, "CALL FOR INFO", font(DM, 32, "Bold"), (20, 28, 44), 255 * env * rp)
    rc = reveal(lt, 1.2)
    text_c(d, CX, 740, "(919) 724-4421   ·   springscreativemarketing.com",
           font(DM, 30, "Medium"), SLATE200, 255 * env * rc, dy=int((1 - rc) * 18))


BEATS = [
    (0.0, 5.0, b_hook),
    (5.0, 9.5, b_brand),
    (9.5, 14.0, b_web),
    (14.0, 18.5, b_seo),
    (18.5, 23.0, b_social),
    (23.0, 26.5, b_ai),
    (26.5, 30.0, b_cta),
]


def envelope(lt, dur):
    fin = ease_out(lt / 0.45)
    fout = ease_out((dur - lt) / 0.4)
    return max(0.0, min(1.0, min(fin, fout)))


def frame(t: float) -> Image.Image:
    img = background(t)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for s, e, fn in BEATS:
        if s <= t < e:
            fn(layer, t - s, e - s, envelope(t - s, e - s))
            break
    return Image.alpha_composite(img, layer).convert("RGB")


# ---- encode ----------------------------------------------------------------
def main():
    silent = ROOT / "_silent.mp4"
    final = ROOT / "final.mp4"
    n = int(round(DUR * FPS))
    print(f"rendering {n} frames {W}x{H}@{FPS} …")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(silent),
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i / FPS).tobytes())
        if i % 90 == 0:
            print(f"  {i}/{n}")
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("video encode failed")

    # subtle synth pad (calm chord), faded + loudness-normalized for social
    print("mixing synth pad + loudnorm …")
    pad = (
        "sine=f=110:d=30[a];sine=f=164.81:d=30[b];sine=f=220:d=30[c];sine=f=329.63:d=30[e];"
        "[a][b][c][e]amix=inputs=4:normalize=0,"
        "tremolo=f=0.10:d=0.22,lowpass=f=900,volume=0.16,"
        "afade=t=in:st=0:d=1.5,afade=t=out:st=28.3:d=1.7,"
        "loudnorm=I=-16:TP=-1.5:LRA=11[aud]"
    )
    cmd2 = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(silent),
        "-filter_complex", pad,
        "-map", "0:v", "-map", "[aud]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", str(final),
    ]
    if subprocess.run(cmd2).returncode != 0:
        raise RuntimeError("audio mux failed")
    silent.unlink(missing_ok=True)
    size = final.stat().st_size / 1e6
    print(f"\ndone: {final} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
