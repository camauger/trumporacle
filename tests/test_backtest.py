"""Calibration / PR metrics."""

from __future__ import annotations

import numpy as np

from trumporacle.evaluation.backtest import auc_pr, expected_calibration_error


def test_ece_perfect_calibration() -> None:
    probs = np.array([0.1, 0.2, 0.9, 0.8])
    labels = np.array([0, 0, 1, 1])
    ece = expected_calibration_error(probs, labels, n_bins=2)
    assert ece >= 0.0
    assert ece < 0.25


def test_auc_pr_binary() -> None:
    probs = np.array([0.0, 0.1, 0.9, 1.0])
    labels = np.array([0, 0, 1, 1])
    assert auc_pr(probs, labels) > 0.9
