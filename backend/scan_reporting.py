"""
CropGuard AI — automatic scan session reports and daily digests for admins.
"""

import sys
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import os

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from email_alerts import send_email_alert
from models import Detection, Farm, ScanSession, User
from whatsapp_alerts import send_whatsapp_alert

URGENT_PROBLEM_RATE_THRESHOLD = 15.0
FRONTEND_URL = os.getenv("FRONTEND_URL", os.getenv("DASHBOARD_URL", "http://localhost:5500"))


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 1)


def _format_scan_datetime(ts: datetime | None) -> str:
    if not ts:
        return "—"
    return ts.strftime("%Y-%m-%d %I:%M %p")


def _admin_emails(db: Session) -> list[str]:
    return [u.email for u in db.query(User).filter(User.role == "admin").all()]


def _problem_count(session: ScanSession) -> int:
    return session.diseased_count + session.pest_count + session.water_stressed_count


def _problem_rate(session: ScanSession) -> float:
    return _pct(_problem_count(session), session.total_scanned)


def _dashboard_link(session_id: int | None = None) -> str:
    base = FRONTEND_URL.rstrip("/")
    if session_id:
        return f"{base}/?view=admin&session={session_id}"
    return f"{base}/?view=admin"


def _load_attachment_images(db: Session, session_id: int, limit: int = 3) -> list[tuple[str, bytes, str]]:
    detections = (
        db.query(Detection)
        .filter(Detection.session_id == session_id)
        .order_by(Detection.confidence.desc())
        .limit(limit)
        .all()
    )
    attachments: list[tuple[str, bytes, str]] = []
    for i, det in enumerate(detections, start=1):
        path = Path(det.image_path)
        if not path.exists():
            continue
        try:
            data = path.read_bytes()
            attachments.append((f"flagged_{i}_{det.predicted_class}.jpg", data, "image/jpeg"))
        except OSError:
            continue
    return attachments


def _build_summary_image(
    farm_name: str,
    manager_name: str,
    session: ScanSession,
    flagged_count: int,
) -> bytes:
    lines = [
        "CropGuard AI — Scan Report",
        f"Farm: {farm_name}",
        f"Manager: {manager_name}",
        f"Completed: {_format_scan_datetime(session.completed_at)}",
        f"Plants scanned: {session.total_scanned}",
        f"Healthy: {session.healthy_count} ({_pct(session.healthy_count, session.total_scanned)}%)",
        f"Diseased: {session.diseased_count} ({_pct(session.diseased_count, session.total_scanned)}%)",
        f"Pest: {session.pest_count} ({_pct(session.pest_count, session.total_scanned)}%)",
        f"Water stressed: {session.water_stressed_count} ({_pct(session.water_stressed_count, session.total_scanned)}%)",
        f"Flagged plants: {flagged_count}",
    ]
    width, height = 640, 40 + len(lines) * 28
    img = Image.new("RGB", (width, height), color=(248, 252, 249))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        title_font = ImageFont.truetype("arialbd.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        title_font = font

    y = 16
    draw.text((20, y), lines[0], fill=(26, 95, 58), font=title_font)
    y += 32
    for line in lines[1:]:
        draw.text((20, y), line, fill=(40, 40, 40), font=font)
        y += 26

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_scan_session_email(
    db: Session,
    session: ScanSession,
    farm: Farm,
    manager: User | None,
) -> tuple[str, str, list[tuple[str, bytes, str]]]:
    """Return (subject, body, attachments) for a completed scan session."""
    farm_name = farm.name
    manager_name = manager.name if manager else "Unknown"
    completed = session.completed_at or datetime.utcnow()
    total = session.total_scanned
    flagged_count = (
        db.query(Detection).filter(Detection.session_id == session.id).count()
    )

    subject = (
        f"Scan Report - {farm_name} by {manager_name} - "
        f"{completed.strftime('%Y-%m-%d')}"
    )

    body = (
        f"Farm: {farm_name}\n"
        f"Manager: {manager_name}\n"
        f"Scan completed: {_format_scan_datetime(completed)}\n"
        f"Plants scanned: {total}\n"
        f"Healthy: {session.healthy_count} ({_pct(session.healthy_count, total)}%)\n"
        f"Diseased: {session.diseased_count} ({_pct(session.diseased_count, total)}%)\n"
        f"Pest affected: {session.pest_count} ({_pct(session.pest_count, total)}%)\n"
        f"Water stressed: {session.water_stressed_count} ({_pct(session.water_stressed_count, total)}%)\n"
        f"Flagged plants requiring attention: {flagged_count}\n"
        f"\nView full report in dashboard:\n{_dashboard_link(session.id)}\n"
    )

    attachments = _load_attachment_images(db, session.id, limit=3)
    if not attachments:
        attachments = [
            ("scan_summary.png", _build_summary_image(farm_name, manager_name, session, flagged_count), "image/png")
        ]

    return subject, body, attachments


def notify_scan_session_completed(db: Session, session: ScanSession, farm: Farm) -> dict:
    """
    Email all admins on session complete; send urgent WhatsApp if problem rate > 15%.
    Returns a small status dict for logging/testing.
    """
    manager = db.query(User).filter(User.id == session.manager_id).first()
    admin_list = _admin_emails(db)

    email_sent = False
    if admin_list:
        subject, body, attachments = build_scan_session_email(db, session, farm, manager)
        email_sent = send_email_alert(admin_list, subject, body, attachments=attachments)

    problem_rate = _problem_rate(session)
    whatsapp_sent = False
    if problem_rate > URGENT_PROBLEM_RATE_THRESHOLD:
        manager_name = manager.name if manager else "Manager"
        urgent_body = (
            f"URGENT: {farm.name} shows {problem_rate:.0f}% plant health issues found "
            f"during {manager_name}'s scan today. Immediate attention recommended."
        )
        whatsapp_sent = send_whatsapp_alert(
            farm.name,
            "scan_urgent",
            problem_rate,
            session.completed_at or datetime.utcnow(),
            custom_body=urgent_body,
            bypass_cooldown=True,
        )

    return {
        "email_sent": email_sent,
        "whatsapp_urgent_sent": whatsapp_sent,
        "problem_rate": problem_rate,
        "admin_recipients": len(admin_list),
    }


def build_daily_digest(db: Session, hours: int = 24) -> dict:
    """Aggregate completed scan sessions from the last N hours."""
    now = datetime.utcnow()
    since = now - timedelta(hours=hours)

    sessions = (
        db.query(ScanSession)
        .filter(
            ScanSession.status == "completed",
            ScanSession.completed_at.isnot(None),
            ScanSession.completed_at >= since,
        )
        .all()
    )

    farms = {f.id: f for f in db.query(Farm).all()}
    managers = {u.id: u for u in db.query(User).all()}

    farm_stats: dict[int, dict] = {}
    active_managers: set[int] = set()
    total_plants = 0
    total_issues = 0

    for s in sessions:
        active_managers.add(s.manager_id)
        total_plants += s.total_scanned
        issues = _problem_count(s)
        total_issues += issues

        if s.farm_id not in farm_stats:
            farm_stats[s.farm_id] = {
                "farm_id": s.farm_id,
                "farm_name": farms[s.farm_id].name if s.farm_id in farms else f"Farm #{s.farm_id}",
                "sessions_count": 0,
                "plants_scanned": 0,
                "issues_found": 0,
            }
        farm_stats[s.farm_id]["sessions_count"] += 1
        farm_stats[s.farm_id]["plants_scanned"] += s.total_scanned
        farm_stats[s.farm_id]["issues_found"] += issues

    breakdown = []
    for stats in farm_stats.values():
        plants = stats["plants_scanned"]
        stats["problem_rate"] = _pct(stats["issues_found"], plants)
        breakdown.append(stats)

    breakdown.sort(key=lambda x: x["farm_name"])
    top_concerning = sorted(
        breakdown,
        key=lambda x: (x["problem_rate"], x["issues_found"]),
        reverse=True,
    )[:3]

    return {
        "period_start": since,
        "period_end": now,
        "farms_scanned": len(farm_stats),
        "managers_active": len(active_managers),
        "total_plants_checked": total_plants,
        "total_issues_found": total_issues,
        "total_sessions": len(sessions),
        "breakdown_by_farm": breakdown,
        "top_concerning_farms": top_concerning,
        "manager_names": [
            managers[mid].name for mid in active_managers if mid in managers
        ],
    }


def format_daily_digest_email(digest: dict) -> tuple[str, str]:
    """Return (subject, body) for the daily digest email."""
    end = digest["period_end"]
    subject = f"CropGuard Daily Scan Digest — {end.strftime('%Y-%m-%d')}"

    lines = [
        "CropGuard AI — Daily Scan Digest (last 24 hours)",
        "",
        f"Farms scanned: {digest['farms_scanned']}",
        f"Managers active: {digest['managers_active']}",
        f"Total scan sessions: {digest['total_sessions']}",
        f"Total plants checked: {digest['total_plants_checked']}",
        f"Total issues found: {digest['total_issues_found']}",
        "",
        "Breakdown by farm:",
    ]

    if not digest["breakdown_by_farm"]:
        lines.append("  No scan sessions completed in the last 24 hours.")
    else:
        for farm in digest["breakdown_by_farm"]:
            lines.append(
                f"  • {farm['farm_name']}: {farm['plants_scanned']} plants, "
                f"{farm['issues_found']} issues ({farm['problem_rate']}%), "
                f"{farm['sessions_count']} session(s)"
            )

    lines.extend(["", "Top concerning farms:"])
    if not digest["top_concerning_farms"]:
        lines.append("  None")
    else:
        for i, farm in enumerate(digest["top_concerning_farms"], start=1):
            lines.append(
                f"  {i}. {farm['farm_name']} — {farm['problem_rate']}% problem rate "
                f"({farm['issues_found']} issues / {farm['plants_scanned']} plants)"
            )

    if digest.get("manager_names"):
        lines.extend(["", f"Active managers: {', '.join(digest['manager_names'])}"])

    lines.extend(["", f"Open admin dashboard: {_dashboard_link()}"])
    return subject, "\n".join(lines)


def send_daily_digest_email(db: Session, hours: int = 24) -> dict:
    """Build digest and email all admins. Returns digest + send status."""
    digest = build_daily_digest(db, hours=hours)
    admin_list = _admin_emails(db)
    subject, body = format_daily_digest_email(digest)
    email_sent = False
    if admin_list:
        email_sent = send_email_alert(admin_list, subject, body)

    return {
        "digest": digest,
        "email_sent": email_sent,
        "admin_recipients": len(admin_list),
    }
