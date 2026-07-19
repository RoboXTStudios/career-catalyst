from copy import deepcopy
import inspect

import app
import pytest

import scripts.generate_followups as followup_module
from scripts.application_tracker import validate_tracker_entries
from scripts.cli import build_parser
from scripts.package_generator import generate_package
from scripts.package_materials import MATERIAL_SPECS
from tests.test_sprint22_6_context_recovery import (
    _generation_context,
    _package_generation_patches,
)


FOLLOWUP_OUTPUT_KEYS = {
    "recruiter_followup",
    "hiring_manager_followup",
    "warm_contact_message",
    "referral_ask",
    "followup_strategy",
}


def test_generate_package_ui_has_no_followup_material_control():
    source = inspect.getsource(app._render_generate_package)

    assert "Generate follow-up materials after package generation" not in source
    assert "package_followups_" not in source
    assert "generate_followups_too" not in source


def test_initial_package_generation_never_invokes_followup_generator(
    monkeypatch, tmp_path
):
    context = _generation_context(tmp_path)
    followup_calls = []

    def unexpected_followup(*args, **kwargs):
        followup_calls.append((args, kwargs))
        return {"outputs": {"recruiter_followup": "unexpected.txt"}}

    monkeypatch.setattr(followup_module, "generate_followups", unexpected_followup)
    with _package_generation_patches(
        context,
        [{"output_path": "resume.md"}],
        lambda *_args, **_kwargs: context,
    ):
        result = generate_package("youtube-role", tmp_path)

    assert followup_calls == []
    assert FOLLOWUP_OUTPUT_KEYS.isdisjoint(result["outputs"])
    assert "followup_error" not in result
    assert not (tmp_path / "exports" / "followups").exists()


def test_followup_tab_and_cli_keep_dedicated_generation_options():
    source = inspect.getsource(app._render_followups)

    assert "Generate eligible follow-ups" in source
    assert "Generate Follow-Up" in source
    assert "generate_missing_followups(PROJECT_ROOT)" in source
    assert "generate_followups(tracker_id, PROJECT_ROOT)" in source
    assert build_parser().parse_args(["followups", "saved-role"]).tracker_id == "saved-role"
    assert build_parser().parse_args(["followups-all"]).command == "followups-all"


def test_existing_saved_package_with_followup_paths_remains_valid():
    record = {
        "id": "saved-role",
        "company": "Example Company",
        "role": "Director, Operations",
        "status": "Applied",
        "priority": "High",
        "show_on_dashboard": True,
        "material_paths": {
            "ATS Resume": "exports/active/saved-role/ats_resume.docx",
            "Recruiter Follow-Up": "exports/followups/saved_role_recruiter_followup.txt",
            "Follow-Up Strategy": "exports/followups/saved_role_followup_strategy.txt",
        },
        "package_manifest": {
            "prospect_id": "saved-role",
            "materials": {
                "Recruiter Follow-Up": "exports/followups/saved_role_recruiter_followup.txt"
            },
        },
    }
    original = deepcopy(record)

    report = validate_tracker_entries([record])

    assert report["errors"] == []
    assert record == original


def test_initial_package_keeps_application_options_but_excludes_followup_summaries():
    source = inspect.getsource(app._render_generate_package)
    material_types = {spec[0] for spec in MATERIAL_SPECS}
    material_groups = {spec[1] for spec in MATERIAL_SPECS}

    assert "public_transparency_requested" in source
    assert "override_closed" in source
    assert {
        "ATS Resume",
        "Styled Resume",
        "Tailored Resume",
        "Cover Letter",
        "Application Note",
        "Recruiter Message",
        "Hiring Manager Message",
        "Strategy Pack",
        "Interview Prep",
        "Package Summary",
    } <= material_types
    assert "Follow-up" not in material_groups
    assert FOLLOWUP_OUTPUT_KEYS.isdisjoint(
        key for spec in MATERIAL_SPECS for key in spec[2]
    )


def test_generate_package_cli_rejects_removed_followup_option():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["generate-package", "saved-role", "--followups"])
