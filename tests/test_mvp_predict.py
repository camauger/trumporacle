"""MVP baseline mapping tests (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime

from trumporacle.prediction.mvp_features import MvpFeatures
from trumporacle.prediction.mvp_predict import feature_hash_payload, features_to_probs


def test_features_to_probs_in_unit_interval() -> None:
    h = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    f = MvpFeatures(
        h=h,
        ecosystem_mean_valence_6h=4.0,
        ecosystem_n_6h=10,
        trump_mean_valence_24h=3.5,
        trump_n_24h=5,
        trump_posts_6h=3,
    )
    p = features_to_probs(f)
    for key in ("c2_3_prob", "c2_4_prob", "c2_5_prob", "c2_6_prob", "c3_prob", "c4_prob"):
        assert 0.0 < p[key] < 1.0
    assert 0.0 <= p["c1_value"] <= 6.0


def test_feature_hash_stable() -> None:
    h = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    f = MvpFeatures(
        h=h,
        ecosystem_mean_valence_6h=2.0,
        ecosystem_n_6h=1,
        trump_mean_valence_24h=1.0,
        trump_n_24h=1,
        trump_posts_6h=0,
    )
    a, _ = feature_hash_payload(f)
    b, _ = feature_hash_payload(f)
    assert a == b
