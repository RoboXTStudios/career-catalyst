from scripts.evidence_tailoring import evidence_score_contribution


def test_score_explanation_when_no_requirements_match():
    result = evidence_score_contribution(
        {"match_score": 72},
        {"match_score": 72, "associated_evidence_matches": []},
    )
    assert result["explanation"] == (
        "No additional role requirements were matched by the selected Evidence."
    )


def test_score_explanation_when_requirements_match_without_score_change():
    result = evidence_score_contribution(
        {"match_score": 72},
        {
            "match_score": 72,
            "associated_evidence_matches": ["product", "content", "requirements"],
        },
    )
    assert result["explanation"] == (
        "Selected Evidence matched relevant role requirements but did not change the overall score."
    )


def test_score_explanation_when_requirements_raise_score():
    result = evidence_score_contribution(
        {"match_score": 72},
        {
            "match_score": 76,
            "associated_evidence_matches": ["product", "content", "requirements"],
        },
    )
    assert result["explanation"] == (
        "Selected Evidence matched additional verified role requirements."
    )
