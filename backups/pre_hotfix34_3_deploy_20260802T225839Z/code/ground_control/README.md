# Ground Control

Ground Control is a calm, local-first cockpit for finances, daily focus, and career transition. It is not a productivity app or a budgeting app.

## Milestones

- Signal Acquired
- Manual Override
- Flight Deck
- Daily Flight Plan

## Run Locally

From the repository root, run:

```bash
streamlit run ground_control/app.py
```

Then open the local URL printed by Streamlit.

## Local State

User changes are stored in `ground_control/local_state.json`. The file is local and gitignored; `ground_control/seed_data.py` provides safe first-run fallback data when no saved state exists.
