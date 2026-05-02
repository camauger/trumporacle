"""MVP baseline predictor: soft probabilities from ecosystem + Trump persistence (not trained)."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from trumporacle.dashboard.metrics import PREDICTIONS_WRITTEN
from trumporacle.prediction.mvp_features import MvpFeatures, fetch_mvp_features
from trumporacle.prediction.time_grid import prediction_window

MVP_MODEL_VERSION = "mvp-baseline-b4soft-001"
MVP_FEATURE_SET_VERSION = "fs_mvp_001"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def features_to_probs(f: MvpFeatures) -> dict[str, float]:
    """Map features to rough calibrated-ish probabilities for C2.k, C3, C4, C1."""

    eco = f.ecosystem_mean_valence_6h
    tr = f.trump_mean_valence_24h
    rate = f.trump_posts_6h / 6.0 if f.trump_posts_6h else 0.0
    c4 = float(min(0.95, max(0.02, 1.0 - math.exp(-2.0 * max(rate, 0.01)))))

    def thr_prob(k: int) -> float:
        z = 1.1 * (eco - (k - 0.75)) + 0.35 * (tr - (k - 1.25))
        return float(min(0.99, max(0.01, _sigmoid(z))))

    c2_3 = thr_prob(3)
    c2_4 = thr_prob(4)
    c2_5 = thr_prob(5)
    c2_6 = thr_prob(6)
    jump_z = (eco - tr) - 1.25 + 0.1 * (f.trump_posts_6h - 2)
    c3 = float(min(0.99, max(0.01, _sigmoid(jump_z))))
    c1 = float(min(6.0, max(0.0, 0.55 * eco + 0.45 * tr)))
    return {
        "c1_value": c1,
        "c2_3_prob": c2_3,
        "c2_4_prob": c2_4,
        "c2_5_prob": c2_5,
        "c2_6_prob": c2_6,
        "c3_prob": c3,
        "c4_prob": c4,
    }


def feature_hash_payload(f: MvpFeatures) -> tuple[str, dict[str, Any]]:
    """SHA256 of canonical JSON for traceability (spec 10.7)."""

    payload = {k: v for k, v in asdict(f).items()}
    for key, val in payload.items():
        if isinstance(val, datetime):
            payload[key] = val.astimezone(UTC).isoformat()
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest(), payload


async def write_baseline_prediction(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> bool:
    """Insert one baseline prediction row for the aligned window if missing."""

    now = now or datetime.now(tz=UTC)
    h, w_end = prediction_window(now, window_hours=2)
    feats = await fetch_mvp_features(session, h)
    fhash, raw_payload = feature_hash_payload(feats)
    probs = features_to_probs(feats)

    dup = await session.execute(
        text(
            """
            SELECT id FROM predictions
            WHERE window_start = :ws AND window_end = :we AND model_version = :mv
            LIMIT 1
            """
        ),
        {"ws": h, "we": w_end, "mv": MVP_MODEL_VERSION},
    )
    if dup.scalar_one_or_none() is not None:
        return False

    await session.execute(
        text(
            """
            INSERT INTO predictions (
                prediction_made_at,
                window_start,
                window_end,
                model_version,
                feature_hash,
                feature_set_version,
                c1_value,
                c2_3_prob,
                c2_4_prob,
                c2_5_prob,
                c2_6_prob,
                c3_prob,
                c4_prob,
                payload
            )
            VALUES (
                :made_at,
                :ws,
                :we,
                :mv,
                :fh,
                :fsv,
                :c1,
                :c23,
                :c24,
                :c25,
                :c26,
                :c3,
                :c4,
                CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "made_at": now.astimezone(UTC),
            "ws": h,
            "we": w_end,
            "mv": MVP_MODEL_VERSION,
            "fh": fhash,
            "fsv": MVP_FEATURE_SET_VERSION,
            "c1": probs["c1_value"],
            "c23": probs["c2_3_prob"],
            "c24": probs["c2_4_prob"],
            "c25": probs["c2_5_prob"],
            "c26": probs["c2_6_prob"],
            "c3": probs["c3_prob"],
            "c4": probs["c4_prob"],
            "payload": json.dumps({"features": raw_payload, "probs": probs}),
        },
    )
    PREDICTIONS_WRITTEN.inc()
    return True
