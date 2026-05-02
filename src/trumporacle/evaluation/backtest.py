"""Backtest metrics for binary escalation targets (AUC-PR, ECE)."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    """ECE for binary probabilities (spec 10.5)."""

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(probs)
    if n == 0:
        return 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (probs >= lo) & (probs < hi if i < n_bins - 1 else probs <= hi)
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        conf = float(probs[mask].mean())
        acc = float(labels[mask].mean())
        ece += (cnt / n) * abs(acc - conf)
    return float(ece)


def auc_pr(probs: np.ndarray, labels: np.ndarray) -> float:
    """Average precision (AUC-PR)."""

    if len(np.unique(labels)) < 2:
        return 0.0
    return float(average_precision_score(labels, probs))


def pr_curve(probs: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Precision-recall curve arrays."""

    precision, recall, thresholds = precision_recall_curve(labels, probs)
    return precision, recall, thresholds
