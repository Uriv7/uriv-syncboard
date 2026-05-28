@echo off
REM ══════════════════════════════════════════════════════════════
REM  SyncBoard — Windows Local Development Startup
REM  Run: start_local.bat
REM ══════════════════════════════════════════════════════════════

echo.
echo [SyncBoard] Starting local development environment...
echo.

REM ── Check Python ──────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo [SyncBoard] %%i

REM ── Check Node ────────────────────────────────────────────────
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do echo [SyncBoard] Node %%i

REM ── Tesseract check ───────────────────────────────────────────
where tesseract >nul 2>&1
if errorlevel 1 (
    echo [WARN] Tesseract not found.
    echo   Download: https://github.com/UB-Mannheim/tesseract/wiki
    echo   After installing, add to PATH and restart this script.
    pause
)

REM ── Start PostgreSQL ─────────────────────────────────────────
echo [SyncBoard] Starting PostgreSQL...
docker compose up postgres -d 2>nul
timeout /t 2 /nobreak >nul

REM ── Backend ───────────────────────────────────────────────────
echo [SyncBoard] Setting up backend...
cd backend

if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if not exist ".env" (
    echo DATABASE_URL=postgresql+asyncpg://syncboard:syncboard_secret@localhost:5432/syncboard > .env
    echo OCR_ENGINE=tesseract >> .env
    echo MIN_CONFIDENCE=30 >> .env
    echo CORS_ORIGINS=http://localhost:5173,http://localhost:3000 >> .env
    echo [SyncBoard] Created backend\.env
)

echo [SyncBoard] Starting backend...
start "SyncBoard Backend" cmd /k "call .venv\Scripts\activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
cd ..

timeout /t 3 /nobreak >nul

REM ── Frontend ──────────────────────────────────────────────────
echo [SyncBoard] Setting up frontend...
cd frontend
call npm install --silent
echo [SyncBoard] Starting frontend...
start "SyncBoard Frontend" cmd /k "npm run dev"
cd ..

echo.
echo ══════════════════════════════════════════════
echo   SyncBoard is starting!
echo   Frontend : http://localhost:5173
echo   Backend  : http://localhost:8000
echo   API docs : http://localhost:8000/docs
echo ══════════════════════════════════════════════
echo.
echo Two new terminal windows have opened.
echo Close them to stop the services.
echo.
pause
