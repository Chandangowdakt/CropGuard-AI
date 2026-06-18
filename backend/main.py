# Run the CropGuard AI backend:
#   cd backend
#   pip install -r requirements.txt
#   python seed.py          (first time — demo data)
#   python main.py
#
# Then open:  http://localhost:8001

import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ai_engine import model_status
from database import DB_PATH, init_db
from routers import alerts, detections, farms, scan, users
from routers.users import admin_router, auth_router

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
STORAGE_DIR = Path(__file__).resolve().parent / "storage"


def _print_startup_banner() -> None:
    status = model_status()
    loaded = status.get("loaded", False)
    model_msg = (
        f"LOADED — {status.get('path', '')}"
        if loaded
        else f"NOT FOUND — {status.get('error', 'unknown')}"
    )

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                                                              ║")
    print("║        CropGuard AI v1.0 — Starting...                       ║")
    print("║        Smart Plantation Monitoring for Indian Farmers        ║")
    print("║                                                              ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Backend URL  : http://localhost:8001                        ║")
    print("║  API Docs     : http://localhost:8001/docs                   ║")
    print("║  Frontend     : http://localhost:5500  (python http.server)  ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"  Database     : SQLite — {DB_PATH}")
    print(f"  AI Model     : {model_msg}")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Admin login  : admin@cropguard.ai / admin123                ║")
    print("║  Farmer demo  : farmer@cropguard.ai / farmer123              ║")
    print("║  Seed data    : python seed.py  (first-time setup)           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    (STORAGE_DIR / "uploads").mkdir(exist_ok=True)
    (STORAGE_DIR / "flagged").mkdir(exist_ok=True)
    _print_startup_banner()
    yield


app = FastAPI(
    title="CropGuard AI",
    description="AI-powered plantation monitoring for Indian farmers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://localhost:3000",
        "http://localhost:8001",
        "https://chandangowdakt.github.io",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth + admin + user management (admin_router defines /api/admin/* routes)
app.include_router(auth_router)
app.include_router(admin_router)   # GET /api/admin/stats, all-farms, all-users, activity-feed
app.include_router(users.router)   # GET /api/users/ (admin user list)
app.include_router(farms.router)
app.include_router(detections.router)
app.include_router(scan.router)
app.include_router(alerts.router)


@app.get("/api/ping")
def ping():
    return {"status": "alive"}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "CropGuard AI", "model": model_status()}


@app.get("/api/setup/seed")
def run_seed_once():
    """One-time seed endpoint for Render deployment - delete after use"""
    from database import SessionLocal
    from models import Farm, User
    from auth import hash_password as get_password_hash

    if not os.environ.get("RENDER"):
        return {"message": "Only runs on Render server"}

    db = SessionLocal()
    try:
        # Check if already seeded
        existing = db.query(User).filter(User.email == "admin@cropguard.ai").first()
        if existing:
            return {"message": "Already seeded", "status": "ok"}

        # Create users
        users = [
            User(name="CropGuard Admin", email="admin@cropguard.ai",
                 password_hash=get_password_hash("admin123"), role="admin"),
            User(name="Ramesh Farmer", email="farmer@cropguard.ai",
                 password_hash=get_password_hash("farmer123"), role="farmer"),
            User(name="Suresh Manager", email="manager@cropguard.ai",
                 password_hash=get_password_hash("manager123"), role="manager"),
        ]
        for u in users:
            db.add(u)
        db.flush()

        # Create farms
        farms = [
            Farm(user_id=users[1].id, name="Hosahalli Block A",
                 location="Hosahalli, Karnataka", crop_type="Chrysanthemum", area_acres=2.5),
            Farm(user_id=users[1].id, name="Hosahalli Block B",
                 location="Hosahalli, Karnataka", crop_type="Chrysanthemum", area_acres=3.0),
        ]
        for f in farms:
            db.add(f)
        db.commit()

        return {"message": "Seeded successfully", "status": "ok",
                "users": ["admin@cropguard.ai", "farmer@cropguard.ai", "manager@cropguard.ai"]}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/styles.css")
    def serve_styles():
        return FileResponse(FRONTEND_DIR / "styles.css")

    @app.get("/app.js")
    def serve_app_js():
        return FileResponse(FRONTEND_DIR / "app.js")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
