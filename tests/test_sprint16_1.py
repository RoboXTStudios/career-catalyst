import errno
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from scripts.filename_utils import (
    build_upload_filename,
    is_valid_role_title,
    role_title_issue,
    safe_filename,
)
from scripts.job_identity import infer_job_fields_from_url, preferred_role_title
from scripts.job_importer import JobImportError, parse_imported_job
from scripts.job_source_registry import normalize_job_source
from scripts.prospect_intake import ProspectIntakeError, create_prospect
from scripts.score_match import score_job_data


PARAMOUNT_URL = (
    "https://careers.paramount.com/job/Burbank-Director%2C-Product%2C-MarTech-"
    "and-Engagement-Platforms-CA-91505/1395690500/"
)
BAD_TITLE = (
    "As Director of Product, MarTech & Engagement Platforms, you will own the "
    "product vision, roadmap, and technical direction for a portfolio of systems."
)
GOOD_TITLE = "Director, Product, MarTech & Engagement Platforms"
DESCRIPTION = (
    "Lead product strategy, MarTech platforms, engagement systems, technical roadmaps, "
    "cross-functional delivery, governance, quality assurance, and measurement handoffs."
)


class Sprint161UrlIntakeTests(unittest.TestCase):
    def test_paramount_url_fallback_extracts_safe_identity(self):
        fields = infer_job_fields_from_url(PARAMOUNT_URL)
        self.assertEqual(
            fields["job_title"],
            "Director, Product, MarTech and Engagement Platforms",
        )
        self.assertEqual(fields["company"], "Paramount")
        self.assertEqual(fields["location"], "Burbank, CA")
        self.assertEqual(fields["job_id"], "1395690500")

        source = normalize_job_source({"official_url": PARAMOUNT_URL})
        self.assertEqual(source["source_name"], "Paramount Careers")
        self.assertEqual(source["source_type"], "Direct Employer")
        self.assertEqual(source["verification_status"], "Employer Source")

    def test_failed_import_preserves_url_and_fallback_fields(self):
        state = {"prospect_url": PARAMOUNT_URL, "prospect_role": ""}

        def fail(_url):
            raise JobImportError("blocked")

        result = app.apply_prospect_url_import_state(state, fail)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(state["prospect_url"], PARAMOUNT_URL)
        self.assertEqual(state["prospect_original_source_url"], PARAMOUNT_URL)
        self.assertEqual(state["prospect_canonical_url"], PARAMOUNT_URL)
        self.assertEqual(state["prospect_company"], "Paramount")
        self.assertEqual(
            state["prospect_role"],
            "Director, Product, MarTech and Engagement Platforms",
        )
        self.assertEqual(state["prospect_job_id"], "1395690500")
        self.assertIn("source URL was saved", state["prospect_import_result"][1])

    def test_enter_and_button_submit_use_the_same_import_helper(self):
        source = inspect.getsource(app._render_add_prospect)
        self.assertIn('st.form("prospect_url_import_form"', source)
        self.assertIn('st.form_submit_button("Try Import From URL")', source)
        self.assertIn("if url_import_submitted:", source)
        self.assertIn("trigger_url_import()", source)
        self.assertIn("apply_prospect_url_import_state", source)

    def test_shared_import_state_rejects_bad_title_and_protects_user_title(self):
        imported = {
            "job_title": BAD_TITLE,
            "company": "Paramount Streaming",
            "location": "Burbank, CA",
            "job_description": DESCRIPTION,
        }
        state = {
            "prospect_url": PARAMOUNT_URL,
            "prospect_role": GOOD_TITLE,
        }
        result = app.apply_prospect_url_import_state(state, lambda _url: imported)
        self.assertEqual(state["prospect_role"], GOOD_TITLE)
        self.assertEqual(result["status"], "partial")
        self.assertIn("looked like job description text", result["message"])

    def test_parse_imported_job_uses_url_title_instead_of_sentence_heading(self):
        raw = f"# {BAD_TITLE}\n\nCompany: Paramount\n\n## Job Description\n\n{DESCRIPTION}"
        parsed = parse_imported_job(raw, PARAMOUNT_URL)
        self.assertEqual(
            parsed["job_title"],
            "Director, Product, MarTech and Engagement Platforms",
        )
        self.assertNotIn("you will", parsed["job_title"].lower())


class Sprint161TitleAndFilenameTests(unittest.TestCase):
    def test_title_guard_rejects_prose_and_accepts_real_title(self):
        rejected = (
            BAD_TITLE,
            "Director, Platforms, you will lead every technical workstream",
            "This role reports to the EVP and owns platform delivery.",
            "Director of Product. You will manage the roadmap.",
            "Director " + "very " * 40,
        )
        for title in rejected:
            with self.subTest(title=title):
                self.assertFalse(is_valid_role_title(title))
                self.assertIsNotNone(role_title_issue(title))
        self.assertTrue(is_valid_role_title(GOOD_TITLE))
        self.assertEqual(
            preferred_role_title(GOOD_TITLE, BAD_TITLE, PARAMOUNT_URL), GOOD_TITLE
        )

    def test_safe_filename_is_capped_stable_hashed_and_keeps_extension(self):
        long_stem = "Paramount Streaming " + ("platform roadmap engagement " * 20)
        first = safe_filename(long_stem, ".md", lowercase=True, max_stem_length=80)
        second = safe_filename(long_stem, "md", lowercase=True, max_stem_length=80)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(".md"))
        self.assertLessEqual(len(Path(first).stem), 80)
        self.assertRegex(Path(first).stem, r"_[0-9a-f]{8}$")
        self.assertNotIn("&", first)
        self.assertNotIn(" ", first)
        with self.assertRaises(ValueError):
            build_upload_filename(
                "Trisha Lynch", BAD_TITLE, "Paramount", "Cover Letter", "md"
            )

    def test_create_prospect_uses_short_filename_and_blocks_bad_title(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "jobs").mkdir()
            (root / "data" / "application_tracker.yml").write_text(
                "applications: []\n", encoding="utf-8"
            )
            result = create_prospect(
                {
                    "official_url": PARAMOUNT_URL,
                    "company": "Paramount Streaming " + "International " * 12,
                    "job_title": BAD_TITLE,
                    "job_description": DESCRIPTION,
                },
                root,
            )
            filename = Path(result["job_file_path"]).name
            self.assertLessEqual(len(Path(filename).stem), 120)
            self.assertTrue(filename.endswith(".md"))
            self.assertNotIn("you_will", filename)
            self.assertEqual(result["application"]["job_id"], "1395690500")
            self.assertEqual(result["application"]["source_url"], PARAMOUNT_URL)

            with self.assertRaises(ProspectIntakeError) as context:
                create_prospect(
                    {
                        "company": "Paramount",
                        "job_title": BAD_TITLE,
                        "job_description": DESCRIPTION,
                    },
                    root,
                )
            self.assertIn("role title", str(context.exception).lower())

    def test_filename_oserror_is_translated_without_tracker_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "jobs").mkdir()
            tracker_path = root / "data" / "application_tracker.yml"
            tracker_path.write_text("applications: []\n", encoding="utf-8")
            with patch.object(
                Path,
                "write_text",
                side_effect=OSError(errno.ENAMETOOLONG, "File name too long"),
            ):
                with self.assertRaises(ProspectIntakeError) as context:
                    create_prospect(
                        {
                            "company": "Paramount",
                            "job_title": GOOD_TITLE,
                            "job_description": DESCRIPTION,
                        },
                        root,
                    )
            self.assertIn("generated filename was too long", str(context.exception))
            self.assertEqual(tracker_path.read_text(encoding="utf-8"), "applications: []\n")

    def test_incomplete_match_gate_remains_not_scored(self):
        report = score_job_data(
            {"company": "Paramount", "job_title": GOOD_TITLE, "job_description": ""}
        )
        self.assertIsNone(report["match_score"])
        self.assertEqual(report["match_tier"], "Not scored")
        self.assertNotEqual(report["recommended_action"], "Pass")


if __name__ == "__main__":
    unittest.main()
