from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import app
import pytest
import yaml

from scripts.application_tracker import add_prospect, load_application_tracker
from scripts.dynamic_role_intelligence import get_effective_voice_profile
from scripts.load_data import load_all_yaml
from scripts.package_context import (
    CONTEXT_MISMATCH_MESSAGE,
    PackageContextMismatchError,
    prospect_context_fingerprint,
    validate_material_context,
)
from scripts.package_generator import (
    PackageGenerationError,
    build_package_context,
    generate_package,
)
from scripts.parse_job import parse_job_description
from scripts.score_match import score_job_match
from scripts.tailor_resume import _render_markdown


DESCRIPTION = (
    "Lead strategy and operations across Product, Marketing, and Partnerships. Build "
    "planning rhythms, clarify ownership, prepare executive decisions, and improve "
    "cross-functional execution against the organization’s most important priorities."
)
YOUTUBE_JOB = {
    "company": "YouTube",
    "job_title": "Strategy and Operations Associate, YouTube Music and Premium",
    "raw_text": DESCRIPTION,
}


def _tracker_root(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    return tmp_path


def _session_state():
    return {
        "prospect_url_value": "https://www.google.com/about/careers/applications/jobs/results/123",
        "prospect_original_source_url": "https://www.google.com/about/careers/applications/jobs/results/123",
        "prospect_company": "YouTube",
        "prospect_role": "Strategy and Operations Associate, YouTube Music and Premium",
        "prospect_location": "US",
        "prospect_salary": "$124000 - $178000",
        "prospect_posting_date": "",
        "prospect_work_arrangement": "On-site",
        "prospect_description": DESCRIPTION,
        "last_package_outputs": {"cover_letter": "old.txt"},
        "last_package_result": {"tracker_id": "old-role"},
        "package_preview_prospect_id": "old-role",
    }


def _score(_values, _root):
    return {
        "match_score": 89,
        "match_tier": "Strong Match",
        "recommended_action": "Generate Package",
        "match_summary": "Current role aligned.",
        "match_reasons": ["Strategy and operations"],
        "match_gaps": [],
    }


def test_material_description_update_advances_revision_and_drops_derived_context(tmp_path):
    root = _tracker_root(tmp_path)
    first = add_prospect(
        {
            "id": "youtube-role",
            "company": "YouTube",
            "role": "Strategy and Operations Associate",
            "status": "Drafted",
            "priority": "High",
            "show_on_dashboard": True,
            "context_fingerprint": "a" * 64,
            "material_paths": {"Cover Letter": "old.txt"},
            "package_manifest": {
                "prospect_id": "youtube-role",
                "prospect_revision": 1,
                "context_fingerprint": "a" * 64,
                "materials": {"Cover Letter": "old.txt"},
            },
        },
        root,
    )["application"]
    second = add_prospect(
        {
            "id": "youtube-role",
            "company": "YouTube",
            "role": "Strategy and Operations Associate",
            "context_fingerprint": "b" * 64,
        },
        root,
    )["application"]

    assert first["prospect_revision"] == 1
    assert second["prospect_revision"] == 2
    assert second["context_fingerprint"] == "b" * 64
    assert "package_manifest" not in second
    assert "material_paths" not in second


def test_first_revision_binding_discards_unversioned_legacy_materials(tmp_path):
    root = _tracker_root(tmp_path)
    add_prospect(
        {
            "id": "legacy-role",
            "company": "Netflix",
            "role": "Program Manager, Design",
            "status": "Drafted",
            "priority": "Medium",
            "show_on_dashboard": True,
            "material_paths": {"Cover Letter": "unversioned.txt"},
            "package_manifest": {
                "prospect_id": "legacy-role",
                "materials": {"Cover Letter": "unversioned.txt"},
            },
        },
        root,
    )
    updated = add_prospect(
        {
            "id": "legacy-role",
            "company": "Netflix",
            "role": "Program Manager, Design",
            "context_fingerprint": "d" * 64,
        },
        root,
    )["application"]

    assert updated["prospect_revision"] == 1
    assert "material_paths" not in updated
    assert "package_manifest" not in updated


def test_manual_reparse_and_rescore_invalidate_session_package_context(monkeypatch):
    monkeypatch.setattr(app, "score_job_data", _score)
    state = _session_state()

    first = app.apply_manual_reparse_state(state)
    assert first["match_report"]["match_score"] == 89
    assert "last_package_outputs" not in state
    assert "last_package_result" not in state

    state["last_package_outputs"] = {"cover_letter": "new-old.txt"}
    state["prospect_description"] += " The updated analysis emphasizes partner strategy."
    second = app.apply_manual_reparse_state(state)
    assert second["match_report"]["match_score"] == 89
    assert "last_package_outputs" not in state


def test_analysis_score_change_changes_saved_context_fingerprint():
    values = {
        "prospect_id": "youtube-role",
        "company": "YouTube",
        "job_title": "Strategy and Operations Associate",
        "job_description": DESCRIPTION,
    }
    intelligence = {
        "role_family": "business_operations",
        "selected_evidence_ids": ["governance_qa_delivery"],
    }

    first = prospect_context_fingerprint(
        values, {**intelligence, "match_report": {"match_score": 78, "match_tier": "Good Match"}}
    )
    second = prospect_context_fingerprint(
        values, {**intelligence, "match_report": {"match_score": 89, "match_tier": "Strong Match"}}
    )
    changed_analysis = prospect_context_fingerprint(
        values,
        {
            **intelligence,
            "match_report": {
                "match_score": 89,
                "match_tier": "Strong Match",
                "match_strengths": ["New partner strategy emphasis"],
            },
        },
    )

    assert first != second
    assert second != changed_analysis


def test_persist_and_generate_uses_saved_id_in_authoritative_order(tmp_path):
    events = []
    state = {}

    def creator(payload, root):
        events.append(("persist", payload["company"], root))
        return {"tracker_id": "youtube-role", "application": {"prospect_revision": 3}}

    def generator(tracker_id, root):
        events.append(("generate", tracker_id, root))
        assert state["last_saved_prospect_id"] == tracker_id
        return {"tracker_id": tracker_id, "outputs": {}, "prospect_revision": 3}

    result = app.persist_and_generate_prospect(
        {
            "company": "YouTube",
            "job_title": "Strategy and Operations Associate",
            "job_description": DESCRIPTION,
        },
        state,
        tmp_path,
        creator=creator,
        generator=generator,
    )

    assert [event[0] for event in events] == ["persist", "generate"]
    assert result["package"]["prospect_revision"] == 3


def test_build_context_uses_latest_saved_revision_and_fingerprint(tmp_path):
    root = _tracker_root(tmp_path)
    (root / "jobs").mkdir()
    job = root / "jobs" / "youtube.md"
    job.write_text(
        "# Strategy and Operations Associate\n\nCompany: YouTube\n\n"
        "## Job Description\n\n" + DESCRIPTION,
        encoding="utf-8",
    )
    intelligence = {
        "company_category": "product_technology",
        "role_family": "business_operations",
        "selected_evidence_ids": ["governance_qa_delivery"],
        "proof_points_to_emphasize": ["Introduced scalable workflows and governance."],
    }
    fingerprint = prospect_context_fingerprint(
        {
            "prospect_id": "youtube-role",
            "company": "YouTube",
            "job_title": "Strategy and Operations Associate",
            "raw_text": job.read_text(encoding="utf-8"),
        },
        {**intelligence, "match_report": {"match_score": 90}},
    )
    add_prospect(
        {
            "id": "youtube-role",
            "company": "YouTube",
            "role": "Strategy and Operations Associate",
            "status": "Drafted",
            "priority": "High",
            "show_on_dashboard": True,
            "job_file": "jobs/youtube.md",
            "context_fingerprint": "a" * 64,
        },
        root,
    )
    add_prospect(
        {
            "id": "youtube-role",
            "company": "YouTube",
            "role": "Strategy and Operations Associate",
            "job_file": "jobs/youtube.md",
            "context_fingerprint": fingerprint,
            "package_manifest": {
                "prospect_id": "youtube-role",
                "prospect_revision": 2,
                "context_fingerprint": fingerprint,
                "materials": {},
            },
        },
        root,
    )

    with patch(
        "scripts.package_generator.get_effective_voice_profile",
        return_value=intelligence,
    ), patch(
        "scripts.package_generator.score_job_match", return_value={"match_score": 90}
    ):
        context = build_package_context(
            "youtube-role", load_application_tracker(root), root
        )

    assert context["prospect_revision"] == 2
    assert context["context_fingerprint"] == fingerprint
    assert context["context_stale"] is False


def test_current_youtube_terms_are_authorized_for_youtube_role():
    result = validate_material_context(
        (
            "This Google opportunity connects YouTube product activation, GTM operations, "
            "seller enablement, Google platform capabilities, and advertiser execution."
        ),
        YOUTUBE_JOB,
    )

    assert result["valid"] is True
    assert result["mismatch_status"] == "current_role_overlap"


def test_manifest_tied_to_another_prospect_id_is_confirmed_and_blocked(tmp_path):
    root = _tracker_root(tmp_path)
    (root / "jobs").mkdir()
    (root / "jobs" / "youtube.md").write_text(
        "# Strategy and Operations Associate\n\nCompany: YouTube\n\n"
        "## Job Description\n\n" + DESCRIPTION,
        encoding="utf-8",
    )
    add_prospect(
        {
            "id": "youtube-role",
            "company": "YouTube",
            "role": "Strategy and Operations Associate",
            "status": "Drafted",
            "priority": "High",
            "show_on_dashboard": True,
            "job_file": "jobs/youtube.md",
            "package_manifest": {"prospect_id": "netflix-role", "materials": {}},
        },
        root,
    )

    with pytest.raises(PackageGenerationError) as captured:
        build_package_context("youtube-role", load_application_tracker(root), root)

    assert str(captured.value) == CONTEXT_MISMATCH_MESSAGE
    assert captured.value.details["mismatch_status"] == "confirmed"
    assert captured.value.details["mismatch_reason"] == "manifest_prospect_id_conflict"


@pytest.mark.parametrize(
    ("parsed_job", "content", "indicator"),
    (
        (
            {"company": "Netflix", "job_title": "Program Manager, Design", "raw_text": "Lead design programs and creative workflows."},
            "This Google opportunity centers on YouTube product activation and seller enablement.",
            "youtube product activation",
        ),
        (
            {"company": "United Talent Agency", "job_title": "Director, Transformation", "raw_text": "Lead operating-model transformation and stakeholder alignment."},
            "This Paramount opportunity focuses on streaming franchise strategy and execution.",
            "paramount opportunity",
        ),
    ),
)
def test_confirmed_cross_role_material_remains_blocked(parsed_job, content, indicator):
    with pytest.raises(PackageContextMismatchError) as captured:
        validate_material_context(content, parsed_job)

    assert indicator in captured.value.violations
    assert captured.value.diagnostics["mismatch_status"] == "confirmed"


def _generation_context(tmp_path):
    job = tmp_path / "youtube.md"
    job.write_text("# Role\n\n" + DESCRIPTION, encoding="utf-8")
    application = {
        "id": "youtube-role",
        "company": "YouTube",
        "role": "Strategy and Operations Associate",
        "status": "Reviewed",
    }
    return {
        "prospect_id": "youtube-role",
        "slug": "youtube-role",
        "application": application,
        "job_path": job,
        "job_reference": str(job),
        "parsed_job": YOUTUBE_JOB,
        "company": "YouTube",
        "raw_company": "YouTube",
        "role_title": YOUTUBE_JOB["job_title"],
        "source_url": "https://careers.google.com/jobs/123",
        "job_description": DESCRIPTION,
        "role_intelligence": {
            "company_category": "product_technology",
            "role_family": "business_operations",
            "profile_name": "google_youtube",
            "source": "known_profile",
            "selected_evidence_ids": ["governance_qa_delivery", "omg23_disney_leadership"],
        },
        "match_report": {"match_score": 90},
        "selected_package_paths": {},
        "context_fingerprint": "c" * 64,
        "prospect_revision": 4,
        "context_stale": False,
        "context_diagnostics": {"prior_context_source": "none"},
    }


def _package_generation_patches(context, tailor_side_effect, refresh):
    material = {"output_path": "material.md"}
    freshness = {
        "is_closed": False,
        "category": "Fresh",
        "label": "Fresh",
        "posting_status": "Open",
        "posting_date": None,
        "age_days": None,
    }
    opportunity = {"overall_score": 90, "apply_recommendation": "Apply", "dimensions": {}}
    quality = {"resume_tailoring_score": 90}
    stack = ExitStack()
    stack.enter_context(patch("scripts.package_generator.resolve_job_reference", return_value={"application": context["application"]}))
    stack.enter_context(patch("scripts.package_generator.load_application_tracker", return_value=[context["application"]]))
    stack.enter_context(patch("scripts.package_generator.build_package_context", return_value=context))
    stack.enter_context(patch("scripts.package_generator.refresh_saved_package_context", side_effect=refresh))
    stack.enter_context(patch("scripts.package_generator.detect_job_freshness", return_value=freshness))
    stack.enter_context(patch("scripts.package_generator.update_prospect", side_effect=lambda _id, _updates, _root: context["application"]))
    stack.enter_context(patch("scripts.package_generator.score_opportunity", return_value=opportunity))
    stack.enter_context(patch("scripts.package_generator.tailor_resume", side_effect=tailor_side_effect))
    stack.enter_context(patch("scripts.package_generator.export_styled_docx", return_value=material))
    stack.enter_context(patch("scripts.package_generator.export_ats_docx", return_value=material))
    stack.enter_context(patch("scripts.package_generator.generate_cover_letter", return_value=material))
    stack.enter_context(patch("scripts.package_generator.generate_message", return_value=material))
    stack.enter_context(patch("scripts.package_generator.generate_application_note", return_value=material))
    stack.enter_context(patch("scripts.package_generator.generate_strategy_pack", return_value=material))
    stack.enter_context(patch("scripts.package_generator.generate_interview_prep", return_value=material))
    stack.enter_context(patch("scripts.package_generator.calculate_package_quality", return_value=quality))
    stack.enter_context(patch("scripts.package_generator.save_package_summary", return_value=material))
    stack.enter_context(patch("scripts.package_generator.create_text_companion", return_value=None))
    stack.enter_context(patch("scripts.package_generator.organize_package_outputs", side_effect=lambda _root, _app, outputs: {"outputs": outputs, "manifest": None}))
    stack.enter_context(patch("scripts.package_generator.validate_package_outputs", return_value=[]))
    stack.enter_context(patch("scripts.package_generator.preferred_material_paths", return_value={}))
    stack.enter_context(patch("scripts.package_generator.generate_dashboard", return_value={}))
    return stack


def test_automatic_refresh_recovers_once_from_stale_derived_context(tmp_path):
    context = _generation_context(tmp_path)
    mismatch = PackageContextMismatchError(["youtube product activation"], "Tailored_Resume")
    refresh_calls = []

    def refresh(*_args, **_kwargs):
        refresh_calls.append("refresh")
        return context

    with _package_generation_patches(context, [mismatch, {"output_path": "resume.md"}], refresh):
        result = generate_package("youtube-role", tmp_path)

    assert refresh_calls == ["refresh"]
    assert result["context_recovery"]["automatic_refresh_attempted"] is True
    assert result["context_recovery"]["refreshed_validation_passed"] is True


def test_confirmed_mismatch_retries_no_more_than_once_and_stays_blocked(tmp_path):
    context = _generation_context(tmp_path)
    mismatch = PackageContextMismatchError(["paramount opportunity"], "Cover_Letter")
    refresh_calls = []

    def refresh(*_args, **_kwargs):
        refresh_calls.append("refresh")
        return context

    with _package_generation_patches(context, mismatch, refresh):
        with pytest.raises(PackageGenerationError) as captured:
            generate_package("youtube-role", tmp_path)

    assert refresh_calls == ["refresh"]
    assert str(captured.value) == CONTEXT_MISMATCH_MESSAGE
    assert captured.value.details["automatic_refresh_attempted"] is True
    assert captured.value.details["refreshed_validation_passed"] is False


def test_recovery_action_refreshes_then_retries_once(tmp_path):
    events = []
    state = {"last_package_outputs": {"old": "path"}}

    def creator(payload, root):
        events.append(("persist", payload["company"], root))
        return {"tracker_id": "youtube-role"}

    def refresher(tracker_id, root):
        events.append(("refresh", tracker_id, root))
        return {"prospect_revision": 5}

    def generator(tracker_id, root, **options):
        events.append(("generate", tracker_id, root, options))
        return {"tracker_id": tracker_id, "outputs": {}}

    result = app.refresh_role_context_and_retry(
        state,
        "youtube-role",
        tmp_path,
        prospect_values={
            "company": "YouTube",
            "job_title": "Strategy and Operations Associate",
            "job_description": DESCRIPTION,
        },
        creator=creator,
        refresher=refresher,
        generator=generator,
    )

    assert [event[0] for event in events] == ["persist", "refresh", "generate"]
    assert events[2][3]["_context_refresh_attempted"] is True
    assert result["context_recovery"]["prospect_revision"] == 5
    assert "last_package_outputs" not in state
    assert "Refresh Role Context & Try Again" in app._render_context_recovery_action.__code__.co_consts


def test_rebuilt_youtube_context_keeps_professional_evidence_and_voice():
    intelligence = get_effective_voice_profile(
        company_name="YouTube",
        job_title="Strategy and Operations Associate, YouTube Music and Premium",
        job_description=(
            DESCRIPTION
            + " Lead GTM operations, seller enablement, platform activation, and "
            "large advertiser execution."
        ),
    )
    rendered = " ".join(
        [
            *intelligence.get("selected_evidence_ids", []),
            *intelligence.get("proof_points_to_emphasize", []),
        ]
    ).lower()

    assert intelligence["profile_name"] == "google_youtube"
    assert {"governance_qa_delivery", "omg23_disney_leadership"}.issubset(
        set(intelligence["selected_evidence_ids"])
    )
    for term in ("career catalyst", "campaignos", "substack"):
        assert term not in rendered


def test_context_rebuild_preserves_plain_ats_resume_and_current_voice():
    root = Path(__file__).resolve().parents[1]
    job_reference = "jobs/google_strategy_ops_lead_youtube_auction_brand.md"
    parsed = parse_job_description(root / job_reference)
    match = score_job_match(job_reference, root)
    resume = _render_markdown(
        load_all_yaml(root), parsed, match, "executive_operations"
    )

    assert "## Profile" in resume
    assert "## Core Competencies" in resume
    assert "## Professional Experience" in resume
    assert "| ---" not in resume
    assert "AI Workflow Design" in resume
    assert "Google and YouTube platform capabilities" in resume
