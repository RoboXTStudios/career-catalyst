"""Ground Control local-first Streamlit app.

Run with: streamlit run ground_control/app.py
"""

from __future__ import annotations

import html
import sys
from datetime import date
from pathlib import Path

import streamlit as st

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from ground_control.model import (  # noqa: E402
    CreativeState,
    FinancialState,
    FinanceSnapshot,
    build_creative_state,
    build_finance_cards,
    build_financial_state,
    build_major_tom_message,
)
from ground_control.career import (  # noqa: E402
    CareerState,
    LocalCareerCatalystProvider,
    load_career_state,
)
from ground_control.local_time import (  # noqa: E402
    format_local_datetime,
    greeting_for_datetime,
    local_date,
    local_now,
)
from ground_control.mission_engine import (  # noqa: E402
    MissionEngineResult,
    run_default_mission_engine,
)
from ground_control.seed_data import SEED_DATA  # noqa: E402
from ground_control.state import (  # noqa: E402
    DailyMission,
    GroundControlState,
    ensure_daily_suggestions,
    load_state,
    reuse_unfinished_missions,
    rollover_for_date,
    save_state,
    unfinished_from_previous_day,
    yesterday_mission_day,
)

MISSION_COUNT = 3


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
        }

        .stApp {
            background:
                radial-gradient(circle at 18% 0%, rgba(216, 166, 87, 0.1), rgba(216, 166, 87, 0) 22rem),
                linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(8, 7, 6, 0) 28rem),
                #090807;
            color: #fff7ed;
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stToolbar"] {
            color: #fff7ed;
        }

        .block-container {
            max-width: 1180px;
            padding: 4rem 2.25rem 5rem;
        }

        .gc-hero {
            border-bottom: 1px solid rgba(255, 247, 237, 0.055);
            margin-bottom: 1.1rem;
            padding-bottom: 2rem;
        }

        .gc-kicker {
            color: #f0c989;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
        }

        .gc-local-time {
            color: #d9cfc1;
            font-size: 0.92rem;
            font-weight: 620;
            margin: 0.65rem 0 0;
        }

        .gc-title {
            color: #fff7ed;
            font-size: 5.45rem;
            font-weight: 800;
            letter-spacing: 0;
            line-height: 0.95;
            margin: 0;
        }

        .gc-status-row {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1.35rem;
        }

        .gc-signal {
            align-items: center;
            background: rgba(89, 214, 181, 0.1);
            border: 1px solid rgba(89, 214, 181, 0.34);
            border-radius: 999px;
            color: #eafff8;
            display: inline-flex;
            gap: 0.18rem;
            line-height: 1;
            padding: 0.75rem 1rem;
        }

        .gc-signal-adjust-course {
            background: rgba(240, 201, 137, 0.1);
            border-color: rgba(240, 201, 137, 0.34);
        }

        .gc-signal-critical-burn {
            background: rgba(204, 96, 66, 0.12);
            border-color: rgba(224, 120, 88, 0.42);
        }

        .gc-flight-main {
            align-items: center;
            color: #eafff8;
            display: inline-flex;
            font-size: 0.94rem;
            font-weight: 800;
            gap: 0.48rem;
            letter-spacing: 0;
        }

        .gc-flight-subtitle {
            color: #c7f4e8;
            font-size: 0.78rem;
            font-weight: 600;
        }

        .gc-signal-dot {
            background: #59d6b5;
            border-radius: 50%;
            box-shadow: 0 0 18px rgba(89, 214, 181, 0.65);
            display: inline-block;
            height: 0.58rem;
            width: 0.58rem;
        }

        .gc-signal-adjust-course .gc-signal-dot {
            background: #f0c989;
            box-shadow: 0 0 18px rgba(240, 201, 137, 0.52);
        }

        .gc-signal-critical-burn .gc-signal-dot {
            background: #e07858;
            box-shadow: 0 0 18px rgba(224, 120, 88, 0.52);
        }

        .gc-grid-title {
            color: #d9cfc1;
            font-size: 0.8rem;
            font-weight: 760;
            letter-spacing: 0;
            margin: 2.4rem 0 1rem;
            text-transform: uppercase;
        }

        .gc-card,
        .gc-state-card,
        .gc-panel {
            background: rgba(18, 16, 14, 0.92);
            border: 1px solid rgba(255, 247, 237, 0.045);
            border-radius: 8px;
            box-shadow: 0 14px 42px rgba(0, 0, 0, 0.16);
        }

        .gc-card {
            min-height: 8.5rem;
            padding: 1.18rem;
        }

        .gc-state-card {
            display: flex;
            flex-direction: column;
            min-height: 16.8rem;
            padding: 1.5rem;
        }

        .gc-state-card-financial {
            background:
                linear-gradient(155deg, rgba(89, 214, 181, 0.16), rgba(18, 16, 14, 0.96) 55%),
                rgba(18, 16, 14, 0.96);
            border-color: rgba(89, 214, 181, 0.14);
            box-shadow: 0 24px 68px rgba(0, 0, 0, 0.26), 0 0 42px rgba(89, 214, 181, 0.08);
        }

        .gc-state-status {
            color: #f0c989;
            font-size: 0.82rem;
            font-weight: 780;
            margin: 1.55rem 0 0.5rem;
            text-transform: uppercase;
        }

        .gc-state-card-financial .gc-state-status {
            color: #c7f4e8;
        }

        .gc-state-value {
            color: #fff7ed;
            font-size: 2.05rem;
            font-weight: 790;
            line-height: 1.08;
            margin: 0 0 0.85rem;
        }

        .gc-state-card-financial .gc-state-value {
            color: #effff9;
            font-size: 4.35rem;
            font-weight: 830;
            line-height: 0.98;
        }

        .gc-state-summary {
            color: #ded4c8;
            font-size: 0.95rem;
            line-height: 1.5;
            margin: auto 0 0;
        }

        .gc-card-label,
        .gc-panel-label {
            color: #d9cfc1;
            font-size: 0.78rem;
            font-weight: 760;
            letter-spacing: 0;
            margin: 0;
            text-transform: uppercase;
        }

        .gc-card-value {
            color: #fff7ed;
            font-size: 2.1rem;
            font-weight: 780;
            letter-spacing: 0;
            line-height: 1.05;
            margin: 1.35rem 0 0.45rem;
        }

        .gc-card-caption,
        .gc-panel-body {
            color: #ded4c8;
            font-size: 0.95rem;
            line-height: 1.5;
            margin: 0;
        }

        .gc-panel {
            min-height: 16.4rem;
            padding: 1.4rem;
        }

        .gc-brief {
            margin-bottom: 0.4rem;
            min-height: 0;
            padding: 1.55rem 1.65rem 1.65rem;
        }

        .gc-brief h2 {
            font-size: 1.9rem;
            margin-bottom: 0.72rem;
        }

        .gc-section-title {
            color: #fff7ed;
            font-size: 1.72rem;
            font-weight: 790;
            margin: 0.38rem 0 1.1rem;
        }

        .gc-panel h2 {
            color: #fff7ed;
            font-size: 1.72rem;
            font-weight: 790;
            letter-spacing: 0;
            margin: 0.38rem 0 1.1rem;
        }

        .gc-missions {
            display: grid;
            gap: 0.72rem;
            margin: 0;
            padding: 0;
        }

        .gc-mission {
            align-items: center;
            background: rgba(244, 239, 232, 0.055);
            border: 1px solid rgba(255, 247, 237, 0.06);
            border-radius: 8px;
            display: grid;
            grid-template-columns: 1.4rem 1fr;
            min-height: 3.15rem;
            padding: 0.72rem 0.82rem;
        }

        .gc-checkbox {
            border: 1px solid rgba(244, 239, 232, 0.5);
            border-radius: 5px;
            display: inline-block;
            height: 0.88rem;
            width: 0.88rem;
        }

        .gc-mission span:last-child {
            color: #fff7ed;
            font-size: 1rem;
            line-height: 1.35;
        }

        div[data-testid="stCheckbox"] {
            background: rgba(244, 239, 232, 0.055);
            border: 1px solid rgba(255, 247, 237, 0.045);
            border-radius: 8px;
            margin-bottom: 0.82rem;
            min-height: 3.15rem;
            padding: 0.45rem 0.72rem;
        }

        div[data-testid="stCheckbox"] label {
            align-items: center;
            min-height: 2.2rem;
        }

        div[data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p {
            color: #fff7ed;
            font-size: 1rem;
            line-height: 1.35;
        }

        [data-testid="stForm"] {
            background: rgba(18, 16, 14, 0.92);
            border: 1px solid rgba(255, 247, 237, 0.045);
            border-radius: 8px;
            box-shadow: 0 18px 54px rgba(0, 0, 0, 0.2);
            margin-top: 2.8rem;
            padding: 1.55rem;
        }

        [data-testid="stNumberInput"] label,
        [data-testid="stTextInput"] label,
        [data-testid="stCheckbox"] label {
            color: #e5dbce;
        }

        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input {
            background: #fffaf3;
            border: 1px solid #9d856b;
            color: #9a4f16;
            font-weight: 650;
            opacity: 1;
        }

        [data-testid="stNumberInput"] input::placeholder,
        [data-testid="stTextInput"] input::placeholder {
            color: #783b10;
            opacity: 1;
        }

        [data-testid="stNumberInput"] input:hover,
        [data-testid="stTextInput"] input:hover {
            border-color: #d8a657;
        }

        [data-testid="stNumberInput"] input:focus,
        [data-testid="stTextInput"] input:focus {
            border-color: #f0c989;
            box-shadow: 0 0 0 3px rgba(240, 201, 137, 0.28);
            outline: none;
        }

        [data-testid="stNumberInput"] input:disabled,
        [data-testid="stTextInput"] input:disabled {
            background: #d8d0c6;
            border-color: #a89b8b;
            color: #65401f;
            cursor: not-allowed;
            opacity: 1;
        }

        [data-testid="stNumberInput"] button {
            background: #f4eadc;
            border-color: #9d856b;
            color: #783b10;
        }

        [data-testid="stNumberInput"] button:hover {
            background: #ead8c0;
            border-color: #d8a657;
            color: #5f2e0b;
        }

        [data-testid="stNumberInput"] button:focus-visible,
        [data-testid="stFormSubmitButton"] button:focus-visible,
        div[data-testid="stButton"] button:focus-visible {
            outline: 3px solid #f0c989;
            outline-offset: 2px;
        }

        [data-testid="stFormSubmitButton"] button,
        div[data-testid="stButton"] button {
            background: #d8a657;
            border: 1px solid #f0c989;
            color: #281609;
            font-weight: 760;
        }

        [data-testid="stFormSubmitButton"] button:hover,
        div[data-testid="stButton"] button:hover {
            background: #f0c989;
            border-color: #ffe0a8;
            color: #1f1006;
        }

        [data-testid="stFormSubmitButton"] button:disabled,
        div[data-testid="stButton"] button:disabled,
        [data-testid="stNumberInput"] button:disabled {
            background: #4c4540;
            border-color: #6e645c;
            color: #c8bdb2;
            cursor: not-allowed;
            opacity: 1;
        }

        [data-testid="stCaptionContainer"] p,
        [data-testid="stWidgetLabel"] p,
        [data-testid="InputInstructions"] {
            color: #ded4c8;
            opacity: 1;
        }

        [data-testid="stExpander"] {
            background: rgba(18, 16, 14, 0.72);
            border: 1px solid rgba(255, 247, 237, 0.055);
            border-radius: 8px;
        }

        .gc-telemetry-intro {
            color: #ded4c8;
            font-size: 0.95rem;
            margin: 0.4rem 0 1.3rem;
        }

        [data-testid="stExpander"] [data-testid="stForm"] {
            margin-top: 1.5rem;
        }

        [data-testid="stExpander"] summary p {
            color: #fff7ed;
            font-weight: 720;
        }

        .gc-log-row {
            align-items: start;
            border-top: 1px solid rgba(255, 247, 237, 0.055);
            color: #ded4c8;
            display: grid;
            gap: 0.65rem;
            grid-template-columns: 1.1rem 1fr;
            padding: 0.72rem 0;
        }

        .gc-log-row:first-child {
            border-top: 0;
        }

        div[data-testid="stAlert"] {
            background: rgba(89, 214, 181, 0.1);
            border-color: rgba(89, 214, 181, 0.28);
            color: #eafff8;
        }

        .gc-major-tom {
            border-color: rgba(240, 201, 137, 0.15);
            position: relative;
        }

        .gc-major-tom:before {
            background: #d8a657;
            border-radius: 999px;
            content: "";
            display: block;
            height: 0.22rem;
            left: 1.25rem;
            position: absolute;
            right: 1.25rem;
            top: 0;
        }

        @media (max-width: 700px) {
            .block-container {
                padding: 2rem 1rem 3rem;
            }

            .gc-title {
                font-size: 3.18rem;
            }

            .gc-card {
                min-height: 8.25rem;
            }

            .gc-state-card {
                min-height: 13.5rem;
            }

            .gc-state-card-financial .gc-state-value {
                font-size: 3rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header(name: str, current_time, financial_state: FinancialState) -> None:
    greeting = greeting_for_datetime(current_time)
    timestamp = format_local_datetime(current_time)
    status_class = financial_state.status.lower().replace(" ", "-")
    st.markdown(
        f"""
        <section class="gc-hero">
            <p class="gc-kicker">{html.escape(greeting)}, {html.escape(name)}</p>
            <h1 class="gc-title">Ground Control</h1>
            <p class="gc-local-time">{html.escape(timestamp)}</p>
            <div class="gc-status-row">
                <div class="gc-signal gc-signal-{html.escape(status_class)}">
                    <span class="gc-flight-main">
                        <span class="gc-signal-dot"></span>
                        {html.escape(financial_state.status.upper())}
                    </span>
                    <span class="gc-flight-subtitle">Signal acquired.</span>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _mission_text_key(index: int) -> str:
    return f"gc_mission_{index}_text"


def _mission_completed_key(index: int) -> str:
    return f"gc_mission_{index}_completed"


def _clean_mission_text(value: object, fallback: str) -> str:
    text = str(value).strip()
    return text or fallback


def _ensure_session_state(today: date) -> None:
    if st.session_state.get("gc_loaded"):
        current = _state_from_session()
        prepared = ensure_daily_suggestions(rollover_for_date(current, today))
        if prepared != current:
            _put_state_in_session(prepared)
            save_state(prepared)
        return

    loaded_state = load_state(current_date=today)
    state = ensure_daily_suggestions(rollover_for_date(loaded_state, today))
    if state != loaded_state:
        save_state(state)

    _put_state_in_session(state)
    st.session_state["gc_loaded"] = True


def _put_state_in_session(state: GroundControlState) -> None:
    st.session_state["gc_person_name"] = state.person_name
    st.session_state["gc_cash"] = state.finance.cash
    st.session_state["gc_monthly_burn"] = state.finance.monthly_burn
    st.session_state["gc_retirement_401k"] = state.finance.retirement_401k
    st.session_state["gc_edd_remaining"] = state.finance.edd_remaining
    st.session_state["gc_mission_date"] = state.mission_date
    st.session_state["gc_mission_history"] = state.mission_history
    st.session_state["gc_mission_suggestions_applied"] = state.mission_suggestions_applied

    for index, mission in enumerate(state.missions):
        st.session_state[_mission_text_key(index)] = mission.text
        st.session_state[_mission_completed_key(index)] = mission.completed


def _state_from_session() -> GroundControlState:
    missions = tuple(
        DailyMission(
            text=_clean_mission_text(
                st.session_state.get(_mission_text_key(index), ""),
                f"Mission {index + 1}",
            ),
            completed=bool(st.session_state.get(_mission_completed_key(index), False)),
        )
        for index in range(MISSION_COUNT)
    )
    suggestions_applied = st.session_state.get("gc_mission_suggestions_applied")
    if not isinstance(suggestions_applied, bool):
        suggestions_applied = tuple(mission.text for mission in missions) != tuple(
            f"Mission {index}" for index in range(1, MISSION_COUNT + 1)
        )

    return GroundControlState(
        person_name=str(st.session_state.get("gc_person_name", "Trisha")),
        finance=FinanceSnapshot(
            cash=float(st.session_state.get("gc_cash", 0)),
            monthly_burn=max(float(st.session_state.get("gc_monthly_burn", 1)), 1.0),
            retirement_401k=float(st.session_state.get("gc_retirement_401k", 0)),
            edd_remaining=float(st.session_state.get("gc_edd_remaining", 0)),
        ),
        mission_date=str(st.session_state.get("gc_mission_date", local_date().isoformat())),
        missions=missions,
        mission_history=tuple(st.session_state.get("gc_mission_history", ())),
        mission_suggestions_applied=suggestions_applied,
    )


def _persist_session_state() -> None:
    save_state(_state_from_session())


def _render_panel_header(label: str, heading: str) -> None:
    st.markdown(
        f'<p class="gc-panel-label">{html.escape(label)}</p><h2>{html.escape(heading)}</h2>',
        unsafe_allow_html=True,
    )


def _render_state_card(
    *,
    label: str,
    status: str,
    value: str,
    summary: str,
    financial: bool = False,
) -> None:
    classes = "gc-state-card gc-state-card-financial" if financial else "gc-state-card"
    st.markdown(
        f"""
        <article class="{classes}">
            <p class="gc-card-label">{html.escape(label)}</p>
            <p class="gc-state-status">{html.escape(status)}</p>
            <p class="gc-state-value">{html.escape(value)}</p>
            <p class="gc-state-summary">{html.escape(summary)}</p>
        </article>
        """,
        unsafe_allow_html=True,
    )


def _render_state_cards(
    financial: FinancialState,
    career: CareerState,
    creative: CreativeState,
) -> None:
    st.markdown('<p class="gc-grid-title">State of the mission</p>', unsafe_allow_html=True)
    columns = st.columns([1.2, 1, 1], gap="medium")
    with columns[0]:
        _render_state_card(
            label="Financial State",
            status=financial.status,
            value=financial.runway_label,
            summary=financial.summary,
            financial=True,
        )
    with columns[1]:
        _render_state_card(
            label="Career State",
            status="Active Search",
            value=career.status,
            summary=career.summary,
        )
    with columns[2]:
        _render_state_card(
            label="Creative State",
            status=creative.status,
            value=creative.project_name,
            summary=creative.summary,
        )


def _render_financial_telemetry(state: GroundControlState) -> None:
    cards = build_finance_cards(state.finance)

    st.markdown('<p class="gc-grid-title">Systems access</p>', unsafe_allow_html=True)
    with st.expander("Financial Telemetry"):
        st.markdown(
            '<p class="gc-telemetry-intro">Inspect reserves and update local telemetry when needed.</p>',
            unsafe_allow_html=True,
        )
        columns = st.columns(4, gap="medium")
        for column, card in zip(columns, cards):
            with column:
                st.markdown(
                    f"""
                    <article class="gc-card">
                        <p class="gc-card-label">{html.escape(card.label)}</p>
                        <p class="gc-card-value">{html.escape(card.value)}</p>
                        <p class="gc-card-caption">{html.escape(card.caption)}</p>
                    </article>
                    """,
                    unsafe_allow_html=True,
                )
        _render_manual_override()


def _render_missions(state: GroundControlState) -> None:
    st.markdown(
        '<p class="gc-panel-label">Today</p><h2 class="gc-section-title">Mission</h2>',
        unsafe_allow_html=True,
    )
    for index, mission in enumerate(state.missions):
        st.checkbox(
            mission.text,
            key=_mission_completed_key(index),
            on_change=_persist_session_state,
        )

    unfinished = unfinished_from_previous_day(state)
    st.caption(f"Flight plan for {date.fromisoformat(state.mission_date).strftime('%A, %B %d')}.")
    st.button(
        "Reuse unfinished",
        disabled=not unfinished,
        help="Reuse unfinished missions from the previous day without carrying them forward automatically.",
        on_click=_reuse_previous_unfinished,
        use_container_width=False,
    )


def _render_yesterday(state: GroundControlState, today: date) -> None:
    day = yesterday_mission_day(state, today)
    st.markdown(
        '<p class="gc-panel-label">Flight log</p><h2 class="gc-section-title">Yesterday</h2>',
        unsafe_allow_html=True,
    )

    if day is None:
        with st.expander("Yesterday · No flight log"):
            st.caption("No mission record was saved for the prior day.")
        return

    completed = sum(mission.completed for mission in day.missions)
    with st.expander(f"Yesterday · {completed} of {MISSION_COUNT} complete"):
        rows = "".join(
            f"""
            <div class="gc-log-row">
                <span>{'✓' if mission.completed else '○'}</span>
                <span>{html.escape(mission.text)}</span>
            </div>
            """
            for mission in day.missions
        )
        st.markdown(rows, unsafe_allow_html=True)


def _reuse_previous_unfinished() -> None:
    reused = reuse_unfinished_missions(_state_from_session())
    for index, mission in enumerate(reused.missions):
        st.session_state[_mission_text_key(index)] = mission.text
        st.session_state[_mission_completed_key(index)] = False
    save_state(_state_from_session())


def _render_manual_override() -> None:
    with st.form("gc_manual_override"):
        _render_panel_header("Manual Override", "Update telemetry")

        left, right = st.columns(2, gap="medium")
        with left:
            st.number_input("Cash", min_value=0.0, step=100.0, format="%.0f", key="gc_cash")
            st.number_input(
                "Monthly essentials burn",
                min_value=1.0,
                step=100.0,
                format="%.0f",
                key="gc_monthly_burn",
            )
        with right:
            st.number_input("401(k)", min_value=0.0, step=1000.0, format="%.0f", key="gc_retirement_401k")
            st.number_input("EDD balance", min_value=0.0, step=100.0, format="%.0f", key="gc_edd_remaining")

        for index in range(MISSION_COUNT):
            st.text_input(f"Mission {index + 1}", key=_mission_text_key(index))

        submitted = st.form_submit_button("Save manual override")

    if submitted:
        _persist_session_state()
        st.success("Manual override saved locally.")


def _render_major_tom(
    state: GroundControlState,
    mission_result: MissionEngineResult,
) -> None:
    next_mission = next(
        (mission.text for mission in state.missions if not mission.completed),
        None,
    )
    message = build_major_tom_message(
        mission_summary=mission_result.summary,
        current_date=date.fromisoformat(state.mission_date),
        missions_completed=sum(mission.completed for mission in state.missions),
        next_mission=next_mission,
    )

    st.markdown(
        f"""
        <section class="gc-panel gc-major-tom gc-brief">
            <p class="gc-panel-label">Major Tom</p>
            <h2>Morning brief</h2>
            <p class="gc-panel-body">{html.escape(message)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Ground Control", layout="wide")
    _inject_styles()
    current_time = local_now()
    today = local_date(current_time)
    _ensure_session_state(today)
    state = _state_from_session()
    financial = build_financial_state(state.finance)
    career = load_career_state(LocalCareerCatalystProvider(SEED_DATA))
    creative = build_creative_state(SEED_DATA, missions=state.missions)
    mission_result = run_default_mission_engine(state.finance, seed=SEED_DATA)
    _render_header(state.person_name, current_time, financial)
    _render_major_tom(state, mission_result)
    _render_state_cards(financial, career, creative)

    st.markdown('<p class="gc-grid-title">Daily flight plan</p>', unsafe_allow_html=True)
    left, right = st.columns([1.35, 0.85], gap="large")
    with left:
        _render_missions(state)
    with right:
        _render_yesterday(state, today)
    _render_financial_telemetry(state)


if __name__ == "__main__":
    main()
