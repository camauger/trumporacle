"""Unit tests for κ + MAE + bias report (spec §9.6)."""

from __future__ import annotations

from trumporacle.evaluation.validation_report import (
    BIAS_MAX_ABS,
    KAPPA_GLOBAL_MIN,
    MAE_MAX,
    compute_report,
)


def test_empty_dataset_returns_no_go() -> None:
    report = compute_report([])
    assert report.decision == "no_go"
    assert report.failures == ["empty_dataset"]
    assert report.n_paired == 0


def test_perfect_agreement_is_go() -> None:
    pairs = [(i, lvl, lvl) for i, lvl in enumerate([0, 1, 2, 3, 4, 4, 5, 5, 6, 6])]
    report = compute_report(pairs)
    assert report.decision == "go"
    assert report.failures == []
    assert report.kappa_global == 1.0
    assert report.mae_ordinal == 0.0
    assert report.signed_bias == 0.0
    assert report.n_high_levels == 6


def test_strong_disagreement_is_no_go() -> None:
    pairs = [(i, 0, 6) for i in range(20)] + [(i + 100, 6, 0) for i in range(20)]
    report = compute_report(pairs)
    assert report.decision == "no_go"
    assert any("kappa_global" in f for f in report.failures)
    assert any("mae_ordinal" in f for f in report.failures)


def test_signed_bias_is_llm_minus_human() -> None:
    pairs = [(i, 4, 3) for i in range(10)]
    report = compute_report(pairs)
    assert report.signed_bias == 1.0
    assert any("abs_bias" in f for f in report.failures)


def test_no_high_levels_does_not_force_failure_on_high_kappa() -> None:
    pairs = [(i, lvl, lvl) for i, lvl in enumerate([0, 1, 2, 3] * 5)]
    report = compute_report(pairs)
    assert report.n_high_levels == 0
    assert "kappa_levels_4_6" not in " ".join(report.failures)


def test_thresholds_match_spec() -> None:
    assert KAPPA_GLOBAL_MIN == 0.70
    assert MAE_MAX == 0.60
    assert BIAS_MAX_ABS == 0.30
