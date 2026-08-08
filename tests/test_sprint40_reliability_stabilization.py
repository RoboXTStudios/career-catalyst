"""Sprint 40 production-shaped reliability invariants."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import yaml

import app
from scripts.application_tracker import load_application_tracker, save_application_tracker
from scripts.dynamic_role_intelligence import ROLE_FAMILIES, ROLE_GUIDANCE
from scripts.company_voice import ROLE_FAMILY_LABELS
from scripts.package_generator import generate_package
from scripts.score_match import incomplete_match_report
from tests.test_sprint38_5_reparse_state_consistency import _reopened_live_nation_root


class _ReadOnlyEvidenceUI:
    def __init__(self, selected: list[str], *, save: bool):
        self.selected = selected
        self.save = save
        self.session_state: dict = {}
        self.errors: list[str] = []

    def multiselect(self, *_args, **_kwargs):
        return list(self.selected)

    def caption(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def error(self, message: str, *_args, **_kwargs):
        self.errors.append(str(message))

    def button(self, *_args, **_kwargs):
        return self.save

    def rerun(self):
        return None


def test_role_family_registries_are_cross_resolvable():
    """Every accepted dynamic family has downstream label and guidance data."""
    assert set(ROLE_FAMILIES) == set(ROLE_GUIDANCE) == set(ROLE_FAMILY_LABELS)
    assert all(ROLE_FAMILY_LABELS[key] for key in ROLE_FAMILIES)


def test_dashboard_evidence_render_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    tracker_before = (root / "data" / "application_tracker.yml").read_bytes()
    application = load_application_tracker(root)[0]
    projects = app.load_evidence_projects(root)
    ui = _ReadOnlyEvidenceUI([str(projects[0]["id"])], save=False)
    monkeypatch.setattr(app, "PROJECT_ROOT", root)
    monkeypatch.setattr(
        app,
        "update_prospect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("render wrote tracker")),
    )

    app._render_relevant_evidence_panel(ui, application, tracker_id)

    assert (root / "data" / "application_tracker.yml").read_bytes() == tracker_before


def test_malformed_match_fields_are_ignored_without_corrupting_evidence_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    raw = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    raw["applications"][0].update(
        {
            "match_tier": "Not scored",
            "recommended_action": "Complete Import / Paste Job Description",
            "match_strengths": [],
        }
    )
    tracker_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    application = load_application_tracker(root)[0]
    projects = app.load_evidence_projects(root)
    ui = _ReadOnlyEvidenceUI([str(projects[0]["id"])], save=True)
    before = dict(application)
    monkeypatch.setattr(app, "PROJECT_ROOT", root)
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
    monkeypatch.setattr(
        app,
        "score_job_match",
        lambda *_args, **_kwargs: {
            **incomplete_match_report({"company": "Live Nation Worldwide"}),
            "match_tier": "Not scored",
            "recommended_action": "Complete Import / Paste Job Description",
            "match_strengths": [],
        },
    )

    app._render_relevant_evidence_panel(ui, application, tracker_id)

    saved = load_application_tracker(root)[0]
    assert saved["evidence_project_ids"] == before["evidence_project_ids"]
    for field in ("match_score", "match_tier", "match_summary", "match_strengths", "match_gaps", "recommended_action", "confidence"):
        assert saved[field] == before[field]
    assert any("needs repair" in message for message in ui.errors)
    assert "Traceback" not in "\n".join(ui.errors)


def test_package_generation_uses_canonical_tracker_writer():
    source = inspect.getsource(generate_package)
    assert "save_application_tracker" in source
    assert "tracker_path.write_text" not in source


def test_live_nation_lifecycle_reloads_one_canonical_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A production-shaped role keeps score, Evidence, intelligence and paths across reload."""
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    payload = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    projects = yaml.safe_load((root / "data" / "evidence_projects.yml").read_text(encoding="utf-8"))[
        "evidence_projects"
    ]
    selected_ids = [str(project["id"]) for project in projects[:3]]
    payload["applications"][0]["evidence_project_ids"] = selected_ids
    save_application_tracker(payload["applications"], root)

    def canonical_score(_job, _root, associated, **_kwargs):
        if associated:
            return incomplete_match_report({"company": "Live Nation Worldwide"})
        return {
            "match_score": 62,
            "match_tier": "Stretch Match",
            "match_summary": "Canonical canary score.",
            "match_strengths": ["Experiential production responsibilities are explicit."],
            "match_gaps": ["Confirm reporting line before applying."],
            "recommended_action": "Review First",
            "confidence": "Medium",
        }

    monkeypatch.setattr("scripts.package_generator.score_job_match", canonical_score)
    result = generate_package(tracker_id, root, export_root=tmp_path / "exports")
    assert result["package_complete"] is True
    assert all(item["exists"] for item in result["package_checklist"])

    saved = next(item for item in load_application_tracker(root) if item["id"] == tracker_id)
    assert saved["match_score"] == 62
    assert saved["evidence_project_ids"] == selected_ids
    assert saved["location"] == "Work From Home - New York"
    assert saved["work_arrangement"] == "Not specified"
    assert saved["package_manifest"]["prospect_id"] == tracker_id
    package_materials = {
        key: path
        for key, path in saved["package_manifest"]["materials"].items()
        if key != "Job Description"
    }
    assert package_materials
    assert all(Path(path).is_relative_to(tmp_path / "exports") for path in package_materials.values())
