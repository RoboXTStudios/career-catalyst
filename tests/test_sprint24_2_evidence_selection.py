from copy import deepcopy
from pathlib import Path

import app
from scripts import ui_performance
from scripts.application_tracker import migrate_application_evidence_selections
from scripts.evidence_summary import (
    build_evidence_page_summary,
    load_evidence_page_summary,
    save_evidence_page_summary,
)
from scripts.generate_cover_letter import load_generation_context
from scripts.role_evidence_selection import (
    build_role_evidence_selection,
    normalize_selection_overrides,
    update_selection_overrides,
)
from scripts.score_match import score_job_match


ROOT = Path(__file__).resolve().parents[1]
REDDIT_JOB = "tests/fixtures/jobs/reddit_manager_technical_solutions.md"


def test_new_role_gets_concise_automatic_selection_without_manual_input():
    selection = score_job_match(REDDIT_JOB, ROOT)["role_evidence_selection"]

    assert selection["automatic_by_default"] is True
    assert 3 <= len(selection["primary_evidence"]) <= 5
    assert len(selection["supporting_evidence"]) <= 3
    assert len(selection["selected_evidence_ids"]) <= 8
    assert selection["automatic_selection"]["selected_evidence_ids"]
    assert selection["manual_additions"] == []
    assert selection["manual_exclusions"] == []


def test_package_context_automatically_supplies_final_evidence_set():
    context = load_generation_context(REDDIT_JOB, ROOT, {})

    assert context["role_evidence_selection"]["selected_evidence_ids"]
    assert [item["id"] for item in context["selected_evidence_cards"]] == context[
        "role_evidence_selection"
    ]["selected_evidence_ids"]


def test_strongest_relevant_items_win_and_unrelated_items_are_excluded():
    selection = score_job_match(REDDIT_JOB, ROOT)["role_evidence_selection"]
    selected = selection["selected_evidence_ids"]
    excluded = {item["id"] for item in selection["excluded_evidence"]}

    assert selected[0] == "technical_troubleshooting"
    assert {"cm360", "dv360"}.issubset(selected)
    assert "career_catalyst_ai_product" not in selected
    assert "career_catalyst_ai_product" in excluded


def test_redundant_automatic_evidence_is_reduced():
    def item(evidence_id, title, description):
        return {
            "id": evidence_id,
            "title": title,
            "description": description,
            "category": "Workflow Design",
            "skills": ["workflow design", "operations"],
            "tags": ["workflow"],
            "confidence": "High",
            "verification_status": "Verified",
            "evidence_type": "Direct Experience",
            "recommended_usage": {"match_scoring": True},
            "related_projects": ["Shared Program"],
        }

    profile = {
        "evidence": [
            item("strong", "Workflow redesign", "Led enterprise workflow design and operating standards."),
            item("duplicate", "Workflow redesign duplicate", "Led enterprise workflow design and operating standards."),
            item("distinct", "Executive governance", "Owned executive governance, decisions, and portfolio risk."),
        ]
    }
    selection = build_role_evidence_selection(
        {
            "job_title": "Director, Workflow Operations",
            "raw_text": "Lead enterprise workflow design, operating standards, executive governance, decisions, and portfolio risk.",
        },
        profile,
        usage="match_scoring",
    )

    assert not {"strong", "duplicate"}.issubset(selection["selected_evidence_ids"])


def test_manual_additions_exclusions_and_priority_are_independent_and_persist():
    overrides = update_selection_overrides({}, "technical_troubleshooting", "exclude")
    overrides = update_selection_overrides(overrides, "people_leadership", "make_primary")
    normalized = normalize_selection_overrides(overrides)

    assert normalized["manual_exclusions"] == ["technical_troubleshooting"]
    assert normalized["manual_additions"] == ["people_leadership"]
    assert normalized["manual_priority_overrides"] == {"people_leadership": "Primary"}
    assert normalize_selection_overrides(deepcopy(normalized)) == normalized


def test_reset_restores_automatic_selection():
    overrides = update_selection_overrides({}, "technical_troubleshooting", "exclude")
    reset = update_selection_overrides(overrides, "", "reset")
    selection = score_job_match(
        REDDIT_JOB, ROOT, evidence_selection_overrides=reset
    )["role_evidence_selection"]

    assert reset["user_reviewed"] is False
    assert "technical_troubleshooting" in selection["selected_evidence_ids"]


def test_legacy_manual_choices_migrate_without_rebuilding_or_deleting_data():
    original_selection = {
        "primary_evidence": [
            {"id": "evidence_1", "selected_by": "User override"}
        ],
        "supporting_evidence": [
            {"id": "automatic", "selected_by": "Automatic selection"}
        ],
        "excluded_evidence": [
            {"id": "evidence_2", "excluded_by": "User override"}
        ],
    }
    applications = [
        {
            "id": "prospect",
            "role_evidence_selection": deepcopy(original_selection),
            "capability_data": {"preserve": True},
        }
    ]

    assert migrate_application_evidence_selections(applications) == 1
    assert applications[0]["role_evidence_selection"] == original_selection
    assert applications[0]["capability_data"] == {"preserve": True}
    assert applications[0]["evidence_selection_overrides"]["manual_additions"] == [
        "evidence_1"
    ]
    assert applications[0]["evidence_selection_overrides"]["manual_exclusions"] == [
        "evidence_2"
    ]


def test_initial_evidence_summary_read_does_not_load_profile_or_graph(monkeypatch, tmp_path):
    expected = build_evidence_page_summary(
        {"evidence": [], "discoveries": []}, {"capabilities": []}
    )
    save_evidence_page_summary(expected, tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("full evidence data was hydrated")

    monkeypatch.setattr(ui_performance, "load_evidence_profile", forbidden)
    monkeypatch.setattr(ui_performance, "load_capability_graph", forbidden)
    ui_performance.invalidate_evidence_caches()

    loaded = ui_performance.load_cached_evidence_page_summary(tmp_path)
    assert loaded["profile_summary"] == expected["profile_summary"]
    assert loaded["needs_review"] == expected["needs_review"]


def test_full_library_code_is_behind_explicit_action_and_summary_navigation_has_no_model_call():
    source = Path(app.__file__).read_text(encoding="utf-8")
    summary_start = source.index("def _render_evidence_explorer")
    summary_source = source[summary_start : source.index("\n\nUI_PAGES", summary_start)]

    assert '"Open Full Evidence Library"' in summary_source
    assert "_render_full_evidence_library(st)" in summary_source
    assert summary_source.index("if st.session_state.get(open_key, False):") < summary_source.index(
        "_render_full_evidence_library(st)"
    )
    assert "get_effective_voice_profile" not in summary_source
    assert "score_job_match" not in summary_source
    assert "load_cached_capability_graph" not in summary_source
