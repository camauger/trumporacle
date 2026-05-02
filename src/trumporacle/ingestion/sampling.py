"""Stratified validation sampling for Phase 1 LLM rubric calibration (spec §9.5)."""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SamplingItem:
    """One row picked into the validation sample."""

    item_id: int
    clean_text: str
    llm_level: int
    llm_confidence: float | None
    llm_target_type: str | None
    llm_target_name: str | None
    stratum: str


# Spec §9.5: ~100 items per level for 0-3, ~150 for 4-6, +100 low-confidence,
# +100 boundary cases. Default total = 950 (within the 500-1000 range).
DEFAULT_QUOTAS: dict[str, int] = {
    "level_0": 100,
    "level_1": 100,
    "level_2": 100,
    "level_3": 100,
    "level_4": 150,
    "level_5": 150,
    "level_6": 150,
    "low_confidence": 100,
    "boundary": 100,
}
DEFAULT_TOTAL = sum(DEFAULT_QUOTAS.values())

LOW_CONFIDENCE_THRESHOLD = 0.6
# No logits stored (instructor JSON output); we proxy "near boundary" with
# mid-range confidence. Documented assumption in docs/ROADMAP.md.
BOUNDARY_RANGE = (0.6, 0.75)


def scale_quotas(target_n: int) -> dict[str, int]:
    """Return quotas summing to ``target_n``, proportional to ``DEFAULT_QUOTAS``."""

    if target_n >= DEFAULT_TOTAL:
        return dict(DEFAULT_QUOTAS)
    if target_n <= 0:
        return {k: 0 for k in DEFAULT_QUOTAS}
    factor = target_n / DEFAULT_TOTAL
    scaled = {k: max(1, int(v * factor)) for k, v in DEFAULT_QUOTAS.items()}
    diff = target_n - sum(scaled.values())
    if diff != 0:
        keys_sorted = sorted(scaled, key=lambda k: scaled[k], reverse=(diff > 0))
        i = 0
        while diff != 0 and keys_sorted:
            k = keys_sorted[i % len(keys_sorted)]
            step = 1 if diff > 0 else -1
            if scaled[k] + step >= 0:
                scaled[k] += step
                diff -= step
            i += 1
    return scaled


async def fetch_candidates(session: AsyncSession) -> list[dict[str, Any]]:
    """Items with ≥1 LLM annotation, no human annotation, not already in gold_standard.

    Picks the latest LLM annotation per item (rubric versions can stack).
    """

    result = await session.execute(
        text(
            """
            SELECT DISTINCT ON (i.id)
                   i.id            AS item_id,
                   i.clean_text    AS clean_text,
                   va.valence_level AS llm_level,
                   va.confidence   AS llm_confidence,
                   va.target_type  AS llm_target_type,
                   va.target_name  AS llm_target_name
            FROM items i
            JOIN valence_annotations va ON va.item_id = i.id
            WHERE va.annotator LIKE 'llm%'
              AND NOT EXISTS (
                  SELECT 1 FROM valence_annotations vh
                  WHERE vh.item_id = i.id AND vh.annotator NOT LIKE 'llm%'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM gold_standard gs WHERE gs.item_id = i.id
              )
            ORDER BY i.id, va.annotated_at DESC
            """
        )
    )
    return [dict(r) for r in result.mappings().all()]


def stratify(
    candidates: Sequence[dict[str, Any]],
    quotas: dict[str, int],
    *,
    seed: int = 0,
) -> list[SamplingItem]:
    """Sample without replacement: levels first, then low-confidence, then boundary."""

    rng = random.Random(seed)
    by_level: dict[int, list[dict[str, Any]]] = {k: [] for k in range(7)}
    for c in candidates:
        try:
            lvl = int(c["llm_level"])
        except (TypeError, ValueError):
            continue
        if 0 <= lvl <= 6:
            by_level[lvl].append(c)
    for lst in by_level.values():
        rng.shuffle(lst)

    selected_ids: set[int] = set()
    sampled: list[SamplingItem] = []

    def pick(item: dict[str, Any], stratum: str) -> None:
        sampled.append(
            SamplingItem(
                item_id=int(item["item_id"]),
                clean_text=str(item["clean_text"]),
                llm_level=int(item["llm_level"]),
                llm_confidence=(
                    float(item["llm_confidence"]) if item["llm_confidence"] is not None else None
                ),
                llm_target_type=item["llm_target_type"],
                llm_target_name=item["llm_target_name"],
                stratum=stratum,
            )
        )
        selected_ids.add(int(item["item_id"]))

    for lvl in range(7):
        n = quotas.get(f"level_{lvl}", 0)
        for c in by_level[lvl][:n]:
            pick(c, f"level_{lvl}")

    remaining = [c for c in candidates if int(c["item_id"]) not in selected_ids]
    rng.shuffle(remaining)

    n_low = quotas.get("low_confidence", 0)
    if n_low:
        low = [c for c in remaining if (c["llm_confidence"] or 0.0) < LOW_CONFIDENCE_THRESHOLD]
        for c in low[:n_low]:
            pick(c, "low_confidence")

    n_b = quotas.get("boundary", 0)
    if n_b:
        remaining = [c for c in remaining if int(c["item_id"]) not in selected_ids]
        boundary = [
            c
            for c in remaining
            if c["llm_confidence"] is not None
            and BOUNDARY_RANGE[0] <= float(c["llm_confidence"]) <= BOUNDARY_RANGE[1]
        ]
        for c in boundary[:n_b]:
            pick(c, "boundary")

    return sampled


def write_jsonl(items: Sequence[SamplingItem], path: Path) -> None:
    """Emit one JSON line per item; ``human_*`` fields blank for the annotator to fill."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            row = {
                "item_id": it.item_id,
                "stratum": it.stratum,
                "clean_text": it.clean_text,
                "llm_level": it.llm_level,
                "llm_confidence": it.llm_confidence,
                "llm_target_type": it.llm_target_type,
                "llm_target_name": it.llm_target_name,
                "human_level": None,
                "human_target_type": None,
                "human_target_name": None,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
