"""Sprint 38.2 tests for stable-ID existing-prospect reparse and rescore."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from app import reparse_dashboard_role
from scripts.application_tracker import load_application_tracker
from tests.test_sprint36_role_intelligence_overrides import (
    _airbnb_overrides,
    _isolated_root,
)


LIVE_NATION_TITLE = (
    "LN Media & Sponsorship || Future Freelance Opportunities: "
    "Live Event Experiential Producers"
)
LIVE_NATION_BODY = """
Live Nation Media & Sponsorship seeks experienced producers to manage experiential live event production.
Responsibilities include production management, production budgets and timelines, fabrication, venue sourcing,
onsite builds, load-in/load-out, vendor management, and production logistics. Partner with clients and creative teams.
"""


def _write_live_nation_fixture(root: Path, tracker_id: str = "live-nation-role") -> dict:
    source_job = root / "jobs" / "example_brand_group_marketing_operations_integration.md"
    job_text = (
        f"# {LIVE_NATION_TITLE}\n\n"
        "Company: Live Nation Worldwide\n"
        f"Tracker ID: {tracker_id}\n"
        "Official URL: https://example.invalid/live-nation\n\n"
        f"## Job Description\n{LIVE_NATION_BODY.strip()}\n"
    )
    source_job.write_text(job_text, encoding="utf-8")
    tracker_path = root / "data" / "application_tracker.yml"
    tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8")) or {}
    record = tracker["applications"][0]
    record.update(
        {
            "id": tracker_id,
            "stable_slug": tracker_id,
            "company": "Live Nation Worldwide",
            "role": LIVE_NATION_TITLE,
            "status": "Prospect",
            "priority": "High",
            "job_file": str(source_job.relative_to(root)),
            "match_score": 62,
            "role_family": "generic_senior_operator",
            "company_category": "marketing_advertising",
            "inferred_role_intelligence": {
                "role_family": "generic_senior_operator",
                "role_family_label": "Generic Senior Operator",
            },
            "evidence_project_ids": [
                "enterprise_media_operations_transformation",
            ],
            "application_history": [{"event": "created", "date": "2026-01-01"}],
            "material_paths": {"ats_docx": "/tmp/existing-ats.docx"},
            "package_manifest": {
                "prospect_id": tracker_id,
                "materials": {"ats_docx": "/tmp/existing-ats.docx"},
            },
        }
    )
    tracker_path.write_text(yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8")
    return copy.deepcopy(record)


def test_reparse_live_nation_preserves_identity_and_refreshes_inference(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    before = _write_live_nation_fixture(root, tracker_id)

    result = reparse_dashboard_role(tracker_id, "", root)
    after = load_application_tracker(root)[0]

    assert result["previous_score"] == 62
    assert isinstance(result["new_score"], int)
    assert result["new_role_family"] == "Experiential Production / Live Event Production"
    assert result["inferred_role_family"] == "Experiential Production / Live Event Production"
    assert after["id"] == before["id"] == tracker_id
    assert after["status"] == before["status"] == "Prospect"
    assert after["priority"] == before["priority"] == "High"
    assert after["evidence_project_ids"] == before["evidence_project_ids"]
    assert after["application_history"] == before["application_history"]
    assert after["material_paths"] == before["material_paths"]
    assert after["package_manifest"] == before["package_manifest"]
    assert after["inferred_role_intelligence"]["role_family"] == "experiential_live_event_production"
    assert len(load_application_tracker(root)) == 1
    assert not (tmp_path / "exports").exists()


def test_reparse_uses_optional_refresh_without_duplicate_or_package_side_effect(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    before = _write_live_nation_fixture(root, tracker_id)
    refreshed = LIVE_NATION_BODY + " The producer owns onsite execution through load-out."

    result = reparse_dashboard_role(tracker_id, refreshed, root)
    after = load_application_tracker(root)[0]
    job_text = (root / before["job_file"]).read_text(encoding="utf-8")

    assert result["used_refreshed_description"] is True
    assert "onsite execution through load-out" in job_text
    assert after["id"] == tracker_id
    assert after["status"] == "Prospect"
    assert after["evidence_project_ids"] == before["evidence_project_ids"]
    assert after["package_manifest"] == before["package_manifest"]
    assert len(load_application_tracker(root)) == 1


def test_saved_override_remains_authoritative_while_inferred_snapshot_refreshes(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8")) or {}
    record = tracker["applications"][0]
    overrides = _airbnb_overrides()
    record.update(
        {
            "role_intelligence_overrides": overrides,
            "match_score": 75,
            "status": "Applied",
            "priority": "Medium",
            "evidence_project_ids": ["enterprise_media_operations_transformation"],
            "application_history": [{"event": "status changed", "date": "2026-01-02"}],
            "material_paths": {"ats_docx": "/tmp/airbnb-ats.docx"},
        }
    )
    tracker_path.write_text(yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8")

    reparse_dashboard_role(tracker_id, "", root)
    after = load_application_tracker(root)[0]

    assert after["role_intelligence_overrides"] == overrides
    assert after["role_family"] == overrides["role_family"]
    assert after["status"] == "Applied"
    assert after["match_score"] is not None
    assert after["evidence_project_ids"] == ["enterprise_media_operations_transformation"]
    assert after["application_history"] == [{"event": "status changed", "date": "2026-01-02"}]
    assert after["material_paths"] == {"ats_docx": "/tmp/airbnb-ats.docx"}
    assert after["inferred_role_intelligence"]["source"] == "dynamic_inference"


def test_existing_role_editor_exposes_explicit_reparse_control():
    import inspect
    import app

    assert "Re-parse details and re-score" in inspect.getsource(app._render_role_card)
