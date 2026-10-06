"""Accesos directos de Windows: inicio automático y escritorio.

Lanzan el programa sin consola (EInkAssistant.exe si está instalado, o
pythonw.exe -m ui desde el código); el de inicio añade `--minimized` para
arrancar directamente en la bandeja.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .app_settings import APP_DIR
from .paths import INSTALL_DIR, app_command

ICON_FILE = APP_DIR / "eink-assistant.ico"  # lo escribe ui/app.py al arrancar
STARTUP_SHORTCUT = (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                    / "Startup" / "E-Ink Assistant.lnk")


def _create_shortcut(lnk: Path, *args: str) -> None:
    lnk.parent.mkdir(parents=True, exist_ok=True)
    # Se crea con WScript.Shell vía PowerShell para no depender de pywin32.
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); "
        "$s.TargetPath = $env:TARGET; $s.Arguments = $env:ARGS; "
        "$s.WorkingDirectory = $env:WORKDIR; $s.Description = 'E-Ink Assistant'; "
        "if (Test-Path $env:ICON) { $s.IconLocation = $env:ICON + ',0' }; $s.Save()"
    )
    target, arguments = app_command(*args)
    env = dict(os.environ, LNK=str(lnk), TARGET=str(target), ARGS=" ".join(arguments), WORKDIR=str(INSTALL_DIR),
               ICON=str(ICON_FILE))
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                   check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def is_enabled() -> bool:
    return STARTUP_SHORTCUT.exists()


def enable() -> None:
    _create_shortcut(STARTUP_SHORTCUT, "--minimized")


def disable() -> None:
    STARTUP_SHORTCUT.unlink(missing_ok=True)


def create_desktop_shortcut() -> Path:
    # El Escritorio puede estar redirigido (OneDrive): se pregunta a Windows dónde está.
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                          "[Environment]::GetFolderPath('Desktop')"], capture_output=True, text=True,
                         check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lnk = Path(out.stdout.strip()) / "E-Ink Assistant.lnk"
    _create_shortcut(lnk)
    return lnk
