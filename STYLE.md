# Style

A few invariants this codebase enforces (some via CI):

- **Async** lives only under `analyzer/llm/`. The pipeline orchestrates it from
  a synchronous boundary via `asyncio.run()`.
- **Subprocess** calls go exclusively through
  `analyzer.subprocess_util.run_external()`. Bare `subprocess.*` is forbidden
  (CI `subprocess-guard`): the wrapper enforces a timeout and an explicit env.
- **Configuration** comes from `analyzer.config.Settings` (pydantic-settings v2,
  strict, no defaults). No module-level secrets or secret references.
- **Linting/formatting** is `ruff` (line length 100; `E,F,W,I,B,S`). Run
  `ruff check analyzer tests` and `ruff format` before committing.
- **No network in tests** — `pytest-socket` blocks sockets by default; mock
  external calls, or mark a test `@pytest.mark.enable_socket` only if truly
  required.
