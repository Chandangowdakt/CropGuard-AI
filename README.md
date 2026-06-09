# CropGuard AI

**AI-powered plantation monitoring platform for Indian farmers.**

CropGuard AI is a full-stack SaaS dashboard that wraps your chrysanthemum disease-detection model in a production-ready web application: FastAPI backend, SQLite database, JWT authentication, role-based access (farmer / manager / admin), and a React 18 single-page frontend served from CDN.

---

## Features

| Area | Capabilities |
|------|----------------|
| **Authentication** | Register, login, JWT sessions (7-day tokens), farmer / manager / admin roles |
| **Farmer Dashboard** | Stats, health chart, recent alerts, quick photo analysis |
| **My Farms** | Farm cards, add farm modal, farm detail page with detection history |
| **Plant Analysis** | Drag-and-drop upload, AI preview, save to farm, analysis history |
| **Alerts** | Filterable alert cards, notification bell, mark read, image modal |
| **Reports** | Date-range farm health reports, HTML export, quick week/month reports |
| **Admin** | Platform stats, all farms/users tables, 7-day trends, live activity feed |
| **AI Engine** | MobileNetV2 — healthy, diseased, pest_affected, water_stressed |

---

## Prerequisites

- **Windows 10/11** (primary target; macOS/Linux also work)
- **Python 3.11+** (tested on Python 3.14)
- **pip** package manager
- Trained model file: `chrysanthemum_model.pth` (see [Connect your model](#connect-your-chrysanthemum_modelpth) below)

---

## Quick start (Windows)

### Option A — One-click launcher

Double-click **`start.bat`** in the project root. It will:

1. Open **Window 1** — FastAPI backend on port **8000**
2. Open **Window 2** — Python `http.server` frontend on port **5500**
3. Wait 3 seconds, then open both URLs in your browser

### Option B — Manual setup (step by step)

#### Step 1 — Clone / open the project

```powershell
cd C:\Users\ktcha\Downloads\cropguard-ai
```

#### Step 2 — Install backend dependencies

```powershell
cd backend
pip install -r requirements.txt
```

Or install packages directly:

```powershell
pip install fastapi uvicorn sqlalchemy pydantic python-jose passlib bcrypt python-multipart pillow torch torchvision python-dotenv aiofiles
```

#### Step 3 — Seed demo data (first time only)

From the project root:

```powershell
python backend\seed.py
```

Or from the backend folder:

```powershell
cd backend
python seed.py
```

#### Step 4 — Start the backend

```powershell
cd backend
python main.py
```

You should see the CropGuard AI startup banner with URLs, database path, and model status.

#### Step 5 — Start the frontend (separate terminal)

```powershell
cd frontend
python -m http.server 5500
```

#### Step 6 — Open in browser

| URL | Purpose |
|-----|---------|
| http://localhost:5500 | **Frontend UI** (recommended for development) |
| http://localhost:8000 | Backend + embedded frontend |
| http://localhost:8000/docs | **FastAPI interactive API docs** |

> The frontend on port **5500** automatically calls the API at **http://localhost:8000**.

---

## Default login credentials

Created by `seed.py`:

| Email | Password | Role |
|-------|----------|------|
| `admin@cropguard.ai` | `admin123` | admin — Platform Admin dashboard |
| `farmer@cropguard.ai` | `farmer123` | farmer — Demo farmer account |
| `manager@cropguard.ai` | `manager123` | manager — Manages assigned farms |

You can also register new farmer accounts from the login screen.

---

## Connect your chrysanthemum_model.pth

CropGuard loads the fine-tuned MobileNetV2 model from your **ai engine** project.

**Default path (Windows):**

```
C:\Users\ktcha\Downloads\ai engine\chrysanthemum_ai\models\chrysanthemum_model.pth
```

**Override with an environment variable:**

```powershell
set CROPGUARD_MODEL_PATH=C:\path\to\your\chrysanthemum_model.pth
cd backend
python main.py
```

**Train or retrain the model** using the linked project:

```powershell
cd "C:\Users\ktcha\Downloads\ai engine"
python phase4_train.py
```

Then restart the CropGuard backend. The startup banner shows **LOADED** or **NOT FOUND** for the model.

---

## File structure

```
cropguard-ai/
├── start.bat                 # Windows one-click launcher
├── README.md                 # This file
│
├── backend/                  # FastAPI API server
│   ├── main.py               # App entry point + startup banner
│   ├── database.py           # SQLite connection (cropguard.db)
│   ├── models.py             # SQLAlchemy tables
│   ├── schemas.py            # Pydantic request/response models
│   ├── auth.py               # JWT + bcrypt authentication
│   ├── ai_engine.py          # Loads chrysanthemum_model.pth
│   ├── seed.py               # Demo users, farms, detections
│   ├── requirements.txt      # Python dependencies
│   ├── cropguard.db          # SQLite database (auto-created)
│   ├── storage/
│   │   ├── uploads/          # Uploaded analysis images
│   │   └── flagged/          # Alert snapshot images
│   └── routers/
│       ├── users.py          # Auth + admin routes
│       ├── farms.py          # Farm CRUD + stats
│       ├── detections.py     # AI analyze/save/report
│       └── alerts.py         # Alerts + notifications
│
└── frontend/                 # React 18 SPA (CDN, no npm build)
    ├── index.html            # Entry HTML
    ├── app.js                # All React components
    └── styles.css            # Design system + layouts
```

---

## API endpoints reference

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register (name, email, password, role) |
| POST | `/api/auth/login` | Login with JSON email + password |
| GET | `/api/auth/me` | Current user (Bearer token) |

### Farms

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/farms/` | List accessible farms |
| POST | `/api/farms/` | Create farm |
| GET | `/api/farms/{id}` | Farm details |
| GET | `/api/farms/{id}/stats` | Health stats per farm |
| PUT | `/api/farms/{id}` | Update farm |
| DELETE | `/api/farms/{id}` | Delete farm |

### Detections / AI

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/detections/analyze` | Upload image → AI preview (no save) |
| POST | `/api/detections/save` | Save confirmed result to farm |
| GET | `/api/detections/farm/{id}` | Detection history for farm |
| GET | `/api/detections/recent` | Last 20 detections |
| GET | `/api/detections/stats` | Global detection stats |
| GET | `/api/detections/report` | Farm report (`?farm_id=&from=&to=`) |
| GET | `/api/detections/{id}/image` | Detection image file |

### Alerts

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/alerts/` | List alerts (`?filter=all\|unread\|diseased\|pest`) |
| GET | `/api/alerts/stats` | Alert statistics |
| GET | `/api/alerts/unread/count` | Unread count for notification bell |
| PUT | `/api/alerts/mark-all-read` | Mark all alerts read |
| PUT | `/api/alerts/{id}/read` | Mark single alert read |
| GET | `/api/alerts/{id}/image` | Flagged alert image |

### Admin (admin role only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/stats` | Platform-wide statistics |
| GET | `/api/admin/all-farms` | All farms with health status |
| GET | `/api/admin/all-users` | All users with farm counts |
| GET | `/api/admin/activity-feed` | Last 20 detections platform-wide |
| PUT | `/api/admin/users/{id}/role` | Change farmer ↔ manager |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check + AI model status |

Full interactive docs: **http://localhost:8000/docs**

---

## Troubleshooting

### `python` is not recognized

Install Python from [python.org](https://www.python.org/downloads/) and check **“Add Python to PATH”** during installation. Restart Command Prompt.

### `pip install` fails on torch

Install CPU-only PyTorch first:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

### AI Model shows NOT FOUND

1. Verify the file exists:
   ```
   C:\Users\ktcha\Downloads\ai engine\chrysanthemum_ai\models\chrysanthemum_model.pth
   ```
2. Or set `CROPGUARD_MODEL_PATH` to your `.pth` file path.
3. Run `python phase4_train.py` in the ai engine project if the model was never trained.

### Frontend on :5500 cannot reach API

- Ensure the **backend is running** on port 8000 first.
- The frontend automatically uses `http://localhost:8000` when served on port 5500.
- Check CORS is not blocked by a firewall.

### Port 8000 or 5500 already in use

```powershell
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

Or change the port in `backend/main.py` (uvicorn) and `start.bat`.

### Login returns 401 / 422

1. Run `python backend\seed.py` to create demo users.
2. Use exact credentials: `farmer@cropguard.ai` / `farmer123`
3. Restart the backend after code updates.

### passlib / bcrypt errors on Python 3.14

CropGuard uses a native bcrypt fallback in `auth.py`. Ensure `bcrypt` is installed:

```powershell
pip install bcrypt passlib
```

### Database schema out of date

Delete `backend\cropguard.db` and re-run:

```powershell
python backend\seed.py
```

### Blank page on localhost:5500

Serve from the **frontend** folder (not project root):

```powershell
cd frontend
python -m http.server 5500
```

---

## Production notes

Before deploying to real farmers:

1. Set `JWT_SECRET` environment variable (see `backend/auth.py`)
2. Change default admin and demo passwords
3. Use HTTPS behind nginx or similar
4. Consider PostgreSQL instead of SQLite at scale
5. Add email/SMS alerts (Gmail integration from your phase5 engine)

---

## Linked AI engine project

```
C:\Users\ktcha\Downloads\ai engine\chrysanthemum_ai\
```

| Script | Purpose |
|--------|---------|
| `phase4_train.py` | Train / fine-tune MobileNetV2 |
| `phase5_video.py` | Video monitoring + Gmail alerts |
| `live_monitor.py` | Webcam monitoring |

CropGuard AI — built for Indian chrysanthemum farmers.
