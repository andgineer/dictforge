# Repository Guidelines

## Project Structure & Module Organization
Application code lives in `src/dictforge/`, with `main.py` exposing the `dictforge` CLI and helpers such as `builder.py`, `langutil.py`, and `kindle.py`. Shared shell utilities sit in `scripts/`, while documentation sources and localisation assets are under `docs/`. Tests reside in `tests/` and mirror CLI behaviours. Dependency metadata is managed through `pyproject.toml` and `uv.lock`, and `. ./activate.sh` bootstraps the development environment.

## Build, Test, and Development Commands
- `. ./activate.sh` — create or activate the uv-managed Python 3.12 virtualenv.
- `uv run dictforge --help` — verify the CLI wiring after changes.
- `uv run pytest` — execute unit tests and doctests defined by `pytest.ini`.
- `invoke pre` — run the configured pre-commit suite across the codebase.
- `invoke docs-en` (or another language suffix) — preview the MkDocs site; matching tasks sync shared assets between locales.

## Coding Style & Naming Conventions
Follow Ruff defaults with the project line length of 99 characters; run `ruff check .` if you need a focused lint pass. Prefer type hints for new interfaces and keep module, package, and test names in `snake_case`. Install hooks via `pre-commit install` so formatting and linting run before each commit.

## Testing Guidelines
Pytest is the primary framework; test modules belong in `tests/` and start with `test_`. Include CLI regression tests via `CliRunner` where practical and leverage doctests for simple contracts. Use `uv run pytest --cov=src/dictforge --cov-report=term-missing` when you need a coverage view, and capture Allure data with `uv run pytest --alluredir=build/tests` for publishing.

## Commit & Pull Request Guidelines
Write short, imperative commit subjects (`Add CLI option`, `Fix Kindle metadata`) to stay consistent with the current history. Squash noisy WIP commits before review. Pull requests should describe the behaviour change, list any docs or assets touched, and link related issues. Attach CLI output or screenshots when altering user-visible functionality, and confirm the `invoke pre` and `uv run pytest` checks have passed.
