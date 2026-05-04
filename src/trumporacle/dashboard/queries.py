"""Data accessors for the ``/escalation-now`` dashboard view.

Pure read-only queries; each function takes an ``AsyncSession`` and returns
plain dataclasses suitable for Jinja2 / JSON serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trumporacle.prediction.time_grid import prediction_window

ACTIVE_MODEL_VERSION = "mvp-baseline-b4soft-001"
HISTORY_DAYS = 7
ESCALATION_THRESHOLD = 3
ESCALATION_LIMIT = 3
CALIBRATION_BINS = 10


@dataclass(frozen=True, slots=True)
class CurrentPrediction:
    """Latest prediction for the 2h-aligned window covering ``now``."""

    window_start: datetime
    window_end: datetime
    made_at: datetime
    model_version: str
    c2_3: float
    c2_4: float
    c2_5: float
    c2_6: float
    c3: float
    c4: float


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    """One window's predicted probs + observed outcome (if closed)."""

    window_start_iso: str
    window_start_ts: float  # epoch seconds, easy to consume in JS
    c2_4: float | None
    c2_5: float | None
    v_max: int | None  # None if outcome not materialized yet
    n_posts: int | None


@dataclass(frozen=True, slots=True)
class EscalationEvent:
    """A closed window where ``v_max >= ESCALATION_THRESHOLD``."""

    window_start: datetime
    window_end: datetime
    v_max: int
    n_posts: int
    had_jump: bool
    posts: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    """One bin of a calibration plot."""

    bin_lo: float
    bin_hi: float
    predicted_mean: float
    observed_rate: float
    n: int


@dataclass(frozen=True, slots=True)
class CalibrationData:
    """Per-target calibration plot + ECE."""

    target: str  # 'c2_4' or 'c2_5'
    bins: list[CalibrationBin] = field(default_factory=list)
    ece: float = 0.0
    n_total: int = 0


async def fetch_current_prediction(
    session: AsyncSession, now: datetime
) -> CurrentPrediction | None:
    """Latest prediction for the window ``[H, H+2h]`` aligned to the 15-min grid."""

    h0, h1 = prediction_window(now, window_hours=2)
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT prediction_made_at, window_start, window_end, model_version,
                       c2_3_prob, c2_4_prob, c2_5_prob, c2_6_prob, c3_prob, c4_prob
                FROM predictions
                WHERE window_start = :ws AND window_end = :we
                  AND model_version = :mv
                ORDER BY prediction_made_at DESC
                LIMIT 1
                """
                ),
                {"ws": h0, "we": h1, "mv": ACTIVE_MODEL_VERSION},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return CurrentPrediction(
        window_start=row["window_start"],
        window_end=row["window_end"],
        made_at=row["prediction_made_at"],
        model_version=str(row["model_version"]),
        c2_3=float(row["c2_3_prob"] or 0.0),
        c2_4=float(row["c2_4_prob"] or 0.0),
        c2_5=float(row["c2_5_prob"] or 0.0),
        c2_6=float(row["c2_6_prob"] or 0.0),
        c3=float(row["c3_prob"] or 0.0),
        c4=float(row["c4_prob"] or 0.0),
    )


async def fetch_history(
    session: AsyncSession, now: datetime, days: int = HISTORY_DAYS
) -> list[HistoryPoint]:
    """Predictions ⨝ outcomes over the last ``days`` days, ordered chronologically."""

    cutoff = now - timedelta(days=days)
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT p.window_start, p.c2_4_prob, p.c2_5_prob,
                       o.v_max, o.n_posts
                FROM predictions p
                LEFT JOIN outcomes o
                  ON o.window_start = p.window_start AND o.window_end = p.window_end
                WHERE p.window_start >= :cutoff AND p.model_version = :mv
                ORDER BY p.window_start ASC
                """
                ),
                {"cutoff": cutoff, "mv": ACTIVE_MODEL_VERSION},
            )
        )
        .mappings()
        .all()
    )
    out: list[HistoryPoint] = []
    for r in rows:
        ws: datetime = r["window_start"]
        out.append(
            HistoryPoint(
                window_start_iso=ws.isoformat(),
                window_start_ts=ws.timestamp(),
                c2_4=float(r["c2_4_prob"]) if r["c2_4_prob"] is not None else None,
                c2_5=float(r["c2_5_prob"]) if r["c2_5_prob"] is not None else None,
                v_max=int(r["v_max"]) if r["v_max"] is not None else None,
                n_posts=int(r["n_posts"]) if r["n_posts"] is not None else None,
            )
        )
    return out


async def fetch_recent_escalations(
    session: AsyncSession,
    threshold: int = ESCALATION_THRESHOLD,
    limit: int = ESCALATION_LIMIT,
) -> list[EscalationEvent]:
    """Last ``limit`` closed windows with ``v_max >= threshold`` + the actual posts."""

    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT window_start, window_end, v_max, n_posts, had_jump
                FROM outcomes
                WHERE v_max >= :thr
                ORDER BY window_start DESC
                LIMIT :lim
                """
                ),
                {"thr": threshold, "lim": limit},
            )
        )
        .mappings()
        .all()
    )

    events: list[EscalationEvent] = []
    for r in rows:
        posts_rows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT i.clean_text
                    FROM raw_items r
                    JOIN items i ON i.raw_item_id = r.id
                    JOIN sources s ON s.id = r.source_id
                    WHERE COALESCE(s.metadata->>'trump_primary', 'false') = 'true'
                      AND r.published_at >= :ws AND r.published_at < :we
                    ORDER BY r.published_at ASC
                    LIMIT 5
                    """
                    ),
                    {"ws": r["window_start"], "we": r["window_end"]},
                )
            )
            .mappings()
            .all()
        )
        posts = [str(p["clean_text"])[:280] for p in posts_rows]
        events.append(
            EscalationEvent(
                window_start=r["window_start"],
                window_end=r["window_end"],
                v_max=int(r["v_max"]),
                n_posts=int(r["n_posts"]),
                had_jump=bool(r["had_jump"]),
                posts=posts,
            )
        )
    return events


async def fetch_calibration(
    session: AsyncSession,
    target: str,
    n_bins: int = CALIBRATION_BINS,
    days: int = HISTORY_DAYS * 4,  # 4 weeks for stable bins
) -> CalibrationData:
    """Bin predictions vs observed outcomes for ``target`` (``c2_4`` or ``c2_5``).

    Uses fixed-width bins on [0, 1]. Bins with zero windows are dropped from
    the returned list. ``ece`` is the count-weighted absolute deviation
    between predicted_mean and observed_rate.
    """

    if target not in {"c2_3", "c2_4", "c2_5", "c2_6"}:
        raise ValueError(f"unknown target {target!r}")
    threshold = int(target.split("_")[1])
    prob_col = f"{target}_prob"

    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows = (
        (
            await session.execute(
                text(
                    f"""
                SELECT p.{prob_col} AS prob, o.v_max
                FROM predictions p
                JOIN outcomes o
                  ON o.window_start = p.window_start AND o.window_end = p.window_end
                WHERE p.window_start >= :cutoff
                  AND p.model_version = :mv
                  AND p.{prob_col} IS NOT NULL
                """
                ),
                {"cutoff": cutoff, "mv": ACTIVE_MODEL_VERSION},
            )
        )
        .mappings()
        .all()
    )

    if not rows:
        return CalibrationData(target=target, bins=[], ece=0.0, n_total=0)

    pairs = [(float(r["prob"]), 1 if int(r["v_max"]) >= threshold else 0) for r in rows]
    n_total = len(pairs)

    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    bins: list[CalibrationBin] = []
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        last = i == n_bins - 1
        bucket = [(p, y) for p, y in pairs if (lo <= p < hi or (last and p == hi))]
        if not bucket:
            continue
        pred = sum(p for p, _ in bucket) / len(bucket)
        obs = sum(y for _, y in bucket) / len(bucket)
        bins.append(
            CalibrationBin(
                bin_lo=lo,
                bin_hi=hi,
                predicted_mean=pred,
                observed_rate=obs,
                n=len(bucket),
            )
        )
        ece += (len(bucket) / n_total) * abs(pred - obs)

    return CalibrationData(target=target, bins=bins, ece=ece, n_total=n_total)
