from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import pytest

import app
import yaml
from scripts.dynamic_role_intelligence import detect_role_family
from scripts.evidence_tailoring import (
    cover_letter_project_paragraph,
    deduplicate_evidence_projects,
    recommend_evidence_ids,
    select_evidence_for_artifact,
)
from scripts.generate_application_note import additional_information_content
from scripts.package_generator import generate_package
from scripts.package_materials import validate_complete_package
from scripts.parse_job import parse_job_description
from scripts.role_intent import build_role_intent
from scripts.score_match import score_job_data, score_job_match
from scripts.storage_paths import canonical_storage_path, require_beneath_export_root
from scripts.text_cleanup import (
    missing_subject_prose_fragments,
    normalize_campaignos_claims,
    normalize_candidate_text,
)
from scripts.role_state_resolver import selected_evidence_ids


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sprint35"


def _complete_outputs(folder: Path) -> dict[str, str]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = {
        "ats_docx": folder / "resume_ats.docx",
        "styled_docx": folder / "resume_styled.docx",
        "cover_letter_docx": folder / "cover_letter.docx",
        "package_summary": folder / "package_summary.txt",
    }
    for path in paths.values():
        path.write_bytes(b"complete")
    manifest = folder / "manifest.json"
    manifest.write_text(
        json.dumps({"prospect_id": "role-a", "files": {key: str(path) for key, path in paths.items()}}),
        encoding="utf-8",
    )
    return {**{key: str(path) for key, path in paths.items()}, "manifest_path": str(manifest)}


def _fixture_evidence(selected_ids: list[str]) -> list[dict[str, object]]:
    records = {
        "just_for_us_podcast": {
            "id": "just_for_us_podcast",
            "title": "Just for Us Podcast",
            "problem": "A multi-host audio series required consistent editorial and release quality.",
            "actions": (
                "Served as audio producer and editor for a ten-episode, multi-host series, managing "
                "dialogue editing, pacing, audio balancing, revisions, and quality control."
            ),
            "results": "Released ten release-ready episodes on Spotify.",
        },
        "roboxt_studios": {
            "id": "roboxt_studios",
            "title": "RoboXT Studios",
            "problem": "A public creative practice required a coherent operating foundation.",
            "actions": "Founded the studio and built creative production workflows.",
            "results": "Established a working creative and technology practice.",
        },
        "enterprise_media_operations_transformation": {
            "id": "enterprise_media_operations_transformation",
            "title": "Enterprise Media Operations Transformation",
            "problem": "Cross-functional media operations required clearer governance and delivery.",
            "actions": "Led cross-functional operations, workflow design, and stakeholder alignment.",
            "results": "Improved visibility, execution quality, and reliable delivery.",
        },
        "career_catalyst": {
            "id": "career_catalyst",
            "title": "Career Catalyst",
            "problem": "Job-search work required role-aware product workflows and quality controls.",
            "actions": "Created and led development of an active AI-enabled career intelligence product.",
            "results": "Built and iterated tested local workflows, acceptance criteria, and release guardrails.",
        },
        "disney_plus_launch_readiness": {
            "id": "disney_plus_launch_readiness",
            "title": "Disney+ Launch Readiness",
            "problem": "The launch required coordinated governance and measurement readiness.",
            "actions": "Coordinated governance, QA, and cross-functional execution.",
            "results": "Improved launch readiness and measurement coordination.",
        },
    }
    return [{**records[identity], "status": "Active"} for identity in selected_ids]


def test_false_success_is_rejected_when_required_artifacts_are_absent(tmp_path: Path):
    report = validate_complete_package({"resume_markdown": str(tmp_path / "resume.md")})
    assert report["complete"] is False
    assert set(report["missing_required"]) == {
        "ATS Resume DOCX", "Styled Resume DOCX", "Cover Letter DOCX", "Package Summary", "Canonical Manifest"
    }


def test_zero_byte_or_missing_required_file_blocks_success(tmp_path: Path):
    outputs = _complete_outputs(tmp_path / "package")
    Path(outputs["cover_letter_docx"]).write_bytes(b"")
    report = validate_complete_package(outputs)
    assert report["complete"] is False
    assert report["missing_required"] == ["Cover Letter DOCX"]


def test_complete_package_is_derived_from_real_final_files(tmp_path: Path):
    outputs = _complete_outputs(tmp_path / "package")
    report = validate_complete_package(outputs, owner_id="role-a", export_root=tmp_path)
    assert report["complete"] is True
    assert all(item["exists"] for item in report["checklist"])


def test_private_users_alias_has_one_canonical_identity():
    value = canonical_storage_path("/private/Users/trisha.lynch/Documents/career-catalyst/exports/x.docx")
    assert str(value) == "/Users/trisha.lynch/Documents/career-catalyst/exports/x.docx"


def test_ownership_check_rejects_traversal_and_accepts_alias(tmp_path: Path):
    root = tmp_path / "exports"
    owned = root / "active" / "role" / "resume.docx"
    owned.parent.mkdir(parents=True)
    owned.write_bytes(b"ok")
    assert require_beneath_export_root(owned, root) == owned.resolve()
    with pytest.raises(ValueError):
        require_beneath_export_root(root / ".." / "outside.docx", root)


def test_scoring_snapshot_is_deterministic_and_evidence_is_separate(tmp_path: Path):
    posting = {
        "company": "OpenAI", "role": "Sales Strategy & Operations - Central",
        "location": "San Francisco, CA", "work_arrangement": "Hybrid, three days per week in office",
        "salary_range": "$190,000-$245,000",
        "job_description": (FIXTURES / "openai_sales_strategy_operations.md").read_text(encoding="utf-8"),
    }
    evidence = [{"id": "enterprise_media_operations_transformation", "title": "Enterprise Media Operations Transformation", "actions": "Led strategy and operations.", "results": "Improved operations."}]
    first = score_job_data(posting, tmp_path, evidence)
    second = score_job_data(posting, tmp_path, evidence)
    assert first["evaluation_snapshot"] == second["evaluation_snapshot"]
    assert first["base_match_score"] + first["evidence_score_delta"] == first["match_score"]
    assert first["work_arrangement"] == "Hybrid, three days per week in office"
    changed = score_job_data({**posting, "location": "New York, NY"}, tmp_path, evidence)
    assert changed["evaluation_snapshot"]["posting_fingerprint"] != first["evaluation_snapshot"]["posting_fingerprint"]


def test_remote_credit_comes_from_posting_arrangement_not_unrelated_text(tmp_path: Path):
    posting = {
        "company": "Example", "role": "Senior Manager, Operations", "location": "Los Angeles, CA",
        "work_arrangement": "On-site", "salary_range": "$160,000-$180,000",
        "job_description": "This on-site operations role manages workflow and strategy. Candidate experience may include remote collaboration across partner teams.",
    }
    report = score_job_data(posting, tmp_path)
    assert report["work_arrangement"] == "On-site"
    assert not any("remote arrangement" in value.lower() for value in report["match_strengths"])


def test_twitch_role_is_music_partnerships_with_explicit_seniority_and_gap(tmp_path: Path):
    parsed = parse_job_description(FIXTURES / "twitch_senior_label_relations_manager.md")
    role_family = detect_role_family(parsed["job_title"], parsed["raw_text"])
    assert role_family == "music_partnerships_label_relations"
    parsed["role_family"] = role_family
    intent = build_role_intent(parsed, ROOT)
    assert intent["seniority"] == "senior_manager"
    assert intent["package_role_label"] == "Music Partnerships & Label Relations"
    report = score_job_match(FIXTURES / "twitch_senior_label_relations_manager.md", tmp_path)
    assert any("label-relations" in gap for gap in report["match_gaps"])


def test_openai_role_is_strategy_and_gtm_operations_with_honest_gap(tmp_path: Path):
    parsed = parse_job_description(FIXTURES / "openai_sales_strategy_operations.md")
    role_family = detect_role_family(parsed["job_title"], parsed["raw_text"])
    assert role_family == "strategy_gtm_operations"
    parsed["role_family"] = role_family
    intent = build_role_intent(parsed, ROOT)
    assert intent["package_role_label"] == "Strategy & GTM Operations"
    report = score_job_match(FIXTURES / "openai_sales_strategy_operations.md", tmp_path)
    assert any("sales-operations depth" in gap for gap in report["match_gaps"])


def test_role_aware_evidence_recommendations_are_stable_and_deduplicated():
    twitch = parse_job_description(FIXTURES / "twitch_senior_label_relations_manager.md")
    projects = [
        {"id": "just_for_us_podcast", "title": "Just for Us Podcast", "actions": "Produced music and audio partnerships.", "results": "Released a ten-episode series."},
        {"id": "roboxt_studios", "title": "RoboXT Studios", "actions": "Built creative partner workflows.", "results": "Improved delivery."},
        {"id": "enterprise_media_operations_transformation", "title": "Enterprise Media Operations Transformation", "actions": "Led cross-functional operations.", "results": "Improved execution."},
        {"id": "campaignos", "title": "CampaignOS", "actions": "Built a working prototype.", "results": "Validated workflows."},
        {"id": "campaignos", "title": "CampaignOS duplicate", "actions": "Duplicate.", "results": "Duplicate."},
    ]
    assert len(deduplicate_evidence_projects(projects)) == 4
    assert recommend_evidence_ids(twitch, projects, limit=3) == [
        "just_for_us_podcast", "roboxt_studios", "enterprise_media_operations_transformation"
    ]


def test_tracker_evidence_selection_remains_authoritative():
    record = {
        "evidence_project_ids": ["career_catalyst", "enterprise_media_operations_transformation"],
        "recommended_evidence_ids": ["campaignos"],
        "selected_evidence_ids": ["stale"],
    }
    assert selected_evidence_ids(record) == ["career_catalyst", "enterprise_media_operations_transformation"]


def test_candidate_language_repairs_missing_subject_and_protected_claims():
    text = normalize_candidate_text(
        "In RoboXT Studios, founded a studio. Led a team of 64. CampaignOS is a platform. OMD Entertainment — seasoned."
    )
    assert "At RoboXT Studios, I founded" in text
    assert "integrated 64-person organization" in text
    assert "working campaign-operations prototype" in text
    assert "—" not in text and "OMD Entertainment" not in text


@pytest.mark.parametrize(
    "claim",
    (
        "CampaignOS systems at scale",
        "an enterprise rollout of CampaignOS",
        "CampaignOS production platform",
        "CampaignOS shipped at scale",
        "CampaignOS live customer adoption",
        "CampaignOS proven business outcomes",
    ),
)
def test_campaignos_guard_repairs_prohibited_scale_and_deployment_claims(claim: str):
    repaired = normalize_campaignos_claims(f"I built {claim}.")
    assert "prototype" in repaired.lower()
    assert not any(
        phrase in repaired.lower()
        for phrase in (
            "systems at scale", "enterprise rollout", "production platform",
            "shipped at scale", "live customer adoption", "proven business outcomes",
        )
    )


def test_campaignos_guard_identifies_every_reference_as_a_working_prototype():
    repaired = normalize_candidate_text(
        "CampaignOS reflects my workflow approach. I built CampaignOS to improve QA and validation.\n\n### CampaignOS"
    )
    assert repaired.lower().count("prototype") == 3
    assert "built and iterated" in repaired.lower()
    assert "### CampaignOS (Working Prototype)" in repaired


def test_cover_letter_project_prose_has_explicit_subjects_and_resume_bullets_remain_allowed():
    project = _fixture_evidence(["enterprise_media_operations_transformation"])[0]
    paragraph = cover_letter_project_paragraph(project, {})
    assert paragraph.startswith("Through Enterprise Media Operations Transformation, I led")
    assert "This work improved" in paragraph
    assert missing_subject_prose_fragments(paragraph) == []
    assert missing_subject_prose_fragments(
        "In Enterprise Media Operations Transformation, led operations. Improved delivery."
    )
    assert missing_subject_prose_fragments("- Led operations.\n- Improved delivery.") == []


def test_music_role_prioritizes_direct_podcast_evidence_for_resume_and_letter():
    parsed = parse_job_description(FIXTURES / "twitch_senior_label_relations_manager.md")
    evidence = _fixture_evidence(
        ["just_for_us_podcast", "roboxt_studios", "enterprise_media_operations_transformation"]
    )
    resume = select_evidence_for_artifact(
        parsed, evidence, artifact_type="ats_resume", capacity=3
    )
    letter = select_evidence_for_artifact(
        parsed, evidence, artifact_type="cover_letter", capacity=2
    )
    assert [item["id"] for item in resume["used"]][0] == "just_for_us_podcast"
    assert [item["id"] for item in letter["used"]] == [
        "just_for_us_podcast", "enterprise_media_operations_transformation"
    ]


def test_additional_information_is_concise_and_has_no_letter_furniture():
    value = additional_information_content("I bring grounded operations and product experience.")
    assert value.startswith("Additional Information\n")
    assert "Dear " not in value and "Sincerely" not in value
    assert len(value.split()) <= 100


def test_success_ui_requires_complete_final_package():
    source = inspect.getsource(app._render_generate_package)
    assert "package_complete" in source
    assert source.index("package_complete") < source.index("st.success")


def test_generate_package_promotes_then_revalidates():
    source = inspect.getsource(generate_package)
    assert "validate_complete_package" in source
    assert source.rindex("validate_complete_package") > source.index("promote")


@pytest.mark.parametrize("fail_at", (2, 3))
def test_failed_promotion_validation_restores_prior_package_and_tracker(
    tmp_path: Path, monkeypatch, fail_at: int
):
    root = tmp_path / "runtime"
    export_root = tmp_path / "exports"
    (root / "data").mkdir(parents=True)
    record = {
        "id": "role-a", "stable_slug": "role-a", "company": "Example",
        "role": "Senior Manager", "status": "Considered", "evidence_project_ids": [],
        "job_file": "jobs/role-a.md", "material_paths": {},
    }
    tracker_path = root / "data" / "application_tracker.yml"
    tracker_path.write_text(yaml.safe_dump({"applications": [record]}, sort_keys=False), encoding="utf-8")
    (root / "jobs").mkdir()
    (root / "jobs" / "role-a.md").write_text("# Senior Manager\nCompany: Example\n" + "Operations delivery. " * 10, encoding="utf-8")
    prior = export_root / "active" / "in_progress" / "role-a"
    prior.mkdir(parents=True)
    (prior / "prior.txt").write_text("prior valid package", encoding="utf-8")
    (prior / "manifest.json").write_text(json.dumps({"prospect_id": "role-a", "files": {"prior": "prior.txt"}}), encoding="utf-8")
    tracker_before = tracker_path.read_bytes()

    def fake_generate(_role, stage, **kwargs):
        package = Path(kwargs["export_root"]) / "active" / "in_progress" / "role-a"
        outputs = _complete_outputs(package)
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        manifest["manifest_path"] = str(package / "manifest.json")
        return {
            "tracker_id": "role-a", "saved_package_location": str(package),
            "outputs": outputs, "manifest": manifest, "package_complete": True,
        }

    real_validator = validate_complete_package
    calls = {"count": 0}

    def fail_final(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == fail_at:
            return {"complete": False, "missing_required": ["Cover Letter DOCX"], "checklist": []}
        return real_validator(*args, **kwargs)

    monkeypatch.setattr("scripts.package_generator._generate_package_in_place", fake_generate)
    monkeypatch.setattr("scripts.package_generator.validate_complete_package", fail_final)
    with pytest.raises(Exception, match="incomplete|final validation"):
        generate_package("role-a", root, force_clean_draft=True, export_root=export_root)
    assert (prior / "prior.txt").read_text(encoding="utf-8") == "prior valid package"
    assert tracker_path.read_bytes() == tracker_before
    assert not list(prior.parent.glob(".role-a.*"))


@pytest.mark.parametrize(
    ("fixture_name", "role_id", "selected_ids"),
    (
        (
            "openai_sales_strategy_operations.md",
            "openai_sales_strategy_operations_central",
            ["enterprise_media_operations_transformation", "career_catalyst", "disney_plus_launch_readiness"],
        ),
        (
            "twitch_senior_label_relations_manager.md",
            "twitch_senior_label_relations_manager",
            ["just_for_us_podcast", "roboxt_studios", "enterprise_media_operations_transformation"],
        ),
    ),
)
def test_sanitized_role_package_completes_transactionally(
    tmp_path: Path, fixture_name: str, role_id: str, selected_ids: list[str]
):
    root = tmp_path / "runtime"
    for name in ("data", "config", "templates"):
        shutil.copytree(ROOT / name, root / name)
    (root / "jobs").mkdir()
    job = root / "jobs" / fixture_name
    shutil.copy2(FIXTURES / fixture_name, job)
    parsed = parse_job_description(job)
    evidence = _fixture_evidence(selected_ids)
    (root / "data" / "evidence_projects.yml").write_text(
        yaml.safe_dump({"evidence_projects": evidence}, sort_keys=False), encoding="utf-8"
    )
    tracker = {
        "applications": [{
            "id": role_id, "stable_slug": role_id, "company": parsed["company"],
            "role": parsed["job_title"], "status": "Prospect", "job_file": f"jobs/{fixture_name}",
            "priority": "High", "show_on_dashboard": True,
            "evidence_project_ids": selected_ids, "material_paths": {},
        }]
    }
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8"
    )
    baseline = score_job_match(f"jobs/{fixture_name}", root, evidence)
    result = generate_package(role_id, root, export_root=tmp_path / "exports")
    assert result["package_complete"] is True
    assert result["match_score"] == baseline["match_score"]
    assert result["manifest"]["prospect_id"] == role_id
    assert {item["material_type"] for item in result["package_checklist"]} == {
        "ATS Resume DOCX", "Styled Resume DOCX", "Cover Letter DOCX", "Package Summary", "Canonical Manifest"
    }
    for item in result["package_checklist"]:
        assert item["exists"] and Path(item["preferred_open_path"]).stat().st_size > 0
    candidate_text = "\n".join(
        Path(item["preferred_open_path"]).read_text(encoding="utf-8", errors="ignore")
        for item in result["package_checklist"]
        if Path(item["preferred_open_path"]).suffix in {".txt", ".json"}
    )
    assert "—" not in candidate_text
    assert "OMD Entertainment" not in candidate_text
    assert "team of 64" not in candidate_text.lower()

    files = result["manifest"]["files"]
    cover_letter = Path(files["cover_letter"]).read_text(encoding="utf-8")
    additional = Path(files["application_note"]).read_text(encoding="utf-8")
    summary = Path(files["package_summary"]).read_text(encoding="utf-8")
    assert missing_subject_prose_fragments(cover_letter) == []
    assert missing_subject_prose_fragments(additional) == []
    assert additional.startswith("Additional Information\n")
    assert "Dear " not in additional and "Best," not in additional
    assert 900 <= len(additional.split("\n", 1)[1]) <= 1400
    assert "systems at scale" not in candidate_text.lower()

    if role_id.startswith("twitch"):
        assert "Just for Us" in cover_letter
        assert "Enterprise Media Operations Transformation" in cover_letter
        assert "Just for Us Podcast" in summary
        assert "ATS résumé: Used" in summary.split("Just for Us Podcast", 1)[1].splitlines()[0]
        assert "cover letter: Used" in summary.split("Just for Us Podcast", 1)[1].splitlines()[0]
        restricted = (
            "owned label accounts", "negotiated label or artist deals", "managed artists",
            "owned commercial forecasting", "music-industry business-development responsibility",
        )
        assert all(phrase not in cover_letter.lower() for phrase in restricted)
    else:
        assert "CampaignOS" not in "\n".join(
            Path(files[key]).read_text(encoding="utf-8", errors="ignore")
            for key in (
                "resume_text", "cover_letter", "application_note",
                "recruiter_message", "hiring_manager_message", "package_summary",
                "strategy_pack", "interview_prep",
            )
            if files.get(key)
        )
        restricted = (
            "administered salesforce", "owned quotas", "owned territories",
            "owned compensation plans", "owned sales forecasts", "sql expertise",
            "owned p&l", "owned revenue operations",
        )
        assert all(phrase not in cover_letter.lower() for phrase in restricted)
