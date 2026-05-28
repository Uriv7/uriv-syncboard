# 🖊 uriv-syncboard

**Smart Whiteboard Assistant** — Computer Vision · Real-time OCR · Multi-format Export

| Layer | Stack |
|-------|-------|
| **Frontend** | React 18 · TypeScript · Vite · Tailwind CSS |
| **Backend** | FastAPI · Python 3.11 · WebSockets · asyncio |
| **OCR** | PaddleOCR (primary) · Tesseract (fallback) |
| **Database** | PostgreSQL 16 (async via SQLAlchemy 2 + asyncpg) |
| **Infrastructure** | Docker · Docker Compose |

---

## Architecture

```
Browser  ←──WebSocket──→  FastAPI /ws
                              │
                    ┌─────────┴──────────┐
                    │  CaptureOrchestrator│
                    │  ┌───────────────┐ │
                    │  │ CameraStream  │ │  ← Webcam / Video / Images
                    │  └──────┬────────┘ │
                    │  ┌──────▼────────┐ │
                    │  │FrameProcessor │ │  ← PaddleOCR + binarization
                    │  └──────┬────────┘ │
                    │  ┌──────▼────────┐ │
                    │  │ BoardTracker  │ │  ← Frame-diff + text debounce
                    │  └──────┬────────┘ │
                    └─────────┼──────────┘
                              │
                         PostgreSQL
                        (boards / sessions / notes)
```

---

## Project Structure

```
uriv-syncboard/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               ← FastAPI app factory + lifespan
│       ├── api/
│       │   ├── ws.py             ← WebSocket orchestrator (Producer-Consumer)
│       │   └── routes.py         ← REST: sessions list, export, file upload
│       ├── core/
│       │   ├── config.py         ← Pydantic settings (env vars)
│       │   ├── camera.py         ← Stream ingestion (webcam/video/images)
│       │   ├── processor.py      ← PaddleOCR + adaptive binarization pipeline
│       │   └── tracker.py        ← Frame-diff board-clear + text debounce
│       ├── db/
│       │   ├── session.py        ← Async SQLAlchemy engine + get_db()
│       │   └── models.py         ← Board / Session / Note ORM models
│       └── services/
│           └── exporter.py       ← PDF / DOCX / PPTX / MD / TXT / JSON
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── src/
        ├── main.tsx
        ├── App.tsx               ← Root layout + source controls
        ├── types/index.ts        ← Shared TypeScript types
        ├── api/socket.ts         ← WebSocket singleton + auto-reconnect
        ├── hooks/useSocket.ts    ← React hook: WS state → component state
        └── components/
            ├── CanvasROI.tsx     ← Live feed canvas + drag-to-select ROI
            └── LiveNotes.tsx     ← OCR output + pages list + export grid
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose v2
- Webcam attached (for live capture; video/images work without one)

### 1 · Clone & configure

```bash
git clone <your-repo>
cd uriv-syncboard
cp .env.example .env          # edit passwords if needed
```

### 2 · Build & run

```bash
docker compose up --build
```

Services spin up:

| Service  | URL                        |
|----------|----------------------------|
| Frontend | http://localhost:5173      |
| Backend  | http://localhost:8000      |
| API docs | http://localhost:8000/docs |
| DB       | localhost:5432             |

### 3 · First run walkthrough

1. Open **http://localhost:5173**
2. Click **📷 Webcam** (or **🎬 Video** / **🖼 Images**)
3. The live feed appears. **Drag a rectangle** around the whiteboard to set ROI.
4. Click **🔄 Set Reference** while showing a clean, empty board.
5. Tick **Auto-detect clears** — every time you wipe the board the app auto-saves.
6. Or click **📸 Capture Page** manually at any time.
7. Use the **Export** grid to download the session as PDF, Word, PowerPoint, Markdown, TXT, or JSON.

---

## Running Without Docker (dev mode)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start Postgres separately (or use Docker for just the DB):
docker compose up postgres -d

# Run backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## WebSocket Protocol

### Client → Server

| Message type    | Payload                        | Effect                              |
|-----------------|--------------------------------|-------------------------------------|
| `start_webcam`  | `device_index?`                | Open webcam stream                  |
| `start_video`   | `path`                         | Open video file                     |
| `start_images`  | `paths[]`                      | Batch-process images                |
| `stop`          | —                              | Stop capture                        |
| `set_roi`       | `x, y, w, h`                   | Crop region for OCR                 |
| `clear_roi`     | —                              | Remove crop                         |
| `capture_page`  | —                              | Save current frame as a page        |
| `set_reference` | —                              | Store current frame as "clean board"|
| `toggle_auto`   | `enabled`                      | Enable/disable auto-clear detection |
| `delete_page`   | `page_id`                      | Remove page from session            |
| `new_session`   | —                              | Start fresh session                 |

### Server → Client

| Message type     | Key fields                                  |
|------------------|---------------------------------------------|
| `frame`          | `data` (base64 JPEG)                        |
| `ocr_update`     | `text`, `confidence`, `lines[]`             |
| `page_captured`  | `page` {seq, text, confidence, timestamp}   |
| `board_cleared`  | —                                           |
| `text_stable`    | `text`                                      |
| `session_update` | `session` {name, page_count, pages[]}       |
| `status`         | `message`, `level` (info/success/error)     |

---

## Database Schema

```sql
boards
  id UUID PK, name VARCHAR, created_at TIMESTAMPTZ

sessions
  id UUID PK, board_id FK→boards, name VARCHAR,
  started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ?

notes                            -- one row per captured page
  id UUID PK, session_id FK→sessions,
  sequence_order INT,            -- timeline ordering
  ocr_text TEXT, confidence FLOAT,
  image_data BYTEA,              -- raw PNG
  created_at TIMESTAMPTZ
```

---

## Configuration Reference

All settings live in `backend/app/core/config.py` and are overridable via env:

| Variable           | Default | Description                                |
|--------------------|---------|--------------------------------------------|
| `DATABASE_URL`     | —       | Async Postgres DSN                         |
| `OCR_ENGINE`       | paddle  | `paddle` or `tesseract`                    |
| `MIN_CONFIDENCE`   | 40      | Word confidence floor (0-100)              |
| `CLEAR_THRESHOLD`  | 0.05    | Diff ratio to trigger board-clear (0-1)    |
| `OCR_WIDTH`        | 1280    | Resize width before OCR                    |
| `OCR_INTERVAL`     | 0.6     | Seconds between OCR passes                 |
| `DEBOUNCE_FRAMES`  | 3       | Stable frames before TEXT_STABLE fires     |
| `FPS_CAP`          | 30      | Max stream FPS                             |

---

## Export Formats

| Format     | Content                                                          |
|------------|------------------------------------------------------------------|
| **PDF**    | A4 report — cover page, one section per capture with image + text |
| **DOCX**   | Word document — heading per page, embedded image, body text       |
| **PPTX**   | 16:9 slides — image left, OCR text right                          |
| **Markdown**| GitHub-compatible — headers, metadata front-matter, text blocks  |
| **TXT**    | Plain separator-delimited dump — paste anywhere                   |
| **JSON**   | Structured array — pipe into databases, LLMs, or other tools      |

---

## Extending

- **Multi-language OCR** — set `lang` in `_PaddleAdapter.__init__` (e.g. `"hi"` for Hindi)
- **GPU acceleration** — set `use_gpu=True` in PaddleOCR init and uncomment CUDA in Dockerfile
- **Object storage** — swap `image_data BYTEA` in `Note` for a `image_url VARCHAR` + S3 upload in `ws.py`
- **Alembic migrations** — `cd backend && alembic init migrations && alembic revision --autogenerate`
