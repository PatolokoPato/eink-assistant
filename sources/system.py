"""Estado del PC: uso de CPU, RAM y disco, y temperaturas.

Temperaturas en Windows:
  - GPU: nvidia-smi, si hay gráfica NVIDIA.
  - CPU: Windows no la expone sin permisos de administrador (la "zona térmica"
    ACPI suele dar un valor fijo de la placa). Se lee de LibreHardwareMonitor
    por WMI si está abierto; si no, queda en None.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass

import psutil

log = logging.getLogger(__name__)

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


@dataclass(frozen=True)
class SystemStatus:
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disk_percent: float
    cpu_temp: float | None = None  # °C
    gpu_temp: float | None = None  # °C


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=8, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug("%s falló: %s", cmd[0], e)
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def gpu_temperature() -> float | None:
    if not shutil.which("nvidia-smi"):
        return None
    out = _run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"])
    try:
        return float(out.splitlines()[0]) if out else None
    except ValueError:
        return None


def cpu_temperature() -> float | None:
    if sys.platform != "win32":
        temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
        for name in ("coretemp", "k10temp", "cpu_thermal"):
            if temps.get(name):
                return temps[name][0].current
        return None
    # LibreHardwareMonitor publica sus sensores en root/LibreHardwareMonitor.
    script = ("Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor "
              "-ErrorAction Stop | Where-Object { $_.SensorType -eq 'Temperature' -and "
              "$_.Name -match 'Package|Tctl|Tdie|CPU Total' } | "
              "Select-Object -First 1 -ExpandProperty Value")
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    try:
        return float(out.replace(",", ".")) if out else None
    except ValueError:
        return None


def get_system_status(disk: str = "C:\\" if sys.platform == "win32" else "/") -> SystemStatus:
    mem = psutil.virtual_memory()
    return SystemStatus(
        cpu_percent=psutil.cpu_percent(interval=0.5),
        ram_percent=mem.percent,
        ram_used_gb=mem.used / 2**30,
        ram_total_gb=mem.total / 2**30,
        disk_percent=psutil.disk_usage(disk).percent,
        cpu_temp=cpu_temperature(),
        gpu_temp=gpu_temperature(),
    )
