from __future__ import annotations

import random
import shutil
from pathlib import Path

import pytest

from scripts.evidence_engine import load_evidence_projects
from scripts.evidence_tailoring import evidence_score_contribution
from scripts.parse_job import parse_job_description
from scripts.requirement_matching import (
    concepts_in,
    match_evidence_to_requirements,
    posting_requirements,
    requirement_coverage_bonus,
)
from scripts.score_match import normalized_posting, score_job_data


ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "tests" / "fixtures" / "jobs"
SONY = JOBS / "sony_music_director_media_commercial_music_group.md"

FYC_EVIDENCE = {
    "id": "fyc_campaigns",
    "title": "FYC Campaign Operations",
    "actions": "Ran FYC campaign trafficking and trade publication placements for awards season.",
    "results": "Delivered FYC flights on schedule.",
}
TRADE_DESK_ONLY = {
    "id": "dsp_ops",
    "title": "DSP Operations",
    "actions": "Managed buys in The Trade Desk.",
}
UNRELATED = {
    "id": "gardening",
    "title": "Community Garden",
    "actions": "Planted tomatoes and organized volunteer watering schedules.",
}


@pytest.fixture()
def runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    for name in ("data", "config"):
        shutil.copytree(ROOT / name, root / name)
    return root


def _job(path: Path) -> dict:
    parsed = parse_job_description(path)
    return {**parsed, "job_description": parsed["raw_text"]}


def test_synonym_layer_links_fyc_to_award_nominations_and_trades_to_trade_media():
    posting = normalized_posting({
        "job_title": "Director, Media",
        "company": "Acme Music",
        "job_description": (
            "What you'll do:\n"
            "Develop media strategies around music award nominations and voting windows\n"
            "Place advertising in trade media and industry outlets\n"
        ),
    })
    coverage = match_evidence_to_requirements(posting, [FYC_EVIDENCE])
    by_text = {row["text"]: row for row in coverage["requirements"]}
    awards = by_text["Develop media strategies around music award nominations and voting windows"]
    trades = by_text["Place advertising in trade media and industry outlets"]
    assert "awards_campaigns" in awards["matched_concepts"]
    assert trades["coverage"] == "full"
    assert "awards-season campaigns" in coverage["matched_labels"]


def test_the_trade_desk_is_not_trade_media():
    assert "trade_media" not in concepts_in("Managed buys in The Trade Desk.")
    assert "programmatic" in concepts_in("Managed buys in The Trade Desk.")


def test_benefits_and_eeo_lines_are_not_requirements():
    requirements = [row["text"].lower() for row in posting_requirements(_job(SONY))]
    assert requirements
    assert not any("community" in text or "equal employment" in text for text in requirements)
    assert any("programmatic" in text for text in requirements)


def test_sony_media_evidence_covers_paid_media_requirements(runtime: Path):
    job = _job(SONY)
    projects = {p["id"]: p for p in load_evidence_projects(runtime)}
    base = score_job_data(job, runtime, [])
    martech = score_job_data(job, runtime, [projects["martech_platform_governance_measurement_operations"]])
    podcast = score_job_data(job, runtime, [projects["just_for_us_podcast"]])
    assert martech["match_score"] > base["match_score"]
    assert "ad operations and campaign setup" in martech["associated_evidence_match_details"]
    assert "programmatic and CTV" in martech["associated_evidence_match_details"]
    # Evidence with no bearing on the posting's requirements adds nothing.
    assert podcast["match_score"] == base["match_score"]


@pytest.mark.parametrize("fixture", [
    "sony_music_director_media_commercial_music_group.md",
    "one_firefly_agency_operations.md",
    "example_company_senior_operations.md",
])
def test_adding_evidence_never_lowers_the_score(runtime: Path, fixture: str):
    job = _job(JOBS / fixture)
    projects = load_evidence_projects(runtime) + [FYC_EVIDENCE, UNRELATED]
    base = score_job_data(job, runtime, [])["match_score"]
    for seed in (1, 2, 3):
        order = list(projects)
        random.Random(seed).shuffle(order)
        selected: list[dict] = []
        previous = base
        for project in order:
            selected.append(project)
            score = score_job_data(job, runtime, selected)["match_score"]
            assert score >= previous, (fixture, project["id"], previous, score)
            previous = score


def test_coverage_bonus_is_monotonic_in_the_evidence_set():
    job = normalized_posting(_job(SONY))
    projects = [FYC_EVIDENCE, TRADE_DESK_ONLY, UNRELATED]
    previous = 0
    for count in range(len(projects) + 1):
        bonus = requirement_coverage_bonus(match_evidence_to_requirements(job, projects[:count]))
        assert bonus >= previous
        previous = bonus


def test_high_confidence_never_sits_next_to_no_supported_matches(runtime: Path):
    job = _job(JOBS / "one_firefly_agency_operations.md")
    assert score_job_data(job, runtime, [])["confidence"] == "High"
    report = score_job_data(job, runtime, [UNRELATED])
    assert report["requirement_coverage"]["covered_count"] == 0
    assert report["confidence"] == "Medium"
    assert any("does not support any parsed posting requirement" in gap for gap in report["match_gaps"])


def test_contribution_reports_requirement_coverage(runtime: Path):
    job = _job(SONY)
    projects = {p["id"]: p for p in load_evidence_projects(runtime)}
    before = score_job_data(job, runtime, [])
    after = score_job_data(job, runtime, [projects["enterprise_media_operations_transformation"]])
    contribution = evidence_score_contribution(before, after)
    coverage = contribution["requirement_coverage"]
    assert coverage["covered"] > 0
    assert coverage["total"] == len(coverage["requirements"])
    assert contribution["delta"] >= 0
    assert contribution["explanation"].startswith(
        f"Selected Evidence supports {coverage['covered']} of {coverage['total']}"
    )
    assert contribution["matched_requirements"]
