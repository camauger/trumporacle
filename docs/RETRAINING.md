# Re-training procedure

Follow spec section 12.2.

1. Freeze `t_train_end` and extend training slice.
2. If `llm_labeler_version` changed, re-annotate affected items (batch jobs).
3. Recompute features for the new training window (`feature_sets` bump).
4. Train candidate models (C1, C2.k, C3, C4) and calibrate on validation only.
5. Evaluate vs current active model using section 10.9 gates (no regression beyond thresholds).
6. If promoted: set `models.is_active`, archive prior artifact paths, document in `MODEL_CARD.md`.

## Monthly cadence

- Default: calendar-month re-train review; drift alerts may trigger opportunistic runs (spec 12.1).

## Weekly qualitative review

- Export top confident errors and surprises (spec 10.8) from `predictions` / `outcomes` joins.
