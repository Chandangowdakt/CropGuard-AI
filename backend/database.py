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


def init_db():
    from models import Alert, Detection, Farm, User  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_farms()
