"""Frozen list of ecosystem RSS feeds for Phase 3 (spec §6.1).

Edit this module to add/remove sources. ``name`` is the slug stored in
``sources.name`` and used as the unique key by ``get_or_create_source``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RSSFeed:
    """One ecosystem RSS source."""

    name: str
    url: str
    label: str


ECOSYSTEM_FEEDS: tuple[RSSFeed, ...] = (
    RSSFeed(
        name="rss_breitbart",
        url="https://feeds.feedburner.com/breitbart",
        label="Breitbart",
    ),
    RSSFeed(
        name="rss_gateway_pundit",
        url="https://www.thegatewaypundit.com/feed/",
        label="Gateway Pundit",
    ),
    RSSFeed(
        name="rss_federalist",
        url="https://thefederalist.com/feed/",
        label="The Federalist",
    ),
)
