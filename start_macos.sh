#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  SyncBoard — macOS Recommended Startup Script
#
#  What this does:
#    1. Starts PostgreSQL via Docker (just the DB container)
#    2. Runs the FastAPI backend LOCALLY so it can access your Mac webcam
#    3. Runs the Vite frontend LOCALLY
#
#  Prerequisites (run once):
#    brew install tesseract
#    brew install --cask docker        # if not installed
#
#  Usage:
#    chmod +x start_macos.sh
#    ./start_macos.sh
# ══════════════════════════════════════════════════════════════

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${GREEN}▶ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $1${NC}"; }
err()   { echo -e "${RED}✗ $1${NC}"; exit 1; }
step()  { echo -e "\n${BOLD}── $1 ──${NC}"; }

echo ""
echo -e "${BOLD}╔═══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   SyncBoard  •  macOS Startup          ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────────
step "Checking prerequisites"
# ─────────────────────────────────────────────────────────────

# Python 3.10+
if ! command -v python3 &>/dev/null; then
  err "Python 3 not found.\n  Install: brew install python"
fi
PY=$(command -v python3)
PY_VER=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $PY_VER found."

# Tesseract
if ! command -v tesseract &>/dev/null; then
  err "Tesseract not installed.\n\n  Run:  brew install tesseract\n\n  Then re-run this script."
fi
TESS_VER=$(tesseract --version 2>&1 | head -1)
info "Tesseract found: $TESS_VER"

# Node.js
if ! command -v node &>/dev/null; then
  err "Node.js not found.\n  Install: brew install node"
fi
info "Node $(node --version) found."

# Docker (for Postgres only)
if ! command -v docker &>/dev/null; then
  warn "Docker not found — PostgreSQL won't start."
  warn "The app still works but session data won't be persisted."
  SKIP_DB=1
fi

# ─────────────────────────────────────────────────────────────
step "Starting PostgreSQL (Docker)"
# ─────────────────────────────────────────────────────────────

if [ -z "$SKIP_DB" ]; then
  # Only start the postgres service
  docker compose up postgres -d
  info "Waiting for PostgreSQL to be ready…"
  for i in $(seq 1 20); do
    if docker compose exec -T postgres pg_isready -U syncboard &>/dev/null 2>&1; then
      info "PostgreSQL is ready."
      break
    fi
    sleep 1
    if [ "$i" -eq 20 ]; then
      warn "PostgreSQL didn't become ready in time — continuing anyway."
    fi
  done
fi

# ─────────────────────────────────────────────────────────────
step "Setting up Python virtual environment"
# ─────────────────────────────────────────────────────────────

cd backend

if [ ! -d ".venv" ]; then
  info "Creating virtual environment…"
  $PY -m venv .venv
fi

source .venv/bin/activate
info "Virtual environment activated."

info "Installing Python dependencies (first run may take ~60s)…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
info "Python dependencies ready."

# ─────────────────────────────────────────────────────────────
step "Writing backend .env"
# ─────────────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
cat > .env << 'ENVEOF'
DATABASE_URL=postgresql+asyncpg://syncboard:syncboard_secret@localhost:5432/syncboard
OCR_ENGINE=tesseract
MIN_CONFIDENCE=30
CLEAR_THRESHOLD=0.05
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173
ENVEOF
  info "Created backend/.env"
else
  info "backend/.env already exists — skipping."
fi

# ─────────────────────────────────────────────────────────────
step "Starting FastAPI backend (local — webcam access enabled)"
# ─────────────────────────────────────────────────────────────

uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --log-level info \
  > /tmp/syncboard_backend.log 2>&1 &

BACKEND_PID=$!
info "Backend PID $BACKEND_PID — waiting for startup…"

# Wait until /health responds
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health &>/dev/null; then
    info "Backend is up: http://localhost:8000"
    break
  fi
  sleep 1
  if [ "$i" -eq 20 ]; then
    warn "Backend didn't respond in time. Check /tmp/syncboard_backend.log"
    cat /tmp/syncboard_backend.log | tail -20
  fi
done

cd ..

# ─────────────────────────────────────────────────────────────
step "Setting up frontend"
# ─────────────────────────────────────────────────────────────

cd frontend

if [ ! -d "node_modules" ]; then
  info "Installing npm packages (first run may take ~30s)…"
  npm install
else
  info "node_modules present — skipping npm install."
fi

info "Starting Vite dev server…"
npm run dev > /tmp/syncboard_frontend.log 2>&1 &
FRONTEND_PID=$!

# Wait for Vite to be ready
for i in $(seq 1 15); do
  if curl -sf http://localhost:5173 &>/dev/null; then
    info "Frontend is up: http://localhost:5173"
    break
  fi
  sleep 1
done

cd ..

# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  🎉  SyncBoard is running!                   ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  Open in browser:                           ║${NC}"
echo -e "${GREEN}║    http://localhost:5173                     ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  Backend API docs:                          ║${NC}"
echo -e "${GREEN}║    http://localhost:8000/docs                ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  Logs:                                      ║${NC}"
echo -e "${GREEN}║    tail -f /tmp/syncboard_backend.log        ║${NC}"
echo -e "${GREEN}║    tail -f /tmp/syncboard_frontend.log       ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║  Press Ctrl+C to stop all services          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""

trap "
  echo ''
  info 'Stopping SyncBoard…'
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  info 'Done.'
" EXIT INT TERM

wait $BACKEND_PID $FRONTEND_PID
