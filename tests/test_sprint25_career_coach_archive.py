from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

import app
from scripts.application_tracker import (
    is_active_prospect,
    is_archived,
    load_application_tracker,
    migrate_closed_role_archives,
    restore_prospect,
    update_status,
)
from scripts.career_coach import (
    build_career_coach_brief,
    career_coach_is_stale,
)
from scripts.generate_dashboard import filter_dashboard_records


def _record(status: str = "Drafted", **updates):
    record = {
        "id": "role",
        "company": "Acme Media",
        "company_aliases": [],
        "role": "Director, Product Operations",
        "role_aliases": [],
        "status": status,
        "priority": "High",
        "show_on_dashboard": True,
        "notes": "Keep this history.",
        "material_paths": {"Resume": "exports/resume.docx"},
    }
    record.update(updates)
    return record


def _write_tracker(root: Path, records: list[dict]) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump({"applications": records}, sort_keys=False),
        encoding="utf-8",
    )


def _coach_record() -> dict:
    record = _record(
        role_interpretation={
            "primary_archetype": "Product Operations",
            "core_mission": "create a reliable operating model for the product organization",
            "true_must_haves": ["Lead cross-functional product planning"],
            "success_metrics": ["Improve decision speed and delivery consistency"],
            "primary_customer_or_stakeholder": "product and engineering leaders",
        },
        match_gaps=["direct ownership of a product operations function"],
        prospect_revision=2,
    )
    record["role_evidence_selection"] = {
        "primary_evidence": [
            {
                "id": "workflow",
                "title": "Workflow Design",
                "category": "Workflow Design",
                "description": "Built reusable workflows that clarified owners, decisions, and quality checks.",
                "verification_status": "User Confirmed",
                "company": "OMG23",
                "role": "Group Director",
                "leadership_scope": "Cross-functional workflow leadership",
            },
            {
                "id": "leadership",
                "title": "Cross-functional Leadership",
                "category": "Cross-functional Leadership",
                "description": "Aligned creative, media, analytics, technology, and operations teams around delivery.",
                "verification_status": "Verified",
                "company": "OMG23",
                "role": "Group Director",
                "leadership_scope": "Enterprise stakeholder alignment",
            },
        ],
        "supporting_evidence": [],
        "known_gaps": [
            {
                "requirement": "Direct ownership of a product operations function",
                "reason": "The exact title is not recorded.",
            }
        ],
        "excluded_evidence": [
            {"title": "Programmatic Platform Administration", "category": "Programmatic"}
        ],
    }
    return record


def test_terminal_status_saves_archive_once_and_preserve_history(tmp_path):
    _write_tracker(tmp_path, [_record()])
    for terminal in ("Rejected", "Withdrawn", "Closed", "Posting Closed", "Role Filled", "Offer Declined"):
        _write_tracker(tmp_path, [_record()])
        saved = update_status("role", terminal, tmp_path)
        assert is_archived(saved)
        assert saved["show_on_dashboard"] is False
        assert saved["notes"] == "Keep this history."
        assert saved["material_paths"] == {"Resume": "exports/resume.docx"}
        assert len(saved["archive_history"]) == 1
        saved_again = update_status("role", saved["status"], tmp_path)
        assert len(saved_again["archive_history"]) == 1


def test_active_status_save_restores_archived_role_without_data_loss(tmp_path):
    _write_tracker(tmp_path, [_record()])
    archived = update_status("role", "Rejected", tmp_path)
    restored = update_status("role", "Interviewing", tmp_path)
    assert is_archived(archived)
    assert not is_archived(restored)
    assert restored["show_on_dashboard"] is True
    assert restored["material_paths"] == archived["material_paths"]
    assert [item["event"] for item in restored["archive_history"]] == ["archived", "restored"]


def test_manual_restore_preserves_terminal_status_and_history(tmp_path):
    _write_tracker(tmp_path, [_record()])
    archived = update_status("role", "Rejected", tmp_path)
    restored = restore_prospect("role", tmp_path)
    assert restored["status"] == archived["status"] == "Rejected"
    assert not is_archived(restored)
    assert restored["show_on_dashboard"] is False
    assert restored["material_paths"] == archived["material_paths"]
    assert migrate_closed_role_archives(tmp_path)["candidate_count"] == 0


def test_archive_migration_is_dry_run_safe_and_idempotent(tmp_path):
    _write_tracker(
        tmp_path,
        [_record("Applied"), _record("Pass", id="closed", role="Closed Role")],
    )
    before = (tmp_path / "data" / "application_tracker.yml").read_bytes()
    dry_run = migrate_closed_role_archives(tmp_path)
    assert dry_run["candidate_ids"] == ["closed"]
    assert (tmp_path / "data" / "application_tracker.yml").read_bytes() == before
    applied = migrate_closed_role_archives(tmp_path, apply=True)
    rerun = migrate_closed_role_archives(tmp_path, apply=True)
    assert applied["archived_count"] == 1
    assert rerun["archived_count"] == 0
    records = {item["id"]: item for item in load_application_tracker(tmp_path)}
    assert not is_archived(records["role"])
    assert is_archived(records["closed"])


def test_archived_roles_are_excluded_by_default_but_available_explicitly():
    active = _record("Applied")
    archived = _record("Applied", id="old", is_archived=True)
    assert is_active_prospect(active)
    assert not is_active_prospect(archived)
    assert [item["id"] for item in filter_dashboard_records([active, archived])] == ["role"]
    assert [
        item["id"]
        for item in filter_dashboard_records([active, archived], include_archived=True)
    ] == ["role", "old"]
    assert app.summarize_applications([active, archived])["Total"] == 1


def test_legacy_record_without_archive_fields_remains_readable():
    record = _record("Applied")
    assert "is_archived" not in record
    assert is_active_prospect(record)


def test_career_coach_is_role_specific_truthful_and_persistable(tmp_path):
    record = _coach_record()
    brief = build_career_coach_brief(record)
    assert "product operations" in brief["recommended_positioning"].lower()
    assert 2 <= len(brief["lead_with"]) <= 4
    assert brief["hiring_manager_concerns"]
    assert all(item["response_strategy"] for item in brief["concern_responses"])
    assert 2 <= len(brief["best_stories"]) <= 4
    assert all(
        story["star"]["result"].startswith("No separate measurable result")
        for story in brief["best_stories"]
    )
    assert 5 <= len(brief["questions_to_prepare_for"]) <= 8
    assert any("product" in question.lower() for question in brief["questions_to_ask_them"])
    assert not career_coach_is_stale(record, brief)

    _write_tracker(tmp_path, [record])
    persisted = app.refresh_saved_career_coach("role", tmp_path)
    assert persisted["career_coach_brief"]["recommended_positioning"] == brief["recommended_positioning"]
    assert load_application_tracker(tmp_path)[0]["career_coach_brief"]


def test_career_coach_staleness_is_quiet_and_does_not_replace_saved_brief():
    record = _coach_record()
    brief = build_career_coach_brief(record)
    changed = deepcopy(record)
    changed["prospect_revision"] = 3
    assert career_coach_is_stale(changed, brief)
    assert brief["source_revision"] == 2


class _FakeStreamlit:
    def __init__(self):
        self.rendered: list[str] = []
        self.session_state: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def markdown(self, value, **_kwargs):
        self.rendered.append(str(value))

    def write(self, value, **_kwargs):
        self.rendered.append(str(value))

    def caption(self, value, **_kwargs):
        self.rendered.append(str(value))

    def info(self, value, **_kwargs):
        self.rendered.append(str(value))

    def columns(self, count):
        size = count if isinstance(count, int) else len(count)
        return [self for _ in range(size)]

    def expander(self, *_args, **_kwargs):
        return self

    def button(self, *_args, **_kwargs):
        return False


def test_default_career_coach_ui_hides_internal_reasoning_terms():
    fake = _FakeStreamlit()
    app._render_career_coach_brief(fake, build_career_coach_brief(_coach_record()))
    rendered = " ".join(fake.rendered).lower()
    assert "capability graph" not in rendered
    assert "evidence id" not in rendered
    assert "confidence calculation" not in rendered
    assert "recommended positioning" in rendered
    assert "next best action" in rendered


def test_career_coach_navigation_is_passive():
    called = []
    app.render_active_page(
        object(),
        "Career Coach",
        renderers={"Career Coach": lambda _st: called.append("rendered")},
    )
    assert called == ["rendered"]


def test_archived_prospect_can_be_opened_directly():
    state = {"active_workspace_page": "Archive"}
    app.open_archived_prospect(state, "closed-role")
    assert state == {
        "active_workspace_page": "Career Coach",
        "career_coach_tracker_id": "closed-role",
    }
