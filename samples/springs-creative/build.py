"""Springs Creative Marketing — promo generator (landscape + vertical).

One engine, two deliverables:
  • final.mp4           1920×1080  (Google Business Profile)
  • final-vertical.mp4  1080×1920  (Reels / TikTok / Stories)

Kinetic typography generated from the client caption and skinned with the
Springs Creative design system (hero gradient, brand colors, Space Grotesk /
DM Sans, inverted logo). Includes an ORIGINAL royalty-free music bed composed
here in numpy (chord pad + arpeggio + soft percussion) — safe to post anywhere.

Run:
    uv run python samples/springs-creative/build.py            # both
    uv run python samples/springs-creative/build.py vertical   # one
"""

from __future__ import annotations

import sys
import wave
import subprocess
from math import sin, cos, pi
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONTS = ROOT / "fonts"
ASSETS = ROOT / "assets"
FPS, DUR = 30, 30.0

# ---- brand tokens ----------------------------------------------------------
NAVY = (14, 36, 88)
BLUE = (0, 90, 163)
TEAL = (0, 163, 168)
ORANGE = (255, 110, 66)
WHITE = (255, 255, 255)
SLATE200 = (224, 229, 235)
INK = (18, 26, 42)

SG = str(FONTS / "SpaceGrotesk-var.ttf")
DM = str(FONTS / "DMSans-var.ttf")

_fc: dict = {}


def font(path, size, inst):
    key = (path, int(size), inst)
    if key not in _fc:
        f = ImageFont.truetype(path, int(size))
        try:
            f.set_variation_by_name(inst)
        except Exception:
            pass
        _fc[key] = f
    return _fc[key]


def ease_out(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def ease_io(t):
    t = max(0.0, min(1.0, t)); return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def reveal(lt, delay, dur=0.55):
    return ease_out((lt - delay) / dur)


# ============================================================================
# ORIGINAL MUSIC — composed procedurally (royalty-free, owned by this build)
# ============================================================================
SR = 48000


def _midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def compose_music(path: Path):
    n = int(SR * DUR)
    t = np.arange(n) / SR
    L = np.zeros(n); R = np.zeros(n)
    rng = np.random.default_rng(7)

    bar = 2.5                      # seconds (96 BPM, 4 beats)
    beat = bar / 4
    # I–V–vi–IV in D major: D, A, Bm, G  (root, triad, arp tones)
    chords = [
        (38, [50, 54, 57], [50, 54, 57, 62]),
        (33, [45, 49, 52], [45, 49, 52, 57]),
        (35, [47, 50, 54], [47, 50, 54, 59]),
        (31, [43, 47, 50], [43, 47, 50, 55]),
    ]

    def add(buf, sig, start):
        s = int(start * SR); e = min(n, s + len(sig))
        if e > s:
            buf[s:e] += sig[: e - s]

    nbars = int(DUR / bar)
    for b in range(nbars):
        root, triad, arp = chords[b % 4]
        t0 = b * bar
        # --- pad: soft detuned triad, slow swell across the bar ---
        bl = int(bar * SR); tt = np.arange(bl) / SR
        env = np.minimum(tt / 0.5, 1.0) * np.minimum((bar - tt) / 0.5, 1.0)
        env = np.clip(env, 0, 1) ** 0.8
        pad = np.zeros(bl)
        for note in triad:
            f = _midi(note)
            pad += np.sin(2 * pi * f * tt) + 0.5 * np.sin(2 * pi * f * 1.005 * tt)
        pad *= env * 0.05
        add(L, pad, t0); add(R, pad, t0)
        # --- bass: root, gentle ---
        f = _midi(root)
        benv = np.minimum(tt / 0.05, 1.0) * np.clip((bar - tt) / 0.4, 0, 1)
        bass = (np.sin(2 * pi * f * tt) + 0.4 * np.sin(2 * pi * f * 0.5 * tt)) * benv * 0.10
        add(L, bass, t0); add(R, bass, t0)
        # --- arpeggio: 8th-note plucks, panned ---
        for k in range(8):
            note = arp[k % len(arp)] + (12 if k >= 4 else 0)
            f = _midi(note)
            pl = int(0.32 * SR); pt = np.arange(pl) / SR
            penv = np.exp(-pt * 7)
            pluck = (np.sin(2 * pi * f * pt) + 0.4 * np.sin(2 * pi * 2 * f * pt)) * penv * 0.06
            pan = 0.5 + 0.35 * sin(k)
            add(L, pluck * (1 - pan), t0 + k * (beat / 2))
            add(R, pluck * pan, t0 + k * (beat / 2))
        # --- soft percussion ---
        for k in range(4):
            # kick: pitch-dropping sine
            kl = int(0.14 * SR); kt = np.arange(kl) / SR
            kf = 120 * np.exp(-kt * 18) + 48
            kick = np.sin(2 * pi * kf * kt) * np.exp(-kt * 16) * 0.18
            add(L, kick, t0 + k * beat); add(R, kick, t0 + k * beat)
            # hat: short noise on offbeat
            hl = int(0.05 * SR)
            hat = rng.standard_normal(hl) * np.exp(-np.arange(hl) / SR * 90) * 0.025
            add(L, hat, t0 + k * beat + beat / 2); add(R, hat, t0 + k * beat + beat / 2)

    stereo = np.stack([L, R], axis=1)
    stereo = np.tanh(stereo * 1.4)                       # soft glue/limit
    fin = np.clip(t / 1.2, 0, 1)[:, None]
    fout = np.clip((DUR - t) / 2.2, 0, 1)[:, None]
    stereo *= fin * fout
    stereo /= max(1e-6, np.max(np.abs(stereo))) / 0.95   # normalize peak
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())


# ============================================================================
# per-format setup (globals reconfigured for each render pass)
# ============================================================================
FORMATS = {
    "landscape": dict(W=1920, H=1080, margin=170, eyebrow=30, head=78, hook=92,
                      tag=42, title=60, contact=30, icon=130, logo_b=820, logo_c=560,
                      gap=24, center=0.50),
    "vertical":  dict(W=1080, H=1920, margin=84, eyebrow=36, head=86, hook=86,
                      tag=48, title=66, contact=33, icon=168, logo_b=860, logo_c=680,
                      gap=40, center=0.48),
    "square":    dict(W=1080, H=1080, margin=92, eyebrow=32, head=74, hook=78,
                      tag=44, title=56, contact=30, icon=140, logo_b=720, logo_c=560,
                      gap=24, center=0.50),
}

P: dict = {}
W = H = CX = 0
BASE = GLOW = LOGO_BRAND = LOGO_CTA = None
DOTS: list = []
_scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))


def configure(fmt: str):
    global P, W, H, CX, BASE, GLOW, LOGO_BRAND, LOGO_CTA, DOTS
    P = FORMATS[fmt]; W = P["W"]; H = P["H"]; CX = W // 2

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (xx + yy) / (W + H)
    stops = [(0.0, NAVY), (0.55, BLUE), (1.0, TEAL)]
    out = np.zeros((H, W, 3), np.float32)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[..., None]
        out = np.where(m[..., None], np.array(c0) + (np.array(c1) - np.array(c0)) * f, out)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    out = out * np.clip(1.0 - 0.16 * (r ** 2), 0.7, 1.0)[..., None]
    BASE = Image.fromarray(np.dstack([out.astype(np.uint8), np.full((H, W), 255, np.uint8)]), "RGBA")

    s = max(W, H)
    yy2, xx2 = np.mgrid[0:s, 0:s].astype(np.float32)
    rr = np.sqrt(((xx2 - s / 2) / (s / 2)) ** 2 + ((yy2 - s / 2) / (s / 2)) ** 2)
    a = np.clip(1.0 - rr, 0.0, 1.0) ** 2 * 42
    GLOW = Image.fromarray(np.dstack([
        np.broadcast_to(np.array([120, 220, 220], np.float32), (s, s, 3)).astype(np.uint8),
        a.astype(np.uint8)]), "RGBA")

    LOGO_BRAND = _load(ASSETS / "logo-inverted.png", P["logo_b"])
    LOGO_CTA = _load(ASSETS / "logo-inverted.png", P["logo_c"])

    DOTS = []
    for i in range(54):
        DOTS.append(dict(x=(i * 137.5) % W, y=(i * 263.1) % H, r=2 + i % 4,
                         sp=9 + (i * 7) % 16, ph=(i * 0.7) % (2 * pi),
                         a=16 + (i * 11) % 30, teal=i % 3 == 0))


def _load(path, w):
    im = Image.open(path).convert("RGBA")
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


def background(t):
    img = BASE.copy()
    fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gx = int(W * 0.5 + cos(t * 0.18) * W * 0.32) - GLOW.width // 2
    gy = int(H * 0.42 + sin(t * 0.13) * H * 0.30) - GLOW.height // 2
    fx.alpha_composite(GLOW, (gx, gy))
    d = ImageDraw.Draw(fx)
    for dt in DOTS:
        y = (dt["y"] - dt["sp"] * t) % (H + 40) - 20
        x = (dt["x"] + sin(t * 0.4 + dt["ph"]) * 18) % W
        a = int(dt["a"] * (0.6 + 0.4 * sin(t * 1.3 + dt["ph"])))
        col = TEAL if dt["teal"] else WHITE
        d.ellipse([x - dt["r"], y - dt["r"], x + dt["r"], y + dt["r"]], fill=col + (a,))
    return Image.alpha_composite(img, fx)


# ---- drawing helpers -------------------------------------------------------
def lh(fnt):
    asc, desc = fnt.getmetrics(); return asc + desc


def fit(text, path, inst, start_fs):
    maxw = W - 2 * P["margin"]
    fs = start_fs
    while fs > 36:
        if _scratch.textlength(text, font=font(path, fs, inst)) <= maxw:
            break
        fs -= 2
    return fs


def fit_tracked(s, path, inst, start_fs, track):
    """Shrink a tracked (letter-spaced) string's font until it fits the width."""
    maxw = W - 2 * P["margin"]
    fs = start_fs
    while fs > 20:
        f = font(path, fs, inst)
        w = sum(_scratch.textlength(c, font=f) for c in s) + track * (len(s) - 1)
        if w <= maxw:
            break
        fs -= 1
    return fs


def text_c(d, y, s, fnt, rgb, alpha, dy=0):
    if alpha > 0:
        d.text((CX, y + dy), s, font=fnt, fill=rgb + (int(alpha),), anchor="mm")


def tracked_c(d, y, s, fnt, rgb, alpha, track, dy=0):
    if alpha <= 0:
        return
    ws = [d.textlength(c, font=fnt) for c in s]
    x = CX - (sum(ws) + track * (len(s) - 1)) / 2
    for c, w in zip(s, ws):
        d.text((x, y + dy), c, font=fnt, fill=rgb + (int(alpha),), anchor="lm")
        x += w + track


def put_logo(layer, logo, yc, alpha, dy=0):
    if alpha <= 0:
        return
    im = logo
    if alpha < 1:
        im = logo.copy(); im.putalpha(logo.getchannel("A").point(lambda v: int(v * alpha)))
    layer.alpha_composite(im, (CX - im.width // 2, int(yc) - im.height // 2 + dy))


# ---- icons -----------------------------------------------------------------
def icon_browser(d, cx, cy, s, a):
    col = WHITE + (a,); ac = ORANGE + (a,)
    w, h = int(s * 1.25), s; x0, y0 = cx - w // 2, cy - h // 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=14, outline=col, width=5)
    d.line([x0, y0 + 28, x0 + w, y0 + 28], fill=col, width=5)
    for i in range(3):
        d.ellipse([x0 + 16 + i * 20, y0 + 9, x0 + 26 + i * 20, y0 + 19], fill=ac)
    d.line([x0 + 24, y0 + 58, x0 + w - 24, y0 + 58], fill=ac, width=6)
    d.line([x0 + 24, y0 + 80, x0 + w - 70, y0 + 80], fill=col, width=5)


def icon_pin(d, cx, cy, s, a):
    col = WHITE + (a,); ac = ORANGE + (a,); r = s // 2
    d.ellipse([cx - r, cy - r - 8, cx + r, cy + r - 8], outline=col, width=6)
    d.ellipse([cx - 12, cy - 20, cx + 12, cy + 4], fill=ac)
    d.polygon([(cx - 16, cy + r - 18), (cx + 16, cy + r - 18), (cx, cy + r + 16)], fill=col)


def icon_chat(d, cx, cy, s, a):
    col = WHITE + (a,); ac = ORANGE + (a,)
    w, h = int(s * 1.2), int(s * 0.85); x0, y0 = cx - w // 2, cy - h // 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=18, outline=col, width=5)
    d.polygon([(x0 + 30, y0 + h - 2), (x0 + 30, y0 + h + 22), (x0 + 60, y0 + h - 2)], fill=col)
    for i in range(3):
        d.ellipse([x0 + 26 + i * 34, cy - 6, x0 + 38 + i * 34, cy + 6], fill=ac)


def icon_spark(d, cx, cy, s, a):
    col = WHITE + (a,); ac = ORANGE + (a,)
    def star(ccx, ccy, rr, fill):
        pts = []
        for k in range(8):
            ang = k * pi / 4; rad = rr if k % 2 == 0 else rr * 0.4
            pts.append((ccx + cos(ang - pi / 2) * rad, ccy + sin(ang - pi / 2) * rad))
        d.polygon(pts, fill=fill)
    star(cx, cy, s // 2, ac); star(cx + s // 2 + 6, cy + s // 2 - 4, s // 5, col)


# ============================================================================
# stack layout engine — centers a vertical stack; adapts to any aspect
# ============================================================================
def _height(it):
    ty = it["type"]
    if ty == "logo":
        return it["img"].height
    if ty == "icon":
        return it["size"]
    if ty == "underline":
        return 6
    if ty == "pill":
        return int(it["fs"] * 2.6)
    return lh(it["font"])


def render_stack(layer, items, lt, env):
    d = ImageDraw.Draw(layer)
    hs = [_height(it) for it in items]
    total = sum(hs) + sum(it.get("gap", P["gap"]) for it in items[1:])
    cur = H * P["center"] - total / 2
    for i, it in enumerate(items):
        if i:
            cur += it.get("gap", P["gap"])
        yc = cur + hs[i] / 2
        r = reveal(lt, it.get("delay", 0.0))
        a = int(255 * env * r)
        dy = int((1 - r) * 34)
        ty = it["type"]
        if ty == "logo":
            put_logo(layer, it["img"], yc, env * reveal(lt, it.get("delay", 0.0), 0.7), dy=int((1 - reveal(lt, it.get("delay", 0.0), 0.7)) * 28))
        elif ty == "icon":
            if a > 0:
                it["fn"](d, CX, int(yc), it["size"], a)
        elif ty == "underline":
            uw = int((P["icon"] + 10) * ease_io((lt - it.get("delay", 0.0)) / 0.5))
            if uw > 0 and env > 0:
                d.rounded_rectangle([CX - uw // 2, int(yc) - 3, CX + uw // 2, int(yc) + 3],
                                    radius=3, fill=ORANGE + (int(255 * env),))
        elif ty == "eyebrow":
            tracked_c(d, yc, it["text"], it["font"], ORANGE, a, it.get("track", 7), dy=dy)
        elif ty == "twotone":
            f = it["font"]; s1, s2 = it["text"]
            w1 = d.textlength(s1, font=f); w2 = d.textlength(s2, font=f)
            x0 = CX - (w1 + w2) / 2
            if a > 0:
                d.text((x0, yc + dy), s1, font=f, fill=WHITE + (a,), anchor="lm")
                d.text((x0 + w1, yc + dy), s2, font=f, fill=ORANGE + (a,), anchor="lm")
        elif ty == "pill":
            if a > 0:
                pw = it["w"]; ph = _height(it); sc = 0.9 + 0.1 * r
                pw2, ph2 = int(pw * sc), int(ph * sc)
                x0 = CX - pw2 // 2; y0 = int(yc) - ph2 // 2
                d.rounded_rectangle([x0, y0, x0 + pw2, y0 + ph2], radius=ph2 // 2, fill=ORANGE + (int(255 * env),))
                text_c(d, yc, it["text"], it["font"], INK, 255 * env * r)
        else:  # head / tagline / title / contact
            text_c(d, yc, it["text"], it["font"], it["color"], a, dy=dy)
        cur += hs[i]


# ---- beat content builders -------------------------------------------------
def hook():
    fh = font(SG, fit("is already scrolling.", SG, "Bold", P["hook"]), "Bold")
    # locations: one tracked line on wide formats, two lines on narrow (vertical)
    loc_lines = (["HOLLY SPRINGS · CARY · APEX · RALEIGH · FUQUAY-VARINA"]
                 if W >= H else
                 ["HOLLY SPRINGS · CARY · APEX", "RALEIGH · FUQUAY-VARINA"])
    items = []
    for i, ln in enumerate(loc_lines):
        fs = fit_tracked(ln, DM, "SemiBold", P["eyebrow"] * 0.92, 5)
        items.append(dict(type="eyebrow", text=ln, font=font(DM, fs, "SemiBold"),
                          track=5, delay=0.1 + i * 0.12,
                          gap=(P["gap"] * 2 if i == len(loc_lines) - 1 else int(P["gap"] * 0.5))))
    items += [
        dict(type="head", text="Your next customer", font=fh, color=WHITE, delay=0.5),
        dict(type="twotone", text=("is already ", "scrolling."), font=fh, delay=0.85),
    ]
    return items


def brand():
    return [
        dict(type="logo", img=LOGO_BRAND, delay=0.1, gap=P["gap"] * 2),
        dict(type="tagline", text="Where creativity springs growth.",
             font=font(DM, fit("Where creativity springs growth.", DM, "Medium", P["tag"]), "Medium"),
             color=SLATE200, delay=0.7),
        dict(type="eyebrow", text="STRATEGY, NOT GUESSWORK",
             font=font(DM, fit_tracked("STRATEGY, NOT GUESSWORK", DM, "Bold", P["eyebrow"] * 0.86, 5), "Bold"),
             track=5, delay=1.05),
    ]


def service(icon, eyebrow, l1, l2):
    fs = fit(l2 if _scratch.textlength(l2, font=font(SG, P["head"], "Bold")) >
             _scratch.textlength(l1, font=font(SG, P["head"], "Bold")) else l1, SG, "Bold", P["head"])
    fh = font(SG, fs, "Bold")
    return [
        dict(type="icon", fn=icon, size=P["icon"], delay=0.05, gap=P["gap"] * 1.6),
        dict(type="eyebrow", text=eyebrow, font=font(DM, fit_tracked(eyebrow, DM, "Bold", P["eyebrow"], 7), "Bold"),
             track=7, delay=0.35, gap=P["gap"]),
        dict(type="underline", delay=0.45, gap=int(P["gap"] * 0.7)),
        dict(type="head", text=l1, font=fh, color=WHITE, delay=0.6, gap=P["gap"] * 1.3),
        dict(type="head", text=l2, font=fh, color=WHITE, delay=0.85),
    ]


def cta():
    return [
        dict(type="title", text="Clear. Measured. Built to grow.",
             font=font(SG, fit("Clear. Measured. Built to grow.", SG, "Bold", P["title"]), "Bold"),
             color=WHITE, delay=0.1, gap=P["gap"] * 1.8),
        dict(type="logo", img=LOGO_CTA, delay=0.5, gap=P["gap"] * 2),
        dict(type="pill", text="CALL FOR INFO", font=font(DM, P["contact"] + 2, "Bold"),
             w=int(P["W"] * (0.34 if P["W"] > P["H"] else 0.62)), fs=P["contact"] + 2, delay=0.9, gap=P["gap"] * 1.6),
        dict(type="contact", text="(919) 724-4421   ·   springscreativemarketing.com",
             font=font(DM, fit("(919) 724-4421   ·   springscreativemarketing.com", DM, "Medium", P["contact"]), "Medium"),
             color=SLATE200, delay=1.2),
    ]


def beats():
    return [
        (0.0, 5.0, hook()),
        (5.0, 9.5, brand()),
        (9.5, 14.0, service(icon_browser, "WEBSITES", "Modern. Fast.", "Built to convert.")),
        (14.0, 18.5, service(icon_pin, "LOCAL SEO", "Get found locally.", "Clean SEO + smart content.")),
        (18.5, 23.0, service(icon_chat, "SOCIAL", "Sounds like you.", "Brings in real leads.")),
        (23.0, 26.5, service(icon_spark, "THE EDGE", "Practical AI consulting.", "Spot opportunities. Save time.")),
        (26.5, 30.0, cta()),
    ]


def envelope(lt, dur):
    return max(0.0, min(1.0, min(ease_out(lt / 0.45), ease_out((dur - lt) / 0.4))))


def render(fmt: str, music: Path):
    configure(fmt)
    BTS = beats()
    out = ROOT / ("final.mp4" if fmt == "landscape" else "final-vertical.mp4")
    silent = ROOT / f"_silent_{fmt}.mp4"
    n = int(round(DUR * FPS))
    print(f"[{fmt}] rendering {n} frames {W}x{H} …")
    enc = subprocess.Popen([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    for i in range(n):
        t = i / FPS
        img = background(t)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for s, e, items in BTS:
            if s <= t < e:
                render_stack(layer, items, t - s, envelope(t - s, e - s))
                break
        enc.stdin.write(Image.alpha_composite(img, layer).convert("RGB").tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("encode failed")

    print(f"[{fmt}] muxing music + loudnorm …")
    rc = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(silent), "-i", str(music),
        "-filter:a", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", str(out)]).returncode
    if rc != 0:
        raise RuntimeError("mux failed")
    silent.unlink(missing_ok=True)
    print(f"[{fmt}] done → {out.name} ({out.stat().st_size/1e6:.1f} MB)")


def main():
    targets = sys.argv[1:] or ["landscape", "vertical"]
    music = ROOT / "_music.wav"
    print("composing original music bed …")
    compose_music(music)
    for fmt in targets:
        render(fmt, music)
    music.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
