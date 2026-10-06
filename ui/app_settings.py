"""Preferencias del programa, guardadas en %APPDATA%\\eink-assistant\\settings.json."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "eink-assistant"
SETTINGS_FILE = APP_DIR / "settings.json"


@dataclass
class AppSettings:
    port: str | None = None      # None = autodetectar
    view_id: str = "home"
    auto: bool = True
    interval_min: int = 5
    update_on_start: bool = True
    invert: bool = False         # True = blanco sobre negro
    # True = el servidor MCP pide a Claude Desktop que envíe un resumen de cada
    # respuesta a la E-Ink, aunque no se le pida (se lee al arrancar Claude).
    mcp_always: bool = False
    hotkeys: bool = True         # atajos de teclado globales (ui/hotkeys.py)

    @classmethod
    def load(cls, path: Path = SETTINGS_FILE) -> "AppSettings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as e:
            log.warning("No se pudieron leer las preferencias (%s); uso las de por defecto", e)
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path = SETTINGS_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
