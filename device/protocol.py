"""Protocolo binario PC <-> ESP32. Espejo de firmware/esp32_eink/protocol.h.

Trama (little-endian):

    A5 5A | TYPE (u8) | SEQ (u8) | LEN (u16) | PAYLOAD[LEN] | CRC16 (u16)

CRC-16/CCITT-FALSE sobre TYPE..PAYLOAD. Ver docs/protocolo.md.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

SYNC = b"\xA5\x5A"
VERSION = 1
HEADER_SIZE = 6
CRC_SIZE = 2
MAX_PAYLOAD = 16384  # holgura sobre los 15005 bytes de una PAGE


class MsgType(IntEnum):
    # PC -> ESP32
    PING = 0x01
    PAGE = 0x10
    CLEAR = 0x11
    # ESP32 -> PC
    HELLO = 0x80
    ACK = 0x81
    BUTTON = 0x90
    LOG = 0x9F


class Status(IntEnum):
    OK = 0
    BAD_CRC = 1
    BAD_LENGTH = 2
    UNKNOWN_TYPE = 3
    TOO_LONG = 4
    DISPLAY_BUSY = 5  # BUSY no se liberó: pantalla ausente o colgada


class Button(IntEnum):
    NEXT = 1
    PREVIOUS = 2
    SELECT = 3


PAGE_FLAG_PARTIAL = 0x01
CAP_BUTTONS = 0x01
CAP_PARTIAL = 0x02


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


# Tabla para que calcular el CRC de 15 KB no cueste nada en Python.
def _make_table() -> list[int]:
    table = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        table.append(c)
    return table


_CRC_TABLE = _make_table()


def crc16_fast(data: bytes, crc: int = 0xFFFF) -> int:
    table = _CRC_TABLE
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ table[(crc >> 8) ^ b]
    return crc


@dataclass(frozen=True)
class Frame:
    type: int
    seq: int
    payload: bytes = b""


def encode(frame: Frame) -> bytes:
    if len(frame.payload) > MAX_PAYLOAD:
        raise ValueError(f"payload demasiado grande ({len(frame.payload)} > {MAX_PAYLOAD})")
    body = struct.pack("<BBH", frame.type, frame.seq & 0xFF, len(frame.payload)) + frame.payload
    return SYNC + body + struct.pack("<H", crc16_fast(body))


class FrameParser:
    """Reconstruye tramas a partir de trozos arbitrarios de bytes.

    Un serial.read() puede devolver media trama, dos tramas o basura (p. ej. los
    mensajes de arranque del bootloader). Se descarta todo lo que no forme una
    trama válida y, ante un CRC erróneo, se resincroniza en el siguiente A5 5A.
    """

    def __init__(self, max_payload: int = MAX_PAYLOAD) -> None:
        self._buf = bytearray()
        self.max_payload = max_payload
        self.discarded = 0   # bytes descartados (diagnóstico)
        self.crc_errors = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        frames: list[Frame] = []
        buf = self._buf
        while True:
            start = buf.find(SYNC)
            if start < 0:
                # Conservar un posible A5 final que sea la mitad de un SYNC.
                keep = 1 if buf.endswith(SYNC[:1]) else 0
                self.discarded += len(buf) - keep
                del buf[: len(buf) - keep]
                break
            if start:
                self.discarded += start
                del buf[:start]
            if len(buf) < HEADER_SIZE:
                break
            mtype, seq, length = struct.unpack_from("<BBH", buf, 2)
            if length > self.max_payload:
                self.discarded += 1
                del buf[:1]
                continue
            total = HEADER_SIZE + length + CRC_SIZE
            if len(buf) < total:
                break
            (rx_crc,) = struct.unpack_from("<H", buf, HEADER_SIZE + length)
            if crc16_fast(bytes(buf[2 : HEADER_SIZE + length])) != rx_crc:
                self.crc_errors += 1
                self.discarded += 1
                del buf[:1]
                continue
            frames.append(Frame(mtype, seq, bytes(buf[HEADER_SIZE : HEADER_SIZE + length])))
            del buf[:total]
        return frames


# --- Payloads concretos -----------------------------------------------------

def page_payload(number: int, total: int, bitmap: bytes, *, partial: bool = False) -> bytes:
    flags = PAGE_FLAG_PARTIAL if partial else 0
    return struct.pack("<HHB", number, total, flags) + bitmap


@dataclass(frozen=True)
class Hello:
    version: int
    width: int
    height: int
    caps: int

    @property
    def has_buttons(self) -> bool:
        return bool(self.caps & CAP_BUTTONS)

    @property
    def has_partial(self) -> bool:
        return bool(self.caps & CAP_PARTIAL)

    @classmethod
    def parse(cls, payload: bytes) -> "Hello":
        return cls(*struct.unpack("<BHHB", payload[:6]))

    def pack(self) -> bytes:
        return struct.pack("<BHHB", self.version, self.width, self.height, self.caps)
