from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import app
from scripts.candidate_output import validate_candidate_output
from scripts.evidence_tailoring import (
    evidence_relevance,
    evidence_score_contribution,
    output_use_metadata,
    package_preview_fingerprint,
    project_title,
    relevant_selected_evidence,
    resume_project_bullets,
)
from scripts.export_docx import export_ats_docx, export_styled_docx
from scripts.generate_cover_letter import _word_count, generate_cover_letter
from scripts.parse_job import parse_job_description
from scripts.role_intent import (
    build_role_intent,
    reconcile_package_role_intelligence,
    tailoring_plan,
)
from scripts.score_match import score_job_match
from scripts.tailor_resume import tailor_resume


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NETFLIX = Path("tests/fixtures/jobs/netflix_product_manager_emerging_formats_sanitized.md")
DISNEY = Path("tests/fixtures/jobs/disney_principal_product_manager_sanitized.md")
GITLAB = Path("tests/fixtures/jobs/gitlab_director_customer_experience_strategy.md")
FOUNDATION_FILES = (
    "data/achievements.yml",
    "data/positions.yml",
    "data/skills.yml",
    "data/platforms.yml",
    "data/projects.yml",
    "data/evidence_projects.yml",
    "data/certifications.yml",
    "data/personal_brand.yml",
    "config/settings.yml",
    "config/target_companies.yml",
    "config/role_profiles.yml",
    "config/voice.yml",
    "config/company_voice_profiles.yml",
    "config/evidence_cards.yml",
    "config/writing_voice_profiles.yml",
    "config/role_editing_rules.yml",
    "config/role_intent_rules.yml",
)


CAREER_CATALYST = {
    "id": "career_catalyst_codex_delivery",
    "title": "Career Catalyst — AI-Enabled Career Intelligence & Application Operations Platform",
    "status": "Active",
    "external_use": True,
    "project_type": "Active Product Development",
    "actions": (
        "Created and led active AI-enabled product development, defining product vision, "
        "requirements, feature priorities, workflows, acceptance criteria, iterative tests, "
        "and release guardrails."
    ),
    "results": (
        "Built a tested local application integrating prospect evaluation, evidence selection, "
        "tailored materials, follow-up planning, interview preparation, and role archiving."
    ),
    "tags": ["Product Strategy", "Requirements", "Workflow Design", "Quality Assurance"],
}

PODCAST = {
    "id": "just_for_us_podcast_audio_production_editing",
    "title": "Just for Us Podcast — Audio Production & Editing",
    "status": "Active",
    "external_use": True,
    "project_type": "Podcast Production",
    "actions": (
        "Served as audio producer and editor for a ten-episode, multi-host podcast series, "
        "managing dialogue editing, pacing, audio balancing, revisions, QA, and release preparation."
    ),
    "results": "Prepared and released the ten-episode series on Spotify.",
    "tags": ["Podcast", "Audio Editing", "Quality Control", "Content Production"],
}

IRRELEVANT = {
    "id": "unrelated_finance_project",
    "title": "Household Finance Filing",
    "status": "Active",
    "external_use": True,
    "actions": "Organized household receipts by tax year.",
    "results": "Completed a private annual filing checklist.",
}


def _isolated_root(tmp_path: Path, fixture: Path = NETFLIX) -> tuple[Path, Path]:
    root = tmp_path / fixture.stem
    for relative in FOUNDATION_FILES:
        source = PROJECT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    job = root / "jobs" / fixture.name
    job.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / fixture, job)
    return root, job.relative_to(root)


def _netflix_intent(root: Path, job: Path) -> tuple[dict, dict]:
    parsed = parse_job_description(root / job)
    intent = build_role_intent({**parsed, "role_family": "product_strategy_ops"}, root)
    intent["manual_evidence_projects"] = [CAREER_CATALYST, PODCAST]
    return parsed, intent


def test_tailoring_plan_separates_manual_evidence_from_recommendations(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    _parsed, intent = _netflix_intent(root, job)
    plan = tailoring_plan(intent)
    assert plan["selected_relevant_evidence"] == [
        CAREER_CATALYST["title"],
        PODCAST["title"],
    ]
    assert plan["system_recommended_projects"] == ["Career Catalyst", "CampaignOS"]
    assert "None" not in plan["selected_relevant_evidence"]
    assert not any("unrelated" in value.lower() for value in plan["de_emphasizing"])


def test_tailoring_plan_has_graceful_manual_evidence_fallback(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    intent = build_role_intent(parse_job_description(root / job), root)
    assert tailoring_plan(intent)["selected_relevant_evidence"] == []


def test_streamlit_tailoring_plan_does_not_render_obsolete_selected_projects_none(
    tmp_path: Path,
):
    root, job = _isolated_root(tmp_path)
    _parsed, intent = _netflix_intent(root, job)

    class FakeStreamlit:
        def __init__(self):
            self.rendered: list[str] = []

        def container(self, **_kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def markdown(self, value):
            self.rendered.append(str(value))

        def caption(self, value):
            self.rendered.append(str(value))

    fake = FakeStreamlit()
    app._render_tailoring_plan(fake, intent)
    rendered = "\n".join(fake.rendered)
    assert "Selected Relevant Evidence" in rendered
    assert CAREER_CATALYST["title"] in rendered and PODCAST["title"] in rendered
    assert "Selected projects: None" not in rendered


def test_output_use_metadata_reports_resume_cover_and_not_used(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    parsed = parse_job_description(root / job)
    metadata = output_use_metadata(
        [CAREER_CATALYST, PODCAST, IRRELEVANT],
        system_recommended_projects=["Career Catalyst", "CampaignOS"],
        resume_projects_used=[CAREER_CATALYST["title"], PODCAST["title"]],
        cover_letter_projects_used=[CAREER_CATALYST["title"], PODCAST["title"]],
        score_contribution={"before": 70, "after": 73, "delta": 3},
        parsed_job=parsed,
    )
    assert metadata["resume_projects_used"] == metadata["cover_letter_projects_used"]
    assert [item["title"] for item in metadata["projects_not_used"]] == [IRRELEVANT["title"]]


def test_evidence_selection_fingerprint_invalidates_only_stale_preview():
    state: dict = {}
    assert app.reset_package_preview_for_selection(state, "netflix", [CAREER_CATALYST["id"]])
    state["last_package_result"] = {"tracker_id": "netflix"}
    state["last_package_outputs"] = {"resume": "/already/generated.docx"}
    assert not app.reset_package_preview_for_selection(state, "netflix", [CAREER_CATALYST["id"]])
    assert app.reset_package_preview_for_selection(
        state, "netflix", [CAREER_CATALYST["id"], PODCAST["id"]]
    )
    assert "last_package_result" not in state and "last_package_outputs" not in state
    assert state["package_preview_selection_fingerprint"] == package_preview_fingerprint(
        "netflix", [CAREER_CATALYST["id"], PODCAST["id"]]
    )


def test_save_relevant_evidence_recomputes_score_without_touching_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    protected = tmp_path / "existing-package.docx"
    protected.write_bytes(b"existing package")
    before = protected.read_bytes()
    updates: list[dict] = []

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "package_preview_prospect_id": "netflix",
                "package_preview_selection_fingerprint": package_preview_fingerprint(
                    "netflix", [CAREER_CATALYST["id"]]
                ),
                "last_package_outputs": {"resume": str(protected)},
            }

        def multiselect(self, *_args, **_kwargs):
            return [CAREER_CATALYST["id"], PODCAST["id"]]

        def caption(self, *_args, **_kwargs):
            return None

        def button(self, *_args, **_kwargs):
            return True

        def rerun(self):
            return None

    fake = FakeStreamlit()
    monkeypatch.setattr(app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(app, "load_evidence_projects", lambda _root: [CAREER_CATALYST, PODCAST])
    monkeypatch.setattr(
        app,
        "resolve_job_reference",
        lambda *_args: {"job_path": tmp_path / "job.md"},
    )
    monkeypatch.setattr(
        app,
        "score_job_match",
        lambda *_args: {"match_score": 81, "match_tier": "Strong Match"},
    )
    monkeypatch.setattr(
        app,
        "update_prospect",
        lambda _tracker_id, values, _root: updates.append(values) or values,
    )
    app._render_relevant_evidence_panel(
        fake,
        {"id": "netflix", "evidence_project_ids": [CAREER_CATALYST["id"]]},
        "netflix",
    )
    assert updates == [
        {
            "evidence_project_ids": [CAREER_CATALYST["id"], PODCAST["id"]],
            "match_score": 81,
            "match_tier": "Strong Match",
        }
    ]
    assert protected.read_bytes() == before
    assert "last_package_outputs" not in fake.session_state
    assert "Regenerate the package" in fake.session_state["dashboard_notice"]


@pytest.mark.parametrize(
    ("role", "family", "label"),
    (
        (
            {
                "job_title": "Product Manager, Emerging Formats",
                "raw_text": "product vision podcasts roadmap requirements content technology",
                "role_family": "product_strategy_ops",
            },
            "product_strategy_ops",
            "Product Strategy & Operations",
        ),
        (
            {"job_title": "Principal Product Manager", "raw_text": "product roadmap requirements"},
            "product_strategy_ops",
            "Product Strategy & Operations",
        ),
        (
            {
                "job_title": "Director, Customer Experience Strategy",
                "raw_text": (
                    "customer journey business operations executive decision support transformation "
                    "advisory client discovery operating model recommendations leadership priorities"
                ),
            },
            "business_operations",
            "Business Operations & Strategy",
        ),
        (
            {"job_title": "Business Operations Director", "raw_text": "operating cadence leadership priorities governance"},
            "business_operations",
            "Business Operations & Strategy",
        ),
    ),
)
def test_package_role_resolution(role: dict, family: str, label: str):
    intent = build_role_intent(role, PROJECT_ROOT)
    assert intent["package_role_family"] == family
    assert intent["package_role_label"] == label


def test_product_marketing_manager_is_not_product_management():
    intent = build_role_intent(
        {
            "job_title": "Product Marketing Manager",
            "raw_text": "go-to-market messaging campaigns product launches marketing",
            "role_family": "product_strategy_ops",
        },
        PROJECT_ROOT,
    )
    assert intent["primary_archetype"] != "product_operations"


def test_saved_comparison_fixtures_preserve_product_boundary():
    disney = build_role_intent(parse_job_description(PROJECT_ROOT / DISNEY), PROJECT_ROOT)
    gitlab = build_role_intent(parse_job_description(PROJECT_ROOT / GITLAB), PROJECT_ROOT)
    assert disney["primary_archetype"] == "product_operations"
    assert gitlab["primary_archetype"] != "product_operations"


def test_role_intelligence_and_tailoring_plan_share_one_family(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    _parsed, intent = _netflix_intent(root, job)
    intelligence = reconcile_package_role_intelligence(
        {"role_family": "product_strategy_ops", "role_family_label": "Product Strategy Ops"},
        intent,
    )
    assert intelligence["role_family_label"] == tailoring_plan(intent)["detected_role"]


def test_selected_evidence_uses_existing_score_without_fixed_bonus(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    before = score_job_match(job, root, [])
    relevant = score_job_match(job, root, [CAREER_CATALYST, PODCAST])
    irrelevant = score_job_match(job, root, [IRRELEVANT])
    assert relevant["associated_evidence_matches"]
    assert irrelevant["match_score"] == before["match_score"]
    contribution = evidence_score_contribution(before, relevant)
    assert set(contribution) == {
        "before", "after", "delta", "matched_requirements", "explanation"
    }


def test_selected_evidence_is_not_double_counted(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    once = score_job_match(job, root, [CAREER_CATALYST])
    twice = score_job_match(job, root, [CAREER_CATALYST, CAREER_CATALYST])
    assert once["match_score"] == twice["match_score"]
    assert once["associated_evidence_matches"] == twice["associated_evidence_matches"]


def test_zero_score_change_has_explicit_explanation(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    before = score_job_match(job, root, [])
    after = score_job_match(job, root, [IRRELEVANT])
    assert evidence_score_contribution(before, after)["explanation"] == (
        "No additional role requirements were matched by the selected Evidence."
    )


def test_netflix_resume_uses_condensed_selected_projects_in_saved_order(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    parsed, intent = _netflix_intent(root, job)
    result = tailor_resume(
        "executive_operations", job, root, [CAREER_CATALYST, PODCAST], intent
    )
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "Product Strategy & Operations Leader | Emerging Media" in text
    assert text.index(CAREER_CATALYST["title"]) < text.index(PODCAST["title"])
    assert result["resume_projects_used"] == [CAREER_CATALYST["title"], PODCAST["title"]]
    assert len(resume_project_bullets(CAREER_CATALYST, parsed)) == 2
    assert len(resume_project_bullets(PODCAST, parsed)) == 1
    assert "ten-episode" in text
    assert "Enterprise Employee Engagement" not in text
    for unsupported in (
        "managed software engineers", "A/B testing", "data-science ownership", "60+ direct reports"
    ):
        assert unsupported.lower() not in text.lower()
    validate_candidate_output(text)


def test_netflix_cover_letter_uses_both_projects_and_is_not_generic(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    _parsed, intent = _netflix_intent(root, job)
    result = generate_cover_letter(job, root, [CAREER_CATALYST, PODCAST], intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert result["cover_letter_projects_used"] == [
        CAREER_CATALYST["title"], PODCAST["title"]
    ]
    for expected in (
        "Career Catalyst", "ten-episode", "emerging formats", "active product development",
        "Disney+ launch readiness", "product judgment",
    ):
        assert expected.lower() in text.lower()
    for unsupported in (
        "consumer podcast products at scale", "A/B testing", "member metrics",
        "managed engineering", "internal Netflix knowledge",
    ):
        assert unsupported.lower() not in text.lower()
    assert 250 <= _word_count(text) <= 325
    validate_candidate_output(text)


def test_unrelated_role_does_not_receive_selected_product_projects(tmp_path: Path):
    root, job = _isolated_root(tmp_path, GITLAB)
    parsed = parse_job_description(root / job)
    intent = build_role_intent(parsed, root)
    result = generate_cover_letter(job, root, [CAREER_CATALYST, PODCAST], intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert result["cover_letter_projects_used"] == []
    assert "Just for Us" not in text and "Career Catalyst" not in text


def test_product_cover_letter_falls_back_to_system_projects_when_manual_is_empty(
    tmp_path: Path,
):
    root, job = _isolated_root(tmp_path)
    _parsed, intent = _netflix_intent(root, job)
    intent["manual_evidence_projects"] = []
    result = generate_cover_letter(job, root, [], intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "Career Catalyst" in result["cover_letter_projects_used"]
    assert "Career Catalyst" in text
    assert "Just for Us" not in text


def test_removing_podcast_removes_it_from_regenerated_materials(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    _parsed, intent = _netflix_intent(root, job)
    with_podcast = generate_cover_letter(job, root, [CAREER_CATALYST, PODCAST], intent)
    assert PODCAST["title"] in with_podcast["cover_letter_projects_used"]
    without_podcast = generate_cover_letter(job, root, [CAREER_CATALYST], intent)
    text = Path(without_podcast["output_path"]).read_text(encoding="utf-8")
    assert PODCAST["title"] not in without_podcast["cover_letter_projects_used"]
    assert "Just for Us" not in text


def test_selected_evidence_ranking_is_relevant_and_deterministic(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    parsed = parse_job_description(root / job)
    first = relevant_selected_evidence([IRRELEVANT, CAREER_CATALYST, PODCAST], parsed)
    second = relevant_selected_evidence([IRRELEVANT, CAREER_CATALYST, PODCAST], parsed)
    assert [project_title(item) for item in first] == [project_title(item) for item in second]
    assert IRRELEVANT["title"] not in [project_title(item) for item in first]
    assert evidence_relevance(CAREER_CATALYST, parsed)["matched_signals"]


def test_netflix_candidate_documents_are_created_in_isolated_root(tmp_path: Path):
    root, job = _isolated_root(tmp_path)
    _parsed, intent = _netflix_intent(root, job)
    resume = tailor_resume(
        "executive_operations", job, root, [CAREER_CATALYST, PODCAST], intent
    )
    ats = export_ats_docx(resume["output_path"], root)
    styled = export_styled_docx(resume["output_path"], root)
    letter = generate_cover_letter(job, root, [CAREER_CATALYST, PODCAST], intent)
    paths = [
        Path(ats["output_path"]),
        Path(styled["output_path"]),
        Path(letter["docx_output_path"]),
    ]
    assert all(path.is_file() and path.is_relative_to(root) for path in paths)
    assert all(not path.is_relative_to(PROJECT_ROOT / "exports") for path in paths)
