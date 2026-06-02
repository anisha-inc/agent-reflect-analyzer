"""Tests for analyzer.audit — RunRecord serialization + write_audit."""

from __future__ import annotations

import json

from analyzer import audit


def test_run_record_default_values():
    r = audit.RunRecord()
    d = r.to_dict()
    assert d["sessions_analyzed"] == 0
    assert d["candidates_total"] == 0
    assert d["redacted"] == {}
    assert d["issue_urls"] == []
    assert d["warnings"] == []


def test_finalize_sets_total_wall_s():
    r = audit.RunRecord()
    r.finalize()
    assert isinstance(r.total_wall_s, float)
    assert r.total_wall_s >= 0


def test_write_audit_writes_json_to_tmp(tmp_path, monkeypatch):
    from analyzer import config

    monkeypatch.setattr(config, "AUDIT_DIR", tmp_path / "audit")
    r = audit.RunRecord(since="7d", limit=10, sessions_analyzed=3)
    path = audit.write_audit(r)
    assert path.exists()
    parsed = json.loads(path.read_text())
    assert parsed["since"] == "7d"
    assert parsed["sessions_analyzed"] == 3
