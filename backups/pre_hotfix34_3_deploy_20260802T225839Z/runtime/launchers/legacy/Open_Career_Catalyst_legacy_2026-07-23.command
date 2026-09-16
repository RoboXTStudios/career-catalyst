#!/bin/bash

# Legacy pre-Sprint 29.5 launcher preserved on 2026-07-23. Do not use for the current runtime.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

keep_window_open() {
  echo
  read -r -p "Press Return to close this window..." _
}

echo "Starting Career Catalyst..."
echo "If this is your first time, make sure requirements are installed."
echo "To stop Career Catalyst, close this window or press Control+C."
echo

if ! cd "$PROJECT_ROOT"; then
  echo "Could not open the Career Catalyst project folder: $PROJECT_ROOT"
  keep_window_open
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3, then double-click this launcher again."
  keep_window_open
  exit 1
fi

if ! python3 -c "import streamlit" >/dev/null 2>&1; then
  echo "Streamlit is not installed yet."
  echo "From this project folder, run once:"
  echo "  python3 -m pip install -r requirements.txt"
  keep_window_open
  exit 1
fi

if command -v open >/dev/null 2>&1; then
  (
    sleep 2
    open "http://127.0.0.1:8501" >/dev/null 2>&1
  ) &
fi

python3 -m streamlit run app.py
exit_status=$?

echo
if [ "$exit_status" -ne 0 ] && [ "$exit_status" -ne 130 ]; then
  echo "Career Catalyst stopped with an error (exit code $exit_status)."
else
  echo "Career Catalyst stopped."
fi
keep_window_open
exit "$exit_status"
