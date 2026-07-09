#!/usr/bin/env bash
# One-click local dev launcher for the AI Coach platform + prompt-optimizer.
#
# Starts, in order:
#   1. AAD token-injecting proxy (host)      -> :PROXY_PORT   (Entra ID for OpenAI)
#   2. prompt-optimizer sidecar (container)   -> :OPTIMIZER_PORT
#   3. FastAPI backend (host, uvicorn)        -> :BACKEND_PORT
#   4. Vite frontend (host)                   -> :FRONTEND_PORT
#
# Why a script (not just docker-compose):
#   * Port 8000 is occupied by an unrelated container, so the backend runs on 8100.
#   * The Foundry resource has API-key auth disabled, so the optimizer must reach
#     Azure OpenAI through an Entra ID token proxy that reuses the host `az login`.
#
# Usage:   scripts/dev-up.sh          (start everything)
#          scripts/dev-down.sh        (stop everything)
# Config:  override via env, e.g.  BACKEND_PORT=8200 scripts/dev-up.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ---- Config (override via env) ----------------------------------------------
BACKEND_PORT="${BACKEND_PORT:-8100}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
OPTIMIZER_PORT="${OPTIMIZER_PORT:-8188}"
PROXY_PORT="${PROXY_PORT:-8199}"
OPTIMIZER_IMAGE="${OPTIMIZER_IMAGE:-linshen/prompt-optimizer:2.11.7}"
OPTIMIZER_NAME="prompt-optimizer-dev"

RUN_DIR="$ROOT/.dev"
mkdir -p "$RUN_DIR"

# ---- Read specific keys from backend/.env (do NOT source: values may contain
# unquoted spaces which would break shell parsing) ---------------------------
read_env() { # read_env <KEY>
  [ -f backend/.env ] || return 0
  sed -n "s/^$1=//p" backend/.env | tail -1
}

UPSTREAM_BASE="${AOAI_UPSTREAM_BASE:-$(read_env AZURE_FOUNDRY_ENDPOINT)}"
UPSTREAM_BASE="${UPSTREAM_BASE:-https://ai-foundry-svc2.services.ai.azure.com}"
UPSTREAM_BASE="${UPSTREAM_BASE%/}"
MODEL="$(read_env AZURE_OPENAI_DEPLOYMENT)"
MODEL="${MODEL:-gpt-4o}"

VENV_PY="$ROOT/backend/.venv/bin/python"
UVICORN="$ROOT/backend/.venv/bin/uvicorn"

log()  { printf '\033[1;36m[dev-up]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[dev-up]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[dev-up]\033[0m %s\n' "$*" >&2; exit 1; }

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- ; }

wait_for() { # wait_for <port> <label> <max_tries>
  local port="$1" label="$2" tries="${3:-40}" i=0
  while ! port_open "$port"; do
    i=$((i + 1)); [ "$i" -ge "$tries" ] && die "$label did not open :$port in time"
    sleep 0.5
  done
  log "$label ready on :$port"
}

start_bg() { # start_bg <name> <logfile> <cmd...>
  local name="$1" logfile="$2"; shift 2
  nohup "$@" >"$logfile" 2>&1 &
  echo $! >"$RUN_DIR/$name.pid"
  log "$name started (pid $(cat "$RUN_DIR/$name.pid"), log: ${logfile#$ROOT/})"
}

# ---- Preconditions ----------------------------------------------------------
[ -x "$VENV_PY" ] || die "backend venv missing: $VENV_PY (run: cd backend && python -m venv .venv && pip install -e '.[dev]')"
command -v docker >/dev/null || die "docker not found"
if ! az account show >/dev/null 2>&1; then
  warn "az CLI not logged in. The AAD proxy needs Entra ID — run 'az login' or prompt optimization will 401."
fi

# ---- 1. AAD token-injecting proxy ------------------------------------------
if port_open "$PROXY_PORT"; then
  log "AAD proxy already listening on :$PROXY_PORT (reusing)"
else
  AOAI_UPSTREAM_BASE="$UPSTREAM_BASE" AOAI_PROXY_PORT="$PROXY_PORT" \
    start_bg aoai-proxy "$RUN_DIR/aoai-proxy.log" \
      "$VENV_PY" "$ROOT/backend/scripts/aoai_aad_proxy.py"
  wait_for "$PROXY_PORT" "AAD proxy"
fi

# ---- 2. prompt-optimizer sidecar -------------------------------------------
docker rm -f "$OPTIMIZER_NAME" >/dev/null 2>&1 || true
docker run -d --name "$OPTIMIZER_NAME" -p "$OPTIMIZER_PORT:80" \
  --add-host=host.docker.internal:host-gateway \
  -e MCP_DEFAULT_MODEL_PROVIDER=custom \
  -e MCP_DEFAULT_LANGUAGE=zh \
  -e VITE_CUSTOM_API_BASE_URL="http://host.docker.internal:$PROXY_PORT/openai/v1" \
  -e VITE_CUSTOM_API_KEY="aad-proxy-placeholder" \
  -e VITE_CUSTOM_API_MODEL="$MODEL" \
  "$OPTIMIZER_IMAGE" >/dev/null
log "optimizer container '$OPTIMIZER_NAME' started -> :$OPTIMIZER_PORT (model=$MODEL)"
wait_for "$OPTIMIZER_PORT" "optimizer"

# ---- 3. Backend -------------------------------------------------------------
if port_open "$BACKEND_PORT"; then
  warn "backend port :$BACKEND_PORT already in use — not starting a second backend"
else
  ( cd "$ROOT/backend" && PROMPT_OPTIMIZER_MCP_URL="http://localhost:$OPTIMIZER_PORT/mcp" \
      start_bg backend "$RUN_DIR/backend.log" \
        "$UVICORN" app.main:app --reload --port "$BACKEND_PORT" )
  wait_for "$BACKEND_PORT" "backend"
fi

# ---- 4. Frontend ------------------------------------------------------------
if port_open "$FRONTEND_PORT"; then
  warn "frontend port :$FRONTEND_PORT already in use — not starting a second frontend"
else
  ( cd "$ROOT/frontend" && VITE_PROXY_TARGET="http://localhost:$BACKEND_PORT" \
      start_bg frontend "$RUN_DIR/frontend.log" \
        npm run dev -- --port "$FRONTEND_PORT" --strictPort )
  wait_for "$FRONTEND_PORT" "frontend"
fi

printf '\n\033[1;32mAll services up:\033[0m\n'
printf '  Frontend   http://localhost:%s\n' "$FRONTEND_PORT"
printf '  Backend    http://localhost:%s   (health: /api/health)\n' "$BACKEND_PORT"
printf '  Optimizer  http://localhost:%s (MCP: /mcp)\n' "$OPTIMIZER_PORT"
printf '  AAD proxy  http://localhost:%s     -> %s\n' "$PROXY_PORT" "$UPSTREAM_BASE"
printf '\nLogs in .dev/*.log   |   Stop with: scripts/dev-down.sh\n'
