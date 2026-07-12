"""Springs Creative — B-roll social posts.

Real-photo posts built from the client's own brand imagery (downtown Holly
Springs, Katie's headshot, portfolio work, the SpringSync dashboard) with a
cinematic Ken Burns pan/zoom, a navy legibility scrim, on-brand captions,
Katie's ElevenLabs voiceover (reusing recorded lines), the original music bed,
and the standard "Book your FREE audit" QR end card.

    uv run python samples/springs-creative/broll.py            # all posts, all formats
    uv run python samples/springs-creative/broll.py test       # first post, vertical only

Outputs: out/broll-<post>-<format>.mp4
"""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import build as E
import studio as S
from vo_lines import VO

ROOT = Path(__file__).resolve().parent
BROLL = ROOT / "assets" / "broll"
OUT = ROOT / "out"
FPS = E.FPS

# Each post: id, photo, eyebrow, headline lines, VO key, then mode-specific extras.
#   mode "kb"   — full-frame Ken Burns photo (real photography), focus = pan target
#   mode "card" — screenshot scrolling inside a browser window on the brand gradient
#                 (keeps UI screenshots pixel-crisp instead of soft full-frame blowups)
POSTS = [
    dict(pid="local-pride", photo="holly-springs-downtown.png", mode="kb", focus=(0.45, 0.55),
         eyebrow="HOLLY SPRINGS · THE TRIANGLE", lines=["Your neighbors", "are searching."],
         vo="svc_local-seo"),
    dict(pid="meet-katie", photo="katie-jackson.png", mode="kb", focus=(0.5, 0.32),
         eyebrow="MEET YOUR STRATEGIST", lines=["Katie Jackson"],
         sub="Founder & CEO · Springs Creative Marketing", vo="brand"),
    dict(pid="our-work", photo="portfolio-aiagentvet.png", mode="card",
         eyebrow="OUR WORK · AIAGENTVET.COM", lines=["Websites that", "win customers."],
         vo="svc_websites"),
    dict(pid="ai-advantage", photo="springsync-review-manager.png", mode="card",
         eyebrow="THE AI ADVANTAGE", lines=["5-star reviews,", "on autopilot."],
         vo="svc_ai-edge"),
]


# ---- Ken Burns -------------------------------------------------------------
def cover_rect(src_w, src_h, out_w, out_h):
    """Largest rect of output aspect that fits in the source (centered)."""
    ar = out_w / out_h
    if src_w / src_h > ar:
        h = src_h; w = h * ar
    else:
        w = src_w; h = w / ar
    return w, h


class KenBurns:
    def __init__(self, path: Path, focus, zoom_from=1.0, zoom_to=1.12):
        self.im = Image.open(path).convert("RGB")
        self.focus = focus
        self.z0, self.z1 = zoom_from, zoom_to

    def frame(self, frac: float) -> Image.Image:
        frac = max(0.0, min(1.0, frac))
        e = E.ease_io(frac)
        z = self.z0 + (self.z1 - self.z0) * e
        sw, sh = self.im.size
        bw, bh = cover_rect(sw, sh, E.W, E.H)
        w, h = bw / z, bh / z
        # pan: drift from center toward the focus point
        cx0, cy0 = sw / 2, sh / 2
        cx1, cy1 = self.focus[0] * sw, self.focus[1] * sh
        cx = cx0 + (cx1 - cx0) * e
        cy = cy0 + (cy1 - cy0) * e
        x0 = min(max(cx - w / 2, 0), sw - w)
        y0 = min(max(cy - h / 2, 0), sh - h)
        return self.im.crop((int(x0), int(y0), int(x0 + w), int(y0 + h))).resize((E.W, E.H), Image.LANCZOS)


_scrim_cache = {}


def scrim() -> Image.Image:
    """Bottom navy gradient so captions stay legible over any photo."""
    key = (E.W, E.H)
    if key not in _scrim_cache:
        g = Image.new("L", (1, E.H))
        for y in range(E.H):
            f = max(0.0, (y / E.H - 0.38)) / 0.62
            g.putpixel((0, y), int(235 * (f ** 1.3)))
        alpha = g.resize((E.W, E.H))
        layer = Image.new("RGBA", (E.W, E.H), E.NAVY + (0,))
        layer.putalpha(alpha)
        _scrim_cache[key] = layer
    return _scrim_cache[key]


def broll_scene_text(layer, lt, env, eyebrow, lines, sub=None, base_frac=None):
    d = ImageDraw.Draw(layer)
    if base_frac is None:
        base_frac = 0.80 if E.H > E.W else 0.76
    base = int(E.H * base_frac)
    fh = E.font(E.SG, E.fit(max(lines, key=len), E.SG, "Bold", E.P["head"]), "Bold")
    lh_px = fh.getmetrics()[0] + fh.getmetrics()[1]
    re = E.reveal(lt, 0.25)
    E.tracked_c(d, base - lh_px * len(lines) // 2 - int(lh_px * 0.9), eyebrow,
                E.font(E.DM, E.fit_tracked(eyebrow, E.DM, "Bold", E.P["eyebrow"], 6), "Bold"),
                E.ORANGE, int(255 * env * re), 6, dy=int((1 - re) * 22))
    for i, ln in enumerate(lines):
        r = E.reveal(lt, 0.5 + i * 0.25)
        E.text_c(d, base + (i - (len(lines) - 1) / 2) * lh_px, ln, fh, E.WHITE,
                 255 * env * r, dy=int((1 - r) * 30))
    if sub:
        rs = E.reveal(lt, 0.85)
        fs = E.font(E.DM, E.fit(sub, E.DM, "Medium", E.P["tag"]), "Medium")
        E.text_c(d, base + lh_px * (len(lines) + 0.4) / 2 + int(lh_px * 0.35), sub, fs,
                 E.SLATE200, 255 * env * rs, dy=int((1 - rs) * 24))


class BrowserCard:
    """A screenshot scrolling inside a floating browser window (pixel-crisp)."""

    CHROME = 46  # top bar height

    def __init__(self, path: Path):
        self.shot = Image.open(path).convert("RGB")

    def _geometry(self):
        if E.H > E.W:            # vertical: card in the upper ~55%
            cw = int(E.W * 0.86); ch = int(E.H * 0.46); cy = int(E.H * 0.30)
        elif E.H == E.W:         # square
            cw = int(E.W * 0.80); ch = int(E.H * 0.52); cy = int(E.H * 0.36)
        else:                    # landscape
            cw = int(E.W * 0.56); ch = int(E.H * 0.64); cy = int(E.H * 0.40)
        return cw, ch, cy

    def frame(self, bg: Image.Image, frac: float) -> Image.Image:
        cw, ch, cy = self._geometry()
        sw = self.shot.width
        scale = cw / sw
        img = self.shot.resize((cw, int(self.shot.height * scale)), Image.LANCZOS)
        # never leave blank card below a short screenshot
        ch = min(ch, self.CHROME + img.height)
        x0 = E.W // 2 - cw // 2
        y0 = cy - ch // 2 + int(6 * (1 - E.ease_out(min(1.0, frac * 3))))  # settle-in
        inner_h = ch - self.CHROME
        scroll_max = max(0, img.height - inner_h)
        off = int(scroll_max * E.ease_io(frac))
        view = img.crop((0, off, cw, min(img.height, off + inner_h)))

        card = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
        card.paste(view, (0, self.CHROME))
        d = ImageDraw.Draw(card)
        d.rectangle([0, 0, cw, self.CHROME], fill=(238, 241, 246, 255))
        for i, col in enumerate((E.ORANGE, (255, 200, 80), (120, 200, 140))):
            cx = 26 + i * 30
            d.ellipse([cx - 8, self.CHROME // 2 - 8, cx + 8, self.CHROME // 2 + 8], fill=col)
        # rounded mask + drop shadow
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw, ch], radius=22, fill=255)
        shadow = Image.new("RGBA", (E.W, E.H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([x0 - 6, y0 + 10, x0 + cw + 6, y0 + ch + 18],
                                                 radius=26, fill=(4, 10, 26, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(14))
        out = bg
        out.alpha_composite(shadow)
        out.paste(card, (x0, y0), mask)
        return out


def render_post(post, fmt):
    pid = post["pid"]; photo = post["photo"]; eyebrow = post["eyebrow"]
    lines = post["lines"]; vo_key = post["vo"]; sub = post.get("sub")
    mode = post.get("mode", "kb")
    E.configure(fmt)
    if mode == "card":
        src = BrowserCard(BROLL / photo)
        text_base = 0.80 if E.H > E.W else (0.82 if E.H == E.W else 0.82)
    else:
        src = KenBurns(BROLL / photo, post["focus"])
        text_base = None
    text = VO[vo_key]
    d1 = max(6.0, S.vo(text)[1] + 2.0)
    d2 = max(4.8, S.vo(VO["cta"])[1] + 1.8)
    scenes = [(d1, None, text), (d2, S.cta_audit(), VO["cta"])]
    total = d1 + d2
    out = OUT / f"broll-{pid}-{fmt}.mp4"
    silent = OUT / f"_broll-{pid}-{fmt}.mp4"
    n = int(round(total * FPS))
    print(f"[{pid}/{fmt}] {E.W}x{E.H} {total:.1f}s")
    enc = subprocess.Popen([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{E.W}x{E.H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    n1 = int(round(d1 * FPS))
    for i in range(n):
        t = i / FPS
        if i < n1:
            lt = t
            env = E.envelope(lt, d1)
            if mode == "card":
                img = src.frame(E.background(t), lt / d1)
            else:
                img = src.frame(lt / d1).convert("RGBA")
                img.alpha_composite(scrim())
            layer = Image.new("RGBA", (E.W, E.H), (0, 0, 0, 0))
            broll_scene_text(layer, lt, env, eyebrow, lines, sub=sub, base_frac=text_base)
        else:
            lt = t - d1
            env = E.envelope(lt, d2)
            img = E.background(t)
            layer = Image.new("RGBA", (E.W, E.H), (0, 0, 0, 0))
            E.render_stack(layer, scenes[1][1], lt, env)
        enc.stdin.write(Image.alpha_composite(img, layer).convert("RGB").tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("encode failed")

    track = OUT / f"_broll-{pid}-{fmt}.wav"
    S.build_track(scenes, total, track)
    rc = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(silent), "-i", str(track),
        "-filter:a", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart", str(out)]).returncode
    silent.unlink(missing_ok=True); track.unlink(missing_ok=True)
    if rc != 0:
        raise RuntimeError("mux failed")
    print(f"  → {out.name} ({out.stat().st_size/1e6:.1f} MB)")


def main():
    S.ensure_voice()
    test = len(sys.argv) > 1 and sys.argv[1] == "test"
    formats = ["vertical"] if test else ["landscape", "square", "vertical"]
    posts = POSTS[:1] if test else POSTS
    for fmt in formats:
        for post in posts:
            render_post(post, fmt)


if __name__ == "__main__":
    main()
