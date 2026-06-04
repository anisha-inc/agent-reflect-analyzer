"""Single choke-point for all external process execution.

Every subprocess call in the package goes through :func:`run_external` so that:

* a timeout is **mandatory** — no unbounded hangs;
* the environment is **explicit** — ``env=None`` means an *empty* environment,
  never an implicit inherit; callers pass the exact variables a tool needs;
* failures raise a uniform :class:`RuntimeError` with a bounded, optionally
  argv-redacted message (references passed on the command line may be secrets).

This is the ONLY module allowed to import :mod:`subprocess` (enforced by the CI
subprocess-guard). Bandit ``S603``/``S607`` are silenced here via
per-file-ignores in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence


class ExecutableNotFoundError(RuntimeError):
    """Raised when an external executable is not on PATH.

    Subclasses ``RuntimeError`` so existing ``except RuntimeError`` handlers keep
    working, but lets callers distinguish a fatal environment misconfiguration
    (binary missing) from a transient/runtime failure that may be tolerated.
    """


def _argv_repr(argv: Sequence[str], redact_argv_log: bool) -> str:
    if not argv:
        return "<empty>"
    if redact_argv_log:
        return f"{argv[0]} <redacted {len(argv) - 1} arg(s)>"
    return " ".join(argv)


def run_external(
    argv: Sequence[str],
    *,
    timeout: float,
    env: dict | None = None,
    redact_argv_log: bool = False,
    stdin: object = None,
    cwd: str | None = None,
    check: bool = True,
):
    """Run an external command under a mandatory timeout.

    ``env=None`` runs with an *empty* environment — pass an explicit dict for
    any variable (``PATH`` included) the command needs.

    With ``check=True`` (default) returns captured **stdout** and raises
    :class:`RuntimeError` on non-zero exit, timeout, or a missing executable.

    With ``check=False`` returns the :class:`subprocess.CompletedProcess` so the
    caller can inspect ``returncode``/``stdout``/``stderr``; only timeout and a
    missing executable raise.
    """
    proc_env: dict = {} if env is None else env
    try:
        result = subprocess.run(
            list(argv),
            env=proc_env,
            cwd=cwd,
            stdin=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"command failed (exit {e.returncode}): {_argv_repr(argv, redact_argv_log)}"
            f"\nstderr: {(e.stderr or '')[:400]}\nstdout: {(e.stdout or '')[:400]}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"command timed out after {timeout}s: {_argv_repr(argv, redact_argv_log)}"
        ) from e
    except FileNotFoundError as e:
        raise ExecutableNotFoundError(
            f"executable not found: {_argv_repr(argv, redact_argv_log)}"
        ) from e
    if check:
        return result.stdout
    return result
