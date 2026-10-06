"""Vistas disponibles: cada una sabe generar su imagen 400x300 en el momento.

Para añadir una pantalla nueva basta con añadir un View a VIEWS.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable

from PIL import Image

from display.calendar import render_month
from tools.make_test_image import make_test_image
from tools.show_home import build_home

from .assistant import ASSISTANT


@dataclass(frozen=True)
class View:
    id: str
    name: str
    description: str
    build: Callable[[], Image.Image]
    # False = su contenido no cambia con el tiempo: la actualización automática
    # no la redibuja (evita parpadeos inútiles).
    auto_refresh: bool = True


def _calendar() -> Image.Image:
    today = dt.date.today()
    return render_month(today.year, today.month, today)


VIEWS: list[View] = [
    View("home", "Pantalla principal", "Hora, tiempo, estado del PC y calendario", build_home),
    View("assistant", "Asistente", "Respuestas del chatbot. Pregunta desde «Abrir asistente…»",
         lambda: ASSISTANT.build(), auto_refresh=False),
    View("calendar", "Calendario", "El mes actual a pantalla completa", _calendar),
    View("test", "Imagen de prueba", "Patrón para comprobar orientación y nitidez", make_test_image,
         auto_refresh=False),
]


def get_view(view_id: str) -> View:
    for v in VIEWS:
        if v.id == view_id:
            return v
    return VIEWS[0]


# Las que se recorren con los atajos ← →. La imagen de prueba se queda fuera.
CYCLE = [v.id for v in VIEWS if v.id != "test"]


def cycle_view(view_id: str, delta: int) -> str:
    """La vista siguiente (delta=1) o anterior (-1) a `view_id`, dando la vuelta."""
    i = CYCLE.index(view_id) if view_id in CYCLE else -1 if delta > 0 else 0
    return CYCLE[(i + delta) % len(CYCLE)]
