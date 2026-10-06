"""Genera las capturas de las vistas para el README (docs/img/), con datos de ejemplo.

    .venv\\Scripts\\python.exe -m tools.make_docs_images

Se dibujan con el mismo código que va a la pantalla y se escalan ×2 sin
suavizado, para que en GitHub se vean nítidas como en la E-Ink.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PIL import Image

from display.assistant import render_answer_pages
from display.bitmap import bitmap_to_image, image_to_bitmap
from display.calendar import render_month
from display.home import render_home
from sources.system import SystemStatus
from sources.weather import Weather

OUT = Path(__file__).resolve().parent.parent / "docs" / "img"
NOW = dt.datetime(2026, 10, 6, 14, 57)


def _save(img: Image.Image, name: str) -> None:
    # Pasar por el bitmap de 1 bit: exactamente lo que recibe el ESP32.
    shown = bitmap_to_image(image_to_bitmap(img, dither=False)).convert("L")
    shown.resize((shown.width * 2, shown.height * 2), Image.NEAREST).save(OUT / name, optimize=True)
    print("  ", OUT / name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    weather = Weather("Madrid", 21.0, "Parcialmente nuboso", 48, 14.0, 24.0, code=2)
    system = SystemStatus(cpu_percent=23, ram_percent=48, ram_used_gb=7.6, ram_total_gb=16, disk_percent=0,
                          cpu_temp=61, gpu_temp=45)
    _save(render_home(NOW, weather, system), "vista-principal.png")
    answer = ("La E-Ink solo gasta energía al cambiar de imagen, así que puede mostrar la misma "
              "información todo el día sin consumir nada.\n\n"
              "- Se lee bien con luz del sol\n- No emite luz: no cansa la vista\n"
              "- A cambio, cada refresco tarda unos segundos")
    _save(render_answer_pages("¿Por qué usar tinta electrónica?", answer)[0], "vista-asistente.png")
    _save(render_month(NOW.year, NOW.month, NOW.date()), "vista-calendario.png")


if __name__ == "__main__":
    main()
