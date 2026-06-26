#!/usr/bin/env python3
"""
make_vo.py — generate the Springs Creative voiceover in YOUR ElevenLabs voice.

Runs on your Mac (the cloud build env can't reach ElevenLabs). It writes one
audio file per line into  vo_eleven/  ; you commit + push those, and the cloud
rebuild drops them into the videos in place of the free voice.

------------------------------------------------------------------------------
ONE-TIME in the ElevenLabs app (to "sound like you")
------------------------------------------------------------------------------
  Voices -> Add a new voice -> Instant Voice Clone -> upload 1-3 minutes of you
  speaking clearly. That creates your voice. (Your API key alone can't clone you.)

------------------------------------------------------------------------------
THEN on your Mac (inside the repo)
------------------------------------------------------------------------------
  cd ~/Desktop/video-use
  export ELEVENLABS_API_KEY="sk_your_key"          # stays on your Mac only
  python3 samples/springs-creative/make_vo.py voices      # find your voice's id
  export ELEVEN_VOICE_ID="paste-your-voice-id"
  python3 samples/springs-creative/make_vo.py gen          # writes vo_eleven/*.mp3
  git add samples/springs-creative/vo_eleven
  git commit -m "Add my ElevenLabs voiceover" && git push

Then tell Claude (web) to rebuild the videos with your voice.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Run:  python3 -m pip install requests")

from vo_lines import VO  # same directory

BASE = "https://api.elevenlabs.io"
OUT = Path(__file__).resolve().parent / "vo_eleven"
MODEL = "eleven_multilingual_v2"   # high quality; supports cloned voices


def key():
    k = (os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY") or "").strip()
    if not k:
        sys.exit("Set ELEVENLABS_API_KEY (export ELEVENLABS_API_KEY=sk_...).")
    return k


def cmd_voices(_):
    r = requests.get(f"{BASE}/v1/voices", headers={"xi-api-key": key()}, timeout=30)
    if r.status_code >= 300:
        sys.exit(f"voices failed [{r.status_code}]: {r.text[:300]}")
    print("Your ElevenLabs voices (use the id of your cloned voice):\n")
    for v in r.json().get("voices", []):
        print(f"  {v.get('voice_id')}   {v.get('name')}   ({v.get('category')})")
    print("\nThen:  export ELEVEN_VOICE_ID=<id>   and run:  make_vo.py gen")


def cmd_gen(_):
    voice = os.environ.get("ELEVEN_VOICE_ID", "").strip()
    if not voice:
        sys.exit("Set ELEVEN_VOICE_ID first (run 'voices' to find your cloned voice's id).")
    OUT.mkdir(exist_ok=True)
    hd = {"xi-api-key": key(), "Content-Type": "application/json", "Accept": "audio/mpeg"}
    for k, text in VO.items():
        body = {
            "text": text,
            "model_id": MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.85,
                               "style": 0.0, "use_speaker_boost": True},
        }
        r = requests.post(f"{BASE}/v1/text-to-speech/{voice}", headers=hd, json=body, timeout=120)
        if r.status_code >= 300:
            sys.exit(f"TTS failed for '{k}' [{r.status_code}]: {r.text[:300]}")
        (OUT / f"{k}.mp3").write_bytes(r.content)
        print(f"  ✓ {k}.mp3")
    print(f"\nDone — {len(VO)} files in {OUT}. Commit + push, then ask Claude to rebuild.")


def main():
    cmds = {"voices": cmd_voices, "gen": cmd_gen}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("usage: make_vo.py [voices|gen]")
    cmds[sys.argv[1]](sys.argv)


if __name__ == "__main__":
    main()
