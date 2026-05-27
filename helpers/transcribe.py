"""Transcribe a video with ElevenLabs Scribe.

Extracts mono 16kHz audio via ffmpeg, uploads to Scribe with verbatim +
diarize + audio events + word-level timestamps, writes the full response
to <edit_dir>/transcripts/<video_stem>.json.

Cached: if the output file already exists, the upload is skipped.

Usage:
    python helpers/transcribe.py <video_path>
    python helpers/transcribe.py <video_path> --edit-dir /custom/edit
    python helpers/transcribe.py <video_path> --language en
    python helpers/transcribe.py <video_path> --num-speakers 2
    python helpers/transcribe.py <video_path> --prompt-file vocabulary.txt
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests


SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"

# ElevenLabs Scribe `keyterms` constraints (see API docs).
SCRIBE_KEYTERM_MAX_CHARS = 50
SCRIBE_KEYTERM_MAX_WORDS = 5
SCRIBE_KEYTERMS_MAX_COUNT = 1000


def load_api_key() -> str:
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "ELEVENLABS_API_KEY":
                    return v.strip().strip('"').strip("'")
    v = os.environ.get("ELEVENLABS_API_KEY", "")
    if not v:
        sys.exit("ELEVENLABS_API_KEY not found in .env or environment")
    return v


def load_keyterms(prompt_file: Path | None, verbose: bool = True) -> list[str]:
    """Load vocabulary-biasing keyterms from a prompt file.

    Parses the file ignoring `#` comments and blank lines. Returns a list of
    phrases suitable for ElevenLabs Scribe's `keyterms` parameter. The same
    file format ("one phrase per line, # comments") is also a good fit for
    OpenAI Whisper's `initial_prompt` (just join with commas).

    Skips silently with a warning if the file is missing — a session whose
    genre ships no vocabulary.txt should still transcribe successfully.

    Filters terms that exceed Scribe's per-keyterm limits (50 chars, 5 words)
    and truncates the total list to SCRIBE_KEYTERMS_MAX_COUNT (1000).
    """
    if prompt_file is None:
        return []

    if not prompt_file.exists():
        if verbose:
            print(
                f"  warn: --prompt-file not found ({prompt_file}); transcribing without keyterm bias",
                flush=True,
            )
        return []

    raw_lines = prompt_file.read_text().splitlines()
    phrases: list[str] = []
    skipped_oversize = 0
    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        word_count = len(stripped.split())
        if len(stripped) > SCRIBE_KEYTERM_MAX_CHARS or word_count > SCRIBE_KEYTERM_MAX_WORDS:
            skipped_oversize += 1
            continue
        phrases.append(stripped)

    if len(phrases) > SCRIBE_KEYTERMS_MAX_COUNT:
        if verbose:
            print(
                f"  warn: --prompt-file has {len(phrases)} phrases; truncating to "
                f"{SCRIBE_KEYTERMS_MAX_COUNT} (Scribe limit)",
                flush=True,
            )
        phrases = phrases[:SCRIBE_KEYTERMS_MAX_COUNT]

    if verbose:
        suffix = f" (skipped {skipped_oversize} oversize)" if skipped_oversize else ""
        print(f"  keyterms: {len(phrases)} loaded from {prompt_file.name}{suffix}", flush=True)

    return phrases


def extract_audio(video_path: Path, dest: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def call_scribe(
    audio_path: Path,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,
    keyterms: list[str] | None = None,
) -> dict:
    data: dict[str, str] = {
        "model_id": "scribe_v1",
        "diarize": "true",
        "tag_audio_events": "true",
        "timestamps_granularity": "word",
    }
    if language:
        data["language_code"] = language
    if num_speakers:
        data["num_speakers"] = str(num_speakers)
    if keyterms:
        # Scribe accepts `keyterms` as a JSON-encoded array of strings when
        # sent over multipart/form-data.
        data["keyterms"] = json.dumps(keyterms)

    with open(audio_path, "rb") as f:
        resp = requests.post(
            SCRIBE_URL,
            headers={"xi-api-key": api_key},
            files={"file": (audio_path.name, f, "audio/wav")},
            data=data,
            timeout=1800,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Scribe returned {resp.status_code}: {resp.text[:500]}")

    return resp.json()


def transcribe_one(
    video: Path,
    edit_dir: Path,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,
    keyterms: list[str] | None = None,
    verbose: bool = True,
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    Cached: returns existing path immediately if the transcript already exists.
    """
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{video.stem}.json"

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    if verbose:
        print(f"  extracting audio from {video.name}", flush=True)

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / f"{video.stem}.wav"
        extract_audio(video, audio)
        size_mb = audio.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"  uploading {video.stem}.wav ({size_mb:.1f} MB)", flush=True)
        payload = call_scribe(audio, api_key, language, num_speakers, keyterms)

    out_path.write_text(json.dumps(payload, indent=2))
    dt = time.time() - t0

    if verbose:
        kb = out_path.stat().st_size / 1024
        print(f"  saved: {out_path.name} ({kb:.1f} KB) in {dt:.1f}s")
        if isinstance(payload, dict) and "words" in payload:
            print(f"    words: {len(payload['words'])}")

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video with ElevenLabs Scribe")
    ap.add_argument("video", type=Path, help="Path to video file")
    ap.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit output directory (default: <video_parent>/edit)",
    )
    ap.add_argument(
        "--language",
        type=str,
        default=None,
        help="Optional ISO language code (e.g., 'en'). Omit to auto-detect.",
    )
    ap.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Optional number of speakers when known. Improves diarization accuracy.",
    )
    ap.add_argument(
        "--prompt-file",
        type=Path,
        default=None,
        help=(
            "Optional vocabulary file (one phrase per line, '#' for comments). "
            "Phrases are passed as ElevenLabs Scribe `keyterms` to bias "
            "transcription toward proper nouns / domain terms (e.g. brand names, "
            "people, places). Missing file is a warn+skip, not an error. "
            "Equivalent semantics to Whisper's --initial-prompt; the same file "
            "format works for both engines."
        ),
    )
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    api_key = load_api_key()
    keyterms = load_keyterms(args.prompt_file)

    transcribe_one(
        video=video,
        edit_dir=edit_dir,
        api_key=api_key,
        language=args.language,
        num_speakers=args.num_speakers,
        keyterms=keyterms,
    )


if __name__ == "__main__":
    main()
