import tempfile
import unittest
from pathlib import Path

from scripts.cleanup_materials import cleanup_materials, plan_materials_cleanup


def _write_tracker(root: Path) -> None:
    tracker = root / "data" / "application_tracker.yml"
    tracker.parent.mkdir(parents=True)
    tracker.write_text(
        """
applications:
- id: active_role
  company: Active Co
  role: Active Role
  status: Applied
- id: rejected_role
  company: Reject Co
  role: Rejected Role
  status: Rejected
""".lstrip(),
        encoding="utf-8",
    )


class CleanupMaterialsTests(unittest.TestCase):
    def test_dry_run_reports_without_deleting_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tracker(root)
            folder = root / "exports" / "active" / "applied_followup" / "active_role"
            folder.mkdir(parents=True)
            temp = folder / "~$active_role_cover_letter.docx"
            temp.write_bytes(b"temp")

            result = cleanup_materials(root, apply=False)

            self.assertEqual(result["applied_count"], 0)
            self.assertTrue(temp.exists())
            self.assertTrue(any(item["reason"] == "Microsoft Word temporary file" for item in result["issues"]))

    def test_active_applied_materials_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tracker(root)
            folder = root / "exports" / "active" / "applied_followup" / "active_role"
            folder.mkdir(parents=True)
            (folder / "active_role_cover_letter.docx").write_bytes(b"docx")
            (folder / "active_role_cover_letter.txt").write_text("text", encoding="utf-8")
            (folder / "manifest.json").write_text("{}", encoding="utf-8")

            result = plan_materials_cleanup(root)

            preserved_paths = {item["path"] for item in result["preserved"]}
            self.assertIn("exports/active/applied_followup/active_role/active_role_cover_letter.docx", preserved_paths)
            self.assertIn("exports/active/applied_followup/active_role/active_role_cover_letter.txt", preserved_paths)
            self.assertFalse(any(item["action"] == "move" for item in result["issues"]))

    def test_inactive_rejected_role_is_identified_for_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tracker(root)
            folder = root / "exports" / "active" / "ready_to_apply" / "rejected_role"
            folder.mkdir(parents=True)
            (folder / "rejected_role_resume.txt").write_text("resume", encoding="utf-8")

            result = plan_materials_cleanup(root)

            moves = [item for item in result["issues"] if item["action"] == "move"]
            self.assertEqual(moves[0]["reason"], "Inactive tracker status: Rejected")
            self.assertEqual(moves[0]["destination"], "exports/archive/inactive/rejected_role")

    def test_duplicate_package_files_and_markdown_remnants_are_flagged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tracker(root)
            folder = root / "exports" / "active" / "applied_followup" / "active_role"
            folder.mkdir(parents=True)
            (folder / "active_role_cover_letter.txt").write_text("txt", encoding="utf-8")
            (folder / "active_role_cover_letter_2.txt").write_text("dup", encoding="utf-8")
            (folder / "active_role_cover_letter.md").write_text("# md", encoding="utf-8")

            result = plan_materials_cleanup(root)
            reasons = {item["path"]: item["reason"] for item in result["issues"]}

            self.assertEqual(
                reasons["exports/active/applied_followup/active_role/active_role_cover_letter_2.txt"],
                "Duplicate generated package file with numeric suffix",
            )
            self.assertEqual(
                reasons["exports/active/applied_followup/active_role/active_role_cover_letter.md"],
                "Markdown remnant with equivalent txt/docx material",
            )

    def test_apply_removes_word_temp_and_empty_directories_only_with_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tracker(root)
            empty = root / "exports" / "archive" / "old_generated_materials" / "empty_role"
            empty.mkdir(parents=True)
            folder = root / "exports" / "active" / "applied_followup" / "active_role"
            folder.mkdir(parents=True)
            temp = folder / "~$active_role_resume.docx"
            temp.write_bytes(b"temp")

            dry = cleanup_materials(root, apply=False)
            self.assertTrue(temp.exists())
            self.assertTrue(empty.exists())
            self.assertTrue(any(item["action"] == "rmdir" for item in dry["issues"]))

            applied = cleanup_materials(root, apply=True)
            self.assertGreaterEqual(applied["applied_count"], 2)
            self.assertFalse(temp.exists())
            self.assertFalse(empty.exists())


if __name__ == "__main__":
    unittest.main()
