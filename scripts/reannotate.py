"""Re-annotate items at the current RUBRIC_VERSION.

Spec §9.8 / §8.3: append-only on valence_annotations. We never delete or
overwrite v1.0 rows; we add v1.1 rows alongside. Items that already have
an annotation at the current rubric version are skipped, so the script is
idempotent and resumable.

Usage:
    uv run python scripts/reannotate.py [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from trumporacle.nlp.annotation.labeler import annotate_valence
from trumporacle.nlp.annotation.rubric import RUBRIC_VERSION
from trumporacle.storage.db import async_session_scope


async def fetch_pending(limit: int | None) -> list[tuple[int, str]]:
    """Items lacking an annotation at the current rubric version."""

    sql = """
        SELECT i.id, i.clean_text
        FROM items i
        WHERE NOT EXISTS (
            SELECT 1 FROM valence_annotations va
            WHERE va.item_id = i.id
              AND va.llm_labeler_version = :ver
        )
        ORDER BY i.id ASC
    """
    if limit is not None:
        sql += " LIMIT :limit"
    async with async_session_scope() as s:
        params: dict[str, object] = {"ver": RUBRIC_VERSION}
        if limit is not None:
            params["limit"] = limit
        rows = (await s.execute(text(sql), params)).all()
    return [(int(r[0]), str(r[1])) for r in rows]


async def write_annotation(
    item_id: int,
    level: int,
    target_type: str | None,
    target_name: str | None,
    confidence: float,
    rationale: str,
) -> None:
    """Insert one valence_annotations row tagged with current rubric version."""

    async with async_session_scope() as s:
        await s.execute(
            text("""
                INSERT INTO valence_annotations (
                    item_id, annotator, valence_level,
                    target_type, target_name, confidence, rationale,
                    llm_labeler_version
                )
                VALUES (:iid, 'llm', :lvl, :ttype, :tname, :conf, :rat, :ver)
            """),
            {
                "iid": item_id,
                "lvl": level,
                "ttype": target_type,
                "tname": target_name,
                "conf": confidence,
                "rat": rationale,
                "ver": RUBRIC_VERSION,
            },
        )


async def main(limit: int | None) -> None:
    pending = await fetch_pending(limit)
    print(f"to re-annotate at {RUBRIC_VERSION}: {len(pending)} items")

    n_done, n_failed = 0, 0
    for idx, (iid, txt) in enumerate(pending, start=1):
        try:
            ann = annotate_valence(txt)
            if ann is None:
                print(f"item {iid}: ANTHROPIC_API_KEY missing — aborting.")
                return
            await write_annotation(
                iid,
                ann.level,
                ann.target_type,
                ann.target_name,
                ann.confidence,
                ann.rationale,
            )
            n_done += 1
        except Exception as e:
            n_failed += 1
            msg = str(e).replace("\n", " ")[:160]
            print(f"item {iid}: {type(e).__name__}: {msg}")

        if idx % 10 == 0 or idx == len(pending):
            print(f"  progress: {idx}/{len(pending)} (ok={n_done} failed={n_failed})")

    print(f"done. new annotations: {n_done}. failed: {n_failed}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap items processed (debug / partial reannotation).",
    )
    args = parser.parse_args()
    asyncio.run(main(args.limit))
