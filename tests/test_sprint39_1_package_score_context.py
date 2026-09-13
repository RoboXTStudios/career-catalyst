"""Sprint 39.1 regressions for canonical scores in package context."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.package_generator import build_package_context
from scripts.score_match import incomplete_match_report
from tests.test_sprint38_5_reparse_state_consistency import (
    _reopened_live_nation_root,
)


def _complete_report(score: int) -> dict:
    return {
        "match_score": score,
        "match_tier": "Stretch Match",
        "match_summary": "Canonical canary score.",
        "match_strengths": [
            "Experiential production responsibilities are explicit.",
            "Live event scope is clearly identified.",
            "The posting provides enough detail for review.",
        ],
        "match_gaps": ["Confirm reporting line before applying."],
        "recommended_action": "Review First",
        "confidence": "Medium",
    }


def _with_selected_evidence(root: Path, tracker_id: str) -> list[dict]:
    tracker_path = root / "data" / "application_tracker.yml"
    payload = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    projects = yaml.safe_load((root / "data" / "evidence_projects.yml").read_text(encoding="utf-8"))
    records = projects.get("evidence_projects", projects) if isinstance(projects, dict) else projects
    selected = [dict(item) for item in records[:3]]
    payload["applications"][0]["evidence_project_ids"] = [
        str(item["id"]) for item in selected
    ]
    tracker_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return selected


def test_selected_evidence_noop_preserves_canonical_package_score(tmp_path, monkeypatch):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    selected = _with_selected_evidence(root, tracker_id)
    before = yaml.safe_load((root / "data" / "application_tracker.yml").read_text(encoding="utf-8"))

    def score(_job, _root, associated, **_kwargs):
        if associated:
            return incomplete_match_report(
                {"company": "Live Nation Worldwide", "job_title": "Producer", "job_description": ""}
            )
        return _complete_report(62)

    monkeypatch.setattr("scripts.package_generator.score_job_match", score)
    context = build_package_context(tracker_id, before, root)

    assert len(context["associated_evidence_projects"]) == len(selected) == 3
    assert context["baseline_match_report"]["match_score"] == 62
    assert context["match_report"]["match_score"] == 62
    assert context["evidence_score_contribution"]["before"] is None
    assert context["evidence_score_contribution"]["after"] == 62
    assert context["evidence_score_contribution"]["delta"] is None
    assert context["match_report"]["evaluation_unavailable"] is True
    assert context["match_report"].get("incomplete_import") is not True
    assert before["applications"][0]["match_score"] == 62
    assert before["applications"][0]["evidence_project_ids"] == [item["id"] for item in selected]


def test_truly_unscored_role_does_not_inherit_a_package_score(tmp_path, monkeypatch):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    payload = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    for field in (
        "match_score",
        "match_tier",
        "match_summary",
        "match_strengths",
        "match_gaps",
        "recommended_action",
        "confidence",
    ):
        payload["applications"][0].pop(field, None)
    tracker_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(
        "scripts.package_generator.score_job_match",
        lambda *_args, **_kwargs: incomplete_match_report(
            {"company": "Live Nation Worldwide", "job_title": "Producer", "job_description": ""}
        ),
    )
    context = build_package_context(tracker_id, payload, root)

    assert context["match_report"]["match_score"] is None
    assert context["match_report"]["incomplete_import"] is True
    assert context["baseline_match_report"]["match_score"] is None


def test_valid_evidence_adjustment_uses_canonical_base_score(tmp_path, monkeypatch):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    _with_selected_evidence(root, tracker_id)
    tracker = yaml.safe_load((root / "data" / "application_tracker.yml").read_text(encoding="utf-8"))

    def score(_job, _root, associated, **_kwargs):
        report = _complete_report(68 if associated else 62)
        if associated:
            report["associated_evidence_matches"] = ["production"]
        return report

    monkeypatch.setattr("scripts.package_generator.score_job_match", score)
    context = build_package_context(tracker_id, tracker, root)

    assert context["baseline_match_report"]["match_score"] == 62
    assert context["match_report"]["match_score"] == 68
    assert context["match_report"]["base_match_score"] == 62
    assert context["match_report"]["evidence_score_delta"] == 6
    assert context["evidence_score_contribution"]["delta"] == 6


def test_incomplete_evidence_report_does_not_mutate_tracker_snapshot(tmp_path, monkeypatch):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    _with_selected_evidence(root, tracker_id)
    tracker_path = root / "data" / "application_tracker.yml"
    before = tracker_path.read_bytes()
    tracker = yaml.safe_load(before)

    monkeypatch.setattr(
        "scripts.package_generator.score_job_match",
        lambda *_args, **_kwargs: incomplete_match_report(
            {"company": "Live Nation Worldwide", "job_title": "Producer", "job_description": ""}
        ),
    )
    context = build_package_context(tracker_id, tracker, root)

    assert context["match_report"]["match_score"] == 62
    assert tracker_path.read_bytes() == before
