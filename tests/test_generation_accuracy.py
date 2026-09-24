from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from scripts.evidence_tailoring import project_header_line, resume_project_bullets
from scripts.evidence_engine import evidence_placeholders, load_evidence_projects, upsert_evidence_project
from scripts.package_generator import preflight_package_generation
from scripts.package_quality import _PLACEHOLDER_PATTERNS
from scripts.parse_job import parse_job_description
from tests.fixture_support import with_confirmed_role_family


ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "tests" / "fixtures" / "jobs" / "example_company_senior_operations.md"

FYC_WITH_PLACEHOLDER = {
    "id": "fyc_placeholder",
    "title": "Awards Season (FYC) Campaign Operations",
    "problem": "FYC campaigns run on fixed nomination and voting windows.",
    "actions": "Managed creative and ad operations for FYC campaigns across studios.",
    "results": "Supported FYC campaigns. [Add any concrete outcome you can stand behind.]",
    "status": "Active",
}


@pytest.fixture()
def runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    for name in ("data", "config", "templates"):
        shutil.copytree(ROOT / name, root / name)
    (root / "jobs").mkdir()
    shutil.copy2(JOB, root / "jobs" / JOB.name)
    return root


def test_bracketed_author_notes_are_detected_but_links_are_not():
    found = evidence_placeholders(FYC_WITH_PLACEHOLDER)
    assert found == [{"field": "results", "text": "[Add any concrete outcome you can stand behind.]"}]
    assert evidence_placeholders({"actions": "Led [confirm dates] rollout."})[0]["field"] == "actions"
    assert not evidence_placeholders({"actions": "See [the case study](https://example.com) and note [1]."})


def test_generated_text_with_author_notes_fails_the_placeholder_gate():
    for text in ("Delivered on time [confirm dates].", "Grew reach [add metric]."):
        assert any(re.search(pattern, text) for pattern in _PLACEHOLDER_PATTERNS), text
    assert not any(re.search(pattern, "Worked across CM360 and DV360.") for pattern in _PLACEHOLDER_PATTERNS)


def test_preflight_blocks_selected_evidence_with_placeholders(runtime: Path):
    upsert_evidence_project(dict(FYC_WITH_PLACEHOLDER), runtime)
    parsed = parse_job_description(runtime / "jobs" / JOB.name)
    record = with_confirmed_role_family({
        "id": "generic",
        "stable_slug": "generic",
        "company": parsed["company"],
        "role": parsed["job_title"],
        "status": "Prospect",
        "job_file": f"jobs/{JOB.name}",
        "evidence_project_ids": ["fyc_placeholder"],
        "material_paths": {},
    }, runtime)
    result = preflight_package_generation(
        "generic", {"applications": [record]}, runtime, export_root=runtime / "qa_exports"
    )
    assert result["status"] == "blocked"
    issue = next(item for item in result["blocking_issues"] if "placeholder" in item)
    assert "Awards Season (FYC) Campaign Operations" in issue
    assert "results" in issue

    record["evidence_project_ids"] = [load_evidence_projects(runtime)[0]["id"]]
    clean = preflight_package_generation(
        "generic", {"applications": [record]}, runtime, export_root=runtime / "qa_exports"
    )
    assert not any("placeholder" in item for item in clean["blocking_issues"])


FYC_SAVED = {
    "id": "fyc",
    "title": "Awards Season (FYC) Campaign Operations",
    "employer": "OMG23 (Omnicom Media Group)",
    "client": "The Walt Disney Company: Pixar, Searchlight Pictures, 20th Century Studios, and Disney+",
    "project_type": "Awards Campaign Operations",
    "actions": (
        "Managed creative and ad operations for FYC campaigns across Disney's film studios, including Pixar, "
        "Searchlight Pictures, and 20th Century Studios. Coordinated creative specs, asset delivery, and placement "
        "deadlines with entertainment trade publications, including Deadline and The Hollywood Reporter."
    ),
    "results": (
        "Supported FYC campaigns across multiple Disney studios through repeated awards seasons. "
        "[Add any concrete outcome you can stand behind.]"
    ),
    "tags": ["FYC", "trade media"],
}
THEATRICAL_SAVED = {
    "id": "theatrical",
    "title": "Disney Studios Theatrical & Home Entertainment Campaign Operations",
    "client": "The Walt Disney Company: Disney Studios Theatrical and Home Entertainment (including Pixar, Marvel, Lucasfilm, and Disney+)",
    "actions": "Oversaw campaign execution for every release, including all Marvel Phase 5 films and Lucasfilm titles.",
    "results": (
        "Delivered campaign operations for the full slate over a decade. "
        "Managed budgets that ranged from about $5M to about $25M per title across all Disney IPs."
    ),
    "technologies": ["CM360", "DV360"],
}


def test_header_keeps_only_names_the_evidence_supports():
    line, dropped = project_header_line(FYC_SAVED)
    assert "Pixar, Searchlight Pictures, and 20th Century Studios" in line
    assert "Disney+" not in line
    assert dropped == ["Disney+"]
    line, dropped = project_header_line(THEATRICAL_SAVED)
    assert "(including Marvel and Lucasfilm)" in line
    assert dropped == ["Pixar", "Disney+"]


def test_bullets_skip_sentences_that_point_back_to_unseen_context():
    project = {
        "actions": (
            "Identified recurring campaign readiness and QA gaps across teams. "
            "Translated those problems into a working CampaignOS prototype with a structured schema and QA logic."
        ),
        "results": "Established a testable product concept.",
    }
    bullets = resume_project_bullets(project, {})
    assert not any("those problems" in bullet for bullet in bullets)


def test_calendar_years_do_not_outrank_budget_figures():
    project = dict(THEATRICAL_SAVED, results=(
        "Delivered campaign operations for the full Disney Studios theatrical and Home Entertainment slate "
        "from 2016 through 2026. Managed budgets that ranged from about $5M to about $25M per title across all Disney IPs."
    ))
    bullets = resume_project_bullets(project, {})
    assert any("$5M" in bullet for bullet in bullets)
    assert not any("from 2016 through 2026" in bullet for bullet in bullets)


def test_bullets_keep_named_entities_and_figures_over_generic_results():
    fyc = resume_project_bullets(FYC_SAVED, {})
    assert any("Deadline and The Hollywood Reporter" in bullet for bullet in fyc)
    assert not any("[" in bullet for bullet in fyc)
    theatrical = resume_project_bullets(THEATRICAL_SAVED, {})
    assert any("$5M" in bullet and "$25M" in bullet for bullet in theatrical)
    assert not any(bullet.startswith("Delivered campaign operations for the full slate") for bullet in theatrical)


@pytest.mark.parametrize("text, expected", [
    ("Over a decade of experience in media.", "Extensive experience in media."),
    ("With 15+ years of experience leading teams.", "With extensive experience leading teams."),
    ("Brings 12 years of expertise.", "Brings extensive experience."),
    ("Delivered the full slate over a decade.", "Delivered the full slate over many years."),
    ("A seasoned, decade-long career.", "An experienced, long-running career."),
    ("20+ years in entertainment.", "Extensive experience in entertainment."),
])
def test_extended_age_signals_are_rewritten(text, expected):
    from scripts.text_cleanup import normalize_candidate_text

    assert normalize_candidate_text(text) == expected


def test_age_signal_detection_ignores_ordinary_durations():
    from scripts.resume_foundation import candidate_language_violations

    assert candidate_language_violations("Brought more than a decade of expertise.")
    assert candidate_language_violations("Leader with 15+ years in media.")
    assert not candidate_language_violations("Managed 6 campaigns in 2 years with 10 direct reports.")


SONY_JOB = ROOT / "tests" / "fixtures" / "jobs" / "sony_music_director_media_commercial_music_group.md"
MEDIA_EVIDENCE = {
    "id": "media_ops",
    "title": "Release Campaign Operations",
    "actions": "Ran campaign setup and trafficking in CM360 and DV360 with pixel tagging and measurement QA.",
    "results": "Kept tracking and measurement accurate across theatrical releases.",
}


def test_letter_names_covered_posting_requirements():
    from scripts.generate_cover_letter import _name_posting_requirements
    from scripts.requirement_matching import concepts_in

    parsed = parse_job_description(SONY_JOB)
    context = {"parsed_job": parsed, "associated_evidence_projects": [MEDIA_EVIDENCE]}
    letter = "Dear Sony Music Entertainment Hiring Team,\n\nI lead operations work.\n\nBest,\n\nTrisha Lynch"
    named = _name_posting_requirements(letter, context)
    assert "Sony Music Entertainment's posting emphasizes" in named
    assert len(concepts_in(named) & {"ad_operations", "programmatic", "tracking_tagging", "measurement"}) >= 2
    # Nothing to name without covering Evidence: warn instead of claiming.
    bare = {"parsed_job": parsed, "associated_evidence_projects": []}
    assert _name_posting_requirements(letter, bare) == letter
    assert bare["material_warnings"]


def test_letter_review_items_flag_missing_company_requirements_and_duplicates():
    from scripts.package_quality import cover_letter_review_items

    parsed = parse_job_description(SONY_JOB)
    bullet = "Influenced platform implementation and designed repeatable workflows across internal teams and partners."
    resume = f"## Projects\n\n- {bullet}\n"
    letter = f"Dear Hiring Team,\n\nI care about good work.\n\n{bullet}\n\nBest,\n\nTrisha Lynch"
    items = cover_letter_review_items(letter, resume, parsed)
    assert any("does not name Sony Music Entertainment" in item for item in items)
    assert any("fewer than two" in item for item in items)
    assert any("paragraph 3 repeats a résumé bullet" in item for item in items)
    good = (
        "Dear Sony Music Entertainment Hiring Team,\n\n"
        "Campaign setup across programmatic and paid social, with tracking and tagging done right.\n\nBest"
    )
    assert cover_letter_review_items(good, resume, parsed) == []


def test_generic_operating_conditions_closing_is_removed_from_every_letter():
    from scripts.generate_cover_letter import _remove_repeated_dynamic_closing

    letter = (
        "Dear Team,\n\nI ran release campaigns. The through line in my experience is building operating "
        "conditions that help people make sound decisions, protect quality, and deliver dependable work.\n\nBest"
    )
    cleaned = _remove_repeated_dynamic_closing(letter, {"role_intent": {"package_role_family": "community_growth"}})
    assert "operating conditions" not in cleaned
    assert "I ran release campaigns." in cleaned


@pytest.mark.parametrize("title, text, expected", [
    ("Director, Special Projects", "Grow our creator community and member engagement.", "Audience & Community"),
    ("Director, Operations", "Own operating cadence and reporting.", "Business Operations"),
    ("Media Director", "Build media plans and buying across CTV and programmatic.", "Paid Media Execution"),
])
def test_headline_follows_role_family_instead_of_base_profile(title, text, expected):
    from scripts.role_intent import build_role_intent

    intent = build_role_intent({"job_title": title, "raw_text": text, "company": "Acme"}, ROOT)
    headline = intent["resume"]["headline_profile"]
    assert expected in headline
    assert headline != "Senior Operations & Transformation Leader | MarTech | AI Systems | Entertainment"


def test_coverage_matrix_requirements_exclude_posting_boilerplate():
    from scripts.submission_readiness import _requirements

    rows = [row["original_jd_wording"].lower() for row in _requirements(parse_job_description(SONY_JOB))]
    assert any("programmatic" in row for row in rows)
    assert any("award nominations" in row for row in rows)
    for boilerplate in ("what we give you", "california pay range", "$115,000", "equal employment",
                        "global community", "pension", "about sony music"):
        assert not any(boilerplate in row for row in rows), boilerplate



def test_coverage_matrix_grades_with_shared_concepts():
    from scripts.golden_resume import load_golden_resume
    from scripts.submission_readiness import build_requirement_coverage_matrix

    inventory = load_golden_resume(ROOT)
    parsed = parse_job_description(SONY_JOB)
    fyc = {
        "id": "fyc_ops",
        "title": "Awards Season FYC Campaign Operations",
        "actions": "Planned FYC media strategies around nomination and voting windows and placed trade media.",
    }
    guarded = {
        "id": "media_ops",
        "title": "Release Campaign Operations",
        "actions": "Ran campaign setup and trafficking in CM360 and DV360.",
        "guardrails": ["Does not imply awards campaign or trade media ownership."],
    }

    def awards_row(evidence):
        matrix = build_requirement_coverage_matrix(parsed, inventory, evidence, "")
        return next(r for r in matrix if "award nominations" in r["original_jd_wording"])

    before = awards_row([])
    after = awards_row([fyc])
    assert before["coverage"] != "PROVEN"
    assert after["coverage"] == "PROVEN"
    assert "fyc_ops" in after["evidence_ids"]
    # Guardrail text never supplies a concept.
    assert "media_ops" not in awards_row([guarded])["evidence_ids"]
