"""Isotonic calibration (spec D10 / section 10.5)."""

from __future__ import annotations

from typing import cast

import numpy as np
from sklearn.isotonic import IsotonicRegression


def fit_isotonic(probs: np.ndarray, labels: np.ndarray) -> IsotonicRegression:
    """Fit isotonic regression mapping raw probabilities to calibrated scores."""

    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(probs.astype(float), labels.astype(float))
    return ir


def apply_isotonic(model: IsotonicRegression, probs: np.ndarray) -> np.ndarray:
    """Apply fitted isotonic mapping."""

    pred = model.predict(probs.astype(float))
    return cast(np.ndarray, np.clip(pred, 0.0, 1.0))
