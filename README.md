# TRUMPORACLE

Implementation of the frozen specification in `trumporacle.mdc`, using the stack in `stack.md`.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — install the CLI and ensure **`uv` is on your `PATH`** (Scoop, pipx, astral installer, etc.). The `justfile` only runs `uv …` (same idea as most uv projects).
- Docker (for local Postgres)

### `just` + Git Bash (Windows)

The `justfile` uses **`bash -c`** so recipes **inherit `PATH`** from the terminal that started `just` (same idea as many other repos). **`bash -lc`** was avoided here because a login profile can **replace** `PATH` and hide Scoop / conda / venv shims.

With **Git Bash** and a Windows **`.venv`**, **`python.exe`** is under **`.venv/Scripts`** (not **`bin/`** like on Unix); subshells spawned by **`just`** may otherwise resolve **`python`** to Git Bash’s **`/usr/bin/python3`**, which is not your project env.

The **`justfile`** therefore **prepends** **`<repo>/.venv/Scripts`** and **`<repo>/.venv/bin`** to **`PATH`** for every recipe so **`python -m uv`** and tools hit the project venv first.

Do **not** reuse **`TRUMPORACLE_PY_LAUNCH`** from older drafts: forcing **`py -3.12`** when that runtime is not installed yields launcher **exit 103**. **`uv sync`** resolves Python per **`requires-python`** in `pyproject.toml`.

Each recipe uses **`uv …`** when the **`uv`** binary is on **`PATH`**, otherwise **`python -m uv …`**. Install **`uv`** in the venv if needed (`pip install uv`, Scoop, etc.).

## Quick start

```bash
uv sync --all-extras
docker compose up -d
set DATABASE_URL=postgresql+psycopg://trumporacle:trumporacle@127.0.0.1:5432/trumporacle
uv run alembic upgrade head
uv run pytest
uv run uvicorn trumporacle.dashboard.api.app:app --reload --host 0.0.0.0 --port 8000
```

Copy `.env.example` to `.env` and set secrets (`ANTHROPIC_API_KEY`, `DATABASE_URL`, etc.). For Truth ingestion, **`TRUTH_SOCIAL_RSS_URL`** defaults in `.env.example` to **[Trump’s Truth](https://www.trumpstruth.org/)** (RSS archive by Defending Democracy Together) — not an official Truth Social endpoint. Append **`?start_date=…&end_date=…`** on that URL for a date-bounded backfill window. Alembic resolves `DATABASE_URL` the same way as the app: shell override if set, otherwise values from `.env` in the project root.

**5432 already in use / password errors:** another Postgres may be bound to `127.0.0.1:5432` with different credentials. Start Docker Desktop and run `docker compose up -d` for this project’s DB, stop the other service, or change the host port mapping in `docker-compose.yml`.

### Neon (managed Postgres) + Netlify

**Neon.** Set `DATABASE_URL` to the connection string from the Neon dashboard (psycopg / SQLAlchemy style). Include `?sslmode=require` for TLS. The app normalizes `postgres://` and bare `postgresql://` URLs to `postgresql+psycopg://`. Async paths use asyncpg with TLS when the host is `*.neon.tech` or `sslmode=require` is present. Neon does not ship TimescaleDB; migrations enable it only if the extension is available—otherwise `raw_items` stays a normal Postgres table (same behavior as the conditional hypertable block).

**Netlify.** Netlify fits static sites and short-lived serverless handlers. This repo’s FastAPI dashboard and APScheduler tick assume a **long-lived Python process** (see `stack.md` / systemd). A workable split is: **Neon** for `DATABASE_URL`, **Netlify** only for static frontend or marketing pages if you split them out, and **API + scheduler** on a VM (OVH), Railway, Fly.io, Render, or similar—unless you redesign jobs into HTTP cron triggers against Netlify Functions (cold starts, timeouts, no shared in-memory scheduler).

On Netlify (Functions or builds), add **`DATABASE_URL`** in Site configuration → Environment variables with the same Neon string.

## MVP runnable (baseline loop)

With Postgres up and migrations applied:

```bash
uv run trumporacle mvp-tick
# or: just mvp-tick
```

This **ingests** Truth Social when `TRUTH_SOCIAL_RSS_URL` is set (optional), writes a **baseline prediction** for the current 15‑minute–aligned 2 h window (`mvp-baseline-b4soft-001`), and **materializes outcomes** for windows that have closed. Open `http://127.0.0.1:8000/predictions` after `just dev`.

LLM annotations during ingest run only if `ANTHROPIC_API_KEY` is set; without it, ingest still stores posts/items but aggregate features may stay empty until annotations exist.

## CLI

```bash
uv run trumporacle ingest-truth
uv run trumporacle mvp-tick
uv run trumporacle sample-validation --n 800
```

## Integration tests

With the DB up and migrated, set `DATABASE_URL` and run `pytest` (see `tests/test_integration_db.py`).

The first `docker compose build` compiles **pgvector** from source and may take several minutes. Dev dependencies include **testcontainers** for future automated DB fixtures; the default CI job runs unit tests only.

## Contributing

Workflow norms (clarify → minimal change → verify → report): see [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`.cursor/rules/operational-principles.mdc`](.cursor/rules/operational-principles.mdc). Architecture context for tools: [`AGENTS.md`](AGENTS.md).

## License

Private research project — see specification for ethics and hosting notes.
