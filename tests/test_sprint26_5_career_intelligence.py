from pathlib import Path


def test_career_intelligence_helper_text_is_visible_and_non_mutating():
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "Career Intelligence helps you explore patterns across experience, applications, strengths, and gaps" in app_source
    assert "Filters on this page only change what you see here" in app_source
    assert "they do not control ATS resumes, cover letters" in app_source
    assert "Relevant Evidence section" in app_source
