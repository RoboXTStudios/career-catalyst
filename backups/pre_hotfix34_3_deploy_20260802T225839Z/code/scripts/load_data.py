"""Load and validate Career Catalyst YAML source files."""

from pathlib import Path
from typing import Any, Optional, Union

import yaml


REQUIRED_DATA_FILES = (
    "data/achievements.yml",
    "data/positions.yml",
    "data/skills.yml",
    "data/platforms.yml",
    "data/projects.yml",
    "data/evidence_projects.yml",
    "data/certifications.yml",
    "data/personal_brand.yml",
)

REQUIRED_CONFIG_FILES = (
    "config/settings.yml",
    "config/target_companies.yml",
    "config/role_profiles.yml",
    "config/voice.yml",
    "config/company_voice_profiles.yml",
)

REQUIRED_YAML_FILES = REQUIRED_DATA_FILES + REQUIRED_CONFIG_FILES


class DataLoadError(Exception):
    """Base exception for YAML loading and validation errors."""


class MissingRequiredFileError(DataLoadError):
    """Raised when a required YAML file is missing."""

    def __init__(self, relative_path: str) -> None:
        super().__init__(f"Missing required YAML file: {relative_path}")
        self.relative_path = relative_path


class MalformedYamlError(DataLoadError):
    """Raised when a YAML file cannot be parsed."""

    def __init__(self, relative_path: str, original_error: Exception) -> None:
        super().__init__(f"Malformed YAML in {relative_path}: {original_error}")
        self.relative_path = relative_path


class InvalidYamlStructureError(DataLoadError):
    """Raised when YAML parses but does not produce a dictionary."""

    def __init__(self, relative_path: str) -> None:
        super().__init__(f"YAML file must contain a top-level dictionary: {relative_path}")
        self.relative_path = relative_path


ProjectRoot = Optional[Union[str, Path]]


def _project_root(project_root: ProjectRoot = None) -> Path:
    return Path(project_root) if project_root is not None else Path.cwd()


def _key_from_relative_path(relative_path: str) -> str:
    return Path(relative_path).stem


def load_yaml_file(relative_path: str, project_root: ProjectRoot = None) -> dict[str, Any]:
    """Load one YAML file from the project root and return its dictionary content."""
    root = _project_root(project_root)
    file_path = root / relative_path

    if not file_path.is_file():
        raise MissingRequiredFileError(relative_path)

    try:
        with file_path.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file)
    except yaml.YAMLError as error:
        raise MalformedYamlError(relative_path, error) from error
    except OSError as error:
        raise DataLoadError(f"Unable to read YAML file {relative_path}: {error}") from error

    if not isinstance(loaded, dict):
        raise InvalidYamlStructureError(relative_path)

    return loaded


def load_data_files(project_root: ProjectRoot = None) -> dict[str, dict[str, Any]]:
    """Load all required files from the data folder."""
    return {
        _key_from_relative_path(relative_path): load_yaml_file(relative_path, project_root)
        for relative_path in REQUIRED_DATA_FILES
    }


def load_config_files(project_root: ProjectRoot = None) -> dict[str, dict[str, Any]]:
    """Load all required files from the config folder."""
    return {
        _key_from_relative_path(relative_path): load_yaml_file(relative_path, project_root)
        for relative_path in REQUIRED_CONFIG_FILES
    }


def load_all_yaml(project_root: ProjectRoot = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Load all required Career Catalyst YAML files."""
    return {
        "data": load_data_files(project_root),
        "config": load_config_files(project_root),
    }
