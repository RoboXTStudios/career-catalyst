from copy import deepcopy
from pathlib import Path
import yaml
import pytest
from docx import Document
from scripts.application_tracker import load_application_tracker, update_prospect
from scripts.dynamic_role_intelligence import get_effective_voice_profile
from scripts.evidence_engine import load_evidence_projects
from scripts.evidence_tailoring import cover_letter_project_paragraph, reconcile_manual_evidence, select_evidence_for_artifact, evidence_score_contribution
from scripts.package_generator import build_package_context
from scripts.parse_job import parse_job_description
from scripts.role_intent import build_role_intent, tailoring_plan
from scripts.role_editing import material_editing_plan
from scripts.score_match import score_job_data, score_job_match, persisted_match_fields
from scripts.tailor_resume import tailor_resume
from scripts.generate_cover_letter import generate_cover_letter
from scripts.export_docx import export_ats_docx, export_styled_docx
from scripts.docx_quality import inspect_docx_hygiene, extract_docx_structure
from scripts.text_cleanup import normalize_candidate_text
from tests.test_sprint31_1_evidence_tailoring_integration import _isolated_root
from tests.fixture_support import replace_evidence_projects

FIXTURE = Path("tests/fixtures/jobs/one_firefly_agency_operations.md")

@pytest.fixture
def case(tmp_path):
    root, job = _isolated_root(tmp_path, FIXTURE)
    parsed = parse_job_description(root / job)
    projects = load_evidence_projects(root)
    ids = ["enterprise_media_operations_transformation", "operational_workflow_design_airtable_implementation", "campaignos"]
    selected = [next(p for p in projects if p["id"] == id) for id in ids]
    talent = {"id": "talent_development_career_acceleration", "title": "Talent Development & Career Acceleration", "status": "Active", "external_use": True, "problem": "Team leads needed people leadership and delivery support.", "actions": "Coached team leads and developed people leadership through regular feedback and clear delivery standards.", "results": "Improved team capability and delivery quality.", "skills": ["People Leadership"], "technologies": [], "tags": ["Leadership"]}
    projects.append(talent)
    selected.insert(1, talent)
    replace_evidence_projects(root / "data/evidence_projects.yml", projects)
    record = {"id": "one_firefly_director_of_agency_operations", "company": "One Firefly", "role": parsed["job_title"], "status": "Prospect", "show_on_dashboard": True, "priority": "Medium", "source": "Company career page", "job_file": str(job), "location": parsed["location"], "work_arrangement": "Remote", "salary_range": parsed["salary_range"], "posting_date": parsed["posting_date"], "evidence_project_ids": [p["id"] for p in selected]}
    record.update(persisted_match_fields(score_job_match(job, root)))
    (root / "data/application_tracker.yml").write_text(yaml.safe_dump({"applications": [record]}))
    return root, job, parsed, selected, record


def test_one_firefly_classification_and_mandate(case):
    root, job, parsed, selected, record = case
    intelligence = get_effective_voice_profile("One Firefly", parsed["job_title"], parsed["raw_text"])
    assert intelligence["company_category"] == "marketing_advertising"
    assert intelligence["role_family"] == "business_operations"
    intent = build_role_intent({**parsed, "role_family": intelligence["role_family"]}, root)
    assert intent["primary_archetype"] == "general_operations"
    assert intent["mandate"] == "agency_delivery"
    assert "delivery-team leaders" in intent["primary_hiring_need"]
    assert "shared services" not in intent["primary_hiring_need"]


def test_input_parity_and_noise(case):
    root, job, parsed, selected, record = case
    body = parsed["raw_text"].split("## Job Description", 1)[1].strip()
    intake = score_job_data({**record, "job_title": record["role"], "job_description": body}, root)
    saved = score_job_match(job, root)
    assert intake["match_score"] == saved["match_score"]
    assert intake["evaluation_snapshot"]["posting_fingerprint"] == saved["evaluation_snapshot"]["posting_fingerprint"]
    noise = [{"id": "noise", "actions": "not people them they who what one real"}]
    report = score_job_match(job, root, noise)
    assert not report["associated_evidence_matches"]
    assert not report["associated_evidence_match_details"]
    assert report["evidence_score_delta"] == 0


def test_evaluation_lifecycle_and_legacy_safety(case):
    root, job, parsed, selected, record = case
    original = deepcopy(record["evaluation_snapshot"])
    report = score_job_match(job, root, selected)
    updated = update_prospect(record["id"], persisted_match_fields(report), root)
    snapshot = updated["evaluation_snapshot"]
    assert snapshot["base_score"] == original["base_score"]
    assert snapshot["adjusted_score"] == report["match_score"]
    assert snapshot["evidence_delta"] == report["match_score"] - original["base_score"]
    assert snapshot["previous_evaluation_id"] == original["evaluation_id"]
    update_prospect(record["id"], persisted_match_fields(report), root)
    context = build_package_context(record["id"], load_application_tracker(root), root)
    assert context["evidence_score_contribution"]["before"] == original["base_score"]
    assert load_application_tracker(root)[0]["evaluation_snapshot"] == snapshot
    # A historical 68 without provenance remains historical; never infer +14.
    legacy = {k: v for k, v in record.items() if k != "evaluation_snapshot"}
    legacy["match_score"] = 68
    before = deepcopy(legacy)
    context = build_package_context(record["id"], [legacy], root)
    assert legacy == before
    assert context["match_report"]["evaluation_snapshot"]["previous_evaluation_id"] is None
    assert context["evidence_score_contribution"]["before"] == original["base_score"]


def test_manual_precedence_and_capacity(case):
    root, job, parsed, selected, record = case
    intent = build_role_intent(parsed, root)
    intent["suppressed_evidence"] = ["campaignos", "career_catalyst", "photography"]
    resolved = reconcile_manual_evidence(intent, selected)
    assert "campaignos" not in resolved["suppressed_evidence"]
    assert "campaignos" in intent["suppressed_evidence"]
    assert "CampaignOS" not in tailoring_plan(resolved)["de_emphasizing"]
    assert "campaignos" not in material_editing_plan(parsed, root, resolved)["omitted_evidence"]
    plan = tailoring_plan(build_package_context(record["id"], [record], root)["role_intent"])
    assert plan["planned_artifact_selections"]["ats_resume"]["capacity"] == 4
    assert plan["planned_artifact_selections"]["styled_resume"]["capacity"] == 4
    assert plan["planned_artifact_selections"]["cover_letter"]["capacity"] == 2
    for kind, capacity in [("ats_resume", 4), ("styled_resume", 4), ("cover_letter", 2)]:
        decision = select_evidence_for_artifact(parsed, selected, artifact_type=kind)
        assert len(decision["used"]) == capacity
        assert len(decision["omitted"]) == 4-capacity
        assert all(item["reason"] for item in decision["omitted"])


def test_no_false_semantic_explanation():
    result = evidence_score_contribution({"match_score": 68}, {"match_score": 72, "associated_evidence_match_details": []})
    assert "keyword overlap" in result["explanation"]
    assert result["delta"] == 4


def test_saved_description_reaches_package(case):
    root, job, parsed, selected, record = case
    record["job_description"] = parsed["raw_text"].split("## Job Description", 1)[1] + "\nA unique delivery visibility mandate."
    context = build_package_context(record["id"], [record], root)
    assert "unique delivery visibility" in context["parsed_job"]["raw_text"]
    expected = score_job_data({**record, "job_title": record["role"]}, root, selected)
    assert context["match_report"]["match_score"] == expected["match_score"]


def test_final_documents_follow_mandate_and_metadata(case):
    root, job, parsed, selected, record = case
    context = build_package_context(record["id"], [record], root)
    intent = context["role_intent"]
    resume = tailor_resume("executive_operations", job, root, selected, intent)
    ats = export_ats_docx(resume["output_path"], root)
    styled = export_styled_docx(resume["output_path"], root)
    letter = generate_cover_letter(job, root, selected, intent)
    for artifact in [ats, styled, {"output_path": letter["docx_output_path"]}]:
        path = Path(artifact["output_path"])
        text = extract_docx_structure(path)["text"].lower()
        assert "shared services" not in text
        assert "multi-brand" not in text
        assert "shared-service" not in text
        assert "connect brands" not in text
        assert "people" in text and "delivery" in text
        properties = Document(path).core_properties
        assert properties.author == properties.last_modified_by == "Trisha Lynch"
        assert inspect_docx_hygiene(path)["status"] == "PASS"
    assert len(resume["evidence_selection"]["selected_ids"]) == 4
    assert len(resume["evidence_selection"]["used"]) == 4
    assert len(letter["evidence_selection"]["used"]) == 2
    for artifact in (ats, styled):
        text = extract_docx_structure(Path(artifact["output_path"]))["text"].lower()
        for project in selected:
            assert normalize_candidate_text(project["title"]).lower() in text
    letter_text = extract_docx_structure(Path(letter["docx_output_path"]))["text"].lower()
    for project in selected:
        assert normalize_candidate_text(project["title"]).lower() not in letter_text


def test_claim_safety_copy_is_removed():
    text = normalize_candidate_text("I led delivery while staying precise about the scope of my direct experience.")
    assert text == "I led delivery."


def test_add_prospect_preserves_intake_evaluation_without_rescore(case):
    from unittest.mock import patch
    from scripts.prospect_intake import create_prospect
    root, job, parsed, selected, record = case
    values = {**record, "company": "Example Agency", "job_title": record["role"],
              "job_description": parsed["raw_text"].split("## Job Description", 1)[1]}
    values["match_report"] = score_job_data(values, root)
    with patch("scripts.prospect_intake.score_job_match") as rescore:
        result = create_prospect(values, root, run_match_analysis=False)
    rescore.assert_not_called()
    saved = result["application"]
    assert saved["evaluation_snapshot"] == values["match_report"]["evaluation_snapshot"]
    assert saved["job_description"] == values["job_description"].strip()
    assert saved["requirements"]


def test_snapshot_changes_when_same_evidence_id_content_changes(case):
    root, job, parsed, selected, record = case
    first = score_job_match(job, root, selected)
    edited = deepcopy(selected)
    edited[0]["actions"] += " Added workflow governance."
    second = score_job_match(job, root, edited)
    assert first["evaluation_snapshot"]["evidence_fingerprint"] != second["evaluation_snapshot"]["evidence_fingerprint"]
    assert first["evaluation_snapshot"]["profile_fingerprint"] == second["evaluation_snapshot"]["profile_fingerprint"]


def test_agency_customer_context_does_not_override_employer_identity():
    profile = get_effective_voice_profile("Example Software", "AI Systems Director",
        "We develop automation software for marketing agency clients using machine learning.")
    assert profile["company_category"] == "ai_technology_startup"


@pytest.mark.parametrize("title", [
    "Enterprise Media Operations Transformation",
    "Operational Workflow Design & Airtable Implementation",
])
def test_cover_letter_evidence_uses_facts_without_card_titles(title):
    project = {"id": "internal_card", "title": title,
               "actions": "Redesigned workflows and clarified ownership.",
               "results": "Improved delivery visibility."}
    text = cover_letter_project_paragraph(project, {})
    assert text == "I redesigned workflows and clarified ownership. This work improved delivery visibility."
    assert title not in text
