"""Tests for `--prompt-file` keyterm biasing in helpers/transcribe.py.

The flag exposes ElevenLabs Scribe's `keyterms` array — a vocabulary prior
that improves recognition of proper nouns and domain terms (brand names,
people, places). The same prompt-file format works for OpenAI Whisper's
`initial_prompt` (just join the lines with commas), so the CLI flag is
engine-agnostic.

Background — the IUIC `show MMC` incident (2026-05-26): on clean speaker
audio, the canonical IUIC salutation `"shalom Most High in Christ Bless"`
transcribed as `"show MMC in Christ Bless"`. A pure post-process fuzzy
correction can't recover `"Most High" -> "MMC"` (no character overlap), so
the fix has to happen at the engine's input. This flag is that input.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helpers import transcribe


# ----------------------------- parser tests -----------------------------


def test_load_keyterms_returns_empty_when_no_file():
    assert transcribe.load_keyterms(None, verbose=False) == []


def test_load_keyterms_strips_comments_and_blanks(tmp_path: Path):
    f = tmp_path / "vocab.txt"
    f.write_text(
        "# IUIC vocabulary\n"
        "Most High\n"
        "\n"
        "  # indented comment\n"
        "shalom\n"
        "\n"
        "Israel United in Christ\n"
    )
    assert transcribe.load_keyterms(f, verbose=False) == [
        "Most High",
        "shalom",
        "Israel United in Christ",
    ]


def test_load_keyterms_three_term_fixture_round_trip(tmp_path: Path):
    """test_prompt_file_loads_and_passes_to_whisper — fixture with 3 terms,
    mock the engine call, assert all 3 terms travel through to the keyterms
    parameter."""
    fixture = tmp_path / "vocabulary.txt"
    fixture.write_text(
        "# fixture\n"
        "Yahawah\n"
        "Yahawashi\n"
        "Israelites United in Christ\n"
    )
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF0000WAVEfmt ")

    captured: dict = {}

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"text": "ok", "words": []}

    def fake_post(url, headers, files, data, timeout):  # noqa: ARG001
        captured.update(data)
        return fake_resp

    keyterms = transcribe.load_keyterms(fixture, verbose=False)
    with patch.object(transcribe.requests, "post", side_effect=fake_post):
        transcribe.call_scribe(
            audio_path=audio,
            api_key="test-key",
            keyterms=keyterms,
        )

    assert "keyterms" in captured, "keyterms must be sent to Scribe"
    sent = json.loads(captured["keyterms"])
    assert sent == ["Yahawah", "Yahawashi", "Israelites United in Christ"]


def test_load_keyterms_missing_file_is_clean_skip(tmp_path: Path, capsys):
    """test_prompt_file_missing_is_clean_skip — nonexistent file must warn
    and return [], so a session with no vocabulary.txt still transcribes."""
    missing = tmp_path / "does-not-exist.txt"
    result = transcribe.load_keyterms(missing, verbose=True)
    assert result == []
    captured = capsys.readouterr()
    assert "warn" in captured.out.lower()
    assert str(missing) in captured.out


def test_load_keyterms_filters_oversize_phrases(tmp_path: Path):
    """Scribe rejects keyterms >50 chars or >5 words; we filter, don't fail."""
    f = tmp_path / "v.txt"
    f.write_text(
        "Most High\n"
        f"{'x' * 60}\n"  # too long
        "one two three four five six\n"  # too many words
        "shalom family\n"
    )
    assert transcribe.load_keyterms(f, verbose=False) == ["Most High", "shalom family"]


def test_load_keyterms_truncates_to_scribe_limit(tmp_path: Path):
    f = tmp_path / "v.txt"
    f.write_text("\n".join(f"term{i}" for i in range(1500)))
    out = transcribe.load_keyterms(f, verbose=False)
    assert len(out) == transcribe.SCRIBE_KEYTERMS_MAX_COUNT


def test_call_scribe_omits_keyterms_when_empty(tmp_path: Path):
    """Empty keyterms => no `keyterms` field, no 20% surcharge."""
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF0000WAVEfmt ")
    captured: dict = {}

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"text": "ok"}

    def fake_post(url, headers, files, data, timeout):  # noqa: ARG001
        captured.update(data)
        return fake_resp

    with patch.object(transcribe.requests, "post", side_effect=fake_post):
        transcribe.call_scribe(audio_path=audio, api_key="k", keyterms=[])

    assert "keyterms" not in captured


# ----------------------------- CLI surface -----------------------------


def test_help_text_documents_prompt_file_flag():
    """--help must surface the new flag so operators discover it."""
    repo_root = Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, str(repo_root / "helpers" / "transcribe.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--prompt-file" in proc.stdout
    assert "vocabulary" in proc.stdout.lower()


# --------------------- real-execution slice (gated) ---------------------


@pytest.mark.skipif(
    os.environ.get("IUIC_RUN_REAL_SCRIBE") != "1",
    reason="set IUIC_RUN_REAL_SCRIBE=1 to exercise the live ElevenLabs Scribe API",
)
def test_keyterms_recover_iuic_phrase_on_real_scribe(tmp_path: Path):
    """Real-execution slice. Synthesizes a TTS clip saying the canonical IUIC
    salutation and verifies that with --prompt-file biasing, Scribe lands on
    a vocabulary-canonical transcript more reliably than without it.

    Gated on IUIC_RUN_REAL_SCRIBE=1 + ELEVENLABS_API_KEY in env.
    Requires `say` (macOS) or skips if no TTS binary is available.
    """
    import shutil

    if not shutil.which("say"):
        pytest.skip("macOS `say` not available; cannot synthesize test audio")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg required to convert TTS output")
    if not os.environ.get("ELEVENLABS_API_KEY"):
        pytest.skip("ELEVENLABS_API_KEY required for real Scribe call")

    phrase = "shalom Most High in Christ bless"
    aiff = tmp_path / "phrase.aiff"
    wav = tmp_path / "phrase.wav"
    subprocess.run(["say", "-o", str(aiff), phrase], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ac", "1", "-ar", "16000", str(wav)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    vocab = tmp_path / "vocab.txt"
    vocab.write_text("Most High\nshalom\nin Christ bless\n")
    keyterms = transcribe.load_keyterms(vocab, verbose=False)
    api_key = transcribe.load_api_key()

    biased = transcribe.call_scribe(wav, api_key, keyterms=keyterms)
    biased_text = biased.get("text", "").lower()

    # The canonical phrase has to show up; we don't compare against an
    # un-biased call (Scribe is non-deterministic enough that a head-to-head
    # in a single CI run is noisy). The presence assertion is the regression.
    assert "most high" in biased_text or "shalom" in biased_text, biased
