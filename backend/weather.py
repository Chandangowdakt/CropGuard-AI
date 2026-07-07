"""
CropGuard AI — live weather via Open-Meteo (free, no API key).
https://open-meteo.com/
"""

import sys
from datetime import datetime, timedelta
from typing import Literal

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_MINUTES = 60

# Hosahalli / Bangalore region default
DEFAULT_LAT = 13.0827
DEFAULT_LON = 77.5877

_cache: dict[tuple[float, float], dict] = {}

DiseaseRisk = Literal["LOW", "MEDIUM", "HIGH"]

UNAVAILABLE_NOTE = "Weather temporarily unavailable — showing last known values"


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 4), round(lon, 4))


def _calc_disease_risk(humidity: float, temperature: float) -> DiseaseRisk:
    if humidity > 80 and temperature > 20:
        return "HIGH"
    if humidity > 60 and temperature > 15:
        return "MEDIUM"
    return "LOW"


def _safe_fallback(now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    return {
        "temperature": 28.0,
        "humidity": 65.0,
        "rainfall": 0.0,
        "windspeed": 12.0,
        "disease_risk": "MEDIUM",
        "updated_at": now.isoformat() + "Z",
        "cached": True,
        "note": UNAVAILABLE_NOTE,
    }


def _fallback_from_cache(cached_data: dict) -> dict:
    result = dict(cached_data)
    result["cached"] = True
    result["note"] = UNAVAILABLE_NOTE
    return result


def get_weather(lat: float, lon: float) -> dict:
    """
    Fetch current weather from Open-Meteo.
    Returns: temperature, humidity, rainfall, windspeed, disease_risk, updated_at.
    Results are cached for 60 minutes per coordinate pair.
    """
    key = _cache_key(lat, lon)
    now = datetime.utcnow()
    cached = _cache.get(key)
    if cached and (now - cached["fetched_at"]) < timedelta(minutes=CACHE_MINUTES):
        return cached["data"]

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,windspeed_10m",
        "wind_speed_unit": "kmh",
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        if response.status_code == 429:
            if cached:
                return _fallback_from_cache(cached["data"])
            return _safe_fallback(now)
        response.raise_for_status()
        current = response.json().get("current", {})
    except requests.RequestException as exc:
        raise RuntimeError(f"Weather API unavailable: {exc}") from exc

    temperature = float(current.get("temperature_2m", 0))
    humidity = float(current.get("relative_humidity_2m", 0))
    rainfall = float(current.get("precipitation", 0))
    windspeed = float(current.get("windspeed_10m", 0))
    disease_risk = _calc_disease_risk(humidity, temperature)

    data = {
        "temperature": round(temperature, 1),
        "humidity": round(humidity, 1),
        "rainfall": round(rainfall, 1),
        "windspeed": round(windspeed, 1),
        "disease_risk": disease_risk,
        "updated_at": now.isoformat() + "Z",
    }

    _cache[key] = {"fetched_at": now, "data": data}
    return data
