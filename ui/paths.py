"""Cómo se lanza el programa: desde el código (.venv) o instalado (.exe de PyInstaller).

Los accesos directos y el registro en Claude Desktop necesitan saber qué
ejecutable y qué argumentos usar en cada caso.
"""

from __future__ import annotations

import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))  # True en la versión instalada
PROJECT_DIR = Path(__file__).resolve().parent.parent
INSTALL_DIR = Path(sys.executable).parent if FROZEN else PROJECT_DIR


def _pythonw() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def app_command(*args: str) -> tuple[Path, list[str]]:
    """(ejecutable, argumentos) para abrir el programa de escritorio sin consola."""
    if FROZEN:
        return Path(sys.executable), list(args)
    return _pythonw(), ["-m", "ui", *args]


def mcp_command() -> tuple[Path, list[str]]:
    """(ejecutable, argumentos) del servidor MCP para Claude Desktop."""
    if FROZEN:
        return INSTALL_DIR / "EInkMCP.exe", []
    return Path(sys.executable).with_name("python.exe"), [str(PROJECT_DIR / "mcp_server" / "eink_mcp.py")]
