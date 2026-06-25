"""Tests for analyzer.checks — JSON shape + a few happy-path probes."""

from __future__ import annotations

import json
import sys

from analyzer import checks, identity


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


def test_run_all_emits_7_probes():
    results = checks.run_all()
    assert len(results) == 7
    ids = [r["id"] for r in results]
    assert set(ids) == {
        "hmac_1p",
        "hmac_duckdb_smoke",
        "gh_cli",
        "recent_ships",
        "anthropic_key",
        "claude_cli",
        "python_deps",
    }


def test_recent_ships_uses_duckdb_glob_v2_layout(monkeypatch):
    # PF-26: probe via DuckDB/HMAC glob (not gsutil), scoped to the caller's own
    # dev= partition under the v=2 layout.
    class _S:
        gcs_bucket = "gs://b"
        hmac_akid = "x" * 60
        hmac_secret = "y" * 60

    captured: dict = {}

    class _Con:
        def execute(self, sql, params=None):
            if sql.lstrip().upper().startswith("SELECT COUNT"):
                captured["pattern"] = params[0]
            return self

        def fetchone(self):
            return (3,)

        def close(self):
            pass

    fake_duckdb = type("M", (), {"connect": staticmethod(lambda *a, **k: _Con())})()
    monkeypatch.setitem(sys.modules, "duckdb", fake_duckdb)
    monkeypatch.setattr(checks, "_load_settings", lambda: _S())
    monkeypatch.setattr(identity, "dev_id", lambda: "abc123")

    r = checks.check_recent_ships()
    assert r["ok"] is True, r
    assert captured["pattern"] == "gs://b/raw/v=2/org=*/dev=abc123/proj=*/*.jsonl"
    assert "DuckDB/HMAC" in r["detail"]


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
    assert len(parsed) == 7
