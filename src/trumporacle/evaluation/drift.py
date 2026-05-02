"""Population stability index (PSI) and simple drift helpers."""

from __future__ import annotations

import numpy as np


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Compute PSI between reference and current distributions."""

    e = np.asarray(expected, dtype=float)
    a = np.asarray(actual, dtype=float)
    if e.size == 0 or a.size == 0:
        return 0.0
    quantiles = np.quantile(e, np.linspace(0, 1, bins + 1))
    quantiles[0] = -np.inf
    quantiles[-1] = np.inf
    e_counts, _ = np.histogram(e, bins=quantiles)
    a_counts, _ = np.histogram(a, bins=quantiles)
    e_pct = (e_counts + 1) / (e_counts.sum() + bins)
    a_pct = (a_counts + 1) / (a_counts.sum() + bins)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))
