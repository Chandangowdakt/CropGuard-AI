import sys

from datetime import date, datetime, timedelta

from pathlib import Path



if hasattr(sys.stdout, "reconfigure"):

    try:

        sys.stdout.reconfigure(encoding="utf-8")

    except (OSError, ValueError):

        pass



from fastapi import APIRouter, Depends, HTTPException, Query, status

from fastapi.responses import FileResponse

from sqlalchemy.orm import Session



from auth import get_accessible_farm_ids, get_current_user, get_farm_for_user

from database import get_db

from models import Alert, User

from schemas import AlertOut, AlertStatsOut, UnreadCountOut



router = APIRouter(prefix="/api/alerts", tags=["alerts"])



FILTER_CLASS_MAP = {

    "diseased": "diseased",

    "pest": "pest_affected",

    "pest_affected": "pest_affected",

    "water": "water_stressed",

    "water_stressed": "water_stressed",

}





def _get_alert_or_404(alert_id: int, user: User, db: Session) -> Alert:

    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    farm_ids = get_accessible_farm_ids(db, user)

    if alert.farm_id not in farm_ids:

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return alert





def _accessible_alerts_query(db: Session, user: User):

    farm_ids = get_accessible_farm_ids(db, user)

    if not farm_ids:

        return None

    return db.query(Alert).filter(Alert.farm_id.in_(farm_ids))





@router.get("/stats", response_model=AlertStatsOut)

def alert_stats(

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    """Alert counts by class for today and the past 7 days."""

    today = date.today()

    week_start = today - timedelta(days=6)

    class_counts: dict[str, int] = {}

    unread = 0

    total_today = 0

    total_week = 0



    query = _accessible_alerts_query(db, user)

    if query is not None:

        alerts = query.all()

        for a in alerts:

            alert_day = a.timestamp.date()

            if alert_day == today:

                total_today += 1

                class_counts[a.class_name] = class_counts.get(a.class_name, 0) + 1

            if alert_day >= week_start:

                total_week += 1

            if not a.is_read:

                unread += 1



    return AlertStatsOut(

        date=today.isoformat(),

        total_today=total_today,

        unread=unread,

        total_week=total_week,

        class_counts=class_counts,

    )





@router.get("/unread/count", response_model=UnreadCountOut)

def unread_alert_count(

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    """Return the number of unread alerts for the current user."""

    query = _accessible_alerts_query(db, user)

    if query is None:

        return UnreadCountOut(count=0)

    count = query.filter(Alert.is_read.is_(False)).count()

    return UnreadCountOut(count=count)





@router.put("/mark-all-read")

def mark_all_alerts_read(

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    """Mark every unread alert as read for accessible farms."""

    query = _accessible_alerts_query(db, user)

    if query is None:

        return {"updated": 0}

    updated = (

        query.filter(Alert.is_read.is_(False))

        .update({Alert.is_read: True}, synchronize_session=False)

    )

    db.commit()

    return {"updated": updated}





@router.get("/farm/{farm_id}", response_model=list[AlertOut])

def farm_alerts(

    farm_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    """All alerts for one farm."""

    get_farm_for_user(db, farm_id, user)

    return (

        db.query(Alert)

        .filter(Alert.farm_id == farm_id)

        .order_by(Alert.timestamp.desc())

        .all()

    )





@router.get("/", response_model=list[AlertOut])

def list_alerts(

    filter: str = Query("all", description="all | unread | diseased | pest | water_stressed"),

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    """List alerts with optional filter by read status or problem class."""

    query = _accessible_alerts_query(db, user)

    if query is None:

        return []



    normalized = filter.lower().strip()

    if normalized == "unread":

        query = query.filter(Alert.is_read.is_(False))

    elif normalized in FILTER_CLASS_MAP:

        query = query.filter(Alert.class_name == FILTER_CLASS_MAP[normalized])



    return query.order_by(Alert.timestamp.desc()).all()





def _mark_read(alert_id: int, db: Session, user: User) -> Alert:

    alert = _get_alert_or_404(alert_id, user, db)

    alert.is_read = True

    db.commit()

    db.refresh(alert)

    return alert





@router.put("/{alert_id}/read", response_model=AlertOut)

def mark_alert_read_put(

    alert_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    """Mark a single alert as read."""

    return _mark_read(alert_id, db, user)





@router.post("/{alert_id}/read", response_model=AlertOut)

def mark_alert_read_post(

    alert_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    """Mark a single alert as read (POST alias)."""

    return _mark_read(alert_id, db, user)





@router.get("/{alert_id}", response_model=AlertOut)

def get_alert(

    alert_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    return _get_alert_or_404(alert_id, user, db)





@router.get("/{alert_id}/image")

def get_alert_image(

    alert_id: int,

    db: Session = Depends(get_db),

    user: User = Depends(get_current_user),

):

    alert = _get_alert_or_404(alert_id, user, db)

    path = Path(alert.flagged_image_path)

    if not path.exists():

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found")

    return FileResponse(path)


