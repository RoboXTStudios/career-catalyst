from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from docx import Document

from scripts.application_tracker import load_application_tracker
from scripts.career_intelligence import generate_career_intelligence
from scripts.generate_cover_letter import generate_cover_letter
from scripts.package_generator import build_package_context, generate_package
from scripts.package_quality import save_package_summary
from scripts.parse_job import parse_job_description
from scripts.tailor_resume import tailor_resume
from scripts.text_cleanup import normalize_candidate_text
from tests.fixture_support import confirm_tracker_role_family
from tests.test_sprint34_application_reliability_gate import _write_openai_fixture_runtime


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_normalize_spaced_and_unspaced_em_dashes():
    assert normalize_candidate_text("one — two") == "one - two"
    assert normalize_candidate_text("one—two") == "one - two"


def test_normalize_multiple_em_dashes_and_is_idempotent():
    value = normalize_candidate_text("one—two — three——four")
    assert value == "one - two - three - four"
    assert normalize_candidate_text(value) == value


def test_normalization_preserves_hyphens_ranges_and_urls():
    value = "AI-enabled 2016-2026 https://example.test/a-b"
    assert normalize_candidate_text(value) == value


def isolated_runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    shutil.copytree(PROJECT_ROOT / "data", root / "data")
    shutil.copytree(PROJECT_ROOT / "config", root / "config")
    shutil.copytree(PROJECT_ROOT / "jobs", root / "jobs")
    shutil.copytree(PROJECT_ROOT / "templates", root / "templates")
    _write_openai_fixture_runtime(root)
    return root


def generated_text(paths: dict) -> str:
    chunks = []
    for value in paths.values():
        if not isinstance(value, (str, Path)):
            continue
        path = Path(str(value))
        if path.is_file() and path.suffix in {".md", ".txt"}:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        elif path.is_file() and path.suffix == ".docx":
            chunks.append("\n".join(paragraph.text for paragraph in Document(path).paragraphs))
    return "\n".join(chunks)


def test_openai_package_qa_normalizes_all_candidate_facing_text(tmp_path, monkeypatch):
    root = isolated_runtime(tmp_path)
    monkeypatch.chdir(root)
    source_before = (root / "data" / "evidence_projects.yml").read_text(encoding="utf-8")
    tracker = load_application_tracker(root)
    context = build_package_context("openai_program_manager_lead", tracker, root)
    score_before = context["match_report"]["match_score"]
    confirm_tracker_role_family("openai_program_manager_lead", root)
    outputs = generate_package(
        "openai_program_manager_lead",
        root,
        generate_followups_too=False,
        export_root=root / "qa_exports",
    )
    assert "—" not in generated_text(outputs)
    tracker_after = {
        record["id"]: record for record in load_application_tracker(root)
    }
    assert tracker_after["openai_program_manager_lead"]["match_score"] == score_before
    assert len(context["associated_evidence_projects"]) == 4
    assert (root / "data" / "evidence_projects.yml").read_text(encoding="utf-8") == source_before


def test_resume_cover_letter_and_interview_prep_have_no_em_dashes(tmp_path, monkeypatch):
    root = isolated_runtime(tmp_path)
    monkeypatch.chdir(root)
    tracker = load_application_tracker(root)
    context = build_package_context("openai_program_manager_lead", tracker, root)
    job = Path(context["job_path"]).relative_to(root)
    resume = tailor_resume(
        "executive_operations",
        job,
        root,
        context["associated_evidence_projects"],
        context["role_intent"],
    )
    cover = generate_cover_letter(
        job,
        root,
        context["associated_evidence_projects"],
        context["role_intent"],
    )
    prep = generate_career_intelligence(job, root, context["role_intent"])
    for result in (resume, cover, prep):
        assert "—" not in Path(result["output_path"]).read_text(encoding="utf-8")


def test_package_summary_normalizes_evidence_titles(tmp_path):
    root = isolated_runtime(tmp_path)
    summary = save_package_summary(
        root,
        parse_job_description(root / "jobs" / "openai_program_manager_lead.md"),
        {"label": "Fresh", "posting_status": "Open", "posting_date": ""},
        {"overall_score": 91, "apply_recommendation": "Generate", "dimensions": {}},
        {"resume_tailoring_score": 91, "cover_letter_score": 91, "ats_keyword_match": 91, "voice_match": 91, "confidence_level": "High"},
        {"selected_evidence": [{"id": "x", "title": "Evidence — Title"}]},
    )
    assert "—" not in Path(summary["output_path"]).read_text(encoding="utf-8")
