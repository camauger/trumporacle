"""Normalize raw HTML/text into clean_text + token_count."""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser


def strip_html(raw: str) -> str:
    """Remove tags; keep text nodes."""

    tree = HTMLParser(raw)
    text = tree.text(separator="\n")
    return text or ""


_WS = re.compile(r"\s+")


def normalize_text(raw: str, *, is_html: bool = False) -> tuple[str, int]:
    """Return cleaned text and approximate token count (whitespace split)."""

    text = strip_html(raw) if is_html else raw
    text = _WS.sub(" ", text).strip()
    tokens = len(text.split()) if text else 0
    return text, tokens
