"""Registro del servidor MCP «eink» en la configuración de Claude Desktop.

Claude Desktop guarda su configuración en memoria y la reescribe al cerrarse,
así que hay que editarla con la app cerrada del todo (bandeja > Quit): si no,
el cambio se pierde. Lo usan el instalador (EInkAssistant.exe --register-mcp),
la ventana del programa y tools/install_claude_mcp.py.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .paths import mcp_command

# La versión de Microsoft Store (MSIX) lee la configuración de su carpeta virtualizada.
STORE_CONFIG = (Path(os.environ.get("LOCALAPPDATA", "")) / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache"
                / "Roaming" / "Claude" / "claude_desktop_config.json")
CLASSIC_CONFIG = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
STORE_APP_ID = r"shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude"


def claude_running() -> bool:
    """¿Está abierta la app de escritorio? (no cuenta el claude.exe de Claude Code)."""
    import psutil

    for proc in psutil.process_iter(["name", "exe"]):
        name = (proc.info["name"] or "").lower()
        exe = (proc.info["exe"] or "").lower()
        if name == "claude.exe" and "claude-code" not in exe:
            return True
    return False


def is_store_install() -> bool:
    return STORE_CONFIG.parent.exists()


def config_path() -> Path:
    return STORE_CONFIG if is_store_install() else CLASSIC_CONFIG


def is_registered() -> bool:
    try:
        cfg = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    command, _ = mcp_command()
    entry = cfg.get("mcpServers", {}).get("eink", {})
    return Path(entry.get("command", "")) == command


def register() -> Path:
    """Añade (o actualiza) la entrada «eink». Claude Desktop debe estar cerrado."""
    path = config_path()
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(path, backup)
    command, args = mcp_command()
    cfg.setdefault("mcpServers", {})["eink"] = {"command": str(command), "args": args}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def reopen_claude() -> None:
    if is_store_install():
        subprocess.Popen(["explorer.exe", STORE_APP_ID])


def register_interactive(parent=None) -> bool:
    """Versión con ventanas: pide cerrar Claude Desktop, registra y lo reabre."""
    from tkinter import messagebox

    title = "Conectar con Claude Desktop"
    while claude_running():
        if not messagebox.askokcancel(
                title, "Cierra Claude Desktop del todo: icono de Claude en la bandeja del sistema > Quit "
                       "(cerrar la ventana no basta).\n\nCuando esté cerrado, pulsa Aceptar.", parent=parent):
            return False
    time.sleep(2)  # que Claude termine de escribir su configuración al cerrarse
    try:
        path = register()
    except (OSError, ValueError) as e:
        messagebox.showerror(title, f"No se pudo modificar la configuración de Claude Desktop:\n{e}", parent=parent)
        return False
    reopen_claude()
    messagebox.showinfo(title, "Listo. Claude Desktop ya puede escribir en la E-Ink (herramienta «eink»).\n\n"
                               "Deja abierto E-Ink Assistant (basta en la bandeja).\n\n"
                               f"Configuración: {path}", parent=parent)
    return True
