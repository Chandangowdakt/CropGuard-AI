"""
CropGuard AI — database seed script.

Run from the backend folder:
    python seed.py

Creates demo users, farms, and sample detections.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from sqlalchemy import inspect, text

from auth import hash_password
from database import SessionLocal, engine, init_db
from models import Detection, Farm, ManagerFarmAssignment, User

STORAGE = Path(__file__).resolve().parent / "storage" / "uploads"
STORAGE.mkdir(parents=True, exist_ok=True)


def _ensure_farm_columns():
    """Add missing columns to farms when upgrading an older database."""
    inspector = inspect(engine)
    if "farms" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("farms")}
    with engine.begin() as conn:
        if "manager_id" not in columns:
            conn.execute(text("ALTER TABLE farms ADD COLUMN manager_id INTEGER"))
        if "description" not in columns:
            conn.execute(text("ALTER TABLE farms ADD COLUMN description TEXT DEFAULT ''"))


def seed():
    init_db()
    _ensure_farm_columns()
    db = SessionLocal()

    try:
        print("\n  CropGuard AI — Seeding database\n")

        # ── Users ─────────────────────────────────────────────────────────────
        users_data = [
            ("CropGuard Admin", "admin@cropguard.ai", "admin123", "admin"),
            ("Ramesh Farmer", "farmer@cropguard.ai", "farmer123", "farmer"),
            ("Priya Manager", "manager@cropguard.ai", "manager123", "manager"),
        ]
        users: dict[str, User] = {}
        for name, email, password, role in users_data:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                users[email] = existing
                print(f"  ·  User exists: {email}")
            else:
                u = User(
                    name=name,
                    email=email,
                    password_hash=hash_password(password),
                    role=role,
                )
                db.add(u)
                db.flush()
                users[email] = u
                print(f"  ✓  Created user: {email} ({role})")
        db.commit()

        farmer = users["farmer@cropguard.ai"]
        manager = users["manager@cropguard.ai"]

        # ── Farms ─────────────────────────────────────────────────────────────
        farms_data = [
            ("Hosahalli Block A", "Hosahalli, Karnataka", "chrysanthemum", 2.5),
            ("Hosahalli Block B", "Hosahalli, Karnataka", "chrysanthemum", 1.8),
        ]
        farms: list[Farm] = []
        for name, location, crop, acres in farms_data:
            existing = (
                db.query(Farm)
                .filter(Farm.user_id == farmer.id, Farm.name == name)
                .first()
            )
            if existing:
                existing.manager_id = manager.id
                farms.append(existing)
                print(f"  ·  Farm exists: {name}")
            else:
                f = Farm(
                    user_id=farmer.id,
                    manager_id=manager.id,
                    name=name,
                    location=location,
                    crop_type=crop,
                    area_acres=acres,
                )
                db.add(f)
                db.flush()
                farms.append(f)
                print(f"  ✓  Created farm: {name}")
        db.commit()

        # ── Manager farm assignments ──────────────────────────────────────────
        for farm in farms:
            if not farm.manager_id:
                continue
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

        # ── Sample detections ─────────────────────────────────────────────────
        samples = [
            ("healthy", 94.2),
            ("healthy", 91.5),
            ("healthy", 88.3),
            ("diseased", 96.1),
            ("diseased", 89.4),
            ("pest_affected", 92.7),
            ("pest_affected", 85.6),
            ("water_stressed", 87.9),
            ("water_stressed", 90.2),
            ("healthy", 93.8),
        ]

        existing_count = db.query(Detection).count()
        if existing_count >= 10:
            print(f"  ·  Detections already seeded ({existing_count} rows)")
        else:
            base_time = datetime.utcnow()
            for i, (cls, conf) in enumerate(samples):
                farm = farms[i % len(farms)]
                img_path = str(STORAGE / f"seed_{farm.id}_{i + 1}.jpg")
                if not Path(img_path).exists():
                    Path(img_path).write_bytes(b"seed-placeholder")

                det = Detection(
                    farm_id=farm.id,
                    image_path=img_path,
                    predicted_class=cls,
                    confidence=conf,
                    timestamp=base_time - timedelta(hours=i * 3),
                )
                db.add(det)
            db.commit()
            print(f"  ✓  Created {len(samples)} sample detections")

        print("\n  Seed complete!")
        print("  ─────────────────────────────────────────")
        print("  admin@cropguard.ai   / admin123")
        print("  farmer@cropguard.ai  / farmer123")
        print("  manager@cropguard.ai / manager123")
        print("  ─────────────────────────────────────────\n")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
