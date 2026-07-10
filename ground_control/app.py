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
    FinanceSnapshot,
    build_finance_cards,
    build_major_tom_message,
    calculate_runway_months,
)
from ground_control.seed_data import SEED_DATA  # noqa: E402
from ground_control.state import (  # noqa: E402
    DailyMission,
    GroundControlState,
    load_state,
    reuse_unfinished_missions,
    rollover_for_date,
    save_state,
    unfinished_from_previous_day,
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
            padding: 3.4rem 2.25rem 4.5rem;
        }

        .gc-hero {
            border-bottom: 1px solid rgba(255, 247, 237, 0.08);
            margin-bottom: 1.9rem;
            padding-bottom: 1.75rem;
        }

        .gc-kicker {
            color: #f0c989;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
        }

        .gc-title {
            color: #fff7ed;
            font-size: 5.15rem;
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
            flex-direction: column;
            gap: 0.18rem;
            line-height: 1;
            padding: 0.75rem 1rem;
        }

        .gc-flight-main {
            color: #eafff8;
            font-size: 0.94rem;
            font-weight: 800;
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

        .gc-grid-title {
            color: #d9cfc1;
            font-size: 0.8rem;
            font-weight: 760;
            letter-spacing: 0;
            margin: 1rem 0 0.85rem;
            text-transform: uppercase;
        }

        .gc-card,
        .gc-panel {
            background: rgba(18, 16, 14, 0.92);
            border: 1px solid rgba(255, 247, 237, 0.07);
            border-radius: 8px;
            box-shadow: 0 18px 54px rgba(0, 0, 0, 0.2);
        }

        .gc-card {
            min-height: 9.6rem;
            padding: 1.18rem;
        }

        .gc-card-primary {
            background:
                linear-gradient(155deg, rgba(89, 214, 181, 0.16), rgba(18, 16, 14, 0.96) 55%),
                rgba(18, 16, 14, 0.96);
            border-color: rgba(89, 214, 181, 0.18);
            box-shadow: 0 24px 68px rgba(0, 0, 0, 0.26), 0 0 42px rgba(89, 214, 181, 0.08);
            min-height: 11.4rem;
            padding: 1.28rem;
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

        .gc-card-primary .gc-card-value {
            color: #effff9;
            font-size: 3.65rem;
            font-weight: 820;
            margin-top: 1.45rem;
        }

        .gc-card-caption,
        .gc-panel-body {
            color: #d3c8ba;
            font-size: 0.95rem;
            line-height: 1.5;
            margin: 0;
        }

        .gc-card-primary .gc-card-caption {
            color: #c7f4e8;
        }

        .gc-panel {
            min-height: 16.4rem;
            padding: 1.4rem;
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
            border: 1px solid rgba(255, 247, 237, 0.06);
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
            border: 1px solid rgba(255, 247, 237, 0.07);
            border-radius: 8px;
            box-shadow: 0 18px 54px rgba(0, 0, 0, 0.2);
            margin-top: 1.35rem;
            padding: 1.4rem;
        }

        [data-testid="stNumberInput"] label,
        [data-testid="stTextInput"] label,
        [data-testid="stCheckbox"] label {
            color: #d9cfc1;
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
            color: #d9cfc1;
            opacity: 1;
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

            .gc-card-primary .gc-card-value {
                font-size: 3rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header(name: str) -> None:
    st.markdown(
        f"""
        <section class="gc-hero">
            <p class="gc-kicker">Good afternoon, {html.escape(name)}</p>
            <h1 class="gc-title">Ground Control</h1>
            <div class="gc-status-row">
                <div class="gc-signal">
                    <span class="gc-flight-main">🟢 NOMINAL</span>
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


def _ensure_session_state() -> None:
    today = date.today()
    if st.session_state.get("gc_loaded"):
        current = _state_from_session()
        rolled = rollover_for_date(current, today)
        if rolled != current:
            _put_state_in_session(rolled)
            save_state(rolled)
        return

    loaded_state = load_state(current_date=today)
    state = rollover_for_date(loaded_state, today)
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

    return GroundControlState(
        person_name=str(st.session_state.get("gc_person_name", "Trisha")),
        finance=FinanceSnapshot(
            cash=float(st.session_state.get("gc_cash", 0)),
            monthly_burn=max(float(st.session_state.get("gc_monthly_burn", 1)), 1.0),
            retirement_401k=float(st.session_state.get("gc_retirement_401k", 0)),
            edd_remaining=float(st.session_state.get("gc_edd_remaining", 0)),
        ),
        mission_date=str(st.session_state.get("gc_mission_date", date.today().isoformat())),
        missions=missions,
        mission_history=tuple(st.session_state.get("gc_mission_history", ())),
    )


def _persist_session_state() -> None:
    save_state(_state_from_session())


def _render_panel_header(label: str, heading: str) -> None:
    st.markdown(
        f'<p class="gc-panel-label">{html.escape(label)}</p><h2>{html.escape(heading)}</h2>',
        unsafe_allow_html=True,
    )


def _render_finance(state: GroundControlState) -> None:
    cards = build_finance_cards(state.finance)

    st.markdown('<p class="gc-grid-title">Financial telemetry</p>', unsafe_allow_html=True)
    columns = st.columns([1, 1.45, 1, 1], gap="medium")
    for column, card in zip(columns, cards):
        card_class = "gc-card gc-card-primary" if card.label == "Runway" else "gc-card"
        with column:
            st.markdown(
                f"""
                <article class="{card_class}">
                    <p class="gc-card-label">{html.escape(card.label)}</p>
                    <p class="gc-card-value">{html.escape(card.value)}</p>
                    <p class="gc-card-caption">{html.escape(card.caption)}</p>
                </article>
                """,
                unsafe_allow_html=True,
            )


def _render_missions(state: GroundControlState) -> None:
    st.markdown(
        '<section class="gc-panel"><p class="gc-panel-label">Today</p><h2>Mission</h2></section>',
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


def _render_major_tom(state: GroundControlState) -> None:
    snapshot = state.finance
    runway_months = calculate_runway_months(
        cash=snapshot.cash,
        edd_remaining=snapshot.edd_remaining,
        monthly_burn=snapshot.monthly_burn,
    )
    message = build_major_tom_message(
        SEED_DATA,
        runway_months=runway_months,
        current_date=date.fromisoformat(state.mission_date),
        missions_completed=sum(mission.completed for mission in state.missions),
    )

    st.markdown(
        f"""
        <section class="gc-panel gc-major-tom">
            <p class="gc-panel-label">Major Tom</p>
            <h2>You're oriented.</h2>
            <p class="gc-panel-body">{html.escape(message)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Ground Control", layout="wide")
    _inject_styles()
    _ensure_session_state()
    state = _state_from_session()
    _render_header(state.person_name)
    _render_finance(state)

    left, right = st.columns([1, 1], gap="medium")
    with left:
        _render_missions(state)
    with right:
        _render_major_tom(state)
    _render_manual_override()


if __name__ == "__main__":
    main()
