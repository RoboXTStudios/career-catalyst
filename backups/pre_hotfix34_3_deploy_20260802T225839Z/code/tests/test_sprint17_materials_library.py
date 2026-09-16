import json
import shutil
import tempfile
import unittest
from pathlib import Path

import app
from scripts.generate_application_note import generate_application_note
from scripts.generate_cover_letter import generate_cover_letter
from scripts.generate_interview_prep import generate_interview_prep
from scripts.generate_messages import generate_message
from scripts.generate_strategy_pack import generate_strategy_pack
from scripts.materials_library import (
    archive_legacy_markdown,
    find_exact_role_package,
    material_route,
    move_role_package,
    organize_exact_material_paths,
    organize_package_outputs,
)
from tests.test_sprint15_4 import _FakeStreamlit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _application(status="Active", **updates):
    value = {
        "id": "netflix_program_manager_design",
        "company": "Netflix",
        "role": "Program Manager, Design",
        "status": status,
        "official_url": "https://jobs.netflix.com/example",
    }
    value.update(updates)
    return value


class MaterialRoutingTests(unittest.TestCase):
    def test_status_routes_are_safe_and_deterministic(self):
        expected = {
            "Active": "active/ready_to_apply",
            "Applied": "active/applied_followup",
            "Follow-up": "active/applied_followup",
            "Drafted": "active/in_progress",
            "Passed": "archive/passed",
            "Rejected": "archive/rejected",
            "Invalid/Hidden": "archive/hidden_invalid",
            "Inactive": "archive/inactive",
            "No Longer Pursuing": "archive/no_longer_pursuing",
        }
        for status, route in expected.items():
            with self.subTest(status=status):
                self.assertEqual(material_route(status)["route"], route)
        ambiguous = material_route("Maybe later")
        self.assertTrue(ambiguous["needs_review"])
        self.assertIsNone(ambiguous["route"])

    def test_organizer_moves_exact_files_and_archives_internal_markdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "exports" / "messages"
            source.mkdir(parents=True)
            cover_txt = source / "cover.txt"
            cover_docx = source / "cover.docx"
            internal_md = source / "cover.md"
            cover_txt.write_text("cover text", encoding="utf-8")
            cover_docx.write_bytes(b"docx")
            internal_md.write_text("# cover", encoding="utf-8")

            result = organize_package_outputs(
                root,
                _application(),
                {
                    "cover_letter_text": str(cover_txt),
                    "cover_letter_docx": str(cover_docx),
                    "cover_letter": str(internal_md),
                },
            )
            manifest = result["manifest"]
            folder = (
                root / "exports/active/ready_to_apply/netflix_program_manager_design"
            )
            self.assertTrue(
                (
                    folder
                    / "netflix_program_manager_design_trisha_lynch_cover_letter.txt"
                ).is_file()
            )
            self.assertTrue(
                (
                    folder
                    / "netflix_program_manager_design_trisha_lynch_cover_letter.docx"
                ).is_file()
            )
            self.assertFalse((folder / "cover_letter.txt").exists())
            self.assertFalse((folder / "cover_letter.docx").exists())
            self.assertIn(
                "netflix_program_manager_design_trisha_lynch_cover_letter.docx",
                manifest["files"]["cover_letter_docx"],
            )
            self.assertIn(
                "netflix_program_manager_design_trisha_lynch_cover_letter.txt",
                manifest["files"]["cover_letter_text"],
            )
            self.assertTrue(
                (
                    root
                    / "exports/archive/old_generated_materials/netflix_program_manager_design/cover.md"
                ).is_file()
            )
            self.assertEqual(manifest["prospect_id"], "netflix_program_manager_design")
            self.assertFalse(manifest["archived"])

    def test_ambiguous_status_does_not_move_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "message.txt"
            source.write_text("keep", encoding="utf-8")
            result = organize_package_outputs(
                root, _application("Needs review"), {"recruiter_message": str(source)}
            )
            self.assertTrue(source.is_file())
            self.assertIsNone(result["manifest"])
            self.assertTrue(result["warnings"])

    def test_existing_destination_is_archived_before_current_file_is_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = (
                root / "exports/active/ready_to_apply/netflix_program_manager_design"
            )
            folder.mkdir(parents=True)
            (
                folder
                / "netflix_program_manager_design_trisha_lynch_recruiter_message.txt"
            ).write_text("old", encoding="utf-8")
            source = root / "new.txt"
            source.write_text("new", encoding="utf-8")
            organize_package_outputs(
                root, _application(), {"recruiter_message": str(source)}
            )
            self.assertEqual(
                (
                    folder
                    / "netflix_program_manager_design_trisha_lynch_recruiter_message.txt"
                ).read_text(encoding="utf-8"),
                "new",
            )
            versions = list((folder / "versions").glob("*/*.txt"))
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0].read_text(encoding="utf-8"), "old")


class ManifestAndArchiveTests(unittest.TestCase):
    def test_existing_tracker_paths_move_to_status_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy_recruiter.txt"
            source.write_text("hello", encoding="utf-8")
            application = _application(
                "Rejected", material_paths={"Recruiter Message": str(source)}
            )
            result = organize_exact_material_paths(root, application)
            expected = (
                root
                / "exports/archive/rejected/netflix_program_manager_design/netflix_program_manager_design_trisha_lynch_recruiter_message.txt"
            )
            self.assertTrue(expected.is_file())
            self.assertTrue(result["manifest"]["archived"])
            self.assertEqual(
                result["manifest"]["materials"]["Recruiter Message"],
                str(expected.resolve()),
            )

    def test_exact_manifest_lookup_archive_and_restore_preserve_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "message.txt"
            source.write_text("hello", encoding="utf-8")
            application = _application()
            organize_package_outputs(
                root, application, {"recruiter_message": str(source)}
            )
            found = find_exact_role_package(root, application)
            self.assertFalse(found["archived"])
            self.assertTrue(found["folder"].is_dir())

            archived = move_role_package(root, application, archive=True)
            self.assertTrue(archived["moved"])
            self.assertTrue(archived["manifest"]["archived"])
            self.assertTrue(
                (
                    archived["folder"]
                    / "netflix_program_manager_design_trisha_lynch_recruiter_message.txt"
                ).is_file()
            )

            restored = move_role_package(root, application, archive=False)
            self.assertTrue(restored["moved"])
            self.assertFalse(restored["manifest"]["archived"])
            payload = json.loads(
                (restored["folder"] / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertFalse(payload["archived"])

    def test_missing_exact_package_returns_clear_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = move_role_package(Path(temporary), _application(), archive=True)
            self.assertFalse(result["moved"])
            self.assertEqual(result["reason"], "No exact package materials yet")

    def test_legacy_markdown_is_archived_and_txt_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            messages = root / "exports/messages"
            messages.mkdir(parents=True)
            markdown = messages / "legacy.md"
            markdown.write_text("# Hello\n\n**World**", encoding="utf-8")

            dry_run = archive_legacy_markdown(root, apply=False)
            self.assertEqual(dry_run["planned_count"], 1)
            self.assertTrue(markdown.is_file())

            applied = archive_legacy_markdown(root, apply=True)
            self.assertEqual(applied["moved_count"], 1)
            self.assertFalse(markdown.exists())
            archived = root / "exports/archive/old_generated_materials/messages"
            self.assertEqual(
                (archived / "legacy.txt").read_text(encoding="utf-8"),
                "Hello\n\nWorld\n",
            )


class FormatAndAppPolicyTests(unittest.TestCase):
    def test_new_user_facing_generators_write_txt_not_markdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in ("data", "config"):
                shutil.copytree(PROJECT_ROOT / directory, root / directory)
            (root / "jobs").mkdir()
            shutil.copy2(
                PROJECT_ROOT / "jobs/netflix_inc_program_manager_design.md",
                root / "jobs/netflix_inc_program_manager_design.md",
            )
            job = "jobs/netflix_inc_program_manager_design.md"
            results = (
                generate_cover_letter(job, root),
                generate_application_note(job, root),
                generate_message("recruiter", job, root),
                generate_message("hiring-manager", job, root),
                generate_strategy_pack(job, root),
                generate_interview_prep(job, root),
            )
            self.assertTrue(
                all(Path(item["output_path"]).suffix == ".txt" for item in results)
            )
            self.assertFalse(list((root / "exports/messages").glob("*.md")))
            self.assertFalse(list((root / "exports/strategy_packs").glob("*.md")))

    def test_material_buttons_hide_markdown_when_txt_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown = root / "cover.md"
            text = root / "cover.txt"
            markdown.write_text("md", encoding="utf-8")
            text.write_text("txt", encoding="utf-8")
            st = _FakeStreamlit()
            app._material_button_rows(
                st,
                "role",
                {"Cover Letter": markdown, "Cover Letter Text": text},
            )
            labels = {label for label, _ in st.buttons}
            self.assertIn("Cover letter text .txt", labels)
            self.assertNotIn("Cover letter .md", labels)

    def test_outputs_view_is_grouped_and_archive_is_separate(self):
        source = __import__("inspect").getsource(app._render_recent_outputs)
        for label in (
            "Active Materials",
            "Needs Cleanup / Legacy Materials",
        ):
            self.assertIn(label, source)
        self.assertNotIn("Archived Packages", source)
        self.assertIn("expanded=False", source)


if __name__ == "__main__":
    unittest.main()
