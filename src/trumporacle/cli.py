"""CLI entry points (ingestion, sampling, training)."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger

from trumporacle.ingestion.truth_pipeline import ingest_truth_social_once
from trumporacle.orchestration.mvp_tick import run_mvp_tick


async def cmd_ingest_truth() -> None:
    """Fetch Truth Social RSS and persist raw_items + items."""

    from trumporacle.config import get_settings

    annotate = bool(get_settings().anthropic_api_key)
    new_raw, ann_n = await ingest_truth_social_once(annotate_with_llm=annotate)
    logger.info("ingest-truth finished new_raw={} annotations={}", new_raw, ann_n)


async def cmd_backfill_truth(since: date, until: date, base_url: str | None) -> None:
    """Calendar-month backfill of Trump's Truth RSS into raw_items + items."""

    from trumporacle.ingestion.backfill import backfill_truth_social

    summary = await backfill_truth_social(since=since, until=until, base_url=base_url)
    print(json.dumps(summary))


async def cmd_ingest_rss() -> None:
    """Fetch ecosystem RSS feeds and persist raw_items + items + LLM annotations."""

    from trumporacle.config import get_settings
    from trumporacle.ingestion.rss.pipeline import ingest_rss_ecosystem_once

    annotate = bool(get_settings().anthropic_api_key)
    summary = await ingest_rss_ecosystem_once(annotate_with_llm=annotate)
    print(json.dumps(summary))


async def cmd_sample_validation(n: int, out: Path | None, seed: int) -> None:
    """Stratified validation sample (spec §9.5) drawn from DB; optional JSONL export."""

    from trumporacle.ingestion.sampling import (
        DEFAULT_TOTAL,
        fetch_candidates,
        scale_quotas,
        stratify,
        write_jsonl,
    )
    from trumporacle.storage.db import async_session_scope

    quotas = scale_quotas(n)
    async with async_session_scope() as session:
        candidates = await fetch_candidates(session)

    sampled = stratify(candidates, quotas, seed=seed)
    by_stratum: dict[str, int] = {}
    for it in sampled:
        by_stratum[it.stratum] = by_stratum.get(it.stratum, 0) + 1

    summary = {
        "candidates_in_pool": len(candidates),
        "target_n": n,
        "default_total": DEFAULT_TOTAL,
        "quotas": quotas,
        "sampled": len(sampled),
        "by_stratum": by_stratum,
        "out": str(out) if out else None,
    }
    if out is not None:
        write_jsonl(sampled, out)
    print(json.dumps(summary))


async def cmd_validation_report(out: Path | None) -> None:
    """Compute kappa / MAE / bias on paired LLM-human annotations and print the verdict."""

    from trumporacle.evaluation.validation_report import (
        compute_report,
        fetch_paired_annotations,
    )
    from trumporacle.storage.db import async_session_scope

    async with async_session_scope() as session:
        pairs = await fetch_paired_annotations(session)

    report = compute_report(pairs)
    payload = report.to_dict()
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload))


async def cmd_evaluate_baseline(
    since: datetime,
    until: datetime,
    train_until: datetime | None,
    out: Path | None,
) -> None:
    """Backtest the MVP baseline + B1/B2/B3/B4 on closed prediction windows."""

    from trumporacle.evaluation.backtest_report import build_backtest_report
    from trumporacle.storage.db import async_session_scope

    async with async_session_scope() as session:
        report = await build_backtest_report(
            session, since=since, until=until, train_until=train_until
        )
    payload = report.to_dict()
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, default=str))


async def cmd_mvp_tick() -> None:
    """Run ingest + baseline prediction + outcome materialization once."""

    summary = await run_mvp_tick()
    print(json.dumps(summary))


def _parse_year_month(value: str) -> date:
    """Accept ``YYYY-MM`` (anchored to first of month)."""

    try:
        y, m = value.split("-", 1)
        return date(int(y), int(m), 1)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM, got: {value!r}") from exc


def _parse_iso_date_utc(value: str) -> datetime:
    """Accept ``YYYY-MM-DD`` and anchor to 00:00 UTC."""

    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM-DD, got: {value!r}") from exc
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser(prog="trumporacle")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest-truth", help="Ingest Truth Social via RSS URL")
    p_ingest.set_defaults(func=lambda _a: asyncio.run(cmd_ingest_truth()))

    p_rss = sub.add_parser(
        "ingest-rss",
        help="Ingest ecosystem RSS feeds (Breitbart, Gateway Pundit, Federalist)",
    )
    p_rss.set_defaults(func=lambda _a: asyncio.run(cmd_ingest_rss()))

    p_backfill = sub.add_parser(
        "backfill-truth",
        help="Calendar-month backfill of Trump's Truth RSS (--since/--until YYYY-MM)",
    )
    p_backfill.add_argument("--since", type=_parse_year_month, required=True)
    p_backfill.add_argument("--until", type=_parse_year_month, required=True)
    p_backfill.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Override TRUTH_SOCIAL_RSS_URL; query start_date/end_date are replaced.",
    )
    p_backfill.set_defaults(
        func=lambda a: asyncio.run(cmd_backfill_truth(a.since, a.until, a.base_url))
    )

    p_sample = sub.add_parser(
        "sample-validation",
        help="Stratified validation sample drawn from DB (spec section 9.5)",
    )
    p_sample.add_argument("--n", type=int, default=950)
    p_sample.add_argument(
        "--out", type=Path, default=None, help="Optional JSONL export for human annotation."
    )
    p_sample.add_argument("--seed", type=int, default=0)
    p_sample.set_defaults(func=lambda a: asyncio.run(cmd_sample_validation(a.n, a.out, a.seed)))

    p_report = sub.add_parser(
        "validation-report",
        help="Cohen's kappa + MAE + bias on paired LLM/human annotations (spec section 9.6)",
    )
    p_report.add_argument("--out", type=Path, default=None)
    p_report.set_defaults(func=lambda a: asyncio.run(cmd_validation_report(a.out)))

    p_eval = sub.add_parser(
        "evaluate-baseline",
        help="Backtest predictions vs B1/B2/B3/B4 on closed windows (spec section 10.3-10.5)",
    )
    p_eval.add_argument("--since", type=_parse_iso_date_utc, required=True)
    p_eval.add_argument("--until", type=_parse_iso_date_utc, required=True)
    p_eval.add_argument(
        "--train-until",
        type=_parse_iso_date_utc,
        default=None,
        help="Chronological split (default: midpoint of available windows).",
    )
    p_eval.add_argument("--out", type=Path, default=None)
    p_eval.set_defaults(
        func=lambda a: asyncio.run(cmd_evaluate_baseline(a.since, a.until, a.train_until, a.out))
    )

    p_tick = sub.add_parser(
        "mvp-tick",
        help="One MVP cycle: ingest (optional RSS), baseline prediction, outcomes",
    )
    p_tick.set_defaults(func=lambda _a: asyncio.run(cmd_mvp_tick()))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
