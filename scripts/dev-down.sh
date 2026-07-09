#!/usr/bin/env bash
# Stop everything started by scripts/dev-up.sh.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.dev"
OPTIMIZER_NAME="prompt-optimizer-dev"

log() { printf '\033[1;36m[dev-down]\033[0m %s\n' "$*"; }

# Kill host processes by recorded pid (frontend, backend, aad-proxy).
for name in frontend backend aoai-proxy; do
  pidfile="$RUN_DIR/$name.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      # Kill the process group so uvicorn/vite child workers die too.
      pgid="$(ps -o pgid= "$pid" 2>/dev/null | tr -d ' ')"
      if [ -n "$pgid" ]; then kill -TERM "-$pgid" 2>/dev/null || kill "$pid" 2>/dev/null; else kill "$pid" 2>/dev/null; fi
      log "$name stopped (pid $pid)"
    else
      log "$name not running"
    fi
    rm -f "$pidfile"
  fi
done

# Stop the optimizer container.
if docker ps -a --format '{{.Names}}' | grep -qx "$OPTIMIZER_NAME"; then
  docker rm -f "$OPTIMIZER_NAME" >/dev/null 2>&1 && log "optimizer container removed"
fi

log "done"
