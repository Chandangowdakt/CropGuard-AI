import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="farmer", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    farms: Mapped[list["Farm"]] = relationship(
        "Farm",
        back_populates="owner",
        foreign_keys="Farm.user_id",
    )
    managed_farms: Mapped[list["Farm"]] = relationship(
        "Farm",
        foreign_keys="Farm.manager_id",
        back_populates="manager",
    )
    farm_assignments: Mapped[list["ManagerFarmAssignment"]] = relationship(
        "ManagerFarmAssignment",
        back_populates="manager",
        foreign_keys="ManagerFarmAssignment.manager_id",
    )


class ManagerFarmAssignment(Base):
    __tablename__ = "manager_farm_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    manager: Mapped["User"] = relationship(
        "User",
        back_populates="farm_assignments",
        foreign_keys=[manager_id],
    )
    farm: Mapped["Farm"] = relationship(
        "Farm",
        back_populates="manager_assignments",
        foreign_keys=[farm_id],
    )


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(255), default="")
    crop_type: Mapped[str] = mapped_column(String(80), default="chrysanthemum")
    area_acres: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship(
        "User",
        back_populates="farms",
        foreign_keys=[user_id],
    )
    manager: Mapped["User | None"] = relationship(
        "User",
        back_populates="managed_farms",
        foreign_keys=[manager_id],
    )
    detections: Mapped[list["Detection"]] = relationship("Detection", back_populates="farm")
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="farm")
    scan_sessions: Mapped[list["ScanSession"]] = relationship("ScanSession", back_populates="farm")
    manager_assignments: Mapped[list["ManagerFarmAssignment"]] = relationship(
        "ManagerFarmAssignment",
        back_populates="farm",
        foreign_keys="ManagerFarmAssignment.farm_id",
    )


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), nullable=False)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_scanned: Mapped[int] = mapped_column(Integer, default=0)
    healthy_count: Mapped[int] = mapped_column(Integer, default=0)
    # Legacy 4-class columns kept for existing DBs (no longer written by new code)
    diseased_count: Mapped[int] = mapped_column(Integer, default=0)
    pest_count: Mapped[int] = mapped_column(Integer, default=0)
    water_stressed_count: Mapped[int] = mapped_column(Integer, default=0)
    # New 3-class leaf counters
    bacterial_count: Mapped[int] = mapped_column(Integer, default=0)
    septoria_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")

    farm: Mapped["Farm"] = relationship("Farm", back_populates="scan_sessions")
    manager: Mapped["User"] = relationship("User", foreign_keys=[manager_id])
    detections: Mapped[list["Detection"]] = relationship("Detection", back_populates="scan_session")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("scan_sessions.id"), nullable=True)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_class: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    plant_zone_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    farm: Mapped["Farm"] = relationship("Farm", back_populates="detections")
    scan_session: Mapped["ScanSession | None"] = relationship("ScanSession", back_populates="detections")
    alert: Mapped["Alert | None"] = relationship("Alert", back_populates="detection", uselist=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), nullable=False)
    detection_id: Mapped[int | None] = mapped_column(ForeignKey("detections.id"), nullable=True)
    class_name: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    flagged_image_path: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    farm: Mapped["Farm"] = relationship("Farm", back_populates="alerts")
    detection: Mapped["Detection | None"] = relationship("Detection", back_populates="alert")
