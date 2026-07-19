from __future__ import annotations

from pathlib import Path

import app
from scripts import ui_performance


def test_passive_page_and_filter_reruns_render_only_the_active_page():
    calls = {"dashboard": 0, "evidence": 0, "package": 0}

    def renderer(name):
        def render(_st):
            calls[name] += 1
        return render

    renderers = {
        "Dashboard": renderer("dashboard"),
        "Evidence & Capabilities": renderer("evidence"),
        "Generate Package": renderer("package"),
    }
    app.render_active_page(object(), "Dashboard", renderers)
    app.render_active_page(object(), "Dashboard", renderers)

    assert calls == {"dashboard": 2, "evidence": 0, "package": 0}


def test_evidence_and_capability_reads_are_cached_across_passive_selection(monkeypatch, tmp_path):
    calls = {"profile": 0, "graph": 0}

    def load_profile(_root):
        calls["profile"] += 1
        return {"schema_version": 1, "evidence": []}

    def load_graph(_root, _profile):
        calls["graph"] += 1
        return {"schema_version": 1, "capabilities": []}

    monkeypatch.setattr(ui_performance, "load_evidence_profile", load_profile)
    monkeypatch.setattr(ui_performance, "load_capability_graph", load_graph)
    ui_performance.invalidate_evidence_caches()

    ui_performance.load_cached_evidence_profile(tmp_path)
    ui_performance.load_cached_capability_graph(tmp_path)
    ui_performance.load_cached_evidence_profile(tmp_path)
    ui_performance.load_cached_capability_graph(tmp_path)

    assert calls == {"profile": 1, "graph": 1}


def test_persisted_file_signature_guards_migration_and_invalidates_after_edit(
    monkeypatch, tmp_path
):
    evidence_path = tmp_path / "data" / "evidence_profile.yml"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("schema_version: 1\nevidence: []\n", encoding="utf-8")
    calls = []

    def load_profile(_root):
        calls.append(evidence_path.read_text(encoding="utf-8"))
        return {"schema_version": 1, "evidence": list(calls)}

    monkeypatch.setattr(ui_performance, "load_evidence_profile", load_profile)
    ui_performance.invalidate_evidence_caches()
    first = ui_performance.load_cached_evidence_profile(tmp_path)
    second = ui_performance.load_cached_evidence_profile(tmp_path)
    evidence_path.write_text(
        "schema_version: 1\nevidence: []\nprofile_updated_at: changed\n",
        encoding="utf-8",
    )
    third = ui_performance.load_cached_evidence_profile(tmp_path)

    assert first == second
    assert len(calls) == 2
    assert third != second


def test_dashboard_package_scan_is_cached_and_invalidates_for_job_change(
    monkeypatch, tmp_path
):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    job = jobs / "role.md"
    job.write_text("first", encoding="utf-8")
    calls = []

    def load_packages(_root):
        calls.append(job.read_text(encoding="utf-8"))
        return {"packages": [], "unassigned": [], "groups": {}}

    monkeypatch.setattr(ui_performance, "load_application_packages", load_packages)
    ui_performance.invalidate_package_cache()
    ui_performance.load_cached_application_packages(tmp_path)
    ui_performance.load_cached_application_packages(tmp_path)
    job.write_text("second version", encoding="utf-8")
    ui_performance.load_cached_application_packages(tmp_path)

    assert calls == ["first", "second version"]


def test_saved_prospect_selection_is_render_only_and_does_not_build_context(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("passive selection attempted expensive analysis")

    monkeypatch.setattr(app, "build_package_context", forbidden)
    result = app.saved_application_voice(
        {
            "id": "prospect",
            "company": "Example",
            "role": "Operations Lead",
            "match_score": 82,
            "match_tier": "Good Match",
            "role_interpretation": {"primary_archetype": "Business Operations"},
            "role_evidence_selection": {"selected_evidence_ids": ["evidence_1"]},
        }
    )

    assert result["match_report"]["match_score"] == 82
    assert result["selected_evidence_ids"] == ["evidence_1"]


def test_unchanged_evidence_override_does_not_write():
    writes = []
    current = {
        "included_ids": ["evidence_1"],
        "excluded_ids": [],
        "primary_ids": [],
        "supporting_ids": [],
        "user_reviewed": True,
    }
    changed = app.persist_evidence_overrides_if_changed(
        "prospect",
        current,
        dict(current),
        writer=lambda *_args, **_kwargs: writes.append(True),
    )

    assert changed is False
    assert writes == []


def test_include_exclude_control_stages_in_session_without_persistence():
    state = {}
    updated = app.stage_evidence_override(
        state,
        "pending_prospect",
        {},
        "evidence_1",
        "exclude",
    )

    assert state["pending_prospect"] == updated
    assert updated["excluded_ids"] == ["evidence_1"]
    assert "score_dirty" not in state


def test_changed_override_marks_only_prospect_dependents_dirty(tmp_path):
    writes = []

    def writer(tracker_id, updates, root):
        writes.append((tracker_id, updates, root))
        return updates

    changed = app.persist_evidence_overrides_if_changed(
        "prospect",
        {},
        {"excluded_ids": ["evidence_1"]},
        tmp_path,
        writer=writer,
    )

    assert changed is True
    updates = writes[0][1]
    assert updates["prospect_evidence_dirty"] is True
    assert updates["score_dirty"] is True
    assert updates["application_strategy_dirty"] is True
    assert updates["package_dirty"] is True
    assert "evidence_profile_dirty" not in updates
    assert "capability_graph_dirty" not in updates


def test_explicit_targeted_refresh_recomputes_one_prospect_and_clears_analysis_flags(
    tmp_path,
):
    writes = []

    def context_builder(tracker_id, applications, root):
        assert tracker_id == "prospect"
        assert len(applications) == 1
        assert root == tmp_path
        return {
            "role_intelligence": {
                "company_category": "technology_platform",
                "role_family": "business_operations",
                "role_lens": {"primary": "business_operations", "confidence": "High"},
                "requirement_map": [],
                "role_interpretation": {"primary_archetype": "Business Operations"},
                "hiring_manager_lens": {"core_problem": "Improve delivery"},
                "application_strategy": {"candidate_positioning": "Lead with delivery"},
            },
            "match_report": {"match_score": 84, "match_tier": "Good Match"},
            "role_evidence_selection": {"selected_evidence_ids": ["evidence_1"]},
            "evidence_selection_overrides": {"included_ids": ["evidence_1"]},
        }

    def writer(tracker_id, updates, root):
        writes.append((tracker_id, updates, root))
        return {"id": tracker_id, **updates}

    updated = app.refresh_saved_application_analysis(
        "prospect",
        [{"id": "prospect"}],
        tmp_path,
        context_builder=context_builder,
        writer=writer,
    )

    assert updated["match_score"] == 84
    assert updated["prospect_evidence_dirty"] is False
    assert updated["role_analysis_dirty"] is False
    assert updated["score_dirty"] is False
    assert updated["application_strategy_dirty"] is False
    assert updated["package_dirty"] is True
    assert len(writes) == 1
