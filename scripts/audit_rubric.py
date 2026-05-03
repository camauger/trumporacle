"""Analyze a manually-annotated rubric audit JSONL.

Reads `artifacts/rubric_audit.jsonl` (or path passed as argv[1]) where each
line has `llm_level` and `human_level` filled in. Prints:

    - confusion matrix LLM vs human
    - signed bias (LLM - human)
    - Cohen's kappa + ordinal MAE on the audited subset
    - explicit list of mismatches, especially around the level-4 boundary

Usage:
    uv run python scripts/audit_rubric.py [path/to/rubric_audit.jsonl]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from trumporacle.evaluation.agreement import cohens_kappa, ordinal_mae


def main(path: Path) -> int:
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 2

    pairs: list[tuple[int, int, dict]] = []
    skipped = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("human_level") is None:
                skipped += 1
                continue
            try:
                lvl_h = int(row["human_level"])
                lvl_l = int(row["llm_level"])
            except (TypeError, ValueError):
                skipped += 1
                continue
            pairs.append((lvl_l, lvl_h, row))

    if not pairs:
        print(f"no annotated rows in {path} (skipped {skipped} unannotated)", file=sys.stderr)
        return 1

    n = len(pairs)
    llm = [p[0] for p in pairs]
    hum = [p[1] for p in pairs]

    print(f"{path}\n{'=' * len(str(path))}")
    print(f"n_annotated: {n}    n_skipped(no human_level): {skipped}\n")

    # --- Confusion matrix ----------------------------------------------------
    levels = list(range(7))
    cm = Counter(zip(llm, hum, strict=True))
    print("Confusion matrix (rows = LLM, cols = HUMAN):\n")
    header = "LLM\\HUM " + " ".join(f"{c:>3}" for c in levels) + "  total"
    print(header)
    print("-" * len(header))
    for r in levels:
        cells = [cm.get((r, c), 0) for c in levels]
        print(f"  {r:>2}    " + " ".join(f"{x:>3}" for x in cells) + f"  {sum(cells):>5}")
    print()
    # column totals
    col_totals = [sum(cm.get((r, c), 0) for r in levels) for c in levels]
    print("  HUM    " + " ".join(f"{x:>3}" for x in col_totals) + f"  {sum(col_totals):>5}")

    # --- Aggregate metrics ---------------------------------------------------
    bias = sum(li - hi for li, hi in zip(llm, hum, strict=True)) / n
    print()
    print(f"Cohen's kappa (LLM vs human): {cohens_kappa(llm, hum):.3f}")
    print(f"Ordinal MAE                 : {ordinal_mae(llm, hum):.3f}")
    print(
        f"Signed bias (LLM - human)   : {bias:+.3f}  "
        f"(positive = LLM over-classes; spec target |bias| < 0.30)"
    )

    # --- Per-level diagnostics ----------------------------------------------
    print("\nLevel-4 diagnostic (the suspected blind spot):")
    n_human4 = sum(1 for h in hum if h == 4)
    n_llm4 = sum(1 for k in llm if k == 4)
    print(f"  human said 4 on {n_human4}/{n} items")
    print(f"  LLM said 4   on {n_llm4}/{n} items")
    if n_human4 > 0:
        misses = [(li, hi) for li, hi in zip(llm, hum, strict=True) if hi == 4 and li != 4]
        if misses:
            from_llm = Counter(li for li, _ in misses)
            print("  Of the items the human marked 4, the LLM said:")
            for k, c in sorted(from_llm.items()):
                print(f"    LLM={k}: {c} item(s)")

    # --- Mismatch listing ----------------------------------------------------
    print("\nMismatched items (|LLM - human| >= 1), sorted by gap desc:")
    rows_diff = sorted(
        [(li, hi, r) for li, hi, r in pairs if li != hi],
        key=lambda t: abs(t[0] - t[1]),
        reverse=True,
    )
    if not rows_diff:
        print("  (none — perfect agreement)")
    for li, hi, r in rows_diff:
        text = (r.get("clean_text") or "").replace("\n", " ")
        if len(text) > 140:
            text = text[:137] + "..."
        marker = " <-- LEVEL-4 CASE" if 4 in (li, hi) else ""
        conf = r.get("llm_confidence")
        print(f"  item={r['item_id']:>4}  LLM={li}  HUM={hi}  conf={conf}{marker}")
        print(f"           text: {text}")
        if r.get("human_notes"):
            print(f"           note: {r['human_notes']}")
    return 0


if __name__ == "__main__":
    arg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/rubric_audit.jsonl")
    sys.exit(main(arg_path))
