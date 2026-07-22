from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import app
from scripts.application_tracker import load_application_tracker, save_application_tracker
from scripts import job_importer
from scripts.job_importer import _extract_greenhouse_job
from scripts.materials_library import organize_package_outputs, standardized_material_filename
from scripts.parse_job import parse_job_description
from scripts.prospect_intake import create_prospect
from scripts.package_generator import (
    PackageGenerationError,
    generate_package,
    preflight_package_generation,
)
from scripts.role_context import is_google_youtube_role

DESCRIPTION = (
    "Lead programming strategy and analytics-informed content operations for a creator slate. "
    * 3
)
GREENHOUSE_URL = (
    "https://job-boards.greenhouse.io/mrbeastyoutube/jobs/6119486004"
)


class _Element:
    def __init__(self, root):
        self.root = root

    def button(self, label, key=None, **_kwargs):
        self.root.buttons.append((label, key))
        return key in self.root.clicks


class _Spinner:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _RecoveryStreamlit(_Element):
    def __init__(self, state, clicks=()):
        self.session_state = state
        self.clicks = set(clicks)
        self.buttons = []
        self.messages = []
        super().__init__(self)

    def columns(self, count):
        return [_Element(self) for _ in range(count)]

    def spinner(self, _message):
        return _Spinner()

    def warning(self, value):
        self.messages.append(("warning", value))

    def error(self, value):
        self.messages.append(("error", value))

    def success(self, value):
        self.messages.append(("success", value))

    def info(self, value):
        self.messages.append(("info", value))

    def caption(self, value):
        self.messages.append(("caption", value))


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


def test_live_empty_material_record_preflights_duplicate_posting_before_generation(tmp_path):
    old_material = tmp_path / "exports" / "active" / "in_progress" / "beast" / "resume.txt"
    old_material.parent.mkdir(parents=True)
    old_material.write_text("original Beast Industries material", encoding="utf-8")
    tracker = [
        {
            "id": "beast_industries_head_of_programming",
            "company": "Beast Industries",
            "role": "Head of Programming",
            "job_id": "6119486004",
            "material_paths": {"Tailored Resume": str(old_material)},
        },
        {
            "id": "mrbeastyoutube_head_of_programming",
            "company": "Mrbeastyoutube",
            "role": "Head of Programming",
            "external_job_id": "6119486004",
            "official_url": GREENHOUSE_URL,
            "material_paths": {},
            "package_manifest": {
                "prospect_id": "mrbeastyoutube_head_of_programming",
                "materials": {},
            },
        },
    ]

    result = preflight_package_generation(
        "mrbeastyoutube_head_of_programming", tracker, tmp_path
    )

    assert result["status"] == "conflict"
    conflict = result["conflicts"][0]
    assert conflict["reason"] == "duplicate tracker records identify the same posting"
    assert conflict["conflicting_prospect_id"] == "beast_industries_head_of_programming"
    assert conflict["conflicting_company"] == "Beast Industries"
    assert conflict["path"] == str(old_material)


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


def test_live_duplicate_preflight_uses_real_empty_manifest_path_and_skips_context(tmp_path):
    old_material = tmp_path / "old-material.txt"
    old_material.write_text("do not overwrite", encoding="utf-8")
    tracker = [
        {
            "id": "beast_industries_head_of_programming",
            "company": "Beast Industries",
            "role": "Head of Programming",
            "job_id": "6119486004",
            "material_paths": {"Tailored Resume": str(old_material)},
        },
        {
            "id": "mrbeastyoutube_head_of_programming",
            "company": "Mrbeastyoutube",
            "role": "Head of Programming",
            "job_id": "6119486004",
            "material_paths": {},
            "package_manifest": {
                "prospect_id": "mrbeastyoutube_head_of_programming",
                "materials": {},
            },
        },
    ]
    with patch(
        "scripts.package_generator.resolve_job_reference",
        return_value={"application": tracker[1]},
    ), patch(
        "scripts.package_generator.load_application_tracker", return_value=tracker
    ), patch(
        "scripts.package_generator.build_package_context"
    ) as build_context, patch(
        "scripts.package_generator.tailor_resume"
    ) as tailor:
        with pytest.raises(PackageGenerationError) as error:
            generate_package("mrbeastyoutube_head_of_programming", tmp_path)

    assert error.value.details["recovery"] is True
    assert error.value.details["conflicts"][0]["path"] == str(old_material)
    build_context.assert_not_called()
    tailor.assert_not_called()
    assert old_material.read_text(encoding="utf-8") == "do not overwrite"


def test_late_content_mismatch_is_preflighted_before_context_or_ai(tmp_path):
    job_path = tmp_path / "jobs" / "beast.md"
    job_path.parent.mkdir(parents=True)
    job_path.write_text(
        "# Head of Programming\n\nCompany: Mrbeastyoutube\n\n"
        "## Job Description\n\nLead original programming strategy, audience analytics, "
        "and creator partnerships for a multi-format content slate.\n",
        encoding="utf-8",
    )
    old_material = (
        tmp_path
        / "exports"
        / "active"
        / "in_progress"
        / "beast_industries_head_of_programming"
        / "resume.txt"
    )
    old_material.parent.mkdir(parents=True)
    old_material.write_text(
        "This Google opportunity focuses on YouTube product activation.",
        encoding="utf-8",
    )
    tracker = [
        {
            "id": "beast_industries_head_of_programming",
            "stable_slug": "beast_industries_head_of_programming",
            "company": "Beast Industries",
            "role": "Head of Programming",
            "job_file": str(job_path),
            "material_paths": {"Tailored Resume": str(old_material)},
        }
    ]

    preflight = preflight_package_generation(
        "beast_industries_head_of_programming", tracker, tmp_path
    )
    assert preflight["status"] == "conflict"
    conflict = next(
        item
        for item in preflight["conflicts"]
        if item["reason"]
        == "existing material content belongs to a different role context"
    )
    assert conflict["path"] == str(old_material)
    assert "youtube product activation" in conflict["violations"]

    with patch(
        "scripts.package_generator.resolve_job_reference",
        return_value={"application": tracker[0]},
    ), patch(
        "scripts.package_generator.load_application_tracker", return_value=tracker
    ), patch(
        "scripts.package_generator.build_package_context"
    ) as build_context, patch(
        "scripts.package_generator.tailor_resume"
    ) as tailor:
        with pytest.raises(PackageGenerationError) as error:
            generate_package("beast_industries_head_of_programming", tmp_path)

    assert error.value.details["recovery"] is True
    build_context.assert_not_called()
    tailor.assert_not_called()
    assert "YouTube product activation" in old_material.read_text(encoding="utf-8")


def test_recovery_state_key_is_role_scoped():
    assert app._package_recovery_key("beast") != app._package_recovery_key("netflix")
    assert "beast" in app._package_recovery_key("beast")


def test_recovery_view_is_one_click_and_persists_across_reruns(tmp_path):
    conflict_path = tmp_path / "original-resume.txt"
    conflict_path.write_text("original material", encoding="utf-8")
    tracker_id = "mrbeastyoutube_head_of_programming"
    key = app._package_recovery_key(tracker_id)
    state = {
        key: {
            "conflicts": [
                {
                    "material_type": "Tailored Resume",
                    "path": str(conflict_path),
                    "conflicting_company": "Beast Industries",
                    "conflicting_role": "Head of Programming",
                }
            ]
        }
    }
    view_key = app._package_recovery_action_key(tracker_id, "view")
    first = _RecoveryStreamlit(state, clicks={view_key})
    with patch.object(app, "open_local_path", return_value=(True, "Opened")) as opened:
        app._render_package_recovery(
            first,
            tracker_id,
            {"company": "Beast Industries", "role": "Head of Programming"},
        )
    opened.assert_called_once_with(conflict_path)
    assert state[key]["viewed_conflict_path"] == str(conflict_path)
    assert ("success", "Opened") in first.messages

    second = _RecoveryStreamlit(state)
    app._render_package_recovery(
        second,
        tracker_id,
        {"company": "Beast Industries", "role": "Head of Programming"},
    )
    assert ("caption", str(conflict_path)) in second.messages
    widget_keys = [widget_key for _label, widget_key in second.buttons]
    assert len(widget_keys) == len(set(widget_keys))


def test_clean_draft_action_preserves_conflicting_material_and_clears_only_role_state(
    tmp_path,
):
    conflict_path = tmp_path / "original-resume.txt"
    conflict_path.write_text("original material", encoding="utf-8")
    tracker_id = "mrbeastyoutube_head_of_programming"
    other_key = app._package_recovery_key("other-role")
    key = app._package_recovery_key(tracker_id)
    state = {
        key: {
            "conflicts": [
                {"material_type": "Tailored Resume", "path": str(conflict_path)}
            ]
        },
        other_key: {"conflicts": [{"material_type": "Cover Letter"}]},
        f"package_followups_{tracker_id}": False,
    }
    st = _RecoveryStreamlit(
        state,
        clicks={app._package_recovery_action_key(tracker_id, "clean")},
    )
    result = {
        "tracker_id": tracker_id,
        "job_title": "Head of Programming",
        "company": "Beast Industries",
        "outputs": {"resume_text": str(tmp_path / "new-resume.txt")},
    }
    with patch.object(app, "generate_package", return_value=result) as generate, patch.object(
        app, "_render_package_summary"
    ):
        app._render_package_recovery(
            st,
            tracker_id,
            {"company": "Beast Industries", "role": "Head of Programming"},
            override_closed=True,
        )

    generate.assert_called_once_with(
        tracker_id,
        app.PROJECT_ROOT,
        generate_followups_too=False,
        override_closed=True,
        force_clean_draft=True,
    )
    assert key not in state
    assert other_key in state
    assert conflict_path.read_text(encoding="utf-8") == "original material"


def test_force_clean_organization_preserves_existing_material_and_manifest(tmp_path):
    application = {
        "id": "beast_industries_head_of_programming",
        "company": "Beast Industries",
        "role": "Head of Programming",
        "status": "Drafted",
    }
    package_folder = (
        tmp_path
        / "exports"
        / "active"
        / "in_progress"
        / application["id"]
    )
    package_folder.mkdir(parents=True)
    old_name = standardized_material_filename(application, "resume", "txt")
    old_material = package_folder / old_name
    old_material.write_text("original Beast resume", encoding="utf-8")
    old_manifest = package_folder / "manifest.json"
    old_manifest.write_text('{"original": true}\n', encoding="utf-8")
    generated = tmp_path / "generated-resume.txt"
    generated.write_text("new clean Beast resume", encoding="utf-8")

    result = organize_package_outputs(
        tmp_path,
        application,
        {"resume_text": str(generated)},
        preserve_existing=True,
    )

    new_material = Path(result["outputs"]["resume_text"])
    assert new_material != old_material
    assert new_material.read_text(encoding="utf-8") == "new clean Beast resume"
    assert old_material.read_text(encoding="utf-8") == "original Beast resume"
    assert Path(result["manifest"]["manifest_path"]) != old_manifest
    assert old_manifest.read_text(encoding="utf-8") == '{"original": true}\n'


def test_cancel_clears_only_selected_prospect_recovery_state():
    tracker_id = "beast"
    key = app._package_recovery_key(tracker_id)
    other_key = app._package_recovery_key("netflix")
    state = {
        key: {"conflicts": [{"material_type": "Tailored Resume"}]},
        other_key: {"conflicts": [{"material_type": "Cover Letter"}]},
    }
    st = _RecoveryStreamlit(
        state,
        clicks={app._package_recovery_action_key(tracker_id, "cancel")},
    )

    app._render_package_recovery(
        st, tracker_id, {"company": "Beast Industries", "role": "Head of Programming"}
    )

    assert key not in state
    assert other_key in state


def test_greenhouse_beast_identity_is_canonical_and_does_not_duplicate_existing_record(
    tmp_path,
):
    _init_tracker(tmp_path)
    save_application_tracker(
        [
            {
                "id": "beast_industries_head_of_programming",
                "company": "Beast Industries",
                "role": "Head of Programming",
                "status": "Drafted",
                "priority": "Medium",
                "show_on_dashboard": True,
            }
        ],
        tmp_path,
    )
    payload = {
        "id": 6119486004,
        "title": "Head of Programming",
        "absolute_url": GREENHOUSE_URL,
        "location": {"name": "Los Angeles, CA"},
        "content": (
            "&lt;h2&gt;About the Role&lt;/h2&gt;&lt;p&gt;Beast Industries is hiring a Head "
            "of Programming to lead original programming strategy, creator partnerships, "
            "audience analytics, and multi-format content development.&lt;/p&gt;"
        ),
    }
    with patch.object(job_importer, "_fetch_json", return_value=payload):
        imported = _extract_greenhouse_job(GREENHOUSE_URL)

    assert imported["company"] == "Beast Industries"
    assert "<" not in imported["job_description"]
    assert "&lt;" not in imported["job_description"]
    # Intake applies the same shared alias map even when another caller supplies
    # the raw ATS board identity instead of the already-normalized import result.
    alias_input = dict(imported)
    alias_input["company"] = "Mrbeastyoutube"
    result = create_prospect(alias_input, tmp_path, run_match_analysis=False)
    records = load_application_tracker(tmp_path)
    assert result["tracker_id"] == "beast_industries_head_of_programming"
    assert len(records) == 1
    assert records[0]["company"] == "Beast Industries"
    assert "Mrbeastyoutube" in records[0]["company_aliases"]

    create_prospect(imported, tmp_path, run_match_analysis=False)
    records = load_application_tracker(tmp_path)
    assert len(records) == 1
    assert "Mrbeastyoutube" in records[0]["company_aliases"]


def test_beast_description_mentioning_youtube_does_not_select_google_materials():
    assert not is_google_youtube_role(
        {
            "company": "Beast Industries",
            "job_title": "Head of Programming",
            "raw_text": "Build creator-led programming beyond the company's origins on YouTube.",
            "keywords": ["youtube", "programming"],
        }
    )
    assert is_google_youtube_role(
        {
            "company": "Google",
            "job_title": "Strategy and Operations Lead",
            "raw_text": "Lead YouTube product activation.",
            "keywords": ["youtube"],
        }
    )


def test_stored_greenhouse_markup_is_stripped_before_analysis(tmp_path):
    job_path = tmp_path / "beast.md"
    job_path.write_text(
        "# Head of Programming\n\nCompany: Mrbeastyoutube\n\n"
        "## Job Description\n\n"
        "&amp;lt;h2&amp;gt;Overview&amp;lt;/h2&amp;gt;"
        "&amp;lt;p&amp;gt;Lead original programming strategy, creator partnerships, "
        "audience analytics, and multi-format content development for Beast Industries."
        "&amp;lt;/p&amp;gt;",
        encoding="utf-8",
    )

    parsed = parse_job_description(job_path)

    assert parsed["company"] == "Beast Industries"
    assert "Lead original programming strategy" in parsed["raw_text"]
    assert "<h2>" not in parsed["raw_text"]
    assert "&lt;" not in parsed["raw_text"]
    assert "&amp;lt;" not in parsed["raw_text"]
