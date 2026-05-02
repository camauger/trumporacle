"""CLI entry points (ingestion, sampling, training)."""

from __future__ import annotations

import argparse
import asyncio
import json

from loguru import logger

from trumporacle.ingestion.truth_pipeline import ingest_truth_social_once
from trumporacle.orchestration.mvp_tick import run_mvp_tick


async def cmd_ingest_truth() -> None:
    """Fetch Truth Social RSS and persist raw_items + items."""

    from trumporacle.config import get_settings

    annotate = bool(get_settings().anthropic_api_key)
    new_raw, ann_n = await ingest_truth_social_once(annotate_with_llm=annotate)
    logger.info("ingest-truth finished new_raw={} annotations={}", new_raw, ann_n)


def cmd_sample_validation(n: int) -> None:
    """Print a JSON line describing stratified sample sizes (placeholder math)."""

    plan = {
        "per_level_low": n // 7,
        "oversample_high": max(1, n // 10),
        "note": "Wire to DB in Phase 1",
    }
    print(json.dumps(plan))


async def cmd_mvp_tick() -> None:
    """Run ingest + baseline prediction + outcome materialization once."""

    summary = await run_mvp_tick()
    print(json.dumps(summary))


def main() -> None:
    parser = argparse.ArgumentParser(prog="trumporacle")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest-truth", help="Ingest Truth Social via RSS URL")
    p_ingest.set_defaults(func=lambda _a: asyncio.run(cmd_ingest_truth()))

    p_sample = sub.add_parser("sample-validation", help="Stratified validation plan")
    p_sample.add_argument("--n", type=int, default=800)
    p_sample.set_defaults(func=lambda a: cmd_sample_validation(a.n))

    p_tick = sub.add_parser(
        "mvp-tick",
        help="One MVP cycle: ingest (optional RSS), baseline prediction, outcomes",
    )
    p_tick.set_defaults(func=lambda _a: asyncio.run(cmd_mvp_tick()))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
