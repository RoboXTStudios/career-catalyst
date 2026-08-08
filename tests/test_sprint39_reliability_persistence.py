"""Sprint 39 regressions for safe match-state persistence."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import app
from scripts.application_tracker import (
    TrackerValidationError,
    load_application_tracker,
    save_application_tracker,
    validate_application_tracker,
)
from scripts.score_match import incomplete_match_report, persisted_match_fields
from tests.test_sprint38_5_reparse_state_consistency import _reopened_live_nation_root


def _complete_report(score: int = 67) -> dict:
    return {
        "match_score": score,
        "match_tier": "Stretch Match",
        "match_summary": "Evidence-adjusted canary score.",
        "match_strengths": [
            "Experiential production responsibilities are explicit.",
            "Live event scope is clearly identified.",
            "The posting provides enough detail for review.",
        ],
        "match_gaps": ["Confirm reporting line before applying."],
        "recommended_action": "Review First",
        "confidence": "Medium",
    }


class _EvidenceStreamlit:
    def __init__(self, selected: list[str]):
        self.selected = selected
        self.session_state: dict = {}

    def multiselect(self, *_args, **_kwargs):
        return list(self.selected)

    def caption(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def button(self, *_args, **_kwargs):
        return True

    def rerun(self):
        return None


def _run_evidence_save(
    root: Path,
    tracker_id: str,
    monkeypatch: pytest.MonkeyPatch,
    report: dict,
) -> list[str]:
    application = load_application_tracker(root)[0]
    projects = app.load_evidence_projects(root)
    selected = [str(projects[0]["id"]), str(projects[1]["id"])]
    fake = _EvidenceStreamlit(selected)
    monkeypatch.setattr(app, "PROJECT_ROOT", root)
    monkeypatch.setattr(app, "score_job_match", lambda *_args, **_kwargs: report)
    monkeypatch.setattr(
        app,
        "resolve_job_reference",
        lambda *_args, **_kwargs: {"job_path": root / application["job_file"]},
    )
    monkeypatch.setattr(
        app,
        "_safe_job_reference_health",
        lambda *_args, **_kwargs: {"status": "valid", "path": root / application["job_file"]},
    )
    app._render_relevant_evidence_panel(fake, application, tracker_id)
    return selected


def test_incomplete_match_reports_never_cross_persistence_boundary():
    report = incomplete_match_report(
        {"company": "Live Nation Worldwide", "job_title": "Producer", "job_description": ""}
    )
    assert report is not None
    assert persisted_match_fields(report) == {}


def test_complete_match_reports_persist_as_one_valid_snapshot():
    report = _complete_report()
    assert persisted_match_fields(report) == report


def test_live_nation_evidence_save_preserves_canonical_match_state_on_incomplete_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    before = deepcopy(load_application_tracker(root)[0])
    selected = _run_evidence_save(
        root,
        tracker_id,
        monkeypatch,
        {
            **incomplete_match_report(
                {"company": "Live Nation Worldwide", "job_title": "Producer", "job_description": ""}
            ),
            "match_tier": "Not scored",
            "recommended_action": "Complete Import / Paste Job Description",
            "match_strengths": [],
        },
    )

    saved = load_application_tracker(root)
    assert len(saved) == 1
    record = saved[0]
    assert record["evidence_project_ids"] == selected
    for field in (
        "match_score",
        "match_tier",
        "match_summary",
        "match_strengths",
        "match_gaps",
        "recommended_action",
        "confidence",
    ):
        assert record[field] == before[field]
    assert validate_application_tracker(root)["errors"] == []
    assert not list((root / "exports").rglob("*")) if (root / "exports").exists() else True


def test_live_nation_evidence_save_persists_complete_adjusted_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    selected = _run_evidence_save(root, tracker_id, monkeypatch, _complete_report(68))
    saved = load_application_tracker(root)
    assert len(saved) == 1
    assert saved[0]["evidence_project_ids"] == selected
    assert saved[0]["match_score"] == 68
    assert saved[0]["match_tier"] == "Stretch Match"
    assert validate_application_tracker(root)["errors"] == []


def test_failed_tracker_mutation_is_byte_for_byte_unchanged(tmp_path: Path):
    root, _tracker_id = _reopened_live_nation_root(tmp_path)
    tracker = root / "data" / "application_tracker.yml"
    before = tracker.read_bytes()
    applications = load_application_tracker(root)
    applications[0]["match_tier"] = "Not scored"
    with pytest.raises(TrackerValidationError):
        save_application_tracker(applications, root)
    assert tracker.read_bytes() == before


def test_incomplete_reparse_preserves_saved_match_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    monkeypatch.setattr(
        "app.score_job_data",
        lambda *_args, **_kwargs: incomplete_match_report(
            {"company": "Live Nation Worldwide", "job_title": "Producer", "job_description": ""}
        ),
    )
    app.reparse_dashboard_role(tracker_id, project_root=root)
    saved = load_application_tracker(root)[0]
    assert saved["match_score"] == 62
    assert saved["match_tier"] == "Stretch Match"
    assert saved["role_family"] == "experiential_live_event_production"
    assert validate_application_tracker(root)["errors"] == []
