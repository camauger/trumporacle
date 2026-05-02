"""Property tests for temporal leakage invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from trumporacle.evaluation.baselines import rolling_mean_valence

utc = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 1, 1),
    timezones=st.just(UTC),
)


@given(
    st.lists(
        st.tuples(utc, st.integers(min_value=0, max_value=6)),
        min_size=1,
        max_size=30,
    ),
    utc,
    st.integers(min_value=1, max_value=48),
)
def test_rolling_mean_only_uses_past(values, cutoff, hours) -> None:
    """Mean at cutoff must ignore events strictly after cutoff."""

    series = [(t, int(v)) for t, v in values]
    m = rolling_mean_valence(series, cutoff, hours=hours)
    manual = [v for ts, v in series if (cutoff - timedelta(hours=hours)) < ts <= cutoff]
    if manual:
        assert abs(m - sum(manual) / len(manual)) < 1e-9
    else:
        assert m == 0.0
