"""Fase 1: envía una imagen 400x300 al ESP32 por USB y la muestra en la E-Ink.

Ejemplos (Windows, desde la carpeta del proyecto):
    python -m tools.send_test_image --list-ports
    python -m tools.send_test_image --port COM5
    python -m tools.send_test_image --port COM5 --image foto.jpg
    python -m tools.send_test_image --port COM5 --clear
    python -m tools.send_test_image --simulate          # sin hardware: guarda PNG en out/sim
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from PIL import Image

from config.settings import load_settings
from device import DeviceError, USBDisplayDevice, list_serial_ports
from display.page import Page
from tools.make_test_image import make_test_image


def main(argv: list[str] | None = None) -> int:
    cfg = load_settings().serial
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=cfg.port, help="p. ej. COM5 (por defecto: autodetectar)")
    ap.add_argument("--baud", type=int, default=cfg.baudrate)
    ap.add_argument("--image", help="imagen a enviar (se escala a 400x300); por defecto, el patrón de prueba")
    ap.add_argument("--no-dither", action="store_true", help="umbral simple en lugar de tramado")
    ap.add_argument("--partial", action="store_true", help="pedir refresco parcial")
    ap.add_argument("--clear", action="store_true", help="solo borrar la pantalla")
    ap.add_argument("--list-ports", action="store_true", help="listar puertos serie y salir")
    ap.add_argument("--simulate", action="store_true", help="usar un ESP32 simulado (guarda en out/sim)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    if args.list_ports:
        ports = list_serial_ports()
        for dev, desc in ports:
            print(f"{dev:10} {desc}")
        if not ports:
            print("No hay puertos serie. ¿Está el ESP32 conectado y el driver CP210x/CH340 instalado?")
        return 0

    transport = None
    if args.simulate:
        from device.simulator import SimulatedESP32

        transport = SimulatedESP32(save_dir="out/sim")

    device = USBDisplayDevice(args.port, args.baud, connect_timeout=cfg.connect_timeout,
                              ack_timeout=cfg.ack_timeout, transport=transport)
    try:
        info = device.connect()
        print(f"Conectado a {info.transport}: {info.width}x{info.height}, protocolo v{info.protocol_version}, "
              f"botones={'sí' if info.has_buttons else 'no'}, parcial={'sí' if info.has_partial_refresh else 'no'}")

        t0 = time.monotonic()
        if args.clear:
            device.clear()
            print(f"Pantalla borrada en {time.monotonic() - t0:.1f} s")
            return 0

        img = Image.open(args.image) if args.image else make_test_image()
        page = Page.from_image(img, partial=args.partial, dither=not args.no_dither)
        device.send_page(page)
        print(f"Página enviada y mostrada en {time.monotonic() - t0:.1f} s")
        if args.simulate:
            print("Simulación: resultado en out/sim/")
        return 0
    except DeviceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        device.close()


if __name__ == "__main__":
    sys.exit(main())
