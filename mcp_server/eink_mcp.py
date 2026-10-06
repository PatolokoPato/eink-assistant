"""Servidor MCP para Claude Desktop: deja que Claude escriba en la E-Ink.

Claude Desktop lo arranca solo (ver README, sección MCP). No toca el puerto
COM: manda el texto al programa E-Ink Assistant por su API local, así que el
programa tiene que estar abierto (en la bandeja basta).

Ojo: en MCP por stdio, stdout es el canal del protocolo; nada de print().
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer

PORT = int(os.environ.get("EINK_API_PORT") or 8765)
BASE = f"http://127.0.0.1:{PORT}"


def _always_show() -> bool:
    """¿Enviar cada respuesta a la E-Ink? EINK_SIEMPRE=1/0 manda; si no está,
    `mcp_always` de las preferencias del programa. Se lee al arrancar Claude."""
    env = os.environ.get("EINK_SIEMPRE")
    if env:
        return env.strip().lower() in ("1", "true", "si", "sí")
    # Mismo fichero que ui/app_settings.py (aquí no se importa: Claude Desktop
    # lanza este script suelto, sin el proyecto en sys.path).
    path = Path(os.environ.get("APPDATA", Path.home())) / "eink-assistant" / "settings.json"
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("mcp_always", False))
    except (OSError, ValueError, AttributeError):
        return False  # sin preferencias: comportamiento normal


INSTRUCTIONS = "Controla una pantalla de tinta electrónica de escritorio (400×300 px, blanco y negro). "
if _always_show():
    INSTRUCTIONS += (
        "El usuario quiere ver TODAS tus respuestas en la pantalla: al terminar cada respuesta, "
        "aunque no lo pida, llama a mostrar_en_eink con un resumen breve de lo que has contestado "
        "(lo esencial, unas pocas líneas) y en 'pregunta' su pregunta resumida. No lo menciones "
        "en el chat salvo que falle."
    )
else:
    INSTRUCTIONS += "Usa mostrar_en_eink cuando el usuario pida ver algo en la pantalla, la pantallita o la E-Ink."

server = MCPServer(name="eink", title="Pantalla E-Ink", instructions=INSTRUCTIONS)


def _call(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json", "X-EInk-Client": "mcp"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", str(e))
        except ValueError:
            msg = str(e)
        raise RuntimeError(f"La pantalla rechazó la petición: {msg}") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise RuntimeError(
            "El programa E-Ink Assistant no está abierto (o no responde). "
            "Pide al usuario que lo abra; queda en la bandeja del sistema."
        ) from e


@server.tool(description=(
    "Muestra un texto en la pantalla E-Ink del escritorio del usuario. La pantalla es pequeña "
    "(400×300 píxeles, blanco y negro, unas 12 líneas de ~40 caracteres por página) y tarda ~10 s "
    "en refrescar. Escribe para esa pantalla: texto plano y conciso, sin tablas, emojis ni bloques "
    "de código; para listas empieza cada elemento con '- '; '# Título' o una línea entera en "
    "**negrita** salen como subtítulo. Si el texto no cabe se reparte en páginas que el usuario "
    "pasa desde el PC. 'pregunta' (opcional) es la pregunta del usuario resumida en una línea; "
    "aparece encima como 'Tú: ...'."
))
def mostrar_en_eink(texto: str, pregunta: str = "") -> str:
    pages = _call("/show", {"text": texto, "question": pregunta})["pages"]
    return f"Enviado a la E-Ink ({pages} página{'s' if pages != 1 else ''}). Tardará unos 10 s en verse."


@server.tool(description="Pasa de página el texto que se está mostrando en la E-Ink.")
def pasar_pagina_eink(direccion: Literal["siguiente", "anterior"] = "siguiente") -> str:
    r = _call("/page", {"delta": 1 if direccion == "siguiente" else -1})
    return f"Página {r['page']} de {r['pages']}."


@server.tool(description="Vuelve la E-Ink a la pantalla principal (hora, tiempo, calendario).")
def volver_a_pantalla_principal_eink() -> str:
    _call("/home", {})
    return "La E-Ink vuelve a la pantalla principal."


@server.tool(description="Estado de la pantalla E-Ink: si está conectada y qué vista muestra.")
def estado_eink() -> str:
    return json.dumps(_call("/status"), ensure_ascii=False)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    sys.exit(main())
