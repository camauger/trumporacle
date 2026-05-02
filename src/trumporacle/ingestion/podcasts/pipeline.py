"""yt-dlp + faster-whisper pipeline (Phase 3 implementation)."""

from __future__ import annotations

from pathlib import Path


def transcribe_audio_file(audio_path: Path, *, model_size: str = "base") -> str:
    """Transcribe a local audio file; returns plain transcript text."""

    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(audio_path))
    return "\n".join(s.text for s in segments).strip()
