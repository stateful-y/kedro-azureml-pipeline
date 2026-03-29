# How to Contribute

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended)
- [just](https://github.com/casey/just) (optional, for task automation)
- Git

## Development setup

1. Fork the repository on GitHub

2. Clone your fork:

    ```bash
    git clone https://github.com/YOUR_USERNAME/kedro-azureml-pipeline.git
    cd kedro-azureml-pipeline
    ```

3. Install dependencies:

    ```bash
    uv sync --group dev
    ```

4. Install pre-commit hooks:

    ```bash
    uv run pre-commit install
    ```

## Make changes

1. Create a branch:

    ```bash
    git checkout -b feature/my-feature
    ```

2. Make your changes

3. Run the fast test suite to verify nothing is broken:

    === "just"
        ```bash
        just test-fast
        ```
    === "nox"
        ```bash
        uvx nox -s test_fast
        ```
    === "uv run"
        ```bash
        uv run pytest -m "not slow and not integration"
        ```

4. Format and fix code:

    === "just"
        ```bash
        just fix
        ```
    === "nox"
        ```bash
        uvx nox -s fix
        ```
    === "uv run"
        ```bash
        uv run ruff format src tests
        uv run ruff check src tests --fix
        uv run ty check src
        ```

5. Commit your changes using [Conventional Commits](https://www.conventionalcommits.org/):

    ```bash
    git commit -m "feat: add my feature"
    ```

## Running tests

Tests are categorized by markers:

- Default (no marker): fast unit tests
- `@pytest.mark.slow`: tests taking more than a few seconds or making network requests
- `@pytest.mark.integration`: end-to-end or multi-component tests

Run all tests:

=== "just"
    ```bash
    just test
    ```
=== "nox"
    ```bash
    uvx nox -s test
    ```
=== "uv run"
    ```bash
    uv run pytest
    ```

Run tests with coverage:

=== "just"
    ```bash
    just test-cov
    ```
=== "nox"
    ```bash
    uvx nox -s test_coverage
    ```
=== "uv run"
    ```bash
    uv run pytest --cov=kedro_azureml_pipeline --cov-report=html
    ```

## Code quality

Run linters and type checks:

=== "just"
    ```bash
    just lint
    ```
=== "nox"
    ```bash
    uvx nox -s lint
    ```
=== "uv run"
    ```bash
    uv run ruff check src tests
    uv run ty check src
    ```

All public functions, methods, and classes require **NumPy-style** docstrings. Coverage is enforced at 100% by `interrogate`.

Check docstring coverage:

```bash
uvx interrogate src
```

## Build and serve documentation

Build:

=== "just"
    ```bash
    just build
    ```
=== "uv run"
    ```bash
    uv run mkdocs build
    ```

Serve locally:

=== "just"
    ```bash
    just serve
    ```
=== "uv run"
    ```bash
    uv run mkdocs serve
    ```

## Pre-PR checklist

- [ ] `just test-fast` passes
- [ ] `just fix` shows no remaining issues
- [ ] New functionality has tests
- [ ] Changed documentation renders correctly via `just serve`
- [ ] Commit messages follow Conventional Commits

## Open a Pull Request

1. Push your branch:

    ```bash
    git push origin feature/my-feature
    ```

2. Open a Pull Request on GitHub

3. Ensure all CI checks pass and address review feedback

## CI test strategy

The CI pipeline uses two tiers:

1. **Fast tests**: Run on Python 3.11 and 3.13. On draft PRs - Ubuntu only. On ready PRs and `main` - Ubuntu, Windows, and macOS.
2. **Full test suite**: Runs all tests (fast + slow + integration) on Ubuntu across Python 3.11-3.13 when the PR is not a draft or on `main`. Includes coverage reporting on the minimum supported Python version.
