"""Text normalization."""

from __future__ import annotations

from trumporacle.nlp.normalize import normalize_text, strip_html


def test_strip_html_basic() -> None:
    assert "Hello" in strip_html("<p>Hello</p>")


def test_normalize_plain() -> None:
    text, n = normalize_text("  a   b  ", is_html=False)
    assert text == "a b"
    assert n == 2
