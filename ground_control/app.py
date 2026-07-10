"""Ground Control local-first Streamlit app.

Run with: streamlit run ground_control/app.py
"""

from __future__ import annotations

import html
import sys
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
    save_state,
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
                linear-gradient(180deg, rgba(216, 166, 87, 0.08), rgba(8, 7, 6, 0) 34rem),
                #080706;
            color: #f4efe8;
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stToolbar"] {
            color: #f4efe8;
        }

        .block-container {
            max-width: 1180px;
            padding: 3rem 2rem 4rem;
        }

        .gc-hero {
            border-bottom: 1px solid rgba(244, 239, 232, 0.12);
            margin-bottom: 1.5rem;
            padding-bottom: 1.5rem;
        }

        .gc-kicker {
            color: #d8a657;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
        }

        .gc-title {
            color: #f4efe8;
            font-size: 4.75rem;
            font-weight: 780;
            letter-spacing: 0;
            line-height: 0.95;
            margin: 0;
        }

        .gc-status-row {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1.2rem;
        }

        .gc-signal {
            align-items: center;
            background: rgba(89, 214, 181, 0.1);
            border: 1px solid rgba(89, 214, 181, 0.34);
            border-radius: 999px;
            color: #d8fff3;
            display: inline-flex;
            font-size: 0.95rem;
            font-weight: 650;
            gap: 0.5rem;
            line-height: 1;
            padding: 0.65rem 0.85rem;
        }

        .gc-signal-dot {
            background: #59d6b5;
            border-radius: 50%;
            box-shadow: 0 0 18px rgba(89, 214, 181, 0.65);
            display: inline-block;
            height: 0.58rem;
            width: 0.58rem;
        }

        .gc-flight-status {
            color: rgba(244, 239, 232, 0.62);
            font-size: 0.95rem;
        }

        .gc-grid-title {
            color: rgba(244, 239, 232, 0.68);
            font-size: 0.8rem;
            font-weight: 720;
            letter-spacing: 0;
            margin: 0.65rem 0 0.65rem;
            text-transform: uppercase;
        }

        .gc-card,
        .gc-panel {
            background: rgba(18, 16, 14, 0.92);
            border: 1px solid rgba(244, 239, 232, 0.11);
            border-radius: 8px;
            box-shadow: 0 22px 70px rgba(0, 0, 0, 0.28);
        }

        .gc-card {
            min-height: 9.25rem;
            padding: 1.05rem;
        }

        .gc-card-label,
        .gc-panel-label {
            color: rgba(244, 239, 232, 0.58);
            font-size: 0.78rem;
            font-weight: 720;
            letter-spacing: 0;
            margin: 0;
            text-transform: uppercase;
        }

        .gc-card-value {
            color: #f4efe8;
            font-size: 2.1rem;
            font-weight: 760;
            letter-spacing: 0;
            line-height: 1.05;
            margin: 1.35rem 0 0.45rem;
        }

        .gc-card-caption,
        .gc-panel-body {
            color: rgba(244, 239, 232, 0.66);
            font-size: 0.95rem;
            line-height: 1.5;
            margin: 0;
        }

        .gc-panel {
            min-height: 16rem;
            padding: 1.25rem;
        }

        .gc-panel h2 {
            color: #f4efe8;
            font-size: 1.65rem;
            font-weight: 760;
            letter-spacing: 0;
            margin: 0.35rem 0 1rem;
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
            border: 1px solid rgba(244, 239, 232, 0.08);
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
            color: #f4efe8;
            font-size: 1rem;
            line-height: 1.35;
        }

        div[data-testid="stCheckbox"] {
            background: rgba(244, 239, 232, 0.055);
            border: 1px solid rgba(244, 239, 232, 0.08);
            border-radius: 8px;
            margin-bottom: 0.72rem;
            min-height: 3.15rem;
            padding: 0.45rem 0.72rem;
        }

        div[data-testid="stCheckbox"] label {
            align-items: center;
            min-height: 2.2rem;
        }

        div[data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p {
            color: #f4efe8;
            font-size: 1rem;
            line-height: 1.35;
        }

        [data-testid="stForm"] {
            background: rgba(18, 16, 14, 0.92);
            border: 1px solid rgba(244, 239, 232, 0.11);
            border-radius: 8px;
            box-shadow: 0 22px 70px rgba(0, 0, 0, 0.28);
            margin-top: 1rem;
            padding: 1.25rem;
        }

        [data-testid="stNumberInput"] label,
        [data-testid="stTextInput"] label,
        [data-testid="stCheckbox"] label {
            color: rgba(244, 239, 232, 0.78);
        }

        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input {
            background: rgba(244, 239, 232, 0.07);
            border-color: rgba(244, 239, 232, 0.16);
            color: #f4efe8;
        }

        div[data-testid="stAlert"] {
            background: rgba(89, 214, 181, 0.1);
            border-color: rgba(89, 214, 181, 0.28);
            color: #d8fff3;
        }

        .gc-major-tom {
            border-color: rgba(216, 166, 87, 0.26);
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
                font-size: 3rem;
            }

            .gc-card {
                min-height: 8.25rem;
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
                    <span class="gc-signal-dot"></span>
                    <span>Signal acquired.</span>
                </div>
                <span class="gc-flight-status">Flight status: Nominal</span>
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
    if st.session_state.get("gc_loaded"):
        return

    state = load_state()
    st.session_state["gc_person_name"] = state.person_name
    st.session_state["gc_cash"] = state.finance.cash
    st.session_state["gc_monthly_burn"] = state.finance.monthly_burn
    st.session_state["gc_retirement_401k"] = state.finance.retirement_401k
    st.session_state["gc_edd_remaining"] = state.finance.edd_remaining

    for index, mission in enumerate(state.missions):
        st.session_state[_mission_text_key(index)] = mission.text
        st.session_state[_mission_completed_key(index)] = mission.completed

    st.session_state["gc_loaded"] = True


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
        missions=missions,
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


def _render_missions(state: GroundControlState) -> None:
    st.markdown(
        "<section class=\"gc-panel\"><p class=\"gc-panel-label\">Today</p><h2>Today's Mission</h2></section>",
        unsafe_allow_html=True,
    )
    for index, mission in enumerate(state.missions):
        st.checkbox(
            mission.text,
            key=_mission_completed_key(index),
            on_change=_persist_session_state,
        )


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
    message = build_major_tom_message(SEED_DATA, runway_months=runway_months)

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
