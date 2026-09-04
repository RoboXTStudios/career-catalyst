from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import yaml

import app
from scripts.application_tracker import load_application_tracker
from scripts.evidence_engine import rank_evidence_projects
from scripts.prospect_intake import create_prospect, recover_saved_prospect_context


MANUAL_JD = """Director, Marketing Operations
Lead enterprise entertainment marketing operations and cross-functional transformation.
- Own operating strategy, workflow governance, and executive stakeholder alignment.
- Develop teams and improve campaign quality across multiple business units.
- Build measurement-ready processes while reducing delivery risk by 25%.
- Experience with gated media and entertainment platforms is required.
"""

REPORT = {
    "match_score": 90,
    "match_tier": "Strong Match",
    "match_summary": "Strong alignment with leadership and marketing operations.",
    "match_strengths": ["Leadership", "Entertainment operations", "Transformation"],
    "match_gaps": ["Confirm source freshness."],
    "recommended_action": "Generate Package",
    "confidence": "High",
}


def _root(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump({"applications": []}), encoding="utf-8"
    )
    return tmp_path


def test_manual_jd_and_prescore_survive_add_and_restart_without_refetch(tmp_path):
    root = _root(tmp_path)
    values = {
        "company": "Example Entertainment",
        "job_title": "Director, Marketing Operations",
        "official_url": "https://www.theladders.com/job/gated-role",
        "source": "Ladders",
        "job_description": MANUAL_JD,
        "match_report": REPORT,
        "next_action": "Paste the job description and re-score before generating package.",
    }
    with patch("scripts.prospect_intake.import_job_from_url") as fetch, patch(
        "scripts.prospect_intake.score_job_match"
    ) as rescore:
        result = create_prospect(values, root, run_match_analysis=False)
    fetch.assert_not_called()
    rescore.assert_not_called()

    saved = load_application_tracker(root)[0]
    assert saved["job_description"] == MANUAL_JD.strip()
    assert saved["match_score"] == 90
    assert saved["match_strengths"] == REPORT["match_strengths"]
    assert saved["match_gaps"]
    assert saved["requirements"]
    assert "Paste the job description" not in saved["next_action"]
    assert "Not scored yet" not in app._match_score_html(saved)

    # A fresh load from disk retains the canonical text and analysis state.
    reloaded = load_application_tracker(root)[0]
    assert reloaded == saved
    assert recover_saved_prospect_context(reloaded, root) == {}
    assert result["application"]["job_description"] == MANUAL_JD.strip()


def test_legacy_buggy_record_recovers_from_local_job_file_only(tmp_path):
    root = _root(tmp_path)
    created = create_prospect(
        {
            "company": "Example Entertainment",
            "job_title": "Director, Marketing Operations",
            "job_description": MANUAL_JD,
        },
        root,
    )
    tracker_id = created["tracker_id"]
    stored = yaml.safe_load((root / "data" / "application_tracker.yml").read_text(encoding="utf-8"))
    for field in ("job_description", "match_score", "requirements"):
        stored["applications"][0].pop(field, None)
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(stored), encoding="utf-8"
    )
    buggy = load_application_tracker(root)[0]
    with patch("scripts.prospect_intake.import_job_from_url") as fetch:
        updates = recover_saved_prospect_context(buggy, root)
    fetch.assert_not_called()
    assert updates["job_description"] == MANUAL_JD.strip()
    assert updates["match_score"] is not None
    assert updates["requirements"]


def test_evidence_intelligence_uses_stored_jd_without_changing_manual_selection():
    application = {
        "company": "Example Entertainment",
        "role": "Director, Marketing Operations",
        "job_description": MANUAL_JD,
        "evidence_project_ids": ["manual"],
    }
    projects = [
        {
            "id": "recommended",
            "title": "Enterprise Transformation",
            "status": "Active",
            "industry": "Entertainment",
            "function": "Marketing Operations",
            "problem": "Enterprise workflows needed governance.",
            "actions": "Led cross-functional transformation with executive stakeholders.",
            "results": "Reduced delivery risk by 25%.",
            "skills": [], "technologies": [], "tags": ["Leadership"],
        },
        {
            "id": "manual", "title": "Manual Choice", "status": "Active",
            "problem": "A workflow needed attention.", "actions": "Improved it.",
            "results": "Improved delivery.", "skills": [], "technologies": [], "tags": [],
        },
    ]
    before_projects = deepcopy(projects)
    before_application = deepcopy(application)
    ranked = rank_evidence_projects(application, projects, limit=5)
    assert ranked[0]["project_id"] == "recommended"
    assert application == before_application
    assert projects == before_projects
    assert application["evidence_project_ids"] == ["manual"]


def test_evidence_intelligence_ui_is_above_manual_selector():
    source = Path(app.__file__).read_text(encoding="utf-8")
    preview = source.index("def _render_intelligence_preview")
    intelligence = source.index("_render_evidence_intelligence(st", preview)
    selector = source.index("_render_role_evidence_selection(", intelligence)
    assert intelligence < selector
    helper = source.index("def _render_evidence_intelligence")
    assert 'application.get("job_description")' in source[helper:preview]
