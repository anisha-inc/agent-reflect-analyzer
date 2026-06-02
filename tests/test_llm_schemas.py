"""Tests for analyzer.llm.schemas — Candidate creation + validation."""

from __future__ import annotations

import pytest

from analyzer.llm.schemas import Candidate, ClusterFinding, Finding, OpusFindings


def test_candidate_from_opus_preserves_fields():
    f = Finding(
        pattern_id="bash-001-loop",
        title="Bash hook retries the same compound command",
        severity="medium",
        frequency_in_sample=4,
        session_examples=["s1", "s2"],
        mast_taxonomy="SI-1.3",
        symptom="Agent re-issues `&&`-chained commands…",
        proposed_fix="Add bash-atomic.sh warning…",
        evidence_quotes=["BASH-001", "BASH-002"],
    )
    c = Candidate.from_opus(f)
    assert c.source == "opus_top_k"
    assert c.pattern_id == "bash-001-loop"
    assert c.frequency == 4
    assert c.mast_taxonomy == "SI-1.3"


def test_candidate_from_cluster_slugifies_name():
    cl = ClusterFinding(
        name="Read/Edit thrash on the same file",
        description="Agent reads then edits then reads the same file repeatedly.",
        frequency=5,
        session_ids=["a", "b", "c", "d", "e"],
    )
    c = Candidate.from_cluster(cl)
    assert c.source == "cluster"
    assert c.pattern_id == "read-edit-thrash-on-the-same-file"
    assert c.frequency == 5
    assert c.severity == "medium"


def test_finding_validation_truncates_oversized_examples():
    f = Finding(
        pattern_id="x", title="t", severity="low", frequency_in_sample=1,
        session_examples=["a", "b", "c", "d"],
        symptom="s", proposed_fix="f", evidence_quotes=["q1", "q2", "q3", "q4", "q5"],
    )
    # Lenient validator truncates to 3 instead of raising.
    assert f.session_examples == ["a", "b", "c"]
    assert f.evidence_quotes == ["q1", "q2", "q3"]


def test_opus_findings_default_empty():
    o = OpusFindings()
    assert o.findings == []
