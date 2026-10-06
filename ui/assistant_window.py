"""Ventana del asistente: escribir la pregunta, leer la conversación y pasar páginas.

La respuesta se envía sola a la E-Ink. La consulta al chatbot corre en un hilo
de fondo; el resultado vuelve a tkinter por la cola de la App (`post`).
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from ai import ChatbotError

from .assistant import ASSISTANT

log = logging.getLogger(__name__)


class AssistantWindow:
    def __init__(self, root: tk.Tk, *, post: Callable[[Callable[[], None]], None],
                 show_on_eink: Callable[[str], None]) -> None:
        self._post = post                  # ejecuta una función en el hilo de tkinter
        self._show_on_eink = show_on_eink  # activa una vista y la manda a la pantalla
        self._busy = False

        self.win = tk.Toplevel(root)
        self.win.title("Asistente — E-Ink Assistant")
        self.win.protocol("WM_DELETE_WINDOW", self.win.withdraw)
        self.win.withdraw()
        self._build()

    def _build(self) -> None:
        frm = ttk.Frame(self.win, padding=10)
        frm.grid(sticky="nsew")
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)

        # Conversación
        conv = ttk.Frame(frm)
        conv.grid(row=0, column=0, sticky="nsew")
        conv.columnconfigure(0, weight=1)
        conv.rowconfigure(0, weight=1)
        self.transcript = tk.Text(conv, width=70, height=18, wrap="word", state="disabled",
                                  font=("Segoe UI", 10), padx=8, pady=6, relief="solid", borderwidth=1)
        self.transcript.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(conv, command=self.transcript.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.transcript.configure(yscrollcommand=scroll.set)
        self.transcript.tag_configure("you", font=("Segoe UI", 10, "bold"))
        self.transcript.tag_configure("bot", font=("Segoe UI", 10, "bold"), foreground="#444")
        self.transcript.tag_configure("error", foreground="#b00020")

        # Páginas en la E-Ink
        pages = ttk.Frame(frm)
        pages.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.btn_prev = ttk.Button(pages, text="◀ Anterior", command=lambda: self._page(-1))
        self.btn_prev.pack(side="left")
        self.lbl_page = ttk.Label(pages, text="E-Ink: página 1 / 1", width=20, anchor="center")
        self.lbl_page.pack(side="left", padx=6)
        self.btn_next = ttk.Button(pages, text="Siguiente ▶", command=lambda: self._page(1))
        self.btn_next.pack(side="left")
        ttk.Button(pages, text="Volver a la pantalla principal",
                   command=lambda: self._show_on_eink("home")).pack(side="right")

        # Pregunta
        ttk.Label(frm, text="Tu pregunta (Intro para enviar, Mayús+Intro para nueva línea):").grid(
            row=2, column=0, sticky="w", pady=(10, 2))
        self.entry = tk.Text(frm, height=3, wrap="word", font=("Segoe UI", 11), padx=6, pady=4,
                             relief="solid", borderwidth=1)
        self.entry.grid(row=3, column=0, sticky="ew")
        self.entry.bind("<Return>", self._on_return)

        bottom = ttk.Frame(frm)
        bottom.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self.btn_send = ttk.Button(bottom, text="Enviar", command=self.send)
        self.btn_send.pack(side="right")
        ttk.Button(bottom, text="Nueva conversación", command=self._reset).pack(side="right", padx=6)
        self.lbl_status = ttk.Label(bottom, foreground="#555")
        self.lbl_status.pack(side="left")
        self._update_pages()

    # ---------------------------------------------------------------- acciones
    def open(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.entry.focus_set()

    def _on_return(self, event: tk.Event) -> str | None:
        if event.state & 0x0001:  # Mayús: salto de línea normal
            return None
        self.send()
        return "break"

    def send(self) -> None:
        question = self.entry.get("1.0", "end").strip()
        if not question or self._busy:
            return
        self._busy = True
        self.btn_send.configure(state="disabled")
        self.entry.delete("1.0", "end")
        self._append("Tú: ", "you", question)
        self.lbl_status.configure(text="Pensando…", foreground="#555")

        def work() -> None:
            try:
                answer = ASSISTANT.ask(question)
            except ChatbotError as e:
                self._post(lambda: self._done(error=str(e)))
                return
            except Exception as e:  # noqa: BLE001
                log.exception("Error consultando al chatbot")
                self._post(lambda: self._done(error=f"{type(e).__name__}: {e}"))
                return
            self._post(lambda: self._done(answer=answer))

        threading.Thread(target=work, name="chatbot", daemon=True).start()

    def _done(self, answer: str | None = None, error: str | None = None) -> None:
        self._busy = False
        self.btn_send.configure(state="normal")
        if error:
            self._append("⚠ ", "error", error, body_tag="error")
            self.lbl_status.configure(text="Error", foreground="#b00020")
            return
        self._append(f"{ASSISTANT.provider.name}: ", "bot", answer or "")
        self.lbl_status.configure(text="Respuesta enviada a la E-Ink", foreground="#1b7f3b")
        self._update_pages()
        self._show_on_eink("assistant")

    def note_external(self, text: str, question: str = "") -> None:
        """Registra en la conversación un texto llegado desde fuera (Claude Desktop por MCP)."""
        if question:
            self._append("Tú (Claude Desktop): ", "you", question)
        self._append("Claude Desktop: ", "bot", text)
        self.lbl_status.configure(text="Recibido desde Claude Desktop", foreground="#1b7f3b")
        self._update_pages()

    def refresh_pages(self) -> None:
        self._update_pages()

    def _reset(self) -> None:
        ASSISTANT.reset()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.lbl_status.configure(text="Conversación nueva", foreground="#555")
        self._update_pages()
        self._show_on_eink("assistant")

    def _page(self, delta: int) -> None:
        if ASSISTANT.go(delta):
            self._update_pages()
            self._show_on_eink("assistant")

    # ---------------------------------------------------------------- interno
    def _append(self, prefix: str, tag: str, text: str, body_tag: str | None = None) -> None:
        t = self.transcript
        t.configure(state="normal")
        if t.index("end-1c") != "1.0":
            t.insert("end", "\n\n")
        t.insert("end", prefix, tag)
        t.insert("end", text, body_tag or ())
        t.configure(state="disabled")
        t.see("end")

    def _update_pages(self) -> None:
        n, total = ASSISTANT.page + 1, ASSISTANT.page_count
        self.lbl_page.configure(text=f"E-Ink: página {n} / {total}")
        self.btn_prev.configure(state="normal" if n > 1 else "disabled")
        self.btn_next.configure(state="normal" if n < total else "disabled")
