"""Configuración de la aplicación.

Por ahora solo lo necesario para la Fase 1. Los valores pueden sobreescribirse
con variables de entorno, p. ej. en PowerShell:

    $env:EINK_PORT = "COM5"
    $env:EINK_BAUD = "460800"
    $env:EINK_CITY = "Valencia"     # por defecto, Madrid

Para dejar tu ubicación fija sin escribirla en el código (no se sube al repositorio):

    [Environment]::SetEnvironmentVariable("EINK_CITY", "Mi ciudad", "User")
    [Environment]::SetEnvironmentVariable("EINK_LAT", "40.4168", "User")
    [Environment]::SetEnvironmentVariable("EINK_LON", "-3.7038", "User")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


@dataclass
class SerialSettings:
    port: str | None = field(default_factory=lambda: os.environ.get("EINK_PORT") or None)
    # Debe coincidir con SERIAL_BAUD en firmware/esp32_eink/config.h
    baudrate: int = field(default_factory=lambda: _env_int("EINK_BAUD", 921600))
    # Tiempo máximo esperando a que el ESP32 arranque y conteste (s).
    connect_timeout: float = 6.0
    # Espera máxima a que el panel termine de refrescar: ~1,5 s el WeAct B/N,
    # ~25 s la variante de tres colores.
    ack_timeout: float = 40.0


def _env_float(name: str) -> float | None:
    value = os.environ.get(name)
    return float(value) if value else None


# Ubicación por defecto si no hay variables de entorno: Madrid.
_DEFAULT_CITY, _DEFAULT_LAT, _DEFAULT_LON = "Madrid", 40.4168, -3.7038


@dataclass
class WeatherSettings:
    # Ciudad para el tiempo. EINK_LAT/EINK_LON, si están, tienen prioridad y
    # evitan la búsqueda de la ciudad. Sin ninguna variable, Madrid.
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        if self.city is not None or self.latitude is not None:
            return  # valores pasados explícitamente
        env_city = os.environ.get("EINK_CITY") or None
        env_lat, env_lon = _env_float("EINK_LAT"), _env_float("EINK_LON")
        if env_city or env_lat is not None:
            self.city, self.latitude, self.longitude = env_city, env_lat, env_lon
        else:
            self.city, self.latitude, self.longitude = _DEFAULT_CITY, _DEFAULT_LAT, _DEFAULT_LON


@dataclass
class Settings:
    serial: SerialSettings = field(default_factory=SerialSettings)
    weather: WeatherSettings = field(default_factory=WeatherSettings)


def load_settings() -> Settings:
    return Settings()
