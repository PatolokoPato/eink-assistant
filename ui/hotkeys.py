"""Atajos de teclado globales (funcionan aunque la ventana no tenga el foco).

Usa RegisterHotKey de Windows: sin dependencias y sin leer el resto de
pulsaciones. Los atajos se registran en un hilo propio con su bucle de
mensajes; las acciones se ejecutan en ese hilo, así que deben limitarse a
encolar trabajo (p. ej. en la cola de la interfaz).

Ojo con Ctrl+Alt: en teclados españoles es lo mismo que AltGr, así que
Ctrl+Alt+número o letra robaría caracteres como | @ #. Por eso los atajos
usan flechas, Re Pág/Av Pág y teclas F, que con AltGr no escriben nada.
"""

from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
VK_PRIOR, VK_NEXT, VK_LEFT, VK_RIGHT, VK_F1 = 0x21, 0x22, 0x25, 0x27, 0x70
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


@dataclass(frozen=True)
class Hotkey:
    label: str                  # para mostrarlo, p. ej. "Ctrl+Alt+→"
    mods: int
    vk: int
    action: Callable[[], None]


class GlobalHotkeys:
    def __init__(self, hotkeys: list[Hotkey]) -> None:
        self.hotkeys = hotkeys
        self.failed: list[str] = []  # atajos que ya usaba otro programa
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()

    def start(self) -> list[str]:
        """Registra los atajos. Devuelve los que no se pudieron registrar."""
        if sys.platform != "win32":
            return []
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)
        return self.failed

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2)

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # crea la cola de mensajes del hilo
        registered = []
        for i, hk in enumerate(self.hotkeys, start=1):
            if user32.RegisterHotKey(None, i, hk.mods | MOD_NOREPEAT, hk.vk):
                registered.append(i)
            else:
                self.failed.append(hk.label)
        if self.failed:
            log.warning("Atajos ocupados por otro programa: %s", ", ".join(self.failed))
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and 1 <= msg.wParam <= len(self.hotkeys):
                    try:
                        self.hotkeys[msg.wParam - 1].action()
                    except Exception:  # noqa: BLE001 - un atajo no debe tumbar el hilo
                        log.exception("Error en un atajo de teclado")
        finally:
            for i in registered:
                user32.UnregisterHotKey(None, i)
