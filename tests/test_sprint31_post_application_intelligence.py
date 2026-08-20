from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import pytest
import yaml

import app
from scripts.application_tracker import (
    VALID_STATUSES,
    active_tracker_records,
    follow_up_action_state,
    get_record_status,
    is_archive_eligible,
    load_application_tracker,
    update_prospect,
)
from scripts.career_intelligence import INFERENCE_NOTICE, generate_career_intelligence
from scripts.generate_followups import generate_followups
from scripts.materials_library import (
    find_exact_role_package,
    merge_role_package_outputs,
    organize_package_outputs,
)
from scripts.package_generator import generate_package
from scripts.role_archive import (
    ARCHIVE_REASONS,
    archive_role,
    bulk_archive_roles,
    infer_archive_reason,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DISNEY_FIXTURE = Path("tests/fixtures/jobs/disney_principal_product_manager_sanitized.md")


def _runtime(tmp_path: Path, *, status: str = "Applied", tracker_id: str = "disney_fixture") -> tuple[Path, str]:
    root = tmp_path / tracker_id
    for directory in ("config", "data", "templates"):
        shutil.copytree(PROJECT_ROOT / directory, root / directory)
    job = root / "jobs" / DISNEY_FIXTURE.name
    job.parent.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / DISNEY_FIXTURE, job)
    application = {
        "id": tracker_id,
        "stable_slug": tracker_id,
        "company": "Disney Entertainment and ESPN Product & Technology",
        "company_aliases": [],
        "role": "Principal Product Manager",
        "role_aliases": [],
        "status": status,
        "priority": "High",
        "show_on_dashboard": True,
        "job_file": f"jobs/{job.name}",
        "official_url": "https://example.test/disney-role",
        "submitted_date": "2026-01-05",
        "recruiter_email": "recruiting@example.test",
        "follow_up_status": "Due now",
        "application_history": [],
        "material_paths": {},
    }
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump({"applications": [application]}, sort_keys=False),
        encoding="utf-8",
    )
    return root, tracker_id


def _application(root: Path, tracker_id: str) -> dict:
    return next(item for item in load_application_tracker(root) if item["id"] == tracker_id)


def _base_package(root: Path, tracker_id: str) -> dict:
    application = _application(root, tracker_id)
    sources = root / "generated"
    sources.mkdir(exist_ok=True)
    values = {}
    for key, filename, content in (
        ("resume_text", "resume.txt", "verified resume"),
        ("cover_letter_text", "cover.txt", "verified cover letter"),
        ("strategy_pack_text", "strategy.txt", "verified strategy"),
    ):
        path = sources / filename
        path.write_text(content, encoding="utf-8")
        values[key] = str(path)
    organized = organize_package_outputs(root, application, values)
    material_paths = {
        "Tailored Resume": organized["outputs"]["resume_text"],
        "Cover Letter": organized["outputs"]["cover_letter_text"],
        "Strategy Pack": organized["outputs"]["strategy_pack_text"],
    }
    update_prospect(
        tracker_id,
        {"material_paths": material_paths, "package_manifest": organized["manifest"]},
        root,
    )
    return organized


# FOLLOW-UP


def test_base_package_generation_does_not_create_followups_by_default(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path, status="Prospect")
    result = generate_package(tracker_id, root, export_root=root / "canonical")
    assert not any("followup" in key for key in result["outputs"])


def test_explicit_followup_generation_remains_supported(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path)
    result = generate_package(
        tracker_id,
        root,
        generate_followups_too=True,
        export_root=root / "canonical",
    )
    assert "followup_strategy" in result["outputs"]


def test_eligible_followup_statuses():
    for status in ("Applied", "Under Consideration", "Interviewing"):
        record = {
            "status": status,
            "submitted_date": "2026-01-01",
            "recruiter_email": "r@example.test",
            "application_history": [{"event": "interview completed"}],
        }
        assert follow_up_action_state(record)["eligible"]


def test_ineligible_followup_statuses():
    for status in ("Prospect", "Considered", "Offer", "Rejected", "Withdrawn / Closed"):
        assert not follow_up_action_state({"status": status})["eligible"]


def test_followup_plan_has_required_structure(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path)
    result = generate_followups(tracker_id, root)
    plan = result["plan"]
    assert {
        "timing_window",
        "recommended_recipient_type",
        "recommended_channel",
        "objective",
        "rationale",
        "reinforce",
        "primary_message_key",
        "alternative_message_keys",
        "what_to_avoid",
    } <= set(plan)
    assert len(plan["alternative_message_keys"]) == 3


def test_warm_contact_precedes_other_routes(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path)
    update_prospect(tracker_id, {"warm_contact": "Former colleague"}, root)
    assert generate_followups(tracker_id, root)["plan"]["primary_message_key"] == "warm_contact_message"


def test_followup_attachment_preserves_base_manifest(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path)
    _base_package(root, tracker_id)
    application = _application(root, tracker_id)
    generated = generate_followups(tracker_id, root)
    merged = merge_role_package_outputs(
        root,
        application,
        generated["outputs"],
        material_labels=app.FOLLOWUP_PACKAGE_LABELS,
    )
    assert {"resume_text", "cover_letter_text", "strategy_pack_text"} <= set(
        merged["manifest"]["files"]
    )
    assert {"Tailored Resume", "Cover Letter", "Strategy Pack"} <= set(
        merged["material_paths"]
    )
    assert "Follow-Up Plan" in merged["material_paths"]


def test_cross_role_attachment_is_rejected(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path)
    package = _base_package(root, tracker_id)
    manifest_path = Path(package["manifest"]["manifest_path"])
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["prospect_id"] = "different_role"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    incoming = root / "incoming.txt"
    incoming.write_text("new", encoding="utf-8")
    with pytest.raises(ValueError):
        merge_role_package_outputs(root, _application(root, tracker_id), {"interview_prep": str(incoming)})


def test_saving_followup_activity_does_not_change_status(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path)
    before = get_record_status(_application(root, tracker_id))
    update_prospect(tracker_id, {"followup_activity": {"channel": "Email"}}, root)
    assert get_record_status(_application(root, tracker_id)) == before


def test_portal_only_guidance_does_not_manufacture_message():
    state = follow_up_action_state(
        {
            "status": "Applied",
            "submitted_date": "2026-01-01",
            "portal_only": True,
            "application_portal_url": "https://example.test/status",
        }
    )
    assert state["key"] == "check_application_status"
    assert not state["eligible"]


# CAREER INTELLIGENCE


def _intelligence(tmp_path: Path, context: str = "") -> dict:
    root, _ = _runtime(tmp_path)
    return generate_career_intelligence(
        root / "jobs" / DISNEY_FIXTURE.name,
        root,
        {"lead_evidence": ["career_catalyst", "workflow_governance"]},
        additional_context=context,
    )


def test_disney_fixture_company_and_role_are_exact(tmp_path: Path):
    result = _intelligence(tmp_path)
    assert result["company"] == "Disney Entertainment and ESPN Product & Technology"
    assert result["role"] == "Principal Product Manager"


def test_hiring_manager_intent_has_inference_notice(tmp_path: Path):
    result = _intelligence(tmp_path)
    assert result["inference_notice"] == INFERENCE_NOTICE
    assert 3 <= len(result["hiring_manager_intent"]) <= 6


def test_question_groups_are_role_relevant_and_structured(tmp_path: Path):
    result = _intelligence(tmp_path)
    categories = {item["category"] for item in result["question_groups"]}
    assert {"Strategy and product judgment", "Execution and prioritization"} <= categories


def test_each_question_has_direction_evidence_and_caution(tmp_path: Path):
    result = _intelligence(tmp_path)
    questions = [question for group in result["question_groups"] for question in group["questions"]]
    assert questions
    assert all(
        all(question.get(key) for key in ("testing", "answer_direction", "evidence", "caution"))
        for question in questions
    )


def test_user_context_is_clearly_labeled(tmp_path: Path):
    result = _intelligence(tmp_path, "Recruiter said the first screen is 30 minutes.")
    assert "not independently verified" in result["source_basis"][-1]
    assert "User-Supplied Context (not independently verified)" in result["content"]


def test_intelligence_produces_text_and_structured_output(tmp_path: Path):
    result = _intelligence(tmp_path)
    assert Path(result["output_path"]).is_file()
    assert result["structured"]["question_groups"]


def test_refresh_versions_only_interview_prep(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path)
    package = _base_package(root, tracker_id)
    application = _application(root, tracker_id)
    first = root / "first.txt"
    second = root / "second.txt"
    first.write_text("first interview prep", encoding="utf-8")
    second.write_text("refreshed interview prep", encoding="utf-8")
    merge_role_package_outputs(root, application, {"interview_prep": str(first)}, material_labels={"interview_prep": "Interview Prep"})
    merged = merge_role_package_outputs(root, application, {"interview_prep": str(second)}, material_labels={"interview_prep": "Interview Prep"})
    assert len(list(Path(package["manifest"]["manifest_path"]).parent.glob("versions/*/*.txt"))) == 1
    assert Path(merged["manifest"]["files"]["resume_text"]).read_text() == "verified resume"
    assert Path(merged["manifest"]["files"]["cover_letter_text"]).read_text() == "verified cover letter"


def test_user_facing_output_has_no_raw_identifiers(tmp_path: Path):
    text = _intelligence(tmp_path)["content"]
    assert "business_operations_chief_of_staff" not in text
    assert "career_catalyst" not in text


def test_output_has_no_unsupported_candidate_claims(tmp_path: Path):
    text = _intelligence(tmp_path)["content"].lower()
    for phrase in (
        "managed 60+",
        "formal principal product manager",
        "owned disney's product roadmap",
        "managed software engineers",
        "bachelor's degree",
        "revenue growth",
        "60+",
    ):
        assert phrase not in text
    # Current evidence selection no longer forces CampaignOS into every
    # product-adjacent artifact. If it is selected, its prototype qualifier is
    # mandatory; otherwise the intelligence remains grounded in career facts.
    if "campaignos" in text:
        assert "working prototype" in text
    assert "omg23 / omd entertainment, omnicom media group" in text


# ARCHIVE


def test_paused_is_legacy_considered_and_not_archive_eligible():
    record = {"status": "Paused"}
    assert "Paused" not in VALID_STATUSES
    assert get_record_status(record) == "Considered"
    assert not is_archive_eligible(record)


def test_terminal_statuses_are_archive_eligible():
    assert is_archive_eligible({"status": "Rejected"})
    assert is_archive_eligible({"status": "Withdrawn / Closed"})


def test_archive_reasons_preserve_legacy_distinctions():
    assert set(ARCHIVE_REASONS) == {"Rejected", "Withdrawn / Closed", "Hidden / Invalid"}
    assert infer_archive_reason({"status": "Passed"}) == "Withdrawn / Closed"
    assert infer_archive_reason({"status": "Invalid/Hidden"}) == "Hidden / Invalid"


def test_missing_archive_metadata_defaults_active():
    record = {"id": "x", "status": "Prospect"}
    assert active_tracker_records([record]) == [record]


def test_archive_removes_role_from_active_records(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path, status="Rejected")
    archive_role(
        tracker_id, "Rejected", root,
        archive_root=root / "local_archive",
    )
    assert not active_tracker_records(load_application_tracker(root))


def test_archive_moves_exact_package_and_updates_paths(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path, status="Rejected")
    _base_package(root, tracker_id)
    result = archive_role(
        tracker_id, "Rejected", root,
        archive_root=root / "local_archive",
    )
    assert not load_application_tracker(root)
    assert Path(result["folder"], "role_manifest.json").is_file()
    assert all(
        Path(result["folder"], item["filename"]).is_file()
        for item in result["manifest"]["materials"]
    )


def test_role_without_materials_archives_safely(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path, status="Withdrawn / Closed")
    result = archive_role(
        tracker_id, "Withdrawn / Closed", root,
        archive_root=root / "local_archive",
    )
    assert result["manifest"]["materials"] == []
    assert not load_application_tracker(root)


def test_archive_ui_has_no_stale_restore_control():
    source = inspect.getsource(app._render_archive)
    assert "Restore as" not in source
    assert "Reopen as New Prospect" in source


def test_bulk_archive_changes_only_selected_records(tmp_path: Path):
    root, first = _runtime(tmp_path, status="Rejected", tracker_id="first")
    tracker = yaml.safe_load((root / "data/application_tracker.yml").read_text())
    second = dict(tracker["applications"][0], id="second", stable_slug="second")
    tracker["applications"].append(second)
    (root / "data/application_tracker.yml").write_text(yaml.safe_dump(tracker, sort_keys=False))
    result = bulk_archive_roles(
        [first], root, reasons={first: "Rejected"},
        archive_root=root / "local_archive",
    )
    by_id = {item["id"]: item for item in load_application_tracker(root)}
    assert result["archived_count"] == 1
    assert first not in by_id
    assert by_id["second"].get("archived") is not True


def test_archive_never_deletes_material_content(tmp_path: Path):
    root, tracker_id = _runtime(tmp_path, status="Rejected")
    _base_package(root, tracker_id)
    archive_role(
        tracker_id, "Rejected", root,
        archive_root=root / "local_archive",
    )
    archived_text = {
        path.read_text(encoding="utf-8")
        for path in (root / "local_archive").rglob("*.txt")
    }
    assert {"verified resume", "verified cover letter", "verified strategy"} <= archived_text


def test_navigation_replaces_followup_with_intelligence_and_archive():
    source = inspect.getsource(app.main)
    assert '"Follow-Up"' not in source
    assert '"Career Intelligence"' in source
    assert '"Archive"' in source
