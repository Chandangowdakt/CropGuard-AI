import sys
from collections import Counter
from datetime import date, datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from models import Detection, Farm, ManagerFarmAssignment, ScanSession, User
from schemas import (
    ActivityFeedItem,
    AdminFarmHealthComparisonOut,
    AdminFarmOut,
    AdminFlaggedDetectionOut,
    AdminManagerOverviewOut,
    AdminScanSessionDetailOut,
    AdminScanSessionOut,
    AdminStatsOut,
    AdminUserOut,
    DailyTrendOut,
    ManagerAssignOut,
    ManagerAssignRequest,
    ManagerAssignmentsOut,
    AdminDailyDigestOut,
    DailyDigestFarmBreakdown,
    DailyDigestSendOut,
    RoleChangeRequest,
    TokenResponse,
    UserLogin,
    UserOut,
    UserRegister,
)

from scan_reporting import build_daily_digest, send_daily_digest_email
from ai_engine import get_shadow_comparison_stats

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


@admin_router.get("/shadow-comparison")
def admin_shadow_comparison(
    _admin: User = Depends(require_roles("admin")),
):
    """
    Admin-only: live vs shadow v2 agreement stats from shadow_predictions.csv.
    Shadow model is never shown to end users.
    """
    return get_shadow_comparison_stats()


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


def _session_issues(session: ScanSession) -> int:
    return session.diseased_count + session.pest_count + session.water_stressed_count


def _session_health_score(session: ScanSession) -> float | None:
    if session.total_scanned <= 0:
        return None
    return round((session.healthy_count / session.total_scanned) * 100, 1)


def _scan_session_row(
    session: ScanSession,
    farms: dict[int, Farm],
    managers: dict[int, User],
) -> AdminScanSessionOut:
    farm = farms.get(session.farm_id)
    manager = managers.get(session.manager_id)
    return AdminScanSessionOut(
        session_id=session.id,
        farm_id=session.farm_id,
        farm_name=farm.name if farm else f"Farm #{session.farm_id}",
        manager_id=session.manager_id,
        manager_name=manager.name if manager else "Unknown",
        started_at=session.started_at,
        completed_at=session.completed_at,
        total_scanned=session.total_scanned,
        issues_found=_session_issues(session),
        status=session.status,
    )


@admin_router.get("/scan-sessions", response_model=list[AdminScanSessionOut])
def admin_scan_sessions(
    farm_id: int | None = Query(None),
    manager_id: int | None = Query(None),
    sort: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """All live scan sessions across farms and managers."""
    q = db.query(ScanSession)
    if farm_id is not None:
        q = q.filter(ScanSession.farm_id == farm_id)
    if manager_id is not None:
        q = q.filter(ScanSession.manager_id == manager_id)
    order = ScanSession.started_at.desc() if sort == "desc" else ScanSession.started_at.asc()
    sessions = q.order_by(order).all()

    farms = {f.id: f for f in db.query(Farm).all()}
    managers = {u.id: u for u in db.query(User).filter(User.role == "manager").all()}
    return [_scan_session_row(s, farms, managers) for s in sessions]


@admin_router.get("/scan-sessions/{session_id}", response_model=AdminScanSessionDetailOut)
def admin_scan_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Full scan session detail with flagged plant detections."""
    session = db.query(ScanSession).filter(ScanSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Scan session not found")

    farms = {f.id: f for f in db.query(Farm).all()}
    managers = {u.id: u for u in db.query(User).all()}
    base = _scan_session_row(session, farms, managers)

    flagged = (
        db.query(Detection)
        .filter(Detection.session_id == session_id)
        .order_by(Detection.timestamp.desc())
        .all()
    )
    flagged_out = [
        AdminFlaggedDetectionOut(
            id=d.id,
            predicted_class=d.predicted_class,
            confidence=d.confidence,
            timestamp=d.timestamp,
            latitude=d.latitude,
            longitude=d.longitude,
        )
        for d in flagged
    ]

    return AdminScanSessionDetailOut(
        **base.model_dump(),
        healthy_count=session.healthy_count,
        diseased_count=session.diseased_count,
        pest_count=session.pest_count,
        water_stressed_count=session.water_stressed_count,
        flagged_detections=flagged_out,
    )


@admin_router.get("/managers-overview", response_model=list[AdminManagerOverviewOut])
def admin_managers_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Per-manager scan activity and issue counts for the current week."""
    today = date.today()
    week_start = today - timedelta(days=6)
    week_start_dt = datetime.combine(week_start, datetime.min.time())

    managers = db.query(User).filter(User.role == "manager").order_by(User.name).all()
    farms = {f.id: f for f in db.query(Farm).all()}
    assignments = db.query(ManagerFarmAssignment).all()
    assign_by_manager: dict[int, list[int]] = {}
    for a in assignments:
        assign_by_manager.setdefault(a.manager_id, []).append(a.farm_id)

    all_sessions = db.query(ScanSession).all()
    result: list[AdminManagerOverviewOut] = []

    for mgr in managers:
        farm_ids = assign_by_manager.get(mgr.id, [])
        if not farm_ids:
            farm_ids = [f.id for f in farms.values() if f.manager_id == mgr.id]

        assigned_names = [farms[fid].name for fid in farm_ids if fid in farms]
        mgr_sessions = [s for s in all_sessions if s.manager_id == mgr.id]
        week_sessions = [
            s for s in mgr_sessions
            if (s.completed_at or s.started_at) >= week_start_dt
        ]
        issues_week = sum(_session_issues(s) for s in week_sessions)
        last_scan = None
        if mgr_sessions:
            last_scan = max(s.completed_at or s.started_at for s in mgr_sessions)

        result.append(
            AdminManagerOverviewOut(
                manager_id=mgr.id,
                manager_name=mgr.name,
                assigned_farms=assigned_names,
                assigned_farm_count=len(assigned_names),
                scans_this_week=len(week_sessions),
                issues_this_week=issues_week,
                last_scan_at=last_scan,
            )
        )
    return result


@admin_router.get("/farms-health-comparison", response_model=list[AdminFarmHealthComparisonOut])
def admin_farms_health_comparison(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Side-by-side farm health scores with scan-based trends."""
    farms = db.query(Farm).order_by(Farm.name).all()
    users = {u.id: u for u in db.query(User).all()}
    all_sessions = (
        db.query(ScanSession)
        .filter(ScanSession.status == "completed")
        .order_by(ScanSession.completed_at.desc())
        .all()
    )
    sessions_by_farm: dict[int, list[ScanSession]] = {}
    for s in all_sessions:
        sessions_by_farm.setdefault(s.farm_id, []).append(s)

    result: list[AdminFarmHealthComparisonOut] = []
    for farm in farms:
        farm_sessions = sessions_by_farm.get(farm.id, [])
        latest_session = farm_sessions[0] if farm_sessions else None
        previous_session = farm_sessions[1] if len(farm_sessions) > 1 else None

        if latest_session and latest_session.total_scanned > 0:
            score = _session_health_score(latest_session) or 100.0
            last_scanned_at = latest_session.completed_at or latest_session.started_at
            last_manager = users.get(latest_session.manager_id)
            last_manager_name = last_manager.name if last_manager else None

            trend = "stable"
            if previous_session and previous_session.total_scanned > 0:
                prev_score = _session_health_score(previous_session) or 0
                if score > prev_score + 2:
                    trend = "improving"
                elif score < prev_score - 2:
                    trend = "worsening"
        else:
            score, last_det_ts = _farm_health(db, farm.id)
            last_scanned_at = last_det_ts
            last_manager_name = None
            if farm.manager_id:
                mgr = users.get(farm.manager_id)
                last_manager_name = mgr.name if mgr else None
            trend = "stable"

        result.append(
            AdminFarmHealthComparisonOut(
                farm_id=farm.id,
                farm_name=farm.name,
                health_score=score,
                health_status=_health_status(score),
                trend=trend,
                last_manager_name=last_manager_name,
                last_scanned_at=last_scanned_at,
            )
        )
    return result


@admin_router.get("/manager-assignments/{manager_id}", response_model=ManagerAssignmentsOut)
def admin_manager_assignments(
    manager_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Return farm IDs currently assigned to a manager."""
    manager = db.query(User).filter(User.id == manager_id, User.role == "manager").first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    farm_ids = [
        a.farm_id
        for a in db.query(ManagerFarmAssignment)
        .filter(ManagerFarmAssignment.manager_id == manager_id)
        .all()
    ]
    if not farm_ids:
        farm_ids = [
            f.id for f in db.query(Farm).filter(Farm.manager_id == manager_id).all()
        ]
    return ManagerAssignmentsOut(manager_id=manager_id, farm_ids=farm_ids)


@admin_router.post("/assign-manager", response_model=ManagerAssignOut)
def admin_assign_manager(
    payload: ManagerAssignRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Assign farms to a manager (replaces existing assignments)."""
    manager = db.query(User).filter(User.id == payload.manager_id).first()
    if not manager or manager.role != "manager":
        raise HTTPException(status_code=400, detail="Invalid manager_id")

    farms = db.query(Farm).filter(Farm.id.in_(payload.farm_ids)).all() if payload.farm_ids else []
    if len(farms) != len(set(payload.farm_ids)):
        raise HTTPException(status_code=400, detail="One or more farm IDs are invalid")

    previous = (
        db.query(ManagerFarmAssignment)
        .filter(ManagerFarmAssignment.manager_id == payload.manager_id)
        .all()
    )
    previous_farm_ids = {a.farm_id for a in previous}
    for a in previous:
        db.delete(a)

    for farm_id in payload.farm_ids:
        db.add(ManagerFarmAssignment(manager_id=payload.manager_id, farm_id=farm_id))

    new_farm_ids = set(payload.farm_ids)
    for farm_id in previous_farm_ids - new_farm_ids:
        farm = db.query(Farm).filter(Farm.id == farm_id).first()
        if farm and farm.manager_id == payload.manager_id:
            farm.manager_id = None

    for farm in farms:
        farm.manager_id = payload.manager_id

    db.commit()
    return ManagerAssignOut(
        manager_id=payload.manager_id,
        assigned_farm_ids=payload.farm_ids,
        message=f"Assigned {len(payload.farm_ids)} farm(s) to {manager.name}",
    )


def _digest_to_schema(raw: dict) -> AdminDailyDigestOut:
    def _farm_row(item: dict) -> DailyDigestFarmBreakdown:
        return DailyDigestFarmBreakdown(
            farm_id=item["farm_id"],
            farm_name=item["farm_name"],
            sessions_count=item["sessions_count"],
            plants_scanned=item["plants_scanned"],
            issues_found=item["issues_found"],
            problem_rate=item["problem_rate"],
        )

    return AdminDailyDigestOut(
        period_start=raw["period_start"],
        period_end=raw["period_end"],
        farms_scanned=raw["farms_scanned"],
        managers_active=raw["managers_active"],
        total_sessions=raw["total_sessions"],
        total_plants_checked=raw["total_plants_checked"],
        total_issues_found=raw["total_issues_found"],
        breakdown_by_farm=[_farm_row(f) for f in raw["breakdown_by_farm"]],
        top_concerning_farms=[_farm_row(f) for f in raw["top_concerning_farms"]],
        manager_names=raw.get("manager_names", []),
    )


@admin_router.get("/daily-digest", response_model=AdminDailyDigestOut)
def admin_daily_digest(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Consolidated summary of all scan sessions from the last 24 hours."""
    return _digest_to_schema(build_daily_digest(db, hours=24))


@admin_router.post("/daily-digest/send", response_model=DailyDigestSendOut)
def admin_send_daily_digest(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Build the daily digest and email it to all admin users."""
    result = send_daily_digest_email(db, hours=24)
    digest = _digest_to_schema(result["digest"])
    if result["admin_recipients"] == 0:
        message = "No admin users found to email"
    elif result["email_sent"]:
        message = f"Daily digest emailed to {result['admin_recipients']} admin(s)"
    else:
        message = "Digest built but email not sent (SMTP not configured or send failed)"
    return DailyDigestSendOut(
        digest=digest,
        email_sent=result["email_sent"],
        admin_recipients=result["admin_recipients"],
        message=message,
    )
