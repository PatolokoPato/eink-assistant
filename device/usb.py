"""DisplayDevice sobre USB/Serial (ESP32 con conversor CP210x/CH340 o USB nativo)."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Protocol

from display.page import Page

from . import protocol as p
from .base import ButtonEvent, DeviceError, DeviceInfo, DisplayDevice

log = logging.getLogger(__name__)

# Al autodetectar, cuánto se espera el HELLO en cada puerto. El firmware lo
# manda al arrancar o en cuanto recibe un PING, así que basta con poco.
PROBE_TIMEOUT = 3.0

# VID USB habituales en placas ESP32.
KNOWN_USB_VIDS = {
    0x10C4: "Silicon Labs CP210x",
    0x1A86: "WCH CH340/CH9102",
    0x303A: "Espressif USB nativo",
    0x0403: "FTDI",
}

_BUTTON_MAP = {
    p.Button.NEXT: ButtonEvent.NEXT,
    p.Button.PREVIOUS: ButtonEvent.PREVIOUS,
    p.Button.SELECT: ButtonEvent.SELECT,
}


class SerialLike(Protocol):
    """Lo mínimo que se usa de serial.Serial (permite inyectar un simulador)."""

    @property
    def in_waiting(self) -> int: ...
    def read(self, size: int = 1) -> bytes: ...
    def write(self, data: bytes) -> int | None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...


def list_serial_ports() -> list[tuple[str, str]]:
    """[(puerto, descripción)] de todos los puertos serie del sistema."""
    from serial.tools import list_ports

    return [(pi.device, f"{pi.description} [{pi.hwid}]") for pi in list_ports.comports()]


def candidate_ports() -> list[str]:
    """Todos los puertos serie, primero los de chips USB típicos del ESP32.

    Se prueban todos (no solo los de VID conocido) porque algunos cables,
    hubs o drivers no informan del VID."""
    from serial.tools import list_ports

    ports = list(list_ports.comports())
    ports.sort(key=lambda pi: pi.vid not in KNOWN_USB_VIDS)  # estable: conocidos delante
    return [pi.device for pi in ports]


class USBDisplayDevice(DisplayDevice):
    def __init__(
        self,
        port: str | None = None,
        baudrate: int = 921600,
        *,
        connect_timeout: float = 6.0,
        ack_timeout: float = 40.0,
        retries: int = 2,
        transport: SerialLike | None = None,
    ) -> None:
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.connect_timeout = connect_timeout
        self.ack_timeout = ack_timeout
        self.retries = retries
        # El USB nativo del ESP32-C3 pierde bytes si recibe los 15 KB de una
        # PAGE de golpe (se desborda su buffer de recepción y la trama queda
        # incompleta, sin ACK). Se envía en trozos con una pausa entre ellos.
        self.write_chunk = 256
        self.write_pause = 0.0 if transport is not None else 0.005

        self._ser: SerialLike | None = transport
        self._injected = transport is not None
        self._parser = p.FrameParser()
        self._info: DeviceInfo | None = None
        self._connected = False

        self._tx_lock = threading.Lock()       # una petición pendiente cada vez
        self._seq = 0
        self._acks: "queue.Queue[p.Frame]" = queue.Queue()
        self._hello = threading.Event()
        self._hello_payload: p.Hello | None = None

        self._running = False
        self._reader: threading.Thread | None = None
        self._dispatcher: threading.Thread | None = None
        self._events: "queue.Queue[ButtonEvent | None]" = queue.Queue()
        self._read_error: Exception | None = None

    # ------------------------------------------------------------------ vida
    def connect(self) -> DeviceInfo:
        if self._connected:
            assert self._info
            return self._info

        if self._injected or self.port:
            return self._connect_port(self.connect_timeout)

        # Autodetección: se prueba cada COM con PING hasta que uno responda HELLO.
        ports = candidate_ports()
        if not ports:
            raise DeviceError("No hay ningún puerto COM. ¿Está enchufado el ESP32 con un cable de datos?")
        errors = []
        for port in ports:
            self.port = port
            try:
                return self._connect_port(min(self.connect_timeout, PROBE_TIMEOUT))
            except DeviceError as e:
                log.info("Autodetección: %s no vale (%s)", port, e)
                errors.append(f"  {port}: {e}")
        self.port = None
        raise DeviceError("Ningún puerto COM responde como la E-Ink:\n" + "\n".join(errors))

    def _open_transport(self) -> SerialLike:
        """Abre el canal de bytes. WiFiDisplayDevice lo sustituye por un socket."""
        import serial  # import tardío: los tests con simulador no lo necesitan

        ser = serial.Serial(baudrate=self.baudrate, timeout=0.05, write_timeout=5)
        ser.port = self.port
        # DTR/RTS a False ANTES de abrir: en el USB nativo de ESP32-C3/S3 y en
        # placas con auto-reset estas líneas controlan EN y el pin de arranque.
        # Así abrir el puerto no deja el chip reiniciado ni en modo descarga.
        ser.dtr = False
        ser.rts = False
        try:
            ser.open()
        except serial.SerialException as e:
            raise DeviceError(f"No se pudo abrir {self.port}: {e}") from e
        return ser

    def _no_reply_message(self) -> str:
        return ("El ESP32 no responde. Comprueba el puerto, que el firmware esté "
                f"cargado y que la velocidad coincida ({self.baudrate} baudios).")

    def _transport_label(self) -> str:
        return f"usb:{self.port}" if not self._injected else "usb:injected"

    def _connect_port(self, timeout: float) -> DeviceInfo:
        if not self._injected:
            self._ser = self._open_transport()

        self._running = True
        self._read_error = None
        self._hello.clear()
        self._parser = p.FrameParser()
        self._events = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, name="eink-usb-rx", daemon=True)
        self._dispatcher = threading.Thread(target=self._dispatch_loop, name="eink-usb-events", daemon=True)
        self._reader.start()
        self._dispatcher.start()

        # Al abrir el puerto muchas placas ESP32 se reinician. El firmware manda
        # HELLO al arrancar; si ya estaba arrancado, responde HELLO a un PING.
        deadline = time.monotonic() + timeout
        while not self._hello.is_set() and time.monotonic() < deadline:
            self._write(p.Frame(p.MsgType.PING, self._next_seq()))
            self._hello.wait(0.5)

        if not self._hello.is_set():
            self.close()
            raise DeviceError(self._no_reply_message())

        h = self._hello_payload
        assert h is not None
        if h.version != p.VERSION:
            self.close()
            raise DeviceError(f"Versión de protocolo distinta: firmware {h.version}, PC {p.VERSION}")
        self._info = DeviceInfo(
            width=h.width,
            height=h.height,
            protocol_version=h.version,
            has_buttons=h.has_buttons,
            has_partial_refresh=h.has_partial,
            transport=self._transport_label(),
        )
        self._connected = True
        log.info("Conectado: %s", self._info)
        return self._info

    def close(self) -> None:
        self._running = False
        self._connected = False
        self._events.put(None)
        for t in (self._reader, self._dispatcher):
            if t and t.is_alive() and t is not threading.current_thread():
                t.join(timeout=1)
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001 - cerrar nunca debe lanzar
                pass
            if not self._injected:
                self._ser = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._read_error is None

    @property
    def info(self) -> DeviceInfo | None:
        return self._info

    # ------------------------------------------------------------- contenido
    def send_page(self, page: Page) -> None:
        payload = p.page_payload(page.number, page.total, page.bitmap, partial=page.partial)
        self._request(p.MsgType.PAGE, payload)

    def clear(self) -> None:
        self._request(p.MsgType.CLEAR, b"")

    # -------------------------------------------------------------- internos
    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def _write(self, frame: p.Frame) -> None:
        if self._ser is None:
            raise DeviceError("Dispositivo no conectado")
        data = p.encode(frame)
        try:
            for i in range(0, len(data), self.write_chunk):
                if i and self.write_pause:
                    time.sleep(self.write_pause)
                self._ser.write(data[i : i + self.write_chunk])
                self._ser.flush()
        except Exception as e:  # noqa: BLE001
            raise DeviceError(f"Error escribiendo en el puerto: {e}") from e

    def _request(self, mtype: int, payload: bytes) -> None:
        if not self._connected:
            raise DeviceError("Dispositivo no conectado")
        with self._tx_lock:
            for attempt in range(self.retries + 1):
                seq = self._next_seq()
                while not self._acks.empty():  # ACKs antiguos/duplicados
                    self._acks.get_nowait()
                self._write(p.Frame(mtype, seq, payload))
                ack = self._wait_ack(seq)
                if ack is None:
                    if self._read_error:
                        raise DeviceError(f"Conexión perdida: {self._read_error}")
                    log.warning("Sin ACK para seq=%d (intento %d)", seq, attempt + 1)
                    continue
                status = ack.payload[1]
                if status == p.Status.OK:
                    return
                if status == p.Status.BAD_CRC:
                    log.warning("CRC erróneo en el ESP32, reintentando (intento %d)", attempt + 1)
                    continue
                if status == p.Status.DISPLAY_BUSY:
                    raise DeviceError("La pantalla no responde (BUSY ocupado): ¿está conectada y cableada?")
                raise DeviceError(f"El ESP32 rechazó la trama: {p.Status(status).name}")
            raise DeviceError(f"Sin respuesta válida tras {self.retries + 1} intentos")

    def _wait_ack(self, seq: int) -> p.Frame | None:
        deadline = time.monotonic() + self.ack_timeout
        while (remaining := deadline - time.monotonic()) > 0:
            if self._read_error:
                return None
            try:
                ack = self._acks.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            if len(ack.payload) >= 2 and ack.payload[0] == seq:
                return ack
        return None

    def _read_loop(self) -> None:
        ser = self._ser
        assert ser is not None
        while self._running:
            try:
                data = ser.read(ser.in_waiting or 1)
            except Exception as e:  # noqa: BLE001 - cable desconectado, etc.
                if self._running:
                    self._read_error = e
                    log.error("Lectura serie falló: %s", e)
                break
            if not data:
                continue
            for frame in self._parser.feed(data):
                self._handle(frame)

    def _handle(self, frame: p.Frame) -> None:
        t = frame.type
        if t == p.MsgType.HELLO:
            self._hello_payload = p.Hello.parse(frame.payload)
            self._hello.set()
        elif t == p.MsgType.ACK:
            self._acks.put(frame)
        elif t == p.MsgType.BUTTON and frame.payload:
            event = _BUTTON_MAP.get(frame.payload[0])
            if event:
                self._events.put(event)
        elif t == p.MsgType.LOG:
            log.info("[esp32] %s", frame.payload.decode("utf-8", "replace"))
        else:
            log.debug("Trama ignorada: %r", frame)

    def _dispatch_loop(self) -> None:
        # Hilo propio para los callbacks: así un handler puede llamar a
        # send_page() sin bloquear la lectura del puerto (que traería el ACK).
        while True:
            event = self._events.get()
            if event is None or not self._running:
                break
            try:
                self._emit_button(event)
            except Exception:  # noqa: BLE001
                log.exception("Error en un manejador de botón")
