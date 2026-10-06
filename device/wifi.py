"""DisplayDevice por Wi-Fi: las mismas tramas que por USB, sobre TCP.

El ESP32 escucha en el puerto WIFI_TCP_PORT de firmware/esp32_eink/config.h y
se anuncia por mDNS como eink.local. Todo lo demás (PING/HELLO, ACK,
reintentos, botones) es idéntico al USB y se hereda de USBDisplayDevice.
"""

from __future__ import annotations

import socket
import struct

from .base import DeviceError
from .usb import SerialLike, USBDisplayDevice

DEFAULT_HOST = "eink.local"
DEFAULT_TCP_PORT = 3333  # WIFI_TCP_PORT en config.h


class SocketSerial:
    """Adapta un socket TCP a la interfaz mínima de serial.Serial (SerialLike)."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._sock.settimeout(0.05)  # como el timeout de lectura del puerto serie

    @property
    def in_waiting(self) -> int:
        return 0  # read() ya devuelve lo que haya disponible

    def read(self, size: int = 1) -> bytes:
        try:
            data = self._sock.recv(max(size, 4096))
        except TimeoutError:
            return b""
        if not data:
            raise ConnectionError("el ESP32 cerró la conexión")
        return data

    def write(self, data: bytes) -> int:
        self._sock.sendall(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()


def _skip_name(data: bytes, i: int) -> int:
    while data[i]:
        if data[i] & 0xC0 == 0xC0:  # puntero de compresión: fin del nombre
            return i + 2
        i += data[i] + 1
    return i + 1


def mdns_resolve(name: str, timeout: float = 2.0) -> str | None:
    """Pregunta por mDNS la IPv4 de `name` (p. ej. eink.local).

    Windows no siempre resuelve los nombres .local por su cuenta (depende del
    perfil de red y de la versión), aunque el ESP32 responda bien."""
    q = struct.pack(">6H", 0, 0, 1, 0, 0, 0)
    for label in name.rstrip(".").split("."):
        q += bytes([len(label)]) + label.encode()
    q += b"\0" + struct.pack(">HH", 1, 0x8001)  # tipo A, clase IN + respuesta unicast
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        try:
            s.sendto(q, ("224.0.0.251", 5353))
            while True:
                data, _ = s.recvfrom(2048)
                ip = _parse_a_record(data)
                if ip:
                    return ip
        except (TimeoutError, OSError, IndexError, struct.error):
            return None


def _parse_a_record(data: bytes) -> str | None:
    _, flags, qd, an = struct.unpack(">4H", data[:8])
    if not flags & 0x8000:
        return None  # es una pregunta, no una respuesta
    i = 12
    for _ in range(qd):
        i = _skip_name(data, i) + 4
    for _ in range(an):
        i = _skip_name(data, i)
        rtype, _, _, rdlen = struct.unpack(">HHIH", data[i:i + 10])
        i += 10
        if rtype == 1 and rdlen == 4:
            return socket.inet_ntoa(data[i:i + 4])
        i += rdlen
    return None


def parse_wifi_target(target: str) -> tuple[str, int]:
    """'wifi:host[:puerto]' (o sin el prefijo) -> (host, puerto)."""
    rest = target.removeprefix("wifi:").strip() or DEFAULT_HOST
    host, sep, port = rest.rpartition(":")
    if sep and port.isdigit():
        return host, int(port)
    return rest, DEFAULT_TCP_PORT


class WiFiDisplayDevice(USBDisplayDevice):
    def __init__(self, host: str = DEFAULT_HOST, tcp_port: int = DEFAULT_TCP_PORT, *,
                 connect_timeout: float = 6.0, ack_timeout: float = 40.0, retries: int = 2) -> None:
        super().__init__(f"{host}:{tcp_port}", connect_timeout=connect_timeout,
                         ack_timeout=ack_timeout, retries=retries)
        self.host = host
        self.tcp_port = tcp_port
        # TCP ya controla el flujo: no hacen falta los trozos con pausa del USB.
        self.write_chunk = 1 << 16
        self.write_pause = 0.0

    def connect(self):
        if self._connected:
            return super().connect()
        return self._connect_port(self.connect_timeout)

    def _resolve(self) -> str:
        if not self.host.endswith(".local"):
            return self.host
        try:
            socket.getaddrinfo(self.host, self.tcp_port)
            return self.host  # Windows ya lo resuelve
        except OSError:
            ip = mdns_resolve(self.host)
            if ip is None:
                raise DeviceError(f"No se encuentra {self.host} en la red: ¿está encendida y con Wi-Fi?")
            return ip

    def _open_transport(self) -> SerialLike:
        addr = self._resolve()
        try:
            sock = socket.create_connection((addr, self.tcp_port), timeout=self.connect_timeout)
        except OSError as e:
            raise DeviceError(f"No se pudo conectar por Wi-Fi a {self.host}:{self.tcp_port}: {e}") from e
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        return SocketSerial(sock)

    def _no_reply_message(self) -> str:
        return f"{self.host} acepta la conexión pero no responde como la E-Ink."

    def _transport_label(self) -> str:
        return f"wifi:{self.host}"
