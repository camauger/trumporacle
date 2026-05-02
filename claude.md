# claude.md

Short context for **Claude Code** on this repo. Full detail: **[`AGENTS.md`](AGENTS.md)**.

## What this is

**TRUMPORACLE** — Python service + pipelines to ingest public text, annotate **valence 0–6**, engineer time-safe features, train calibrated models (XGBoost + isotonic), and serve predictions via FastAPI. Spec: [`trumporacle.mdc`](trumporacle.mdc). Tooling: [`stack.md`](stack.md).

## Rules of engagement

0. **Operational principles:** follow [`.cursor/rules/operational-principles.mdc`](.cursor/rules/operational-principles.mdc) — clarify assumptions, minimal scope, verify (`just lint` / `just test` / `just typecheck` when relevant), and for non-trivial tasks end with **Done / Decided / Not done / Not verified / Spotted**. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

1. **Treat `trumporacle.mdc` and `stack.md` as frozen** unless the user explicitly asks to change them.
2. **No temporal leakage** in features (spec §10.2); validate with tests / clear `H` cutoff docs.
3. **Append-only** bias for `raw_items`, `predictions`, `outcomes`, `valence_annotations`.
4. **Secrets:** only via `.env` / env vars (`config.py`); never commit keys.
5. **mypy strict** only on `prediction`, `evaluation`, `features` — see `pyproject.toml`.

## Where to look

| Need | Location |
|------|----------|
| Schema | `alembic/versions/`, spec §8 in `trumporacle.mdc` |
| Ingest / DB writes | `src/trumporacle/ingestion/`, `storage/db.py` |
| LLM labels | `src/trumporacle/nlp/annotation/` |
| Models / metrics | `src/trumporacle/prediction/`, `evaluation/` |
| Web + scheduler | `src/trumporacle/dashboard/api/app.py` |
| CLI | `src/trumporacle/cli.py` → `trumporacle` |

## Commands

```bash
just install && just test && just lint
python -m uv run alembic upgrade head   # after compose DB up
```

If `uv` is missing: `pip install uv` or use standalone CLI — see README.

## Note

Some tools expect `CLAUDE.md` (capital name). This project uses `claude.md` at the repo root; duplicate or symlink if a tool requires the other filename.
