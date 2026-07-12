# video-use — launch demo (sample)

A self-contained demo that exercises the full render pipeline **without any
source footage or ElevenLabs key**. All "footage" is synthesized so the sample
is reproducible from `build.py` alone.

## Session 1 — 2026-06-04

**Strategy:** A 15s vertical (1080×1920 @ 24fps) promo for video-use itself, in
the near-black + orange terminal aesthetic from SKILL.md. Three synthetic source
clips (6s each) stand in for raw takes; the EDL trims each to a 5s window to
demonstrate cutting + lossless concat. One eased PIL alpha overlay (a REC /
timecode / progress-bar HUD) runs the whole output timeline and is composited
PTS-shifted. 2-word UPPERCASE subtitles are burned last. `warm_cinematic` grade.

**Decisions:**
- Sources generated with PIL → ffmpeg (rawvideo pipe), each with a distinct
  sine-chord audio bed so the 30ms fades, concat, and loudnorm operate on real
  audio.
- Overlay encoded as QuickTime Animation (`qtrle` / argb), **not** VP9 — the
  libvpx-vp9 encoder dropped the alpha plane here (decoded back as `yuv420p`),
  which painted the transparent HUD black over the base. `qtrle` carries RGBA
  alpha that ffmpeg's `overlay` filter honors.
- All scene content kept above ~y1050 so it never collides with the subtitle
  safe zone (MarginV=90 → captions ride ~30% up from the bottom).
- Cubic easing everywhere (never linear). Typewriter reveals; nodes appear one
  at a time (never two new things at once).

**Reasoning log:**
- EDL ranges trimmed to [0.40, 5.40] per source — trims a lead-in and a tail
  hold while keeping each scene's animation fully inside the kept window.
- A single continuous HUD overlay doubles as a transition mask — the running
  timecode/progress bar make the hard scene cuts read as intentional.

**Self-eval:** duration 15.04s (matches EDL 3×5.0s). Checked both cut boundaries
(5.0s, 10.0s) — no flash, no carryover. Verified scene/overlay/subtitle layering
at 6 sample points. Audio normalized to -14 LUFS / -1 dBTP.

**Outstanding:** none. To swap in real footage, drop files in a folder and point
the agent at it — this demo only stands in for the transcribe step.
