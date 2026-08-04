"""Deterministic, posting-grounded career and interview intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

try:
    from .candidate_output import humanize_values, validate_candidate_output
    from .career_claims import validate_public_career_claims
    from .filename_utils import build_upload_filename
    from .generate_cover_letter import load_generation_context
    from .package_context import validate_material_context
    from .text_cleanup import normalize_candidate_text
except ImportError:  # pragma: no cover
    from candidate_output import humanize_values, validate_candidate_output
    from career_claims import validate_public_career_claims
    from filename_utils import build_upload_filename
    from generate_cover_letter import load_generation_context
    from package_context import validate_material_context
    from text_cleanup import normalize_candidate_text


PathInput = Union[str, Path]
INFERENCE_NOTICE = "These are posting-based inferences, not verified internal company information."


def _evidence_catalogue() -> list[Dict[str, str]]:
    return [
        {
            "id": "integrated_leadership",
            "label": "Integrated operational leadership",
            "description": "Led 10 direct reports and provided strategic and operational leadership across an integrated 64-person organization.",
        },
        {
            "id": "workflow_governance",
            "label": "Workflow governance and Airtable adoption",
            "description": "Translated leadership priorities into operating plans, workflow governance, training, adoption, and clearer execution across stakeholders.",
        },
        {
            "id": "disney_plus_launch_support",
            "label": "Disney+ launch support",
            "description": "Supported Disney+ launch readiness through cross-functional platform coordination, quality assurance, measurement readiness, and execution workflows.",
        },
        {
            "id": "career_catalyst",
            "label": "Career Catalyst product development",
            "description": "Built and iterated an active, tested system that turns job, evidence, and workflow requirements into reliable candidate-facing outputs.",
        },
        {
            "id": "campaignos_working_prototype",
            "label": "CampaignOS working prototype",
            "description": "Designed a working prototype for AI-powered campaign operations focused on readiness, governance, validation, reporting, and operational risk detection.",
        },
    ]


def _posting_signals(parsed: Dict[str, Any]) -> Dict[str, bool]:
    text = " ".join(
        str(parsed.get(key) or "")
        for key in ("job_title", "raw_text", "job_description", "summary", "keywords")
    ).lower()
    return {
        "product": any(word in text for word in ("product", "roadmap", "user needs", "customer needs")),
        "strategy": any(word in text for word in ("strategy", "strategic", "roadmap", "vision")),
        "prioritization": any(word in text for word in ("priorit", "tradeoff", "trade-off", "portfolio")),
        "delivery": any(word in text for word in ("launch", "delivery", "execution", "adoption", "readiness")),
        "stakeholders": any(word in text for word in ("stakeholder", "cross-functional", "cross functional", "partner")),
        "measurement": any(word in text for word in ("metric", "measure", "analytics", "data", "kpi", "outcome")),
    }


def _question(
    question: str,
    testing: str,
    answer_direction: str,
    evidence: Iterable[Dict[str, str]],
    caution: str,
) -> Dict[str, Any]:
    return {
        "question": question,
        "testing": testing,
        "answer_direction": answer_direction,
        "evidence": [item["label"] for item in evidence],
        "evidence_ids": [item["id"] for item in evidence],
        "caution": caution,
    }


def _render(result: Dict[str, Any]) -> str:
    lines = [
        "# Career Intelligence and Interview Prep",
        "",
        f"## {result['role']} at {result['company']}",
        "",
        f"> {result['inference_notice']}",
        "",
        "## What the hiring manager is likely hiring for",
        "",
        *(f"- {item}" for item in result["hiring_manager_intent"]),
        "",
        "## Likely First-Screen Priorities",
        "",
        *(f"- {item}" for item in result["first_screen_priorities"]),
        "",
        "## Likely Interview Questions",
        "",
    ]
    for group in result["question_groups"]:
        lines.extend((f"### {group['category']}", ""))
        for item in group["questions"]:
            lines.extend(
                (
                    f"**{item['question']}**",
                    "",
                    f"- What they are testing: {item['testing']}",
                    f"- Answer direction: {item['answer_direction']}",
                    f"- Best verified evidence: {', '.join(item['evidence'])}",
                    f"- Caution: {item['caution']}",
                    "",
                )
            )
    lines.extend(("## Best Evidence and STAR Stories", ""))
    lines.extend(
        f"- **{item['label']}**: {item['description']}"
        for item in result["best_evidence"]
    )
    lines.extend(("", "## Likely Concerns or Gaps", ""))
    lines.extend(
        f"- **Concern:** {item['concern']}  \n  **Bridge:** {item['bridge']}"
        for item in result["concerns_and_bridges"]
    )
    lines.extend(("", "## Questions Trisha Should Ask", ""))
    lines.extend(f"- {item}" for item in result["questions_to_ask"])
    lines.extend(
        (
            "",
            "## Tell Me About Yourself",
            "",
            result["tell_me_about_yourself"],
            "",
            "## Why This Company / Why This Role",
            "",
            result["why_company_role"],
            "",
            "## First 90-Day Themes",
            "",
            *(f"- {item}" for item in result["first_90_day_themes"]),
        )
    )
    if result.get("user_supplied_context"):
        lines.extend(
            (
                "",
                "## User-Supplied Context (not independently verified)",
                "",
                result["user_supplied_context"],
            )
        )
    lines.extend(("", "## Voice Reminder", "", result["voice_reminder"], ""))
    return "\n".join(lines)


def generate_career_intelligence(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    role_intent: Optional[Dict[str, Any]] = None,
    *,
    additional_context: str = "",
    associated_evidence_projects: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate structured and readable interview preparation from saved sources."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    context = load_generation_context(job_path, root, role_intent=role_intent)
    parsed = context["parsed_job"]
    company = str(parsed.get("company") or "the company")
    role = str(parsed.get("job_title") or "the role")
    signals = _posting_signals(parsed)
    extra_projects = list(associated_evidence_projects or [])
    campaignos_selected = any(
        str(project.get("id") or project.get("name") or project.get("title") or "").lower()
        == "campaignos"
        for project in extra_projects
    )
    evidence = [
        item
        for item in _evidence_catalogue()
        if campaignos_selected or item["id"] != "campaignos_working_prototype"
    ]
    project_evidence = []
    for project in extra_projects[:3]:
        label = str(project.get("title") or project.get("name") or "").strip()
        description = str(project.get("results") or project.get("summary") or "").strip()
        project_id = str(project.get("id") or "").strip()
        if label and description and project_id:
            item = {"id": project_id, "label": label, "description": description}
            evidence.append(item)
            project_evidence.append(item)

    intents = [
        "Turn ambiguous business and user needs into clear priorities and practical decisions.",
        "Create alignment across product, technology, analytics, operations, and business stakeholders.",
        "Balance near-term delivery with durable operating clarity and measurable outcomes.",
    ]
    if signals["product"]:
        intents.insert(0, "Exercise product judgment across strategy, roadmap choices, prioritization, and tradeoffs.")
    if signals["delivery"]:
        intents.append("Guide launch, readiness, adoption, and follow-through across dependent teams.")
    if signals["measurement"]:
        intents.append("Use evidence and measurement to clarify decisions and assess progress.")

    groups = []
    if signals["product"] or signals["strategy"]:
        groups.append(
            {
                "category": "Strategy and product judgment",
                "questions": [
                    _question(
                        "How do you turn a broad product or business need into a clear direction?",
                        "Product judgment, problem framing, and disciplined choice-making.",
                        "Describe how you clarify the user and business need, define decision criteria, surface tradeoffs, and align stakeholders before committing to a path.",
                        (evidence[3], evidence[1]),
                        (
                            "Frame Career Catalyst as active product development and CampaignOS only as a working prototype; keep prior title history precise."
                            if campaignos_selected
                            else "Frame Career Catalyst as active product development; keep prior title history precise."
                        ),
                    )
                ],
            }
        )
    if signals["prioritization"] or signals["delivery"]:
        groups.append(
            {
                "category": "Execution and prioritization",
                "questions": [
                    _question(
                        "Tell me about a time you had to prioritize competing needs under a fixed timeline.",
                        "Tradeoff quality, operating discipline, and accountable delivery.",
                        "Use a situation where leadership priorities became an operating plan, then explain the choices, governance, readiness signals, and outcome.",
                        (evidence[1], evidence[2]),
                        "Keep ownership precise and distinguish coordination from sole product-roadmap ownership.",
                    )
                ],
            }
        )
    groups.extend(
        [
            {
                "category": "Cross-functional leadership",
                "questions": [
                    _question(
                        "How have you aligned teams with different incentives around one outcome?",
                        "Influence, operating clarity, and leadership across functions.",
                        "Explain how you established shared goals, decision rights, cadences, and escalation paths while leading 10 direct reports across an integrated 64-person organization.",
                        (evidence[0], evidence[1]),
                        "Distinguish strategic and operational leadership across the broader organization from direct people management, and do not imply engineering management.",
                    )
                ],
            },
            {
                "category": "Stakeholder management",
                "questions": [
                    _question(
                        "How do you create trust when senior stakeholders disagree on priorities?",
                        "Executive communication, listening, and decision support.",
                        "Show how you made constraints visible, separated facts from assumptions, and translated leadership priorities into a decision-ready operating plan.",
                        (evidence[0], evidence[1]),
                        "Do not imply knowledge of this company's internal stakeholders or current team dynamics.",
                    )
                ],
            },
        ]
    )
    if signals["measurement"]:
        groups.append(
            {
                "category": "Data, measurement, and decision-making",
                "questions": [
                    _question(
                        "How do you decide what to measure and when the data is sufficient to act?",
                        "Measurement judgment and the ability to connect signals to decisions.",
                        "Start with the decision, identify the smallest reliable signals, establish data-quality checks, and explain how results change the next action.",
                        (evidence[1], evidence[2]),
                        "Do not invent revenue outcomes or metrics that are not in the verified record.",
                    )
                ],
            }
        )
    if signals["product"]:
        groups.append(
            {
                "category": "Role-specific domain knowledge",
                "questions": [
                    _question(
                        "What does strong product leadership look like when authority is distributed across teams?",
                        "Adjacent product leadership, partnership, and practical operating judgment.",
                        "Connect product thinking to requirements, user needs, validation, prioritization, adoption, and cross-functional operating systems.",
                        (evidence[3], evidence[1]),
                        "Position the experience as adjacent product leadership; do not claim unsupported end-to-end ownership of a Disney product roadmap.",
                    )
                ],
            }
        )
    lead_labels = humanize_values((role_intent or {}).get("lead_evidence") or [])
    source_basis = ["Saved job description", "Verified career foundation"]
    if role_intent:
        source_basis.append("Humanized tailoring plan")
    if additional_context.strip():
        source_basis.append("User-supplied context, not independently verified")
    result: Dict[str, Any] = {
        "company": company,
        "role": role,
        "source_basis": source_basis,
        "inference_notice": INFERENCE_NOTICE,
        "hiring_manager_intent": intents[:6],
        "first_screen_priorities": [
            "A clear explanation of product or operating judgment grounded in real decisions.",
            "Evidence of prioritization, cross-functional influence, and reliable execution.",
            "Precise ownership language and a practical approach to measurement and learning.",
        ],
        "question_groups": groups,
        "best_evidence": (project_evidence + evidence[:5])[:5],
        "concerns_and_bridges": [
            {
                "concern": "The title path is rooted in operations and transformation, while this opportunity uses a senior product-management title.",
                "bridge": "The relevant through-line is adjacent product leadership: translating needs into requirements, making tradeoffs, building governance, enabling adoption, and aligning product, technology, analytics, media, creative, and business stakeholders.",
            }
        ],
        "questions_to_ask": [
            "Which decisions and operating outcomes would define strong progress for this role in the first six months?",
            "How are user needs, business priorities, and technical constraints brought together when roadmap tradeoffs are made?",
            "Where would this role need to build the strongest cross-functional relationships first?",
            "How does the team evaluate readiness, adoption, and learning after a launch or major change?",
        ],
        "tell_me_about_yourself": (
            "I am an operations and transformation leader who has spent my career turning complex, cross-functional work into clearer decisions and more reliable execution. At OMG23 (Omnicom Media Group), I advanced through five roles, led 10 direct reports, and provided strategic and operational leadership across an integrated 64-person organization supporting demanding entertainment work. I have also built workflow-governance and adoption systems, supported Disney+ launch readiness, and now apply that operating experience to active product development through Career Catalyst. What connects those experiences is practical judgment: understanding the need, aligning the right people, testing the approach, and making execution easier to trust."
        ),
        "why_company_role": (
            f"I am interested in {company} and the {role} opportunity because the saved posting emphasizes the combination of judgment, prioritization, cross-functional delivery, and operating clarity that has defined my strongest work. The role offers a chance to connect user and business needs to practical choices, align stakeholders around those choices, and build the conditions for reliable delivery and learning. That is a grounded extension of the leadership, governance, launch-readiness, and product-development work I have already done."
        ),
        "first_90_day_themes": [
            "Understand the users, business goals, decision context, and success measures before prescribing solutions.",
            "Map stakeholders, dependencies, current workflows, and where decisions or handoffs lose clarity.",
            "Assess the roadmap or operating plan against user value, business need, delivery risk, and available evidence.",
            "Clarify priorities, decision rights, and the cadence for surfacing tradeoffs and resolving blockers.",
            "Establish a small set of useful readiness, adoption, and outcome signals; identify and validate early opportunities to improve operating clarity.",
        ],
        "voice_reminder": "Use these as natural frameworks, not memorized speeches. Answer the question asked, choose one verified story, and keep ownership precise.",
        "user_supplied_context": additional_context.strip(),
        "lead_evidence_labels": lead_labels,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    content = normalize_candidate_text(_render(result))
    validate_candidate_output(content, context="Career Intelligence")
    validate_public_career_claims(content)
    validate_material_context(content, parsed, "Interview_Prep")
    filename = build_upload_filename(
        "Trisha Lynch", role, company, "Interview Prep", "txt"
    )
    output_path = root / "exports" / "strategy_packs" / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    result.update(
        {
            "job_title": role,
            "output_path": str(output_path),
            "content": content,
            "structured": {key: value for key, value in result.items()},
        }
    )
    result["structured"].pop("structured", None)
    return result
