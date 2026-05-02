# Datasheet (TRUMPORACLE)

Template aligned with Gebru et al. (2018). Fill before public release.

## Motivation

- **Purpose**: Monitor and estimate calibrated probabilities of rhetorical valence escalation in public posts (spec `trumporacle.mdc`).
- **Creators**: Christian Mauger (initial design, May 2026).

## Composition

- **Sources**: Truth Social (Trump + allies), Telegram MAGA channels, Fox transcripts, RSS articles, MAGA podcasts (see spec section 6).
- **Labels**: Ordinal valence 0–6 via LLM rubric + human stratified validation + frozen gold subset.

## Collection process

- **Ingestion**: `ingestion/*` modules; append-only `raw_items` / `items`.
- **Known limitations**: Scraping fragility, English-centric rubric, no exogenous event prediction.

## Recommended uses

- Research, journalism, media monitoring — not automated public targeting.

## Maintenance

- Re-training cadence: monthly + drift-driven (spec section 12).
- Contact: maintainers documented in repository metadata when published.
