"""Tests for analyzer.subprocess_util.run_external — the single subprocess wrapper."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from analyzer import subprocess_util


def _completed(returncode=0, stdout="out", stderr=""):
    return subprocess.CompletedProcess(
        args=["x"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_timeout_is_required():
    with pytest.raises(TypeError):
        subprocess_util.run_external(["echo", "hi"])


def test_returns_stdout_on_success():
    with patch.object(
        subprocess_util.subprocess, "run", return_value=_completed(stdout="hello\n")
    ) as run:
        out = subprocess_util.run_external(["echo", "hello"], timeout=5, env={"PATH": "/usr/bin"})
    assert out == "hello\n"
    assert run.call_args.kwargs["env"] == {"PATH": "/usr/bin"}
    assert run.call_args.kwargs["timeout"] == 5
    assert run.call_args.kwargs["check"] is True


def test_env_none_becomes_empty_dict():
    with patch.object(subprocess_util.subprocess, "run", return_value=_completed()) as run:
        subprocess_util.run_external(["true"], timeout=5)
    assert run.call_args.kwargs["env"] == {}


def test_check_false_returns_completed_process():
    cp = _completed(returncode=2, stdout="o", stderr="e")
    with patch.object(subprocess_util.subprocess, "run", return_value=cp):
        res = subprocess_util.run_external(["x"], timeout=5, check=False)
    assert res.returncode == 2
    assert res.stdout == "o"


def test_called_process_error_becomes_runtime_error():
    err = subprocess.CalledProcessError(1, ["cmd", "arg"], output="", stderr="boom")
    with patch.object(subprocess_util.subprocess, "run", side_effect=err):
        with pytest.raises(RuntimeError) as ei:
            subprocess_util.run_external(["cmd", "arg"], timeout=5)
    assert "boom" in str(ei.value)
    assert "arg" in str(ei.value)  # argv not redacted by default


def test_redact_argv_log_hides_arguments():
    err = subprocess.CalledProcessError(
        1, ["op", "read", "op://vault/secret"], output="", stderr="x"
    )
    with patch.object(subprocess_util.subprocess, "run", side_effect=err):
        with pytest.raises(RuntimeError) as ei:
            subprocess_util.run_external(
                ["op", "read", "op://vault/secret"], timeout=5, redact_argv_log=True
            )
    msg = str(ei.value)
    assert "op://vault/secret" not in msg
    assert "redacted" in msg


def test_timeout_expired_becomes_runtime_error():
    err = subprocess.TimeoutExpired(["sleep", "10"], 5)
    with patch.object(subprocess_util.subprocess, "run", side_effect=err):
        with pytest.raises(RuntimeError, match="timed out"):
            subprocess_util.run_external(["sleep", "10"], timeout=5)


def test_missing_executable_becomes_runtime_error():
    with patch.object(subprocess_util.subprocess, "run", side_effect=FileNotFoundError()):
        with pytest.raises(RuntimeError, match="not found"):
            subprocess_util.run_external(["nope"], timeout=5)
