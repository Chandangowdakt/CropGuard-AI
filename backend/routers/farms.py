import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import (
    farms_query_for_user,
    get_current_user,
    get_farm_for_user,
)
from class_constants import empty_class_counts, is_problem, normalize_class
from database import get_db
from models import Detection, Farm, User
from schemas import FarmCreate, FarmOut, FarmStatsOut, FarmUpdate, FarmWeatherOut
from weather import DEFAULT_LAT, DEFAULT_LON, get_weather

router = APIRouter(prefix="/api/farms", tags=["farms"])


@router.get("/", response_model=list[FarmOut])
def list_farms(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return farms_query_for_user(db, user).order_by(Farm.created_at.desc()).all()


@router.post("/", response_model=FarmOut, status_code=status.HTTP_201_CREATED)
def create_farm(
    payload: FarmCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.manager_id and user.role not in ("admin",):
        raise HTTPException(status_code=403, detail="Only admin can assign a manager")

    farm = Farm(
        user_id=user.id,
        manager_id=payload.manager_id if user.role == "admin" else None,
        name=payload.name,
        location=payload.location,
        crop_type=payload.crop_type,
        area_acres=payload.area_acres,
        description=payload.description or "",
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


@router.get("/{farm_id}/stats", response_model=FarmStatsOut)
def farm_stats(
    farm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Detection counts per class and health metrics for one farm."""
    get_farm_for_user(db, farm_id, user)
    detections = (
        db.query(Detection)
        .filter(Detection.farm_id == farm_id)
        .order_by(Detection.timestamp.desc())
        .all()
    )
    class_counts = empty_class_counts()
    problems_found = 0
    for d in detections:
        canonical = normalize_class(d.predicted_class)
        if canonical in class_counts:
            class_counts[canonical] += 1
        if is_problem(d.predicted_class):
            problems_found += 1
    total = len(detections)
    healthy = class_counts.get("Healthy", 0)
    health_score = round((healthy / total) * 100, 1) if total else 100.0
    last_scan = detections[0].timestamp if detections else None
    return FarmStatsOut(
        farm_id=farm_id,
        total_detections=total,
        problems_found=problems_found,
        last_scan=last_scan,
        health_score=health_score,
        class_counts=class_counts,
    )


@router.get("/{farm_id}/weather", response_model=FarmWeatherOut)
def farm_weather(
    farm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Live weather and disease risk for a farm (Open-Meteo, no API key)."""
    farm = get_farm_for_user(db, farm_id, user)
    lat, lon = DEFAULT_LAT, DEFAULT_LON
    try:
        data = get_weather(lat, lon)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return FarmWeatherOut(
        farm_id=farm.id,
        farm_name=farm.name,
        latitude=lat,
        longitude=lon,
        temperature=data["temperature"],
        humidity=data["humidity"],
        rainfall=data["rainfall"],
        windspeed=data["windspeed"],
        disease_risk=data["disease_risk"],
        updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "")),
        cached=data.get("cached"),
        note=data.get("note"),
    )


@router.get("/{farm_id}", response_model=FarmOut)
def get_farm(
    farm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_farm_for_user(db, farm_id, user)


@router.put("/{farm_id}", response_model=FarmOut)
def update_farm(
    farm_id: int,
    payload: FarmUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    farm = get_farm_for_user(db, farm_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(farm, field, value)
    db.commit()
    db.refresh(farm)
    return farm


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_farm(
    farm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    farm = get_farm_for_user(db, farm_id, user)
    if user.role == "farmer" and farm.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    db.delete(farm)
    db.commit()
    return None
