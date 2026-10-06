"""Hilo que habla con la pantalla. La interfaz solo encola órdenes y lee `status`.

Un único hilo usa el DisplayDevice: así un refresco de ~10 s nunca bloquea la
ventana y dos órdenes no se pisan. Si la conexión se pierde (USB desenchufado),
la siguiente orden vuelve a conectar.
"""

from __future__ import annotations

import datetime as dt
import logging
import queue
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from device import DeviceError, DisplayDevice, USBDisplayDevice, WiFiDisplayDevice
from device.wifi import parse_wifi_target
from display.page import Page

from .views import get_view

log = logging.getLogger(__name__)

DeviceFactory = Callable[[str | None], DisplayDevice]

# El refresco parcial del panel de 3 colores es un B/N diferencial: solo mueve
# los píxeles que cambian y no los limpia del todo, así que un cambio grande
# (p. ej. pasar de la vista principal al asistente) deja la imagen anterior en
# gris debajo de la nueva. Por encima de esta fracción de píxeles cambiados se
# hace refresco completo. Que cambie la hora es ~1,5 %; cambiar de vista, ~17 %.
PARTIAL_MAX_CHANGE = 0.05


def changed_fraction(a: bytes, b: bytes) -> float:
    """Fracción de píxeles distintos entre dos bitmaps del mismo tamaño."""
    diff = int.from_bytes(a, "big") ^ int.from_bytes(b, "big")
    return diff.bit_count() / (len(a) * 8)


def invert_bitmap(bitmap: bytes) -> bytes:
    """Blanco sobre negro: cada píxel al color contrario."""
    return bytes(b ^ 0xFF for b in bitmap)


def usb_factory(port: str | None) -> DisplayDevice:
    """`port`: "COM3" (USB), "wifi:eink.local[:3333]" (Wi-Fi) o None.

    Con None prueba todos los COM y, si ninguno responde, la E-Ink por Wi-Fi."""
    from config.settings import load_settings

    cfg = load_settings().serial
    timeouts = {"connect_timeout": cfg.connect_timeout, "ack_timeout": cfg.ack_timeout}
    if port and port.startswith("wifi:"):
        return WiFiDisplayDevice(*parse_wifi_target(port), **timeouts)
    usb = USBDisplayDevice(port, cfg.baudrate, **timeouts)
    if port:
        return usb
    try:
        usb.connect()
        return usb
    except DeviceError as usb_error:
        wifi = WiFiDisplayDevice(**timeouts)
        try:
            wifi.connect()
        except DeviceError as wifi_error:
            raise DeviceError(f"{usb_error}\nWi-Fi: {wifi_error}") from wifi_error
        return wifi


def seconds_to_next(interval_min: int, now: dt.datetime | None = None) -> float:
    """Hasta el siguiente múltiplo de `interval_min` (14:05, 14:10...), para que la hora cuadre."""
    now = now or dt.datetime.now()
    minutes = now.hour * 60 + now.minute
    nxt = (minutes // interval_min + 1) * interval_min
    target = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=nxt)
    return (target - now).total_seconds()


@dataclass(frozen=True)
class Status:
    connected: bool = False
    port: str | None = None             # el elegido; None = autodetectar
    transport: str | None = None        # el realmente conectado, p. ej. "usb:COM3"
    busy: str | None = None             # qué está haciendo ahora, o None
    view_id: str = "home"
    last_update: dt.datetime | None = None
    last_duration: float | None = None
    last_error: str | None = None
    auto: bool = False
    interval_min: int = 5
    next_auto: dt.datetime | None = None
    invert: bool = False                # blanco sobre negro


class DisplayController:
    def __init__(self, port: str | None, *, view_id: str = "home", auto: bool = False,
                 interval_min: int = 5, invert: bool = False, factory: DeviceFactory = usb_factory) -> None:
        self._factory = factory
        self._device: DisplayDevice | None = None
        self._cmds: "queue.Queue[tuple]" = queue.Queue()
        self._lock = threading.Lock()
        self._status = Status(port=port, view_id=view_id, auto=auto, interval_min=interval_min, invert=invert)
        self._thread = threading.Thread(target=self._run, name="eink-controller", daemon=True)
        # Lo último enviado; None = la siguiente imagen va con refresco completo
        # (primera de cada conexión, o tras borrar).
        self._shown: bytes | None = None
        self._deferred: tuple | None = None  # orden sacada de la cola al juntar "show"
        self.on_change: Callable[[Status], None] | None = None

    # --- API para la interfaz (cualquier hilo) --------------------------------
    @property
    def status(self) -> Status:
        with self._lock:
            return self._status

    def start(self) -> None:
        self._schedule_auto()
        self._thread.start()

    def stop(self) -> None:
        self._cmds.put(("stop",))
        self._thread.join(timeout=60)

    def show(self, view_id: str | None = None, *, full: bool = False) -> None:
        self._cmds.put(("show", view_id, full))

    def clear(self) -> None:
        self._cmds.put(("clear",))

    def set_port(self, port: str | None) -> None:
        self._cmds.put(("port", port))

    def set_auto(self, auto: bool, interval_min: int | None = None) -> None:
        self._update(auto=auto, interval_min=interval_min or self.status.interval_min)
        self._schedule_auto()
        self._cmds.put(("wake",))

    def set_invert(self, invert: bool) -> None:
        """Cambia los colores y redibuja (cambia todo: irá con refresco completo)."""
        self._update(invert=invert)
        self.show()

    # --- interno ----------------------------------------------------------------
    def _update(self, **changes) -> None:
        with self._lock:
            self._status = replace(self._status, **changes)
            st = self._status
        if self.on_change:
            self.on_change(st)

    def _schedule_auto(self) -> None:
        st = self.status
        nxt = (dt.datetime.now() + dt.timedelta(seconds=seconds_to_next(st.interval_min))) if st.auto else None
        self._update(next_auto=nxt)

    def _ensure_device(self) -> DisplayDevice:
        if self._device is not None and self._device.is_connected:
            return self._device
        self._disconnect()
        self._update(busy="Conectando…")
        dev = self._factory(self.status.port)
        info = dev.connect()
        self._device = dev
        self._shown = None
        self._update(connected=True, last_error=None, transport=info.transport)
        return dev

    def _disconnect(self) -> None:
        if self._device is not None:
            self._device.close()
            self._device = None
        self._update(connected=False)

    def _do_show(self, view_id: str | None, full: bool) -> None:
        view = get_view(view_id or self.status.view_id)
        self._update(busy=f"Generando «{view.name}»…", view_id=view.id)
        img = view.build()
        dev = self._ensure_device()
        page = Page.from_image(img, dither=view.id == "test")
        if self.status.invert:
            page = replace(page, bitmap=invert_bitmap(page.bitmap))
        partial = (not full and self._shown is not None
                   and bool(dev.info and dev.info.has_partial_refresh)
                   and changed_fraction(self._shown, page.bitmap) <= PARTIAL_MAX_CHANGE)
        self._update(busy=f"Refrescando la pantalla ({'parcial' if partial else 'completo'})…")
        t0 = time.monotonic()
        self._shown = None  # si el envío falla, no se sabe qué quedó en pantalla
        dev.send_page(replace(page, partial=partial))
        self._shown = page.bitmap
        self._update(last_update=dt.datetime.now(), last_duration=time.monotonic() - t0, last_error=None)

    def _latest_show(self, cmd: tuple) -> tuple:
        """Junta varias "show" seguidas en una: si se pulsa → tres veces durante
        un refresco, se dibuja solo la última vista, no las intermedias."""
        while self._deferred is None:
            try:
                nxt = self._cmds.get_nowait()
            except queue.Empty:
                break
            if nxt[0] != "show":
                self._deferred = nxt  # se atiende justo después, en su orden
                break
            # La vista pedida más reciente gana; show(None) = "la actual", no la cambia.
            cmd = ("show", nxt[1] or cmd[1], cmd[2] or nxt[2])
        return cmd

    def _run(self) -> None:
        while True:
            st = self.status
            timeout = None
            if st.auto and st.next_auto:
                timeout = max(0.0, (st.next_auto - dt.datetime.now()).total_seconds())
            try:
                if self._deferred is not None:
                    cmd, self._deferred = self._deferred, None
                else:
                    cmd = self._cmds.get(timeout=timeout)
            except queue.Empty:
                self._schedule_auto()
                if not get_view(self.status.view_id).auto_refresh:
                    continue  # p. ej. el asistente: su página no cambia con el tiempo
                cmd = ("show", None, False)  # toca la actualización automática

            if cmd[0] == "show":
                cmd = self._latest_show(cmd)
            kind = cmd[0]
            if kind == "stop":
                self._disconnect()
                return
            try:
                if kind == "show":
                    self._do_show(cmd[1], cmd[2])
                elif kind == "clear":
                    self._update(busy="Borrando la pantalla…")
                    self._ensure_device().clear()
                    self._shown = None
                    self._update(last_update=dt.datetime.now(), last_error=None)
                elif kind == "port":
                    self._disconnect()
                    self._update(port=cmd[1])
                    self._ensure_device()
            except DeviceError as e:
                log.warning("Error con la pantalla: %s", e)
                self._disconnect()
                self._update(last_error=str(e))
            except Exception as e:  # noqa: BLE001 — el hilo no debe morir
                log.exception("Error inesperado")
                self._update(last_error=f"{type(e).__name__}: {e}")
            finally:
                self._update(busy=None)
