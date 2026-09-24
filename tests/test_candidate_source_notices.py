from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

from scripts.resume_foundation import (
    CandidateLanguageError,
    candidate_source_notices,
    load_resume_foundation,
)


ROOT = Path(__file__).resolve().parents[1]
# The user's live runtime; tests only ever read it into a temporary copy.
REAL_RUNTIME = Path.home() / "Library" / "Application Support" / "Career Catalyst" / "runtime"


def _copy_runtime(source: Path, tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    for name in ("data", "config"):
        shutil.copytree(source / name, root / name)
    return root


def _set_first_evidence_results(root: Path, results: str, title_contains: str | None = None) -> str:
    path = root / "data" / "evidence_projects.yml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    projects = payload["evidence_projects"]
    project = next(
        (p for p in projects if title_contains and title_contains in str(p.get("title"))),
        next(p for p in projects if str(p.get("status") or "Active") == "Active"),
    )
    project["results"] = results
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    return str(project["title"])


def _assert_flagged_not_fatal(root: Path, title: str) -> None:
    load_resume_foundation(root)  # must not raise
    notices = candidate_source_notices(root)
    assert any(title in notice and "(results)" in notice and "over a decade" in notice for notice in notices), notices


def test_age_wording_in_repo_source_is_flagged_not_fatal(tmp_path: Path):
    root = _copy_runtime(ROOT, tmp_path)
    title = _set_first_evidence_results(root, "Delivered campaign operations for the full slate over a decade.")
    _assert_flagged_not_fatal(root, title)


def test_unsupported_brand_claims_still_fail_the_load(tmp_path: Path):
    root = _copy_runtime(ROOT, tmp_path)
    _set_first_evidence_results(root, "Led campaigns for National Geographic.")
    with pytest.raises(CandidateLanguageError, match="National Geographic"):
        load_resume_foundation(root)


@pytest.mark.skipif(not (REAL_RUNTIME / "data" / "evidence_projects.yml").is_file(), reason="no local runtime")
def test_real_candidate_source_with_original_theatrical_wording_is_flagged_not_fatal(tmp_path: Path):
    real_file = REAL_RUNTIME / "data" / "evidence_projects.yml"
    before = hashlib.sha256(real_file.read_bytes()).hexdigest()
    root = _copy_runtime(REAL_RUNTIME, tmp_path)
    load_resume_foundation(root)
    title = _set_first_evidence_results(
        root,
        "Delivered campaign operations for the full Disney Studios theatrical and Home Entertainment slate "
        "over a decade. Managed budgets that ranged from about $5M to about $25M per title across all Disney IPs.",
        title_contains="Theatrical",
    )
    _assert_flagged_not_fatal(root, title)
    # The real source itself is untouched by the test.
    assert hashlib.sha256(real_file.read_bytes()).hexdigest() == before
