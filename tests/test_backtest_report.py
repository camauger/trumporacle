"""Unit tests for backtest report logic (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trumporacle.evaluation.backtest_report import (
    THRESHOLDS,
    WindowRow,
    b1_marginals,
    baselines_for_test,
    compute_target_metrics,
    labels_for_window,
    score_set_for_predictions,
    split_train_test,
)


def _w(
    offset_h: int,
    *,
    v_max: int,
    n_posts: int = 1,
    had_jump: bool = False,
    v_recent: float = 0.0,
    eco: float = 0.0,
    eco_n: int = 0,
) -> WindowRow:
    base = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=offset_h)
    return WindowRow(
        window_start=base,
        window_end=base + timedelta(hours=2),
        v_max=v_max,
        n_posts=n_posts,
        had_jump=had_jump,
        v_recent=v_recent,
        eco_mean_6h=eco,
        eco_n_6h=eco_n,
    )


def test_split_train_test_chronological() -> None:
    windows = [_w(i * 2, v_max=i % 7) for i in range(6)]
    train_until = windows[2].window_end
    train, test = split_train_test(windows, train_until)
    assert len(train) == 3
    assert len(test) == 3
    assert all(w.window_end <= train_until for w in train)
    assert all(w.window_end > train_until for w in test)


def test_b1_marginals_match_observed_rates() -> None:
    train = [
        _w(0, v_max=0, n_posts=1, had_jump=False),
        _w(2, v_max=4, n_posts=2, had_jump=True),
        _w(4, v_max=5, n_posts=0, had_jump=False),
        _w(6, v_max=3, n_posts=1, had_jump=True),
    ]
    m = b1_marginals(train)
    assert m.threshold_rates[3] == 0.75
    assert m.threshold_rates[4] == 0.5
    assert m.threshold_rates[5] == 0.25
    assert m.threshold_rates[6] == 0.0
    assert m.jump_rate == 0.5
    assert m.posts_rate == 0.75


def test_b1_marginals_empty_train_returns_zeros() -> None:
    m = b1_marginals([])
    assert all(v == 0.0 for v in m.threshold_rates.values())
    assert m.jump_rate == 0.0
    assert m.posts_rate == 0.0


def test_baselines_b3_first_test_window_falls_back_to_b1() -> None:
    train: list[WindowRow] = []
    test = [_w(0, v_max=5), _w(2, v_max=2)]
    out = baselines_for_test(train, test)
    first_key = (test[0].window_start, test[0].window_end)
    second_key = (test[1].window_start, test[1].window_end)
    for k in THRESHOLDS:
        col = f"c2_{k}_prob"
        assert out["B3"][first_key][col] == 0.0
    assert out["B3"][second_key]["c2_5_prob"] == 1.0
    assert out["B3"][second_key]["c2_6_prob"] == 0.0


def test_baselines_b2_b4_step_on_continuous_inputs() -> None:
    test = [_w(0, v_max=0, v_recent=4.5, eco=3.7)]
    out = baselines_for_test([], test)
    key = (test[0].window_start, test[0].window_end)
    assert out["B2"][key]["c2_4_prob"] == 1.0
    assert out["B2"][key]["c2_5_prob"] == 0.0
    assert out["B4"][key]["c2_3_prob"] == 1.0
    assert out["B4"][key]["c2_4_prob"] == 0.0


def test_b1_includes_c3_c4_b234_do_not() -> None:
    train = [_w(0, v_max=4, had_jump=True, n_posts=2)]
    test = [_w(2, v_max=0)]
    out = baselines_for_test(train, test)
    key = (test[0].window_start, test[0].window_end)
    assert "c3_prob" in out["B1"][key]
    assert "c4_prob" in out["B1"][key]
    assert "c3_prob" not in out["B2"][key]
    assert "c3_prob" not in out["B3"][key]
    assert "c3_prob" not in out["B4"][key]


def test_compute_target_metrics_c1_uses_mae() -> None:
    metrics = compute_target_metrics("c1", probs=[1.0, 2.0, 3.0], labels=[1, 2, 4])
    assert metrics.target == "c1"
    assert metrics.mae is not None
    assert abs(metrics.mae - (0 + 0 + 1) / 3) < 1e-9
    assert metrics.auc_pr is None
    assert metrics.ece is None


def test_compute_target_metrics_binary_returns_none_when_one_class() -> None:
    metrics = compute_target_metrics("c2_3", probs=[0.9, 0.8, 0.7], labels=[1, 1, 1])
    assert metrics.auc_pr is None
    assert metrics.ece is None
    assert metrics.base_rate == 1.0


def test_compute_target_metrics_binary_perfect() -> None:
    metrics = compute_target_metrics(
        "c2_4",
        probs=[0.9, 0.1, 0.95, 0.05],
        labels=[1, 0, 1, 0],
    )
    assert metrics.auc_pr is not None
    assert metrics.auc_pr > 0.99
    assert metrics.ece is not None
    assert metrics.base_rate == 0.5


def test_score_set_skips_targets_absent_from_predictions() -> None:
    test = [_w(0, v_max=4, n_posts=2, had_jump=True)]
    preds_only_c2 = {
        (test[0].window_start, test[0].window_end): {
            "c2_3_prob": 0.9,
            "c2_4_prob": 0.7,
            "c2_5_prob": 0.2,
            "c2_6_prob": 0.05,
        }
    }
    scores = score_set_for_predictions("B-test", test, preds_only_c2, include_c1=False)
    by_target = {m.target: m for m in scores.metrics}
    assert by_target["c2_4"].n == 1
    assert by_target["c3"].n == 0
    assert by_target["c4"].n == 0


def test_labels_for_window_matches_observation() -> None:
    w = _w(0, v_max=5, n_posts=2, had_jump=True)
    labs = labels_for_window(w)
    assert labs == {
        "c2_3_prob": 1,
        "c2_4_prob": 1,
        "c2_5_prob": 1,
        "c2_6_prob": 0,
        "c3_prob": 1,
        "c4_prob": 1,
    }
