"""
Center-crop helper for Live Scan leaf focus.
Crops ~70% of the frame around the center before inference.
Full-frame bytes are kept separately for storage/alerts.
"""

from __future__ import annotations

import io
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from PIL import Image

# Fraction of the shorter side to keep (centered). 0.7 ≈ "focus on leaf".
CROP_RATIO = 0.70


def center_crop_image_bytes(image_bytes: bytes, ratio: float = CROP_RATIO) -> bytes:
    """
    Return JPEG bytes of a center crop of the input image.
    Falls back to original bytes if decode fails or image is tiny.
    """
    if not image_bytes:
        return image_bytes

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return image_bytes

    width, height = image.size
    if width < 32 or height < 32:
        return image_bytes

    ratio = max(0.3, min(1.0, float(ratio)))
    crop_w = max(1, int(width * ratio))
    crop_h = max(1, int(height * ratio))
    left = (width - crop_w) // 2
    top = (height - crop_h) // 2
    right = left + crop_w
    bottom = top + crop_h

    cropped = image.crop((left, top, right, bottom))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
