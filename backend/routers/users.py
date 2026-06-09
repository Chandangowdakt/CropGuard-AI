import sys
from collections import Counter
from datetime import date, timedelta

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_user_by_email,
    hash_password,
    require_roles,
    user_to_out,
)
from database import get_db
from models import Detection, Farm, User
from schemas import (
    ActivityFeedItem,
    AdminFarmOut,
    AdminStatsOut,
    AdminUserOut,
    DailyTrendOut,
    RoleChangeRequest,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
)

PROBLEM_CLASSES = {"diseased", "pest_affected", "water_stressed"}

# ── Authentication routes ───────────────────────────────────────────────────────
auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])


@auth_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user.
    Accepts name, email, password, and role (farmer / manager / admin).
    Returns a JWT token valid for 7 days.
    """
    if get_user_by_email(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    allowed_roles = {"farmer", "manager", "admin"}
    role = payload.role if payload.role in allowed_roles else "farmer"

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token, user=user_to_out(user))


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Login with JSON body: email + password. Returns JWT + user info."""
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token, user=user_to_out(user))


@auth_router.post("/login/form", response_model=TokenResponse, include_in_schema=False)
def login_form(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 form login (username = email) — used by Swagger UI."""
    user = authenticate_user(db, form.username, form.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token, user=user_to_out(user))


@auth_router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user (requires Bearer JWT)."""
    return user_to_out(user)


# ── User management routes (admin) ────────────────────────────────────────────
router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [user_to_out(u) for u in users]


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserRegister,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    if get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_out(user)


# ── Admin routes ──────────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


def _health_status(score: float) -> str:
    if score >= 70:
        return "healthy"
    if score >= 40:
        return "warning"
    return "critical"


def _farm_health(db: Session, farm_id: int) -> tuple[float, str | None]:
    detections = (
        db.query(Detection)
        .filter(Detection.farm_id == farm_id)
        .order_by(Detection.timestamp.desc())
        .all()
    )
    if not detections:
        return 100.0, None
    healthy = sum(1 for d in detections if d.predicted_class == "healthy")
    score = round((healthy / len(detections)) * 100, 1)
    return score, detections[0].timestamp


@admin_router.get("/stats", response_model=AdminStatsOut)
def admin_platform_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Platform-wide statistics for the admin dashboard."""
    today = date.today()
    week_start = today - timedelta(days=6)

    all_detections = db.query(Detection).all()
    today_detections = [d for d in all_detections if d.timestamp.date() == today]

    problem_counts: Counter[str] = Counter()
    healthy_total = 0
    for d in all_detections:
        if d.predicted_class == "healthy":
            healthy_total += 1
        elif d.predicted_class in PROBLEM_CLASSES:
            problem_counts[d.predicted_class] += 1

    most_common_problem = problem_counts.most_common(1)[0][0] if problem_counts else None
    total_det = len(all_detections)
    platform_health = round((healthy_total / total_det) * 100, 1) if total_det else 100.0

    daily_trends: list[DailyTrendOut] = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        day_dets = [d for d in all_detections if d.timestamp.date() == day]
        counts: dict[str, int] = {}
        for d in day_dets:
            counts[d.predicted_class] = counts.get(d.predicted_class, 0) + 1
        daily_trends.append(
            DailyTrendOut(
                date=day.isoformat(),
                healthy=counts.get("healthy", 0),
                diseased=counts.get("diseased", 0),
                pest_affected=counts.get("pest_affected", 0),
                water_stressed=counts.get("water_stressed", 0),
                total=len(day_dets),
            )
        )

    week_detections = [d for d in all_detections if d.timestamp.date() >= week_start]
    farm_activity: Counter[int] = Counter(d.farm_id for d in week_detections)
    most_active_farm = None
    if farm_activity:
        top_farm_id = farm_activity.most_common(1)[0][0]
        farm = db.query(Farm).filter(Farm.id == top_farm_id).first()
        most_active_farm = farm.name if farm else f"Farm #{top_farm_id}"

    today_problems: Counter[str] = Counter(
        d.predicted_class for d in today_detections if d.predicted_class in PROBLEM_CLASSES
    )
    most_common_disease_today = (
        today_problems.most_common(1)[0][0] if today_problems else None
    )

    total_users = db.query(User).filter(User.role.in_(["farmer", "manager"])).count()

    return AdminStatsOut(
        total_farms=db.query(Farm).count(),
        total_users=total_users,
        total_detections=total_det,
        detections_today=len(today_detections),
        most_common_problem=most_common_problem,
        platform_health_score=platform_health,
        daily_trends=daily_trends,
        most_active_farm=most_active_farm,
        most_common_disease_today=most_common_disease_today,
    )


@admin_router.get("/all-farms", response_model=list[AdminFarmOut])
def admin_all_farms(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """All farms across every user."""
    farms = db.query(Farm).order_by(Farm.created_at.desc()).all()
    owners = {u.id: u for u in db.query(User).all()}
    result: list[AdminFarmOut] = []
    for farm in farms:
        owner = owners.get(farm.user_id)
        score, last_scan = _farm_health(db, farm.id)
        result.append(
            AdminFarmOut(
                id=farm.id,
                name=farm.name,
                owner_name=owner.name if owner else "Unknown",
                owner_email=owner.email if owner else "",
                crop_type=farm.crop_type,
                location=farm.location,
                last_scan=last_scan,
                health_score=score,
                health_status=_health_status(score),
            )
        )
    return result


@admin_router.get("/all-users", response_model=list[AdminUserOut])
def admin_all_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """All registered users with farm counts."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    farm_counts: Counter[int] = Counter(
        f.user_id for f in db.query(Farm).all()
    )
    return [
        AdminUserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role,
            farms_count=farm_counts.get(u.id, 0),
            created_at=u.created_at,
            status="Active",
        )
        for u in users
    ]


@admin_router.get("/activity-feed", response_model=list[ActivityFeedItem])
def admin_activity_feed(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Latest 20 detections across all farms."""
    detections = (
        db.query(Detection)
        .order_by(Detection.timestamp.desc())
        .limit(20)
        .all()
    )
    farms = {f.id: f for f in db.query(Farm).all()}
    feed: list[ActivityFeedItem] = []
    for d in detections:
        farm = farms.get(d.farm_id)
        farm_name = farm.name if farm else f"Farm #{d.farm_id}"
        label = d.predicted_class.replace("_", " ").title()
        feed.append(
            ActivityFeedItem(
                id=d.id,
                farm_id=d.farm_id,
                farm_name=farm_name,
                predicted_class=d.predicted_class,
                confidence=d.confidence,
                timestamp=d.timestamp,
                message=f"{label} detected at {farm_name} ({d.confidence:.1f}%)",
            )
        )
    return feed


@admin_router.put("/users/{user_id}/role", response_model=AdminUserOut)
def admin_change_user_role(
    user_id: int,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Toggle a user between farmer and manager roles."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Cannot change admin role")
    if payload.role not in ("farmer", "manager"):
        raise HTTPException(status_code=400, detail="Role must be farmer or manager")

    user.role = payload.role
    db.commit()
    db.refresh(user)
    farm_counts: Counter[int] = Counter(f.user_id for f in db.query(Farm).all())
    return AdminUserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        farms_count=farm_counts.get(user.id, 0),
        created_at=user.created_at,
        status="Active",
    )
