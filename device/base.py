"""Interfaz común para cualquier pantalla, sea por USB o (en el futuro) Wi-Fi.

El resto de la aplicación solo usa esta clase:

    with USBDisplayDevice() as display:
        display.on_button(lambda b: ...)
        display.send_page(page)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from display.page import Page


class ButtonEvent(Enum):
    NEXT = "next"
    PREVIOUS = "previous"
    SELECT = "select"


@dataclass(frozen=True)
class DeviceInfo:
    width: int
    height: int
    protocol_version: int
    has_buttons: bool
    has_partial_refresh: bool
    transport: str  # "usb:COM5", "wifi:192.168.1.40", "simulator"...


class DeviceError(Exception):
    """Fallo de comunicación con la pantalla."""


ButtonHandler = Callable[[ButtonEvent], None]


class DisplayDevice(ABC):
    def __init__(self) -> None:
        self._button_handlers: list[ButtonHandler] = []

    # --- ciclo de vida ------------------------------------------------------
    @abstractmethod
    def connect(self) -> DeviceInfo:
        """Abre la conexión y espera a que el dispositivo se identifique."""

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @property
    @abstractmethod
    def info(self) -> DeviceInfo | None: ...

    # --- contenido ----------------------------------------------------------
    @abstractmethod
    def send_page(self, page: Page) -> None:
        """Envía una página y bloquea hasta que la pantalla la ha mostrado."""

    @abstractmethod
    def clear(self) -> None: ...

    # --- botones ------------------------------------------------------------
    def on_button(self, handler: ButtonHandler) -> None:
        """Registra un callback. Se llama desde un hilo de fondo: no bloquearlo."""
        self._button_handlers.append(handler)

    def _emit_button(self, event: ButtonEvent) -> None:
        for handler in list(self._button_handlers):
            handler(event)

    # --- context manager ----------------------------------------------------
    def __enter__(self) -> "DisplayDevice":
        if not self.is_connected:
            self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
