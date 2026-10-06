"""Chatbot (Fase 4). Speech-to-Text (Fase 5) vendrá aquí también.

El resto de la aplicación solo usa ChatbotProvider; ClaudeProvider es la
implementación con la API de Anthropic.
"""

from .base import ChatbotError, ChatbotProvider
from .claude import ClaudeProvider

__all__ = ["ChatbotError", "ChatbotProvider", "ClaudeProvider"]
