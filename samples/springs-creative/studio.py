"""Springs Creative — full studio build: main promo + per-service series,
each in landscape / square / vertical, with free neural voiceover (Piper),
ducked original music, and a 'Book your FREE audit' QR end card.

Reuses the rendering engine in build.py (fonts, gradient, stack layout, icons).

    uv run python samples/springs-creative/studio.py test   # main vertical only
    uv run python samples/springs-creative/studio.py         # everything
"""
from __future__ import annotations

import sys
import wave
import hashlib
import subprocess
from math import sin, pi, ceil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import build as E   # the rendering engine (same directory)

ROOT = Path(__file__).resolve().parent
ASSETS = E.ASSETS
VOICES = ROOT / "voices"
VOCACHE = ROOT / "_vo"
OUT = ROOT / "out"
for d in (VOCACHE, OUT):
    d.mkdir(exist_ok=True)

SR = 48000
VOICE = VOICES / "en-us-lessac-medium.onnx"
VOICE_URL = "https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-lessac-medium.tar.gz"


# ---- voiceover (Piper neural TTS, free / local) ----------------------------
def ensure_voice():
    # If every scripted line has ElevenLabs audio, the Piper fallback is unused —
    # skip its download entirely.
    if _TEXT2KEY and all(_eleven_for(t) for t in _TEXT2KEY):
        print("voiceover: ElevenLabs audio found for all lines — skipping Piper download")
        return
    if VOICE.exists():
        return
    VOICES.mkdir(exist_ok=True)
    tgz = VOICES / "v.tgz"
    subprocess.run(["curl", "-fsSL", VOICE_URL, "-o", str(tgz)], check=True)
    subprocess.run(["tar", "xzf", str(tgz), "-C", str(VOICES)], check=True)
    tgz.unlink(missing_ok=True)


def _load48(path: Path):
    with wave.open(str(path)) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    if sr != SR:
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * SR / sr)),
                      np.arange(len(a)), a)
    return a


_vo_cache: dict = {}


try:
    from vo_lines import VO as _VO_LINES
    _TEXT2KEY = {v: k for k, v in _VO_LINES.items()}
except Exception:
    _TEXT2KEY = {}
ELEVEN_DIR = ROOT / "vo_eleven"   # ElevenLabs audio (your voice), if generated


def _eleven_for(text: str):
    key = _TEXT2KEY.get(text)
    if not key:
        return None
    for ext in (".mp3", ".wav", ".m4a"):
        p = ELEVEN_DIR / f"{key}{ext}"
        if p.exists():
            return p
    return None


def vo(text: str):
    """Synthesize a line → (samples@48k mono, duration_s). Cached on disk.

    Prefers your ElevenLabs audio (vo_eleven/<key>.<ext>) when present; otherwise
    falls back to the free local Piper voice.
    """
    if text in _vo_cache:
        return _vo_cache[text]
    h = hashlib.md5(text.encode()).hexdigest()[:12]
    src = _eleven_for(text)
    wav = VOCACHE / f"{h}_{'el' if src else 'pp'}.wav"   # separate caches per source
    if not wav.exists():
        if src:  # decode ElevenLabs mp3/m4a → 48k mono wav
            subprocess.run(["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", str(SR), str(wav)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:    # free Piper voice
            subprocess.run([sys.executable, "-m", "piper", "--model", str(VOICE),
                            "--output_file", str(wav)], input=text.encode(),
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    a = _load48(wav)
    _vo_cache[text] = (a, len(a) / SR)
    return _vo_cache[text]


# ---- original music bed (parametric duration) ------------------------------
def _midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def compose_music(dur: float):
    n = int(dur * SR)
    L = np.zeros(n); R = np.zeros(n)
    rng = np.random.default_rng(7)
    bar = 2.5; beat = bar / 4
    chords = [(38, [50, 54, 57], [50, 54, 57, 62]), (33, [45, 49, 52], [45, 49, 52, 57]),
              (35, [47, 50, 54], [47, 50, 54, 59]), (31, [43, 47, 50], [43, 47, 50, 55])]

    def add(buf, sig, start):
        s = int(start * SR); e = min(n, s + len(sig))
        if e > s:
            buf[s:e] += sig[:e - s]

    for b in range(ceil(dur / bar)):
        root, triad, arp = chords[b % 4]
        t0 = b * bar; bl = int(bar * SR); tt = np.arange(bl) / SR
        env = np.clip(np.minimum(tt / 0.5, (bar - tt) / 0.5), 0, 1) ** 0.8
        pad = np.zeros(bl)
        for nt in triad:
            f = _midi(nt); pad += np.sin(2 * pi * f * tt) + 0.5 * np.sin(2 * pi * f * 1.005 * tt)
        pad *= env * 0.05
        add(L, pad, t0); add(R, pad, t0)
        f = _midi(root); benv = np.minimum(tt / 0.05, 1) * np.clip((bar - tt) / 0.4, 0, 1)
        bass = (np.sin(2 * pi * f * tt) + 0.4 * np.sin(2 * pi * f * 0.5 * tt)) * benv * 0.10
        add(L, bass, t0); add(R, bass, t0)
        for k in range(8):
            nt = arp[k % len(arp)] + (12 if k >= 4 else 0); f = _midi(nt)
            pl = int(0.32 * SR); pt = np.arange(pl) / SR; penv = np.exp(-pt * 7)
            pluck = (np.sin(2 * pi * f * pt) + 0.4 * np.sin(2 * pi * 2 * f * pt)) * penv * 0.06
            pan = 0.5 + 0.35 * sin(k)
            add(L, pluck * (1 - pan), t0 + k * beat / 2); add(R, pluck * pan, t0 + k * beat / 2)
        for k in range(4):
            kl = int(0.14 * SR); kt = np.arange(kl) / SR
            kick = np.sin(2 * pi * (120 * np.exp(-kt * 18) + 48) * kt) * np.exp(-kt * 16) * 0.16
            add(L, kick, t0 + k * beat); add(R, kick, t0 + k * beat)
            hl = int(0.05 * SR)
            hat = rng.standard_normal(hl) * np.exp(-np.arange(hl) / SR * 90) * 0.02
            add(L, hat, t0 + k * beat + beat / 2); add(R, hat, t0 + k * beat + beat / 2)
    return np.stack([L, R], 1)


def build_track(scenes, total, out_wav: Path):
    """scenes: list of (dur, items, vo_text|None). Mix ducked music + VO."""
    n = int(total * SR)
    vt = np.zeros(n)
    cur = 0.0
    for dur, _items, line in scenes:
        if line:
            samp, _d = vo(line)
            s = int((cur + 0.35) * SR); e = min(n, s + len(samp))
            if e > s:
                vt[s:e] += samp[:e - s]
        cur += dur
    music = compose_music(total)[:n]
    # duck music where VO is present
    present = (np.abs(vt) > 0.02).astype(np.float32)
    k = np.ones(int(0.08 * SR)) / int(0.08 * SR)
    duck = 1.0 - 0.6 * np.clip(np.convolve(present, k, "same"), 0, 1)
    L = music[:, 0] * duck + vt * 0.95
    R = music[:, 1] * duck + vt * 0.95
    st = np.tanh(np.stack([L, R], 1) * 1.2)
    t = np.arange(n) / SR
    st *= np.clip(t / 0.8, 0, 1)[:, None] * np.clip((total - t) / 0.8, 0, 1)[:, None]
    st /= max(1e-6, np.max(np.abs(st))) / 0.95
    data = (np.clip(st, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())


# ---- QR end-card image (white rounded card + QR) ---------------------------
def qr_card(px: int) -> Image.Image:
    qr = Image.open(ASSETS / "qr-audit.png").convert("RGB").resize((px, px), Image.NEAREST)
    pad = int(px * 0.12); card = px + 2 * pad
    im = Image.new("RGBA", (card, card), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, card, card], radius=int(card * 0.10), fill=(255, 255, 255, 255))
    im.paste(qr, (pad, pad))
    return im


# ---- CTA beat (Book your FREE audit + QR) ----------------------------------
def cta_audit():
    px = int(min(E.W, E.H) * 0.30)
    card = qr_card(px)
    return [
        dict(type="title", text="Book your FREE audit",
             font=E.font(E.SG, E.fit("Book your FREE audit", E.SG, "Bold", E.P["title"]), "Bold"),
             color=E.ORANGE, delay=0.1, gap=E.P["gap"] * 1.4),
        dict(type="logo", img=card, delay=0.45, gap=E.P["gap"] * 1.5),
        dict(type="contact", text="Scan to book your free marketing audit",
             font=E.font(E.DM, E.fit("Scan to book your free marketing audit", E.DM, "Medium", E.P["contact"]), "Medium"),
             color=E.WHITE, delay=0.95, gap=int(E.P["gap"] * 0.7)),
        dict(type="contact", text="(919) 724-4421   ·   springscreativemarketing.com",
             font=E.font(E.DM, E.fit("(919) 724-4421   ·   springscreativemarketing.com", E.DM, "Medium", E.P["contact"] * 0.92), "Medium"),
             color=E.SLATE200, delay=1.15),
    ]


# ---- compositions (built per-format so layout adapts) ----------------------
SERVICES = [
    ("websites", E.icon_browser, "WEBSITES", "Modern. Fast.", "Built to convert.",
     "Your website is your first impression. We build sites that are modern, fast, and built to convert."),
    ("local-seo", E.icon_pin, "LOCAL SEO", "Get found locally.", "Clean SEO + content.",
     "When your neighbors search, be the first name they find, with clean local SEO and smart content."),
    ("social", E.icon_chat, "SOCIAL", "Sounds like you.", "Brings in real leads.",
     "Your brand has a voice. We run social campaigns that sound like you, and bring in real leads."),
    ("ai-edge", E.icon_spark, "THE EDGE", "Practical AI.", "Spot. Save time.",
     "Want an edge? We use practical AI to spot opportunities and save you time."),
]


def main_scenes():
    return [
        (5.0, E.hook(), "Your next customer is already scrolling."),
        (4.5, E.brand(), "Springs Creative Marketing. Strategy, not guesswork."),
        (4.5, E.service(E.icon_browser, "WEBSITES", "Modern. Fast.", "Built to convert."),
         "Websites that feel modern, load fast, and convert."),
        (4.0, E.service(E.icon_pin, "LOCAL SEO", "Get found locally.", "Clean SEO + content."),
         "We sharpen your local search with clean SEO."),
        (4.0, E.service(E.icon_chat, "SOCIAL", "Sounds like you.", "Brings in real leads."),
         "Social that sounds like you, and brings in real leads."),
        (3.5, E.service(E.icon_spark, "THE EDGE", "Practical AI.", "Spot. Save time."),
         "Plus practical AI to spot opportunities and save time."),
        (4.5, cta_audit(), "Book your free marketing audit today."),
    ]


def service_scenes(icon, eyebrow, l1, l2, pitch):
    d1 = max(5.0, vo(pitch)[1] + 1.6)
    d2 = max(4.8, vo("Book your free marketing audit today.")[1] + 1.8)
    return [
        (d1, E.service(icon, eyebrow, l1, l2), pitch),
        (d2, cta_audit(), "Book your free marketing audit today."),
    ]


# ---- render ----------------------------------------------------------------
def render_comp(name, fmt, scenes):
    total = sum(s[0] for s in scenes)
    starts = []
    acc = 0.0
    for dur, _i, _v in scenes:
        starts.append(acc); acc += dur
    out = OUT / f"{name}-{fmt}.mp4"
    silent = OUT / f"_{name}-{fmt}.mp4"
    nfr = int(round(total * E.FPS))
    print(f"[{name}/{fmt}] {E.W}x{E.H} {total:.1f}s ({nfr}f)")
    enc = subprocess.Popen([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{E.W}x{E.H}", "-r", str(E.FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    for i in range(nfr):
        t = i / E.FPS
        si = max(j for j, s0 in enumerate(starts) if s0 <= t + 1e-6)
        dur, items, _v = scenes[si]
        lt = t - starts[si]
        img = E.background(t)
        layer = Image.new("RGBA", (E.W, E.H), (0, 0, 0, 0))
        E.render_stack(layer, items, lt, E.envelope(lt, dur))
        enc.stdin.write(Image.alpha_composite(img, layer).convert("RGB").tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("encode failed")

    track = OUT / f"_{name}-{fmt}.wav"
    build_track(scenes, total, track)
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
    ensure_voice()
    test = len(sys.argv) > 1 and sys.argv[1] == "test"
    formats = ["vertical"] if test else ["landscape", "square", "vertical"]
    for fmt in formats:
        E.configure(fmt)
        render_comp("main", fmt, main_scenes())
        if test:
            break
        for sid, icon, eb, l1, l2, pitch in SERVICES:
            render_comp(sid, fmt, service_scenes(icon, eb, l1, l2, pitch))


if __name__ == "__main__":
    main()
