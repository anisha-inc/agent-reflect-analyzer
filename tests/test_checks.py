"""Tests for analyzer.checks — JSON shape + a few happy-path probes."""

from __future__ import annotations

import json

from analyzer import checks


def test_each_probe_returns_required_fields():
    for probe in checks.PROBES:
        # Probes may legitimately fail in this sandbox (no 1P, no gsutil).
        # We only check schema.
        r = probe()
        assert isinstance(r, dict)
        assert {"id", "category", "ok", "detail"} <= set(r.keys()), r
        assert isinstance(r["ok"], bool)
        assert isinstance(r["id"], str) and r["id"]
        assert isinstance(r["category"], str) and r["category"]
        assert isinstance(r["detail"], str)


def test_run_all_emits_8_probes():
    results = checks.run_all()
    assert len(results) == 8
    ids = [r["id"] for r in results]
    assert set(ids) == {
        "hmac_1p",
        "hmac_duckdb_smoke",
        "gh_cli",
        "app_token",
        "recent_ships",
        "anthropic_key",
        "claude_cli",
        "python_deps",
    }


def test_check_app_token_script_ok_via_bash(monkeypatch):
    # PF-25: the probe finds the script and runs `bash <path> --help` without
    # requiring the executable bit (force-included wheel copies aren't +x).
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    r = checks.check_app_token_script()
    assert r["id"] == "app_token"
    assert r["ok"] is True, r


def test_all_ok_reflects_results():
    fake_ok = [{"id": "x", "category": "y", "ok": True, "detail": ""}]
    fake_fail = [{"id": "x", "category": "y", "ok": False, "detail": ""}]
    assert checks.all_ok(fake_ok) is True
    assert checks.all_ok(fake_fail) is False
    assert checks.all_ok([]) is True  # vacuously true


def test_results_are_json_serializable():
    results = checks.run_all()
    s = json.dumps(results)
    parsed = json.loads(s)
    assert len(parsed) == 8
