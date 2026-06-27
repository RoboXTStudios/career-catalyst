import re
import unittest

from scripts.filename_utils import (
    build_upload_filename,
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

    def test_upload_filename_is_compact_and_safe(self):
        filename = build_upload_filename(
            "Trisha Lynch",
            "Head of Global Creative and Product Development Operations",
            "Sony Interactive Entertainment / PlayStation",
            "Cover Letter",
            ".md",
        )

        self.assertEqual(
            filename,
            "TrishaLynch_HeadGlobalCreativeOps_PlayStation_CoverLetter.md",
        )
        self.assertIsNone(re.search(r"[/,()&\s]", filename))


if __name__ == "__main__":
    unittest.main()
