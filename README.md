# CropGuard AI

AI-powered chrysanthemum plantation monitoring for farmers, field managers, and platform admins.

CropGuard wraps a **3-class leaf disease model** (Bacterial / Healthy / Septoria) in a production web app: FastAPI backend, SQLite, JWT auth with roles, and a React 18 SPA (no npm build). Farmers can upload leaf photos, walk rows with a live camera, or analyze an uploaded video. Confirmed disease can create alerts and optional WhatsApp/email reports.

This README is for a new engineer with zero prior context.

---

## Live deployment

| Surface | URL |
|---------|-----|
| **Frontend (GitHub Pages)** | https://chandangowdakt.github.io/CropGuard-AI/ |
| **Backend API (Render)** | https://cropguard-ai-backend.onrender.com |
| **API docs (when backend is awake)** | https://cropguard-ai-backend.onrender.com/docs |
| **Health check** | https://cropguard-ai-backend.onrender.com/api/health |
| **GitHub repo** | https://github.com/Chandangowdakt/CropGuard-AI |

Demo logins (seeded on empty databases):

| Email | Password | Role |
|-------|----------|------|
| `admin@cropguard.ai` | `admin123` | admin — Platform Admin |
| `farmer@cropguard.ai` | `farmer123` | farmer |
| `manager@cropguard.ai` | `manager123` | manager — scan sessions |

Render’s free tier **spins down** after idle time. The first request after sleep can take 30–60 seconds. If `/api/health` shows `"torch_available": false`, predictions return “uncertain / model unavailable” until PyTorch is installed (Docker image on Render includes CPU torch).

---

## What the product does

1. **Authenticate** — register/login; JWT stored in `localStorage`; roles: `farmer`, `manager`, `admin`.
2. **Manage farms** — CRUD, weather widget (Open-Meteo, no API key), farm-level stats.
3. **Analysis** — upload one or many leaf photos → classify → optionally save to a farm (creates alerts when Bacterial/Septoria and confidence is high).
4. **Leaf Scan** — dedicated close-up leaf UI (`/api/detections/analyze-leaf`).
5. **Live Scan** — phone camera or **uploaded video**; frames go to `/api/scan/analyze-frame` every ~2s (camera) or seek-step ~1.5s (video). Disease is confirmed only after a 3-frame majority at ≥70% confidence. GPS + `plant_zone_id` tag affected plants. End scan → bulk save + complete session (email/WhatsApp).
6. **Alerts / Reports / Admin** — unread bell, HTML reports, scan-session overview, manager-farm assignments.

**Not in this repo:** training scripts. Weights live under `backend/models/`. Training historically lived in a sibling “ai engine” folder; CropGuard only **loads** checkpoints.

---

## Tech stack

### Backend

| Piece | Choice |
|-------|--------|
| Runtime | Python 3.11 recommended (Render Docker). Local 3.12–3.14 can work; torch wheels may fail on 3.14. |
| API | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| ORM / DB | SQLAlchemy 2 + **SQLite** (`backend/cropguard.db`; on Render: `/tmp/cropguard.db`) |
| Auth | JWT (`python-jose`), bcrypt (`passlib` + native `bcrypt` fallback) |
| Images | Pillow |
| Model | PyTorch MobileNetV2, CPU. **Not** in `requirements.txt` — install separately locally; Docker `build.sh` installs CPU torch 2.4.1 |
| Weather | Open-Meteo HTTP (cached 60 minutes) |
| Alerts | Optional Twilio WhatsApp + SMTP email |

### Frontend

| Piece | Choice |
|-------|--------|
| UI | React 18 (UMD from unpkg) |
| JSX | Babel standalone — `index.html` fetches `app.js` and transforms it in the browser |
| Styling | Single `styles.css` (no Tailwind/build step) |
| Package manager | **None.** No `package.json`, no webpack, no Vite |
| API base | `localhost` → `http://localhost:8001`; otherwise `https://cropguard-ai-backend.onrender.com` |

**Important:** `frontend/app.js` must **not** use ES module `import`/`export` at line start. Babel classic runtime + `<script>` injection cannot load modules.

### Deploy

- Frontend: GitHub Actions → `gh-pages` branch from `./frontend` (`.github/workflows/deploy.yml`).
- Backend: Render **Docker** (`backend/Dockerfile`, root `render.yaml`).

---

## Architecture (high level)

```
Browser (GitHub Pages or localhost:5500)
    │  JWT Bearer
    ▼
FastAPI (localhost:8001 or Render)
    ├── /api/auth, /api/farms, /api/detections, /api/alerts, /api/admin
    ├── /api/scan  (live/video walk — analyze-frame has no DB write)
    ├── ai_engine.py     → chrysanthemum_leaf_model.pth  (3-class, primary)
    ├── leaf_engine.py   → same leaf weights for Leaf Scan page
    └── SQLite + storage/uploads, storage/flagged, storage/scan_flags
```

Live Scan flow:

1. `POST /api/scan/sessions` — create session  
2. `POST /api/scan/analyze-frame` — JPEG + optional GPS (no persist)  
3. `POST /api/scan/sessions/{id}/detections` — bulk save evidence  
4. `POST /api/scan/sessions/{id}/complete` — counters + reporting  

Center-crop (`leaf_focus.py`) runs only on the scan analyze path. Analysis / Leaf Scan pages are unchanged.

---

## Repository layout

```
cropguard-ai/
├── README.md
├── start.bat                      # Windows: backend :8001 + frontend :5500
├── render.yaml                    # Render Docker service
├── runtime.txt                    # Hint: python-3.11.9 (Docker is source of truth)
├── .github/workflows/deploy.yml   # Pages deploy of ./frontend
│
├── frontend/                      # Static SPA (this folder is published to Pages)
│   ├── index.html                 # React + Babel CDN, boots app.js
│   ├── app.js                     # Entire UI (login, dashboard, farms, analysis,
│   │                              #   leaf scan, live scan, alerts, reports, admin)
│   ├── styles.css
│   └── favicon.ico
│
└── backend/
    ├── main.py                    # FastAPI app, CORS, mounts frontend if present
    ├── requirements.txt           # App deps (no torch)
    ├── Dockerfile + build.sh      # CPU torch + pip install
    ├── .env.example               # Copy to .env
    ├── seed.py                    # Demo users/farms (also auto-runs if DB empty)
    ├── database.py                # SQLite + lightweight ALTER migrations
    ├── models.py                  # User, Farm, Detection, Alert, ScanSession, …
    ├── schemas.py                 # Request/response models
    ├── auth.py                    # JWT, roles, farm access
    ├── class_constants.py         # Bacterial / Healthy / Septoria (+ legacy map)
    ├── ai_engine.py               # Primary leaf model + optional shadow v2 logging
    ├── leaf_engine.py             # Leaf Scan inference
    ├── leaf_focus.py              # Center-crop for Live Scan frames
    ├── scan_smoothing.py          # 3-frame majority + plant_zone_id
    ├── weather.py
    ├── email_alerts.py / whatsapp_alerts.py / scan_reporting.py
    ├── routers/
    │   ├── users.py               # /api/auth, /api/users, /api/admin
    │   ├── farms.py               # /api/farms
    │   ├── detections.py          # /api/detections (analyze, batch, leaf, save)
    │   ├── scan.py                # /api/scan
    │   └── alerts.py              # /api/alerts
    ├── models/                    # .pth weights (leaf model is git-tracked)
    └── storage/                   # uploads / flagged / scan_flags (gitignored)
```

SQLite file `backend/cropguard.db` is **gitignored**; it is created on first run.

---

## Prerequisites

- Python **3.11** strongly preferred (matches Docker).
- `pip`
- Git
- For AI locally: CPU **PyTorch** + torchvision (see backend setup)
- Optional: Twilio + Gmail app password for alerts

No Node.js required.

---

## Environment variables

Copy `backend/.env.example` → `backend/.env`. FastAPI loads dotenv via `python-dotenv` where used; unset vars fall back to defaults.

| Variable | Required | Purpose |
|----------|----------|---------|
| `JWT_SECRET` | **Production yes** | Signs JWTs. Default is a well-known dev string — change it on Render. |
| `PORT` | Render sets this | Uvicorn listen port. Local default **8001**. |
| `RENDER` | Set by Render | Switches DB path to `/tmp/cropguard.db`. |
| `CROPGUARD_MODEL_PATH` | No | Override path to live `.pth`. |
| `CROPGUARD_MODEL_URL` | No | Download URL if weights missing (used on Render). |
| `CROPGUARD_LEAF_MODEL_PATH` | No | Override Leaf Scan weights. |
| `CROPGUARD_LEAF_MODEL_URL` | No | Download URL for leaf weights. |
| `CROPGUARD_SHADOW_MODEL_PATH` | No | Optional v2 model for logging only (not shown in UI). |
| `TWILIO_SID` | No | WhatsApp via Twilio. All four Twilio vars must be set to send. |
| `TWILIO_TOKEN` | No | |
| `TWILIO_FROM` | No | e.g. `whatsapp:+14155238886` |
| `ALERT_PHONE` | No | Destination, e.g. `whatsapp:+91…` |
| `SMTP_HOST` | No | Default `smtp.gmail.com` |
| `SMTP_PORT` | No | Default `587` |
| `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | No | Email reports |
| `SMTP_USE_TLS` | No | Default `true` |
| `FRONTEND_URL` | No | Links in scan emails. Local: `http://localhost:5500`. Production: GitHub Pages URL. `DASHBOARD_URL` is an alias. |

Frontend has **no** `.env`. API host is hardcoded in `frontend/app.js` (`API_BASE`).

---

## Setup — backend

From a terminal (PowerShell shown):

```powershell
cd C:\Users\ktcha\Downloads\cropguard-ai\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`

### 1. Install PyTorch (CPU) then app deps

```powershell
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

Without torch the API still starts; `/api/health` reports `torch_available: false` and classifications degrade.

### 2. Environment file

```powershell
copy .env.example .env
```

Edit `JWT_SECRET` at minimum if this machine is shared.

### 3. Model weights

Expected file:

```
backend/models/chrysanthemum_leaf_model.pth
```

If missing, the engine may download from `CROPGUARD_MODEL_URL` / GitHub `raw` (file must be > ~5 MB). Confirm on startup banner: **LOADED**.

### 4. Database

First start of `main.py` calls `init_db()` and **auto-seeds** if the user table is empty. To seed explicitly:

```powershell
python seed.py
```

Do **not** commit `cropguard.db`.

### 5. Run the API

```powershell
python main.py
```

| Local URL | Purpose |
|-----------|---------|
| http://localhost:8001 | API (+ serves frontend files if `frontend/` exists) |
| http://localhost:8001/docs | Swagger |
| http://localhost:8001/api/health | Model + torch status |
| http://localhost:8001/api/ping | Liveness |

Stop with Ctrl+C.

---

## Setup — frontend

The frontend is static files. It **must** be served from the `frontend` directory (so `./app.js` and `./styles.css` resolve).

```powershell
cd C:\Users\ktcha\Downloads\cropguard-ai\frontend
python -m http.server 5500
```

Open **http://localhost:5500**.

On `localhost`, `app.js` calls **http://localhost:8001**. Start the backend first.

CORS already allows `http://localhost:5500`. If you use another static port, add it in `backend/main.py` (`CORSMiddleware`) or keep using `*`.

There is no `npm install`, lint script, or production webpack bundle. GitHub Pages hosts these same files.

---

## Run locally (both)

### Windows one-click

Double-click `start.bat` in the repo root. It opens:

1. Backend window → `python main.py` (port **8001**)
2. Frontend window → `python -m http.server 5500`
3. Browser tabs for both

### Two terminals

**Terminal A — backend**

```powershell
cd C:\Users\ktcha\Downloads\cropguard-ai\backend
.\.venv\Scripts\Activate.ps1   # if you created a venv
python main.py
```

**Terminal B — frontend**

```powershell
cd C:\Users\ktcha\Downloads\cropguard-ai\frontend
python -m http.server 5500
```

Log in at http://localhost:5500 with a seed account above.

### Sanity checks

```powershell
# from anywhere, with backend running
curl http://localhost:8001/api/health
```

You want `"status": "ok"` and a loaded leaf model. Then: Dashboard → Analysis (upload a leaf photo) or Live Scan (camera / upload video).

---

## Roles (what you can touch)

| Role | Typical access |
|------|----------------|
| `farmer` | Own farms, analysis, leaf scan, live scan, alerts, reports |
| `manager` | Assigned farms; live walk-through sessions |
| `admin` | Platform Admin: users, all farms, scan sessions, assignments, digest |

Farm access is enforced in `auth.get_farm_for_user` — do not bypass it in new endpoints.

---

## Main API map

Interactive list: http://localhost:8001/docs  

| Prefix | Module | Notes |
|--------|--------|--------|
| `/api/auth` | `routers/users.py` | `POST /register`, `/login`, `GET /me` |
| `/api/farms` | `routers/farms.py` | CRUD, `/stats`, `/weather` |
| `/api/detections` | `routers/detections.py` | `analyze`, `analyze-batch`, `save`, `save-batch`, `analyze-leaf`, history, reports |
| `/api/scan` | `routers/scan.py` | Live/video pipeline |
| `/api/alerts` | `routers/alerts.py` | List, read, images |
| `/api/admin` | `routers/users.py` | Admin-only |
| `/api/health` | `main.py` | Model status |

Auth: `Authorization: Bearer <jwt>`.

---

## Deployment (how production is wired)

### Frontend

Push to `main` → GitHub Action publishes `frontend/` to `gh-pages` → Pages URL above.

After a frontend-only change, hard-refresh the Pages site (CDN cache).

### Backend

Render service `cropguard-ai-backend`, Docker, `rootDir: backend`.

`PORT` is injected. Env vars to set in the Render dashboard (not only `render.yaml`):

- `JWT_SECRET` (required for real security)
- `FRONTEND_URL` = `https://chandangowdakt.github.io/CropGuard-AI`
- Optional Twilio / SMTP
- Model URLs are already in `render.yaml`

SQLite on Render lives under `/tmp` and **does not persist** across deploys/restarts. Empty DB is auto-seeded. For durable production data, migrate to Postgres (not implemented yet).

---

## Conventions for new code

- **Do not** add `import`/`export` at the start of `app.js`.
- Prefer additive API fields (optional Pydantic) over breaking JSON shapes the SPA already sends.
- Live Scan confirmation logic lives in `scan_smoothing.py`; UI should trust `is_problem` from analyze-frame.
- Analysis page and Leaf Scan should not call `leaf_focus` / scan smoothing unless product asks for it.
- Never commit `.env`, `*.db`, or `backend/storage/` uploads.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Blank page on `:5500` | Serve from `frontend/`, not repo root. |
| Login fails / CORS | Backend on **8001**, not 8000. |
| Every prediction “uncertain” | Install CPU torch; confirm `GET /api/health` `torch_available`. |
| `python` not found | Install Python and tick “Add to PATH”. |
| passlib/bcrypt noise on 3.14 | Known; `auth.py` falls back to native bcrypt. |
| Render 503 / long wait | Cold start on free plan. |
| Stale Pages UI | Hard refresh; confirm latest `main` Action succeeded. |
| Schema confusion | `database.py` adds columns with `ALTER TABLE` — avoid dropping columns. Last resort: delete local `cropguard.db` and restart (loses local data). |

---

## Related local training workspace

If you also have the training tree (not this git repo):

```
C:\Users\ktcha\Downloads\ai engine\
```

That folder is for dataset/training experiments. CropGuard production inference uses `backend/models/chrysanthemum_leaf_model.pth` only.

---

CropGuard AI — chrysanthemum leaf monitoring for Indian farms.
