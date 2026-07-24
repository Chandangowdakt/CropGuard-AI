import base64
import re
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ai_engine import ModelLoadError, predict_image_bytes
from auth import get_current_user, get_farm_for_user, require_roles
from class_constants import is_healthy, is_problem, normalize_class
from database import get_db
from leaf_focus import center_crop_image_bytes
from models import Alert, Detection, Farm, ScanSession, User
from schemas import (
    ScanBulkDetectionsIn,
    ScanBulkDetectionsOut,
    ScanFrameAnalyzeOut,
    ScanSessionCreate,
    ScanSessionCreateOut,
    ScanSessionIn,
    ScanSessionOut,
    ScanSessionSummaryOut,
)
from scan_reporting import notify_scan_session_completed
from scan_smoothing import reset_session, update_prediction
from whatsapp_alerts import WHATSAPP_CONFIDENCE_THRESHOLD, send_whatsapp_alert

router = APIRouter(prefix="/api/scan", tags=["scan"])

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
FLAGGED_DIR = STORAGE_DIR / "flagged"
SCAN_FLAGS_DIR = STORAGE_DIR / "scan_flags"
ALERT_THRESHOLD = 70.0
SKIP_CLASSES = {"uncertain", "unavailable"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_BULK_DETECTIONS = 200
# Save every Nth healthy frame during bulk submit (problems always saved when imaged)
HEALTHY_SAMPLE_EVERY = 5
_ZONE_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-]+")


def _ensure_dirs():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    FLAGGED_DIR.mkdir(parents=True, exist_ok=True)
    SCAN_FLAGS_DIR.mkdir(parents=True, exist_ok=True)


async def _read_frame_upload(file: UploadFile) -> bytes:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty frame")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Frame too large")
    return image_bytes


def _run_prediction(image_bytes: bytes) -> dict:
    try:
        focused = center_crop_image_bytes(image_bytes)
        return predict_image_bytes(focused)
    except ModelLoadError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _decode_image_base64(data: str) -> bytes:
    payload = data.split(",", 1)[-1] if "," in data else data
    try:
        return base64.b64decode(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image_base64") from exc


def _normalize_class(cls: str) -> str:
    return normalize_class(cls)


def _safe_zone_tag(plant_zone_id: str | None) -> str:
    if not plant_zone_id:
        return ""
    cleaned = _ZONE_SAFE_RE.sub("-", plant_zone_id.strip())[:60]
    return f"_{cleaned}" if cleaned else ""


def _increment_session_counts(session: ScanSession, cls: str) -> None:
    session.total_scanned += 1
    canonical = normalize_class(cls)
    if canonical == "Healthy":
        session.healthy_count += 1
    elif canonical == "Bacterial":
        session.bacterial_count += 1
    elif canonical == "Septoria":
        session.septoria_count += 1


def _get_session_for_user(db: Session, session_id: int, user: User) -> ScanSession:
    session = db.query(ScanSession).filter(ScanSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan session not found")
    get_farm_for_user(db, session.farm_id, user)
    return session


def _flagged_count_for_session(db: Session, session_id: int) -> int:
    return (
        db.query(Detection)
        .filter(Detection.session_id == session_id)
        .count()
    )


def _session_to_summary(db: Session, session: ScanSession) -> ScanSessionSummaryOut:
    return ScanSessionSummaryOut(
        session_id=session.id,
        farm_id=session.farm_id,
        manager_id=session.manager_id,
        status=session.status,
        total_scanned=session.total_scanned,
        healthy_count=session.healthy_count,
        bacterial_count=session.bacterial_count,
        septoria_count=session.septoria_count,
        diseased_count=session.diseased_count,
        pest_count=session.pest_count,
        water_stressed_count=session.water_stressed_count,
        flagged_count=_flagged_count_for_session(db, session.id),
        started_at=session.started_at,
        completed_at=session.completed_at,
    )


def _save_flagged_detection(
    db: Session,
    farm: Farm,
    session: ScanSession,
    image_bytes: bytes,
    predicted_class: str,
    confidence: float,
    latitude: float | None,
    longitude: float | None,
    timestamp: datetime,
    plant_zone_id: str | None = None,
    *,
    create_alert: bool = True,
) -> tuple[Detection, dict | None]:
    """Persist one detection. Returns (detection, optional WhatsApp payload to send after commit)."""
    stamp = timestamp.strftime("%Y%m%d_%H%M%S_%f")
    zone_tag = _safe_zone_tag(plant_zone_id)
    safe_class = _ZONE_SAFE_RE.sub("-", predicted_class)[:40] or "class"
    flagged_path = SCAN_FLAGS_DIR / f"session{session.id}{zone_tag}_{safe_class}_{stamp}.jpg"
    try:
        flagged_path.write_bytes(image_bytes)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not store scan image") from exc

    detection = Detection(
        farm_id=farm.id,
        session_id=session.id,
        image_path=str(flagged_path),
        predicted_class=predicted_class,
        confidence=confidence,
        latitude=latitude,
        longitude=longitude,
        plant_zone_id=plant_zone_id,
        timestamp=timestamp,
    )
    db.add(detection)
    db.flush()

    whatsapp_payload = None
    canonical = normalize_class(predicted_class)
    if create_alert and is_problem(canonical) and confidence > ALERT_THRESHOLD:
        alert = Alert(
            farm_id=farm.id,
            detection_id=detection.id,
            class_name=canonical,
            confidence=confidence,
            flagged_image_path=str(flagged_path),
        )
        db.add(alert)

        if confidence > WHATSAPP_CONFIDENCE_THRESHOLD:
            loc = ""
            if latitude is not None and longitude is not None:
                loc = f"\nGPS: {latitude:.5f}, {longitude:.5f}"
            zone = f"\nPlant zone: {plant_zone_id}" if plant_zone_id else ""
            body = (
                f"🌿 CropGuard AI Alert\n"
                f"Farm: {farm.name}\n"
                f"Problem: {canonical.upper()}\n"
                f"Confidence: {confidence:.1f}%\n"
                f"Time: {timestamp.strftime('%Y-%m-%d %H:%M')}"
                f"{zone}{loc}\n"
                f"Action: Inspect this plant zone immediately"
            )
            whatsapp_payload = {
                "farm_name": farm.name,
                "class_name": canonical,
                "confidence": confidence,
                "timestamp": timestamp,
                "custom_body": body,
                "plant_zone_id": plant_zone_id,
            }

    return detection, whatsapp_payload


def _save_detection_with_alert(
    db: Session,
    farm: Farm,
    image_bytes: bytes,
    predicted_class: str,
    confidence: float,
) -> tuple[Detection, bool]:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    save_path = UPLOADS_DIR / f"scan_farm{farm.id}_{stamp}.jpg"
    with open(save_path, "wb") as out:
        out.write(image_bytes)

    detection = Detection(
        farm_id=farm.id,
        image_path=str(save_path),
        predicted_class=predicted_class,
        confidence=confidence,
    )
    db.add(detection)
    db.flush()

    alert_created = False
    canonical = normalize_class(predicted_class)
    if is_problem(canonical) and confidence > ALERT_THRESHOLD:
        flagged_path = FLAGGED_DIR / f"SCAN_ALERT_{predicted_class}_{stamp}.jpg"
        try:
            flagged_path.write_bytes(image_bytes)
        except OSError:
            flagged_path = save_path
        alert = Alert(
            farm_id=farm.id,
            detection_id=detection.id,
            class_name=canonical,
            confidence=confidence,
            flagged_image_path=str(flagged_path),
        )
        db.add(alert)
        alert_created = True

    return detection, alert_created


@router.post("/analyze-frame", response_model=ScanFrameAnalyzeOut)
async def analyze_frame(
    file: UploadFile = File(...),
    farm_id: int | None = Form(None),
    session_id: int | None = Form(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("manager", "admin")),
):
    """Fast inference on a single live camera frame — no database writes."""
    active_session_id = None
    if session_id is not None:
        session = _get_session_for_user(db, session_id, user)
        if session.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not active")
        if farm_id is not None and int(farm_id) != int(session.farm_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="farm_id does not match session")
        get_farm_for_user(db, session.farm_id, user)
        active_session_id = session.id
    elif farm_id is not None:
        get_farm_for_user(db, farm_id, user)

    image_bytes = await _read_frame_upload(file)
    prediction = _run_prediction(image_bytes)

    pred_class = prediction.get("class", "unavailable")
    actual_class = prediction.get("actual_class") or pred_class
    confidence = float(prediction.get("confidence", 0))

    smoothed = update_prediction(
        active_session_id,
        actual_class if pred_class not in SKIP_CLASSES else pred_class,
        confidence,
        latitude,
        longitude,
    )
    smoothed_class = smoothed["smoothed_class"]
    display_class = pred_class if pred_class in SKIP_CLASSES else smoothed_class
    problem_detected = bool(smoothed["is_confirmed_problem"]) and display_class not in SKIP_CLASSES

    return ScanFrameAnalyzeOut(
        predicted_class=display_class,
        confidence=float(smoothed["smoothed_confidence"] if pred_class not in SKIP_CLASSES else confidence),
        is_problem=problem_detected,
        actual_class=actual_class if pred_class not in SKIP_CLASSES else None,
        smoothed_class=smoothed_class if pred_class not in SKIP_CLASSES else None,
        latitude=latitude,
        longitude=longitude,
        plant_zone_id=smoothed.get("plant_zone_id"),
        analyzed_at=datetime.utcnow(),
    )


@router.post("/sessions", response_model=ScanSessionCreateOut)
def create_scan_session(
    payload: ScanSessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start a new live walk-through scan session."""
    get_farm_for_user(db, payload.farm_id, user)
    session = ScanSession(
        farm_id=payload.farm_id,
        manager_id=user.id,
        started_at=payload.started_at or datetime.utcnow(),
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    reset_session(session.id)
    return ScanSessionCreateOut(session_id=session.id)


@router.get("/sessions/farm/{farm_id}", response_model=list[ScanSessionSummaryOut])
def list_farm_scan_sessions(
    farm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all scan sessions for a farm with summary counts."""
    get_farm_for_user(db, farm_id, user)
    sessions = (
        db.query(ScanSession)
        .filter(ScanSession.farm_id == farm_id)
        .order_by(ScanSession.started_at.desc())
        .all()
    )
    return [_session_to_summary(db, s) for s in sessions]


@router.post("/sessions/{session_id}/detections", response_model=ScanBulkDetectionsOut)
def bulk_save_session_detections(
    session_id: int,
    payload: ScanBulkDetectionsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bulk insert detections from a completed walk-through session."""
    _ensure_dirs()
    session = _get_session_for_user(db, session_id, user)
    if session.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not active")

    if len(payload.detections) > MAX_BULK_DETECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many detections. Maximum is {MAX_BULK_DETECTIONS}.",
        )

    farm = db.query(Farm).filter(Farm.id == session.farm_id).first()
    saved_count = 0
    flagged_count = 0
    healthy_seen = 0
    saved_problem_zones: set[str] = set()
    pending_whatsapp: list[dict] = []

    for item in payload.detections:
        cls = _normalize_class(item.predicted_class)
        if cls in SKIP_CLASSES:
            continue

        zone_id = (item.plant_zone_id or "").strip() or None
        if zone_id:
            zone_id = _ZONE_SAFE_RE.sub("-", zone_id)[:80]

        # One saved problem detection per plant zone (best evidence first from client)
        if is_problem(cls):
            zone_key = zone_id or f"anon-{item.timestamp.isoformat()}"
            if zone_key in saved_problem_zones:
                continue
            if item.confidence <= ALERT_THRESHOLD or not item.image_base64:
                continue
            saved_problem_zones.add(zone_key)
        elif is_healthy(cls):
            healthy_seen += 1
            if healthy_seen % HEALTHY_SAMPLE_EVERY != 0 or not item.image_base64:
                continue
            if item.confidence <= 0:
                continue
        else:
            continue

        _increment_session_counts(session, cls)
        image_bytes = _decode_image_base64(item.image_base64)
        _, whatsapp_payload = _save_flagged_detection(
            db,
            farm,
            session,
            image_bytes,
            cls,
            item.confidence,
            item.lat,
            item.lon,
            item.timestamp,
            plant_zone_id=zone_id,
            create_alert=is_problem(cls),
        )
        saved_count += 1
        if is_problem(cls):
            flagged_count += 1
        if whatsapp_payload:
            pending_whatsapp.append(whatsapp_payload)

    db.commit()

    for msg in pending_whatsapp:
        send_whatsapp_alert(
            msg["farm_name"],
            msg["class_name"],
            msg["confidence"],
            msg["timestamp"],
            custom_body=msg["custom_body"],
            plant_zone_id=msg.get("plant_zone_id"),
        )

    return ScanBulkDetectionsOut(saved_count=saved_count, flagged_count=flagged_count)


@router.post("/sessions/{session_id}/complete", response_model=ScanSessionSummaryOut)
def complete_scan_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark a scan session complete, summarize counts, and notify admins."""
    session = _get_session_for_user(db, session_id, user)
    if session.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not active")

    farm = db.query(Farm).filter(Farm.id == session.farm_id).first()
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(session)

    reset_session(session_id)
    notify_scan_session_completed(db, session, farm)
    return _session_to_summary(db, session)


@router.post("/sessions/{session_id}/cancel", response_model=ScanSessionSummaryOut)
def cancel_scan_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cancel an active walk-through without sending completion reports."""
    session = _get_session_for_user(db, session_id, user)
    if session.status != "active":
        return _session_to_summary(db, session)

    session.status = "cancelled"
    session.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    reset_session(session_id)
    return _session_to_summary(db, session)


@router.post("/submit-session", response_model=ScanSessionOut)
def submit_session(
    payload: ScanSessionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist a completed live scan session to the farm record (legacy bulk endpoint)."""
    _ensure_dirs()
    farm = get_farm_for_user(db, payload.farm_id, user)

    saved = 0
    alerts_created = 0
    for item in payload.detections:
        save_class = normalize_class(item.actual_class or item.predicted_class)
        if save_class in SKIP_CLASSES:
            continue
        if not item.image_base64:
            continue

        image_bytes = _decode_image_base64(item.image_base64)
        _, alert_created = _save_detection_with_alert(
            db, farm, image_bytes, save_class, item.confidence
        )
        saved += 1
        if alert_created:
            alerts_created += 1

    db.commit()
    return ScanSessionOut(
        message="Live scan session saved",
        detections_saved=saved,
        alerts_created=alerts_created,
        farm_id=farm.id,
    )
