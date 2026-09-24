from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import app
from scripts.package_generator import PackageGenerationError, job_reference_health, preflight_package_generation
from tests.fixture_support import with_confirmed_role_family


ROOT = Path(__file__).resolve().parents[1]


class _Element:
    def __init__(self, root):
        self.root = root

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def button(self, label, **kwargs):
        self.root.buttons.append((label, kwargs))
        return False

    def link_button(self, label, url, **_kwargs):
        self.root.links.append((label, url))

    def markdown(self, value, **_kwargs):
        self.root.rendered.append(str(value))

    def caption(self, value, **_kwargs):
        self.root.rendered.append(str(value))

    def warning(self, value, **_kwargs):
        self.root.warnings.append(str(value))


class _FakeStreamlit(_Element):
    def __init__(self):
        self.session_state = {}
        self.buttons = []
        self.links = []
        self.rendered = []
        self.warnings = []
        super().__init__(self)

    def container(self, **_kwargs):
        return _Element(self)

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Element(self) for _ in range(count)]

    def multiselect(self, _label, options, default=None, **_kwargs):
        self.selected = list(default or [])
        self.options = list(options)
        return self.selected

    def expander(self, *_args, **_kwargs):
        return _Element(self)


def _missing_application():
    return {
        "id": "3cloud_missing_job_render_guard",
        "stable_slug": "3cloud_missing_job_render_guard",
        "company": "3Cloud",
        "role": "Senior Director, Digital Workplace",
        "status": "Applied",
        "match_score": 82,
        "job_file": "jobs/3cloud_missing_job_render_guard.md",
        "source_url": "https://jobs.example.test/3cloud/senior-director-digital-workplace",
        "evidence_project_ids": ["career_catalyst", "governance_qa_delivery"],
        "material_paths": {},
    }


def test_missing_job_fixture_is_safe_and_recoverable(tmp_path: Path):
    application = _missing_application()
    health = job_reference_health(application, tmp_path)
    assert health["status"] == "missing"
    assert health["recoverable"] is True
    tracker = {"applications": [application]}
    preflight = preflight_package_generation(application["id"], tracker, tmp_path)
    assert preflight["status"] == "blocked"
    assert preflight["job_health"]["status"] == "missing"
    assert application["evidence_project_ids"] == ["career_catalyst", "governance_qa_delivery"]


def test_relevant_evidence_panel_never_resolves_missing_posting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    application = _missing_application()
    fake = _FakeStreamlit()
    monkeypatch.setattr(app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        app,
        "load_evidence_projects",
        lambda _root: [
            {"id": "career_catalyst", "title": "Career Catalyst", "status": "Active"},
            {"id": "governance_qa_delivery", "title": "Governance and QA", "status": "Active"},
        ],
    )

    def unexpected_resolve(*_args, **_kwargs):
        raise AssertionError("read-only Evidence rendering must not resolve a missing posting")

    monkeypatch.setattr(app, "resolve_job_reference", unexpected_resolve)
    app._render_relevant_evidence_panel(fake, application, application["id"])

    assert app.MISSING_POSTING_NOTICE in fake.warnings
    assert fake.selected == application["evidence_project_ids"]
    save_buttons = [kwargs for label, kwargs in fake.buttons if label == "Save Relevant Evidence"]
    assert save_buttons and save_buttons[0]["disabled"] is True
    assert application["evidence_project_ids"] == ["career_catalyst", "governance_qa_delivery"]


def test_compact_dashboard_card_survives_missing_posting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = _FakeStreamlit()
    application = _missing_application()
    package = {"files": {"resume": str(tmp_path / "existing-package.docx")}}
    (tmp_path / "existing-package.docx").write_bytes(b"preserved package")
    monkeypatch.setattr(app, "PROJECT_ROOT", tmp_path)
    app._render_role_card(fake, application, package, compact=True)
    assert app.MISSING_POSTING_NOTICE in fake.warnings
    assert "3Cloud" in " ".join(fake.rendered)
    assert "Senior Director, Digital Workplace" in " ".join(fake.rendered)
    assert any(label == "Open Materials" for label, _kwargs in fake.buttons)


def test_one_missing_role_does_not_block_another_dashboard_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake = _FakeStreamlit()
    missing = _missing_application()
    healthy = {
        **missing,
        "id": "healthy-role",
        "company": "Example",
        "role": "Operations Lead",
    }
    monkeypatch.setattr(app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        app,
        "_safe_job_reference_health",
        lambda application, _root: (
            {"status": "missing", "posting_url": "https://jobs.example.test/relink"}
            if application["id"] == missing["id"]
            else {"status": "valid"}
        ),
    )
    app._render_role_card(fake, missing, {}, compact=True)
    app._render_role_card(fake, healthy, {}, compact=True)
    rendered = " ".join(fake.rendered)
    assert app.MISSING_POSTING_NOTICE in fake.warnings
    assert "Example" in rendered and "Operations Lead" in rendered


def test_valid_relinked_fixture_returns_ready(tmp_path: Path):
    application = _missing_application()
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copytree(ROOT / "config", tmp_path / "config")
    application["evidence_project_ids"] = [
        str(project["id"]) for project in app.load_evidence_projects(tmp_path)[:2]
    ]
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    posting = jobs / "3cloud_missing_job_render_guard.md"
    posting.write_text(
        "# Senior Director, Digital Workplace\n"
        "Company: 3Cloud\n"
        "Tracker ID: 3cloud_missing_job_render_guard\n\n"
        "Lead digital workplace strategy, partner with product and engineering teams, "
        "and improve employee technology operations through measurable delivery outcomes.\n",
        encoding="utf-8",
    )
    application["job_file"] = str(posting.relative_to(tmp_path))
    with_confirmed_role_family(application, tmp_path)
    preflight = preflight_package_generation(
        application["id"], {"applications": [application]}, tmp_path
    )
    assert preflight["status"] in {"ready", "repairable"}
    assert preflight["job_health"]["status"] == "valid"


def test_safe_health_converts_unexpected_resolution_failure(monkeypatch: pytest.MonkeyPatch):
    def fail(*_args, **_kwargs):
        raise PackageGenerationError("missing posting")

    monkeypatch.setattr(app, "job_reference_health", fail)
    health = app._safe_job_reference_health(_missing_application(), ROOT)
    assert health["status"] == "missing"
    assert health["message"] == app.MISSING_POSTING_NOTICE
