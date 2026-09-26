"""Sprint 39.2 regressions for experiential package generation."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.company_voice import company_voice_context
from scripts.package_generator import build_package_context, generate_package
from scripts.application_tracker import load_application_tracker
from scripts.score_match import incomplete_match_report
from tests.test_sprint38_5_reparse_state_consistency import (
    POSTING,
    _reopened_live_nation_root,
)


def _select_three_evidence(root: Path, tracker_id: str) -> None:
    evidence = yaml.safe_load((root / "data" / "evidence_projects.yml").read_text())
    records = evidence["evidence_projects"]
    selected = [record["id"] for record in records[:3]]
    tracker_path = root / "data" / "application_tracker.yml"
    payload = yaml.safe_load(tracker_path.read_text())
    payload["applications"][0]["evidence_project_ids"] = selected
    tracker_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_experiential_family_is_registered_for_company_voice_context():
    context = company_voice_context(
        {
            "company": "Live Nation Worldwide",
            "role": "LN Media & Sponsorship || Future Freelance Opportunities: Live Event Experiential Producers",
            "raw_text": POSTING,
        },
        {},
    )
    assert context["role_family"] == "experiential_live_event_production"
    assert context["role_family_label"] == "Experiential Production / Live Event Production"


def test_reopened_live_nation_generates_experiential_package_in_isolation(tmp_path: Path, monkeypatch):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    _select_three_evidence(root, tracker_id)
    export_root = tmp_path / "exports"

    def canonical_score(_job, _root, associated, **_kwargs):
        if associated:
            return incomplete_match_report(
                {"company": "Live Nation Worldwide", "job_title": "Producer", "job_description": ""}
            )
        return {
            "match_score": 62,
            "match_tier": "Stretch Match",
            "match_summary": "Canonical canary score.",
            "match_strengths": ["Experiential production responsibilities are explicit."],
            "match_gaps": ["Confirm reporting line before applying."],
            "recommended_action": "Review First",
            "confidence": "Medium",
        }

    monkeypatch.setattr("scripts.package_generator.score_job_match", canonical_score)

    result = generate_package(tracker_id, root, export_root=export_root)

    assert result["package_complete"] is True
    assert result["manifest"]["prospect_id"] == tracker_id
    assert {item["material_type"] for item in result["package_checklist"]} == {
        "ATS Resume DOCX",
        "Styled Resume DOCX",
        "Cover Letter DOCX",
        "Package Summary",
        "ATS Parsed Preview",
        "Requirement Coverage Matrix",
        "Interview Conversion Gate",
        "Canonical Manifest",
    }
    for item in result["package_checklist"]:
        assert item["exists"]
        assert Path(item["preferred_open_path"]).is_file()
        assert Path(item["preferred_open_path"]).is_relative_to(export_root)

    files = result["manifest"]["files"]
    assert Path(files["resume_text"]).is_file()
    assert Path(files["styled_docx"]).is_file()
    assert Path(files["cover_letter"]).is_file()
    summary = Path(files["package_summary"]).read_text(encoding="utf-8")
    assert "- Selected: 3" in summary

    tracker = load_application_tracker(root)
    saved = next(record for record in tracker if record["id"] == tracker_id)
    selected_ids = [record["id"] for record in yaml.safe_load(
        (root / "data" / "evidence_projects.yml").read_text()
    )["evidence_projects"][:3]]
    assert saved["evidence_project_ids"] == selected_ids

    context = build_package_context(tracker_id, tracker, root)
    assert context["match_report"]["match_score"] == 62
    assert context["baseline_match_report"]["match_score"] == 62
    # This canary's canonical_score stub returns an incomplete match report
    # whenever Evidence is associated, so build_package_context falls back to
    # the tracker's saved score (scripts/package_generator.py,
    # evaluation_unavailable handling). scripts/evidence_tailoring.py commit
    # df5ac3f made evidence_score_contribution() return delta=None (not 0) in
    # that fallback case, since a retained saved score is not a fresh
    # zero-contribution evaluation - it's an unknown one. That commit
    # predates this test; None is the current, correct value here.
    assert context["match_report"]["evaluation_unavailable"] is True
    assert context["evidence_score_contribution"]["delta"] is None
    assert context["role_intelligence"]["role_family"] == "experiential_live_event_production"
    assert "production" in context["role_intent"]["primary_hiring_need"].lower()

    candidate_text = "\n".join(
        Path(files[key]).read_text(encoding="utf-8", errors="ignore")
        for key in ("resume_text", "cover_letter", "application_note", "package_summary")
    )
    assert "experiential" in candidate_text.lower()
    assert "martech" not in candidate_text.lower()
