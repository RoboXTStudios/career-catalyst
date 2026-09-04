from pathlib import Path
from unittest.mock import patch

import pytest

import yaml

import app
from scripts.prospect_intake import create_prospect
from scripts.package_generator import (
    _GenerationTransaction,
    PackageGenerationError,
    build_package_context,
    generate_package,
    preflight_package_generation,
)

DESCRIPTION = (
    "Lead programming strategy and analytics-informed content operations for a creator slate. "
    * 3
)


def _init_tracker(root: Path) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump({"applications": []}), encoding="utf-8"
    )


def test_streamlit_save_path_skips_match_scoring_and_dashboard(tmp_path):
    _init_tracker(tmp_path)
    with patch("scripts.prospect_intake.import_job_from_url") as import_url, patch(
        "scripts.prospect_intake.score_job_match"
    ) as score, patch("app.generate_dashboard") as dashboard:
        result = create_prospect(
            {
                "company": "Beast Industries",
                "job_title": "Head of Programming",
                "job_description": DESCRIPTION,
                "official_url": "https://www.mrbeastjobs.com/jobs/6119486004",
            },
            tmp_path,
            run_match_analysis=False,
        )
    assert result["tracker_id"] == "beast_industries_head_of_programming"
    import_url.assert_not_called()
    score.assert_not_called()
    dashboard.assert_not_called()


def test_explicit_import_still_fetches_when_required(tmp_path):
    _init_tracker(tmp_path)
    with patch(
        "scripts.prospect_intake.import_job_from_url",
        return_value={
            "company": "Beast Industries",
            "job_title": "Head of Programming",
            "job_description": DESCRIPTION,
        },
    ) as import_url, patch(
        "scripts.prospect_intake.score_job_match", return_value={"match_score": 80}
    ):
        create_prospect(
            {"official_url": "https://www.mrbeastjobs.com/jobs/6119486004"},
            tmp_path,
        )
    import_url.assert_called_once()


def test_material_preflight_blocks_conflict_before_expensive_generation(tmp_path):
    other_path = (
        tmp_path / "exports" / "active" / "in_progress" / "other_role" / "resume.txt"
    )
    other_path.parent.mkdir(parents=True)
    other_path.write_text("other role resume", encoding="utf-8")
    tracker = [
        {
            "id": "role-a",
            "company": "Netflix",
            "role": "Program Manager",
            "material_paths": {"Tailored Resume": str(other_path)},
        },
        {
            "id": "role-b",
            "company": "Beast Industries",
            "role": "Head of Programming",
            "material_paths": {"Tailored Resume": str(other_path)},
        },
    ]
    result = preflight_package_generation("role-b", tracker, tmp_path)
    assert result["status"] == "conflict"
    assert result["conflicts"][0]["material_type"] == "Tailored Resume"
    assert result["conflicts"][0]["conflicting_company"] == "Netflix"


def test_generate_package_preflight_stops_before_context_and_ai(tmp_path):
    tracker = [
        {"id": "role-b", "company": "Beast Industries", "role": "Head of Programming"}
    ]
    with patch(
        "scripts.package_generator.resolve_job_reference",
        return_value={"application": tracker[0]},
    ), patch(
        "scripts.package_generator.load_application_tracker", return_value=tracker
    ), patch(
        "scripts.package_generator.preflight_package_generation",
        return_value={
            "status": "conflict",
            "conflicts": [
                {
                    "material_type": "Tailored Resume",
                    "conflicting_company": "Netflix",
                    "conflicting_role": "Program Manager",
                }
            ],
        },
    ), patch(
        "scripts.package_generator.build_package_context"
    ) as build_context, patch(
        "scripts.package_generator.tailor_resume"
    ) as tailor:
        with pytest.raises(PackageGenerationError) as error:
            generate_package("role-b", tmp_path)
    assert "clean new draft" in str(error.value)
    build_context.assert_not_called()
    tailor.assert_not_called()
    assert error.value.details["recovery"] is True


def test_recovery_state_key_is_role_scoped():
    assert app._package_recovery_key("beast") != app._package_recovery_key("netflix")
    assert "beast" in app._package_recovery_key("beast")


def test_failed_generation_transaction_restores_valid_files_and_tracker(tmp_path):
    tracker = tmp_path / "data" / "application_tracker.yml"
    tracker.parent.mkdir()
    tracker.write_text("applications:\n- id: role-a\n", encoding="utf-8")
    valid = tmp_path / "exports" / "active" / "valid.docx"
    valid.parent.mkdir(parents=True)
    valid.write_bytes(b"valid package")

    transaction = _GenerationTransaction(tmp_path)
    valid.write_bytes(b"incomplete replacement")
    partial = tmp_path / "exports" / "active" / "partial.docx"
    partial.write_bytes(b"partial")
    tracker.write_text("applications:\n- id: corrupted\n", encoding="utf-8")
    transaction.rollback()

    assert valid.read_bytes() == b"valid package"
    assert not partial.exists()
    assert tracker.read_text(encoding="utf-8") == "applications:\n- id: role-a\n"


def test_banned_builder_phrase_is_rewritten_before_validation():
    from scripts.role_editing import rewrite_banned_voice_phrases

    text, rewrites = rewrite_banned_voice_phrases(
        "I bring a builder's mindset to operational transformation."
    )
    assert "builder's mindset" not in text.lower()
    assert rewrites[0]["phrase"] == "builder's mindset"


def test_package_context_prefers_canonical_pasted_job_description(tmp_path):
    _init_tracker(tmp_path)
    wrapped_job = tmp_path / "jobs" / "role.md"
    wrapped_job.parent.mkdir()
    wrapped_job.write_text(
        "# Head of Programming\n\nCompany: Beast Industries\n\n"
        "## Job Description\n\nWrapped local representation.",
        encoding="utf-8",
    )
    pasted = "Authoritative manually pasted description from a gated source. " * 3
    tracker = [
        {
            "id": "beast",
            "company": "Beast Industries",
            "role": "Head of Programming",
            "job_file": "jobs/role.md",
            "job_description": pasted,
        }
    ]
    with patch(
        "scripts.package_generator.get_effective_voice_profile",
        return_value={"profile_name": "default"},
    ) as intelligence, patch(
        "scripts.package_generator.score_job_match", return_value={"match_score": 90}
    ):
        context = build_package_context("beast", tracker, tmp_path)

    assert context["job_description"] == pasted
    assert intelligence.call_args.kwargs["job_description"] == pasted
