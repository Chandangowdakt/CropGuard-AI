"""
Temporal smoothing and plant-zone IDs for Live Scan sessions.

Keeps a short per-session prediction window in memory (no DB writes).
Confirms disease when majority of recent frames are Bacterial/Septoria
with average confidence >= threshold.
"""

from __future__ import annotations

import math
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from class_constants import PROBLEM_CLASSES, normalize_class

WINDOW_SIZE = 3
MIN_CONFIDENCE = 70.0
ZONE_GAP_SECONDS = 8.0
# ~5 meters movement starts a new plant zone (approx degrees)
GPS_MOVE_DEG = 0.00005


@dataclass
class _FramePred:
    class_name: str
    confidence: float
    latitude: float | None
    longitude: float | None
    ts: float


@dataclass
class _SessionState:
    history: deque = field(default_factory=lambda: deque(maxlen=WINDOW_SIZE))
    zone_seq: int = 0
    last_zone_id: str | None = None
    last_flag_ts: float = 0.0
    last_flag_lat: float | None = None
    last_flag_lon: float | None = None


_sessions: dict[int, _SessionState] = defaultdict(_SessionState)


def _gps_moved(
    lat1: float | None,
    lon1: float | None,
    lat2: float | None,
    lon2: float | None,
) -> bool:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return False
    return math.hypot(lat2 - lat1, lon2 - lon1) >= GPS_MOVE_DEG


def reset_session(session_id: int | None) -> None:
    if session_id is None:
        return
    _sessions.pop(int(session_id), None)


def update_prediction(
    session_id: int | None,
    class_name: str,
    confidence: float,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    """
    Update rolling window and return smoothed view.

    Returns:
      {
        "smoothed_class": str,
        "smoothed_confidence": float,
        "is_confirmed_problem": bool,
        "plant_zone_id": str | None,
      }
    """
    raw = normalize_class(class_name) or class_name
    now = time.time()

    if session_id is None:
        is_problem = raw in PROBLEM_CLASSES and confidence >= MIN_CONFIDENCE
        return {
            "smoothed_class": raw,
            "smoothed_confidence": confidence,
            "is_confirmed_problem": is_problem,
            "plant_zone_id": None,
        }

    sid = int(session_id)
    state = _sessions[sid]
    state.history.append(
        _FramePred(
            class_name=raw,
            confidence=float(confidence),
            latitude=latitude,
            longitude=longitude,
            ts=now,
        )
    )

    frames = list(state.history)
    # Majority class among window
    counts: dict[str, int] = {}
    conf_sum: dict[str, float] = {}
    for f in frames:
        counts[f.class_name] = counts.get(f.class_name, 0) + 1
        conf_sum[f.class_name] = conf_sum.get(f.class_name, 0.0) + f.confidence

    smoothed_class = max(counts.items(), key=lambda x: (x[1], conf_sum[x[0]]))[0]
    smoothed_confidence = conf_sum[smoothed_class] / counts[smoothed_class]

    is_confirmed = (
        smoothed_class in PROBLEM_CLASSES
        and smoothed_confidence >= MIN_CONFIDENCE
        and counts[smoothed_class] >= max(1, (len(frames) + 1) // 2)
    )

    plant_zone_id = None
    if is_confirmed:
        need_new_zone = (
            state.last_zone_id is None
            or (now - state.last_flag_ts) >= ZONE_GAP_SECONDS
            or _gps_moved(state.last_flag_lat, state.last_flag_lon, latitude, longitude)
        )
        if need_new_zone:
            state.zone_seq += 1
            state.last_zone_id = f"row-{sid}-{state.zone_seq}"
            state.last_flag_ts = now
            state.last_flag_lat = latitude
            state.last_flag_lon = longitude
        plant_zone_id = state.last_zone_id

    return {
        "smoothed_class": smoothed_class,
        "smoothed_confidence": round(float(smoothed_confidence), 2),
        "is_confirmed_problem": is_confirmed,
        "plant_zone_id": plant_zone_id,
    }
