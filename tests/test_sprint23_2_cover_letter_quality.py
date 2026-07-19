import re
import shutil
from pathlib import Path

import pytest

from scripts.cover_letter_quality import (
    cover_letter_quality_pass,
    semantic_similarity,
)
from scripts.generate_cover_letter import generate_cover_letter
from scripts.package_generator import generate_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_JOBS = {
    "uta": "uta_director_people_operations.md",
    "youtube": "youtube_strategy_operations_associate.md",
}
GOLDEN_FILES = {
    "uta": "uta_people_operations.txt",
    "youtube": "youtube_strategy_operations.txt",
}


def _body_paragraphs(content: str) -> list[str]:
    paragraphs = [
        value.strip()
        for value in re.split(r"\n\s*\n", content.strip())
        if value.strip()
    ]
    return paragraphs[1:-2]


def _project_fixture(root: Path, key: str) -> tuple[Path, str]:
    shutil.copytree(ROOT / "config", root / "config")
    shutil.copytree(ROOT / "data", root / "data")
    (root / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    (root / "jobs").mkdir()
    filename = FIXTURE_JOBS[key]
    shutil.copy2(ROOT / "tests" / "fixtures" / "jobs" / filename, root / "jobs" / filename)
    return root, f"jobs/{filename}"


@pytest.fixture(scope="module")
def golden_outputs(tmp_path_factory):
    results = {}
    for key in FIXTURE_JOBS:
        root, job = _project_fixture(tmp_path_factory.mktemp(key), key)
        result = generate_cover_letter(job, root)
        results[key] = {
            "content": Path(result["output_path"]).read_text(encoding="utf-8"),
            "diagnostics": result["cover_letter_quality"],
            "word_count": result["word_count"],
        }
    return results


def test_exact_duplicate_sentence_is_removed():
    sentence = "I introduced usable standards that made ownership easier to understand."
    content = f"Hello,\n\nWhy this role matters.\n\n{sentence} {sentence}\n\nBest,\n\nTrisha Lynch"

    cleaned, diagnostics = cover_letter_quality_pass(content)

    assert cleaned.count(sentence) == 1
    assert diagnostics["duplicate_sentences_removed"] == [sentence]


def test_semantic_duplicate_google_youtube_claim_is_detected():
    first = (
        "I translated Google and YouTube platform capabilities into campaign activation, "
        "measurement readiness, and operational workflows for large advertisers."
    )
    second = (
        "I translated Google and YouTube advertising capabilities into campaign activation, "
        "measurement readiness, and operational workflows for large advertisers."
    )
    content = (
        f"Hello,\n\nWhy this role matters.\n\n{first}\n\n{second} Quality checks reduced "
        "handoff risk.\n\nA grounded approach to clear adoption would help.\n\nBest,\n\nTrisha Lynch"
    )

    cleaned, diagnostics = cover_letter_quality_pass(content, is_google_youtube=True)

    assert semantic_similarity(first, second) >= 0.78
    assert len(diagnostics["semantic_duplicates_detected"]) == 1
    assert cleaned.lower().count("translated google and youtube") == 1


def test_repeated_paragraph_opening_and_employer_aliases_are_normalized():
    content = (
        "Hello,\n\nAt OMG23 / OMD Entertainment, Omnicom Media Group, I led the work.\n\n"
        "At OMG23 / OMD Entertainment, I introduced quality checks.\n\nBest,\n\nTrisha Lynch"
    )

    cleaned, diagnostics = cover_letter_quality_pass(content)
    body = _body_paragraphs(cleaned)

    assert cleaned.count("OMG23 / Omnicom Media Group") == 1
    assert "OMD Entertainment" not in cleaned
    assert not all(paragraph.startswith("At OMG23") for paragraph in body)
    assert diagnostics["employer_names_normalized"] is True
    assert diagnostics["repeated_paragraph_openings"]


def test_repeated_first_person_sentence_opening_is_varied():
    content = (
        "Hello,\n\nI translated platform requirements into workflows. I translated stakeholder "
        "priorities into decision points.\n\nBest,\n\nTrisha Lynch"
    )

    cleaned, diagnostics = cover_letter_quality_pass(content)

    assert "The same approach translated stakeholder priorities" in cleaned
    assert diagnostics["repeated_sentence_openings"][0]["opening"] == "i translated"


def test_repeated_style_word_is_reduced_without_changing_evidence():
    content = (
        "Hello,\n\nA grounded view matters. The grounded evidence is useful. "
        "That grounded perspective supports the same verified work.\n\nBest,\n\nTrisha Lynch"
    )

    cleaned, diagnostics = cover_letter_quality_pass(content)

    assert cleaned.lower().count("grounded") == 1
    assert "same verified work" in cleaned
    assert diagnostics["repeated_words_flagged"][0]["word"] == "grounded"


def test_quality_pass_does_not_add_unsupported_claims_for_legacy_copy():
    content = (
        "Hello,\n\nThis role connects operating priorities with team decisions.\n\n"
        "I built workflows and quality standards across cross-functional teams.\n\n"
        "The work improved handoffs without changing the evidence boundary.\n\n"
        "I would bring a calm and useful perspective.\n\nBest,\n\nTrisha Lynch"
    )
    forbidden = ("owned employee relations", "owned google products", "led recruiting")

    cleaned, diagnostics = cover_letter_quality_pass(
        content, forbidden_phrases=forbidden
    )

    assert all(phrase not in cleaned.lower() for phrase in forbidden)
    assert diagnostics["unsupported_rewrite_rejected"] == []
    assert diagnostics["final_paragraph_count"] == 4


def test_quality_pass_rejects_a_rewrite_that_introduces_forbidden_language():
    content = (
        "Hello,\n\nWhy the role matters.\n\nI translated Google and YouTube platform "
        "capabilities into campaign activation and measurement workflows.\n\nI translated "
        "Google and YouTube advertising capabilities into campaign activation and measurement "
        "workflows. Quality checks made handoffs more dependable.\n\nA grounded approach to "
        "clear adoption would help.\n\nBest,\n\nTrisha Lynch"
    )

    cleaned, diagnostics = cover_letter_quality_pass(
        content,
        is_google_youtube=True,
        forbidden_phrases=("advertiser-side campaign context",),
    )

    assert "advertiser-side campaign context" not in cleaned
    assert diagnostics["unsupported_rewrite_rejected"] == [
        "advertiser-side campaign context"
    ]


def test_uta_golden_fixture_preserves_people_operations_boundary(golden_outputs):
    content = golden_outputs["uta"]["content"]
    expected = (
        ROOT / "tests" / "fixtures" / "cover_letters" / "golden" / GOLDEN_FILES["uta"]
    ).read_text(encoding="utf-8")

    assert content == expected
    assert "operations rather than a traditional HR function" not in content
    assert "ownership of employee relations, HR systems, or People policy" not in content
    assert "I bring a practical understanding of how change is adopted" in content
    assert not any(
        phrase in content.lower()
        for phrase in (
            "led people operations",
            "owned employee relations",
            "owned hris",
            "led payroll",
            "led recruiting",
        )
    )
    assert 250 <= golden_outputs["uta"]["word_count"] <= 350
    assert golden_outputs["uta"]["diagnostics"]["final_paragraph_count"] == 4


def test_youtube_golden_fixture_has_four_distinct_paragraphs(golden_outputs):
    content = golden_outputs["youtube"]["content"]
    expected = (
        ROOT
        / "tests"
        / "fixtures"
        / "cover_letters"
        / "golden"
        / GOLDEN_FILES["youtube"]
    ).read_text(encoding="utf-8")
    paragraphs = _body_paragraphs(content)

    assert content == expected
    assert len(paragraphs) == 4
    assert content.lower().count("translated google and youtube") == 1
    assert any(
        term in paragraphs[2].lower()
        for term in ("quality assurance", "handoffs", "execution risks", "feedback")
    )
    assert not any(
        left.startswith("At OMG23") and right.startswith("At OMG23")
        for left, right in zip(paragraphs, paragraphs[1:])
    )
    assert content.lower().count("grounded") <= 1
    assert "traditional hr" not in content.lower()
    assert all(
        semantic_similarity(left, right) < 0.78
        for index, left in enumerate(paragraphs)
        for right in paragraphs[index + 1 :]
    )
    assert golden_outputs["youtube"]["diagnostics"]["semantic_duplicates_detected"]
    assert 250 <= golden_outputs["youtube"]["word_count"] <= 350


@pytest.mark.parametrize("key", ("uta", "youtube"))
def test_package_generation_still_succeeds_for_golden_roles(tmp_path, key):
    root, job = _project_fixture(tmp_path / key, key)

    result = generate_package(job, root, generate_followups_too=False)

    assert result["tracker_id"]
    assert Path(result["outputs"]["cover_letter"]).is_file()
    assert result["role_lens"]
