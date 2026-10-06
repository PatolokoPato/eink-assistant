"""Pantalla principal: hora, fecha, tiempo, estado del PC y calendario.

Ejemplos (Windows, desde la carpeta del proyecto):
    $env:EINK_CITY = "Valencia"
    python -m tools.show_home --port COM3
    python -m tools.show_home --port COM3 --watch              # actualiza cada 5 min
    python -m tools.show_home --port COM3 --watch --interval 10
    python -m tools.show_home --preview out/home.png           # solo genera la imagen

Con --watch, la primera imagen usa el refresco completo (~10 s, parpadea) y las
siguientes el parcial blanco/negro (~1,5 s, casi sin parpadeo).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from config.settings import load_settings
from device import DeviceError, USBDisplayDevice
from display.home import render_home
from display.page import Page
from sources.system import get_system_status
from sources.weather import get_weather


def build_home():
    w = load_settings().weather
    weather = get_weather(w.city, w.latitude, w.longitude)
    system = get_system_status()
    return render_home(dt.datetime.now(), weather, system)


def _seconds_to_next(interval_min: int) -> float:
    """Hasta el siguiente múltiplo de `interval_min` (14:05, 14:10...), para que la hora cuadre."""
    now = dt.datetime.now()
    minutes = now.hour * 60 + now.minute
    nxt = (minutes // interval_min + 1) * interval_min
    target = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=nxt)
    return (target - now).total_seconds()


def main(argv: list[str] | None = None) -> int:
    cfg = load_settings().serial
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=cfg.port, help="p. ej. COM3 (por defecto: autodetectar)")
    ap.add_argument("--baud", type=int, default=cfg.baudrate)
    ap.add_argument("--watch", action="store_true", help="seguir en marcha y actualizar periódicamente")
    ap.add_argument("--interval", type=int, default=5, help="minutos entre actualizaciones con --watch")
    ap.add_argument("--partial", action="store_true",
                    help="usar refresco parcial también en la primera imagen (sin parpadeo)")
    ap.add_argument("--preview", metavar="PNG", help="guardar la imagen en vez de enviarla")
    ap.add_argument("--simulate", action="store_true", help="usar un ESP32 simulado (guarda en out/sim)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    if not 1 <= args.interval <= 1440:
        ap.error("--interval debe estar entre 1 y 1440 minutos")

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    if args.preview:
        out = Path(args.preview)
        out.parent.mkdir(parents=True, exist_ok=True)
        build_home().save(out)
        print(f"Guardado {out}")
        return 0

    transport = None
    if args.simulate:
        from device.simulator import SimulatedESP32

        transport = SimulatedESP32(save_dir="out/sim")

    device = USBDisplayDevice(args.port, args.baud, connect_timeout=cfg.connect_timeout,
                              ack_timeout=cfg.ack_timeout, transport=transport)
    try:
        info = device.connect()
        # La primera imagen va con refresco completo; las siguientes piden el
        # parcial (casi sin parpadeo). El ESP32 intercala uno completo cada
        # FULL_REFRESH_EVERY para limpiar restos de imágenes anteriores.
        partial = args.partial
        while True:
            t0 = time.monotonic()
            page = Page.from_image(build_home(), partial=partial and info.has_partial_refresh, dither=False)
            device.send_page(page)
            kind = "parcial" if page.partial else "completo"
            print(f"{dt.datetime.now():%H:%M} pantalla principal mostrada en {time.monotonic() - t0:.1f} s ({kind})")
            partial = True
            if not args.watch:
                return 0
            time.sleep(_seconds_to_next(args.interval))
    except DeviceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        device.close()


if __name__ == "__main__":
    sys.exit(main())
