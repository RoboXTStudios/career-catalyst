import json
from copy import deepcopy
from pathlib import Path

import yaml

from scripts import application_tracker, generate_dashboard, materials_library


def _application(**updates):
    record = {
        "id": "example_labs_operations_lead",
        "company": "Example Labs",
        "role": "Operations Lead",
        "status": "Drafted",
        "priority": "High",
        "show_on_dashboard": True,
    }
    record.update(updates)
    return record


def _write_tracker(root: Path, applications=None) -> Path:
    path = root / application_tracker.TRACKER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"applications": applications or [_application()]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_tracker_cache_reuses_parse_returns_copies_and_invalidates_on_change(
    tmp_path, monkeypatch
):
    tracker_path = _write_tracker(tmp_path)
    application_tracker.invalidate_application_tracker_cache()
    real_load = application_tracker.yaml.load
    calls = []

    def counted_load(*args, **kwargs):
        calls.append(True)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(application_tracker.yaml, "load", counted_load)
    first = application_tracker.load_application_tracker(tmp_path)
    first[0]["company"] = "Mutated in caller"
    second = application_tracker.load_application_tracker(tmp_path)

    assert len(calls) == 1
    assert second[0]["company"] == "Example Labs"

    changed = _application(company="Changed Labs")
    tracker_path.write_text(
        yaml.safe_dump({"applications": [changed]}, sort_keys=False),
        encoding="utf-8",
    )
    third = application_tracker.load_application_tracker(tmp_path)

    assert len(calls) == 2
    assert third[0]["company"] == "Changed Labs"


def test_tracker_save_invalidates_the_in_process_read_cache(tmp_path):
    _write_tracker(tmp_path)
    application_tracker.invalidate_application_tracker_cache()
    application_tracker.load_application_tracker(tmp_path)
    cache_path = (tmp_path / application_tracker.TRACKER_PATH).resolve()
    assert cache_path in application_tracker._TRACKER_READ_CACHE

    application_tracker.save_application_tracker(
        [_application(company="Saved Labs")], tmp_path
    )

    assert cache_path not in application_tracker._TRACKER_READ_CACHE
    loaded = application_tracker.load_application_tracker(tmp_path)
    assert loaded[0]["company"] == "Saved Labs"


def test_dashboard_package_cache_reuses_work_and_invalidates_for_job_inputs(
    tmp_path, monkeypatch
):
    _write_tracker(tmp_path)
    generate_dashboard._PACKAGE_READ_CACHE.clear()
    calls = []

    def counted_load_jobs(root):
        calls.append(root)
        return []

    monkeypatch.setattr(generate_dashboard, "_load_jobs", counted_load_jobs)
    first = generate_dashboard.load_application_packages(tmp_path)
    first["packages"][0]["company"] = "Mutated in caller"
    second = generate_dashboard.load_application_packages(tmp_path)

    assert len(calls) == 1
    assert second["packages"][0]["company"] == "Example Labs"

    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "new-role.md").write_text("# New Role\n", encoding="utf-8")
    generate_dashboard.load_application_packages(tmp_path)

    assert len(calls) == 2


def test_material_manifest_index_and_payload_cache_invalidate_safely(
    tmp_path, monkeypatch
):
    application = _application()
    export_root = tmp_path / "canonical-exports"
    slug = materials_library.role_slug(application)
    folder = export_root / "active" / "in_progress" / slug
    folder.mkdir(parents=True)
    material = folder / "example_labs_operations_lead_resume.docx"
    material.write_bytes(b"resume")
    manifest_path = folder / "manifest.json"
    manifest = {
        "prospect_id": application["id"],
        "files": {"Styled DOCX": str(material)},
        "archived": False,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    materials_library._MANIFEST_INDEX_CACHE.clear()
    materials_library._MANIFEST_PAYLOAD_CACHE.clear()

    real_glob = Path.glob
    scans = []

    def counted_glob(path, pattern):
        if pattern == "*/*/manifest.json":
            scans.append(path)
        return real_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", counted_glob)
    first = materials_library.find_exact_role_package(
        tmp_path, application, export_root=export_root
    )
    first["manifest"]["archived"] = True
    second = materials_library.find_exact_role_package(
        tmp_path, application, export_root=export_root
    )

    assert len(scans) == 2
    assert second["manifest"]["archived"] is False
    assert second["files"]["Styled DOCX"] == material

    updated = deepcopy(manifest)
    updated["archived"] = True
    manifest_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    third = materials_library.find_exact_role_package(
        tmp_path, application, export_root=export_root
    )

    assert len(scans) == 2
    assert third["manifest"]["archived"] is True


def test_material_lookup_still_requires_exact_stable_identity(tmp_path):
    application = _application()
    export_root = tmp_path / "canonical-exports"
    slug = materials_library.role_slug(application)
    folder = export_root / "active" / "in_progress" / slug
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps({"prospect_id": "different_stable_id", "files": {}}),
        encoding="utf-8",
    )
    materials_library._MANIFEST_INDEX_CACHE.clear()
    materials_library._MANIFEST_PAYLOAD_CACHE.clear()

    found = materials_library.find_exact_role_package(
        tmp_path, application, export_root=export_root
    )

    assert found["folder"] is None
    assert found["manifest"] is None


def test_normal_manifest_write_invalidates_a_prebuilt_empty_index(tmp_path):
    application = _application()
    export_root = tmp_path / "canonical-exports"
    folder = (
        export_root
        / "active"
        / "in_progress"
        / materials_library.role_slug(application)
    )
    folder.mkdir(parents=True)
    materials_library.invalidate_material_package_cache()
    before = materials_library.find_exact_role_package(
        tmp_path, application, export_root=export_root
    )
    assert before["folder"] is None

    materials_library.write_role_manifest(
        folder,
        application,
        {},
        archived=False,
    )
    after = materials_library.find_exact_role_package(
        tmp_path, application, export_root=export_root
    )

    assert after["folder"] == folder
