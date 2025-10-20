# Repository Guidelines

The Dictforge project pairs a CLI with supporting tooling for ebook dictionary workflows. Follow these notes to stay aligned with the existing repo practices.

## Project Structure & Module Organization
- Application code lives in `src/dictforge/`; `main.py` exposes the `dictforge` CLI while `builder.py`, `langutil.py`, and `kindle.py` hold feature modules.
- Shared shell helpers reside in `scripts/`.
- Documentation and localisation assets sit under `docs/`.
- Tests mirror CLI behaviour in `tests/`.
- Tooling metadata is tracked in `pyproject.toml` and `uv.lock`, and `. ./activate.sh` prepares the uv-managed Python 3.12 env.

## Build, Test, and Development Commands
- `source activate.sh` — always run this first to enter the uv-managed Python env before any other command.
- `uv run dictforge --help` — confirm CLI wiring after edits.
- `uv run pytest` — run the test suite (use this command for all automated tests).
- `invoke pre` — execute linting and formatting hooks.
- `invoke docs-en` — build the English MkDocs site; swap suffix for other locales.

## Coding Style & Naming Conventions
Follow Ruff defaults with a 99-character line limit and standard Black-style indentation. Prefer type hints for new APIs, keep modules, packages, and tests in `snake_case`, and rely on `ruff check .` for focussed linting. Add comments sparingly and align docstrings with public interfaces.

## Testing Guidelines
Pytest drives coverage; name test files `test_*.py` under `tests/`. Exercise CLI commands via `CliRunner` where practical, and call `uv run pytest --cov=src/dictforge --cov-report=term-missing` to verify coverage. Generate Allure artifacts with `uv run pytest --alluredir=build/tests` for publishing.

## Commit & Pull Request Guidelines
Write imperative, <=50 character commit subjects (e.g., `Add CLI option`), and mention scope in the body when needed. Before opening a PR, ensure `invoke pre` and `uv run pytest` are green, document any CLI-facing changes, attach relevant output or screenshots, and link issues or tickets. Squash WIP commits so reviewers see a concise history.
