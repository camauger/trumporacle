"""Closed captions + Whisper fallback (Phase 2 wiring)."""

from __future__ import annotations

from pathlib import Path


def segment_transcript(text: str, *, max_chars: int = 1200) -> list[str]:
    """Split transcript into ~2–5 minute proxy chunks by character budget."""

    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in text.split("\n\n"):
        p = para.strip()
        if not p:
            continue
        if size + len(p) > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf = [p]
            size = len(p)
        else:
            buf.append(p)
            size += len(p) + 2
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def load_caption_file(path: Path) -> str:
    """Read a raw caption/transcript file from disk."""

    return path.read_text(encoding="utf-8", errors="replace")
