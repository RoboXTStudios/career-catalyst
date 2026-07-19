from copy import deepcopy
from pathlib import Path

import app
from scripts.application_strategy import build_application_strategy, build_hiring_manager_lens
from scripts.evidence_profile import evidence_as_card
from scripts.hiring_manager_brief import (
    brief_card_summary,
    build_hiring_manager_brief,
    default_brief_contains_internal_language,
)
from scripts.role_evidence_selection import selected_evidence
from scripts.score_match import score_job_match


ROOT = Path(__file__).resolve().parents[1]
REDDIT_JOB = "tests/fixtures/jobs/reddit_manager_technical_solutions.md"
UTA_JOB = "tests/fixtures/jobs/uta_director_people_operations.md"


def _analysis(job=REDDIT_JOB):
    report = score_job_match(job, ROOT)
    interpretation = report["role_interpretation"]
    selection = report["role_evidence_selection"]
    lens = build_hiring_manager_lens(
        interpretation,
        report["capability_graph"]["alignment_matrix"],
        report["evidence_gap_analysis"],
    )
    strategy = build_application_strategy(
        interpretation,
        lens,
        report,
        [evidence_as_card(item) for item in selected_evidence(selection)],
    )
    return report, selection, lens, strategy


def _brief(job=REDDIT_JOB):
    return build_hiring_manager_brief(*_analysis(job))


def test_analyzed_prospect_payload_persists_hiring_manager_brief(monkeypatch, tmp_path):
    from scripts import prospect_intake

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    report, _selection, _lens, _strategy = _analysis()
    captured = {}

    def fake_score(*_args, **_kwargs):
        return deepcopy(report)

    def fake_add(values, _root):
        captured.update(values)
        return {"created": True, "application": deepcopy(values)}

    monkeypatch.setattr(prospect_intake, "score_job_data", fake_score)
    monkeypatch.setattr(prospect_intake, "add_prospect", fake_add)
    result = prospect_intake.create_prospect(
        {
            "company": "Example",
            "job_title": "Manager, Technical Solutions",
            "job_description": (ROOT / REDDIT_JOB).read_text(encoding="utf-8"),
            "official_url": "https://example.com/jobs/technical-solutions",
        },
        tmp_path,
    )

    assert result["application"]["hiring_manager_brief"]
    assert captured["hiring_manager_brief_dirty"] is False
    assert captured["hiring_manager_brief"]["grounding"]["selected_evidence_ids"] == report[
        "role_evidence_selection"
    ]["selected_evidence_ids"]


def test_brief_is_grounded_in_exact_selected_verified_experience():
    report, selection, lens, strategy = _analysis()
    brief = build_hiring_manager_brief(report, selection, lens, strategy)

    assert brief["grounding"]["selected_evidence_ids"] == selection[
        "selected_evidence_ids"
    ]
    assert brief["grounding"]["selected_evidence_count"] == len(
        selected_evidence(selection)
    )
    assert 3 <= len(brief["why_match"]) <= 5
    assert all(item["explanation"] for item in brief["why_match"])


def test_default_brief_has_no_internal_system_terminology():
    brief = _brief()
    visible = " ".join(
        [
            brief["match_recommendation"],
            brief["match_summary"],
            *(item["heading"] + " " + item["explanation"] for item in brief["why_match"]),
            *brief["what_to_emphasize"],
            *brief["what_to_discuss"],
        ]
    ).lower()

    assert default_brief_contains_internal_language(brief) == []
    for term in (
        "evidence id",
        "capability id",
        "capability graph",
        "primary evidence",
        "supporting evidence",
        "adjacent",
        "transferable",
        "derivation type",
        "provenance",
        "confidence calculation",
    ):
        assert term not in visible


def test_genuine_gaps_are_candid_without_becoming_rejection_arguments():
    brief = _brief(UTA_JOB)
    discussion = " ".join(brief["what_to_discuss"]).lower()

    assert brief["what_to_discuss"]
    assert len(brief["what_to_discuss"]) <= 3
    assert "you lack" not in discussion
    assert "therefore may not qualify" not in discussion
    assert "prepare" in discussion or "should be weighed" in discussion


def test_recommendation_thresholds_respect_hard_requirement_gaps():
    strong_report = {
        "match_score": 92,
        "match_summary": "Strong alignment.",
        "capability_graph": {"alignment_matrix": []},
    }
    hard_gap_report = deepcopy(strong_report)
    hard_gap_report["capability_graph"]["alignment_matrix"] = [
        {
            "requirement": "Active license required",
            "requirement_type": "Hard Gate",
            "alignment_level": "Unsupported",
        }
    ]
    selection = {"selected_evidence_ids": [], "primary_evidence": [], "supporting_evidence": []}

    assert build_hiring_manager_brief(strong_report, selection)["recommendation"] == "Apply Immediately"
    assert build_hiring_manager_brief(hard_gap_report, selection)["recommendation"] == "Consider"
    low_report = {"match_score": 40, "capability_graph": {"alignment_matrix": []}}
    assert build_hiring_manager_brief(low_report, selection)["recommendation"] == "Probably Skip"


class _Container:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _BriefStreamlit:
    def __init__(self, state=None):
        self.session_state = dict(state or {})
        self.markdown_values = []

    def container(self, **_kwargs):
        return _Container()

    def markdown(self, value, **_kwargs):
        self.markdown_values.append(str(value))

    def write(self, value):
        self.markdown_values.append(str(value))

    def caption(self, value):
        self.markdown_values.append(str(value))

    def info(self, value):
        self.markdown_values.append(str(value))

    def button(self, *_args, **_kwargs):
        return False


def test_passive_brief_render_does_not_call_model_or_load_full_graph(monkeypatch):
    st = _BriefStreamlit()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("passive rendering called analysis or hydrated advanced data")

    monkeypatch.setattr(app, "get_effective_voice_profile", forbidden)
    monkeypatch.setattr(app, "load_cached_evidence_profile", forbidden)
    monkeypatch.setattr(app, "load_cached_capability_graph", forbidden)
    monkeypatch.setattr(app, "_render_role_interpretation", forbidden)
    monkeypatch.setattr(app, "_render_role_evidence_selection", forbidden)

    app._render_intelligence_preview(
        st,
        {"hiring_manager_brief": _brief()},
        evidence_tracker_id="prospect",
    )

    rendered = " ".join(st.markdown_values)
    assert "Hiring Manager Brief" in rendered
    assert "How Career Catalyst Reached This Conclusion" not in rendered


def test_advanced_explanation_is_available_only_after_explicit_open(monkeypatch):
    calls = []
    st = _BriefStreamlit({"advanced_conclusion_prospect": True})

    monkeypatch.setattr(app, "_render_prospect_validation", lambda *_args: calls.append("validation"))
    monkeypatch.setattr(app, "_render_role_interpretation", lambda *_args, **_kwargs: calls.append("interpretation"))
    monkeypatch.setattr(app, "_render_role_evidence_selection", lambda *_args, **_kwargs: calls.append("evidence"))
    monkeypatch.setattr(app, "_render_application_strategy", lambda *_args: calls.append("strategy"))

    app._render_intelligence_preview(
        st,
        {"hiring_manager_brief": _brief()},
        evidence_tracker_id="prospect",
    )

    assert {"validation", "interpretation", "evidence", "strategy"} <= set(calls)


def test_dashboard_summary_uses_persisted_brief_without_full_analysis():
    brief = _brief()
    summary = brief_card_summary(
        {
            "company": "Reddit",
            "role": "Manager, Technical Solutions",
            "hiring_manager_brief": brief,
            "match_score": 1,
        }
    )

    assert summary["match_recommendation"] == brief["match_recommendation"]
    assert summary["reason"] == brief["match_summary"]
    assert summary["next_action"] == brief["recommended_next_step"]


def test_advanced_data_and_manual_overrides_remain_intact():
    report, selection, lens, strategy = _analysis()
    original = deepcopy(selection)
    selection["overrides"] = {
        "manual_additions": ["people_leadership"],
        "manual_exclusions": ["technical_troubleshooting"],
        "manual_priority_overrides": {"people_leadership": "Primary"},
    }
    brief = build_hiring_manager_brief(report, selection, lens, strategy)

    assert brief["advanced"]["manual_overrides"] == selection["overrides"]
    assert original["automatic_selection"] == selection["automatic_selection"]
    assert brief["advanced"]["relevant_capabilities"] == selection[
        "important_capabilities"
    ]


def test_career_intelligence_and_advanced_library_are_summary_first():
    source = Path(app.__file__).read_text(encoding="utf-8")
    start = source.index("def _render_evidence_explorer")
    page = source[start : source.index("\n\nUI_PAGES", start)]

    assert 'st.subheader("Career Intelligence")' in page
    assert '"### Career Profile"' in page
    assert '"### Strongest Areas"' in page
    assert '"### Featured Projects and Experience"' in page
    assert '"Open Advanced Library"' in page
    assert page.index("if st.session_state.get(open_key, False):") < page.index(
        "_render_full_evidence_library(st)"
    )
