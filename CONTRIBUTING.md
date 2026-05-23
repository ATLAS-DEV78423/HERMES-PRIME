# Contributing to HERMES-PRIME

Thanks for your interest in contributing! This project follows a governance-first philosophy — changes should preserve deterministic behaviour and provenance for all actions.

## How to contribute

- Fork the repository and create a feature branch.
- Run tests locally and ensure linting passes with `ruff`.
- Open a pull request against `main` with a clear description and linked issue if applicable.

Please follow the project's `CODE_OF_CONDUCT.md` and ensure contributions include documentation and tests where appropriate.

## Developer workflow

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .[dev]
pre-commit install
pre-commit run --all-files
pytest -q
```

## Code style

- Use `ruff` for linting and autofixes.
- Keep functions small and focused; prefer readable dataclasses for schemas.
- All changes that affect security, policy, or provenance must include tests and an architecture note in `hermes/`.

## Reporting security issues

If you discover a security vulnerability, please report it privately by opening a security advisory on GitHub or contacting the maintainers via the project email in `pyproject.toml`.
All changes that materially affect security, policy, or provenance must include tests, an architecture note in `hermes/`, and a proposed mitigation plan.
