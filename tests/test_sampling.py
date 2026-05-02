"""Unit tests for stratified validation sampling (spec §9.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trumporacle.ingestion.sampling import (
    DEFAULT_QUOTAS,
    DEFAULT_TOTAL,
    scale_quotas,
    stratify,
    write_jsonl,
)


def _candidate(item_id: int, level: int, conf: float | None) -> dict:
    return {
        "item_id": item_id,
        "clean_text": f"text-{item_id}",
        "llm_level": level,
        "llm_confidence": conf,
        "llm_target_type": "person",
        "llm_target_name": None,
    }


def test_scale_quotas_full_target_returns_default() -> None:
    assert scale_quotas(DEFAULT_TOTAL) == DEFAULT_QUOTAS


def test_scale_quotas_smaller_target_sums_to_target() -> None:
    target = 200
    out = scale_quotas(target)
    assert sum(out.values()) == target
    assert all(v >= 0 for v in out.values())


def test_scale_quotas_zero_or_negative() -> None:
    assert sum(scale_quotas(0).values()) == 0
    assert sum(scale_quotas(-5).values()) == 0


def test_stratify_respects_quotas_when_pool_is_large_enough() -> None:
    candidates: list[dict] = []
    next_id = 1
    for lvl in range(7):
        for _ in range(300):
            candidates.append(_candidate(next_id, lvl, 0.9))
            next_id += 1
    for _ in range(150):
        candidates.append(_candidate(next_id, 2, 0.5))
        next_id += 1
    for _ in range(150):
        candidates.append(_candidate(next_id, 2, 0.7))
        next_id += 1

    quotas = dict(DEFAULT_QUOTAS)
    sampled = stratify(candidates, quotas, seed=42)

    by_stratum: dict[str, int] = {}
    for it in sampled:
        by_stratum[it.stratum] = by_stratum.get(it.stratum, 0) + 1

    for lvl in range(7):
        assert by_stratum.get(f"level_{lvl}", 0) == quotas[f"level_{lvl}"]
    assert by_stratum.get("low_confidence", 0) == quotas["low_confidence"]
    assert by_stratum.get("boundary", 0) == quotas["boundary"]

    assert len({it.item_id for it in sampled}) == len(sampled)


def test_stratify_underfills_when_pool_is_small() -> None:
    candidates = [_candidate(i, 0, 0.9) for i in range(1, 11)]
    quotas = scale_quotas(50)
    sampled = stratify(candidates, quotas, seed=0)
    assert len(sampled) <= 10
    assert all(it.stratum == "level_0" for it in sampled)


def test_stratify_low_confidence_picks_below_threshold() -> None:
    candidates = [_candidate(i, 0, 0.95) for i in range(1, 21)] + [
        _candidate(i, 0, 0.4) for i in range(101, 121)
    ]
    quotas = {f"level_{lvl}": 0 for lvl in range(7)}
    quotas["level_0"] = 5
    quotas["low_confidence"] = 5
    quotas["boundary"] = 0
    sampled = stratify(candidates, quotas, seed=1)
    low = [it for it in sampled if it.stratum == "low_confidence"]
    assert len(low) == 5
    assert all(it.llm_confidence is not None and it.llm_confidence < 0.6 for it in low)


def test_stratify_seed_is_deterministic() -> None:
    candidates = [_candidate(i, i % 7, 0.8) for i in range(1, 200)]
    a = stratify(candidates, scale_quotas(50), seed=7)
    b = stratify(candidates, scale_quotas(50), seed=7)
    assert [it.item_id for it in a] == [it.item_id for it in b]


def test_write_jsonl_roundtrip(tmp_path: Path) -> None:
    candidates = [_candidate(i, i % 7, 0.8) for i in range(1, 30)]
    sampled = stratify(candidates, scale_quotas(20), seed=3)
    path = tmp_path / "sample.jsonl"
    write_jsonl(sampled, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(sampled)
    rec = json.loads(lines[0])
    assert {"item_id", "stratum", "llm_level", "human_level"} <= set(rec)
    assert rec["human_level"] is None


@pytest.mark.parametrize("target", [10, 100, 500, 950, 1500])
def test_scale_quotas_sum_equals_target_when_under_default(target: int) -> None:
    out = scale_quotas(target)
    expected = min(target, DEFAULT_TOTAL)
    assert sum(out.values()) == expected
