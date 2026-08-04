from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml
from docx import Document

from scripts.dynamic_role_intelligence import detect_role_family
from scripts.generate_application_note import additional_information_content
from scripts.generate_cover_letter import _word_count
from scripts.package_generator import generate_package
from scripts.parse_job import parse_job_description
from scripts.role_editing import rewrite_banned_voice_phrases
from scripts.role_intent import build_role_intent

from tests.test_sprint35_package_scoring_reliability import (
    FIXTURES,
    ROOT,
    _fixture_evidence,
)


CASES = (
    (
        "openai_sales_strategy_operations_central",
        "openai_sales_strategy_operations.md",
        [
            "enterprise_media_operations_transformation",
            "career_catalyst",
            "disney_plus_launch_readiness",
        ],
        "Senior Strategy & Operations Leader | Transformation | AI Systems | Marketing Operations",
        "strategy_gtm_operations",
    ),
    (
        "twitch_senior_label_relations_manager",
        "twitch_senior_label_relations_manager.md",
        ["just_for_us_podcast", "roboxt_studios", "enterprise_media_operations_transformation"],
        "Senior Operations & Entertainment Partnerships Leader | Media Operations | Creator Platforms",
        "music_partnerships_label_relations",
    ),
)


def _isolated_runtime(tmp_path: Path, role_id: str, fixture_name: str, selected_ids: list[str]) -> Path:
    root = tmp_path / role_id
    for name in ("data", "config", "templates"):
        shutil.copytree(ROOT / name, root / name)
    (root / "jobs").mkdir()
    shutil.copy2(FIXTURES / fixture_name, root / "jobs" / fixture_name)
    parsed = parse_job_description(root / "jobs" / fixture_name)
    evidence = _fixture_evidence(selected_ids)
    (root / "data" / "evidence_projects.yml").write_text(
        yaml.safe_dump({"evidence_projects": evidence}, sort_keys=False), encoding="utf-8"
    )
    tracker = {
        "applications": [
            {
                "id": role_id,
                "stable_slug": role_id,
                "company": parsed["company"],
                "role": parsed["job_title"],
                "status": "Prospect",
                "job_file": f"jobs/{fixture_name}",
                "priority": "High",
                "show_on_dashboard": True,
                "evidence_project_ids": selected_ids,
                "material_paths": {},
            }
        ]
    }
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8"
    )
    return root


def test_dynamic_role_intent_supplies_shared_writing_rules():
    for _role_id, fixture_name, _selected_ids, headline, family in CASES:
        parsed = parse_job_description(FIXTURES / fixture_name)
        role_family = detect_role_family(parsed["job_title"], parsed["raw_text"])
        assert role_family == family
        intent = build_role_intent({**parsed, "role_family": role_family}, ROOT)
        assert intent["package_role_family"] == family
        assert intent["resume"]["headline_profile"] == headline
        assert 55 <= len(intent["resume"]["summary_profile"].split()) <= 90
        assert len(intent["resume"]["competency_priorities"]) == 8


@pytest.mark.parametrize("role_id,fixture_name,selected_ids,headline,_family", CASES)
def test_isolated_candidate_documents_follow_writing_standard(
    tmp_path: Path,
    role_id: str,
    fixture_name: str,
    selected_ids: list[str],
    headline: str,
    _family: str,
):
    root = _isolated_runtime(tmp_path, role_id, fixture_name, selected_ids)
    result = generate_package(role_id, root, export_root=tmp_path / "exports")
    assert result["package_complete"] is True
    files = result["manifest"]["files"]
    resume = Path(files["resume_text"]).read_text(encoding="utf-8")
    cover = Path(files["cover_letter"]).read_text(encoding="utf-8")
    additional = Path(files["application_note"]).read_text(encoding="utf-8")
    summary = Path(files["package_summary"]).read_text(encoding="utf-8")
    profile = resume.split("Profile\n\n", 1)[1].split("\n\nCore Competencies", 1)[0]

    assert headline in resume
    assert 55 <= len(profile.split()) <= 90
    assert 300 <= _word_count(cover) <= 400
    assert 900 <= len(additional) <= 1400
    assert not additional.lower().startswith("additional information")
    assert "Dear " not in additional and "Best," not in additional
    assert cover != additional
    assert "—" not in "\n".join((resume, cover, additional))
    assert not re.search(r"\b(?:20\+ years|two decades|nearly two decades|seasoned|veteran)\b", resume + cover + additional, re.I)
    assert "OMD Entertainment" not in resume + cover + additional
    assert "calm senior judgment" not in cover.lower()
    assert "i bring a practical operating style:" not in cover.lower()
    assert "the through line in my experience" not in cover.lower()
    assert "caught my attention" not in cover.lower() + additional.lower()
    restricted = (
        "administered salesforce", "owned quotas", "owned territories", "owned compensation plans",
        "owned sales forecasts", "sql expertise", "owned p&l", "owned revenue operations",
        "owned label accounts", "managed artists", "negotiated label or artist deals",
        "owned commercial forecasting", "music-industry business-development responsibility",
    )
    assert all(phrase not in (resume + cover + additional).lower() for phrase in restricted)
    expected_titles = (
        {"Enterprise Media Operations Transformation", "Career Catalyst", "Disney+ Launch Readiness"}
        if role_id.startswith("openai")
        else {"Just for Us Podcast", "RoboXT Studios", "Enterprise Media Operations Transformation"}
    )
    assert all(title in summary for title in expected_titles)
    if role_id.startswith("twitch"):
        competency_section = resume.split("Core Competencies\n\n", 1)[1].split(
            "Platforms & Technologies", 1
        )[0]
        competencies = [
            line[2:].strip() for line in competency_section.splitlines() if line.startswith("- ")
        ]
        assert competencies == [
            "Media Operations",
            "Entertainment Marketing",
            "Cross-Functional Leadership",
            "Partner Coordination",
            "Workflow Governance",
            "Quality Assurance",
            "Executive Stakeholder Management",
            "Creative Operations",
        ]

    for docx_key in ("ats_docx", "styled_docx"):
        doc_text = "\n".join(paragraph.text for paragraph in Document(files[docx_key]).paragraphs)
        assert headline in doc_text
        assert "—" not in doc_text


def test_twitch_competencies_are_music_partnership_relevant():
    parsed = parse_job_description(FIXTURES / "twitch_senior_label_relations_manager.md")
    role_family = detect_role_family(parsed["job_title"], parsed["raw_text"])
    intent = build_role_intent({**parsed, "role_family": role_family}, ROOT)
    assert intent["resume"]["competency_priorities"] == [
        "Media Operations",
        "Entertainment Marketing",
        "Cross-Functional Leadership",
        "Partner Coordination",
        "Workflow Governance",
        "Quality Assurance",
        "Executive Stakeholder Management",
        "Creative Operations",
    ]
    assert not any(
        re.search(r"\b(?:AI|MarTech|AdTech|Product Operations)\b", competency, re.I)
        for competency in intent["resume"]["competency_priorities"]
    )


def test_additional_information_formatter_is_copy_ready():
    value = additional_information_content("A concise, verified starting point.")
    assert 900 <= len(value) <= 1400
    assert not value.startswith("Additional Information")
    assert "Dear " not in value and "Best," not in value


def test_banned_phrase_rewrite_does_not_corrupt_related_words():
    value, rewrites = rewrite_banned_voice_phrases(
        "The role needs clear planning rhythms and a clear plan for execution."
    )
    assert "clear planning rhythms" in value
    assert "clear operating structure for execution" in value
    assert [item["phrase"] for item in rewrites] == ["clear plan"]
