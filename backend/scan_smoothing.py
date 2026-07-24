"""
Temporal smoothing and plant-zone IDs for Live Scan sessions.

Keeps a short per-session prediction window in memory (no DB writes).
Confirms disease only with a full window majority of Bacterial/Septoria
and average confidence >= threshold.
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
# When GPS is unavailable, open a new zone after this idle gap
ZONE_GAP_SECONDS = 8.0
# ~5 meters of real movement starts a new plant zone
GPS_MOVE_METERS = 5.0


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


def _haversine_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _gps_moved(
    lat1: float | None,
    lon1: float | None,
    lat2: float | None,
    lon2: float | None,
) -> bool:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return False
    return _haversine_meters(lat1, lon1, lat2, lon2) >= GPS_MOVE_METERS


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
        # No session: never auto-confirm (avoid single-frame false alerts)
        return {
            "smoothed_class": raw,
            "smoothed_confidence": confidence,
            "is_confirmed_problem": False,
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
    counts: dict[str, int] = {}
    conf_sum: dict[str, float] = {}
    for f in frames:
        counts[f.class_name] = counts.get(f.class_name, 0) + 1
        conf_sum[f.class_name] = conf_sum.get(f.class_name, 0.0) + f.confidence

    smoothed_class = max(counts.items(), key=lambda x: (x[1], conf_sum[x[0]]))[0]
    smoothed_confidence = conf_sum[smoothed_class] / counts[smoothed_class]

    # Require a full window and a strict majority (> half of frames)
    full_window = len(frames) >= WINDOW_SIZE
    majority = counts[smoothed_class] > (len(frames) / 2)
    is_confirmed = (
        full_window
        and majority
        and smoothed_class in PROBLEM_CLASSES
        and smoothed_confidence >= MIN_CONFIDENCE
    )

    plant_zone_id = None
    if is_confirmed:
        has_gps = latitude is not None and longitude is not None
        moved = _gps_moved(state.last_flag_lat, state.last_flag_lon, latitude, longitude)
        timed_out_no_gps = (
            not has_gps
            and state.last_zone_id is not None
            and (now - state.last_flag_ts) >= ZONE_GAP_SECONDS
        )
        need_new_zone = state.last_zone_id is None or moved or timed_out_no_gps
        if need_new_zone:
            state.zone_seq += 1
            state.last_zone_id = f"row-{sid}-{state.zone_seq}"
            state.last_flag_ts = now
            state.last_flag_lat = latitude
            state.last_flag_lon = longitude
        else:
            state.last_flag_ts = now
        plant_zone_id = state.last_zone_id

    return {
        "smoothed_class": smoothed_class,
        "smoothed_confidence": round(float(smoothed_confidence), 2),
        "is_confirmed_problem": is_confirmed,
        "plant_zone_id": plant_zone_id,
    }
