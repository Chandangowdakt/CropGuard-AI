"""
CropGuard AI — email alerts via SMTP (stdlib).

Configure in backend/.env:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your@gmail.com
  SMTP_PASSWORD=your-app-password
  SMTP_FROM=your@gmail.com
  SMTP_USE_TLS=true
"""

import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import os
import smtplib

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)


def _is_configured() -> bool:
    return bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_USER")
        and os.getenv("SMTP_PASSWORD")
        and os.getenv("SMTP_FROM")
    )


def send_email_alert(
    to: list[str] | str,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """
    Send an email alert. Returns True if sent, False if skipped or failed.
    `attachments` is a list of (filename, data, mime_type) tuples.
    """
    if not _is_configured():
        print("Email not configured")
        return False

    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    if not recipients:
        print("Email skipped — no recipients")
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM", "")
    msg["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    for filename, data, mime_type in attachments or []:
        if mime_type.startswith("image/"):
            subtype = mime_type.split("/", 1)[1]
            part = MIMEImage(data, _subtype=subtype)
        else:
            from email.mime.application import MIMEApplication
            subtype = mime_type.split("/")[-1] if "/" in mime_type else mime_type
            part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_tls:
                server.starttls()
            server.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            server.sendmail(msg["From"], recipients, msg.as_string())
        print(f"  ✓  Email sent — {subject} → {', '.join(recipients)}")
        return True
    except smtplib.SMTPException as exc:
        print(f"  ⚠  Email send failed: {exc}")
        return False
    except OSError as exc:
        print(f"  ⚠  Email connection error: {exc}")
        return False
