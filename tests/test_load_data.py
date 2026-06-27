import tempfile
import unittest
from pathlib import Path

from scripts.load_data import (
    MalformedYamlError,
    MissingRequiredFileError,
    REQUIRED_CONFIG_FILES,
    REQUIRED_DATA_FILES,
    load_all_yaml,
    load_yaml_file,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LoadDataTests(unittest.TestCase):
    def test_required_yaml_files_can_be_loaded(self):
        loaded = load_all_yaml(PROJECT_ROOT)

        self.assertEqual(set(loaded["data"].keys()), {Path(path).stem for path in REQUIRED_DATA_FILES})
        self.assertEqual(set(loaded["config"].keys()), {Path(path).stem for path in REQUIRED_CONFIG_FILES})

    def test_loader_returns_dictionaries(self):
        loaded = load_all_yaml(PROJECT_ROOT)

        self.assertIsInstance(loaded, dict)
        self.assertIsInstance(loaded["data"], dict)
        self.assertIsInstance(loaded["config"], dict)

        for group in loaded.values():
            for yaml_data in group.values():
                self.assertIsInstance(yaml_data, dict)

    def test_canonical_platforms_file_is_required_and_loaded(self):
        loaded = load_all_yaml(PROJECT_ROOT)

        self.assertIn("data/platforms.yml", REQUIRED_DATA_FILES)
        self.assertIn("platforms", loaded["data"])
        self.assertIn("platform_categories", loaded["data"]["platforms"])

    def test_missing_file_error_is_handled_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(MissingRequiredFileError) as context:
                load_yaml_file("data/achievements.yml", Path(temp_dir))

        self.assertIn("Missing required YAML file: data/achievements.yml", str(context.exception))

    def test_malformed_yaml_error_is_handled_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "data"
            data_dir.mkdir()
            malformed_file = data_dir / "achievements.yml"
            malformed_file.write_text("achievements: [bad yaml", encoding="utf-8")

            with self.assertRaises(MalformedYamlError) as context:
                load_yaml_file("data/achievements.yml", temp_path)

        self.assertIn("Malformed YAML in data/achievements.yml", str(context.exception))


if __name__ == "__main__":
    unittest.main()
