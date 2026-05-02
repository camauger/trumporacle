# Model Card (TRUMPORACLE)

Template aligned with Mitchell et al. (2019). One card per promoted `models.version` + `task`.

## Model details

- **Tasks**: C1 (`E[v_max]`), C2.k (`P(v_max ≥ k)`), C3 (jump), C4 (post presence) — spec section 5.
- **Primary algorithms**: XGBoost + isotonic calibration (MVP); survival experiments for C4 optional.
- **Inputs**: Versioned tabular features at reference time `H` (spec section 11.1).

## Performance

- **Primary metrics**: AUC-PR and ECE for C2.4/C2.5 on temporal hold-out (spec section 10).
- **Baselines**: B4 (media persistence) is the main comparison bar.

## Ethics / limitations

- Descriptive probabilities, not moral judgments; see spec sections 14–15.

## Versioning

- Each training run logs to MLflow and registers `model_version`, `feature_set_id`, `artifact_path` in Postgres.
