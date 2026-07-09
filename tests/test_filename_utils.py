import re
import unittest
from pathlib import Path

from scripts.filename_utils import (
    build_upload_filename,
    normalize_material_type,
    short_company_name,
    short_role_name,
)


class FilenameUtilsTests(unittest.TestCase):
    def test_known_company_names_are_shortened(self):
        self.assertEqual(
            short_company_name("Sony Interactive Entertainment / PlayStation"),
            "PlayStation",
        )
        for company in ("Crunchyroll", "Google", "Netflix", "Tencent"):
            self.assertEqual(short_company_name(company), company)

    def test_known_role_names_are_shortened(self):
        expected = {
            "Head of Global Creative and Product Development Operations": "HeadGlobalCreativeOps",
            "Director, Enterprise Strategy & Initiatives": "DirectorEnterpriseStrategy",
            "Strategy and Operations Lead, YouTube Auction Brand": "StrategyOpsLeadYouTube",
            "Operations Lead – AI Creator Platform": "OpsLeadAICreatorPlatform",
        }
        for role, short_name in expected.items():
            self.assertEqual(short_role_name(role), short_name)

    def test_disney_principal_product_manager_filename_generation(self):
        self.assertEqual(
            build_upload_filename(
                "Trisha Lynch",
                "Principal Product Manager",
                "Disney",
                "ATS Resume",
                ".docx",
            ),
            "disney_principal_product_manager_trisha_lynch_ats_resume.docx",
        )

    def test_ea_senior_manager_marketing_operations_filename_generation(self):
        self.assertEqual(
            build_upload_filename(
                "Trisha Lynch",
                "Senior Manager, Marketing Operations",
                "Electronic Arts",
                "Application Note",
                "txt",
            ),
            "electronic_arts_senior_manager_marketing_operations_trisha_lynch_application_note.txt",
        )

    def test_long_titles_are_shortened_safely_without_description_fragments(self):
        filename = build_upload_filename(
            "Trisha Lynch",
            "Senior Director of Global Creative Marketing Operations Strategy and Transformation",
            "Very Long Entertainment Company International Incorporated",
            "Strategy Pack",
            "txt",
        )

        self.assertLessEqual(len(filename), 124)
        self.assertEqual(
            filename,
            "very_long_entertainment_company_senior_director_global_creative_marketing_operations_trisha_lynch_strategy_pack.txt",
        )
        self.assertNotIn("transformation", filename)

    def test_punctuation_cleanup_and_no_duplicate_underscores(self):
        filename = build_upload_filename(
            "Trisha Lynch",
            "Program Manager, Design & UX",
            "Netflix, Inc.",
            "Recruiter Message",
            ".txt",
        )

        self.assertEqual(
            filename,
            "netflix_program_manager_design_ux_trisha_lynch_recruiter_message.txt",
        )
        self.assertIsNone(re.search(r"[/,()&\s]", filename))
        self.assertNotIn("__", filename)

    def test_no_filename_too_long_error_regression(self):
        filename = build_upload_filename(
            "Trisha Lynch",
            "Principal Product Manager Platform Operations Workflow Automation Governance",
            "The Walt Disney Company Direct to Consumer Streaming Product and Technology",
            "Hiring Manager Message",
            "txt",
        )

        self.assertLessEqual(len(filename), 124)
        self.assertTrue(filename.endswith("_hiring_manager_message.txt"))

    def test_material_type_normalization(self):
        expected = {
            "Styled": "styled_resume",
            "ATS": "ats_resume",
            "Cover_Letter": "cover_letter",
            "Hiring Manager Follow Up": "hiring_manager_followup",
            "Followup Strategy": "followup_strategy",
        }
        for label, normalized in expected.items():
            self.assertEqual(normalize_material_type(label), normalized)


class GitignoreTests(unittest.TestCase):
    def test_word_temp_docx_files_are_ignored(self):
        gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(
            encoding="utf-8"
        )
        self.assertIn("~$*.docx", gitignore.splitlines())


class ActivePackageFilenameTests(unittest.TestCase):
    def test_active_package_material_filename_helper_uses_standard_names(self):
        from scripts.materials_library import standardized_material_filename

        application = {
            "company": "Netflix",
            "role": "Specialist, Performance Marketing",
            "candidate_name": "Trisha Lynch",
        }
        self.assertEqual(
            standardized_material_filename(application, "ATS Resume", "docx"),
            "netflix_specialist_performance_marketing_trisha_lynch_ats_resume.docx",
        )
        self.assertEqual(
            standardized_material_filename(application, "Cover Letter", "docx"),
            "netflix_specialist_performance_marketing_trisha_lynch_cover_letter.docx",
        )

    def test_disney_active_package_material_filename_helper(self):
        from scripts.materials_library import standardized_material_filename

        application = {"company": "Disney", "role": "Principal Product Manager"}
        self.assertEqual(
            standardized_material_filename(application, "Styled Resume", "docx"),
            "disney_principal_product_manager_trisha_lynch_styled_resume.docx",
        )


if __name__ == "__main__":
    unittest.main()
