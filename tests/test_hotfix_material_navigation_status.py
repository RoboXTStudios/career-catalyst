from __future__ import annotations

import json
from pathlib import Path

import app


def _persisted_package_root(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "runtime"
    folder = root / "exports" / "active" / "in_progress" / "role_a"
    folder.mkdir(parents=True)
    files = {
        "ats_docx": folder / "ats.docx",
        "styled_docx": folder / "styled.docx",
        "cover_letter_docx": folder / "cover.docx",
        "package_summary": folder / "summary.txt",
    }
    for path in files.values():
        path.write_bytes(b"generated")
    manifest = {
        "prospect_id": "role-a",
        "slug": "role_a",
        "files": {key: str(path) for key, path in files.items()},
        "materials": {
            "ATS Resume": str(files["ats_docx"]),
            "Styled Resume": str(files["styled_docx"]),
            "Cover Letter": str(files["cover_letter_docx"]),
            "Package Summary": str(files["package_summary"]),
        },
        "tailoring_metadata": {"selected_count": 4, "used_anywhere_count": 4},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root, {
        "id": "role-a",
        "company": "Example",
        "role": "Program Manager",
        "status": "Considered",
        "match_score": 78,
        "status_updated_at": "2026-08-01T12:00:00Z",
        "evidence_project_ids": ["evidence-a"],
    }


def test_persisted_manifest_reconstructs_completed_results_after_rerun(tmp_path: Path):
    root, application = _persisted_package_root(tmp_path)
    result = app._persisted_package_result(root, application)

    assert result is not None
    assert result["package_complete"] is True
    assert result["tracker_id"] == "role-a"
    assert result["tailoring_metadata"]["selected_count"] == 4
    assert len(result["package_checklist"]) == 5
    assert all(item["exists"] for item in result["package_checklist"])
    assert Path(result["outputs"]["manifest_path"]).name == "manifest.json"


def test_open_button_is_read_only_and_has_deterministic_key(tmp_path: Path, monkeypatch):
    artifact = tmp_path / "resume.docx"
    artifact.write_bytes(b"generated")
    opened: list[Path] = []

    class FakeStreamlit:
        def button(self, _label, **kwargs):
            self.key = kwargs["key"]
            return True

        def success(self, message):
            assert str(artifact) in message

        def warning(self, _message):
            raise AssertionError("artifact open should succeed")

    monkeypatch.setattr(
        app,
        "open_local_path",
        lambda path: (opened.append(path) or True, str(path)),
    )
    fake = FakeStreamlit()
    key = app._stable_widget_key("generated_output", "role-a", "ats_docx", artifact)
    app._show_open_button(fake, "Open ATS resume", artifact, key)

    assert opened == [artifact]
    assert fake.key == key
    assert app._stable_widget_key("generated_output", "role-a", "ats_docx", artifact) == key


def test_status_date_label_matches_canonical_role_status():
    applied = {
        "id": "applied",
        "status": "Applied",
        "applied_date": "2026-07-01T00:00:00Z",
    }
    considered = {
        "id": "considered",
        "status": "Considered",
        "status_updated_at": "2026-07-02T00:00:00Z",
    }
    prospect = {"id": "prospect", "status": "Prospect", "status_updated_at": "2026-07-03"}

    assert app._status_date_fact(applied) == ("Applied date", "2026-07-01")
    assert app._status_date_fact(considered) == ("Status date", "2026-07-02")
    assert app._status_date_fact(prospect) is None
    assert "Applied / status date" not in app._primary_facts_html(considered, {})
    assert "Applied date" not in app._primary_facts_html(prospect, {})
