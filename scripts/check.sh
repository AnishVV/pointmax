#!/usr/bin/env sh
# Lint, format check and offline tests: what CI runs. Use before every push.
set -e
uv run ruff check .
uv run ruff format --check .
uv run pytest "$@"
