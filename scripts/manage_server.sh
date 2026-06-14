#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_SCRIPT="$ROOT_DIR/scripts/start_server.sh"
LOG_DIR="$ROOT_DIR/server/logs"
LOG_FILE="$LOG_DIR/server.log"
PID_FILE="$LOG_DIR/server.pid"

mkdir -p "$LOG_DIR"

get_dashboard_ip() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -n "$ip" ]]; then
    printf '%s\n' "$ip"
  else
    printf '127.0.0.1\n'
  fi
}

get_running_pid() {
  local pid

  if [[ -f "$PID_FILE" ]]; then
    pid="$(tr -d '[:space:]' < "$PID_FILE" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" >/dev/null 2>&1; then
      printf '%s\n' "$pid"
      return 0
    fi
  fi

  pid="$(pgrep -f 'server/app.py --host 0.0.0.0 --port 8443' | head -n 1 || true)"
  if [[ -n "$pid" ]]; then
    printf '%s\n' "$pid"
  fi
}

start_server() {
  local pid
  pid="$(get_running_pid || true)"
  if [[ -n "$pid" ]]; then
    echo "Server already running with PID $pid"
    echo "Dashboard: https://$(get_dashboard_ip):8443/"
    return 0
  fi

  setsid "$START_SCRIPT" < /dev/null >> "$LOG_FILE" 2>&1 &
  sleep 2
  pid="$(get_running_pid || true)"

  if [[ -n "$pid" ]] && ps -p "$pid" >/dev/null 2>&1; then
    echo "$pid" > "$PID_FILE"
    echo "Server started with PID $pid"
    echo "Dashboard: https://$(get_dashboard_ip):8443/"
    echo "Log file: $LOG_FILE"
    return 0
  fi

  rm -f "$PID_FILE"
  echo "Server failed to start. Last log lines:" >&2
  tail -n 30 "$LOG_FILE" >&2 || true
  return 1
}

stop_server() {
  local pid
  pid="$(get_running_pid || true)"
  if [[ -z "$pid" ]]; then
    echo "Server is not running"
    rm -f "$PID_FILE"
    return 0
  fi

  kill "$pid"
  sleep 2
  if ps -p "$pid" >/dev/null 2>&1; then
    kill -9 "$pid"
  fi

  rm -f "$PID_FILE"
  echo "Server stopped"
}

status_server() {
  local pid
  pid="$(get_running_pid || true)"
  if [[ -n "$pid" ]]; then
    echo "Server is running with PID $pid"
    echo "Dashboard: https://$(get_dashboard_ip):8443/"
    echo "Log file: $LOG_FILE"
    return 0
  fi

  echo "Server is stopped"
  echo "Log file: $LOG_FILE"
  return 1
}

open_dashboard() {
  xdg-open "https://$(get_dashboard_ip):8443/" >/dev/null 2>&1 &
}

show_log() {
  touch "$LOG_FILE"
  tail -n 40 "$LOG_FILE"
}

case "${1:-status}" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  restart)
    stop_server || true
    start_server
    ;;
  status)
    status_server
    ;;
  log)
    show_log
    ;;
  open-dashboard)
    open_dashboard
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|log|open-dashboard}" >&2
    exit 1
    ;;
esac
