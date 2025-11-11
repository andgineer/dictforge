# Repository Guidelines

## Project Structure & Module Organization
The CLI entrypoint lives in `src/dictforge/main.py`, while feature modules such as `builder.py`, and `kindle.py` hold the ebook dictionary logic. Shared shell helpers are under `scripts/`, documentation and localisation assets reside in `docs/`, and tests mirror CLI behaviour in `tests/`. Tooling metadata is maintained in `pyproject.toml` and `uv.lock`; keep changes in sync across these files when adding dependencies.

## Build, Test, and Development Commands
- `source activate.sh` — enter the managed Python 3.12 environment before running any tooling. Always run this first in each new shell.
- Once activated, call tools directly (e.g., `dictforge --help`, `pytest`, `invoke pre`). **Do not prefix commands with `uv run`.**
- `pytest [--cov=src/dictforge --cov-report=term-missing]` — execute the automated test suite and optional coverage report.
- `invoke pre` — run formatting, linting, and static checks prior to committing.
- `invoke docs-en` — build the English MkDocs site; swap locale suffixes for translated docs.

## Coding Style & Naming Conventions
Follow Ruff defaults with a 99-character limit and Black-style formatting; rely on `ruff check .` and `invoke pre` to keep imports and style consistent. Prefer type-hinted functions and `snake_case` for modules, packages, and tests. Add concise docstrings for public CLI surfaces and only include comments that clarify non-obvious intent.

## Testing Guidelines
Pytest drives validation; place new tests in `tests/test_*.py` and exercise CLI commands via `CliRunner` where practical. Maintain healthy coverage using the `--cov` invocation and generate Allure artifacts with `pytest --alluredir=build/tests` when needed. Keep fixtures scoped to minimise runtime and document any slow integration paths.

## Commit & Pull Request Guidelines
Write commits with imperative subjects under 50 characters (e.g., `Add CLI option`) and expand on scope in the body when clarification helps reviewers. Before raising a PR, ensure `invoke pre` and `pytest` pass, document CLI-affecting changes, attach relevant output or screenshots, and reference tickets. Squash intermediate WIP commits so the history stays focused and easy to review.
After activating the environment with `source activate.sh`, run required checks directly (e.g., `pytest`, `invoke pre`) without the `uv run` wrapper.
