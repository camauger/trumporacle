"""Inter-annotator agreement (Cohen's kappa, ordinal MAE)."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import cohen_kappa_score, mean_absolute_error


def cohens_kappa(levels_a: list[int], levels_b: list[int]) -> float:
    """Cohen's kappa on paired ordinal labels."""

    if len(levels_a) != len(levels_b) or not levels_a:
        return 0.0
    return float(cohen_kappa_score(levels_a, levels_b, weights=None))


def ordinal_mae(levels_a: list[int], levels_b: list[int]) -> float:
    """Mean absolute error between paired integer levels."""

    if not levels_a:
        return 0.0
    return float(mean_absolute_error(np.asarray(levels_a), np.asarray(levels_b)))
