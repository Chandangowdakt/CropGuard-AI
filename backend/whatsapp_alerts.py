"""
CropGuard AI — WhatsApp alerts via Twilio REST API (no Twilio SDK).

── How to set up Twilio WhatsApp Sandbox (free trial) ──────────────────────

1. Create a free account at https://www.twilio.com/try-twilio

2. In the Twilio Console, open: Messaging → Try it out → Send a WhatsApp message

3. Join the sandbox from your phone:
   - Open WhatsApp on your mobile
   - Send the join message shown in the console (e.g. "join happy-plant")
     to the Twilio sandbox number: +1 415 523 8886

4. Copy your credentials from the Twilio Console home page:
   - Account SID  → paste as TWILIO_SID in backend/.env
   - Auth Token   → paste as TWILIO_TOKEN in backend/.env

5. Set in backend/.env:
   TWILIO_FROM=whatsapp:+14155238886   (Twilio sandbox sender)
   ALERT_PHONE=whatsapp:+91XXXXXXXXXX  (your phone, include country code)

6. Restart the CropGuard backend after saving .env

Messages are only sent when a problem detection is saved with confidence > 80%.
A 30-minute cooldown applies per farm + problem class to avoid spam.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import os

import requests
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

COOLDOWN_MINUTES = 30
WHATSAPP_CONFIDENCE_THRESHOLD = 80.0

_CLASS_ACTIONS = {
    "diseased": "Apply fungicide within 48 hours",
    "pest_affected": "Apply pesticide and check surrounding plants",
    "water_stressed": "Water this plant immediately and check irrigation",
}

# (farm_name, class_name) → last send time (UTC)
_cooldown: dict[tuple[str, str], datetime] = {}


def _is_configured() -> bool:
    return bool(
        os.getenv("TWILIO_SID")
        and os.getenv("TWILIO_TOKEN")
        and os.getenv("TWILIO_FROM")
        and os.getenv("ALERT_PHONE")
    )


def _format_timestamp(ts: datetime) -> str:
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M")
    return str(ts)


def send_whatsapp_alert(
    farm_name: str,
    class_name: str,
    confidence: float,
    timestamp: datetime,
    *,
    custom_body: str | None = None,
    bypass_cooldown: bool = False,
) -> bool:
    """
    Send a WhatsApp alert via Twilio. Returns True if sent, False if skipped.
    Skips silently when not configured, on cooldown, or on API failure.
    Pass custom_body to override the default template (e.g. urgent scan alerts).
    """
    if not _is_configured():
        print("WhatsApp not configured")
        return False

    key = (farm_name, class_name)
    now = datetime.utcnow()
    last_sent = _cooldown.get(key)
    if not bypass_cooldown and last_sent and (now - last_sent) < timedelta(minutes=COOLDOWN_MINUTES):
        return False

    if custom_body:
        body = custom_body
    else:
        problem_label = class_name.replace("_", " ").upper()
        action = _CLASS_ACTIONS.get(class_name, "Inspect the affected plants immediately")
        time_str = _format_timestamp(timestamp)
        body = (
            f"🌿 CropGuard AI Alert\n"
            f"Farm: {farm_name}\n"
            f"Problem: {problem_label}\n"
            f"Confidence: {confidence:.1f}%\n"
            f"Time: {time_str}\n"
            f"Action: {action}"
        )

    sid = os.getenv("TWILIO_SID", "")
    token = os.getenv("TWILIO_TOKEN", "")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    try:
        response = requests.post(
            url,
            auth=(sid, token),
            data={
                "From": os.getenv("TWILIO_FROM"),
                "To": os.getenv("ALERT_PHONE"),
                "Body": body,
            },
            timeout=15,
        )
        if response.ok:
            if not bypass_cooldown:
                _cooldown[key] = now
            print(f"  ✓  WhatsApp alert sent — {farm_name}")
            return True
        print(f"  ⚠  WhatsApp send failed ({response.status_code}): {response.text[:200]}")
        return False
    except requests.RequestException as exc:
        print(f"  ⚠  WhatsApp request error: {exc}")
        return False
