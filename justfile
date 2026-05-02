# TRUMPORACLE — Git Bash (MINGW) + venv Windows sous le dépôt (.venv/Scripts).
# `just` exécute les recettes dans un bash non interactif : sans ça, `python` du venv
# n'est pas devant le PATH et `/usr/bin/python3` (MSYS) prend le relais par erreur.

set shell := ["bash", "-c"]

export PATH := (justfile_directory() / ".venv" / "Scripts") + ":" + (justfile_directory() / ".venv" / "bin") + ":" + env_var_or_default("PATH", "")

default:
    @just --list

install:
    (command -v uv >/dev/null 2>&1 && uv sync --all-extras) || python -m uv sync --all-extras

lint:
    (command -v uv >/dev/null 2>&1 && uv run ruff check src tests && uv run ruff format --check src tests) || (python -m uv run ruff check src tests && python -m uv run ruff format --check src tests)

format:
    (command -v uv >/dev/null 2>&1 && uv run ruff format src tests && uv run ruff check --fix src tests) || (python -m uv run ruff format src tests && python -m uv run ruff check --fix src tests)

typecheck:
    (command -v uv >/dev/null 2>&1 && uv run mypy src/trumporacle) || python -m uv run mypy src/trumporacle

test *ARGS:
    (command -v uv >/dev/null 2>&1 && uv run pytest {{ARGS}}) || python -m uv run pytest {{ARGS}}

migrate:
    (command -v uv >/dev/null 2>&1 && uv run alembic upgrade head) || python -m uv run alembic upgrade head

migrate-down:
    (command -v uv >/dev/null 2>&1 && uv run alembic downgrade -1) || python -m uv run alembic downgrade -1

dev:
    (command -v uv >/dev/null 2>&1 && uv run uvicorn trumporacle.dashboard.api.app:app --reload --host 0.0.0.0 --port 8000) || python -m uv run uvicorn trumporacle.dashboard.api.app:app --reload --host 0.0.0.0 --port 8000

mvp-tick:
    (command -v uv >/dev/null 2>&1 && uv run trumporacle mvp-tick) || python -m uv run trumporacle mvp-tick
