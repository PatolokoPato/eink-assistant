"""Interfaz común para cualquier chatbot."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ChatbotError(Exception):
    """Fallo al consultar el chatbot, con un mensaje apto para mostrar al usuario."""


class ChatbotProvider(ABC):
    """Conversación con memoria: cada `ask` ve las preguntas y respuestas anteriores."""

    name: str = "chatbot"

    @abstractmethod
    def ask(self, question: str) -> str:
        """Envía la pregunta y devuelve la respuesta en texto plano. Bloquea."""

    @abstractmethod
    def reset(self) -> None:
        """Olvida la conversación."""
