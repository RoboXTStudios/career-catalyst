from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from scripts.application_tracker import load_application_tracker, update_prospect
from scripts.generate_cover_letter import _word_count, generate_cover_letter
from scripts.package_generator import build_package_context
from scripts.package_generator import generate_package
from scripts.parse_job import parse_job_description
from scripts.role_intent import (
    apply_role_intelligence_overrides,
    build_role_intent,
    normalize_role_intelligence_overrides,
    tailoring_plan,
)
from scripts.tailor_resume import tailor_resume


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/jobs/example_brand_group_marketing_operations_integration.md"
FOUNDATION_FILES = (
    "data/achievements.yml",
    "data/positions.yml",
    "data/skills.yml",
    "data/platforms.yml",
    "data/projects.yml",
    "data/evidence_projects.yml",
    "data/certifications.yml",
    "data/personal_brand.yml",
    "config/settings.yml",
    "config/target_companies.yml",
    "config/role_profiles.yml",
    "config/voice.yml",
    "config/company_voice_profiles.yml",
    "config/evidence_cards.yml",
    "config/writing_voice_profiles.yml",
    "config/role_editing_rules.yml",
    "config/role_intent_rules.yml",
)


def _isolated_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "runtime"
    shutil.copytree(ROOT / "templates", root / "templates")
    for relative in FOUNDATION_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    job = root / "jobs" / FIXTURE.name
    job.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURE, job)
    parsed = parse_job_description(job)
    tracker_id = "airbnb-role"
    record = {
        "id": tracker_id,
        "stable_slug": tracker_id,
        "company": parsed.get("company"),
        "role": parsed.get("job_title"),
        "status": "Considered",
        "priority": "High",
        "show_on_dashboard": True,
        "job_file": str(job.relative_to(root)),
        "match_score": 75,
        "evidence_project_ids": [],
        "application_history": [{"event": "created", "date": "2026-01-01"}],
        "material_paths": {},
    }
    tracker = root / "data" / "application_tracker.yml"
    tracker.parent.mkdir(parents=True, exist_ok=True)
    tracker.write_text(yaml.safe_dump({"applications": [record]}, sort_keys=False), encoding="utf-8")
    return root, tracker_id


def _airbnb_overrides() -> dict[str, object]:
    return {
        "company_voice": "Airbnb / global consumer technology marketplace",
        "category": "Marketing Operations",
        "role_family": "Marketing Strategy & Operations",
        "primary_hiring_need": (
            "Build and manage scalable operating systems for marketing planning, budgeting, "
            "forecasting, resource allocation, performance visibility, and cross-functional execution."
        ),
        "leading_themes": (
            "Marketing operations leadership; operating cadence; annual planning; executive communication; "
            "workflow design; financial and resource stewardship; measurement governance; stakeholder alignment"
        ),
        "supporting_themes": (
            "Airtable workflow transformation; enterprise collaboration adoption; Disney+ operational readiness; "
            "integrated cross-functional leadership"
        ),
    }


def test_partial_override_falls_back_and_normalizes_themes():
    overrides = normalize_role_intelligence_overrides(
        {"category": " Marketing Operations ", "leading_themes": "planning; visibility\nQA"}
    )
    assert overrides == {
        "category": "Marketing Operations",
        "leading_themes": ["planning", "visibility", "QA"],
    }


def test_override_resolution_preserves_inferred_snapshot_and_clear_restores():
    inferred_i = {
        "profile_name": "default",
        "company_category": "nonprofit",
        "company_category_label": "Nonprofit",
        "role_family": "general_operations",
        "role_family_label": "General Operations",
        "company_voice_label": "Nonprofit",
    }
    inferred_r = {
        "primary_archetype": "general_operations",
        "package_role_family": "business_operations",
        "package_role_label": "Senior Operations Leadership",
        "primary_hiring_need": "Inferred need",
        "lead_evidence": ["inferred lead"],
        "supporting_evidence": ["inferred support"],
        "resume": {},
        "cover_letter": {},
    }
    effective_i, effective_r = apply_role_intelligence_overrides(
        {"role_intelligence_overrides": _airbnb_overrides()}, inferred_i, inferred_r
    )
    assert effective_i["company_category"] == "Marketing Operations"
    assert effective_r["effective_role_family"] == "Marketing Strategy & Operations"
    assert effective_r["primary_hiring_need"].startswith("Build and manage scalable")
    assert effective_r["inferred_role_intelligence"]["company_category"] == "nonprofit"
    assert effective_r["inferred_role_intent"]["primary_hiring_need"] == "Inferred need"
    cleared_i, cleared_r = apply_role_intelligence_overrides(
        {"role_intelligence_overrides": {}}, inferred_i, inferred_r
    )
    assert cleared_i["company_category"] == "nonprofit"
    assert cleared_r["primary_hiring_need"] == "Inferred need"


def test_package_context_uses_effective_values_without_score_change(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    tracker = load_application_tracker(root)
    before = build_package_context(tracker_id, tracker, root)["match_report"]["match_score"]
    update_prospect(tracker_id, {"role_intelligence_overrides": _airbnb_overrides()}, root)
    context = build_package_context(tracker_id, load_application_tracker(root), root)
    assert context["match_report"]["match_score"] == before
    assert context["role_intelligence"]["company_category"] == "Marketing Operations"
    assert context["role_intelligence"]["role_family"] == "Marketing Strategy & Operations"
    assert context["role_intent"]["package_role_family"] == "strategy_gtm_operations"
    assert tailoring_plan(context["role_intent"])["detected_role"] == "Marketing Strategy & Operations"
    assert context["inferred_role_intelligence"]["company_category"] != "Marketing Operations"
    assert load_application_tracker(root)[0]["match_score"] == 75


def test_override_drives_resume_and_cover_letter_writing_profile(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    update_prospect(tracker_id, {"role_intelligence_overrides": _airbnb_overrides()}, root)
    context = build_package_context(tracker_id, load_application_tracker(root), root)
    resume = tailor_resume(
        "executive_operations",
        context["job_reference"],
        root,
        role_intent=context["role_intent"],
    )
    resume_text = Path(resume["output_path"]).read_text(encoding="utf-8")
    cover = generate_cover_letter(
        context["job_reference"], root, role_intent=context["role_intent"]
    )
    cover_text = Path(cover["output_path"]).read_text(encoding="utf-8")
    assert "Marketing Operations" in resume_text
    assert "Senior Strategy & Operations Leader" in resume_text
    assert "nonprofit" not in (resume_text + cover_text).lower()
    assert 250 <= _word_count(cover_text) <= 400


def test_package_summary_metadata_discloses_inferred_and_overridden_values(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    update_prospect(tracker_id, {"role_intelligence_overrides": _airbnb_overrides()}, root)
    result = generate_package(tracker_id, root, export_root=tmp_path / "exports")
    disclosure = result["tailoring_metadata"]["role_intelligence"]
    assert disclosure["overrides"]["category"] == "Marketing Operations"
    assert disclosure["effective"]["role_family"] == "Marketing Strategy & Operations"
    assert disclosure["inferred"]["company_category"] != "Marketing Operations"
    summary = Path(result["manifest"]["files"]["package_summary"]).read_text(
        encoding="utf-8"
    )
    assert "Explicit override applied; inferred source retained." in summary
    assert "Marketing Strategy & Operations" in summary


def test_overrides_are_scoped_to_one_stable_role(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    records = load_application_tracker(root)
    records.append({**records[0], "id": "other-role", "stable_slug": "other-role"})
    tracker_path.write_text(yaml.safe_dump({"applications": records}, sort_keys=False), encoding="utf-8")
    update_prospect(tracker_id, {"role_intelligence_overrides": _airbnb_overrides()}, root)
    saved = {record["id"]: record for record in load_application_tracker(root)}
    assert saved[tracker_id]["role_intelligence_overrides"]["category"] == "Marketing Operations"
    assert "role_intelligence_overrides" not in saved["other-role"]


def test_dashboard_save_persists_only_role_intelligence_and_preserves_score_history(tmp_path: Path):
    from app import update_dashboard_role

    root, tracker_id = _isolated_root(tmp_path)
    before = load_application_tracker(root)[0]
    update_dashboard_role(
        tracker_id,
        {"role_intelligence_overrides": {"role_family": "Marketing Strategy & Operations"}},
        root,
    )
    after = load_application_tracker(root)[0]
    assert after["role_intelligence_overrides"] == {
        "role_family": "Marketing Strategy & Operations"
    }
    assert after["status"] == before["status"]
    assert after["match_score"] == before["match_score"]
    assert after["evidence_project_ids"] == before["evidence_project_ids"]
    assert after["application_history"] == before["application_history"]


def test_generated_output_aliases_do_not_create_duplicate_open_keys(tmp_path: Path):
    from app import _show_output_paths

    artifact = tmp_path / "application_note.txt"
    artifact.write_text("isolated output", encoding="utf-8")

    class FakeStreamlit:
        def __init__(self):
            self.buttons = []

        def markdown(self, *_args, **_kwargs):
            return None

        def code(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def button(self, label, key):
            self.buttons.append((label, key))
            return False

    st = FakeStreamlit()
    _show_output_paths(
        st,
        {"application_note": str(artifact), "Application Note": str(artifact)},
        "generated_output",
    )
    assert len(st.buttons) == 1
