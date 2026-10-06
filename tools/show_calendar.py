"""Muestra el calendario del mes en la E-Ink.

Ejemplos (Windows, desde la carpeta del proyecto):
    python -m tools.show_calendar --port COM3
    python -m tools.show_calendar --port COM3 --month 2026-12
    python -m tools.show_calendar --port COM3 --watch     # redibuja cada medianoche
    python -m tools.show_calendar --simulate             # sin hardware: guarda PNG en out/sim
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time

from config.settings import load_settings
from device import DeviceError, USBDisplayDevice
from display.calendar import render_month
from display.page import Page


def _parse_month(text: str) -> tuple[int, int]:
    try:
        d = dt.datetime.strptime(text, "%Y-%m")
    except ValueError:
        raise argparse.ArgumentTypeError("formato AAAA-MM, p. ej. 2026-10") from None
    return d.year, d.month


def _seconds_to_midnight() -> float:
    now = dt.datetime.now()
    tomorrow = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time())
    return (tomorrow - now).total_seconds() + 5  # margen para no caer en el día anterior


def main(argv: list[str] | None = None) -> int:
    cfg = load_settings().serial
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=cfg.port, help="p. ej. COM3 (por defecto: autodetectar)")
    ap.add_argument("--baud", type=int, default=cfg.baudrate)
    ap.add_argument("--month", type=_parse_month, help="mes a mostrar, AAAA-MM (por defecto: el actual)")
    ap.add_argument("--watch", action="store_true", help="seguir en marcha y redibujar cada medianoche")
    ap.add_argument("--simulate", action="store_true", help="usar un ESP32 simulado (guarda en out/sim)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.watch and args.month:
        ap.error("--watch muestra siempre el mes actual; no se combina con --month")

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    transport = None
    if args.simulate:
        from device.simulator import SimulatedESP32

        transport = SimulatedESP32(save_dir="out/sim")

    device = USBDisplayDevice(args.port, args.baud, connect_timeout=cfg.connect_timeout,
                              ack_timeout=cfg.ack_timeout, transport=transport)
    try:
        device.connect()
        while True:
            today = dt.date.today()
            year, month = args.month or (today.year, today.month)
            t0 = time.monotonic()
            device.send_page(Page.from_image(render_month(year, month, today), dither=False))
            print(f"Calendario {month:02d}/{year} mostrado en {time.monotonic() - t0:.1f} s")
            if not args.watch:
                return 0
            time.sleep(_seconds_to_midnight())
    except DeviceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        device.close()


if __name__ == "__main__":
    sys.exit(main())
