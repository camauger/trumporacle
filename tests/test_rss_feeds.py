"""Smoke tests on the ecosystem RSS feed list (data, not network)."""

from __future__ import annotations

from urllib.parse import urlparse

from trumporacle.ingestion.rss.feeds import ECOSYSTEM_FEEDS


def test_at_least_one_feed_configured() -> None:
    assert len(ECOSYSTEM_FEEDS) >= 1


def test_feed_names_are_unique() -> None:
    names = [f.name for f in ECOSYSTEM_FEEDS]
    assert len(names) == len(set(names))


def test_feed_urls_look_like_https_urls() -> None:
    for f in ECOSYSTEM_FEEDS:
        parsed = urlparse(f.url)
        assert parsed.scheme in {"http", "https"}, f.url
        assert parsed.netloc, f.url


def test_feed_slugs_use_rss_prefix() -> None:
    for f in ECOSYSTEM_FEEDS:
        assert f.name.startswith("rss_"), f.name


def test_feed_label_non_empty() -> None:
    for f in ECOSYSTEM_FEEDS:
        assert f.label.strip()
