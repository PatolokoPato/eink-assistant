"""Estado del asistente: conversación con el chatbot y página que se muestra.

Es independiente de tkinter: la ventana llama a `ask` desde un hilo de fondo y
la vista "Asistente" (ui/views.py) dibuja la página actual con `build`.
"""

from __future__ import annotations

import threading

from PIL import Image

from ai import ChatbotProvider, ClaudeProvider
from display.assistant import render_answer_pages, render_welcome


class Assistant:
    def __init__(self, provider: ChatbotProvider | None = None) -> None:
        self._provider = provider
        self._lock = threading.Lock()
        self.question: str | None = None
        self.answer: str | None = None
        self.history: list[tuple[str, str]] = []  # (pregunta, respuesta) de esta conversación
        self._pages: list[Image.Image] = []
        self.page = 0

    @property
    def provider(self) -> ChatbotProvider:
        if self._provider is None:
            self._provider = ClaudeProvider()
        return self._provider

    def ask(self, question: str) -> str:
        """Bloquea mientras el chatbot responde. Lanza ChatbotError si falla."""
        answer = self.provider.ask(question)
        pages = render_answer_pages(question, answer)
        with self._lock:
            self.question, self.answer, self._pages, self.page = question, answer, pages, 0
            self.history.append((question, answer))
        return answer

    def show_text(self, text: str, question: str = "") -> int:
        """Muestra un texto que viene de fuera (p. ej. Claude Desktop por MCP). Devuelve las páginas."""
        pages = render_answer_pages(question, text)
        with self._lock:
            self.question, self.answer, self._pages, self.page = question or None, text, pages, 0
        return len(pages)

    def reset(self) -> None:
        self.provider.reset()
        with self._lock:
            self.question = self.answer = None
            self.history, self._pages, self.page = [], [], 0

    @property
    def page_count(self) -> int:
        return max(1, len(self._pages))

    def go(self, delta: int) -> bool:
        """Cambia de página; devuelve False si ya estaba en el extremo."""
        with self._lock:
            new = min(max(self.page + delta, 0), self.page_count - 1)
            changed, self.page = new != self.page, new
            return changed

    def build(self) -> Image.Image:
        with self._lock:
            if not self._pages:
                return render_welcome(self.provider.name)
            return self._pages[self.page]


ASSISTANT = Assistant()
