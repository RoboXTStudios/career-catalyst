from __future__ import annotations

import shutil
from pathlib import Path

import app
import yaml

from tests.fixture_support import replace_evidence_projects

from scripts.evidence_engine import evidence_projects_for_role
from scripts.package_generator import build_package_context, preflight_package_generation
from scripts.role_state_resolver import resolve_selected_evidence, selected_evidence_ids


ROOT = Path(__file__).resolve().parents[1]
OPENAI_IDS = [
    "disney_launch_readiness",
    "enterprise_media_operations",
    "campaignos",
    "career_catalyst",
]


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    for name in ("data", "config", "templates"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, root / name)
    (root / "jobs").mkdir()
    shutil.copy2(
        ROOT / "tests" / "fixtures" / "sprint34" / "openai_program_manager_lead.md",
        root / "jobs" / "openai_program_manager_lead.md",
    )
    evidence = [
        {
            "id": evidence_id,
            "title": title,
            "employer": "RoboXT Studios",
            "problem": "A complex operating problem required clear ownership.",
            "actions": "Led cross-functional delivery and governance.",
            "results": "Improved visibility and execution quality.",
            "status": "Active",
        }
        for evidence_id, title in zip(
            OPENAI_IDS,
            (
                "Disney+ Launch Readiness",
                "Enterprise Media Operations Transformation",
                "CampaignOS",
                "Career Catalyst",
            ),
        )
    ]
    replace_evidence_projects(root / "data" / "evidence_projects.yml", evidence)
    return root


def _record(**updates):
    record = {
        "id": "openai_program_manager_lead",
        "stable_slug": "openai_program_manager_lead",
        "company": "OpenAI",
        "role": "Program Manager Lead",
        "status": "Applied",
        "match_score": 91,
        "evidence_project_ids": list(OPENAI_IDS),
        "job_file": "jobs/openai_program_manager_lead.md",
        "material_paths": {},
    }
    record.update(updates)
    return record


def test_widget_keys_are_contextual_stable_and_artifact_scoped(tmp_path: Path):
    cover = tmp_path / "cover-letter.docx"
    cover.write_bytes(b"cover")
    version = tmp_path / "versions" / "cover-letter.docx"
    version.parent.mkdir()
    version.write_bytes(b"cover-v2")

    first = app._stable_widget_key("existing_material_open", "role-a", "Cover Letter", cover)
    same_rerender = app._stable_widget_key("existing_material_open", "role-a", "Cover Letter", cover)
    other_context = app._stable_widget_key("generated_checklist_open", "role-a", "Cover Letter", cover)
    other_version = app._stable_widget_key("existing_material_open", "role-a", "Cover Letter", version)

    assert first == same_rerender
    assert first != other_context
    assert first != other_version


def test_all_material_controls_get_unique_keys_across_sections(tmp_path: Path):
    files = {}
    for label, suffix in (
        ("ATS DOCX", "ats.docx"),
        ("Styled DOCX", "styled.docx"),
        ("Cover Letter", "cover.docx"),
        ("Package Summary", "summary.txt"),
    ):
        path = tmp_path / suffix
        path.write_bytes(b"artifact")
        files[label] = path

    class FakeColumn:
        def __init__(self, keys):
            self.keys = keys

        def button(self, _label, **kwargs):
            self.keys.append(kwargs["key"])
            return False

    class FakeStreamlit:
        def __init__(self):
            self.keys = []

        def columns(self, count):
            return [FakeColumn(self.keys) for _ in range(count)]

        def button(self, _label, **kwargs):
            self.keys.append(kwargs["key"])
            return False

        def markdown(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

    fake = FakeStreamlit()
    app._material_button_rows(fake, "role-a", files, context="existing_material_open")
    app._material_button_rows(fake, "role-a", files, context="generated_checklist_open")
    assert len(fake.keys) == 8
    assert len(fake.keys) == len(set(fake.keys))


def test_persistent_package_renders_six_controls_without_key_collisions(tmp_path: Path, monkeypatch):
    folder = tmp_path / "package"
    folder.mkdir()
    files = {}
    for label, suffix in (
        ("ATS DOCX", "ats.docx"),
        ("Styled DOCX", "styled.docx"),
        ("Cover Letter", "cover.docx"),
        ("Package Summary", "summary.txt"),
    ):
        path = folder / suffix
        path.write_bytes(b"artifact")
        files[label] = path

    class FakeColumn:
        def __init__(self, keys):
            self.keys = keys

        def button(self, _label, **kwargs):
            self.keys.append(kwargs["key"])
            return False

    class FakeStreamlit:
        def __init__(self):
            self.keys = []
            self.session_state = {}

        def columns(self, count):
            return [FakeColumn(self.keys) for _ in range(count)]

        def button(self, _label, **kwargs):
            self.keys.append(kwargs["key"])
            return False

        def markdown(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        app,
        "find_exact_role_package",
        lambda *_args, **_kwargs: {"files": files, "folder": folder, "archived": False},
    )
    fake = FakeStreamlit()
    app._render_persistent_package_controls(fake, "role-a", {}, context="existing_material_open")
    app._render_persistent_package_controls(fake, "role-a", {}, context="generated_checklist_open")
    assert len(fake.keys) == 12
    assert len(fake.keys) == len(set(fake.keys))


def test_tracker_is_authoritative_for_evidence_aliases_and_stale_state():
    record = {
        "evidence_project_ids": ["canonical-a", "canonical-b"],
        "selected_evidence_ids": ["stale-manifest-id"],
        "selected_evidence": [{"id": "stale-session-id"}],
    }
    assert selected_evidence_ids(record) == ["canonical-a", "canonical-b"]
    resolved = resolve_selected_evidence(
        record,
        [{"id": "canonical-a"}, {"id": "canonical-b"}, {"id": "stale-manifest-id"}],
    )
    assert [item["id"] for item in resolved["projects"]] == ["canonical-a", "canonical-b"]
    assert resolved["missing_ids"] == []


def test_openai_four_evidence_ids_flow_through_preflight_and_generation_context(tmp_path: Path):
    root = _runtime(tmp_path)
    record = _record()
    tracker = {"applications": [record]}

    preflight = preflight_package_generation(record["id"], tracker, root)
    assert preflight["status"] in {"ready", "repairable"}
    assert preflight["selected_evidence_ids"] == OPENAI_IDS
    assert preflight["resolved_evidence_ids"] == OPENAI_IDS
    assert preflight["missing_evidence_ids"] == []
    assert any("Selected Evidence resolves (4 selected)" in item for item in preflight["ready"])

    associated = evidence_projects_for_role(record, root)
    assert [project["id"] for project in associated] == OPENAI_IDS
    context = build_package_context(record["id"], tracker, root)
    assert [project["id"] for project in context["associated_evidence_projects"]] == OPENAI_IDS


def test_invalid_selected_evidence_preserves_valid_ids_and_blocks_only_generation(tmp_path: Path):
    root = _runtime(tmp_path)
    record = _record(evidence_project_ids=[OPENAI_IDS[0], "missing-evidence-id", OPENAI_IDS[1]])
    preflight = preflight_package_generation(record["id"], {"applications": [record]}, root)
    assert preflight["status"] == "blocked"
    assert preflight["selected_evidence_ids"] == [OPENAI_IDS[0], "missing-evidence-id", OPENAI_IDS[1]]
    assert preflight["resolved_evidence_ids"] == [OPENAI_IDS[0], OPENAI_IDS[1]]
    assert preflight["missing_evidence_ids"] == ["missing-evidence-id"]
    assert any("missing-evidence-id" in item for item in preflight["blocking_issues"])


def test_missing_posting_and_existing_materials_remain_readable(tmp_path: Path):
    root = _runtime(tmp_path)
    material = root / "exports" / "active" / "openai_program_manager_lead" / "ats.docx"
    material.parent.mkdir(parents=True)
    material.write_bytes(b"existing")
    record = _record(
        id="missing_openai_role",
        job_file="jobs/missing-openai.md",
        material_paths={"ATS Resume": str(material)},
        company="Missing Co",
        role="Missing Role",
    )
    preflight = preflight_package_generation(record["id"], {"applications": [record]}, root)
    assert preflight["status"] == "blocked"
    assert preflight["job_health"]["status"] == "missing"
    assert material.read_bytes() == b"existing"
