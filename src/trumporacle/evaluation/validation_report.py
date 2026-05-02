"""Phase 1 LLM-rubric validation: Cohen's κ, ordinal MAE, signed bias (spec §9.6)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trumporacle.evaluation.agreement import cohens_kappa, ordinal_mae

KAPPA_GLOBAL_MIN = 0.70
KAPPA_HIGH_LEVELS_MIN = 0.50
MAE_MAX = 0.60
BIAS_MAX_ABS = 0.30


@dataclass(frozen=True)
class ValidationReport:
    """Structured report on (LLM, human) annotation agreement."""

    n_paired: int
    n_high_levels: int
    kappa_global: float
    kappa_high_levels: float
    mae_ordinal: float
    signed_bias: float
    decision: str
    failures: list[str]

    def to_dict(self) -> dict[str, object]:
        """Plain dict for JSON serialization."""

        return asdict(self)


async def fetch_paired_annotations(session: AsyncSession) -> list[tuple[int, int, int]]:
    """Return ``(item_id, llm_level, human_level)`` for items annotated by both.

    Picks the latest annotation of each kind per item (rubric versions can stack).
    """

    result = await session.execute(
        text(
            """
            WITH latest_llm AS (
                SELECT DISTINCT ON (item_id)
                       item_id, valence_level
                FROM valence_annotations
                WHERE annotator LIKE 'llm%'
                ORDER BY item_id, annotated_at DESC
            ),
            latest_human AS (
                SELECT DISTINCT ON (item_id)
                       item_id, valence_level
                FROM valence_annotations
                WHERE annotator NOT LIKE 'llm%'
                ORDER BY item_id, annotated_at DESC
            )
            SELECT l.item_id AS item_id,
                   l.valence_level AS llm_level,
                   h.valence_level AS human_level
            FROM latest_llm l
            JOIN latest_human h ON h.item_id = l.item_id
            """
        )
    )
    rows = result.mappings().all()
    return [(int(r["item_id"]), int(r["llm_level"]), int(r["human_level"])) for r in rows]


def _safe_kappa(a: list[int], b: list[int]) -> float:
    """``cohens_kappa`` returns NaN when one rater has a single class; force 0.0."""

    k = cohens_kappa(a, b)
    if math.isnan(k):
        return 0.0
    return k


def compute_report(pairs: list[tuple[int, int, int]]) -> ValidationReport:
    """Compute κ + MAE + bias and apply spec §9.6 thresholds to set ``decision``."""

    if not pairs:
        return ValidationReport(
            n_paired=0,
            n_high_levels=0,
            kappa_global=0.0,
            kappa_high_levels=0.0,
            mae_ordinal=0.0,
            signed_bias=0.0,
            decision="no_go",
            failures=["empty_dataset"],
        )

    llm = [p[1] for p in pairs]
    hum = [p[2] for p in pairs]
    high_pairs = [(li, hi) for li, hi in zip(llm, hum, strict=True) if hi >= 4]
    high_llm = [p[0] for p in high_pairs]
    high_hum = [p[1] for p in high_pairs]

    k_global = _safe_kappa(llm, hum)
    k_high = _safe_kappa(high_llm, high_hum) if len(high_llm) >= 2 else 0.0
    mae = ordinal_mae(llm, hum)
    bias = sum(li - hi for li, hi in zip(llm, hum, strict=True)) / len(llm)

    failures: list[str] = []
    if k_global < KAPPA_GLOBAL_MIN:
        failures.append(f"kappa_global<{KAPPA_GLOBAL_MIN}")
    if len(high_llm) >= 2 and k_high < KAPPA_HIGH_LEVELS_MIN:
        failures.append(f"kappa_levels_4_6<{KAPPA_HIGH_LEVELS_MIN}")
    if mae >= MAE_MAX:
        failures.append(f"mae_ordinal>={MAE_MAX}")
    if abs(bias) >= BIAS_MAX_ABS:
        failures.append(f"abs_bias>={BIAS_MAX_ABS}")

    if not failures:
        decision = "go"
    elif len(failures) >= 3:
        decision = "no_go"
    else:
        decision = "partial"

    return ValidationReport(
        n_paired=len(pairs),
        n_high_levels=len(high_llm),
        kappa_global=k_global,
        kappa_high_levels=k_high,
        mae_ordinal=mae,
        signed_bias=bias,
        decision=decision,
        failures=failures,
    )
