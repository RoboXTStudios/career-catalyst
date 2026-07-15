import inspect
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import app
from scripts.generate_dashboard import _relative_href
from scripts.materials_library import role_slug
from tests.test_sprint15_4 import _FakeStreamlit, _record


def _write_package(root: Path, application: dict, *, archived: bool = False) -> tuple[Path, Path]:
    route = "archive/inactive" if archived else "active/in_progress"
    folder = root / "exports" / route / role_slug(application)
    folder.mkdir(parents=True)
    material = folder / "Trisha Lynch & Acme – Cover Letter.docx"
    material.write_bytes(b"docx")
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "prospect_id": application["id"],
                "archived": archived,
                "files": {"Cover Letter DOCX": str(material)},
            }
        ),
        encoding="utf-8",
    )
    return folder, material


def test_existing_exact_package_resolves_to_package_folder(tmp_path):
    application = _record(status="Drafted")
    folder, _ = _write_package(tmp_path, application)

    target, guidance = app.resolve_role_materials_target(
        application, project_root=tmp_path
    )

    assert target == folder.resolve()
    assert guidance == "Opening the application package folder."


def test_missing_materials_returns_clear_guidance_and_does_not_open(tmp_path):
    job_description = tmp_path / "jobs" / "role.md"
    job_description.parent.mkdir()
    job_description.write_text("job", encoding="utf-8")
    application = _record(
        material_paths={"Job Description": str(job_description)}
    )
    st = _FakeStreamlit()

    with patch.object(app, "open_local_path") as open_path:
        opened = app.open_role_materials(st, application, {}, tmp_path)

    assert opened is False
    open_path.assert_not_called()
    assert (
        "warning",
        "No generated application materials exist for this role yet. Generate a package first.",
    ) in st.messages


def test_archived_materials_resolve_to_archived_package_folder(tmp_path):
    application = _record(status="Withdrawn / Closed")
    folder, _ = _write_package(tmp_path, application, archived=True)

    target, guidance = app.resolve_role_materials_target(
        application, project_root=tmp_path
    )

    assert target == folder.resolve()
    assert guidance == "Opening the archived application package folder."


def test_spaces_and_special_characters_are_opened_without_shell_parsing(tmp_path):
    material = tmp_path / "exports" / "messages" / "Trisha & Acme – Cover Letter.docx"
    material.parent.mkdir(parents=True)
    material.write_bytes(b"docx")

    with patch.object(app.sys, "platform", "darwin"), patch.object(
        subprocess, "run"
    ) as run:
        opened, _ = app.open_local_path(material, tmp_path)

    assert opened is True
    run.assert_called_once_with(["open", str(material.resolve())], check=True)


def test_static_dashboard_material_href_encodes_special_characters(tmp_path):
    dashboard = tmp_path / "exports" / "dashboard"
    material = tmp_path / "exports" / "messages" / "Trisha & Acme Cover Letter.docx"
    href = _relative_href(material, dashboard)

    assert href == "../messages/Trisha%20%26%20Acme%20Cover%20Letter.docx"


def test_role_card_open_materials_action_uses_shared_opener(tmp_path):
    material = tmp_path / "resume.docx"
    material.write_bytes(b"docx")
    application = _record()
    package = {"files": {"Styled DOCX": material}}
    st = _FakeStreamlit(clicks={"compact_materials_stable-role"})

    with patch.object(app, "open_role_materials", return_value=True) as open_materials:
        app._render_role_card(st, application, package, compact=True)

    open_materials.assert_called_once_with(st, application, package, app.PROJECT_ROOT)


def test_focused_workspace_open_materials_action_uses_shared_opener():
    source = inspect.getsource(app._render_role_card)

    assert 'key=f"dashboard_quick_{tracker_id}_{action_key}"' in source
    assert source.count("open_role_materials(st, application, package, PROJECT_ROOT)") == 2
