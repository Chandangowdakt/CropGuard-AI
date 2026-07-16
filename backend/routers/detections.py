import sys
import shutil
from datetime import date, datetime, time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ai_engine import ModelLoadError, get_model_status, predict_image_bytes
from class_constants import (
    empty_class_counts,
    is_healthy,
    is_problem,
    normalize_class,
)
from leaf_engine import predict_leaf_bytes
from whatsapp_alerts import WHATSAPP_CONFIDENCE_THRESHOLD, send_whatsapp_alert
from auth import get_accessible_farm_ids, get_current_user, get_farm_for_user
from database import get_db
from models import Alert, Detection, Farm, User
from schemas import (
    AnalysisPreviewOut,
    BatchAnalysisOut,
    BatchImagePredictionOut,
    BatchSaveOut,
    DetectionOut,
    DetectionResult,
    FarmReportOut,
    FarmReportSummary,
    FarmSummaryOut,
    LeafAnalysisOut,
    PredictionOut,
    ReportDetectionOut,
    StatsOut,
)

router = APIRouter(prefix="/api/detections", tags=["detections"])

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
FLAGGED_DIR = STORAGE_DIR / "flagged"
ALERT_THRESHOLD = 70.0


def _ensure_dirs():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    FLAGGED_DIR.mkdir(parents=True, exist_ok=True)


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _read_image_upload(file: UploadFile) -> tuple[bytes, str]:
    ext = Path(file.filename or "image.jpg").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPG, JPEG, and PNG images are allowed",
        )
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be 10MB or smaller",
        )
    return image_bytes, ext


def _run_prediction(image_bytes: bytes) -> dict:
    try:
        return predict_image_bytes(image_bytes)
    except ModelLoadError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/model-status")
def detection_model_status():
    """Public model health check (no auth required)."""
    return get_model_status()


def _persist_detection(
    db: Session,
    farm: Farm,
    image_bytes: bytes,
    ext: str,
    prediction: dict,
) -> DetectionResult:
    predicted_class = normalize_class(prediction["class"])
    confidence = prediction["confidence"]
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    save_path = UPLOADS_DIR / f"farm{farm.id}_{stamp}{ext}"
    with open(save_path, "wb") as out:
        out.write(image_bytes)

    detection = Detection(
        farm_id=farm.id,
        image_path=str(save_path),
        predicted_class=predicted_class,
        confidence=confidence,
    )
    db.add(detection)
    db.commit()
    db.refresh(detection)

    alert_created = False
    message = f"Detected {predicted_class} ({confidence:.1f}%)"

    should_alert = is_problem(predicted_class) and confidence > ALERT_THRESHOLD
    if should_alert:
        flagged_path = FLAGGED_DIR / f"ALERT_{predicted_class}_{stamp}.jpg"
        try:
            shutil.copy(save_path, flagged_path)
        except Exception:
            flagged_path = save_path

        alert = Alert(
            farm_id=farm.id,
            detection_id=detection.id,
            class_name=predicted_class,
            confidence=confidence,
            flagged_image_path=str(flagged_path),
        )
        db.add(alert)
        db.commit()
        alert_created = True
        message = f"ALERT: {predicted_class} detected at {confidence:.1f}% confidence"

    if not is_healthy(predicted_class) and confidence > WHATSAPP_CONFIDENCE_THRESHOLD:
        send_whatsapp_alert(
            farm.name,
            predicted_class,
            confidence,
            detection.timestamp,
        )

    return DetectionResult(
        detection=detection,
        prediction=PredictionOut(**prediction),
        alert_created=alert_created,
        message=message,
    )


@router.post("/analyze", response_model=AnalysisPreviewOut)
async def analyze_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload an image and run AI analysis without saving to the database."""
    _ensure_dirs()
    image_bytes, _ext = await _read_image_upload(file)
    prediction = _run_prediction(image_bytes)
    predicted_class = prediction["class"]
    confidence = prediction["confidence"]
    actual_class = prediction.get("actual_class", predicted_class)
    summary = (
        prediction.get("message")
        or f"Detected {actual_class} ({confidence:.1f}%)"
    )
    return AnalysisPreviewOut(
        prediction=PredictionOut(**prediction),
        message=summary,
        analyzed_at=datetime.utcnow(),
    )


@router.post("/analyze-batch", response_model=BatchAnalysisOut)
async def analyze_images_batch(
    files: list[UploadFile] = File(...),
    _user: User = Depends(get_current_user),
):
    """Batch analysis for multiple uploaded images (no DB writes)."""
    _ensure_dirs()
    if not files:
        raise HTTPException(status_code=400, detail="No images uploaded")

    results: list[BatchImagePredictionOut] = []
    class_counts = empty_class_counts()

    for file in files:
        image_bytes, _ext = await _read_image_upload(file)
        prediction = _run_prediction(image_bytes)
        predicted_class = prediction["class"]
        actual_class = normalize_class(prediction.get("actual_class", predicted_class))
        confidence = prediction.get("confidence", 0.0)

        prediction_payload = {
            "class": predicted_class,
            "actual_class": actual_class,
            "confidence": confidence,
            "is_problem": is_problem(actual_class),
            "message": prediction.get("message"),
        }
        results.append(
            BatchImagePredictionOut(
                filename=file.filename or "image",
                prediction=PredictionOut(**prediction_payload),
            )
        )

        if actual_class in class_counts:
            class_counts[actual_class] += 1

    total = len(results)
    class_percentages = {
        cls: round((count / total) * 100, 1) if total else 0.0
        for cls, count in class_counts.items()
    }

    return BatchAnalysisOut(
        total_images=total,
        class_counts=class_counts,
        class_percentages=class_percentages,
        results=results,
        message="Batch analysis complete",
        analyzed_at=datetime.utcnow(),
    )


@router.post("/save-batch", response_model=BatchSaveOut, status_code=status.HTTP_201_CREATED)
async def save_images_batch(
    farm_id: int = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Analyze and save multiple uploaded images to a farm, creating alerts as needed."""
    _ensure_dirs()
    if not files:
        raise HTTPException(status_code=400, detail="No images uploaded")

    farm = get_farm_for_user(db, farm_id, user)
    class_counts = empty_class_counts()
    saved_count = 0
    alert_count = 0

    for file in files:
        image_bytes, ext = await _read_image_upload(file)
        prediction = _run_prediction(image_bytes)
        predicted_class = normalize_class(
            prediction.get("actual_class", prediction.get("class"))
        )
        confidence = float(prediction.get("confidence", 0))
        persist_prediction = {
            "class": predicted_class,
            "confidence": confidence,
            "is_problem": is_problem(predicted_class),
            "message": prediction.get("message"),
        }
        result = _persist_detection(db, farm, image_bytes, ext, persist_prediction)
        saved_count += 1
        if predicted_class in class_counts:
            class_counts[predicted_class] += 1
        if result.alert_created:
            alert_count += 1

    class_percentages = {
        cls: round((count / saved_count) * 100, 1) if saved_count else 0.0
        for cls, count in class_counts.items()
    }

    return BatchSaveOut(
        farm_id=farm_id,
        saved_count=saved_count,
        alert_count=alert_count,
        class_counts=class_counts,
        class_percentages=class_percentages,
        message="Batch detections saved successfully",
        saved_at=datetime.utcnow(),
    )


@router.post("/analyze-leaf", response_model=LeafAnalysisOut)
async def analyze_leaf_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Upload a chrysanthemum leaf photo for 3-class disease classification."""
    _ensure_dirs()
    image_bytes, _ext = await _read_image_upload(file)
    result = predict_leaf_bytes(image_bytes)
    return LeafAnalysisOut(**result)


@router.post("/save", response_model=DetectionResult, status_code=status.HTTP_201_CREATED)
async def save_detection(
    farm_id: int = Form(...),
    predicted_class: str = Form(...),
    confidence: float = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save a confirmed analysis result to the selected farm."""
    _ensure_dirs()
    farm = get_farm_for_user(db, farm_id, user)
    image_bytes, ext = await _read_image_upload(file)
    canonical = normalize_class(predicted_class)
    prediction = {
        "class": canonical,
        "confidence": confidence,
        "is_problem": is_problem(canonical),
    }
    return _persist_detection(db, farm, image_bytes, ext, prediction)


def _build_recommendations(class_counts: dict[str, int], total: int) -> str:
    if total == 0:
        return (
            "No detections were recorded during this period. "
            "We recommend scheduling regular photo scans every 3–4 days to establish a health baseline."
        )
    parts: list[str] = []
    bacterial = class_counts.get("Bacterial", 0)
    septoria = class_counts.get("Septoria", 0)
    healthy = class_counts.get("Healthy", 0)
    healthy_pct = round((healthy / total) * 100)

    if bacterial:
        parts.append(
            f"Your farm detected {bacterial} case{'s' if bacterial != 1 else ''} of bacterial infection this period. "
            "Apply copper-based bactericide within 48 hours, remove affected leaves, "
            "and avoid overhead watering to limit spread."
        )
    if septoria:
        parts.append(
            f"Septoria leaf spot was identified in {septoria} scan{'s' if septoria != 1 else ''}. "
            "Apply fungicide promptly, improve air circulation between plants, "
            "and remove and destroy affected leaves."
        )
    if not parts:
        parts.append(
            f"Your farm maintained {healthy_pct}% healthy detections this period. "
            "Continue regular monitoring and maintain current irrigation and fertilisation schedules."
        )
    return " ".join(parts)


@router.get("/report", response_model=FarmReportOut)
def farm_health_report(
    farm_id: int = Query(...),
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a farm health report for a date range."""
    if to_date < from_date:
        raise HTTPException(status_code=400, detail="'to' date must be on or after 'from' date")

    farm = get_farm_for_user(db, farm_id, user)
    start_dt = datetime.combine(from_date, time.min)
    end_dt = datetime.combine(to_date, time.max)

    detections = (
        db.query(Detection)
        .filter(
            Detection.farm_id == farm_id,
            Detection.timestamp >= start_dt,
            Detection.timestamp <= end_dt,
        )
        .order_by(Detection.timestamp.desc())
        .all()
    )

    alerts = db.query(Alert).filter(Alert.farm_id == farm_id).all()
    alert_by_detection = {a.detection_id: a for a in alerts if a.detection_id}

    class_counts = empty_class_counts()
    for d in detections:
        canonical = normalize_class(d.predicted_class)
        if canonical in class_counts:
            class_counts[canonical] += 1

    total = len(detections)
    healthy = class_counts.get("Healthy", 0)
    health_score = round((healthy / total) * 100, 1) if total else 100.0

    class_percentages: dict[str, float] = {}
    for cls, count in class_counts.items():
        class_percentages[cls] = round((count / total) * 100, 1) if total else 0.0

    report_detections: list[ReportDetectionOut] = []
    for d in detections:
        if is_healthy(d.predicted_class):
            det_status = "Resolved"
        else:
            alert = alert_by_detection.get(d.id)
            det_status = "Active" if alert and not alert.is_read else "Resolved"
        report_detections.append(
            ReportDetectionOut(
                id=d.id,
                farm_id=d.farm_id,
                predicted_class=d.predicted_class,
                confidence=d.confidence,
                timestamp=d.timestamp,
                status=det_status,
            )
        )

    summary = FarmReportSummary(
        farm_id=farm.id,
        farm_name=farm.name,
        crop_type=farm.crop_type,
        location=farm.location,
        period_from=from_date.isoformat(),
        period_to=to_date.isoformat(),
        generated_at=datetime.utcnow(),
        total_detections=total,
        health_score=health_score,
        class_counts=class_counts,
        class_percentages=class_percentages,
    )

    return FarmReportOut(
        summary=summary,
        detections=report_detections,
        recommendations=_build_recommendations(class_counts, total),
    )


@router.get("/{detection_id}/image")
def get_detection_image(
    detection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the uploaded image for a detection record."""
    detection = db.query(Detection).filter(Detection.id == detection_id).first()
    if not detection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    get_farm_for_user(db, detection.farm_id, user)
    path = Path(detection.image_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found")
    return FileResponse(path)


@router.get("/farm/{farm_id}", response_model=list[DetectionOut])
def list_farm_detections(
    farm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """All detections for one farm, newest first."""
    get_farm_for_user(db, farm_id, user)
    return (
        db.query(Detection)
        .filter(Detection.farm_id == farm_id)
        .order_by(Detection.timestamp.desc())
        .all()
    )


@router.get("/recent", response_model=list[DetectionOut])
def recent_detections(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Last 20 detections across all accessible farms."""
    farm_ids = get_accessible_farm_ids(db, user)
    if not farm_ids:
        return []
    return (
        db.query(Detection)
        .filter(Detection.farm_id.in_(farm_ids))
        .order_by(Detection.timestamp.desc())
        .limit(20)
        .all()
    )


@router.get("/summary/{farm_id}", response_model=FarmSummaryOut)
def farm_detection_summary(
    farm_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Detection counts per class for one farm."""
    get_farm_for_user(db, farm_id, user)
    detections = db.query(Detection).filter(Detection.farm_id == farm_id).all()
    class_counts = empty_class_counts()
    for d in detections:
        canonical = normalize_class(d.predicted_class)
        if canonical in class_counts:
            class_counts[canonical] += 1
    return FarmSummaryOut(
        farm_id=farm_id,
        total_detections=len(detections),
        class_counts=class_counts,
    )


@router.get("/stats", response_model=StatsOut)
def get_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Global stats for dashboard (all accessible farms)."""
    farm_ids = get_accessible_farm_ids(db, user)
    detections = (
        db.query(Detection).filter(Detection.farm_id.in_(farm_ids)).all()
        if farm_ids else []
    )
    alerts = (
        db.query(Alert).filter(Alert.farm_id.in_(farm_ids)).all()
        if farm_ids else []
    )
    class_counts = empty_class_counts()
    for d in detections:
        canonical = normalize_class(d.predicted_class)
        if canonical in class_counts:
            class_counts[canonical] += 1
    return StatsOut(
        total_farms=len(farm_ids),
        total_detections=len(detections),
        total_alerts=len(alerts),
        unread_alerts=sum(1 for a in alerts if not a.is_read),
        class_counts=class_counts,
    )
