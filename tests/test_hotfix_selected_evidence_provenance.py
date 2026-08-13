from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.evidence_tailoring import candidate_project_reference_violations
from scripts.role_state_resolver import resolve_selected_evidence
from scripts.tailor_resume import ResumeTailoringError, tailor_resume


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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

MULTIVERSE = {
    "id": "multiverse_editorial",
    "title": "OMG23 Multiverse Newsletter",
    "status": "Active",
    "problem": "The company needed an internal publication for employee storytelling.",
    "actions": (
        "Created and served as Managing Editor, developing the editorial voice, "
        "content strategy, and contributor framework."
    ),
    "results": "Reached more than 400 employees through the internal publication.",
    "tags": ["Editorial", "Storytelling", "Internal Communications"],
}
LEGACY_MULTIVERSE = {
    "name": "OMG23 Multiverse Newsletter",
    "role": "Creator & Managing Editor",
}
UNSELECTED = {
    "id": "unselected_product_lab",
    "title": "Unselected Product Lab",
    "problem": "A separate product experiment.",
    "actions": "Built an unrelated prototype.",
    "results": "Validated a separate concept.",
}


def _context(*, duplicate_selected: bool = False) -> dict:
    associated = [MULTIVERSE, MULTIVERSE] if duplicate_selected else [MULTIVERSE]
    return {
        "career_data": {
            "data": {
                "projects": {"projects": [LEGACY_MULTIVERSE, UNSELECTED]},
                "evidence_projects": {
                    "evidence_projects": [MULTIVERSE, UNSELECTED]
                },
            }
        },
        "associated_evidence_projects": associated,
        "evidence_scope_enforced": True,
        "resume_evidence_selection": {
            "used_projects": [{"_project": MULTIVERSE}],
            "fallback_used": [],
        },
    }


@pytest.mark.parametrize(
    "reference",
    (
        "OMG23 Multiverse Newsletter",
        "multiverse_editorial",
        "multiverse editorial",
    ),
)
def test_selected_stable_id_authorizes_its_exact_aliases(reference: str):
    assert candidate_project_reference_violations(
        f"Selected proof: {reference}.", _context(), "ats_resume"
    ) == []


def test_tracker_selected_multiverse_resolves_one_of_one():
    resolved = resolve_selected_evidence(
        {"evidence_project_ids": ["multiverse_editorial"]}, [MULTIVERSE, UNSELECTED]
    )
    assert resolved["selected_ids"] == ["multiverse_editorial"]
    assert resolved["projects"] == [MULTIVERSE]
    assert resolved["missing_ids"] == []


def test_duplicate_alias_records_do_not_create_false_or_duplicate_violations():
    assert candidate_project_reference_violations(
        "OMG23 Multiverse Newsletter demonstrates editorial operations.",
        _context(duplicate_selected=True),
        "ats_resume",
    ) == []

    violations = candidate_project_reference_violations(
        "Unselected Product Lab is mentioned twice. Unselected Product Lab.",
        _context(duplicate_selected=True),
        "ats_resume",
    )
    assert violations == ["unselected product lab"]


def test_similar_unselected_title_is_not_fuzzily_authorized():
    context = _context()
    similar = {
        "id": "multiverse_newsletter_redesign",
        "title": "OMG23 Multiverse Newsletter Redesign",
    }
    context["career_data"]["data"]["projects"]["projects"].append(similar)

    violations = candidate_project_reference_violations(
        "OMG23 Multiverse Newsletter Redesign", context, "ats_resume"
    )
    assert "omg23 multiverse newsletter redesign" in violations
    assert violations


def _isolated_axs_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "axs"
    for relative in FOUNDATION_FILES:
        source = PROJECT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    job = root / "jobs/axs_product_marketing.md"
    job.parent.mkdir(parents=True, exist_ok=True)
    job.write_text(
        """# Sr. Manager, Product Marketing

Company: AXS

## Role

Lead product marketing for a live-entertainment platform. Develop audience
storytelling, editorial content strategy, cross-functional launch plans, and
contributor programs that communicate product value to fans and partners.
""",
        encoding="utf-8",
    )
    return root, job.relative_to(root)


def test_tailor_resume_accepts_selected_multiverse_and_blocks_unselected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, job = _isolated_axs_root(tmp_path)
    result = tailor_resume(
        "entertainment_marketing", job, root, [MULTIVERSE]
    )
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "OMG23 Multiverse Newsletter" in text
    assert result["resume_projects_used"] == ["OMG23 Multiverse Newsletter"]

    from scripts import tailor_resume as resume_module

    original_render = resume_module._render_markdown

    def contaminated_render(*args, **kwargs):
        return original_render(*args, **kwargs) + "\n\nCareer Catalyst\n"

    monkeypatch.setattr(resume_module, "_render_markdown", contaminated_render)
    with pytest.raises(ResumeTailoringError, match="unselected Evidence/project"):
        resume_module.tailor_resume(
            "entertainment_marketing", job, root, [MULTIVERSE]
        )
