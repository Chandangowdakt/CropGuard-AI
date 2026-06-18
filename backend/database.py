import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
if os.environ.get("RENDER"):
    DB_PATH = Path("/tmp/cropguard.db")
else:
    DB_PATH = BASE_DIR / "cropguard.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_farms():
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "farms" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("farms")}
    with engine.begin() as conn:
        if "manager_id" not in columns:
            conn.execute(text("ALTER TABLE farms ADD COLUMN manager_id INTEGER"))
        if "description" not in columns:
            conn.execute(text("ALTER TABLE farms ADD COLUMN description TEXT DEFAULT ''"))


def _migrate_detections():
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "detections" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("detections")}
    with engine.begin() as conn:
        if "session_id" not in columns:
            conn.execute(text("ALTER TABLE detections ADD COLUMN session_id INTEGER"))
        if "latitude" not in columns:
            conn.execute(text("ALTER TABLE detections ADD COLUMN latitude REAL"))
        if "longitude" not in columns:
            conn.execute(text("ALTER TABLE detections ADD COLUMN longitude REAL"))


def _backfill_manager_assignments():
    """Copy legacy Farm.manager_id links into manager_farm_assignments."""
    from sqlalchemy import inspect

    from models import Farm, ManagerFarmAssignment

    inspector = inspect(engine)
    if "manager_farm_assignments" not in inspector.get_table_names():
        return
    if "farms" not in inspector.get_table_names():
        return

    db = SessionLocal()
    try:
        farms = db.query(Farm).filter(Farm.manager_id.isnot(None)).all()
        for farm in farms:
            exists = (
                db.query(ManagerFarmAssignment)
                .filter(
                    ManagerFarmAssignment.manager_id == farm.manager_id,
                    ManagerFarmAssignment.farm_id == farm.id,
                )
                .first()
            )
            if not exists:
                db.add(
                    ManagerFarmAssignment(
                        manager_id=farm.manager_id,
                        farm_id=farm.id,
                    )
                )
        db.commit()
    finally:
        db.close()


def init_db():
    from models import Alert, Detection, Farm, ManagerFarmAssignment, ScanSession, User  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_farms()
    _migrate_detections()
    _backfill_manager_assignments()
