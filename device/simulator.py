"""ESP32 simulado: habla el mismo protocolo que el firmware, sin hardware.

Se usa como "puerto serie" falso dentro de USBDisplayDevice:

    sim = SimulatedESP32(save_dir="out/sim")
    dev = USBDisplayDevice(transport=sim)

Sirve para los tests y para probar el lado del PC antes de tener la pantalla.
"""

from __future__ import annotations

import struct
import threading
import time
from pathlib import Path

from display.bitmap import BITMAP_SIZE, HEIGHT, WIDTH, bitmap_to_image

from . import protocol as p

BOOT_NOISE = b"ets Jun  8 2016 00:22:57\r\nrst:0x1 (POWERON_RESET),boot:0x13\r\n"


class SimulatedESP32:
    def __init__(
        self,
        *,
        save_dir: str | Path | None = None,
        buttons: bool = True,
        partial: bool = True,
        refresh_delay: float = 0.0,
        boot_noise: bool = True,
    ) -> None:
        self.save_dir = Path(save_dir) if save_dir else None
        self.caps = (p.CAP_BUTTONS if buttons else 0) | (p.CAP_PARTIAL if partial else 0)
        self.refresh_delay = refresh_delay
        self._parser = p.FrameParser()
        self._out = bytearray()
        self._cv = threading.Condition()
        self._seq = 0
        self._closed = False

        self.pages: list[tuple[int, int, int, bytes]] = []  # (número, total, flags, bitmap)
        self.clears = 0
        self.corrupt_next_rx = 0  # simula N tramas recibidas con CRC erróneo

        if boot_noise:
            self._out += BOOT_NOISE
        self._send(p.MsgType.HELLO, self._hello())

    # --- "puerto serie" -----------------------------------------------------
    @property
    def in_waiting(self) -> int:
        with self._cv:
            return len(self._out)

    def read(self, size: int = 1) -> bytes:
        with self._cv:
            if not self._out and not self._closed:
                self._cv.wait(0.05)
            data = bytes(self._out[:size])
            del self._out[:size]
            return data

    def write(self, data: bytes) -> int:
        for frame in self._parser.feed(data):
            self._handle(frame)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    # --- acciones de prueba -------------------------------------------------
    def press(self, button: p.Button) -> None:
        self._send(p.MsgType.BUTTON, bytes([button]))

    @property
    def last_bitmap(self) -> bytes | None:
        return self.pages[-1][3] if self.pages else None

    # --- internos -----------------------------------------------------------
    def _hello(self) -> bytes:
        return p.Hello(p.VERSION, WIDTH, HEIGHT, self.caps).pack()

    def _send(self, mtype: int, payload: bytes) -> None:
        frame = p.encode(p.Frame(mtype, self._seq, payload))
        self._seq = (self._seq + 1) & 0xFF
        with self._cv:
            self._out += frame
            self._cv.notify_all()

    def _ack(self, seq: int, status: p.Status) -> None:
        self._send(p.MsgType.ACK, bytes([seq, status]))

    def _handle(self, f: p.Frame) -> None:
        if self.corrupt_next_rx:
            self.corrupt_next_rx -= 1
            self._ack(f.seq, p.Status.BAD_CRC)
            return
        if f.type == p.MsgType.PING:
            self._send(p.MsgType.HELLO, self._hello())
        elif f.type == p.MsgType.PAGE:
            if len(f.payload) != 5 + BITMAP_SIZE:
                self._ack(f.seq, p.Status.BAD_LENGTH)
                return
            number, total, flags = struct.unpack_from("<HHB", f.payload)
            bitmap = f.payload[5:]
            if self.refresh_delay:
                time.sleep(self.refresh_delay)
            self.pages.append((number, total, flags, bitmap))
            if self.save_dir:
                self.save_dir.mkdir(parents=True, exist_ok=True)
                bitmap_to_image(bitmap).save(self.save_dir / f"pantalla_{len(self.pages):03d}.png")
            self._ack(f.seq, p.Status.OK)
        elif f.type == p.MsgType.CLEAR:
            self.clears += 1
            self._ack(f.seq, p.Status.OK)
        else:
            self._ack(f.seq, p.Status.UNKNOWN_TYPE)
