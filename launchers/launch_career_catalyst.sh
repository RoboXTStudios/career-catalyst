#!/bin/bash

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_CODE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_DIR="${CAREER_CATALYST_STATE_DIR:-$HOME/Library/Application Support/Career Catalyst}"
LOG_DIR="${CAREER_CATALYST_LOG_DIR:-$HOME/Library/Logs/Career Catalyst}"
CONFIG_FILE="${CAREER_CATALYST_CONFIG_FILE:-$STATE_DIR/launcher.conf}"
BASE_PORT="${CAREER_CATALYST_BASE_PORT:-8503}"
PYTHON_BIN="${CAREER_CATALYST_PYTHON:-python3}"
OPEN_COMMAND="${CAREER_CATALYST_OPEN_COMMAND:-open}"
LOCK_DIR="$STATE_DIR/launch.lock"
STATE_FILE="$STATE_DIR/runtime.state"
LAUNCH_LOG="$LOG_DIR/launcher-$(date +%Y-%m-%d).log"

load_config() {
  [ -f "$CONFIG_FILE" ] || return 0
  while IFS='=' read -r key value; do
    case "$key" in
      CAREER_CATALYST_CODE_ROOT)
        [ -n "${CAREER_CATALYST_CODE_ROOT:-}" ] || CAREER_CATALYST_CODE_ROOT="$value"
        ;;
      CAREER_CATALYST_RUNTIME_ROOT)
        [ -n "${CAREER_CATALYST_RUNTIME_ROOT:-}" ] || CAREER_CATALYST_RUNTIME_ROOT="$value"
        ;;
      CAREER_CATALYST_EXPORT_ROOT)
        [ -n "${CAREER_CATALYST_EXPORT_ROOT:-}" ] || CAREER_CATALYST_EXPORT_ROOT="$value"
        ;;
      CAREER_CATALYST_LAUNCHER_PATH)
        ;;
    esac
  done < "$CONFIG_FILE"
}

load_config
CODE_ROOT="${CAREER_CATALYST_CODE_ROOT:-$DEFAULT_CODE_ROOT}"
RUNTIME_ROOT="${CAREER_CATALYST_RUNTIME_ROOT:-$CODE_ROOT}"
EXPORT_ROOT="${CAREER_CATALYST_EXPORT_ROOT:-$HOME/Documents/career-catalyst/exports}"
ENTRYPOINT="$CODE_ROOT/launchers/career_catalyst_entrypoint.py"

mkdir -p "$STATE_DIR" "$LOG_DIR"

log_message() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LAUNCH_LOG"
}

show_error() {
  message="$1"
  log_message "ERROR: $message"
  if command -v osascript >/dev/null 2>&1; then
    osascript - "$message" <<'APPLESCRIPT' >/dev/null 2>&1
on run argv
  display alert "Career Catalyst could not start" message (item 1 of argv) as critical
end run
APPLESCRIPT
  fi
  printf '%s\n' "$message" >&2
}

listener_pid() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -n 1
}

process_command() {
  ps -p "$1" -o command= 2>/dev/null
}

process_cwd() {
  lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
}

is_healthy() {
  curl -fsS --max-time 2 "http://127.0.0.1:$1/_stcore/health" 2>/dev/null |
    grep -q "ok"
}

is_career_catalyst_process() {
  pid="$1"
  port="$2"
  command_line="$(process_command "$pid")"
  cwd="$(process_cwd "$pid")"
  [ "$cwd" = "$CODE_ROOT" ] || return 1
  case "$command_line" in
    *"streamlit run "*"career_catalyst_entrypoint.py"* | \
    *"streamlit run "*"career_catalyst_sprint29_baseline_launcher.py"* | \
    *"streamlit run app.py"*)
      ;;
    *)
      return 1
      ;;
  esac
  is_healthy "$port"
}

state_value() {
  [ -f "$STATE_FILE" ] || return 0
  sed -n "s/^$1=//p" "$STATE_FILE" | head -n 1
}

record_state() {
  pid="$1"
  port="$2"
  temporary="$STATE_FILE.tmp.$$"
  {
    printf 'pid=%s\n' "$pid"
    printf 'port=%s\n' "$port"
    printf 'url=http://127.0.0.1:%s\n' "$port"
    printf 'code_root=%s\n' "$CODE_ROOT"
    printf 'entrypoint=%s\n' "$ENTRYPOINT"
  } > "$temporary"
  mv "$temporary" "$STATE_FILE"
}

choose_target() {
  recorded_pid="$(state_value pid)"
  recorded_port="$(state_value port)"
  if [ -n "$recorded_pid" ] && [ -n "$recorded_port" ] &&
    is_career_catalyst_process "$recorded_pid" "$recorded_port"; then
    printf 'reuse:%s:%s\n' "$recorded_port" "$recorded_pid"
    return 0
  fi

  port="$BASE_PORT"
  while [ "$port" -le 8599 ]; do
    pid="$(listener_pid "$port")"
    if [ -z "$pid" ]; then
      printf 'start:%s:\n' "$port"
      return 0
    fi
    if [ "$port" = "$BASE_PORT" ] &&
      is_career_catalyst_process "$pid" "$port"; then
      printf 'reuse:%s:%s\n' "$port" "$pid"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}

open_url() {
  "$OPEN_COMMAND" "$1" >/dev/null 2>&1
}

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    return 0
  fi
  owner_pid="$(sed -n '1p' "$LOCK_DIR/pid" 2>/dev/null)"
  if [ -n "$owner_pid" ] && ! kill -0 "$owner_pid" 2>/dev/null; then
    rmdir "$LOCK_DIR" 2>/dev/null || true
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      printf '%s\n' "$$" > "$LOCK_DIR/pid"
      return 0
    fi
  fi
  return 1
}

release_lock() {
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}

main() {
  if ! acquire_lock; then
    show_error "Another Career Catalyst launch is already in progress."
    return 1
  fi
  trap release_lock EXIT

  target="$(choose_target)" || {
    show_error "No available local port was found from $BASE_PORT through 8599."
    return 1
  }
  action="${target%%:*}"
  remainder="${target#*:}"
  port="${remainder%%:*}"
  pid="${target##*:}"
  url="http://127.0.0.1:$port"

  if [ "$action" = "reuse" ]; then
    record_state "$pid" "$port"
    log_message "Reusing Career Catalyst pid=$pid url=$url"
    open_url "$url"
    return 0
  fi

  if [ ! -f "$ENTRYPOINT" ]; then
    show_error "The current Career Catalyst entrypoint is missing: $ENTRYPOINT"
    return 1
  fi
  if [ ! -f "$RUNTIME_ROOT/data/application_tracker.yml" ]; then
    show_error "The reconciled Career Catalyst runtime is unavailable: $RUNTIME_ROOT"
    return 1
  fi
  if ! "$PYTHON_BIN" -c "import streamlit" >/dev/null 2>&1; then
    show_error "Python can run, but Streamlit is not installed for $PYTHON_BIN."
    return 1
  fi

  streamlit_log="$LOG_DIR/streamlit-$(date +%Y-%m-%d)-$port.log"
  log_message "Starting Career Catalyst code_root=$CODE_ROOT runtime_root=$RUNTIME_ROOT url=$url"
  (
    cd "$CODE_ROOT" || exit 1
    CAREER_CATALYST_CODE_ROOT="$CODE_ROOT" \
      CAREER_CATALYST_RUNTIME_ROOT="$RUNTIME_ROOT" \
      CAREER_CATALYST_EXPORT_ROOT="$EXPORT_ROOT" \
      PYTHONDONTWRITEBYTECODE=1 \
      nohup "$PYTHON_BIN" -m streamlit run "$ENTRYPOINT" \
        --server.port "$port" \
        --server.address 127.0.0.1 \
        --server.headless true \
        --browser.gatherUsageStats false \
        >> "$streamlit_log" 2>&1 &
    printf '%s\n' "$!" > "$STATE_DIR/starting.pid"
  )
  pid="$(sed -n '1p' "$STATE_DIR/starting.pid")"
  rm -f "$STATE_DIR/starting.pid"
  record_state "$pid" "$port"

  attempts=0
  while [ "$attempts" -lt 120 ]; do
    if is_healthy "$port"; then
      log_message "Career Catalyst healthy pid=$pid url=$url"
      open_url "$url"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      show_error "Career Catalyst stopped during startup. See: $streamlit_log"
      return 1
    fi
    attempts=$((attempts + 1))
    sleep 0.5
  done

  show_error "Career Catalyst did not become healthy. See: $streamlit_log"
  return 1
}

if [ "${CAREER_CATALYST_SOURCE_ONLY:-0}" != "1" ]; then
  main "$@"
fi
