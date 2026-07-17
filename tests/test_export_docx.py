import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from scripts.cli import main
from scripts.export_docx import (
    MissingMarkdownFileError,
    export_ats_docx,
    export_styled_docx,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_RESUME = "exports/markdown/Trisha_Lynch_executive_operations_Crunchyroll_Resume.md"
LINKEDIN_URL = "https://www.linkedin.com/in/trisha-lynch-3433417"
OLD_LINKEDIN_URL = "https://www.linkedin.com/in/trishalynch"


def _document_text(document):
    body_text = [paragraph.text for paragraph in document.paragraphs]
    table_text = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return "\n".join(body_text + table_text)


class ExportDocxTests(unittest.TestCase):
    def test_styled_export_creates_docx(self):
        result = export_styled_docx(MARKDOWN_RESUME, PROJECT_ROOT)

        self.assertTrue(
            result["output_path"].endswith(
                "TrishaLynch_DirectorEnterpriseStrategy_Crunchyroll_Styled.docx"
            )
        )
        self.assertTrue(Path(result["output_path"]).is_file())

    def test_ats_export_creates_docx(self):
        result = export_ats_docx(MARKDOWN_RESUME, PROJECT_ROOT)

        self.assertTrue(
            result["output_path"].endswith(
                "TrishaLynch_DirectorEnterpriseStrategy_Crunchyroll_ATS.docx"
            )
        )
        self.assertTrue(Path(result["output_path"]).is_file())

    def test_both_output_files_are_not_empty(self):
        styled = export_styled_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        ats = export_ats_docx(MARKDOWN_RESUME, PROJECT_ROOT)

        self.assertGreater(Path(styled["output_path"]).stat().st_size, 0)
        self.assertGreater(Path(ats["output_path"]).stat().st_size, 0)

    def test_missing_markdown_file_produces_helpful_error(self):
        missing_path = "exports/markdown/missing_resume.md"

        with self.assertRaises(MissingMarkdownFileError) as context:
            export_styled_docx(missing_path, PROJECT_ROOT)

        self.assertIn("Markdown resume file not found", str(context.exception))

    def test_ats_output_has_no_tables_and_one_column(self):
        result = export_ats_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        document = Document(result["output_path"])

        self.assertEqual(document.tables, [])
        for section in document.sections:
            columns = section._sectPr.find(qn("w:cols"))
            self.assertIsNotNone(columns)
            self.assertEqual(columns.get(qn("w:num")), "1")

    def test_styled_output_has_at_least_one_paragraph(self):
        result = export_styled_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        document = Document(result["output_path"])

        self.assertGreater(len(document.paragraphs), 0)

    def test_styled_output_has_four_column_platforms_table(self):
        result = export_styled_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        document = Document(result["output_path"])

        self.assertGreaterEqual(len(document.tables), 1)
        platform_table = document.tables[0]
        self.assertEqual(len(platform_table.columns), 4)
        table_text = "\n".join(cell.text for cell in platform_table.rows[0].cells)
        for heading in (
            "AdTech & Measurement",
            "AI, Automation & Operational Systems",
            "Workflow & Collaboration",
            "Publishing & Content",
        ):
            self.assertIn(heading, table_text)

    def test_styled_output_contains_platforms_without_personal_projects(self):
        result = export_styled_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        document = Document(result["output_path"])
        content = _document_text(document)

        self.assertIn("Platforms & Technologies", content)
        for term in ("Career Catalyst", "CampaignOS", "Substack"):
            self.assertNotIn(term, content)

    def test_ats_output_excludes_personal_projects(self):
        result = export_ats_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        document = Document(result["output_path"])

        content = _document_text(document)
        for term in ("Career Catalyst", "CampaignOS", "Substack"):
            self.assertNotIn(term, content)

    def test_styled_output_contains_full_clickable_linkedin_url(self):
        result = export_styled_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        document = Document(result["output_path"])
        content = _document_text(document)

        self.assertIn(LINKEDIN_URL, content)
        self.assertNotIn(OLD_LINKEDIN_URL, content)
        self.assertNotIn("LinkedIn: linkedin.com/", content)
        self.assertTrue(
            any(
                relationship.reltype == RT.HYPERLINK
                and relationship.target_ref == LINKEDIN_URL
                for relationship in document.part.rels.values()
            )
        )

    def test_ats_output_contains_full_visible_linkedin_url(self):
        result = export_ats_docx(MARKDOWN_RESUME, PROJECT_ROOT)
        content = _document_text(Document(result["output_path"]))

        self.assertIn(LINKEDIN_URL, content)
        self.assertNotIn(OLD_LINKEDIN_URL, content)
        self.assertNotIn("LinkedIn: linkedin.com/", content)

    def test_exports_use_human_profile_and_professional_evidence(self):
        for exporter in (export_styled_docx, export_ats_docx):
            result = exporter(MARKDOWN_RESUME, PROJECT_ROOT)
            content = _document_text(Document(result["output_path"]))
            self.assertNotIn("Emphasizes", content)
            self.assertNotIn("Relevant strengths include", content)
            self.assertIn("known for finding the real constraint", content)
            self.assertIn("Introduced scalable workflows", content)
            for term in ("Career Catalyst", "CampaignOS", "Substack"):
                self.assertNotIn(term, content)

    def test_exports_preserve_canonical_platform_language(self):
        for exporter in (export_styled_docx, export_ats_docx):
            result = exporter(MARKDOWN_RESUME, PROJECT_ROOT)
            content = _document_text(Document(result["output_path"]))
            self.assertIn("AI Workflow Design", content)
            self.assertIn("Process Automation", content)
            self.assertIn("Python (Working Knowledge)", content)
            self.assertIn("Newsletter Development", content)
            self.assertIn("Editorial Production", content)

    def test_styled_export_uses_template_when_present(self):
        result = export_styled_docx(MARKDOWN_RESUME, PROJECT_ROOT)

        self.assertEqual(
            result["template_path"],
            str(PROJECT_ROOT / "templates" / "docx" / "styled_resume_template.docx"),
        )

    def test_backward_compatible_cli_defaults_to_styled(self):
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["export-docx", MARKDOWN_RESUME])

        self.assertEqual(exit_code, 0)
        self.assertIn("Export mode: styled", output.getvalue())
        self.assertTrue(
            (
                PROJECT_ROOT
                / "exports"
                / "docx"
                / "TrishaLynch_DirectorEnterpriseStrategy_Crunchyroll_Styled.docx"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
