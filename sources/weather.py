"""Tiempo actual desde Open-Meteo (gratis, sin clave de API).

La ubicación sale de EINK_CITY (se geocodifica una vez) o de EINK_LAT/EINK_LON.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10

# Códigos WMO que usa Open-Meteo.
_WMO = {
    0: "Despejado", 1: "Casi despejado", 2: "Parcialmente nuboso", 3: "Nublado",
    45: "Niebla", 48: "Niebla con escarcha",
    51: "Llovizna débil", 53: "Llovizna", 55: "Llovizna intensa",
    56: "Llovizna helada", 57: "Llovizna helada",
    61: "Lluvia débil", 63: "Lluvia", 65: "Lluvia intensa",
    66: "Lluvia helada", 67: "Lluvia helada",
    71: "Nieve débil", 73: "Nieve", 75: "Nieve intensa", 77: "Granizo fino",
    80: "Chubascos débiles", 81: "Chubascos", 82: "Chubascos fuertes",
    85: "Chubascos de nieve", 86: "Chubascos de nieve",
    95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta con granizo",
}


def describe(code: int) -> str:
    return _WMO.get(code, "—")


@dataclass(frozen=True)
class Weather:
    place: str
    temperature: float  # °C
    description: str
    humidity: int       # %
    temp_min: float
    temp_max: float
    code: int = 3       # código WMO (para el icono)


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float


def _get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=TIMEOUT) as resp:
        return json.load(resp)


@lru_cache(maxsize=8)
def geocode(city: str) -> Location:
    data = _get_json(GEOCODE_URL, {"name": city, "count": 1, "language": "es", "format": "json"})
    results = data.get("results") or []
    if not results:
        raise LookupError(f"Open-Meteo no conoce la ciudad {city!r}")
    r = results[0]
    return Location(r["name"], r["latitude"], r["longitude"])


def parse_forecast(place: str, data: dict) -> Weather:
    cur, daily = data["current"], data["daily"]
    return Weather(
        place=place,
        temperature=cur["temperature_2m"],
        description=describe(cur["weather_code"]),
        humidity=round(cur["relative_humidity_2m"]),
        temp_min=daily["temperature_2m_min"][0],
        temp_max=daily["temperature_2m_max"][0],
        code=cur["weather_code"],
    )


def fetch_weather(loc: Location) -> Weather:
    data = _get_json(FORECAST_URL, {
        "latitude": loc.latitude, "longitude": loc.longitude,
        "current": "temperature_2m,weather_code,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto", "forecast_days": 1,
    })
    return parse_forecast(loc.name, data)


def get_weather(city: str | None, lat: float | None = None, lon: float | None = None) -> Weather | None:
    """El tiempo actual, o None si no hay ubicación configurada o falla la red."""
    try:
        if lat is not None and lon is not None:
            loc = Location(city or f"{lat:.2f}, {lon:.2f}", lat, lon)
        elif city:
            loc = geocode(city)
        else:
            return None
        return fetch_weather(loc)
    except Exception as e:  # noqa: BLE001 — sin red no debe caerse la pantalla
        log.warning("No se pudo obtener el tiempo: %s", e)
        return None
