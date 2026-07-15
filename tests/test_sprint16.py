import shutil
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import app
from scripts.application_tracker import add_prospect, load_application_tracker
from scripts.generate_cover_letter import generate_cover_letter
from scripts.generate_dashboard import _asset_label, _attach_assets
from scripts.job_source_registry import classify_source, normalize_job_source
from scripts.package_materials import validate_package_outputs
from scripts.package_generator import _safe_docx_export, generate_package
from scripts.score_match import score_job_data
from tests.test_sprint15_4 import _FakeStreamlit, _record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AEG_URL = (
    "https://aegworldwide.com/careers/jobs/AXSDG9363/"
    "sr.-technical-project-manager?gh_jid=8606676002"
)
COMPLETE_DESCRIPTION = (
    "Lead technical project delivery across business and engineering teams. Own requirements, "
    "timelines, dependencies, QA governance, stakeholder reporting, campaign systems, and "
    "operational risk through launch and measurement handoffs."
)


class Sprint16SourceAndScoringTests(unittest.TestCase):
    def test_aeg_official_url_is_direct_employer_with_greenhouse_hint(self):
        classified = classify_source(AEG_URL)
        self.assertEqual(classified["display_name"], "AEG Worldwide Careers")
        self.assertEqual(classified["source_type"], "Direct Employer")

        normalized = normalize_job_source(
            {"official_url": AEG_URL, "company": "AEG Worldwide / AXS"}
        )
        self.assertEqual(normalized["source_trust_label"], "Direct Employer")
        self.assertEqual(normalized["verification_status"], "Employer Source")
        self.assertEqual(normalized["canonical_apply_url"], AEG_URL)
        self.assertEqual(normalized["greenhouse_job_id"], "8606676002")
        self.assertTrue(normalized["greenhouse_backed_hint"])
        self.assertFalse(normalized["requires_verification"])
        self.assertEqual(normalized["freshness_risk"], "Unknown")
        self.assertIn("Official employer source detected", normalized["recommended_next_step"])

    def test_aeg_partial_import_message_preserves_official_source(self):
        preview = app.import_failure_preview(AEG_URL, "page blocked")
        self.assertEqual(preview["verification"]["source_type"], "Direct Employer")
        self.assertIn("Import partially failed", preview["message"])
        self.assertIn("re-parse and re-score", preview["message"])

    def test_missing_required_fields_are_not_scored_or_passed(self):
        fixtures = (
            {"job_title": "Director", "job_description": COMPLETE_DESCRIPTION},
            {"company": "Acme", "job_description": COMPLETE_DESCRIPTION},
            {"company": "Acme", "job_title": "Director", "job_description": "Short"},
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                report = score_job_data(fixture, PROJECT_ROOT)
                self.assertIsNone(report["match_score"])
                self.assertEqual(report["match_tier"], "Not scored")
                self.assertEqual(
                    report["recommended_action"],
                    "Complete Import / Paste Job Description",
                )
                self.assertNotEqual(report["recommended_action"], "Pass")

    def test_complete_manual_fields_can_be_reparsed_and_scored(self):
        refreshed = app.reparse_prospect_fields(
            {
                "official_url": AEG_URL,
                "company": "AEG Worldwide / AXS",
                "job_title": "Sr. Technical Project Manager",
                "job_description": COMPLETE_DESCRIPTION,
            }
        )
        self.assertIsInstance(refreshed["match_report"]["match_score"], int)
        self.assertFalse(refreshed["match_report"].get("incomplete_import", False))


class Sprint16PackageMaterialTests(unittest.TestCase):
    def test_checklist_prefers_docx_and_marks_missing_without_active_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cover_md = root / "cover.md"
            cover_docx = root / "cover.docx"
            ats_docx = root / "ats.docx"
            cover_md.write_text("cover", encoding="utf-8")
            cover_docx.write_bytes(b"docx")
            ats_docx.write_bytes(b"docx")
            checklist = validate_package_outputs(
                {
                    "cover_letter": str(cover_md),
                    "cover_letter_docx": str(cover_docx),
                    "ats_docx": str(ats_docx),
                }
            )
            by_type = {item["material_type"]: item for item in checklist}
            self.assertEqual(by_type["Cover Letter"]["preferred_open_path"], str(cover_docx))
            self.assertEqual(by_type["ATS Resume"]["preferred_open_path"], str(ats_docx))
            self.assertFalse(by_type["Recruiter Message"]["exists"])
            self.assertIsNone(by_type["Recruiter Message"]["preferred_open_path"])
            self.assertEqual(
                by_type["Recruiter Message"]["missing_reason"],
                "Missing / not generated",
            )
            self.assertEqual(
                by_type["PDF Resume"]["missing_reason"],
                "PDF not generated / unsupported",
            )

    def test_docx_export_failure_is_nonfatal_and_reportable(self):
        def unavailable(*_args):
            raise RuntimeError("python-docx unavailable")

        result = _safe_docx_export(
            unavailable, "resume.md", Path("."), "ATS resume DOCX"
        )
        self.assertIn("missing / unsupported", result["error"])
        checklist = validate_package_outputs(
            {}, {"ats_docx": result["error"]}
        )
        ats = next(item for item in checklist if item["material_type"] == "ATS Resume")
        self.assertFalse(ats["exists"])
        self.assertIn("missing / unsupported", ats["missing_reason"])

    def test_dashboard_asset_lookup_prefers_user_facing_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            messages = root / "exports" / "messages"
            messages.mkdir(parents=True)
            md = messages / "TrishaLynch_SrTechnicalProjectManager_AegWorldwideAxs_CoverLetter.md"
            docx = md.with_suffix(".docx")
            md.write_text("markdown", encoding="utf-8")
            docx.write_bytes(b"docx")
            package = {
                "company": "AEG Worldwide / AXS",
                "role": "Sr. Technical Project Manager",
                "tracker": {"id": "aeg-tpm"},
                "files": {},
            }
            self.assertEqual(_asset_label(docx), "Cover Letter DOCX")
            _attach_assets(root, [package])
            self.assertEqual(package["files"]["Cover Letter DOCX"], docx)
            self.assertEqual(package["files"]["Cover Letter"], md)

    def test_open_materials_from_todays_focus_opens_existing_material(self):
        with tempfile.TemporaryDirectory() as temporary:
            material = Path(temporary) / "recruiter_message.txt"
            material.write_text("message", encoding="utf-8")
            record = _record(_material_paths={"Recruiter Message": str(material)})
            st = _FakeStreamlit(clicks={"next_materials_stable-role"})
            with patch.object(app, "_render_role_card") as render_role, patch.object(
                app, "open_local_path", return_value=(True, str(material))
            ) as open_path:
                app._render_recommended_next_steps(
                    st, [record], "All Mode", {}, focus_records=[record]
                )
            self.assertNotIn("dashboard_focused_role_id", st.session_state)
            render_role.assert_not_called()
            open_path.assert_called_once_with(material.resolve(), app.PROJECT_ROOT)

    def test_package_generation_persists_only_verified_material_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "jobs").mkdir()
            (root / "exports").mkdir()
            (root / "data" / "application_tracker.yml").write_text(
                "applications: []\n", encoding="utf-8"
            )
            job_path = root / "jobs" / "aeg.md"
            job_path.write_text(
                "# Sr. Technical Project Manager\n\nCompany: AEG Worldwide / AXS\n"
                "Tracker ID: aeg-tpm\n\n## Job Description\n\n"
                + COMPLETE_DESCRIPTION,
                encoding="utf-8",
            )
            add_prospect(
                {
                    "id": "aeg-tpm",
                    "company": "AEG Worldwide / AXS",
                    "role": "Sr. Technical Project Manager",
                    "status": "Drafted",
                    "priority": "High",
                    "show_on_dashboard": True,
                    "job_file": "jobs/aeg.md",
                },
                root,
            )

            def material(name, suffix=".md"):
                path = root / "exports" / f"{name}{suffix}"
                path.write_text(name, encoding="utf-8")
                return {"output_path": str(path)}

            resume = material("resume")
            styled = material("styled", ".docx")
            ats = material("ats", ".docx")
            cover = material("cover")
            cover["txt_output_path"] = material("cover", ".txt")["output_path"]
            cover["docx_output_path"] = material("cover", ".docx")["output_path"]
            recruiter = material("recruiter")
            recruiter["txt_output_path"] = material("recruiter", ".txt")["output_path"]
            manager = material("manager")
            manager["txt_output_path"] = material("manager", ".txt")["output_path"]
            note = material("note")
            note["txt_output_path"] = material("note", ".txt")["output_path"]
            strategy = material("strategy")
            interview = material("interview")
            summary = material("summary")
            dashboard = material("dashboard", ".html")

            parsed = {
                "job_title": "Sr. Technical Project Manager",
                "company": "AEG Worldwide / AXS",
                "raw_text": COMPLETE_DESCRIPTION,
            }
            intelligence = {
                "company_category": "entertainment_media",
                "role_family": "business_operations",
                "profile_name": "default",
                "source": "dynamic_inference",
                "company_voice_label": "Entertainment",
                "confidence_label": "High",
            }
            freshness = {
                "is_closed": False,
                "category": "Unknown Freshness",
                "label": "Unknown freshness / Verify manually",
                "posting_status": "Verify manually",
                "posting_date": None,
                "age_days": None,
            }
            score = {
                "match_score": 88,
                "match_band": "Strong",
                "match_tier": "Strong Match",
                "match_summary": "Strong fit.",
                "match_strengths": ["Delivery", "Systems", "Stakeholders"],
                "match_gaps": ["Verify posting freshness."],
                "recommended_action": "Generate Package",
                "confidence": "High",
            }
            opportunity = {
                "overall_score": 85,
                "apply_recommendation": "Apply",
                "dimensions": {"fit": 85},
            }
            quality = {
                "resume_tailoring_score": 90,
                "cover_letter_score": 90,
                "ats_keyword_match": 90,
                "voice_match": 90,
                "confidence_level": "High",
            }
            with ExitStack() as stack:
                for target, value in (
                    ("scripts.package_generator.parse_job_description", parsed),
                    ("scripts.package_generator.get_effective_voice_profile", intelligence),
                    ("scripts.package_generator.detect_job_freshness", freshness),
                    ("scripts.package_generator.score_job_match", score),
                    ("scripts.package_generator.score_opportunity", opportunity),
                    ("scripts.package_generator.tailor_resume", resume),
                    ("scripts.package_generator.export_styled_docx", styled),
                    ("scripts.package_generator.export_ats_docx", ats),
                    ("scripts.package_generator.generate_cover_letter", cover),
                    ("scripts.package_generator.generate_application_note", note),
                    ("scripts.package_generator.generate_strategy_pack", strategy),
                    ("scripts.package_generator.generate_interview_prep", interview),
                    ("scripts.package_generator.calculate_package_quality", quality),
                    ("scripts.package_generator.save_package_summary", summary),
                    ("scripts.package_generator.generate_dashboard", dashboard),
                ):
                    stack.enter_context(patch(target, return_value=value))
                stack.enter_context(
                    patch(
                        "scripts.package_generator.generate_message",
                        side_effect=(recruiter, manager),
                    )
                )
                result = generate_package(
                    "aeg-tpm", root, generate_followups_too=False
                )

            checklist = {
                item["material_type"]: item for item in result["package_checklist"]
            }
            self.assertTrue(checklist["ATS Resume"]["exists"])
            ats_path = Path(checklist["ATS Resume"]["preferred_open_path"])
            self.assertEqual(ats_path.name, "ats_resume.docx")
            self.assertIn("exports/active/in_progress/aeg_tpm", ats_path.as_posix())
            tracker = load_application_tracker(root)[0]
            self.assertEqual(
                tracker["material_paths"]["ATS Resume"], str(ats_path)
            )
            self.assertNotIn("Recruiter Follow-Up", tracker["material_paths"])


class Sprint16CoverLetterTests(unittest.TestCase):
    def test_aeg_tpm_cover_letter_is_role_specific_and_generates_docx_txt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in ("data", "config"):
                shutil.copytree(PROJECT_ROOT / directory, root / directory)
            (root / "jobs").mkdir()
            shutil.copy2(
                PROJECT_ROOT / "jobs" / "sr_technical_project_manager_aeg_worldwide_axs.md",
                root / "jobs" / "aeg_tpm.md",
            )
            result = generate_cover_letter("jobs/aeg_tpm.md", root)
            content = Path(result["output_path"]).read_text(encoding="utf-8")
            lowered = content.lower()
            self.assertTrue(Path(result["txt_output_path"]).is_file())
            self.assertTrue(Path(result["docx_output_path"]).is_file())
            for expected in ("requirements", "dependencies", "qa", "technical", "operational risk"):
                self.assertIn(expected, lowered)
            for excluded in ("multiverse", "substack", "editorial projects"):
                self.assertNotIn(excluded, lowered)
            body_paragraphs = [
                paragraph.strip()
                for paragraph in content.split("\n\n")
                if paragraph.strip() not in {"Hello,", "Best,", "Trisha Lynch"}
                and not paragraph.strip().startswith("Best,")
            ]
            self.assertEqual(len(body_paragraphs), 4)


if __name__ == "__main__":
    unittest.main()
