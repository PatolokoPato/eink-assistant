"""API HTTP local para que otros programas (el servidor MCP de Claude Desktop)
manden contenido a la E-Ink a través de la app, que es quien tiene el puerto COM.

Solo escucha en 127.0.0.1. Cada petición debe llevar la cabecera
`X-EInk-Client`: una página web no puede añadirla sin una petición previa
OPTIONS (CORS) que aquí no se responde, así que una web abierta en el
navegador no puede escribir en la pantalla.

    POST /show  {"text": "...", "question": "..."}  -> {"pages": 2}
    POST /page  {"delta": 1}                         -> {"page": 2, "pages": 3}
    POST /home  {}                                   -> {}
    GET  /status                                     -> {"connected": true, ...}
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
CLIENT_HEADER = "X-EInk-Client"
MAX_BODY = 200_000  # bytes: de sobra para un texto de varias páginas


def api_port() -> int:
    return int(os.environ.get("EINK_API_PORT") or DEFAULT_PORT)


@dataclass
class Handlers:
    """Qué hacer con cada petición. Se llaman desde el hilo del servidor HTTP."""
    show: Callable[[str, str], int]          # (texto, pregunta) -> páginas
    page: Callable[[int], tuple[int, int]]   # delta -> (página actual, total)
    home: Callable[[], None]
    status: Callable[[], dict[str, Any]]


class _Handler(BaseHTTPRequestHandler):
    server_version = "EInkAssistant"
    handlers: Handlers  # se asigna en LocalApi

    def log_message(self, fmt: str, *args: Any) -> None:  # al log, no a stderr
        log.debug("API %s - " + fmt, self.client_address[0], *args)

    def _reply(self, code: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self) -> bool:
        if not self.headers.get(CLIENT_HEADER) or self.headers.get("Origin"):
            self._reply(403, {"error": "petición no permitida"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed():
            return
        if self.path == "/status":
            self._reply(200, self.handlers.status())
        else:
            self._reply(404, {"error": "no existe"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._allowed():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._reply(413, {"error": "texto demasiado largo"})
            return
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._reply(400, {"error": "JSON no válido"})
            return
        try:
            if self.path == "/show":
                text = str(data.get("text") or "").strip()
                if not text:
                    self._reply(400, {"error": "falta 'text'"})
                    return
                self._reply(200, {"pages": self.handlers.show(text, str(data.get("question") or ""))})
            elif self.path == "/page":
                page, total = self.handlers.page(int(data.get("delta") or 1))
                self._reply(200, {"page": page, "pages": total})
            elif self.path == "/home":
                self.handlers.home()
                self._reply(200, {})
            else:
                self._reply(404, {"error": "no existe"})
        except Exception as e:  # noqa: BLE001
            log.exception("Error en la API local")
            self._reply(500, {"error": str(e)})


class LocalApi:
    def __init__(self, handlers: Handlers, port: int | None = None) -> None:
        handler = type("Handler", (_Handler,), {"handlers": handlers})
        self.server = ThreadingHTTPServer((HOST, api_port() if port is None else port), handler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, name="eink-api", daemon=True)

    def start(self) -> None:
        self._thread.start()
        log.info("API local en http://%s:%d", HOST, self.port)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
