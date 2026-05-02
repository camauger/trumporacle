# AGENTS.md

## Project overview

**TRUMPORACLE** is a Python application for monitoring and estimating calibrated probabilities of **rhetorical valence escalation** (ordinal scale 0–6) in public communications, primarily Donald Trump on Truth Social, using ecosystem media signals (spec: [`trumporacle.mdc`](trumporacle.mdc)). Audience: research, journalism, media monitoring — **descriptive/predictive, not normative**.

**Tech stack:** Python 3.12–3.13 (`requires-python` in [`pyproject.toml`](pyproject.toml)), FastAPI + HTMX/Jinja dashboard, PostgreSQL 16 + TimescaleDB + pgvector + pg_trgm (Docker), SQLAlchemy 2 Core + Alembic + asyncpg, XGBoost/sklearn + MLflow, Anthropic + instructor for LLM labeling.

Canonical implementation stack choices live in [`stack.md`](stack.md).

## Operational principles (binding)

All work on this repository **must follow** [`.cursor/rules/operational-principles.mdc`](.cursor/rules/operational-principles.mdc) (Cursor: `alwaysApply: true`). Contributor-facing summary: [`CONTRIBUTING.md`](CONTRIBUTING.md).

**Project checklist (Principles 4–5):**

1. **Before** non-trivial changes: state **testable** success criteria (what changes, what must remain true).
2. **After** implementation: run **`just lint`** and **`just test`**; **`just typecheck`** if you edited `prediction/`, `evaluation/`, or `features/`. If something cannot be run, document it under **Not verified** (do not substitute “should work”).
3. **After** non-trivial tasks: provide a short structured wrap-up — **Done** (files), **Decided** (assumptions/tradeoffs), **Not done**, **Not verified**, **Spotted** (bugs/debt left untouched).

## Architecture

```
trumporacle/
├── src/trumporacle/
│   ├── cli.py                 # CLI: ingest-truth, sample-validation
│   ├── config.py              # Pydantic Settings / env
│   ├── storage/db.py          # sync + async SQLAlchemy engines
│   ├── ingestion/           # Truth Social, RSS, Telegram (stub), Fox, podcasts
│   ├── nlp/                   # normalize, annotation (LLM), embedding (BGE)
│   ├── features/              # windows, ablation flags
│   ├── prediction/            # calibration, XGBoost training helpers
│   ├── evaluation/          # baselines B1–B4, backtest, agreement, drift
│   ├── dashboard/api/app.py # FastAPI + APScheduler + /metrics
│   └── orchestration/       # scheduled jobs, Discord webhook alerts
├── alembic/versions/          # DB schema (spec §8)
├── docker/db/                 # Postgres image: Timescale + pgvector build
├── tests/
├── docs/                      # DATASHEET, MODEL_CARD, RETRAINING templates
├── trumporacle.mdc            # Frozen product/ML spec — treat as source of truth
└── stack.md                   # Frozen tooling choices
```

**Data flow (target):** ingest → `raw_items` → `items` (+ embeddings) → `valence_annotations` → feature engineering at reference time `H` → models → `predictions` → `outcomes` after window closes.

## Coding conventions

**Style**

- Match existing modules: type hints on public APIs, `from __future__ import annotations` where already used.
- **mypy strict** applies to `trumporacle.prediction`, `trumporacle.evaluation`, `trumporacle.features` only (see [`pyproject.toml`](pyproject.toml)); ingestion/dashboard/nlp are looser — do not force strict mypy there without tightening overrides first.
- Line length **100** (ruff). Run `ruff check` + `ruff format` before committing.

**Patterns**

- **Append-only** semantics for log-like tables (`raw_items`, `predictions`, `outcomes`, `valence_annotations`) — avoid destructive updates unless the spec explicitly allows it.
- **No temporal leakage:** features at `H` must use only information available strictly before/at `H` (see spec §10.2). Property tests live under `tests/` (e.g. rolling mean cutoff).
- Prefer **SQLAlchemy `text()` + async `AsyncSession`** in ingestion paths already written; keep DB access centralized in `storage/` and `ingestion/repository.py` unless there is a clear reason to split.

**Naming**

- Package name: `trumporacle` under `src/trumporacle/`. Entry: `trumporacle` console script → `trumporacle.cli:main`.

## Key files

| File | Purpose |
|------|---------|
| [`trumporacle.mdc`](trumporacle.mdc) | Frozen functional spec (targets C1–C4, schema, evaluation). |
| [`stack.md`](stack.md) | Frozen stack / tooling decisions. |
| [`pyproject.toml`](pyproject.toml) | Dependencies, ruff, mypy, pytest, entry points. |
| [`justfile`](justfile) | `install`, `lint`, `test`, `migrate`, `dev` (uses `python -m uv`). |
| [`alembic/versions/20260502_0001_initial_schema.py`](alembic/versions/20260502_0001_initial_schema.py) | Initial Postgres schema + conditional hypertable. |
| [`src/trumporacle/config.py`](src/trumporacle/config.py) | Env-driven settings; never commit secrets. |
| [`src/trumporacle/cli.py`](src/trumporacle/cli.py) | User-facing ingest / sampling commands. |
| [`src/trumporacle/dashboard/api/app.py`](src/trumporacle/dashboard/api/app.py) | ASGI app, scheduler, Prometheus `/metrics`. |
| [`docker-compose.yml`](docker-compose.yml) | Local DB service. |
| [`.cursor/rules/operational-principles.mdc`](.cursor/rules/operational-principles.mdc) | Workflow rules (clarify, minimal scope, verify, report). |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How principles map to commands and PR expectations. |

## Development

**Setup**

```bash
pip install uv   # if `python -m uv` is not available
just install     # uv sync --all-extras (bash -c; uv or python -m uv)
docker compose up -d
cp .env.example .env   # fill DATABASE_URL and API keys
python -m uv run alembic upgrade head
```

**Test**

```bash
just test
# DB integration (optional): set DATABASE_URL then pytest
```

**Lint / types**

```bash
just lint
just typecheck   # strict packages only
```

## Common tasks

**Add a migration**

1. Edit models via new Alembic revision under `alembic/versions/`.
2. `just migrate` against a dev DB with extensions (Timescale + vector) when testing hypertables.

**Add an ingestion source**

1. Implement `SourceConnector` under `src/trumporacle/ingestion/<source>/`.
2. Persist via `ingestion/repository.py`; register `sources` row with correct `kind` / `metadata` (e.g. `trump_primary` for materialized view filtering).

**Change LLM rubric / labeler version**

1. Update `nlp/annotation/rubric.py` (and bump `RUBRIC_VERSION`).
2. Spec §9.8: document impact on re-annotation and training data lineage.

**MVP runnable baseline loop**

1. Postgres up + `alembic upgrade head`; `.env` with `DATABASE_URL`.
2. `trumporacle mvp-tick` (or rely on APScheduler via `just dev`).
3. Dashboard: `/predictions` lists rows from `predictions`; Prometheus counters in `dashboard/metrics.py`.

## Constraints and gotchas

- **Do not silently rewrite [`trumporacle.mdc`](trumporacle.mdc) or [`stack.md`](stack.md)** — they are normative for the project; changes need explicit maintainer intent and version bumps.
- **Hypertables:** unique constraints on hypertables must include the partition column; current schema avoids `(source_id, external_id)` uniqueness at DB level — dedupe is application-level in `insert_raw_item`.
- **Git Bash + Windows:** `justfile` uses `bash -c` (inherits `PATH`) and `uv` / `python -m uv` — see README.
- **Docker DB build** compiles pgvector — first build can be slow.
- **Neon:** `DATABASE_URL` with `?sslmode=require` is fine; `postgres://` URLs are normalized. No TimescaleDB on Neon—migrations skip the extension; `raw_items` is a plain table. **Netlify** is for static/short functions; the FastAPI + APScheduler process still needs a long-lived host (see README “Neon + Netlify”).
- **Ethics / dual-use:** monitoring context is sensitive; avoid features that enable harassment or automated targeting (spec §14).

## AI assistant guidelines

- Apply [operational principles](.cursor/rules/operational-principles.mdc) **first**: clarify ambiguities, avoid speculative abstractions, touch only necessary files, verify or say **Not verified**, finish non-trivial work with **Done / Decided / Not done / Not verified / Spotted**.
- Read **§8 (schema)** and **§10 (evaluation / leakage)** in [`trumporacle.mdc`](trumporacle.mdc) before changing features, labels, or migrations.
- Prefer **minimal diffs**; do not refactor unrelated modules or add frameworks absent from [`stack.md`](stack.md).
- After code changes, run **`just lint`** and **`just test`** (and `just typecheck` if touching strict packages).
- For new dependencies: justify against [`stack.md`](stack.md) (“boring tech”, solo maintainability).
- <!-- TODO: maintainer — default branch, release process, `gold_standard` row-level rules. -->
